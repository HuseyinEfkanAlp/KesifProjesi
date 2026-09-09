"""Keşif kalemi × (malzeme + işçilik birim fiyatı) = maliyet; × adam-saat/birim = süre.

Fiyat kalemi anahtarı: "<tür>:<grup>" (bkz. quantity.boq). "<tür>:*" o türün genel fiyatıdır; kaleme özel
fiyat girilmemişse genel fiyat kullanılır. Marka bilgi amaçlıdır (raporda görünür).

Süre: kalem saati = miktar × adam-saat/birim; kalem günü = saat / (ekip × günlük saat).
  - "ardışık" toplam: tüm kalem günlerinin toplamı (tek ekip her işi sırayla yapar)
  - "disiplin bazlı": her disiplinin toplam günü; disiplinler paralel çalışırsa süre = en uzun disiplin
"""
from __future__ import annotations

from dataclasses import dataclass

from ..quantity.boq import KIND_META, BoqItem

# Geriye uyumluluk (eski içe aktarmalar)
QUANTITY_KINDS: dict[str, tuple[str, str]] = {k: (v[0], v[1]) for k, v in KIND_META.items()}


@dataclass
class PriceItem:
    key: str
    name: str
    unit: str
    unit_price: float = 0.0        # malzeme
    labor_price: float = 0.0       # işçilik
    brand: str = ""
    hours_per_unit: float = 0.0    # adam-saat / birim
    crew_size: float = 0.0         # 0 = belirtilmedi (genel satır ya da 1 kişi)
    set_fields: tuple[str, ...] = ()   # kullanıcının açıkça girdiği alanlar: 0 girildiyse genel satıra düşülmez


def default_price_items(items: list[BoqItem]) -> list[PriceItem]:
    """Keşifteki her kalem için sıfır fiyatlı satır + her tür için genel satır (kullanıcı doldurur)."""
    out: list[PriceItem] = []
    seen: set[str] = set()
    for it in items:
        if it.detail.get("system") or it.detail.get("info"):
            continue   # katmanlı sistem başlığı / bilgi satırı: fiyatlanmaz
        if it.kind not in seen:
            seen.add(it.kind)
            out.append(PriceItem(f"{it.kind}:*", f"{it.kind_label} (genel)", it.unit))
    for it in items:
        if it.group != "*" and not (it.detail.get("system") or it.detail.get("info")):
            out.append(PriceItem(it.key, it.label, it.unit))
    return out


def compute_cost(items: list[BoqItem], prices: list[PriceItem], vat_rate: float = 0.0,
                 hours_per_day: float = 8.0) -> dict:
    price_map = {p.key: p for p in prices}
    hours_per_day = hours_per_day if hours_per_day and hours_per_day > 0 else 8.0
    lines = []
    for it in items:
        if it.quantity <= 0 or it.detail.get("system") or it.detail.get("info"):
            continue
        own = price_map.get(it.key)
        gen = price_map.get(f"{it.kind}:*")

        def pick(attr: str, default=0.0):
            v = getattr(own, attr, None) if own else None
            explicit = bool(own) and attr in (getattr(own, "set_fields", None) or [])
            if explicit and v is not None:
                return v, "özel"           # açıkça girilen 0 da özeldir (işçiliği yok / ekip yok)
            if v not in (None, 0, 0.0, ""):
                return v, "özel"
            g = getattr(gen, attr, None) if gen else None
            if g not in (None, 0, 0.0, ""):
                return g, "genel"
            return default, "girilmedi"

        mat, mat_src = pick("unit_price")
        lab, lab_src = pick("labor_price")
        hpu, _ = pick("hours_per_unit")
        crew, _ = pick("crew_size", 1.0)
        brand, _ = pick("brand", "")
        hours = it.quantity * float(hpu)
        days = hours / (max(float(crew), 0.01) * hours_per_day) if hours > 0 else 0.0
        mat_total = round(it.quantity * float(mat), 2)
        lab_total = round(it.quantity * float(lab), 2)
        lines.append({
            "key": it.key, "kind": it.kind, "kind_label": it.kind_label,
            "group": it.group, "group_label": it.label, "discipline": it.discipline,
            "discipline_label": it.discipline_label,
            "unit": it.unit, "quantity": round(it.quantity, 3),
            "work_group": it.work_group, "work_group_label": it.to_dict()["work_group_label"], "poz": it.poz,
            "recipe": bool(it.detail.get("recipe")),
            "brand": brand or "",
            "unit_price": float(mat), "labor_price": float(lab),
            "material_total": mat_total, "labor_total": lab_total, "total": round(mat_total + lab_total, 2),
            "price_source": mat_src if mat else "fiyat girilmedi",
            "labor_source": lab_src if lab else "işçilik girilmedi",
            "hours_per_unit": float(hpu), "crew_size": float(crew),
            "hours": round(hours, 1), "days": round(days, 2),
        })
    material_subtotal = round(sum(l["material_total"] for l in lines), 2)
    labor_subtotal = round(sum(l["labor_total"] for l in lines), 2)
    subtotal = round(material_subtotal + labor_subtotal, 2)
    vat = round(subtotal * vat_rate, 2)
    by_kind: dict[str, float] = {}
    by_disc: dict[str, dict] = {}
    by_group: dict[str, dict] = {}
    for l in lines:
        by_kind[l["kind"]] = round(by_kind.get(l["kind"], 0.0) + l["total"], 2)
        g = by_group.setdefault(l["work_group"], {"group": l["work_group"], "label": l["work_group_label"],
                                                  "material": 0.0, "labor": 0.0, "total": 0.0, "hours": 0.0, "days": 0.0, "lines": 0})
        g["material"] = round(g["material"] + l["material_total"], 2)
        g["labor"] = round(g["labor"] + l["labor_total"], 2)
        g["total"] = round(g["total"] + l["total"], 2)
        g["hours"] = round(g["hours"] + l["hours"], 1)
        g["days"] = round(g["days"] + l["days"], 2)
        g["lines"] += 1
        d = by_disc.setdefault(l["discipline"], {"discipline": l["discipline"], "label": l["discipline_label"],
                                                 "material": 0.0, "labor": 0.0, "total": 0.0, "hours": 0.0, "days": 0.0})
        d["material"] = round(d["material"] + l["material_total"], 2)
        d["labor"] = round(d["labor"] + l["labor_total"], 2)
        d["total"] = round(d["total"] + l["total"], 2)
        d["hours"] = round(d["hours"] + l["hours"], 1)
        d["days"] = round(d["days"] + l["days"], 2)
    total_hours = round(sum(l["hours"] for l in lines), 1)
    sequential_days = round(sum(l["days"] for l in lines), 1)
    parallel_days = round(max((d["days"] for d in by_disc.values()), default=0.0), 1)
    return {
        "lines": lines,
        "material_subtotal": material_subtotal, "labor_subtotal": labor_subtotal,
        "subtotal": subtotal, "vat_rate": vat_rate, "vat": vat,
        "grand_total": round(subtotal + vat, 2),
        "by_kind": by_kind,
        "by_discipline": list(by_disc.values()),
        "by_group": list(by_group.values()),
        "missing_prices": [l["key"] for l in lines if l["unit_price"] <= 0],
        "missing_labor": [l["key"] for l in lines if l["labor_price"] <= 0],
        "duration": {
            "hours_per_day": hours_per_day,
            "total_hours": total_hours,
            "sequential_days": sequential_days,
            "parallel_days": parallel_days,
            "missing_rates": [l["key"] for l in lines if l["hours_per_unit"] <= 0],
        },
    }
