"""Çok büyük dosyalarda blok içeriğinin akışla açılması; doğrama poz listesi."""
from __future__ import annotations

import ezdxf
import pytest

from app.parser import sheets
from app.parser.analyzer import analyze_file
from app.parser.schedules import parse_schedule, parse_schedule_text
from app.parser.sheets import crop_sheets, scan_sheets
from tests.fixtures.make_dxf import make_block_plan_dxf


@pytest.fixture(scope="module")
def block_dxf(tmp_path_factory):
    return make_block_plan_dxf(tmp_path_factory.mktemp("dxf") / "blok.dxf")


def test_parse_schedule():
    r = parse_schedule_text("Poz: EMP3\n9 Adet AÇILIR KAPI")
    assert r.poz == "EMP3" and r.count == 9 and r.note == "AÇILIR KAPI"
    r = parse_schedule_text("Poz: EMP2\\PAdet: 2\\P(FOTOSELLİ KAPI)")
    assert r.poz == "EMP2" and r.count == 2 and r.note == "FOTOSELLİ KAPI"
    assert parse_schedule_text("Poz: EMP914").count == 14 and parse_schedule_text("Poz: EMP914").poz == "EMP9"
    assert parse_schedule_text("Poz: EMP4'\nAdet: 1").poz == "EMP4'"
    assert parse_schedule_text("EMP1") is None and parse_schedule_text("Poz: EMP1") is None
    rows = parse_schedule(["Poz: EMP1 Adet: 77", "Poz: EMP1\nAdet: 82", "Poz: EMP7 Adet: 34"])
    assert [(r.poz, r.count) for r in rows] == [("EMP1", 82), ("EMP7", 34)]


def test_stream_block_expansion(block_dxf, tmp_path, monkeypatch):
    monkeypatch.setattr(sheets, "STREAM_BLOCK_MIN_BYTES", 0)      # küçük dosyada da akış yolu
    monkeypatch.setattr(sheets, "BLOCK_EXPAND_MAX_ENTITIES", 5000)
    sc = scan_sheets(block_dxf)
    assert len(sc.sheets) == 2
    plan = next(s for s in sc.sheets if "KALIP" in s.title)
    dog = next(s for s in sc.sheets if "DOĞRAMA" in s.title)
    out1, out2 = tmp_path / "plan.dxf", tmp_path / "dograma.dxf"
    crop_sheets(block_dxf, [(plan.bbox, out1), (dog.bbox, out2)])
    doc = ezdxf.readfile(str(out1))
    msp = doc.modelspace()
    kol = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "KOLON"]
    assert len(kol) == 2
    xs = sorted(min(p[0] for p in e.get_points()) for e in kol)
    assert xs == pytest.approx([300.0, 700.0])            # taban noktası (100,100) -> yerleştirme (100,100): kayma yok
    texts = {e.dxf.text for e in msp if e.dxftype() == "TEXT"}
    assert {"S1", "(50/50)"} <= texts                     # iç içe blok açıldı
    ins = [e for e in msp if e.dxftype() == "INSERT"]
    assert sum(1 for e in ins if e.dxf.name == "KAPI90") == 3     # INSERT işaretleri korunur (adet sayımı)
    assert not any(e.dxf.layer == "DOKU" and e.dxftype() == "LINE" for e in msp)   # dev blok açılmadı
    # analiz: kolonlar bulunur; kapılar KAPI katmanındaki bloklardan sayılır
    r = analyze_file(str(out1), discipline="structural")
    assert len(r.by_type("column")) == 2 and all(e.b == pytest.approx(0.5) for e in r.by_type("column"))
    r2 = analyze_file(str(out1), discipline="architectural")
    assert len(r2.by_type("door")) == 3
    # doğrama paftası: poz listesi elemanları
    r3 = analyze_file(str(out2), discipline="mapped")
    d = {e.subtype: e.count for e in r3.by_type("dograma")}
    assert d == {"EMP1": 82, "EMP3": 9, "EMP9": 14} and any("poz listesi" in w for w in r3.warnings)


def test_api_schedule_to_boq(client, block_dxf, monkeypatch):
    monkeypatch.setattr(sheets, "STREAM_BLOCK_MIN_BYTES", 0)
    pid = client.post("/api/projects", json={"name": "Blok"}).json()["id"]
    with open(block_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("proje.dxf", f, "application/dxf")})
    assert r.status_code == 200 and r.json()["needs_sheet_selection"]
    sheets_ = {s["title"]: s for s in r.json()["sheets"]}
    dog = sheets_["DOĞRAMA DETAYLARI"]
    assert dog["plan_type"] == "mim_dograma"
    r = client.post(f"/api/projects/{pid}/drawings/from-source", json={
        "token": r.json()["source"]["token"],
        "sheets": [{"index": sheets_["ZEMİN KAT KALIP PLANI"]["index"]}, {"index": dog["index"], "discipline": "mapped"}]})
    assert r.status_code == 201, r.text
    by = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    assert by["dograma:emp1"]["quantity"] == 82 and by["dograma:emp9"]["quantity"] == 14 and by["dograma:emp1"]["unit"] == "adet"
    assert by["dograma:emp1"]["discipline"] == "ksf:MIM"
