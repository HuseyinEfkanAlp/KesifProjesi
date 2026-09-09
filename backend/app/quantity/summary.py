"""Metraj satırlarını eleman tipine, çizime (kata) ve donatı tablolarını çapa göre özetler."""
from __future__ import annotations

from collections import defaultdict

from ..parser.layer_profile import ELEMENT_TYPES
from .engine import QuantityLine

SUBTYPE_LABELS = {"raft": "Radye Temel", "strip": "Sürekli Temel"}
GROUP_ORDER = ["foundation:raft", "foundation:strip", "foundation", "column", "shear_wall", "beam", "slab", "parapet", "stair"]


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
    warnings: list[str] = []
    groups: dict[str, dict] = {}
    # oran demiri kot bazında: donatı paftası olan kotların oran tahmini düşülür, olmayan kotlar oranla kalır
    ratio_by_etype_kot: dict[str, dict[str | None, float]] = defaultdict(lambda: defaultdict(float))
    ratio_kg_by_key_kot: dict[str, dict[str | None, float]] = defaultdict(lambda: defaultdict(float))
    for ln in lines:
        k = group_key(ln)
        g = groups.setdefault(k, {"key": k, "label": group_label(k), "etype": ln.etype, "element_count": 0,
                                  "concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": 0.0, "rebar_source": "oran",
                                  "rebar_ratio_kg": 0.0, "rebar_table_kg": 0.0, "rebar_kots_ratio": []})
        g["element_count"] += ln.count * ln.multiplier
        g["concrete_m3"] += ln.total_concrete
        g["formwork_m2"] += ln.total_formwork
        g["rebar_kg"] += ln.total_rebar
        kot = _norm_kot(info.get(ln.element_id, {}).get("kot"))
        ratio_by_etype_kot[ln.etype][kot] += ln.total_rebar
        ratio_kg_by_key_kot[k][kot] += ln.total_rebar

    # donatı tabloları: hedef eleman tipinin oran demirini tablo / poz toplamıyla değiştir.
    # Kot eşleşmesi: tablonun kotu kalıp planının kotuyla eşleşiyorsa yalnız o katın oranı düşer; tablonun kotu yoksa ya da
    # hiçbir kalıp planı kotuyla eşleşmiyorsa (temel, kiriş detayları) eleman tipinin tamamı tablodan sayılır.
    table_by_target: dict[str, float] = defaultdict(float)
    table_kots: dict[str, set] = defaultdict(set)
    sources_by_target: dict[str, set] = defaultdict(set)
    for r in rebar_tables:
        table_by_target[r["target"]] += float(r["weight_kg"])
        table_kots[r["target"]].add(_norm_kot(r.get("kot")))
        sources_by_target[r["target"]].add(r.get("source") or "tablo")
    for etype, kg in table_by_target.items():
        keys = [k for k in groups if groups[k]["etype"] == etype]
        line_kots = set(ratio_by_etype_kot.get(etype, {}))
        matched = {k for k in table_kots[etype] if k is not None and k in line_kots}
        whole = (not matched) or (None in table_kots[etype]) or etype == "foundation"
        src = "tablo" if sources_by_target[etype] <= {"tablo", "elle"} else ("poz" if sources_by_target[etype] == {"poz"} else "tablo+poz")
        if keys:
            total_conc = sum(groups[k]["concrete_m3"] for k in keys) or 1.0
            for k in keys:   # radye/sürekli gibi alt gruplara beton oranında dağıt
                share = groups[k]["concrete_m3"] / total_conc
                if whole:
                    groups[k]["rebar_kg"] = kg * share
                    groups[k]["rebar_ratio_kg"] = 0.0
                    groups[k]["rebar_source"] = src
                else:
                    kept = sum(v for kk, v in ratio_kg_by_key_kot[k].items() if kk not in matched)
                    groups[k]["rebar_kg"] = kg * share + kept
                    groups[k]["rebar_ratio_kg"] = kept
                    groups[k]["rebar_source"] = src if kept <= 0 else f"{src}+oran"
                    missing = sorted((kk for kk in ratio_kg_by_key_kot[k] if kk not in matched and ratio_kg_by_key_kot[k][kk] > 0),
                                     key=lambda x: (x is None, _kot_val(x)))
                    groups[k]["rebar_kots_ratio"] = [m or "kotsuz" for m in missing]
                    if missing:
                        warnings.append(f"{groups[k]['label']}: {', '.join(m or 'kotsuz' for m in missing)} kotundaki kalıp planının donatı "
                                        "paftası yok; bu katlar beton × kg/m³ oranıyla (düşük güven)")
                groups[k]["rebar_table_kg"] = kg * share
        else:
            k = etype
            groups[k] = {"key": k, "label": group_label(k), "etype": etype, "element_count": 0,
                         "concrete_m3": 0.0, "formwork_m2": 0.0, "rebar_kg": kg, "rebar_source": src,
                         "rebar_ratio_kg": 0.0, "rebar_table_kg": kg, "rebar_kots_ratio": []}
    for g in groups.values():
        if g["rebar_source"] == "oran":
            g["rebar_ratio_kg"] = g["rebar_kg"]

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
        for k in ("concrete_m3", "formwork_m2", "rebar_kg", "rebar_ratio_kg", "rebar_table_kg"):
            g[k] = round(g[k], 3)
    # kalıp iskelesi: döşeme alanı × (H − d) × kat çarpanı (ÇŞB 15.185; kolon / perde / kiriş yan kalıbına iskele yazılmaz)
    scaffold = 0.0
    for ln in lines:
        if ln.etype != "slab":
            continue
        i = info.get(ln.element_id, {})
        H, d = float(i.get("storey_height") or 0.0), float(i.get("slab_thickness") or 0.0)
        if H > 0:
            scaffold += float(i.get("area") or 0.0) * ln.count * ln.multiplier * max(H - d, 0.0)
    totals = {
        "concrete_m3": round(sum(g["concrete_m3"] for g in ordered), 3),
        "formwork_m2": round(sum(g["formwork_m2"] for g in ordered), 3),
        "rebar_kg": round(sum(g["rebar_kg"] for g in ordered), 2),
        "scaffold_m3": round(scaffold, 2),
    }

    # çap bazında demir (yalnız tablolardan / poz yazılarından / elle girilenden)
    by_dia: dict[int, dict] = {}
    for r in rebar_tables:
        d = int(r["dia_mm"])
        e = by_dia.setdefault(d, {"dia_mm": d, "weight_kg": 0.0, "length_m": 0.0, "targets": {}, "sources": {}})
        e["weight_kg"] += float(r["weight_kg"])
        e["length_m"] += float(r.get("length_m") or 0.0)
        e["targets"][r["target"]] = e["targets"].get(r["target"], 0.0) + float(r["weight_kg"])
        src = r.get("source") or "tablo"
        e["sources"][src] = e["sources"].get(src, 0.0) + float(r["weight_kg"])
    rebar_by_dia = [{**v, "weight_kg": round(v["weight_kg"], 1), "length_m": round(v["length_m"], 1),
                     "targets": {k: round(x, 1) for k, x in v["targets"].items()},
                     "sources": {k: round(x, 1) for k, x in v["sources"].items()}}
                    for v in sorted(by_dia.values(), key=lambda v: v["dia_mm"])]
    table_total = round(sum(v["weight_kg"] for v in rebar_by_dia), 1)
    ratio_total = round(sum(g["rebar_ratio_kg"] for g in ordered), 1)
    by_source = {"tablo": 0.0, "poz": 0.0, "elle": 0.0}
    for r in rebar_tables:
        by_source[r.get("source") or "tablo"] = by_source.get(r.get("source") or "tablo", 0.0) + float(r["weight_kg"])
    by_source["oran"] = ratio_total
    rebar_by_source = {k: round(v, 1) for k, v in by_source.items() if v > 0}

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

    # kat bazında: tablosu / poz yazısı olan kotlarda oran demiri gösterilmez (toplamla çelişmesin)
    for row in by_drawing:
        if row.get("rebar_table_kg"):
            continue
        kot = _norm_kot(row.get("kot"))
        for et, g in row["groups"].items():
            tk = table_kots.get(et)
            if tk and (kot in tk or None in tk or et == "foundation"):
                g["rebar_kg"] = 0.0
                g["rebar_note"] = "donatı paftasından"
        row["rebar_kg"] = round(sum(g["rebar_kg"] for g in row["groups"].values()), 2)

    return {"groups": ordered, "sections": section_rows, "totals": totals, "rebar_by_dia": rebar_by_dia,
            "rebar_table_total_kg": table_total, "rebar_ratio_total_kg": ratio_total, "rebar_by_source": rebar_by_source,
            "by_drawing": by_drawing, "warnings": warnings}


def _kot_val(k: str | None) -> float:
    try:
        return float((k or "0").replace("+", ""))
    except ValueError:
        return 0.0


def _norm_kot(k: str | None) -> str | None:
    """'+7.95' / '7,95' / ' +7.950' -> '+7.95' (kot eşleştirmesi için)."""
    if not k:
        return None
    try:
        v = float(str(k).replace(",", ".").replace(" ", ""))
    except ValueError:
        return str(k).strip()
    return f"{v:+.2f}"
