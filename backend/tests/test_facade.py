"""Cephe: etiket sayımı (prekast panel kodları), cephe brüt alanı (görünüş / elle / kalıp planından tahmin), cephe sistemi kalemi."""
from __future__ import annotations

import pytest

from app.parser.analyzer import analyze_file
from app.parser.detectors.standard import _label_text, suggest_item
from app.parser.layer_profile import LayerProfile
from app.quantity.boq import effective_params, standard_items
from app.standard.catalog import Catalog
from tests.test_api import client  # noqa: F401


def test_label_text():
    assert _label_text("GP-4") == "GP-4" and _label_text("EP9B") == "EP9B"
    assert _label_text("+4.15") == "" and _label_text("-4.03 (+0.12)") == "" and _label_text("12") == "" and _label_text("A") == ""
    assert _label_text("x" * 41) == ""


def test_label_count_and_facade_outline(precast_dxf):
    cat = Catalog()
    assert cat.get("PREKAST_PANEL").measure == "label_count" and cat.get("PREKAST_PANEL").unit == "adet"
    assert suggest_item("inova prekast - YAZI", cat) == "PREKAST_PANEL" and suggest_item("CEPHE HAT", cat) == "CEPHE_BRUT"
    prof = (LayerProfile().with_layer("item:PREKAST_PANEL", "inova prekast - YAZI").with_layer("item:CEPHE_BRUT:area", "CEPHE HAT")
            .with_layer("item:CAM:area", "brn_glass"))
    r = analyze_file(str(precast_dxf), profile=prof, discipline="mapped", catalog=cat)
    panels = r.by_type("prekast_panel")
    assert len(panels) == 6 and sorted(e.subtype for e in panels) == ["EP17", "EP17", "GP-3-a", "GP-4", "GP-4", "GP-4"]
    items = standard_items([{"label": "Ön cephe", "storey_count": 1, "elements": r.elements}], effective_params({}), cat)
    by = {i.key: i for i in items}
    assert by["prekast_panel:gp-4"].quantity == 3 and by["prekast_panel:ep17"].quantity == 2 and by["prekast_panel:gp-3-a"].quantity == 1
    assert by["prekast_panel:gp-4"].unit == "adet" and by["prekast_panel:gp-4"].discipline == "ksf:CEP"
    assert by["cephe_brut:*"].quantity == pytest.approx(180.0) and by["cam:*"].quantity == pytest.approx(6.0)


def test_facade_from_structural_estimate_and_system(client, storey_dxf, precast_dxf):
    pid = client.post("/api/projects", json={"name": "Cephe", "storey_height": 3.0}).json()["id"]
    with open(storey_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("KALIP PLANI.dxf", f, "application/dxf")}, data={"storey_count": "4"})
    assert r.status_code == 201 and r.json()["discipline"] == "structural"
    sy = client.get(f"/api/projects/{pid}/systems").json()
    fa = sy["facade"]
    assert fa["source"] == "estimated" and fa["gross"] > 0 and fa["per_drawing"][0]["storey_count"] == 4
    assert fa["per_drawing"][0]["area"] == pytest.approx(fa["per_drawing"][0]["perimeter"] * 3.0 * 4, rel=1e-3)
    boq = client.get(f"/api/projects/{pid}/quantities").json()["boq"]
    by = {i["key"]: i for i in boq["items"]}
    assert "cephe_brut:*" not in by and "mantolama_sistem:*" not in by   # sistem seçilmeden keşfe girmez

    # cephe sistemi seç: mantolama; miktar = net cephe alanı, bileşenler kanıtsız -> hepsi "projede yok" diye sorulur
    r = client.patch(f"/api/projects/{pid}", json={"params": {"facade_system": "MANTOLAMA_SISTEM"}})
    assert r.status_code == 200 and r.json()["params"]["facade_system"] == "MANTOLAMA_SISTEM"
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["cephe_brut:*"]["detail"]["info"] is True and by["cephe_brut:*"]["quantity"] == pytest.approx(fa["gross"], abs=0.01)
    assert by["mantolama_sistem:*"]["quantity"] == pytest.approx(fa["net"], abs=0.01) and by["mantolama_sistem:*"]["detail"]["system"] is True
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    assert not any(l["key"] in ("cephe_brut:*", "mantolama_sistem:*") for l in cost["lines"])   # bilgi ve sistem satırı fiyatlanmaz
    assert client.get(f"/api/projects/{pid}/systems").json()["facade"]["source"] == "estimated"
    sy = client.get(f"/api/projects/{pid}/systems").json()
    m = next(s for s in sy["systems"] if s["code"] == "MANTOLAMA_SISTEM")
    assert m["quantity"] == pytest.approx(fa["net"], abs=0.01) and len(m["missing"]) == 7
    # EPS'i ekle -> keşifte eps kalemi net cephe alanı kadar; dübel 6 adet/m²
    r = client.put(f"/api/projects/{pid}/systems", json={"MANTOLAMA_SISTEM": {"EPS": {"include": True, "spec": "6"}, "MANTOLAMA_DUBEL": {"include": True}}})
    assert r.status_code == 200
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["eps:6"]["quantity"] == pytest.approx(fa["net"], abs=0.01) and by["mantolama_dubel:120"]["quantity"] == pytest.approx(fa["net"] * 6, abs=0.1)

    # elle brüt alan: tahmini ezer
    client.patch(f"/api/projects/{pid}", json={"params": {"facade_gross_m2": 500}})
    fa2 = client.get(f"/api/projects/{pid}/systems").json()["facade"]
    assert fa2["source"] == "manual" and fa2["gross"] == 500
    # görünüş yüklenip dış hat eşlenince ölçülen alan hepsini ezer, cam düşülür
    with open(precast_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("ON CEPHE GORUNUSU.dxf", f, "application/dxf")})
    assert r.status_code == 201 and r.json()["discipline"] == "mapped"
    client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "CEPHE HAT", "etype": "item:CEPHE_BRUT:area"})
    client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "brn_glass", "etype": "item:CAM:area"})
    client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "inova prekast - YAZI", "etype": "item:PREKAST_PANEL"})
    fa3 = client.get(f"/api/projects/{pid}/systems").json()["facade"]
    assert fa3["source"] == "measured" and fa3["gross"] == pytest.approx(180.0) and fa3["net"] == pytest.approx(174.0)
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["mantolama_sistem:*"]["quantity"] == pytest.approx(174.0) and by["prekast_panel:gp-4"]["quantity"] == 3
    assert "cephe_brut:*" in by and "info" not in by["cephe_brut:*"]["detail"]   # ölçülen alan gerçek kalem


def test_label_pattern_and_markers(client, precast_dxf):
    """Etiket deseni: yalnız uyan yazılar sayılır; kesit / detay işaretleri hiç sayılmaz."""
    from app.parser.detectors.standard import _label_text
    assert _label_text("KESİT-3") == "" and _label_text("1-1 KESİTİ") == "" and _label_text("A-A DETAYI") == "" and _label_text("KÖPRÜ") == "KÖPRÜ"
    pid = client.post("/api/projects", json={"name": "Desen"}).json()["id"]
    with open(precast_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("cephe.dxf", f, "application/dxf")}, data={"discipline": "mapped"})
    did = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "inova prekast - YAZI", "etype": "item:PREKAST_PANEL::^EP"})
    assert r.status_code == 200, r.text
    layer = next(l for l in client.get(f"/api/drawings/{did}/layers").json()["layers"] if l["name"] == "inova prekast - YAZI")
    assert layer["mapped_measure"] == "label_count" and layer["mapped_pattern"] == "^EP"
    els = client.get(f"/api/drawings/{did}/elements").json()
    assert sorted(e["subtype"] for e in els if e["etype"] == "prekast_panel") == ["EP17", "EP17"]
    assert client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "x", "etype": "item:PREKAST_PANEL::("}).status_code == 400
    assert client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "x", "etype": "item:CAM:area:^EP"}).status_code == 400
