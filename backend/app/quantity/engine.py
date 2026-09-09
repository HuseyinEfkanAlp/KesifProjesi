"""Eleman bazlı beton (m³), kalıp (m²) ve demir (kg) metrajı.

Formüller:
  Kolon      beton = alan × Hk                kalıp = çevre × Hf
  Perde      beton = alan × Hk                kalıp = 2 × uzunluk × Hf
  Kiriş      beton = b × hk × L               kalıp = (b + 2 × hk) × L
  Döşeme     beton = alan × kalınlık          kalıp = alan
  Radye      beton = alan × kalınlık          kalıp = çevre × kalınlık
  Sürekli T. beton = b × h × L                kalıp = 2 × L × h
  Demir      kg = beton × oran(kg/m³, eleman tipine göre)
H: kat yüksekliği, d: döşeme kalınlığı.
  Döşeme brüt alanla ölçülüyorsa (döşeme çokgeni kolonu da kapsar): Hk = H − d, hk = h − d.
  Döşeme kirişler arası NET alansa (beam_full_height): kolon döşeme kalınlığı boyunca da tek sayılır -> Hk = H, hk = h.
  Kolon/perde kalıbı kiriş altına kadar: Hf = H − (kattaki baskın kiriş yüksekliği; yoksa d).
Temel dışındaki her kalem kat sayısı ile çarpılır.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Beton × kg/m³ oran tahmini: yalnız donatı paftası yüklenmemişse kullanılır (düşük güven). Değerler Türkiye'de
# betonarme konut / ticari yapı için yaygın aralıkların orta noktasıdır; gerçek projede (KIYI A4-A5 AVM, 2023) kolon 374,
# kiriş 178, radye 97, döşeme 82 kg/m³ ölçüldü — kolon ve kiriş için eski varsayılanlar (130 / 110) çok düşüktü.
DEFAULT_REBAR_RATIOS: dict[str, float] = {
    "column": 180.0,
    "shear_wall": 140.0,
    "beam": 140.0,
    "slab": 85.0,
    "foundation": 95.0,
    "parapet": 100.0,
    "stair": 120.0,
}


@dataclass
class QuantityParams:
    storey_height: float = 3.0        # H (m)
    slab_thickness: float = 0.15      # d (m) - kiriş/kolon net yüksekliği için düşülür
    storey_count: int = 1             # bu planın temsil ettiği kat sayısı
    beam_full_height: bool = False    # True: kiriş b×h×L ve kolon alan×H (döşemeler net alan ise); False: b×(h−d)×L, alan×(H−d)
    beam_depth: float | None = None   # kattaki baskın kiriş yüksekliği (m); kolon/perde kalıbı H − beam_depth; etiketsiz kirişe varsayılan h
    rebar_ratios: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_REBAR_RATIOS))

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "QuantityParams":
        d = d or {}
        ratios = dict(DEFAULT_REBAR_RATIOS)
        ratios.update({k: float(v) for k, v in (d.get("rebar_ratios") or {}).items()})
        return cls(
            storey_height=float(d.get("storey_height", 3.0)),
            slab_thickness=float(d.get("slab_thickness", 0.15)),
            storey_count=int(d.get("storey_count", 1)),
            beam_full_height=bool(d.get("beam_full_height", False)),
            beam_depth=float(d["beam_depth"]) if d.get("beam_depth") is not None else None,
            rebar_ratios=ratios,
        )

    def to_dict(self) -> dict:
        return {"storey_height": self.storey_height, "slab_thickness": self.slab_thickness,
                "storey_count": self.storey_count, "beam_full_height": self.beam_full_height,
                "beam_depth": self.beam_depth, "rebar_ratios": dict(self.rebar_ratios)}


@dataclass
class ElementData:
    """Dedektör çıktısı ya da veritabanı kaydından bağımsız, metraj için gereken alanlar."""
    id: int | str | None
    etype: str
    name: str | None = None
    subtype: str | None = None
    b: float | None = None
    h: float | None = None
    thickness: float | None = None
    area: float = 0.0
    length: float = 0.0
    perimeter: float = 0.0
    count: int = 1

    @classmethod
    def from_obj(cls, o: Any, id: Any = None) -> "ElementData":
        g = (lambda k, d=None: o.get(k, d)) if isinstance(o, dict) else (lambda k, d=None: getattr(o, k, d))
        return cls(id=id if id is not None else g("id"), etype=g("etype"), name=g("name"), subtype=g("subtype"),
                   b=g("b"), h=g("h"), thickness=g("thickness"), area=g("area", 0.0) or 0.0,
                   length=g("length", 0.0) or 0.0, perimeter=g("perimeter", 0.0) or 0.0, count=g("count", 1) or 1)


@dataclass
class QuantityLine:
    element_id: Any
    etype: str
    name: str | None
    subtype: str | None
    count: int
    multiplier: int
    concrete_m3: float      # tek kat, tek eleman
    formwork_m2: float
    rebar_kg: float
    notes: list[str] = field(default_factory=list)

    @property
    def total_concrete(self) -> float:
        return self.concrete_m3 * self.count * self.multiplier

    @property
    def total_formwork(self) -> float:
        return self.formwork_m2 * self.count * self.multiplier

    @property
    def total_rebar(self) -> float:
        return self.rebar_kg * self.count * self.multiplier

    def to_dict(self) -> dict:
        return {
            "element_id": self.element_id, "etype": self.etype, "name": self.name, "subtype": self.subtype,
            "count": self.count, "multiplier": self.multiplier,
            "concrete_m3": round(self.concrete_m3, 4), "formwork_m2": round(self.formwork_m2, 4),
            "rebar_kg": round(self.rebar_kg, 2),
            "total_concrete_m3": round(self.total_concrete, 4), "total_formwork_m2": round(self.total_formwork, 4),
            "total_rebar_kg": round(self.total_rebar, 2), "notes": self.notes,
        }


def compute_element(el: ElementData, p: QuantityParams) -> QuantityLine:
    notes: list[str] = []
    H, d = p.storey_height, p.slab_thickness
    conc_h = H if p.beam_full_height else max(H - d, 0.0)          # kolon/perde beton yüksekliği
    form_h = max(H - (p.beam_depth if p.beam_depth else d), 0.0)   # kolon/perde kalıp yüksekliği (kiriş altına kadar)
    concrete = formwork = 0.0
    multiplier = p.storey_count

    if el.etype == "column":
        concrete = el.area * conc_h
        formwork = el.perimeter * form_h
    elif el.etype == "shear_wall":
        concrete = el.area * conc_h
        formwork = 2.0 * el.length * form_h
    elif el.etype == "beam":
        h = el.h
        if not h and el.b and p.beam_depth:
            # etiketsiz kiriş: kattaki baskın kiriş yüksekliği varsayılır (kullanıcı düzeltebilir)
            h = p.beam_depth
            notes.append(f"Kesit etiketi yok; kattaki baskın kiriş yüksekliği ({h*100:.0f} cm) alındı")
        if not h or el.b is None:
            notes.append("Kiriş kesiti (b/h) eksik; beton ve kalıp 0 alındı")
        else:
            web = h if p.beam_full_height else max(h - d, 0.0)     # beton: net döşeme modunda tam yükseklik
            side = max(h - d, 0.0)                                   # yan kalıp döşeme altına kadar (ÇŞB 15.180: kalıp gören yüz)
            concrete = el.b * web * el.length
            if p.beam_full_height:
                formwork = (el.b + 2.0 * side) * el.length           # net döşeme: kiriş alt yüzü döşeme kalıbında değil
            else:
                formwork = 2.0 * side * el.length                    # brüt döşeme çokgeni kirişi kapsar: alt yüz döşeme kalıbında sayıldı
    elif el.etype == "slab":
        t = el.thickness if el.thickness is not None else d
        concrete = el.area * t
        formwork = el.area
    elif el.etype == "parapet":
        if not (el.b and el.h):
            notes.append("Parapet kesiti (b/h) eksik; 0 alındı")
        else:
            concrete = el.b * el.h * el.length
            formwork = 2.0 * el.h * el.length
    elif el.etype == "foundation":
        multiplier = 1
        if el.subtype == "strip":
            if el.b is None or el.h is None:
                notes.append("Sürekli temel kesiti eksik; 0 alındı")
            else:
                concrete = el.b * el.h * el.length
                formwork = 2.0 * el.length * el.h
        else:
            t = el.thickness if el.thickness is not None else 0.0
            if t <= 0:
                notes.append("Radye kalınlığı eksik; 0 alındı")
            concrete = el.area * t
            formwork = el.perimeter * t
    else:
        notes.append(f"Bilinmeyen eleman tipi: {el.etype}")

    rebar = concrete * p.rebar_ratios.get(el.etype, 0.0)
    return QuantityLine(element_id=el.id, etype=el.etype, name=el.name, subtype=el.subtype,
                        count=int(el.count or 1), multiplier=multiplier,
                        concrete_m3=concrete, formwork_m2=formwork, rebar_kg=rebar, notes=notes)


def compute_all(elements: list[ElementData], p: QuantityParams) -> list[QuantityLine]:
    return [compute_element(e, p) for e in elements]
