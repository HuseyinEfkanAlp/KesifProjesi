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
    assert slabs[1].area == pytest.approx(26.75, abs=0.05)
    assert slabs[0].area == pytest.approx(25.75, abs=0.05)   # 1 m² şaft düşüldü
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
