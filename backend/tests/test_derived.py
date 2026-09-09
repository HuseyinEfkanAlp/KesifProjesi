"""Türetilmiş kalemler ve tamlık kontrolü; çatı alanı / sistemi; başlık konumundan pafta ayırma."""
from __future__ import annotations

import ezdxf
import numpy as np
import pytest

from app.parser.sheets import boxes_from_titles, scan_sheets
from tests.fixtures.make_dxf import _rect


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
    assert {"tavan", "temel_yalitim", "grobeton", "koruma_sapi"} <= rules
    assert "sap" not in rules and "kaplama" not in rules            # mahal yazısı yok: şap / kaplama oturumdan türetilmez
    assert "kaplama_alani" in codes and sy["finish"]["source"] == "none"
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["tavan_siva_boya:*"]["detail"]["derived"] is True
    assert by["grobeton:10"]["quantity"] == pytest.approx(by["temel_su_yalitimi:*"]["quantity"] * 0.10, rel=1e-3)
    # şap / kaplama alanı elle
    client.patch(f"/api/projects/{pid}", json={"params": {"finish_area_m2": 120}})
    sy = client.get(f"/api/projects/{pid}/systems").json()
    assert sy["finish"]["source"] == "manual" and sy["finish"]["area"] == 120
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["sap:5"]["quantity"] == pytest.approx(6.0) and by["doseme_kaplama:*"]["quantity"] == 120
    # kural kapatma
    client.patch(f"/api/projects/{pid}", json={"params": {"derived_off": "kaplama, sap"}})
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert "doseme_kaplama:*" not in by and "sap:5" not in by and "tavan_siva_boya:*" in by
    client.patch(f"/api/projects/{pid}", json={"params": {"derived_off": "", "finish_area_m2": None}})
    # çatı sistemi: kesit notlarındaki kanıttan otomatik (roof_dxf yazılarında KENET)
    with open(roof_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("CATI DETAYI.dxf", f, "application/dxf")}, data={"discipline": "mapped"})
    assert r.status_code == 201
    sy = client.get(f"/api/projects/{pid}/systems").json()
    assert sy["roof"]["system"] == "KENET_CATI" and sy["roof"]["system_source"] == "evidence"
    assert "cati_sistemi" not in {c["code"] for c in sy["checklist"]}
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["kenet_cati:*"]["quantity"] == pytest.approx(sy["roof"]["area"], abs=0.01) and by["kenet_cati:*"]["detail"]["system"]
    # ÇATI katmanı otomatik eşlenip ölçüldüğünden bilgi satırı yerine ölçülen kalem var; bileşenler çatı alanı kadar
    assert "cati_alani:*" not in by or by["cati_alani:*"]["detail"]["info"] is True
    assert by["osb:11mm"]["quantity"] == pytest.approx(sy["roof"]["area"], abs=0.01)
    # elle çatı sistemi: ÇATI katmanı otomatik eşlemede seçilen sisteme gider; alan çizimden ölçüldüğü için parametre değil ölçüm esas
    client.patch(f"/api/projects/{pid}", json={"params": {"roof_area_m2": 250, "roof_system": "TERAS_CATI"}})
    sy = client.get(f"/api/projects/{pid}/systems").json()
    assert sy["roof"]["source"] == "measured" and sy["roof"]["system"] == "TERAS_CATI" and sy["roof"]["system_source"] == "manual"
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["teras_cati:*"]["quantity"] == pytest.approx(sy["roof"]["area"], abs=0.01) and "kenet_cati:*" not in by
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    assert not any(l["key"] in ("cati_alani:*", "teras_cati:*") for l in cost["lines"])


def test_rooms_finish_area(client, tmp_path):
    """Mahal alanı yazıları: yalnız seçili mahal türleri (lobi, vitrin…) şap / kaplama alır; mağazalar dışarıda kalır."""
    import ezdxf
    from app.parser.schedules import parse_room_area, parse_rooms
    r = parse_room_area("CALZEDONIA\n106.60m2"); assert r.name == "CALZEDONIA" and r.area_m2 == 106.6
    r = parse_room_area("LOBİ 45,20 m²"); assert r.name == "LOBİ" and r.area_m2 == 45.2
    assert parse_room_area("14.93m2").name == "MAHAL" and parse_room_area("S1 30/60") is None and parse_room_area("+4.15") is None
    assert len(parse_rooms(["LOBİ 45.20 m2", "LOBİ 45.20 m2", "VİTRİN 12 m2"])) == 2
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 5
    for n in ("DUVAR", "YAZI"):
        doc.layers.add(n)
    msp = doc.modelspace()
    for y in (0, 400):
        msp.add_lwpolyline(_rect(0, y, 600, 20), close=True, dxfattribs={"layer": "DUVAR"})      # 6 m duvarlar
    for i, t in enumerate(("LOBİ\\P45.20 m2", "VİTRİN 1\\P12.50 m2", "CALZEDONIA\\P106.60m2", "TWIST\\P199.85m2", "WC\\P8.00 m2")):
        msp.add_mtext(t, dxfattribs={"layer": "YAZI", "char_height": 15}).set_location((60 + i * 120, 200))
    for i in range(22):   # birim sağlaması için yeterli yazı (20 cm)
        msp.add_text(f"M{i}", dxfattribs={"layer": "YAZI", "height": 20}).set_placement((20 + i * 25, 100))
    p = tmp_path / "mahal.dxf"; doc.saveas(p)
    pid = client.post("/api/projects", json={"name": "Mahal"}).json()["id"]
    with open(p, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("ZEMIN KAT PLANI.dxf", f, "application/dxf")}, data={"storey_count": "2"})
    assert r.status_code == 201 and r.json()["discipline"] == "architectural" and any("Mahal alanı" in w for w in r.json()["warnings"])
    sy = client.get(f"/api/projects/{pid}/systems").json()
    fin = sy["finish"]
    assert fin["source"] == "rooms" and fin["area"] == pytest.approx((45.2 + 12.5) * 2)
    assert {r["name"] for r in fin["rooms"] if r["included"]} == {"LOBİ", "VİTRİN 1"} and len(fin["excluded"]) == 3
    assert any(c["code"] == "kaplama_disi" for c in sy["checklist"])
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["sap:5"]["quantity"] == pytest.approx((45.2 + 12.5) * 2 * 0.05, rel=1e-3) and by["doseme_kaplama:*"]["quantity"] == pytest.approx(115.4)
    # ıslak hacim (WC 8 m² × 2 kat): yer seramiği, duvar seramiği (4·√8 × 2,2 − kapı) ve sürme izolasyon türetilir
    assert by["seramik_zemin:*"]["quantity"] == pytest.approx(16.0, rel=1e-3)
    assert by["seramik_duvar:*"]["quantity"] == pytest.approx((4 * 8 ** 0.5 * 2.2 - 0.9 * 2.1) * 2, rel=1e-3)
    assert by["surme_izolasyon:*"]["quantity"] == pytest.approx(16.0 + 4 * 8 ** 0.5 * 0.3 * 2, rel=1e-3)
    # mağazaları da dahil et
    client.patch(f"/api/projects/{pid}", json={"params": {"finish_rooms": "LOBİ, VİTRİN, CALZEDONIA, TWIST, WC"}})
    fin = client.get(f"/api/projects/{pid}/systems").json()["finish"]
    assert fin["area"] == pytest.approx((45.2 + 12.5 + 106.6 + 199.85 + 8.0) * 2) and not fin["excluded"]
