"""Mekanik / sıhhi / havalandırma / yangın sezgisel dedektörü."""
import ezdxf
import pytest

from app.parser.analyzer import analyze_file
from app.parser.labels_ext import mech_fixture_code, parse_mech_label, pipe_system
from app.parser.layer_profile import LayerProfile
from app.standard.catalog import Catalog


@pytest.mark.parametrize("text,kind,spec,system", [
    ("Ø110 PVC", "pipe", "110", "BORU_PVC"),
    ("PPRC 32", "pipe", "32", "BORU_PPRC_TEMIZ"),
    ("DN65", "pipe", "DN65", "BORU_CELIK"),
    ('1 1/4"', "pipe", "40", None),
    ("600x400", "duct", "600x400", "HAVA_KANAL"),
    ("Ø315 SPİRAL KANAL", "duct", "315", "HAVA_KANAL_YUVARLAK"),
    ("FLEX Ø200", "duct", "200", "FLEX_KANAL"),
    ("+4.15", None, None, None),
])
def test_mech_label(text, kind, spec, system):
    lab = parse_mech_label(text)
    assert lab.kind == kind
    if kind:
        assert lab.spec == spec and lab.system == system


def test_layer_classification_and_systems():
    prof = LayerProfile()
    assert prof.classify("-ST-Soğuksu", "mechanical") == "pipe"
    assert prof.classify("-0-Kolon Pissu", "mechanical") == "pipe"
    assert prof.classify("-HT-Kanal Egzost", "mechanical") == "duct"
    assert prof.classify("brn_vitrifiye", "mechanical") == "mech_fixture"
    assert prof.classify("M-SPRINKLER-BORU", "mechanical") == "pipe" and prof.classify("M-SPRINKLER", "mechanical") == "mech_fixture"
    assert prof.classify("brn_duvar_gazbeton", "mechanical") is None
    assert pipe_system("-ST-Soğuksu") == "BORU_PPRC_TEMIZ" and pipe_system("PİS SU") == "BORU_PVC" and pipe_system("M-SPRINKLER-BORU") == "YANGIN_BORU"
    assert mech_fixture_code("Water Closet_ACCESIBLE WC_01") == "KLOZET" and mech_fixture_code("lavabooo") == "LAVABO"
    assert mech_fixture_code("CREACİT PİSUVAR PLAN") == "PISUAR" and mech_fixture_code("MENFEZ_600x600") == "MENFEZ"
    assert mech_fixture_code("bilinmeyen_blok") is None


def _mech_dxf(path):
    """mm çizim: PVC pis su hattı 12 m (etiket Ø110 PVC), PPRC temiz su 8 m (katman adından), çelik ısıtma hattı 6 m (DN65),
    dikdörtgen kanal 10 m (600x400) + flex 3 m, 4 sprinkler bloğu, 2 lavabo, 1 klozet, 1 menfez, 1 tanınmayan blok."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for name in ("M-PISSU", "M-TEMIZSU-PPRC", "M-ISITMA", "H-KANAL", "H-FLEX", "Y-SPRINKLER", "S-VITRIFIYE", "YAZI"):
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_line((0, 0), (12000, 0), dxfattribs={"layer": "M-PISSU"})
    msp.add_text("Ø110 PVC", dxfattribs={"layer": "YAZI", "height": 120}).set_placement((6000, 150))
    msp.add_line((0, 1000), (8000, 1000), dxfattribs={"layer": "M-TEMIZSU-PPRC"})
    msp.add_text("Ø32", dxfattribs={"layer": "YAZI", "height": 120}).set_placement((4000, 1150))
    msp.add_line((0, 2000), (6000, 2000), dxfattribs={"layer": "M-ISITMA"})
    msp.add_text("DN65", dxfattribs={"layer": "YAZI", "height": 120}).set_placement((3000, 2150))
    msp.add_lwpolyline([(0, 3000), (10000, 3000)], dxfattribs={"layer": "H-KANAL"})
    msp.add_text("600x400", dxfattribs={"layer": "YAZI", "height": 120}).set_placement((5000, 3150))
    msp.add_line((0, 4000), (3000, 4000), dxfattribs={"layer": "H-FLEX"})
    msp.add_text("FLEX Ø200", dxfattribs={"layer": "YAZI", "height": 120}).set_placement((1500, 4150))
    spr = doc.blocks.new("SPRINKLER_K80")
    spr.add_circle((0, 0), 60)
    for i in range(4):
        msp.add_blockref("SPRINKLER_K80", (1000 + i * 2000, 6000), dxfattribs={"layer": "Y-SPRINKLER"})
    lav = doc.blocks.new("LAVABO_60")
    lav.add_lwpolyline([(0, 0), (600, 0), (600, 450), (0, 450)], close=True)
    wc = doc.blocks.new("KLOZET_ASMA")
    wc.add_lwpolyline([(0, 0), (380, 0), (380, 550), (0, 550)], close=True)
    men = doc.blocks.new("MENFEZ_600x600")
    men.add_lwpolyline([(0, 0), (600, 0), (600, 600), (0, 600)], close=True)
    unk = doc.blocks.new("XYZ_123")
    unk.add_circle((0, 0), 100)
    for x in (1000, 3000):
        msp.add_blockref("LAVABO_60", (x, 8000), dxfattribs={"layer": "S-VITRIFIYE"})
    msp.add_blockref("KLOZET_ASMA", (5000, 8000), dxfattribs={"layer": "S-VITRIFIYE"})
    msp.add_blockref("MENFEZ_600x600", (7000, 8000), dxfattribs={"layer": "H-KANAL"})
    msp.add_blockref("XYZ_123", (9000, 8000), dxfattribs={"layer": "S-VITRIFIYE"})
    for i in range(22):
        msp.add_text(f"MAHAL {i}", dxfattribs={"layer": "YAZI", "height": 250}).set_placement((i * 500, -1500))
    doc.saveas(path)
    return path


def test_mechanical_detection(tmp_path):
    res = analyze_file(str(_mech_dxf(tmp_path / "mek.dxf")), discipline="mechanical", catalog=Catalog())
    by_code = {}
    for e in res.elements:
        by_code.setdefault(e.meta.get("ksf_code"), []).append(e)
    assert sum(e.length for e in by_code["BORU_PVC"]) == pytest.approx(12.0, abs=0.01) and by_code["BORU_PVC"][0].subtype == "110"
    assert sum(e.length for e in by_code["BORU_PPRC_TEMIZ"]) == pytest.approx(8.0, abs=0.01) and by_code["BORU_PPRC_TEMIZ"][0].subtype == "32"
    assert sum(e.length for e in by_code["BORU_CELIK"]) == pytest.approx(6.0, abs=0.01) and by_code["BORU_CELIK"][0].subtype == "DN65"
    assert sum(e.length for e in by_code["HAVA_KANAL"]) == pytest.approx(10.0, abs=0.01) and by_code["HAVA_KANAL"][0].subtype == "600x400"
    assert sum(e.length for e in by_code["FLEX_KANAL"]) == pytest.approx(3.0, abs=0.01)
    assert sum(e.count for e in by_code["SPRINKLER"]) == 4 and sum(e.count for e in by_code["LAVABO"]) == 2
    assert sum(e.count for e in by_code["KLOZET"]) == 1 and sum(e.count for e in by_code["MENFEZ"]) == 1
    assert sum(e.count for e in by_code["MEKANIK_CIHAZ"]) == 1
    assert res.disciplines == ["mechanical"] and any(w.startswith("Mekanik:") for w in res.warnings)


def test_mechanical_boq_and_recipes(tmp_path):
    from app.quantity.boq import standard_items
    from app.quantity.recipes import expand_recipes
    cat = Catalog()
    res = analyze_file(str(_mech_dxf(tmp_path / "mek2.dxf")), discipline="mechanical", catalog=cat)
    entry = {"label": "Mek", "storey_count": 1, "elements": [e.to_dict() | {"meta": e.meta} for e in res.elements]}
    items = expand_recipes(standard_items([entry], {}, cat), cat, storey_height=3.0)
    k = {i.key: i for i in items}
    assert k["boru_pvc:110"].quantity == pytest.approx(12.0, abs=0.01) and k["boru_pvc:110"].work_group == "MEK"
    assert k["hava_kanal:600x400"].quantity == pytest.approx(10.0, abs=0.01)
    assert k["sprinkler:*"].quantity == 4 and k["lavabo:*"].quantity == 2
    assert k["boru_montaj:*"].quantity > 0 and k["boru_aski:*"].quantity > 0      # reçete: montaj işçiliği, askı
    assert k["sprinkler_montaj:*"].quantity == pytest.approx(4 * 1.2 + 1 * 0) or k["sprinkler_montaj:*"].quantity >= 4.8
    assert k["vitrifiye_montaj:*"].quantity == pytest.approx(2 * 2.0 + 2.5)
    assert k["kanal_montaj:*"].quantity == pytest.approx(10 * 0.6 + 3 * 0.2)
