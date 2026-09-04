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
    assert cost["grand_total"] > 0 and cost["missing_prices"] == []

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
    bad = tmp_path / "x.dwg"
    bad.write_bytes(b"AC1032 not really")
    with open(bad, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("x.dwg", f, "application/octet-stream")})
    assert r.status_code == 400 and "DXF" in r.json()["detail"]
    bad2 = tmp_path / "y.dxf"
    bad2.write_bytes(b"garbage")
    with open(bad2, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("y.dxf", f, "application/dxf")})
    assert r.status_code == 400
