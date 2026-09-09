import pytest

from app.parser.analyzer import analyze_file
from app.parser.layer_profile import LayerProfile
from app.parser.loader import load_dxf


def test_loader_units_and_blocks(storey_dxf):
    d = load_dxf(storey_dxf)
    assert d.unit == "cm" and d.scale == pytest.approx(0.01) and d.unit_detected
    kolon = [e for e in d.entities if e.layer == "KOLON"]
    # 3 polyline + 1 blok içinden gelen polyline + 1 hatch = 5 çokgen
    assert len([e for e in kolon if e.is_closed_polygon]) == 5
    assert any(e.block == "KOLON_30x60" for e in kolon)
    texts = [e.text for e in d.texts()]
    assert "K102 25/50" in texts  # MTEXT plain_text


def test_layer_profile_default():
    p = LayerProfile()
    assert p.classify("KOLON") == "column"
    assert p.classify("S-KIRIS") == "beam"
    assert p.classify("DÖŞEME") == "slab"
    assert p.classify("PERDE") == "shear_wall"
    assert p.classify("TEMEL") == "foundation"
    assert p.classify("YAZI") is None
    assert p.classify("AKS") is None
    assert p.classify("XYZ") is None
    p2 = p.with_layer("column", "XYZ")
    assert p2.classify("XYZ") == "column"
    assert p2.with_layer(None, "XYZ").classify("XYZ") is None


def test_storey_detection(storey_dxf):
    r = analyze_file(str(storey_dxf))
    cols = r.by_type("column")
    assert len(cols) == 4, [c.to_dict() for c in cols]
    for c in cols:
        assert c.area == pytest.approx(0.18, abs=1e-6)
        assert c.perimeter == pytest.approx(1.8, abs=1e-6)
        assert c.b == pytest.approx(0.30) and c.h == pytest.approx(0.60)
        assert c.confidence >= 0.9
    assert sorted(c.name for c in cols) == ["S1", "S2", "S3", "S4"]

    beams = {b.name: b for b in r.by_type("beam")}
    assert set(beams) == {"K101", "K102"}, list(beams)
    assert beams["K101"].b == pytest.approx(0.25) and beams["K101"].h == pytest.approx(0.50)
    assert beams["K101"].length == pytest.approx(4.70, abs=1e-3)
    assert beams["K102"].length == pytest.approx(5.40, abs=1e-3)

    slabs = r.by_type("slab")
    assert len(slabs) == 1
    assert slabs[0].name == "D101"
    assert slabs[0].area == pytest.approx(34.98, abs=1e-6)
    assert slabs[0].thickness == pytest.approx(0.15)

    walls = r.by_type("shear_wall")
    assert len(walls) == 1
    assert walls[0].name == "P1"
    assert walls[0].area == pytest.approx(0.5, abs=1e-6)
    assert walls[0].b == pytest.approx(0.20) and walls[0].length == pytest.approx(2.50)

    assert r.by_type("foundation") == []
    names = {l.name: l.etype for l in r.layers}
    assert names["KOLON"] == "column" and names["AKS"] is None


def test_foundation_detection(foundation_dxf):
    r = analyze_file(str(foundation_dxf))
    f = r.by_type("foundation")
    rafts = [e for e in f if e.subtype == "raft"]
    strips = [e for e in f if e.subtype == "strip"]
    assert len(rafts) == 1 and len(strips) == 1
    assert rafts[0].area == pytest.approx(42.0, abs=1e-6)
    assert rafts[0].thickness == pytest.approx(0.60)
    assert strips[0].name == "TK1"
    assert strips[0].b == pytest.approx(0.60) and strips[0].h == pytest.approx(0.80)
    assert strips[0].length == pytest.approx(4.0, abs=1e-3)


def test_network_slabs_split_labels_and_unit_fix(network_dxf):
    r = analyze_file(str(network_dxf))
    # $INSUNITS mm diyordu, etiketler cm'i doğruladı
    assert r.unit == "cm" and r.suggested_unit == "cm"
    assert any("kolon etiketleri" in w for w in r.warnings)

    cols = r.by_type("column")
    assert len(cols) == 6
    for c in cols:
        assert c.area == pytest.approx(0.25, abs=1e-6)
        assert c.b == pytest.approx(0.5) and c.h == pytest.approx(0.5)   # ayrı "(50/50)" yazısından
    assert sorted(c.name for c in cols) == [f"S{i}" for i in range(1, 7)]

    beams = {b.name: b for b in r.by_type("beam")}
    assert set(beams) == {f"K{i}" for i in range(1, 8)}, sorted(beams)
    for name, b in beams.items():
        assert b.b == pytest.approx(0.30) and b.h == pytest.approx(0.50), name
        expected = 5.5 if int(name[1:]) <= 4 else 4.5
        assert b.length == pytest.approx(expected, abs=0.02), (name, b.length)

    slabs = sorted(r.by_type("slab"), key=lambda s: s.area)
    assert len(slabs) == 2
    assert all(s.subtype == "net" and s.name == "D1" and s.thickness == pytest.approx(0.12) for s in slabs)
    assert slabs[1].area == pytest.approx(26.75, abs=0.1)   # 1 mm hassasiyet ızgarası (set_precision) ile ±0,05 oynar
    assert slabs[0].area == pytest.approx(25.75, abs=0.1)   # 1 m² şaft düşüldü
    names = {l.name: l.etype for l in r.layers}
    assert names["VM Döşeme Şaft"] == "hole" and names["VM Kolon Markası"] is None


REAL = __import__("pathlib").Path(__file__).resolve().parents[2] / "+4.15 KOTU KALIP PLANI -10.02.2025.dxf"


@pytest.mark.skipif(not REAL.exists(), reason="gerçek çizim yok")
def test_real_drawing_smoke():
    import time
    t = time.time()
    r = analyze_file(str(REAL))
    assert time.time() - t < 90, "analiz çok yavaş"
    assert r.unit == "cm"
    cols = [c for c in r.by_type("column") if c.confidence >= 0.4]
    assert 140 <= len(cols) <= 170
    assert sum(1 for c in cols if c.name) >= 130
    walls = r.by_type("shear_wall")
    assert 15 <= len(walls) <= 25
    beams = r.by_type("beam")
    assert 300 <= len(beams) <= 600
    assert sum(1 for b in beams if b.name and b.h) / len(beams) > 0.7
    slabs = r.by_type("slab")
    assert 150 <= len(slabs) <= 400
    assert all(s.subtype == "net" for s in slabs)
    assert 0.8 < sum(s.area for s in slabs) / 1000 < 12   # 800 .. 12.000 m² plan


def test_unit_guess_and_override(unitless_dxf):
    d = load_dxf(unitless_dxf)
    assert d.unit == "mm" and not d.unit_detected
    assert d.warnings
    r = analyze_file(str(unitless_dxf))
    assert r.by_type("column")[0].area == pytest.approx(0.18, abs=1e-6)
    d2 = load_dxf(unitless_dxf, unit_override="cm")
    assert d2.unit == "cm" and d2.unit_detected


def test_open_polyline_closed_via_network(tmp_path):
    """L şeklinde açık polyline + kapatan çizgi: uçları doğrudan birleştirmek üçgen verir; ağ kapatması doğru şekli verir."""
    import ezdxf
    from app.parser.detectors.base import polygons_on_layers
    from app.parser.geometry import polygon_area
    from app.parser.loader import load_dxf
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    # 10x6 dikdörtgen: 3 kenar polyline (4 nokta), 4. kenar ayrı çizgi
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 6), (0, 6)], dxfattribs={"layer": "TEMEL"})
    msp.add_line((0, 6), (0, 0), dxfattribs={"layer": "TEMEL"})
    # pafta kenarında kesilmiş açık sınır (ağ ile kapanmaz): uçtan kapatılır
    msp.add_lwpolyline([(20, 0), (30, 0), (30, 6), (25, 6), (20, 6)], dxfattribs={"layer": "TEMEL"})
    # 12x8 bölge, sınır çizgileri arasında 0.8 m boşluklar (gerçek çizim): köprüleme ile kapanır
    msp.add_line((40, 0), (51.2, 0), dxfattribs={"layer": "TEMEL"})
    msp.add_line((52, 0.8), (52, 8), dxfattribs={"layer": "TEMEL"})
    msp.add_line((52, 8), (40, 8), dxfattribs={"layer": "TEMEL"})
    msp.add_line((40, 7.2), (40, 0), dxfattribs={"layer": "TEMEL"})
    f = tmp_path / "t.dxf"; doc.saveas(f)
    polys = polygons_on_layers(load_dxf(f), ["TEMEL"], close_open=True, min_area=2.0)
    areas = sorted(round(polygon_area(p.points), 1) for p in polys)
    assert areas == [60.0, 60.0], [(p.source, polygon_area(p.points)) for p in polys]
    polys = polygons_on_layers(load_dxf(f), ["TEMEL"], close_open=True, min_area=2.0, snap_tol=1.5)
    areas = sorted(round(polygon_area(p.points), 1) for p in polys)
    assert areas == [60.0, 60.0, 96.0], [(p.source, polygon_area(p.points)) for p in polys]
    assert {p.source for p in polys} == {"LINES>LOOP", "POLYLINE>CLOSED"}


def test_slab_faces_close_with_column_gap(tmp_path):
    """Kiriş çizgileri kolon yüzüne 3 cm uzaktan biter: tampon olmadan hücre kapanmaz, tamponla döşeme bulunur."""
    import ezdxf
    from app.parser.analyzer import analyze_file
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 5
    for n in ("KOLON", "KIRIS", "YAZI"): doc.layers.add(n)
    msp = doc.modelspace()
    cols = [(0, 0), (600, 0), (0, 500), (600, 500)]
    for cx, cy in cols:
        msp.add_lwpolyline([(cx - 25, cy - 25), (cx + 25, cy - 25), (cx + 25, cy + 25), (cx - 25, cy + 25)], close=True, dxfattribs={"layer": "KOLON"})
        msp.add_text("S1 50/50", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((cx + 30, cy + 30))
    g = 3  # cm boşluk
    for cy in (0, 500):
        for off in (-15, 15):
            msp.add_line((25 + g, cy + off), (575 - g, cy + off), dxfattribs={"layer": "KIRIS"})
        msp.add_text("K1 30/50", dxfattribs={"layer": "YAZI", "height": 6}).set_placement((300, cy - 3))
    for cx in (0, 600):
        for off in (-15, 15):
            msp.add_line((cx + off, 25 + g), (cx + off, 475 - g), dxfattribs={"layer": "KIRIS"})
        msp.add_text("K2 30/50", dxfattribs={"layer": "YAZI", "height": 6, "rotation": 90}).set_placement((cx + 3, 250))
    msp.add_text("D1", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((300, 250))
    msp.add_text("d=12", dxfattribs={"layer": "YAZI", "height": 6}).set_placement((300, 235))
    f = tmp_path / "gap.dxf"; doc.saveas(f)
    r = analyze_file(str(f))
    slabs = r.by_type("slab")
    assert len(slabs) == 1 and slabs[0].subtype == "net"
    assert slabs[0].area == pytest.approx(5.7 * 4.7, rel=0.03)   # kirişler arası net alan (iç yüzler 15 cm)
    assert slabs[0].thickness == pytest.approx(0.12)


# ---------------------------------------------------------------- 9 Eyl 2026: statik düzeltmeleri

def _doc_cm():
    import ezdxf
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for name in ("VM Kolon", "VM Kiriş", "VM Kolon Markası", "VM Kiriş Markası", "VM Döşeme Markası", "VM Temel", "VM Parapet Marka"):
        doc.layers.add(name)
    return doc


def test_slab_faces_close_despite_float_noise(tmp_path):
    """Kiriş çizgi uçları 1e-10 farkla 'çakışmıyor' (gerçek çizimlerde yaygın): 1 mm hassasiyet ızgarası hücreyi kapatır."""
    from tests.fixtures.make_dxf import _rect
    doc = _doc_cm(); msp = doc.modelspace()
    eps = 1e-9
    for cx, cy in ((0, 0), (600, 0), (0, 500), (600, 500)):
        msp.add_lwpolyline(_rect(cx - 25, cy - 25, 50, 50), close=True, dxfattribs={"layer": "VM Kolon"})
        msp.add_text("S1 (50/50)", dxfattribs={"layer": "VM Kolon Markası", "height": 6}).set_placement((cx - 20, cy + 30))
    # kirişler çift çizgi; uçlar gürültülü
    for cy in (0, 500):
        for off in (-15, 15):
            msp.add_line((25 + eps, cy + off), (575 - eps, cy + off + eps), dxfattribs={"layer": "VM Kiriş"})
    for cx in (0, 600):
        for off in (-15, 15):
            msp.add_line((cx + off, 25 - eps), (cx + off + eps, 475 + eps), dxfattribs={"layer": "VM Kiriş"})
    msp.add_text("K1 (30/50)", dxfattribs={"layer": "VM Kiriş Markası", "height": 6}).set_placement((300, -3))
    msp.add_text("D1", dxfattribs={"layer": "VM Döşeme Markası", "height": 8}).set_placement((300, 260))
    msp.add_text("d=12", dxfattribs={"layer": "VM Döşeme Markası", "height": 6}).set_placement((300, 245))
    path = tmp_path / "noise.dxf"; doc.saveas(path)
    r = analyze_file(str(path))
    slabs = r.by_type("slab")
    assert len(slabs) == 1 and slabs[0].area == pytest.approx(26.7, abs=0.2) and slabs[0].thickness == pytest.approx(0.12)


def test_dims_only_label_is_not_slab_thickness_and_parapet_not_column(tmp_path):
    """Yüzey içindeki '(100/100)' kolon kesiti döşeme kalınlığı olmaz; 'Parapet (20/82)' kolon kesitine yapışmaz,
    alanla tutarlı '(100/100)' seçilir."""
    from tests.fixtures.make_dxf import _rect
    from app.parser.text_parser import parse_label
    lab = parse_label("Parapet (20/82)")
    assert lab.type_hint == "parapet" and lab.b == pytest.approx(0.20) and lab.h == pytest.approx(0.82)
    doc = _doc_cm(); msp = doc.modelspace()
    msp.add_lwpolyline(_rect(0, 0, 100, 100), close=True, dxfattribs={"layer": "VM Kolon"})
    msp.add_text("S1", dxfattribs={"layer": "VM Kolon Markası", "height": 6}).set_placement((10, 110))
    msp.add_text("Parapet (20/82)", dxfattribs={"layer": "VM Parapet Marka", "height": 6}).set_placement((10, 120))   # daha yakın
    msp.add_text("(100/100)", dxfattribs={"layer": "VM Kolon Markası", "height": 6}).set_placement((10, 140))
    path = tmp_path / "par.dxf"; doc.saveas(path)
    r = analyze_file(str(path), unit_override="cm")
    col = r.by_type("column")[0]
    assert col.b == pytest.approx(1.0) and col.h == pytest.approx(1.0) and not any("uyuşmuyor" in w for w in col.warnings)


def test_untagged_closed_polyline_not_raft(tmp_path):
    """Temel katmanındaki etiketsiz, açık çizilmiş kutu (antet / bölge kutusu) radye sayılmaz; etiketli bölge sayılır."""
    from tests.fixtures.make_dxf import _rect
    doc = _doc_cm(); msp = doc.modelspace()
    msp.add_lwpolyline(_rect(0, 0, 2000, 1500), close=True, dxfattribs={"layer": "VM Temel"})
    msp.add_text("RD1", dxfattribs={"layer": "VM Kolon Markası", "height": 10}).set_placement((900, 700))
    msp.add_text("70cm", dxfattribs={"layer": "VM Kolon Markası", "height": 8}).set_placement((900, 680))
    msp.add_lwpolyline([(5000, 0), (7000, 0), (7000, 1000), (5000, 1000)], close=False, dxfattribs={"layer": "VM Temel"})   # açık kutu, etiketsiz
    path = tmp_path / "temel.dxf"; doc.saveas(path)
    r = analyze_file(str(path), unit_override="cm")
    rafts = sorted(r.by_type("foundation"), key=lambda e: -e.area)
    good = [e for e in rafts if e.confidence >= 0.4]
    assert len(good) == 1 and good[0].name == "RD1" and good[0].thickness == pytest.approx(0.7)
    bad = [e for e in rafts if e.confidence < 0.4]
    assert bad and any("Etiketsiz açık polyline" in w for w in bad[0].warnings)


def test_crossing_beam_polygons_intersection_deducted(tmp_path):
    """Kesişen kiriş dikdörtgenlerinde ortak alan dar kirişin uzunluğundan düşülür (beton çift sayılmasın)."""
    from tests.fixtures.make_dxf import _rect
    doc = _doc_cm(); msp = doc.modelspace()
    msp.add_lwpolyline(_rect(0, -20, 800, 40), close=True, dxfattribs={"layer": "VM Kiriş"})       # 8 m × 40 cm
    msp.add_lwpolyline(_rect(380, -300, 25, 600), close=True, dxfattribs={"layer": "VM Kiriş"})    # 6 m × 25 cm, ortada kesişir
    msp.add_text("K1 (40/60)", dxfattribs={"layer": "VM Kiriş Markası", "height": 6}).set_placement((100, 25))
    msp.add_text("K2 (25/50)", dxfattribs={"layer": "VM Kiriş Markası", "height": 6, "rotation": 90}).set_placement((410, -250))
    path = tmp_path / "cross.dxf"; doc.saveas(path)
    r = analyze_file(str(path), unit_override="cm")
    beams = {b.name: b for b in r.by_type("beam")}
    assert beams["K1"].length == pytest.approx(8.0, abs=0.05)
    assert beams["K2"].length == pytest.approx(6.0 - 0.40, abs=0.05) and any("Kesişen" in w for w in beams["K2"].warnings)
