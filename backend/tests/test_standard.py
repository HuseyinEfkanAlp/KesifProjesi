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
