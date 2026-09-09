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


# ---------------------------------------------------------------- 9 Eyl 2026: demir hattı düzeltmeleri

def test_poz_line_extensions():
    """Kanca payı toplanır (160+30), metre yazılan boy, Q simgesi, adet çarpanı; adetsiz poz yalnız uyarıda sayılır."""
    import ezdxf
    from app.parser.loader import Drawing, Entity
    from app.parser.rebar_tables import _poz_length_m, POZ_LINE, parse_rebar_labels
    assert _poz_length_m("160") == pytest.approx(1.60)
    assert _poz_length_m("160+30") == pytest.approx(1.90)
    assert _poz_length_m("1,60") == pytest.approx(1.60)
    assert _poz_length_m("2.35") == pytest.approx(2.35)
    assert POZ_LINE.match("P45 4Q14 ila. l=160") is not None
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for i, t in enumerate(["P45 4Ø14 ila. l=160", "P46 2Ø14 l=160+40", "P47 4Ø12 mon. l=200 (2 ADET)", "P02 Ø10 l=256"]):
        msp.add_text(t, dxfattribs={"height": 0.2, "insert": (0, i)})
    d = doc  # noqa
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".dxf"); os.close(fd)
    doc.saveas(path)
    lab = parse_rebar_labels(load_dxf(path))
    assert lab.total_length[14] == pytest.approx(4 * 1.6 + 2 * 2.0)
    assert lab.total_length[12] == pytest.approx(4 * 2.0 * 2)
    assert lab.pos_count == 3
    assert any("adetsiz" in w for w in lab.warnings) and any("adet çarpanı" in w for w in lab.warnings)


def test_rebar_target_for_plan_type_and_filename():
    from app.parser.rebar_tables import rebar_target_for
    assert rebar_target_for("sta_kiris", "K1075", "5-KİRİŞ DETAYLARI.dxf") == "beam"
    assert rebar_target_for(None, "K1075 (50/45)", "5-KIYI A4-A5 BLOK KİRİŞ DETAYLARI.dxf") == "beam"
    assert rebar_target_for(None, "İLAVE DONATI PLANI", "1-A4-A5 TEMEL KALIP ve DONATI PLANLARI.dxf") == "foundation"
    assert rebar_target_for(None, "+7.95 KOTU X YÖNÜ DONATI PLANI", "4-KALIP DONATI PLANLARI.dxf") == "slab"
    assert rebar_target_for("sta_kolon", "S1 detay", "") == "column"
    assert rebar_target_for(None, "TEMEL X YÖNÜ", "KOLON.dxf") == "foundation"     # başlık dosya adından önce


def test_classify_title_prefers_rebar_candidate():
    from app.planset import classify_title, resolve_plan
    assert classify_title("+7.95 KOTU KALIP PLANI", "X -YÖNÜ DONATI PLANI").code == "sta_doseme_donati"
    assert classify_title("+7.95 KOTU KALIP PLANI").code == "sta_kat_kalip"
    # katman kanıtı: donatı katmanları kalabalık -> donatı paftası
    assert resolve_plan(["+7.95 KOTU KALIP PLANI"], {"VM Kiriş": 1506, "VM Üst Donatı": 818, "VM Kolon": 113}) == ("sta_doseme_donati", "rebar")
    assert resolve_plan(["+7.95 KOTU KALIP PLANI"], {"VM Kiriş": 1506, "VM Kolon": 113}) == ("sta_kat_kalip", "structural")


def test_summary_kot_based_table_merge():
    """İki kattan yalnız birinin donatı paftası var: o katın oranı düşer, öbür kat oranla kalır ve uyarı verilir."""
    p = QuantityParams(storey_height=3.0, slab_thickness=0.15, rebar_ratios={"slab": 80})
    lines = compute_all([ElementData(id=1, etype="slab", area=10.0, thickness=0.15), ElementData(id=2, etype="slab", area=10.0, thickness=0.15)], p)
    info = {1: {"drawing": "+4.15 KALIP", "drawing_id": 1, "kot": "+4.15"}, 2: {"drawing": "+7.95 KALIP", "drawing_id": 2, "kot": "+7.95"}}
    rows = [{"drawing": "Donatı +7.95", "drawing_id": 9, "kot": "+7.95", "target": "slab", "dia_mm": 12, "weight_kg": 500.0, "length_m": 100.0, "source": "tablo"}]
    s = summarize(lines, rows, info)
    slab = next(g for g in s["groups"] if g["key"] == "slab")
    assert slab["rebar_kg"] == pytest.approx(500.0 + 1.5 * 80)
    assert slab["rebar_ratio_kg"] == pytest.approx(120.0) and slab["rebar_source"] == "tablo+oran"
    assert slab["rebar_kots_ratio"] == ["+4.15"] and any("+4.15" in w for w in s["warnings"])
    assert s["rebar_by_source"] == {"tablo": 500.0, "oran": 120.0}
    bd = {r["drawing"]: r for r in s["by_drawing"]}
    assert bd["+7.95 KALIP"]["groups"]["slab"]["rebar_kg"] == 0.0 and bd["+4.15 KALIP"]["groups"]["slab"]["rebar_kg"] == pytest.approx(120.0)
    items = {i.key: i for i in structural_items(s, effective_params({}))}
    assert items["demir:slab"].quantity == pytest.approx(120.0) and "+4.15" in items["demir:slab"].notes[0]
    assert items["demir:o12"].quantity == pytest.approx(500.0) and "tablo" in items["demir:o12"].notes[0]
    # kotsuz tablo (kiriş detayları) eleman tipinin tamamını kapsar
    rows2 = [{"drawing": "K1", "drawing_id": 9, "kot": None, "target": "slab", "dia_mm": 12, "weight_kg": 500.0, "length_m": 100.0, "source": "poz"}]
    s2 = summarize(lines, rows2, info)
    slab2 = next(g for g in s2["groups"] if g["key"] == "slab")
    assert slab2["rebar_kg"] == pytest.approx(500.0) and slab2["rebar_source"] == "poz" and not s2["warnings"]


def test_table_ton_unit_and_declared_tolerance(tmp_path):
    """'AĞIRLIK (ton)' satırı kg'a çevrilir; sütunlar arasına ortalanmış genel toplam okunur ve uyuşmazlık uyarısı verilir."""
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    def t(x, y, s): msp.add_text(s, dxfattribs={"height": 0.2, "insert": (x, y)})
    t(0, 10, "POZ"); t(4, 10, "Ø10"); t(6, 10, "Ø12")
    t(0, 9, "01"); t(1, 9, "10"); t(2, 9, "100"); t(3, 9, "300"); t(4, 9, "300.00")
    t(0, 8, "TOPLAM BOY (m)"); t(4, 8, "300.00"); t(6, 8, "200.00")
    t(0, 7, "AĞIRLIK (ton)"); t(4, 7, "0.185"); t(6, 7, "0.178")
    t(0, 6, "TOPLAM AĞIRLIK (kg)"); t(5, 6, "400.0")        # sütunlar arasına ortalanmış, çap toplamı 363 ile uyuşmuyor
    path = tmp_path / "t.dxf"; doc.saveas(path)
    tables = parse_rebar_tables(load_dxf(str(path)))
    assert len(tables) == 1
    tb = tables[0]
    assert tb.weight[10] == pytest.approx(185.0) and tb.weight[12] == pytest.approx(178.0)
    assert tb.total_kg_declared == pytest.approx(400.0)
    assert any("uyuşmuyor" in w for w in tb.warnings)
