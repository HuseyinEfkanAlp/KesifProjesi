"""Metraj özeti × birim fiyat = maliyet.

Fiyat kalemi anahtarı: "<metraj_türü>:<grup>" ; grup eleman tipi ("column") ya da
temel alt tipi ("foundation:raft"). "<metraj_türü>:*" genel fiyat olarak kullanılır.
Örn. "beton:column", "beton:*", "kalip:slab", "demir:*".
"""
from __future__ import annotations

from dataclasses import dataclass

from ..quantity.summary import group_label

QUANTITY_KINDS: dict[str, tuple[str, str]] = {
    "beton": ("Beton", "m³"),
    "kalip": ("Kalıp", "m²"),
    "demir": ("Demir", "kg"),
}
KIND_FIELD = {"beton": "concrete_m3", "kalip": "formwork_m2", "demir": "rebar_kg"}


@dataclass
class PriceItem:
    key: str
    name: str
    unit: str
    unit_price: float


def default_price_items(summary: dict) -> list[PriceItem]:
    """Özetteki her grup için sıfır fiyatlı kalem listesi (kullanıcı doldurur)."""
    items: list[PriceItem] = []
    for kind, (kname, unit) in QUANTITY_KINDS.items():
        items.append(PriceItem(f"{kind}:*", f"{kname} (genel)", unit, 0.0))
        for g in summary["groups"]:
            items.append(PriceItem(f"{kind}:{g['key']}", f"{kname} - {g['label']}", unit, 0.0))
    return items


def compute_cost(summary: dict, prices: list[PriceItem], vat_rate: float = 0.0) -> dict:
    price_map = {p.key: p for p in prices}
    lines = []
    for kind, (kname, unit) in QUANTITY_KINDS.items():
        field = KIND_FIELD[kind]
        for g in summary["groups"]:
            qty = g[field]
            if qty <= 0:
                continue
            item = price_map.get(f"{kind}:{g['key']}")
            source = "özel"
            if item is None or item.unit_price <= 0:
                item = price_map.get(f"{kind}:*")
                source = "genel"
            unit_price = item.unit_price if item else 0.0
            lines.append({
                "key": f"{kind}:{g['key']}", "kind": kind, "kind_label": kname,
                "group": g["key"], "group_label": group_label(g["key"]),
                "unit": unit, "quantity": round(qty, 3), "unit_price": unit_price,
                "price_source": source if unit_price > 0 else "fiyat girilmedi",
                "total": round(qty * unit_price, 2),
            })
    subtotal = round(sum(l["total"] for l in lines), 2)
    vat = round(subtotal * vat_rate, 2)
    by_kind = {}
    for l in lines:
        by_kind[l["kind"]] = round(by_kind.get(l["kind"], 0.0) + l["total"], 2)
    return {"lines": lines, "subtotal": subtotal, "vat_rate": vat_rate, "vat": vat,
            "grand_total": round(subtotal + vat, 2), "by_kind": by_kind,
            "missing_prices": [l["key"] for l in lines if l["unit_price"] <= 0]}
