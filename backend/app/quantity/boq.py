"""Keşif listesi (bill of quantities): tüm disiplinlerin metrajını tek tip kalem listesine çevirir.

Kalem anahtarı "<tür>:<grup>" biçimindedir; tür fiyat kategorisidir (beton, kalip, demir, duvar, siva, boya, pencere,
cam, kapi, tava, kablo, boru, armatur), grup eleman grubudur (kolon, ytong:20, NYY_4x16, 200x60, priz ...).
"<tür>:*" fiyat kalemi o türün genel fiyatıdır.

Statik:  beton / kalıp / demir (quantity.engine + summary'den)
Mimari:  duvar m² = uzunluk × duvar yüksekliği × kat çarpanı − kapı/pencere boşlukları (malzeme + kalınlık bazında)
         sıva m² = net duvar × sıva yüzü sayısı, boya m² = net duvar × boya yüzü sayısı
         pencere adet (ad / ölçü bazında), cam m² = pencere genişlik × yükseklik, kapı adet
Elektrik: tava m (boyut bazında), kablo m (kesit bazında; iniş payı × hat sayısı, fire %), boru m, armatür adet (kategori)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..parser.labels_ext import FIXTURE_CATEGORIES, WALL_MATERIALS
from ..parser.layer_profile import DISCIPLINES
from ..standard.catalog import Catalog, parse_layer, spec_numbers

# tür -> (görünen ad, birim, disiplin)
KIND_META: dict[str, tuple[str, str, str]] = {
    "beton": ("Beton", "m³", "structural"),
    "kalip": ("Kalıp", "m²", "structural"),
    "demir": ("Demir", "kg", "structural"),
    "duvar": ("Duvar", "m²", "architectural"),
    "siva": ("Sıva", "m²", "architectural"),
    "boya": ("Boya", "m²", "architectural"),
    "pencere": ("Pencere", "adet", "architectural"),
    "cam": ("Cam", "m²", "architectural"),
    "kapi": ("Kapı", "adet", "architectural"),
    "tava": ("Kablo tavası", "m", "electrical"),
    "kablo": ("Kablo", "m", "electrical"),
    "boru": ("Boru", "m", "electrical"),
    "armatur": ("Armatür / priz / anahtar", "adet", "electrical"),
}

DEFAULT_PARAMS: dict[str, Any] = {
    "wall_height": None,          # m; None -> kat yüksekliği − döşeme kalınlığı
    "plaster_sides": 2,           # sıva yüzü sayısı (0 = sıva yok)
    "paint_sides": 2,             # boya yüzü sayısı
    "cable_drop": 0.0,            # her kablo hattına eklenen iniş/çıkış payı (m)
    "cable_waste_pct": 5.0,       # kablo fire %
    "tray_waste_pct": 5.0,
    "work_hours_per_day": 8.0,    # süre hesabı: günlük çalışma saati
}


def effective_params(raw: dict[str, Any] | None) -> dict[str, Any]:
    p = dict(DEFAULT_PARAMS)
    for k, v in (raw or {}).items():
        if k in p:
            p[k] = v
    return p


def slug(s: str) -> str:
    s = s.strip().replace("ı", "i").replace("İ", "I").replace("ş", "s").replace("Ş", "S").replace("ğ", "g").replace("Ğ", "G")
    s = s.replace("ç", "c").replace("Ç", "C").replace("ö", "o").replace("Ö", "O").replace("ü", "u").replace("Ü", "U")
    s = re.sub(r"[ØøΦφ∅]", "o", s)
    s = re.sub(r"[^A-Za-z0-9.+/x×-]+", "_", s)
    return s.strip("_").lower() or "x"


@dataclass
class BoqItem:
    key: str
    kind: str
    group: str
    label: str
    unit: str
    quantity: float
    discipline: str
    kind_label: str = ""
    discipline_label: str = ""
    count: float = 0.0                     # adet (eleman/hat sayısı) bilgi amaçlı
    notes: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.kind_label:
            self.kind_label = KIND_META.get(self.kind, (self.kind,))[0]
        if not self.discipline_label:
            self.discipline_label = DISCIPLINES.get(self.discipline, self.discipline)

    def to_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "kind_label": self.kind_label, "group": self.group,
                "label": self.label, "unit": self.unit, "quantity": round(self.quantity, 3), "count": self.count,
                "discipline": self.discipline, "discipline_label": self.discipline_label,
                "notes": self.notes, "detail": self.detail}


class _Acc:
    def __init__(self):
        self.items: dict[str, BoqItem] = {}

    def add(self, kind: str, group: str, label: str, qty: float, count: float = 0.0, note: str | None = None,
            meta: tuple[str, str, str, str] | None = None, **detail) -> BoqItem:
        """meta: (tür adı, birim, disiplin kodu, disiplin adı) — KIND_META dışındaki (katalog) kalemler için."""
        key = f"{kind}:{group}"
        it = self.items.get(key)
        if it is None:
            if meta:
                kname, unit, disc, dlabel = meta
            else:
                kname, unit, disc = KIND_META[kind]
                dlabel = DISCIPLINES.get(disc, disc)
            it = BoqItem(key=key, kind=kind, group=group, label=label, unit=unit, quantity=0.0, discipline=disc,
                         kind_label=kname, discipline_label=dlabel)
            self.items[key] = it
        it.quantity += qty
        it.count += count
        if note and note not in it.notes:
            it.notes.append(note)
        for k, v in detail.items():
            it.detail[k] = it.detail.get(k, 0) + v if isinstance(v, (int, float)) else v
        return it


# ------------------------------------------------------------------ statik

def structural_items(summary: dict) -> list[BoqItem]:
    acc = _Acc()
    field_kind = (("concrete_m3", "beton"), ("formwork_m2", "kalip"), ("rebar_kg", "demir"))
    for g in summary.get("groups", []):
        for fld, kind in field_kind:
            if g.get(fld, 0) > 0:
                acc.add(kind, g["key"], f"{KIND_META[kind][0]} - {g['label']}", g[fld], count=g.get("element_count", 0))
    return list(acc.items.values())


# ------------------------------------------------------------------ mimari

def _fmt_cm(v: float | None) -> str:
    return f"{round(v * 100):.0f}" if v else "?"


def architectural_items(drawings: list[dict], params: dict[str, Any]) -> list[BoqItem]:
    """drawings: [{"label", "storey_count", "storey_height", "slab_thickness", "elements": [Element-benzeri]}]"""
    acc = _Acc()
    for d in drawings:
        mult = int(d.get("storey_count") or 1)
        wall_h = params.get("wall_height") or max((d.get("storey_height") or 3.0) - (d.get("slab_thickness") or 0.0), 0.0)
        elements = [e for e in d["elements"] if _g(e, "etype") in ("wall", "door", "window")]
        wall_groups: dict[str, float] = {}      # anahtar -> brüt alan (tek kat)
        wall_labels: dict[str, str] = {}
        for e in elements:
            if _g(e, "etype") != "wall":
                continue
            b = _g(e, "b") or 0.2
            length = _g(e, "length") or 0.0
            h = _g(e, "h") or wall_h                 # duvar elemanına özel yükseklik girilmişse o
            mat = _g(e, "subtype") or "duvar"
            key = f"{slug(mat)}:{_fmt_cm(b)}"
            mat_label = WALL_MATERIALS.get(mat, (mat.capitalize(),))[0] if mat != "duvar" else "Duvar (malzeme belirsiz)"
            wall_groups[key] = wall_groups.get(key, 0.0) + length * h * (_g(e, "count") or 1)
            wall_labels[key] = f"{mat_label} {_fmt_cm(b)} cm"
        opening_area = 0.0
        for e in elements:
            et = _g(e, "etype")
            if et not in ("door", "window"):
                continue
            b, h = _g(e, "b") or 0.0, _g(e, "h") or 0.0
            n = _g(e, "count") or 1
            area = b * h * n
            opening_area += area
            name = _g(e, "name") or f"{_fmt_cm(b)}x{_fmt_cm(h)}"
            group = slug(f"{name}_{_fmt_cm(b)}x{_fmt_cm(h)}")
            kind = "kapi" if et == "door" else "pencere"
            acc.add(kind, group, f"{KIND_META[kind][0]} {name} ({_fmt_cm(b)}×{_fmt_cm(h)} cm)", n * mult, count=n * mult,
                    width_cm=0, area_m2=area * mult)
            if et == "window":
                acc.add("cam", "*", "Cam (pencere alanı)", area * mult, count=n * mult,
                        note="Pencere genişlik × yükseklik; doğrama payı düşülmedi")
        gross = sum(wall_groups.values())
        # boşluklar duvar gruplarından alanlarıyla orantılı düşülür
        net_total = 0.0
        for key, area in wall_groups.items():
            share = opening_area * (area / gross) if gross > 0 else 0.0
            net = max(area - share, 0.0) * mult
            net_total += net
            note = f"{d.get('label', '')}: brüt {area*mult:.1f} m², boşluk −{share*mult:.1f} m²" if share > 0 else None
            acc.add("duvar", key, wall_labels[key], net, note=note, gross_m2=area * mult, openings_m2=share * mult)
        if net_total > 0:
            ps, bs = float(params.get("plaster_sides") or 0), float(params.get("paint_sides") or 0)
            if ps > 0:
                acc.add("siva", "*", f"Sıva ({ps:g} yüz)", net_total * ps, note="Net duvar alanı × yüz sayısı")
            if bs > 0:
                acc.add("boya", "*", f"Boya ({bs:g} yüz)", net_total * bs, note="Net duvar alanı × yüz sayısı")
    return list(acc.items.values())


# ------------------------------------------------------------------ elektrik

def electrical_items(drawings: list[dict], params: dict[str, Any]) -> list[BoqItem]:
    acc = _Acc()
    drop = float(params.get("cable_drop") or 0.0)
    cw = 1.0 + float(params.get("cable_waste_pct") or 0.0) / 100.0
    tw = 1.0 + float(params.get("tray_waste_pct") or 0.0) / 100.0
    for d in drawings:
        mult = int(d.get("storey_count") or 1)
        for e in d["elements"]:
            et = _g(e, "etype")
            n = _g(e, "count") or 1
            if et == "tray":
                spec = _g(e, "subtype") or "boyut_belirsiz"
                acc.add("tava", slug(spec), f"Kablo tavası {spec} mm", (_g(e, "length") or 0.0) * n * mult * tw, count=n * mult,
                        note=f"Fire %{(tw-1)*100:g} dahil" if tw > 1 else None)
            elif et == "cable":
                spec = _g(e, "subtype") or "kesit_belirsiz"
                L = ((_g(e, "length") or 0.0) + drop) * n * mult * cw
                acc.add("kablo", slug(spec), f"Kablo {spec}", L, count=n * mult,
                        note=("İniş payı " + f"{drop:g} m/hat, " if drop else "") + (f"fire %{(cw-1)*100:g}" if cw > 1 else "") or None)
            elif et == "conduit":
                spec = _g(e, "subtype") or "cap_belirsiz"
                acc.add("boru", slug(spec), f"Boru {spec}", (_g(e, "length") or 0.0) * n * mult, count=n * mult)
            elif et == "fixture":
                cat = _g(e, "subtype") or "diger"
                label = FIXTURE_CATEGORIES.get(cat, ("Diğer eleman",))[0]
                name = _g(e, "name") or ""
                group = slug(f"{cat}_{name}") if name else slug(cat)
                acc.add("armatur", group, f"{label}" + (f" ({name})" if name else ""), n * mult, count=n * mult)
    return list(acc.items.values())


def _g(o: Any, k: str, default=None):
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


# ------------------------------------------------------------------ KSF standart çizim

def standard_items(drawings: list[dict], params: dict[str, Any], catalog: Catalog) -> list[BoqItem]:
    """Standart çizim elemanları: katman adından kalem + özellik, katalogdan ölçüm kuralı.
    Disiplin anahtarı 'ksf:<KOD>' (ör. ksf:HAV) — sezgisel disiplinlerle çakışmaz."""
    acc = _Acc()
    for d in drawings:
        mult = int(d.get("storey_count") or 1)
        wall_h_default = params.get("wall_height") or max((d.get("storey_height") or 3.0) - (d.get("slab_thickness") or 0.0), 0.0)
        for e in d["elements"]:
            p = parse_layer(_g(e, "layer") or "", catalog)
            if p is None:
                continue
            item = p.item
            measure = item.measure if item else None
            spec = _g(e, "subtype") or p.spec
            n = _g(e, "count") or 1
            length = _g(e, "length") or 0.0
            area = _g(e, "area") or 0.0
            nums = spec_numbers(spec)
            note = None
            if measure is None:
                # katalog dışı: geometriye göre
                if length > 0:
                    measure = "length"
                elif area > 0:
                    measure = "area"
                else:
                    measure = "count"
                note = "Katalogda yok; geometriye göre ölçüldü"
            if measure == "count":
                qty = n
            elif measure == "length":
                qty = length * n
            elif measure == "area":
                qty = area * n
            elif measure == "wall_area":
                h = _g(e, "h") or (nums[1] / 100.0 if len(nums) >= 2 and nums[1] > 50 else None) or wall_h_default
                qty = length * h * n
                note = f"uzunluk × yükseklik {h:g} m"
            else:  # volume
                t = _g(e, "thickness") or (nums[0] / 100.0 if nums else None)
                if not t:
                    t = 0.0
                    note = "Kalınlık özellikte yok (ör. KSF-STA-DOLGU-30); hacim 0"
                else:
                    note = f"alan × kalınlık {t:g} m"
                qty = area * t * n
            kind = p.code.lower()
            unit = item.unit if item else {"count": "adet", "length": "m", "area": "m²"}.get(measure, "")
            kname = item.name if item else p.code
            disc_key = f"ksf:{p.discipline}"
            group = slug(spec) if spec else "*"
            label = f"{kname}" + (f" {spec}" if spec else "")
            acc.add(kind, group, label, qty * mult, count=n * mult, note=note,
                    meta=(kname, unit, disc_key, catalog.discipline_name(p.discipline)))
    return list(acc.items.values())


# ------------------------------------------------------------------ birleşik

KIND_ORDER = list(KIND_META)


def sort_items(items: list[BoqItem]) -> list[BoqItem]:
    def k(i: BoqItem):
        return (KIND_ORDER.index(i.kind) if i.kind in KIND_META else 100, i.discipline, i.kind_label, i.group != "*", i.label)
    return sorted(items, key=k)


def boq_summary(items: list[BoqItem]) -> dict:
    by_disc: dict[str, tuple[str, list[dict]]] = {}
    for it in sort_items(items):
        by_disc.setdefault(it.discipline, (it.discipline_label, []))[1].append(it.to_dict())
    kinds = {k: {"label": v[0], "unit": v[1], "discipline": v[2]} for k, v in KIND_META.items()}
    for it in items:
        kinds.setdefault(it.kind, {"label": it.kind_label, "unit": it.unit, "discipline": it.discipline})
    return {
        "items": [it.to_dict() for it in sort_items(items)],
        "by_discipline": [{"discipline": d, "label": lbl, "items": its} for d, (lbl, its) in by_disc.items()],
        "kinds": kinds,
    }
