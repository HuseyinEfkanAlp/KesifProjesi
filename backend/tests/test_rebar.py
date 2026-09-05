"""Donatı metraj tablosu okuma, kat/çap bazında özet, sarf kalemleri."""
import pytest

from app.parser.analyzer import analyze_file
from app.parser.loader import load_dxf
from app.parser.rebar_tables import kot_from_label, parse_rebar_labels, parse_rebar_tables, target_from_label, unit_weight
from app.quantity.boq import effective_params, structural_items
from app.quantity.engine import ElementData, QuantityParams, compute_all
from app.quantity.summary import summarize


def test_parse_rebar_tables(rebar_dxf):
    tables = parse_rebar_tables(load_dxf(str(rebar_dxf)))
    assert len(tables) == 2
    t = tables[0]
    assert set(t.columns) == {10, 12, 16}
    assert t.total_length[10] == pytest.approx(1212.0) and t.total_length[12] == pytest.approx(762.0)
    assert t.weight[10] == pytest.approx(747.8) and t.weight[12] == pytest.approx(676.66) and t.weight.get(16, 0) == 0
    assert t.total_kg_declared == pytest.approx(1424.46) and t.pos_count == 2 and not t.warnings
    t2 = tables[1]
    assert set(t2.columns) == {14} and t2.weight[14] == pytest.approx(100 * unit_weight(14), rel=1e-3)
    assert any("boy × birim ağırlık" in w for w in t2.warnings)
    assert target_from_label("+7.95 KOTU DÖŞEME DONATI PLANI") == "slab"
    assert target_from_label("TEMEL X YÖNÜ DONATI PLANI") == "foundation"
    assert target_from_label("KİRİŞ DETAYLARI") == "beam" and target_from_label("KOLON APLİKASYON") == "column"
    assert kot_from_label("+7.95 KOTU KALIP PLANI") == "+7.95" and kot_from_label("TEMEL") is None


def test_rebar_discipline_and_summary(rebar_dxf):
    r = analyze_file(str(rebar_dxf), discipline="rebar", label="+7.95 KOTU DÖŞEME DONATI PLANI")
    els = r.by_type("rebar")
    assert {e.meta["dia_mm"] for e in els} == {10, 12, 14}
    assert all(e.meta["target"] == "slab" and e.meta["kot"] == "+7.95" for e in els)
    rows = [{"drawing": "Donatı +7.95", "drawing_id": 9, "kot": e.meta["kot"], "target": e.meta["target"],
             "dia_mm": e.meta["dia_mm"], "weight_kg": e.meta["weight_kg"], "length_m": e.meta["length_m"]} for e in els]
    # geometri metrajı: 1 döşeme (oranla 80 kg/m³ -> 120 kg) + 1 kolon (oranla)
    p = QuantityParams(storey_height=3.0, slab_thickness=0.15, rebar_ratios={"slab": 80, "column": 130})
    lines = compute_all([ElementData(id=1, etype="slab", area=10.0, thickness=0.15), ElementData(id=2, etype="column", area=0.16, perimeter=1.6)], p)
    info = {1: {"drawing": "+7.95 KOTU KALIP PLANI", "drawing_id": 1, "kot": "+7.95"}, 2: {"drawing": "+7.95 KOTU KALIP PLANI", "drawing_id": 1, "kot": "+7.95"}}
    s = summarize(lines, rows, info)
    slab = next(g for g in s["groups"] if g["key"] == "slab")
    col = next(g for g in s["groups"] if g["key"] == "column")
    table_kg = 747.8 + 676.66 + 100 * unit_weight(14)
    assert slab["rebar_source"] == "tablo" and slab["rebar_kg"] == pytest.approx(table_kg, rel=1e-3)
    assert col["rebar_source"] == "oran" and col["rebar_kg"] > 0
    assert [d["dia_mm"] for d in s["rebar_by_dia"]] == [10, 12, 14]
    assert s["rebar_table_total_kg"] == pytest.approx(table_kg, rel=1e-3)
    bd = {r["drawing"]: r for r in s["by_drawing"]}
    assert bd["Donatı +7.95"]["rebar_by_dia"]["12"] == pytest.approx(676.7, abs=0.1) and bd["Donatı +7.95"]["kot"] == "+7.95"
    assert bd["+7.95 KOTU KALIP PLANI"]["groups"]["slab"]["concrete_m3"] == pytest.approx(1.5)

    items = {i.key: i for i in structural_items(s, effective_params({"concrete_waste_pct": 3, "rebar_waste_pct": 5,
                                                                     "tie_wire_kg_per_t": 8, "plywood_sheet_m2": 3.125, "formwork_reuse": 5}))}
    assert items["demir:o12"].quantity == pytest.approx(676.66, abs=0.1) and "demir:slab" not in items and "demir:column" in items
    total_rebar = s["totals"]["rebar_kg"]
    assert items["demir:fire"].quantity == pytest.approx(total_rebar * 0.05, rel=1e-3)
    assert items["bag_teli:*"].quantity == pytest.approx(total_rebar / 1000 * 8, rel=1e-3)
    form = s["totals"]["formwork_m2"]
    assert items["plywood:*"].quantity == pytest.approx(form / 3.125 / 5, rel=1e-3) and items["plywood:*"].unit == "adet"
    assert items["beton:fire"].quantity == pytest.approx(s["totals"]["concrete_m3"] * 0.03, rel=1e-3)


def test_rebar_labels_and_block_crop(beam_detail_dxf, tmp_path):
    """Kiriş açılımı: adetli poz yazıları toplanır, kesit tekrarları sayılmaz. Kolon paftası blok içinde: kırpma blok içeriğini alır."""
    from app.parser.sheets import crop_sheets
    lab = parse_rebar_labels(load_dxf(str(beam_detail_dxf)))
    assert lab is not None and lab.pos_count == 3
    assert lab.weight[8] == pytest.approx(72 * 1.60 * unit_weight(8), rel=1e-3)
    assert lab.weight[14] == pytest.approx(4 * 1.60 * unit_weight(14), rel=1e-3)
    assert lab.weight[16] == pytest.approx(4 * 5.25 * unit_weight(16), rel=1e-3)
    # iki pafta bölgesi: kiriş paftası poz yazılarıyla, kolon paftasının içeriği blokta (kırpma bloğu patlatır)
    kiris_bbox, kolon_bbox = (0.0, 0.0, 3000.0, 2000.0), (3200.0, 0.0, 6200.0, 2000.0)
    outk = tmp_path / "kiris.dxf"
    crop_sheets(beam_detail_dxf, [(kiris_bbox, outk)])
    r = analyze_file(str(outk), discipline="rebar", label="KİRİŞ DETAYLARI")
    els = r.by_type("rebar")
    assert {e.meta["dia_mm"] for e in els} == {8, 14, 16} and all(e.meta["target"] == "beam" and e.source == "REBAR_LABELS" for e in els)
    out = tmp_path / "kolon.dxf"
    crop_sheets(beam_detail_dxf, [(kolon_bbox, out)])
    tables = parse_rebar_tables(load_dxf(str(out)))
    assert len(tables) == 1 and tables[0].weight[12] == pytest.approx(888.0)
    out2 = tmp_path / "kolon_bloksuz.dxf"
    crop_sheets(beam_detail_dxf, [(kolon_bbox, out2)], include_blocks=False)
    assert parse_rebar_tables(load_dxf(str(out2))) == []
