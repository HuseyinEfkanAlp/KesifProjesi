"""Keşif kalemi -> malzeme (ürün) eşlemesi.

Malzeme fiyatı **ürüne** girilir (C30/37 hazır beton, Ø12 nervürlü demir, Ytong 20 cm), işçilik fiyatı keşif
kalemine (poza). Aynı ürünü kullanan bütün kalemler tek fiyattan hesaplanır: kolon, perde, kiriş ve döşeme
betonu aynı "C30/37 hazır beton" satırından; Ø12 demir hangi elemanda geçerse geçsin tek satır.

Ürün anahtarı "<tür>:<ürün>" biçimindedir ve keşif kalemi anahtarından farklı olabilir:
    beton:column, beton:shear_wall, beton:fire    -> beton:c30_37    (eleman tipine atanan sınıf)
    grobeton:10                                   -> beton:c16_20    (grobeton sınıfı)
    demir:o12                                     -> demir:o12       (donatı tablosundan: çap bazında)
    demir:column, demir:fire                      -> demir:karisik   (oranla gelen: çap dağılımı bilinmiyor)
    kalip:column, kalip:slab                      -> kalip:plywood   (kalıp malzemesi)
    duvar:ytong:20, kablo:nyy_4x16, kapi:k1_90x210 -> kalemin kendisi (zaten ürün bazında gruplanmış)

Birimi "saat" olan kalemler (kalıp işçiliği, demir işçiliği, montaj saatleri) salt işçiliktir; malzemesi yoktur.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..parser.layer_profile import STRUCTURAL_TYPES
from ..quantity.boq import BoqItem
from ..standard.rules import WORK_GROUPS

DEFAULT_CONCRETE_CLASS = "C30/37"
DEFAULT_LEAN_CLASS = "C16/20"
DEFAULT_REBAR_GRADE = "B420C"
DEFAULT_FORMWORK = "plywood"

# Beton sınıfı atanabilen statik eleman tipleri (parametre adı: concrete_class_<tip>)
CONCRETE_TYPES: dict[str, str] = {
    "foundation": "Temel",
    "column": "Kolon",
    "shear_wall": "Perde",
    "beam": "Kiriş",
    "slab": "Döşeme",
}
CONCRETE_CLASSES = ["C16/20", "C20/25", "C25/30", "C30/37", "C35/45", "C40/50", "C45/55", "C50/60"]
REBAR_GRADES = ["B420C", "B500C", "S220"]
FORMWORK_MATERIALS: dict[str, str] = {
    "plywood": "Plywood kalıp",
    "ahsap": "Ahşap (kereste) kalıp",
    "celik": "Çelik / hazır kalıp",
    "tunel": "Tünel kalıp",
}
LABOR_UNITS = {"saat", "sa", "adam-saat"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")


def rebar_dia(group: str) -> str:
    """Demir kaleminin grubundan çap: "o12", "12", "12MM", "Ø14" -> "12" / "14"; çap değilse "".

    Çap donatı tablosundan "o12" biçiminde gelir, KSF katmanından (KSF-STA-DEMIR-12) yalnız sayı olarak."""
    m = re.fullmatch(r"[oø∅]?(\d+(?:[.,]\d+)?)\s*(?:mm)?", (group or "").strip().lower().rsplit(":", 1)[-1])
    if not m:
        return ""
    d = m.group(1).replace(",", ".")
    return d[:-2] if d.endswith(".0") else d


def _is_element_group(group: str) -> bool:
    """Grup bir statik eleman tipi mi (kolon, perde…) — çapı bilinmeyen, oranla gelen demir."""
    g = (group or "").split(":")[0]
    return g in STRUCTURAL_TYPES or g in ("*", "fire", "")


def concrete_class_for(group: str, params: dict) -> str:
    """Eleman tipine atanan beton sınıfı; tipe özel boşsa projenin genel sınıfı."""
    etype = (group or "").split(":")[0]
    own = str(params.get(f"concrete_class_{etype}") or "").strip()
    return own or str(params.get("concrete_class") or "").strip() or DEFAULT_CONCRETE_CLASS


def is_labor_only(item: BoqItem) -> bool:
    """Salt işçilik kalemi (birimi saat): malzeme fiyatı istenmez."""
    return (item.unit or "").strip().lower() in LABOR_UNITS


def material_of(item: BoqItem, params: dict | None = None) -> tuple[str, str] | None:
    """(ürün anahtarı, ürün adı). None: kalemin malzemesi yok (salt işçilik, sistem başlığı, bilgi satırı)."""
    params = params or {}
    if item.detail.get("system") or item.detail.get("info") or is_labor_only(item):
        return None
    kind, group = item.kind, item.group
    if kind == "beton":
        c = concrete_class_for(group, params)
        return f"beton:{_slug(c)}", f"Hazır beton {c}"
    if kind == "grobeton":
        c = str(params.get("lean_concrete_class") or "").strip() or DEFAULT_LEAN_CLASS
        return f"beton:{_slug(c)}", f"Hazır beton {c}"
    if kind == "demir":
        grade = str(params.get("rebar_grade") or "").strip() or DEFAULT_REBAR_GRADE
        dia = rebar_dia(group)
        if dia:
            return f"demir:o{dia}", f"Nervürlü inşaat demiri Ø{dia} ({grade})"
        if _is_element_group(group):
            return "demir:karisik", f"Nervürlü inşaat demiri, çap karışık ({grade})"
        return item.key, item.label       # hasır çelik gibi çap dışı özellik: kendi ürünü
    if kind == "kalip":
        code = _slug(str(params.get("formwork_material") or "")) or DEFAULT_FORMWORK
        return f"kalip:{code}", FORMWORK_MATERIALS.get(code, f"Kalıp malzemesi ({code})")
    return item.key, item.label       # kalemin kendisi zaten ürün (duvar malzemesi, kablo kesiti, kapı tipi…)


@dataclass
class MaterialData:
    """Bir ürünün fiyat satırı (kullanıcı girer)."""
    key: str
    name: str
    unit: str
    unit_price: float = 0.0
    brand: str = ""


@dataclass
class MaterialLine:
    """Keşiften türeyen ürün satırı: aynı ürünü kullanan kalemler tek satırda toplanır."""
    key: str
    name: str
    unit: str
    kind: str
    kind_label: str = ""
    work_group: str = ""
    work_group_label: str = ""
    quantity: float = 0.0
    items: list[dict] = field(default_factory=list)     # {"key", "label", "quantity"}

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "unit": self.unit, "kind": self.kind,
                "kind_label": self.kind_label, "work_group": self.work_group, "work_group_label": self.work_group_label,
                "quantity": round(self.quantity, 3), "items": self.items}


def material_lines(items: list[BoqItem], params: dict | None = None) -> list[MaterialLine]:
    """Keşif listesinden ürün listesi (miktarlar toplanmış, hangi kalemden geldiği ayrıntıda)."""
    out: dict[str, MaterialLine] = {}
    for it in items:
        m = material_of(it, params)
        if m is None:
            continue
        key, name = m
        line = out.get(key)
        if line is None:
            line = MaterialLine(key=key, name=name, unit=it.unit, kind=it.kind, kind_label=it.kind_label,
                                work_group=it.work_group, work_group_label=WORK_GROUPS.get(it.work_group, it.work_group))
            out[key] = line
        line.quantity += max(it.quantity, 0.0)
        if it.quantity > 0 and len(line.items) < 40:
            line.items.append({"key": it.key, "label": it.label, "quantity": round(it.quantity, 3)})
    return list(out.values())
