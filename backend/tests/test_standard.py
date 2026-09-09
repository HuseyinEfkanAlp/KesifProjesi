"""KÇS standart çizim: katalog, katman adı ayrıştırma, ölçüm, keşif, API."""
import pytest

from app.parser.analyzer import analyze_file
from app.quantity.boq import effective_params, standard_items
from app.standard.catalog import Catalog, parse_layer, spec_numbers
from app.standard.template import build_template


def test_parse_layer():
    cat = Catalog()
    p = parse_layer("KSF-HAV-HAVA_KANAL-600x400", cat)
    assert p and p.discipline == "HAV" and p.code == "HAVA_KANAL" and p.spec == "600x400" and p.known
    assert p.item.measure == "length" and p.item.unit == "m"
    p = parse_layer("ksf-mim-duvar_ytong-20x300", cat)          # küçük harf de kabul
    assert p and p.code == "DUVAR_YTONG" and p.item.measure == "wall_area"
    assert spec_numbers(p.spec) == [20.0, 300.0]
    p = parse_layer("KSF-ALT-YENI_KALEM-X", cat)
    assert p and not p.known and p.code == "YENI_KALEM"
    assert parse_layer("KSF-YAN-SPRINKLER", cat).spec is None
    assert parse_layer("DUVAR", cat) is None
    assert parse_layer("KSF-HAV", cat) is None                   # kalem yok
    assert spec_numbers("NYY_4x16") == [4.0, 16.0] and spec_numbers("DN65") == [65.0] and spec_numbers(None) == []


def test_catalog_overrides_roundtrip(tmp_path):
    cat = Catalog()
    n = len(cat.items)
    cat.upsert_item({"code": "cephe ışığı", "discipline": "CEP", "name": "Cephe aydınlatması", "measure": "count"})
    assert cat.get("CEPHE_ISIGI").custom and cat.get("CEPHE_ISIGI").unit == "adet"
    cat.remove_item("BANK")
    cat.upsert_discipline("hav", "Havalandırma ve iklimlendirme")
    with pytest.raises(ValueError):
        cat.upsert_item({"code": "X", "discipline": "ZZZ", "name": "x", "measure": "count"})
    with pytest.raises(ValueError):
        cat.upsert_item({"code": "X", "discipline": "CEP", "name": "x", "measure": "kilo"})
    path = tmp_path / "catalog.json"
    cat.save(path)
    cat2 = Catalog.load(path)
    assert len(cat2.items) == n and cat2.get("CEPHE_ISIGI") and cat2.get("BANK") is None
    assert cat2.disciplines["HAV"] == "Havalandırma ve iklimlendirme"
    assert Catalog.load(tmp_path / "yok.json").get("BANK") is not None


def test_standard_detection_and_boq(standard_dxf):
    r = analyze_file(str(standard_dxf), discipline="standard", catalog=Catalog())
    assert r.discipline == "standard"
    types = {e.etype for e in r.elements}
    assert {"hava_kanal", "boru_pprc_temiz", "sprinkler", "kompozit_panel", "xps", "duvar_ytong", "dolgu", "agac", "yeni_kalem"} <= types
    assert len(r.by_type("sprinkler")) == 6 and len(r.by_type("agac")) == 3
    assert sum(e.length for e in r.by_type("hava_kanal")) == pytest.approx(15.0)
    assert r.by_type("xps")[0].area == pytest.approx(20.0)
    wall = r.by_type("duvar_ytong")[0]        # duvar: alan = uzunluk × katman adındaki yükseklik (20x300 -> 3 m), kalınlık 20 cm
    assert wall.h == pytest.approx(3.0) and wall.thickness == pytest.approx(0.20) and wall.area == pytest.approx(wall.length * 3.0)
    assert any("YENI_KALEM" in w for w in r.warnings)
    assert any("Standart dışı" in w and "AKS" in w for w in r.warnings)
    layer = next(l for l in r.layers if l.name == "KSF-HAV-HAVA_KANAL-600x400")
    assert layer.etype == "hava_kanal" and "Havalandırma" in layer.to_dict()["etype_label"]

    items = standard_items([{"label": "Zemin", "storey_count": 2, "storey_height": 3.5, "slab_thickness": 0.2,
                             "elements": r.elements}], effective_params({}), Catalog())
    by = {i.key: i for i in items}
    assert by["hava_kanal:600x400"].quantity == pytest.approx(30.0) and by["hava_kanal:600x400"].unit == "m"
    assert by["hava_kanal:600x400"].discipline == "ksf:HAV" and by["hava_kanal:600x400"].discipline_label == "Havalandırma"
    assert by["boru_pprc_temiz:25"].quantity == pytest.approx(16.0)
    assert by["sprinkler:k80_ust"].quantity == 12 and by["sprinkler:k80_ust"].unit == "adet"
    assert by["kompozit_panel:4mm"].quantity == pytest.approx(60.0) and by["kompozit_panel:4mm"].unit == "m²"
    assert by["xps:5"].quantity == pytest.approx(40.0)
    assert by["duvar_ytong:20x300"].quantity == pytest.approx(6 * 3.0 * 2) and by["duvar_ytong:20x300"].unit == "m²"
    assert by["dolgu:30"].quantity == pytest.approx(20 * 0.3 * 2) and by["dolgu:30"].unit == "m³"
    assert by["agac:cinar"].quantity == 6
    assert by["yeni_kalem:x"].quantity == pytest.approx(6.0) and "Katalogda yok" in by["yeni_kalem:x"].notes[0]


def test_template_dxf(tmp_path):
    data = build_template(Catalog())
    assert data.startswith(b"  0\nSECTION") or b"SECTION" in data[:200]
    import ezdxf
    p = tmp_path / "t.dxf"
    p.write_bytes(data)
    doc = ezdxf.readfile(str(p))
    names = {l.dxf.name for l in doc.layers}
    assert "KSF-HAV-HAVA_KANAL-600x400" in names and "KSF-YAN-SPRINKLER-K80_UST" in names
    assert len(names) > 100


def test_mapped_discipline_facade(facade_dxf):
    """Ofis katmanları -> katalog kalemi eşlemesi: tarama m², kapalı polyline m², çizgi m, blok adet; öneriler."""
    from app.parser.layer_profile import LayerProfile
    from app.parser.detectors.standard import suggest_item
    cat = Catalog()
    assert suggest_item("brn_hatch_gazbeton", cat) == "DUVAR_YTONG" and suggest_item("brn_glass", cat) == "CAM"
    assert suggest_item("dc mantolama01", cat) == "MANTOLAMA_SISTEM" and suggest_item("brn_dim", cat) is None   # mantolama katmanı sisteme yükselir
    r0 = analyze_file(str(facade_dxf), discipline="mapped", catalog=cat)
    assert r0.elements and any("otomatik eşlendi" in w and "brn_hatch_gazbeton → Ytong" in w for w in r0.warnings)   # öneri onaysız uygulanır
    assert all(e.meta.get("auto_mapped") and e.confidence < 0.7 for e in r0.elements)
    prof = (LayerProfile().with_layer("item:DUVAR_YTONG:area", "brn_hatch_gazbeton").with_layer("item:CAM", "brn_glass")
            .with_layer("item:KOREKUYU:length", "Söve").with_layer("item:CEPHE_TASI:count", "Kartonpiyer"))
    r = analyze_file(str(facade_dxf), profile=prof, discipline="mapped", catalog=cat)
    by = {}
    for e in r.elements:
        by.setdefault(e.etype, []).append(e)
    assert sum(e.area for e in by["duvar_ytong"]) == pytest.approx(48.0)
    assert sum(e.area for e in by["cam"]) == pytest.approx(9.0) and len(by["cam"]) == 3
    assert sum(e.length for e in by["korekuyu"]) == pytest.approx(8.0)
    assert len(by["cephe_tasi"]) == 5 and all(e.meta["ksf_code"] == "CEPHE_TASI" for e in by["cephe_tasi"])
    layer = next(l for l in r.layers if l.name == "brn_hatch_gazbeton")
    assert layer.mapped_code == "DUVAR_YTONG" and layer.mapped_measure == "area" and "m²" in layer.to_dict()["etype_label"]
    items = standard_items([{"label": "Ön cephe", "storey_count": 1, "elements": r.elements}], effective_params({}), cat)
    by_key = {i.key: i for i in items}
    assert by_key["duvar_ytong:*"].quantity == pytest.approx(48.0) and by_key["duvar_ytong:*"].unit == "m²"
    assert by_key["duvar_ytong:*"].discipline == "ksf:MIM"
    assert by_key["cam:*"].quantity == pytest.approx(9.0) and by_key["korekuyu:*"].quantity == pytest.approx(8.0)
    assert by_key["cephe_tasi:*"].quantity == 5



def test_ksf_wall_openings_deducted_and_finishes(tmp_path):
    """KSF duvarında kapı / pencere boşluğu (≥ 0,10 m²) düşülür; sıva / boya duvar alanından türetilir; cam pencereden;
    asansör gibi proje geneli kalemler kat sayısıyla çarpılmaz; kapalı çokgen duvarda eksen uzunluğu alınır."""
    import ezdxf
    from tests.fixtures.make_dxf import _rect
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    for name in ["KSF-MIM-DUVAR_YTONG-20x300", "KSF-MIM-KAPI-90x210", "KSF-MIM-PENCERE-120x140", "KSF-ASN-ASANSOR-1000KG"]:
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_line((0, 0), (10000, 0), dxfattribs={"layer": "KSF-MIM-DUVAR_YTONG-20x300"})                      # 10 m × 3 = 30 m²
    msp.add_lwpolyline(_rect(0, 5000, 10000, 200), close=True, dxfattribs={"layer": "KSF-MIM-DUVAR_YTONG-20x300"})  # kapalı çokgen 10 × 0,2 m -> 10 m, 30 m²
    k = doc.blocks.new("KAPI"); k.add_line((0, 0), (900, 0))
    w = doc.blocks.new("PENCERE"); w.add_line((0, 0), (1200, 0))
    a = doc.blocks.new("ASANSOR"); a.add_circle((0, 0), 800)
    msp.add_blockref("KAPI", (2000, 0), dxfattribs={"layer": "KSF-MIM-KAPI-90x210"})
    msp.add_blockref("PENCERE", (6000, 0), dxfattribs={"layer": "KSF-MIM-PENCERE-120x140"})
    msp.add_blockref("PENCERE", (8000, 0), dxfattribs={"layer": "KSF-MIM-PENCERE-120x140"})
    msp.add_blockref("ASANSOR", (20000, 0), dxfattribs={"layer": "KSF-ASN-ASANSOR-1000KG"})
    msp.add_blockref("ASANSOR", (25000, 0), dxfattribs={"layer": "KSF-ASN-ASANSOR-1000KG"})
    path = tmp_path / "ksf_wall.dxf"; doc.saveas(path)
    r = analyze_file(str(path), discipline="standard", catalog=Catalog())
    walls = r.by_type("duvar_ytong")
    assert len(walls) == 2 and all(abs(w.length - 10.0) < 0.05 for w in walls)
    assert any("eksen uzunluğu" in x for w in walls for x in w.warnings)
    items = standard_items([{"label": "Kat", "storey_count": 3, "storey_height": 3.0, "slab_thickness": 0.15, "elements": r.elements}],
                           effective_params({"plaster_sides": 2, "paint_sides": 2}), Catalog())
    by = {i.key: i for i in items}
    openings = 0.9 * 2.1 + 2 * 1.2 * 1.4      # 5,25 m² (tek kat)
    assert by["duvar_ytong:20x300"].quantity == pytest.approx((60.0 - openings) * 3, rel=1e-3)
    assert by["duvar_ytong:20x300"].detail["openings_m2"] == pytest.approx(openings * 3, rel=1e-3)
    assert by["kapi:90x210"].quantity == 3 and by["pencere:120x140"].quantity == 6
    assert by["cam:120x140"].quantity == pytest.approx(2 * 1.2 * 1.4 * 3, rel=1e-3)
    assert by["siva:*"].quantity == pytest.approx((60.0 - openings) * 3 * 2, rel=1e-3)
    assert by["boya:*"].quantity == pytest.approx((60.0 - openings) * 3 * 2, rel=1e-3)
    assert by["asansor:1000kg"].quantity == 2 and "Proje geneli" in by["asansor:1000kg"].notes[0]
