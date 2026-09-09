"""Kaba yapı türetmeleri: temel kazısı + geri dolgu; lento reçetesi (beton, demir, kalıp) ve zincir; otomatik katman eşleme."""
import ezdxf
import pytest

from app.parser.analyzer import analyze_file
from app.parser.layer_profile import LayerProfile
from app.quantity.boq import architectural_items
from app.quantity.recipes import expand_recipes
from app.standard.catalog import Catalog


def test_lento_recipe_chain():
    cat = Catalog()
    walls = [{"etype": "wall", "b": 0.2, "length": 10.0, "subtype": "ytong", "count": 1}]
    win = {"etype": "window", "b": 1.2, "h": 1.4, "count": 10, "name": "P1"}
    items = expand_recipes(architectural_items([{"label": "Z", "storey_count": 1, "storey_height": 3.0, "slab_thickness": 0.0, "elements": walls + [win]}], {}), cat, storey_height=3.0)
    k = {i.key: i for i in items}
    assert k["lento:*"].quantity == 10
    assert k["beton:25"].quantity == pytest.approx(0.3) and k["demir:12"].quantity == pytest.approx(30) and k["kalip:*"].quantity == pytest.approx(3.0)
    assert k["demir_iscilik:*"].quantity == pytest.approx(30 * 0.02) and k["kalip_iscilik:*"].quantity == pytest.approx(3.0 * 1.2)
    assert k["demir:12"].poz == "15.160.1003" and k["beton:25"].work_group == "KABA"


def test_excavation_from_foundation(client, foundation_dxf):
    pid = client.post("/api/projects", json={"name": "Temel", "storey_height": 3.0, "slab_thickness": 0.15}).json()["id"]
    with open(foundation_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("temel.dxf", f, "application/dxf")}, data={"label": "Temel", "discipline": "structural"})
    assert r.status_code == 201, r.text
    q = client.get(f"/api/projects/{pid}/quantities").json()
    items = {i["key"]: i for i in q["boq"]["items"]}
    kazi = next(i for key, i in items.items() if key.startswith("kazi:"))
    assert kazi["quantity"] > 0 and kazi["detail"].get("derived") and kazi["work_group"] == "KABA"
    assert "geri_dolgu:*" in items and items["geri_dolgu:*"]["quantity"] < kazi["quantity"]
    assert "kazi_makine:*" in items and "kamyon:*" in items          # kazı reçetesi: ekskavatör + kamyon saati
    # kural kapatılınca türemez
    client.patch(f"/api/projects/{pid}", json={"params": {"derived_off": "kazi,geri_dolgu"}})
    q = client.get(f"/api/projects/{pid}/quantities").json()
    assert not any(i["key"].startswith("kazi:") for i in q["boq"]["items"])


def test_auto_mapping_on_mapped_drawing(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for name in ("SERAMIK ZEMIN", "ASMA TAVAN", "AKS", "YAZI"):
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (1000, 0), (1000, 600), (0, 600)], close=True, dxfattribs={"layer": "SERAMIK ZEMIN"})
    msp.add_lwpolyline([(0, 800), (500, 800), (500, 1200), (0, 1200)], close=True, dxfattribs={"layer": "ASMA TAVAN"})
    msp.add_line((0, -100), (1000, -100), dxfattribs={"layer": "AKS"})
    for i in range(22):
        msp.add_text(f"MAHAL {i}", dxfattribs={"layer": "YAZI", "height": 20}).set_placement((i * 50, 300))
    p = tmp_path / "tavan.dxf"
    doc.saveas(p)
    cat = Catalog()
    res = analyze_file(str(p), discipline="mapped", catalog=cat)
    by = {e.meta.get("ksf_code"): e for e in res.elements}
    assert by["SERAMIK_ZEMIN"].area == pytest.approx(60.0) and by["SERAMIK_ZEMIN"].meta.get("auto_mapped") and by["SERAMIK_ZEMIN"].confidence < 0.7
    assert by["ASMA_TAVAN"].area == pytest.approx(20.0)
    assert any("otomatik eşlendi" in w for w in res.warnings)
    infos = {l.name: l for l in res.layers}
    assert infos["SERAMIK ZEMIN"].auto and infos["SERAMIK ZEMIN"].mapped_code == "SERAMIK_ZEMIN" and not infos["AKS"].mapped_code
    # kullanıcı 'ölçülmez' derse otomatik eşleme uygulanmaz
    prof = LayerProfile().with_layer(None, "ASMA TAVAN")
    res2 = analyze_file(str(p), profile=prof, discipline="mapped", catalog=cat)
    assert "ASMA_TAVAN" not in {e.meta.get("ksf_code") for e in res2.elements}


def test_no_auto_mapping_on_section_sheets(tmp_path):
    """Kesit / detay paftası (analyze=False) otomatik eşlenmez: kesitteki duvar taraması plan duvarı sayılmaz."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    doc.layers.add("brn_duvar_gazbeton")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (1000, 0), (1000, 300), (0, 300)], close=True, dxfattribs={"layer": "brn_duvar_gazbeton"})
    for i in range(22):
        msp.add_text(f"+{i}.00", dxfattribs={"height": 20}).set_placement((i * 50, 400))
    p = tmp_path / "kesit.dxf"
    doc.saveas(p)
    from app.parser.detectors.base import DetectParams
    cat = Catalog()
    assert analyze_file(str(p), discipline="mapped", catalog=cat).elements                      # plan gibi: otomatik eşlenir
    assert not analyze_file(str(p), params=DetectParams(auto_map=False), discipline="mapped", catalog=cat).elements
