"""Türetilmiş kalemler ve tamlık kontrolü; çatı alanı / sistemi; başlık konumundan pafta ayırma."""
from __future__ import annotations

import ezdxf
import numpy as np
import pytest

from app.parser.sheets import boxes_from_titles, scan_sheets
from tests.fixtures.make_dxf import _rect
from tests.test_api import client  # noqa: F401


def test_boxes_from_titles(tmp_path):
    """Çerçevesiz 4 pafta yan yana, başlıklar aynı hizada: bantlar başlık x konumlarından çıkar."""
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 5
    for n in ("KOLON", "YAZI"):
        doc.layers.add(n)
    msp = doc.modelspace()
    titles = ("ZEMİN KAT PLANI", "BİRİNCİ KAT PLANI", "ÇATI KATI PLANI", "KESİTLER")
    for k, title in enumerate(titles):
        ox = k * 3000
        msp.add_text(title, dxfattribs={"layer": "YAZI", "height": 40}).set_placement((ox + 100, 2200))
        for i in range(6):
            msp.add_lwpolyline(_rect(ox + 300 + i * 400, 500 + (i % 2) * 600, 50, 50), close=True, dxfattribs={"layer": "KOLON"})
            msp.add_text(f"S{i}", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((ox + 300 + i * 400, 560))
    p = tmp_path / "cercevesiz.dxf"; doc.saveas(p)
    sc = scan_sheets(p)
    assert len(sc.sheets) == 4 and all(s.source == "title" for s in sc.sheets)
    assert [s.title for s in sc.sheets] == list(titles)
    for s in sc.sheets:
        assert s.entity_count >= 12
    # doğrudan: uzak aykırı nesne bandı bozmaz
    ts = [(k * 3000 + 100, 2200, 40, t) for k, t in enumerate(titles)]
    xs = np.array([100.0, 3100.0, 6100.0, 9100.0, 200.0, 200.0, 200.0, 200.0, 250.0, 250.0])
    ys = np.array([2200.0, 2200.0, 2200.0, 2200.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1e6])
    b = boxes_from_titles(ts, xs, ys, 12000.0)
    assert len(b) >= 1 and b[0][3] < 5000


def test_roof_and_derived_via_api(client, storey_dxf, foundation_dxf, roof_dxf):
    pid = client.post("/api/projects", json={"name": "Türetme", "storey_height": 3.0}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("ZEMIN KAT KALIP PLANI.dxf", f, "application/dxf")}, data={"storey_count": "3"})
    with open(foundation_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("TEMEL KALIP PLANI.dxf", f, "application/dxf")})
    sy = client.get(f"/api/projects/{pid}/systems").json()
    # çatı: en üst kat planı oturumundan tahmin; sistem seçilmedi -> kontrol listesi sorar
    assert sy["roof"]["source"] == "estimated" and sy["roof"]["area"] > 10 and sy["roof"]["system"] == ""
    codes = {c["code"] for c in sy["checklist"]}
    assert {"cati_sistemi", "cephe_sistemi", "korkuluk", "drenaj"} <= codes
    rules = {d["rule"] for d in sy["derived"]}
    assert {"tavan", "sap", "kaplama", "temel_yalitim", "grobeton", "koruma_sapi"} <= rules
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["tavan_siva_boya:*"]["detail"]["derived"] is True and by["sap:5"]["unit"] == "m³"
    assert by["grobeton:10"]["quantity"] == pytest.approx(by["temel_su_yalitimi:*"]["quantity"] * 0.10, rel=1e-3)
    # kural kapatma
    client.patch(f"/api/projects/{pid}", json={"params": {"derived_off": "kaplama, sap"}})
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert "doseme_kaplama:*" not in by and "sap:5" not in by and "tavan_siva_boya:*" in by
    # çatı sistemi: kesit notlarındaki kanıttan otomatik (roof_dxf yazılarında KENET)
    with open(roof_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("CATI DETAYI.dxf", f, "application/dxf")}, data={"discipline": "mapped"})
    assert r.status_code == 201
    sy = client.get(f"/api/projects/{pid}/systems").json()
    assert sy["roof"]["system"] == "KENET_CATI" and sy["roof"]["system_source"] == "evidence"
    assert "cati_sistemi" not in {c["code"] for c in sy["checklist"]}
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["kenet_cati:*"]["quantity"] == pytest.approx(sy["roof"]["area"], abs=0.01) and by["kenet_cati:*"]["detail"]["system"]
    assert by["cati_alani:*"]["detail"]["info"] is True and by["osb:11mm"]["quantity"] == pytest.approx(sy["roof"]["area"], abs=0.01)
    # elle çatı alanı ve sistem
    client.patch(f"/api/projects/{pid}", json={"params": {"roof_area_m2": 250, "roof_system": "TERAS_CATI"}})
    sy = client.get(f"/api/projects/{pid}/systems").json()
    assert sy["roof"]["area"] == 250 and sy["roof"]["system"] == "TERAS_CATI" and sy["roof"]["system_source"] == "manual"
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["teras_cati:*"]["quantity"] == 250 and "kenet_cati:*" not in by
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    assert not any(l["key"] in ("cati_alani:*", "teras_cati:*") for l in cost["lines"])
