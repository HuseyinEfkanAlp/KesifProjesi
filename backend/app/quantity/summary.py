"""Metraj satırlarını eleman tipine, çizime (kata) ve donatı tablolarını çapa göre özetler."""
from __future__ import annotations

from collections import defaultdict

from ..parser.layer_profile import ELEMENT_TYPES
from .engine import QuantityLine

SUBTYPE_LABELS = {"raft": "Radye Temel", "strip": "Sürekli Temel"}
GROUP_ORDER = ["foundation:raft", "foundation:strip", "foundation", "column", "shear_wall", "beam", "slab", "stair"]


def group_key(line: QuantityLine) -> str:
    if line.etype == "foundation" and line.subtype:
        return f"{line.etype}:{line.subtype}"
    return line.etype


def group_label(key: str) -> str:
    etype, _, sub = key.partition(":")
    if sub:
        return SUBTYPE_LABELS.get(sub, ELEMENT_TYPES.get(etype, etype))
    return ELEMENT_TYPES.get(etype, etype)


def summarize(lines: list[QuantityLine], rebar_tables: list[dict] | None = None, info: dict | None = None) -> dict:
    """rebar_tables: donatı tablosu satırları [{"target": etype, "dia_mm": 12, "weight_kg": ..., "length_m": ..., "kot": "+7.95", "drawing": ...}].
    Tablosu olan eleman tipinin demiri tablodan (kaynak 'tablo'), diğerleri beton × oran ('oran') alınır.
    info: element_id -> {"drawing", "drawing_id", ...} (kat bazında dağılım için)."""
    rebar_tables = rebar_tables or []
    info = info or {}
    groups: dict[str, dict] = {}
    for ln in lines:
        k = group_key(ln)
        g = groups.setdefault(k, {"key": k, "label": group_label(k), "etype": ln.etype, "element_count": 0,
                                  "concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": 0.0, "rebar_source": "oran"})
        g["element_count"] += ln.count * ln.multiplier
        g["concrete_m3"] += ln.total_concrete
        g["formwork_m2"] += ln.total_formwork
        g["rebar_kg"] += ln.total_rebar

    # donatı tabloları: hedef eleman tipinin demirini tablo toplamıyla değiştir
    table_by_target: dict[str, float] = defaultdict(float)
    for r in rebar_tables:
        table_by_target[r["target"]] += float(r["weight_kg"])
    for etype, kg in table_by_target.items():
        keys = [k for k in groups if groups[k]["etype"] == etype]
        if keys:
            total_conc = sum(groups[k]["concrete_m3"] for k in keys) or 1.0
            for k in keys:   # radye/sürekli gibi alt gruplara beton oranında dağıt
                groups[k]["rebar_kg"] = kg * groups[k]["concrete_m3"] / total_conc
                groups[k]["rebar_source"] = "tablo"
        else:
            k = etype
            groups[k] = {"key": k, "label": group_label(k), "etype": etype, "element_count": 0,
                         "concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": kg, "rebar_source": "tablo"}

    # kesit bazında: aynı tip ve aynı kesit / kalınlıktaki elemanlar tek satır (98 kiriş 30x60 -> "Kiriş 30x60: 98 adet, 392 m, 70,6 m³")
    sections: dict[str, dict] = {}
    for ln in lines:
        i = info.get(ln.element_id, {})
        b, h, t = i.get("b"), i.get("h"), i.get("thickness")
        if ln.etype in ("column", "beam"):
            sec = f"{round((b or 0) * 100):.0f}x{round((h or 0) * 100):.0f}" if b and h else "kesit ?"
        elif ln.etype == "shear_wall":
            sec = f"{round((b or 0) * 100):.0f} cm" if b else "kalınlık ?"
        elif ln.etype in ("slab", "foundation"):
            sec = f"{round((t or 0) * 100):.0f} cm" if t else "kalınlık ?"
        else:
            sec = ln.subtype or ""
        key = f"{group_key(ln)}|{sec}"
        sg = sections.setdefault(key, {"key": key, "group": group_key(ln), "etype": ln.etype, "label": group_label(group_key(ln)),
                                       "section": sec, "element_count": 0, "length_m": 0.0, "area_m2": 0.0,
                                       "concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": 0.0})
        mult = ln.count * ln.multiplier
        sg["element_count"] += mult
        sg["length_m"] += float(i.get("length") or 0.0) * mult
        sg["area_m2"] += float(i.get("area") or 0.0) * mult
        sg["concrete_m3"] += ln.total_concrete
        sg["formwork_m2"] += ln.total_formwork
        sg["rebar_kg"] += ln.total_rebar
    section_rows = sorted(sections.values(), key=lambda g: (GROUP_ORDER.index(g["group"]) if g["group"] in GROUP_ORDER else 99, -g["concrete_m3"]))
    for sg in section_rows:
        for k in ("length_m", "area_m2", "concrete_m3", "formwork_m2", "rebar_kg"):
            sg[k] = round(sg[k], 2)

    ordered = sorted(groups.values(), key=lambda g: GROUP_ORDER.index(g["key"]) if g["key"] in GROUP_ORDER else 99)
    for g in ordered:
        for k in ("concrete_m3", "formwork_m2", "rebar_kg"):
            g[k] = round(g[k], 3)
    totals = {
        "concrete_m3": round(sum(g["concrete_m3"] for g in ordered), 3),
        "formwork_m2": round(sum(g["formwork_m2"] for g in ordered), 3),
        "rebar_kg": round(sum(g["rebar_kg"] for g in ordered), 2),
    }

    # çap bazında demir (yalnız tablolardan)
    by_dia: dict[int, dict] = {}
    for r in rebar_tables:
        d = int(r["dia_mm"])
        e = by_dia.setdefault(d, {"dia_mm": d, "weight_kg": 0.0, "length_m": 0.0, "targets": {}})
        e["weight_kg"] += float(r["weight_kg"])
        e["length_m"] += float(r.get("length_m") or 0.0)
        e["targets"][r["target"]] = e["targets"].get(r["target"], 0.0) + float(r["weight_kg"])
    rebar_by_dia = [{**v, "weight_kg": round(v["weight_kg"], 1), "length_m": round(v["length_m"], 1),
                     "targets": {k: round(x, 1) for k, x in v["targets"].items()}} for v in sorted(by_dia.values(), key=lambda v: v["dia_mm"])]
    table_total = round(sum(v["weight_kg"] for v in rebar_by_dia), 1)
    ratio_total = round(sum(g["rebar_kg"] for g in ordered if g["rebar_source"] == "oran"), 1)

    # kat (çizim) bazında
    per: dict[str, dict] = {}
    for ln in lines:
        i = info.get(ln.element_id, {})
        name = i.get("drawing") or "?"
        row = per.setdefault(name, {"drawing": name, "drawing_id": i.get("drawing_id"), "kot": i.get("kot"),
                                    "groups": {}, "concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": 0.0, "rebar_by_dia": {}})
        g = row["groups"].setdefault(ln.etype, {"concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": 0.0, "count": 0})
        g["concrete_m3"] += ln.total_concrete
        g["formwork_m2"] += ln.total_formwork
        g["rebar_kg"] += ln.total_rebar
        g["count"] += ln.count * ln.multiplier
        row["concrete_m3"] += ln.total_concrete
        row["formwork_m2"] += ln.total_formwork
        row["rebar_kg"] += ln.total_rebar
    for r in rebar_tables:
        name = r.get("drawing") or "donatı"
        row = per.setdefault(name, {"drawing": name, "drawing_id": r.get("drawing_id"), "kot": r.get("kot"),
                                    "groups": {}, "concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": 0.0, "rebar_by_dia": {}})
        row["rebar_by_dia"][str(int(r["dia_mm"]))] = round(row["rebar_by_dia"].get(str(int(r["dia_mm"])), 0.0) + float(r["weight_kg"]), 1)
        row["rebar_table_kg"] = round(row.get("rebar_table_kg", 0.0) + float(r["weight_kg"]), 1)
        row["rebar_target"] = r["target"]
    by_drawing = []
    for row in per.values():
        for g in row["groups"].values():
            for k in ("concrete_m3", "formwork_m2", "rebar_kg"):
                g[k] = round(g[k], 2)
        for k in ("concrete_m3", "formwork_m2", "rebar_kg"):
            row[k] = round(row[k], 2)
        by_drawing.append(row)
    by_drawing.sort(key=lambda r: (r.get("kot") is None, _kot_val(r.get("kot")), r["drawing"]))

    return {"groups": ordered, "sections": section_rows, "totals": totals, "rebar_by_dia": rebar_by_dia,
            "rebar_table_total_kg": table_total, "rebar_ratio_total_kg": ratio_total, "by_drawing": by_drawing}


def _kot_val(k: str | None) -> float:
    try:
        return float((k or "0").replace("+", ""))
    except ValueError:
        return 0.0
