"""Metraj satırlarını eleman tipine göre özetler."""
from __future__ import annotations

from ..parser.layer_profile import ELEMENT_TYPES
from .engine import QuantityLine

SUBTYPE_LABELS = {"raft": "Radye Temel", "strip": "Sürekli Temel"}


def group_key(line: QuantityLine) -> str:
    if line.etype == "foundation" and line.subtype:
        return f"{line.etype}:{line.subtype}"
    return line.etype


def group_label(key: str) -> str:
    etype, _, sub = key.partition(":")
    if sub:
        return SUBTYPE_LABELS.get(sub, ELEMENT_TYPES.get(etype, etype))
    return ELEMENT_TYPES.get(etype, etype)


def summarize(lines: list[QuantityLine]) -> dict:
    groups: dict[str, dict] = {}
    for ln in lines:
        k = group_key(ln)
        g = groups.setdefault(k, {"key": k, "label": group_label(k), "etype": ln.etype, "element_count": 0,
                                  "concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": 0.0})
        g["element_count"] += ln.count * ln.multiplier
        g["concrete_m3"] += ln.total_concrete
        g["formwork_m2"] += ln.total_formwork
        g["rebar_kg"] += ln.total_rebar
    order = ["foundation:raft", "foundation:strip", "foundation", "column", "shear_wall", "beam", "slab"]
    ordered = sorted(groups.values(), key=lambda g: order.index(g["key"]) if g["key"] in order else 99)
    for g in ordered:
        for k in ("concrete_m3", "formwork_m2", "rebar_kg"):
            g[k] = round(g[k], 3)
    totals = {
        "concrete_m3": round(sum(g["concrete_m3"] for g in ordered), 3),
        "formwork_m2": round(sum(g["formwork_m2"] for g in ordered), 3),
        "rebar_kg": round(sum(g["rebar_kg"] for g in ordered), 2),
    }
    return {"groups": ordered, "totals": totals}
