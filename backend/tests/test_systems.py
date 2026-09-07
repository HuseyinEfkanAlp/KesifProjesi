"""Katmanlı sistemler: katalog bileşenleri, yazıdan malzeme tarama, proje bileşen kararı, keşif genişletme, API."""
from __future__ import annotations

from app.parser.analyzer import analyze_file
from app.parser.detectors.standard import suggest_item
from app.parser.layer_profile import LayerProfile
from app.parser.materials import merge_materials, scan_texts
from app.standard.catalog import Catalog, normalize_components
from tests.test_api import client  # noqa: F401


def test_catalog_components():
    cat = Catalog()
    kenet = cat.get("KENET_CATI")
    assert kenet.is_system and {c["code"] for c in kenet.components} >= {"OSB", "TASYUNU", "BUHAR_KESICI", "MERTEK"}
    assert cat.get("OSB").is_system is False
    assert normalize_components("OSB×1:11; TASYUNU x 2 : 5; MERTEK*1.6; ;") == [
        {"code": "OSB", "factor": 1.0, "spec": "11"}, {"code": "TASYUNU", "factor": 2.0, "spec": "5"}, {"code": "MERTEK", "factor": 1.6, "spec": ""}]
    it = cat.upsert_item({"code": "CATI_TEST", "discipline": "CAT", "name": "Deneme sistemi", "measure": "area",
                          "components": "OSB×1:18; MERTEK×2"})
    assert it.is_system and it.components[0] == {"code": "OSB", "factor": 1.0, "spec": "18"}
    try:
        cat.upsert_item({"code": "X", "discipline": "CAT", "name": "x", "measure": "area", "components": "YOK_BOYLE_KALEM"})
        assert False, "bilinmeyen bileşen kabul edilmemeli"
    except ValueError:
        pass
    # kalıcılık: bileşenler override dosyasına yazılır ve geri okunur
    cat2 = Catalog.from_overrides(cat.overrides())
    assert cat2.get("CATI_TEST").components == it.components


def test_scan_texts():
    ev = scan_texts(["ÇATI DETAYI - KENET ÇATI", "3- OSB 11 mm", "5- 10 cm TAŞYÜNÜ", "BUHAR KESİCİ", "EPS 5 cm mantolama", "S1 30/60"])
    assert ev["KENET_CATI"]["evidence"] == ["ÇATI DETAYI - KENET ÇATI"]
    assert ev["OSB"]["spec"] == "11MM" and ev["TASYUNU"]["spec"] == "10"
    assert "BUHAR_KESICI" in ev and ev["EPS"]["spec"] == "5" and "MANTOLAMA_SISTEM" in ev
    assert "MERTEK" not in ev
    merged = merge_materials([ev, {"OSB": {"evidence": ["OSB 18"], "spec": "18MM"}, "MERTEK": {"evidence": ["MERTEK"], "spec": ""}}])
    assert merged["OSB"]["evidence"] == ["3- OSB 11 mm", "OSB 18"] and merged["OSB"]["spec"] == "11MM" and "MERTEK" in merged


def test_roof_suggestion_and_materials(roof_dxf):
    cat = Catalog()
    r = analyze_file(str(roof_dxf), discipline="mapped", catalog=cat)
    assert "KENET_CATI" in r.materials and "OSB" in r.materials and "BUHAR_KESICI" not in r.materials
    layer = next(l for l in r.layers if l.name == "ÇATI")
    assert layer.suggested == "KENET_CATI"          # yazılarda kenet var: kiremit değil kenet sistemi
    assert suggest_item("ÇATI", cat) == "CATI_KIREMIT"   # kanıt yoksa düz kiremit
    assert suggest_item("ÇATI", cat, {"TERAS_CATI": {"evidence": ["x"]}}) == "TERAS_CATI"
    prof = LayerProfile().with_layer("item:KENET_CATI", "ÇATI")
    r2 = analyze_file(str(roof_dxf), profile=prof, discipline="mapped", catalog=cat)
    el = next(e for e in r2.elements if e.etype == "kenet_cati")
    assert abs(el.area - 200.0) < 0.5


def test_api_systems_flow(client, roof_dxf):
    pid = client.post("/api/projects", json={"name": "Çatı"}).json()["id"]
    with open(roof_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("CATI PLANI.dxf", f, "application/dxf")})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["discipline"] == "mapped" and d["plan_type"] == "mim_cati"
    # henüz katman eşlenmedi: sistem yok
    assert client.get(f"/api/projects/{pid}/systems").json()["systems"] == []
    layers = client.get(f"/api/drawings/{d['id']}/layers").json()["layers"]
    assert next(l for l in layers if l["name"] == "ÇATI")["suggested"] == "KENET_CATI"
    r = client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "ÇATI", "etype": "item:KENET_CATI"})
    assert r.status_code == 200

    sy = client.get(f"/api/projects/{pid}/systems").json()
    assert len(sy["systems"]) == 1
    k = sy["systems"][0]
    assert k["code"] == "KENET_CATI" and abs(k["quantity"] - 200) < 1
    comps = {c["code"]: c for c in k["components"]}
    assert comps["OSB"]["source"] == "project" and comps["OSB"]["include"] and comps["OSB"]["spec"] == "11MM"
    assert comps["TASYUNU"]["spec"] == "10" and comps["MERTEK"]["include"]
    assert comps["BUHAR_KESICI"]["source"] == "missing" and not comps["BUHAR_KESICI"]["include"]
    assert comps["ASIK"]["source"] == "missing"
    assert k["missing"] == ["Buhar kesici", "Aşık (ahşap / çelik)"] and sy["missing"] == 2
    assert any("projede yazmıyor" in w and "Buhar kesici" in w for w in sy["warnings"])

    # keşif: sistem satırı fiyatlanmaz, dahil bileşenler ayrı kalem
    boq = client.get(f"/api/projects/{pid}/quantities").json()["boq"]
    by_key = {i["key"]: i for i in boq["items"]}
    assert by_key["kenet_cati:*"]["detail"]["system"] is True
    assert abs(by_key["osb:11mm"]["quantity"] - 200) < 1 and abs(by_key["mertek:5x10"]["quantity"] - 340) < 1
    assert "buhar_kesici:*" not in by_key and "asik:*" not in by_key
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    assert not any(l["key"] == "kenet_cati:*" for l in cost["lines"]) and any(l["key"] == "osb:11mm" for l in cost["lines"])

    # kullanıcı: buhar kesici projede var (elle ekle), taşyünü 12 cm, mertek çıkar
    r = client.put(f"/api/projects/{pid}/systems", json={"KENET_CATI": {
        "BUHAR_KESICI": {"include": True}, "TASYUNU": {"spec": "12"}, "MERTEK": {"include": False}}})
    assert r.status_code == 200, r.text
    comps = {c["code"]: c for c in r.json()["systems"][0]["components"]}
    assert comps["BUHAR_KESICI"]["include"] and comps["BUHAR_KESICI"]["source"] == "manual"
    assert comps["TASYUNU"]["spec"] == "12" and comps["MERTEK"]["source"] == "excluded"
    assert r.json()["missing"] == 1
    by_key = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert "buhar_kesici:*" in by_key and "mertek:5x10" not in by_key and "tasyunu:12" in by_key
    # kararı geri al
    r = client.put(f"/api/projects/{pid}/systems", json={"KENET_CATI": {"MERTEK": {}}})
    assert {c["code"]: c for c in r.json()["systems"][0]["components"]}["MERTEK"]["include"]
    assert client.put(f"/api/projects/{pid}/systems", json={"OSB": {"X": {"include": True}}}).status_code == 400
    assert client.put(f"/api/projects/{pid}/systems", json={"KENET_CATI": {"YOK": {"include": True}}}).status_code == 400
    # katalog API: bileşenli kalem ekleme
    r = client.put("/api/catalog/items", json={"code": "SANDVIC_CATI", "discipline": "CAT", "name": "Sandviç çatı", "measure": "area",
                                               "components": "CATI_SANDVIC_PANEL×1:50; ASIK×1.2"})
    assert r.status_code == 200 and r.json()["is_system"] and r.json()["components"][1]["factor"] == 1.2
