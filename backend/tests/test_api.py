import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine
from sqlmodel.pool import StaticPool


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KESIF_DATA_DIR", str(tmp_path / "data"))
    import importlib

    from app import db as dbmod
    importlib.reload(dbmod)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    dbmod.engine = engine
    from app import main as mainmod
    importlib.reload(mainmod)
    from app import models  # noqa: F401
    SQLModel.metadata.create_all(engine)

    from sqlmodel import Session

    def _get_session():
        with Session(engine) as s:
            yield s

    mainmod.app.dependency_overrides[dbmod.get_session] = _get_session
    with TestClient(mainmod.app) as c:
        yield c


def test_full_flow(client, storey_dxf, foundation_dxf):
    r = client.post("/api/projects", json={"name": "Deneme", "storey_height": 3.0, "slab_thickness": 0.15})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    with open(storey_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("kat.dxf", f, "application/dxf")},
                        data={"label": "Normal Kat", "storey_count": "3"})
    assert r.status_code == 201, r.text
    d1 = r.json()
    assert d1["unit"] == "cm" and d1["element_count"] == 8

    with open(foundation_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("temel.dxf", f, "application/dxf")},
                        data={"label": "Temel"})
    assert r.status_code == 201
    d2 = r.json()

    els = client.get(f"/api/drawings/{d1['id']}/elements").json()
    assert {e["etype"] for e in els} == {"column", "beam", "slab", "shear_wall"}

    q = client.get(f"/api/projects/{pid}/quantities").json()
    groups = {g["key"]: g for g in q["summary"]["groups"]}
    assert groups["column"]["concrete_m3"] == pytest.approx(4 * 0.18 * 2.85 * 3, abs=1e-2)
    assert groups["foundation:raft"]["concrete_m3"] == pytest.approx(42 * 0.6, abs=1e-2)   # kat çarpanı yok
    assert groups["foundation:strip"]["concrete_m3"] == pytest.approx(0.6 * 0.8 * 4.0, abs=1e-2)

    # eleman düzenleme: kolonu 40/40 yap -> alan yeniden türetilir
    col = next(e for e in els if e["etype"] == "column")
    r = client.patch(f"/api/elements/{col['id']}", json={"b": 0.4, "h": 0.4})
    assert r.status_code == 200 and r.json()["area"] == pytest.approx(0.16) and r.json()["manual"]
    # elle eleman ekleme
    r = client.post(f"/api/drawings/{d1['id']}/elements", json={"etype": "column", "name": "S9", "b": 0.5, "h": 0.5, "count": 2})
    assert r.status_code == 201
    q = client.get(f"/api/projects/{pid}/quantities").json()
    assert q["summary"]["groups"][0]["key"].startswith("foundation")
    col_total = next(g for g in q["summary"]["groups"] if g["key"] == "column")["concrete_m3"]
    assert col_total == pytest.approx((3 * 0.18 + 0.16 + 2 * 0.25) * 2.85 * 3, abs=1e-2)

    # katman eşleme: AKS katmanını kolona ata -> yeniden analiz; manuel elemanlar korunur
    r = client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "AKS", "etype": "column"})
    assert r.status_code == 200
    layers = client.get(f"/api/drawings/{d1['id']}/layers").json()["layers"]
    assert next(l for l in layers if l["name"] == "AKS")["etype"] == "column"
    els2 = client.get(f"/api/drawings/{d1['id']}/elements").json()
    assert any(e["name"] == "S9" for e in els2)
    client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "AKS", "etype": None})

    # fiyatlar
    prices = client.get(f"/api/projects/{pid}/prices").json()
    assert any(p["key"] == "beton:*" for p in prices)
    r = client.put(f"/api/projects/{pid}/prices", json=[{"key": "beton:*", "unit_price": 4000},
                                                       {"key": "kalip:*", "unit_price": 350},
                                                       {"key": "demir:*", "unit_price": 28}])
    assert r.status_code == 200
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    assert cost["grand_total"] > 0
    # beton/kalıp/demir fiyatlandı; yalnız sarf kalemleri (bağ teli, plywood, yağ, çivi) fiyatsız kalabilir
    DERIVED = {"doseme_kaplama", "tavan_siva_boya", "sap", "astar", "temel_su_yalitimi", "grobeton", "koruma_sapi"}
    assert not any(k.startswith(("beton:", "kalip:", "demir:")) for k in cost["missing_prices"]), cost["missing_prices"]
    # sarf, türetilmiş ve reçete kalemleri (bağ teli, plywood, iskele, işçilik saatleri…) fiyatsız kalabilir
    keys = {l["key"] for l in cost["lines"]}
    assert {"beton:fire", "demir:fire", "bag_teli:*", "plywood:*"} <= keys

    r = client.get(f"/api/projects/{pid}/cost.xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"

    svg = client.get(f"/api/drawings/{d1['id']}/preview.svg")
    assert svg.status_code == 200 and b"el-column" in svg.content

    # silme
    assert client.delete(f"/api/drawings/{d2['id']}").status_code == 204
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_rejects_non_dxf(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "X"}).json()["id"]
    bad = tmp_path / "x.step"
    bad.write_bytes(b"not a drawing")
    with open(bad, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("x.step", f, "application/octet-stream")})
    assert r.status_code == 400 and "dxf" in r.json()["detail"].lower()
    bad = tmp_path / "x.dwg"
    bad.write_bytes(b"AC1032 not really")
    with open(bad, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("x.dwg", f, "application/octet-stream")})
    assert r.status_code == 400   # dönüştürücü yoksa açıklama, varsa bozuk dosya
    bad2 = tmp_path / "y.dxf"
    bad2.write_bytes(b"garbage")
    with open(bad2, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("y.dxf", f, "application/dxf")})
    assert r.status_code == 400


def test_multi_discipline_flow(client, storey_dxf, arch_dxf, elec_dxf):
    pid = client.post("/api/projects", json={"name": "Karma", "storey_height": 3.0, "slab_thickness": 0.15,
                                             "params": {"wall_height": 2.8, "work_hours_per_day": 9}}).json()["id"]
    p = client.get(f"/api/projects/{pid}").json()
    assert p["params"]["wall_height"] == 2.8 and p["params"]["work_hours_per_day"] == 9 and p["params"]["plaster_sides"] == 2

    with open(storey_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("kat.dxf", f, "application/dxf")},
                        data={"label": "Kalıp", "storey_count": "2"})
    assert r.status_code == 201 and r.json()["discipline"] == "structural"
    with open(arch_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("mimari.dxf", f, "application/dxf")},
                        data={"label": "Mimari Zemin", "storey_count": "2", "discipline": "architectural"})
    assert r.status_code == 201, r.text
    arch = r.json()
    assert arch["discipline"] == "architectural"
    # yanlış disiplinle yüklenen elektrik paftası -> disiplin değiştirilince yeniden analiz
    with open(elec_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("elektrik.dxf", f, "application/dxf")},
                        data={"label": "Tava planı", "discipline": "structural"})   # yanlış disiplin elle seçildi
    elec = r.json()
    assert elec["element_count"] == 0 and elec["plan_type"] == "elk_tava"
    r = client.patch(f"/api/drawings/{elec['id']}", json={"discipline": "electrical"})
    assert r.status_code == 200 and r.json()["element_count"] > 0
    assert client.patch(f"/api/drawings/{elec['id']}", json={"discipline": "makine"}).status_code == 400

    layers = client.get(f"/api/drawings/{arch['id']}/layers").json()
    assert set(layers["element_types"]) == {"wall", "door", "window"}
    els = client.get(f"/api/drawings/{arch['id']}/elements").json()
    assert {e["etype"] for e in els} == {"wall", "door", "window"}
    # elle pencere ekle
    r = client.post(f"/api/drawings/{arch['id']}/elements", json={"etype": "window", "name": "P9", "b": 1.0, "h": 1.0, "count": 3})
    assert r.status_code == 201 and r.json()["area"] == pytest.approx(1.0)

    q = client.get(f"/api/projects/{pid}/quantities").json()
    assert q["summary"]["groups"]                      # statik özet
    keys = {i["key"] for i in q["boq"]["items"]}
    assert {"beton:column", "duvar:ytong:20", "pencere:p9_100x100", "cam:*", "siva:*", "tava:200x60", "kablo:nyy_4x16",
            "armatur:priz_priz_toprakli"} <= keys, keys
    p9 = next(i for i in q["boq"]["items"] if i["key"] == "pencere:p9_100x100")
    assert p9["quantity"] == 6                          # 3 adet × 2 kat
    discs = [d["discipline"] for d in q["boq"]["by_discipline"]]
    assert {"structural", "architectural", "electrical"} <= set(discs)
    assert all(d.startswith("ksf:") for d in discs if d not in ("structural", "architectural", "electrical"))   # türetilmiş + reçete kalemleri
    groups = [g["group"] for g in q["boq"]["by_group"]]
    assert groups == [g for g in ("KABA", "INCE", "MEK", "ELK", "ALT") if g in groups] and "KABA" in groups and "ELK" in groups

    prices = client.get(f"/api/projects/{pid}/prices").json()
    assert {"beton:*", "duvar:*", "duvar:ytong:20", "kablo:*", "tava:200x60"} <= {x["key"] for x in prices}
    r = client.put(f"/api/projects/{pid}/prices", json=[
        {"key": "duvar:*", "unit_price": 450, "labor_price": 250, "hours_per_unit": 0.8, "crew_size": 3, "brand": "Ytong"},
        {"key": "kablo:*", "unit_price": 40, "labor_price": 12, "hours_per_unit": 0.04, "crew_size": 2},
        {"key": "beton:*", "unit_price": 4000, "labor_price": 600, "hours_per_unit": 1.5, "crew_size": 6},
        {"key": "armatur:*", "unit_price": 700, "labor_price": 120, "hours_per_unit": 0.5},
    ])
    assert r.status_code == 200
    assert next(x for x in r.json() if x["key"] == "duvar:*")["brand"] == "Ytong"
    assert client.put(f"/api/projects/{pid}/prices", json=[{"key": "makine:*", "unit_price": 1}]).status_code == 400

    c = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    wall = next(l for l in c["lines"] if l["key"] == "duvar:ytong:20")
    assert wall["brand"] == "Ytong" and wall["labor_price"] == 250 and wall["price_source"] == "genel"
    assert wall["days"] == pytest.approx(wall["quantity"] * 0.8 / (3 * 9), abs=0.01)
    assert c["material_subtotal"] > 0 and c["labor_subtotal"] > 0
    assert c["duration"]["hours_per_day"] == 9 and c["duration"]["parallel_days"] <= c["duration"]["sequential_days"]
    assert {"structural", "architectural", "electrical"} <= {d["discipline"] for d in c["by_discipline"]}   # + türetilmiş (ksf:INC…)
    assert "kapi:k1_90x210" in c["missing_prices"]

    r = client.get(f"/api/projects/{pid}/cost.xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    svg = client.get(f"/api/drawings/{arch['id']}/preview.svg")
    assert svg.status_code == 200 and b"el-wall" in svg.content and b"el-window" in svg.content


def test_standard_flow_and_catalog_api(client, standard_dxf):
    # katalog
    cat = client.get("/api/catalog").json()
    assert "HAV" in cat["disciplines"] and any(i["code"] == "HAVA_KANAL" for i in cat["items"])
    chk = client.get("/api/catalog/check-layer", params={"name": "KSF-HAV-HAVA_KANAL-600x400"}).json()
    assert chk["valid"] and chk["known"] and chk["discipline_name"] == "Havalandırma"
    assert not client.get("/api/catalog/check-layer", params={"name": "DUVAR"}).json()["valid"]
    r = client.put("/api/catalog/items", json={"code": "yeni_kalem", "discipline": "ALT", "name": "Yeni kalem", "measure": "length"})
    assert r.status_code == 200 and r.json()["code"] == "YENI_KALEM" and r.json()["custom"]
    assert client.put("/api/catalog/items", json={"code": "x", "discipline": "QQQ", "name": "x", "measure": "count"}).status_code == 400
    t = client.get("/api/catalog/template.dxf")
    assert t.status_code == 200 and b"KSF-HAV-HAVA_KANAL" in t.content

    pid = client.post("/api/projects", json={"name": "KSF"}).json()["id"]
    with open(standard_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("ksf.dxf", f, "application/dxf")},
                        data={"label": "Zemin tesisat", "storey_count": "1", "discipline": "standard"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["discipline"] == "standard" and d["element_count"] >= 15
    layers = client.get(f"/api/drawings/{d['id']}/layers").json()
    assert layers["element_types"] == {}
    q = client.get(f"/api/projects/{pid}/quantities").json()
    by = {i["key"]: i for i in q["boq"]["items"]}
    assert by["hava_kanal:600x400"]["quantity"] == pytest.approx(15.0)
    assert by["sprinkler:k80_ust"]["quantity"] == 6
    assert by["dolgu:30"]["quantity"] == pytest.approx(6.0)
    assert by["yeni_kalem:x"]["kind_label"] == "Yeni kalem"           # kataloğa eklenen kalem tanındı
    discs = {dd["label"] for dd in q["boq"]["by_discipline"]}
    assert {"Havalandırma", "Yangın tesisatı", "Peyzaj", "Altyapı"} <= discs

    prices = client.get(f"/api/projects/{pid}/prices").json()
    hk = next(p for p in prices if p["key"] == "hava_kanal:*")
    assert hk["discipline_label"] == "Havalandırma" and hk["unit"] == "m"
    r = client.put(f"/api/projects/{pid}/prices", json=[{"key": "hava_kanal:*", "unit_price": 900, "labor_price": 300, "hours_per_unit": 0.6, "crew_size": 2},
                                                       {"key": "sprinkler:k80_ust", "unit_price": 250, "labor_price": 150, "hours_per_unit": 0.5}])
    assert r.status_code == 200
    c = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    hk_line = next(l for l in c["lines"] if l["key"] == "hava_kanal:600x400")
    assert hk_line["total"] == pytest.approx(15 * 1200) and hk_line["discipline_label"] == "Havalandırma"
    assert c["duration"]["parallel_days"] > 0
    assert client.get(f"/api/projects/{pid}/cost.xlsx").status_code == 200

    assert client.delete("/api/catalog/items/YENI_KALEM").status_code == 204
    assert client.delete("/api/catalog/items/YENI_KALEM").status_code == 404
    assert client.post("/api/catalog/reset").status_code == 200


def test_dwg_upload_when_converter_available(client, storey_dxf, tmp_path):
    """ODA File Converter kuruluysa DWG yükleme uçtan uca çalışır (DXF -> DWG -> yükle); yoksa test atlanır."""
    from app.parser.dwg import find_oda_converter
    import subprocess
    exe = find_oda_converter()
    if not exe:
        pytest.skip("ODA File Converter yok")
    src_dir = tmp_path / "in"; src_dir.mkdir(); out_dir = tmp_path / "out"; out_dir.mkdir()
    import shutil
    shutil.copyfile(storey_dxf, src_dir / "kat.dxf")
    subprocess.run([exe, str(src_dir), str(out_dir), "ACAD2018", "DWG", "0", "1", "*.dxf"], capture_output=True, timeout=300)
    dwg = out_dir / "kat.dwg"
    assert dwg.exists()
    assert client.get("/api/health").json()["dwg_support"] is True
    pid = client.post("/api/projects", json={"name": "DWG"}).json()["id"]
    with open(dwg, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("kat.DWG", f, "application/octet-stream")},
                        data={"label": "Kat", "storey_count": "1"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["filename"].endswith(".dxf") and d["element_count"] == 8 and d["unit"] == "cm"


def test_mapped_flow_api(client, facade_dxf):
    pid = client.post("/api/projects", json={"name": "Cephe"}).json()["id"]
    with open(facade_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("cephe.dxf", f, "application/dxf")},
                        data={"label": "Ön cephe", "discipline": "mapped"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["element_count"] > 0 and all(l["auto"] for l in d["layers"] if l["mapped_code"])   # katman adından otomatik eşlendi
    layers = {l["name"]: l for l in d["layers"]}
    assert layers["brn_hatch_gazbeton"]["suggested"] == "DUVAR_YTONG"
    assert client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "brn_hatch_gazbeton", "etype": "item:duvar ytong:area"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "brn_glass", "etype": "item:CAM"}).status_code == 200
    assert client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "x", "etype": "item:YOK_BOYLE"}).status_code == 400
    assert client.post(f"/api/projects/{pid}/layer-profile/map", json={"layer": "x", "etype": "item:CAM:kilo"}).status_code == 400
    d = client.get(f"/api/drawings/{d['id']}").json()
    assert d["element_count"] >= 5           # elle eşlenen 2 katman + otomatik eşlenen öteki katmanlar
    q = client.get(f"/api/projects/{pid}/quantities").json()
    by = {i["key"]: i for i in q["boq"]["items"]}
    assert by["duvar_ytong:*"]["quantity"] == pytest.approx(48.0) and by["cam:*"]["quantity"] == pytest.approx(9.0)
    assert by["duvar_ytong:*"]["discipline_label"] == "Mimari"
