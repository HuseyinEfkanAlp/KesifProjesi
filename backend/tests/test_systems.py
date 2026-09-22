"""Katmanlı sistemler: katalog bileşenleri, yazıdan malzeme tarama, proje bileşen kararı, keşif genişletme, API."""
from __future__ import annotations

from app.parser.analyzer import analyze_file
from app.parser.detectors.standard import suggest_item
from app.parser.layer_profile import LayerProfile
from app.parser.materials import merge_materials, scan_texts
from app.standard.catalog import Catalog, normalize_components


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
    auto = client.get(f"/api/projects/{pid}/systems").json()["systems"]          # ÇATI katmanı otomatik eşlendi -> sistem hazır
    assert [s["code"] for s in auto] == ["KENET_CATI"]
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


def _zone_roof_dxf(path):
    """Üç bölgeli çatı planı: kenet (300 m²), çelik çatı (150 m²), yazısız (100 m²)."""
    import ezdxf
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 6        # metre
    for n in ("ÇATI", "YAZI"):
        doc.layers.add(n)
    msp = doc.modelspace()
    def rect(x, y, w, h):
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    msp.add_lwpolyline(rect(0, 0, 20, 15), close=True, dxfattribs={"layer": "ÇATI"})      # 300
    msp.add_lwpolyline(rect(22, 0, 10, 15), close=True, dxfattribs={"layer": "ÇATI"})     # 150
    msp.add_lwpolyline(rect(34, 0, 10, 10), close=True, dxfattribs={"layer": "ÇATI"})     # 100
    msp.add_text("KENET ÇATI", dxfattribs={"layer": "YAZI", "height": 0.5}).set_placement((8, 7))
    msp.add_text("ÇELİK ÇATI", dxfattribs={"layer": "YAZI", "height": 0.5}).set_placement((25, 7))
    for i in range(22):
        msp.add_text(f"N{i}", dxfattribs={"layer": "YAZI", "height": 0.25}).set_placement((1 + i * 1.2, 16))
    doc.saveas(path)
    return path


def test_celik_cati_tanima():
    """Çelik çatı artık zincire bağlı: katman adından öneri, kesit notundan sistem yükseltme."""
    cat = Catalog()
    assert suggest_item("ÇELİK ÇATI", cat) == "CELIK_CATI"
    assert suggest_item("ÇATI MAKAS", cat) == "CELIK_CATI"
    assert suggest_item("ÇATI TRAPEZ SAC", cat) == "CELIK_CATI"
    assert suggest_item("SANDVİÇ PANEL", cat) == "KOMPOZIT_PANEL"     # cephe paneli çatı değildir
    # düz "ÇATI" katmanı + kesitte "ÇELİK ÇATI" yazısı -> çelik çatı sistemine yükselir
    assert suggest_item("ÇATI", cat, scan_texts(["ÇELİK ÇATI MAKASI"])) == "CELIK_CATI"
    assert "CATI_SANDVIC_PANEL" in scan_texts(["SANDVİÇ PANEL 50 MM"])


def test_roof_zones_from_plan(client, tmp_path):
    """Çatı bölge bazlı: her kapalı alan sistemini kendi içindeki nottan alır; yazısız bölge sorulur."""
    p = _zone_roof_dxf(tmp_path / "cati_bolge.dxf")
    pid = client.post("/api/projects", json={"name": "Bölge"}).json()["id"]
    with open(p, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("ÇATI PLANI.dxf", f, "application/dxf")})
    assert r.status_code == 201, r.text
    assert any("bölge bazlı okundu" in w for w in r.json()["warnings"])
    sy = client.get(f"/api/projects/{pid}/systems").json()
    zones = {(z["system"], z["area"]): z for z in sy["roof"]["zones"]}
    assert set(zones) == {("KENET_CATI", 300.0), ("CELIK_CATI", 150.0), ("KENET_CATI", 100.0)}
    assert zones[("KENET_CATI", 300.0)]["source"] == "note" and "KENET" in zones[("KENET_CATI", 300.0)]["note"]
    assert zones[("CELIK_CATI", 150.0)]["source"] == "note"
    assert zones[("KENET_CATI", 100.0)]["source"] == "layer"      # içinde yazı yok: katmanın kalemiyle kaldı
    assert sy["roof"]["system_source"] == "zones" and sy["roof"]["area"] == 550.0
    assert any(c["code"] == "cati_bolge_yazisiz" for c in sy["checklist"])
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["celik_cati:*"]["quantity"] == 150.0                # çelik çatı artık ölçülüyor
    assert by["kenet_cati:*"]["quantity"] == 400.0                # 300 + yazısız 100
    # her bölge kendi sistem kalemidir; bileşenleri sistem panelinde kendi reçetesiyle listelenir
    assert {s["code"] for s in sy["systems"]} == {"KENET_CATI", "CELIK_CATI"}
    celik = next(s for s in sy["systems"] if s["code"] == "CELIK_CATI")
    assert celik["quantity"] == 150.0 and {c["code"] for c in celik["components"]} >= {"CELIK_KONSTRUKSIYON", "ASIK", "CATI_SANDVIC_PANEL"}
