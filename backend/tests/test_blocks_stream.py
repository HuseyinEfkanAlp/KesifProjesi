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
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("proje.dxf", f, "application/dxf")},
                        data={"auto": "false"})   # uzman seçim akışı
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


def test_buyuk_plan_blogu_acilir_doku_acilmaz(tmp_path, monkeypatch):
    """Bağlanmış dış referansta bütün plan tek bloktur (A1 blok: 89.599 nesne) — sınırı aşsa da açılmalı.
    Tek katmanda binlerce yazısız çizgi ise dokudur, açılmaz."""
    monkeypatch.setattr(sheets, "STREAM_BLOCK_MIN_BYTES", 0)
    monkeypatch.setattr(sheets, "BLOCK_EXPAND_MAX_ENTITIES", 500)
    doc = ezdxf.new("R2010")
    plan = doc.blocks.new("A1 BLOK - 22.12.2023")
    for i in range(600):
        plan.add_line((i, 0), (i, 50), dxfattribs={"layer": ("DUVAR", "KAPI", "AKS")[i % 3]})
    plan.add_text("ZEMİN KAT", dxfattribs={"layer": "YAZI"})
    doku = doc.blocks.new("DOKU")
    for i in range(600):
        doku.add_line((i, 0), (i, 1), dxfattribs={"layer": "DOKU"})
    msp = doc.modelspace()
    msp.add_blockref("A1 BLOK - 22.12.2023", (0, 0))
    msp.add_blockref("DOKU", (0, 100))
    src, out = tmp_path / "xref.dxf", tmp_path / "pafta.dxf"
    doc.saveas(src)
    crop_sheets(src, [((-10.0, -10.0, 700.0, 200.0), out)])
    katman = {e.dxf.layer for e in ezdxf.readfile(str(out)).modelspace() if e.dxftype() == "LINE"}
    assert {"DUVAR", "KAPI", "AKS"} <= katman          # plan bloğu açıldı
    assert "DOKU" not in katman                         # doku açılmadı


def test_orijine_yerlesen_plan_blogu_paftalara_kirpilarak_acilir(tmp_path, monkeypatch):
    """A1 blok mimarisi: bütün plan tek blok, orijine yerleşmiş; içeriği iki paftanın üstüne düşüyor. Yerleştirme
    noktası paftalarda olmadığı için hiç açılmıyordu (A1'in kat planlarında sıfır duvar)."""
    monkeypatch.setattr(sheets, "STREAM_BLOCK_MIN_BYTES", 0)
    doc = ezdxf.new("R2010")
    blk = doc.blocks.new("A1 BLOK XREF")
    blk.add_line((1000, 0), (1100, 0), dxfattribs={"layer": "DUVAR_BODRUM"})     # sol paftaya düşer
    blk.add_line((2000, 0), (2100, 0), dxfattribs={"layer": "DUVAR_ZEMIN"})      # sağ paftaya düşer
    doc.modelspace().add_blockref("A1 BLOK XREF", (0, 0))                          # 0,0 hiçbir paftada değil
    src, sol, sag = tmp_path / "x.dxf", tmp_path / "sol.dxf", tmp_path / "sag.dxf"
    doc.saveas(src)
    crop_sheets(src, [((900.0, -100.0, 1200.0, 100.0), sol), ((1900.0, -100.0, 2200.0, 100.0), sag)])
    k = lambda p: {e.dxf.layer for e in ezdxf.readfile(str(p)).modelspace() if e.dxftype() == "LINE"}   # noqa: E731
    assert k(sol) == {"DUVAR_BODRUM"}          # yalnız kendi parçası
    assert k(sag) == {"DUVAR_ZEMIN"}
