"""Çok paftalı DXF: pafta tespiti (çerçeve ve kümeleme), kırpma ve API akışı."""
from __future__ import annotations

import ezdxf
import pytest

from app.parser.analyzer import analyze_file
from app.parser.sheets import crop_sheets, scan_sheets
from tests.fixtures.make_dxf import _rect

FRAME_W, FRAME_H = 2000, 1400          # pafta çerçevesi (cm)


def _add_plan(msp, ox: float, oy: float, prefix: str, ncols: int) -> None:
    """(ox, oy) köşeli paftaya küçük bir kalıp planı çizer: ncols adet 50x50 kolon + etiketler."""
    for i in range(ncols):
        x, y = ox + 300 + i * 400, oy + 400
        msp.add_lwpolyline(_rect(x, y, 50, 50), close=True, dxfattribs={"layer": "KOLON"})
        msp.add_text(f"{prefix}{i + 1}", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((x, y + 60))
        msp.add_text("(50/50)", dxfattribs={"layer": "YAZI", "height": 6}).set_placement((x, y + 70))


def make_multi_sheet_dxf(path, frames: bool = True):
    """Yan yana 3 pafta: temel (2 kolon), zemin (3 kolon), detay (kolonsuz).

    frames=True: her paftanın çevresinde ANTET katmanında kapalı dikdörtgen + antet kutusu.
    frames=False: çerçeve yok; paftalar sadece boşlukla ayrılır (kümeleme yedeği).
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for name in ("KOLON", "YAZI", "ANTET", "DETAY"):
        doc.layers.add(name)
    msp = doc.modelspace()
    specs = [("TEMEL KALIP PLANI", "SB", 2), ("ZEMİN KAT KALIP PLANI", "SZ", 3), ("KOLON DETAYLARI", "", 0)]
    # çerçeveli paftalar bitişik olabilir; çerçevesizlerde paftalar arası boşluk pafta içi boşluklardan büyük olmalı
    gap = 300 if frames else 1500
    for k, (title, prefix, ncols) in enumerate(specs):
        ox = k * (FRAME_W + gap)
        if frames:
            msp.add_lwpolyline(_rect(ox, 0, FRAME_W, FRAME_H), close=True, dxfattribs={"layer": "ANTET"})
            msp.add_lwpolyline(_rect(ox + 1500, 0, 500, 300), close=True, dxfattribs={"layer": "ANTET"})  # antet kutusu
        msp.add_text(title, dxfattribs={"layer": "ANTET", "height": 40}).set_placement((ox + 1550, 150))
        if ncols:
            _add_plan(msp, ox, 0, prefix, ncols)
        else:
            for i in range(12):   # detay paftası: kolonsuz çizgiler
                msp.add_line((ox + 200, 400 + i * 60), (ox + 1400, 400 + i * 60), dxfattribs={"layer": "DETAY"})
    doc.saveas(path)
    return path


@pytest.fixture(scope="module")
def multi_dxf(tmp_path_factory):
    return make_multi_sheet_dxf(tmp_path_factory.mktemp("sheets") / "proje.dxf")


@pytest.fixture(scope="module")
def multi_dxf_noframe(tmp_path_factory):
    return make_multi_sheet_dxf(tmp_path_factory.mktemp("sheets") / "proje_cercevesiz.dxf", frames=False)


def test_scan_finds_frames_and_titles(multi_dxf):
    scan = scan_sheets(multi_dxf)
    assert scan.insunits == 5 and scan.multi_sheet
    titles = [s.title for s in scan.sheets]
    assert titles == ["TEMEL KALIP PLANI", "ZEMİN KAT KALIP PLANI", "KOLON DETAYLARI"]
    assert all(s.source == "frame" and s.titled for s in scan.sheets)
    x0, y0, x1, y1 = scan.sheets[1].bbox
    assert x0 == pytest.approx(FRAME_W + 300) and x1 == pytest.approx(2 * FRAME_W + 300)
    assert y0 == pytest.approx(0) and y1 == pytest.approx(FRAME_H)


def test_scan_cluster_fallback(multi_dxf_noframe):
    scan = scan_sheets(multi_dxf_noframe)
    assert len(scan.sheets) == 3
    assert [s.title for s in scan.sheets] == ["TEMEL KALIP PLANI", "ZEMİN KAT KALIP PLANI", "KOLON DETAYLARI"]
    assert all(s.source == "cluster" for s in scan.sheets)


def test_single_sheet_drawing_is_not_multi(storey_dxf):
    scan = scan_sheets(storey_dxf)
    assert not scan.multi_sheet


def test_crop_and_analyze(multi_dxf, tmp_path):
    scan = scan_sheets(multi_dxf)
    targets = [(scan.sheets[0].bbox, tmp_path / "temel.dxf"), (scan.sheets[1].bbox, tmp_path / "zemin.dxf")]
    counts = crop_sheets(multi_dxf, targets)
    assert counts[0] > 0 and counts[1] > 0
    res = analyze_file(str(tmp_path / "zemin.dxf"))
    cols = [e for e in res.elements if e.etype == "column"]
    assert len(cols) == 3 and sorted(e.name for e in cols) == ["SZ1", "SZ2", "SZ3"]
    assert res.unit == "cm"
    res2 = analyze_file(str(tmp_path / "temel.dxf"))
    assert sorted(e.name for e in res2.elements if e.etype == "column") == ["SB1", "SB2"]
    assert not [e for e in res2.elements if e.etype == "foundation"]   # radye çokgeni/etiketi yok -> tahmin de yok


def test_api_sheet_selection_flow(client, multi_dxf):
    pid = client.post("/api/projects", json={"name": "Çok pafta", "storey_height": 3.0}).json()["id"]
    with open(multi_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("proje.dxf", f, "application/dxf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["needs_sheet_selection"] and len(body["sheets"]) == 3
    token = body["source"]["token"]
    assert body["source"]["can_use_whole"]

    r = client.get(f"/api/sources/{token}/sheets")
    assert r.status_code == 200 and len(r.json()["sheets"]) == 3

    r = client.post(f"/api/projects/{pid}/drawings/from-source", json={
        "token": token,
        "sheets": [{"index": 0, "label": "Temel"}, {"index": 1, "label": "Zemin", "storey_count": 2, "storey_height": 3.5}],
    })
    assert r.status_code == 201, r.text
    ds = r.json()
    assert [d["label"] for d in ds] == ["Temel", "Zemin"]
    assert ds[0]["element_count"] == 2 and ds[1]["element_count"] == 3
    assert ds[1]["storey_count"] == 2 and ds[1]["storey_height"] == 3.5 and ds[0]["storey_height"] is None

    # pafta bazlı kat yüksekliği metraja yansır: zemin kolonları 0.25 m² × H(3.5, brüt: −d) × 2 kat
    q = client.get(f"/api/projects/{pid}/quantities").json()
    col = next(g for g in q["summary"]["groups"] if g["key"] == "column")
    assert col["concrete_m3"] == pytest.approx(2 * 0.25 * (3.0 - 0.15) + 3 * 0.25 * (3.5 - 0.15) * 2, abs=1e-2)

    # kat yüksekliğini kaldır -> proje değeri
    r = client.patch(f"/api/drawings/{ds[1]['id']}", json={"storey_height": None})
    assert r.status_code == 200 and r.json()["storey_height"] is None

    r = client.post(f"/api/projects/{pid}/drawings/from-source", json={"token": token, "sheets": []})
    assert r.status_code == 400
    r = client.post(f"/api/projects/{pid}/drawings/from-source", json={"token": "0123456789", "sheets": [{"index": 0}]})
    assert r.status_code == 404


def test_crop_margin_does_not_enter_neighbour_frame(tmp_path):
    """Bitişik iki çerçeve: sınıra yakın yazı yalnız kendi paftasına yazılır (kırpma payı komşuya taşmaz)."""
    import ezdxf
    from app.parser.sheets import crop_sheets
    from app.parser.loader import load_dxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    a = (0.0, 0.0, 100.0, 100.0)
    b = (100.0, 0.0, 200.0, 100.0)
    for x0, y0, x1, y1 in (a, b):
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "CERCEVE"})
    msp.add_text("P45 4Ø14 ila. l=160", dxfattribs={"height": 1.0, "insert": (99.0, 50.0), "layer": "POZ"})   # A'nın sağ kenarı
    msp.add_text("P46 4Ø14 ila. l=160", dxfattribs={"height": 1.0, "insert": (101.0, 50.0), "layer": "POZ"})  # B'nin sol kenarı
    blk = doc.blocks.new("KAPI_90"); blk.add_line((0, 0), (0.9, 0))
    inner = doc.blocks.new("IC"); inner.add_line((0, 0), (1, 1))
    outer = doc.blocks.new("DIS"); outer.add_blockref("IC", (0, 0))
    for x in (10.0, 20.0, 30.0):
        msp.add_blockref("KAPI_90", (x, 10.0), dxfattribs={"layer": "KAPI"})
        msp.add_blockref("KAPI_90", (100 + x, 10.0), dxfattribs={"layer": "KAPI"})
    msp.add_blockref("DIS", (50.0, 50.0), dxfattribs={"layer": "DETAY"})
    src = tmp_path / "two.dxf"; doc.saveas(src)
    da, db = tmp_path / "a.dxf", tmp_path / "b.dxf"
    crop_sheets(src, [(a, da), (b, db)])
    dra, drb = load_dxf(str(da)), load_dxf(str(db))
    ta = [e.text for e in dra.texts()]
    tb = [e.text for e in drb.texts()]
    assert ta == ["P45 4Ø14 ila. l=160"] and tb == ["P46 4Ø14 ila. l=160"]
    # küçük dosya (ezdxf) yolunda da blok yerleşimleri yazılır (kapı / pencere / armatür sayımı) ve iç içe blok açılır
    assert len([i for i in dra.inserts() if i.block == "KAPI_90"]) == 3 and len([i for i in drb.inserts() if i.block == "KAPI_90"]) == 3
    assert any(e.kind == "line" and e.source.startswith("INSERT") is False and e.layer == "DETAY" for e in dra.entities) or \
        any(e.layer == "DETAY" and e.kind == "line" for e in dra.entities)
    # tek pafta kırpılsa da komşu çerçeve verilirse pay oraya taşmaz
    crop_sheets(src, [(a, da)], neighbors=[a, b])
    assert [e.text for e in load_dxf(str(da)).texts()] == ["P45 4Ø14 ila. l=160"]


def test_title_inside_block_definition_and_stream_hatch(tmp_path):
    """Antet bloğunun içindeki 'PLANI' yazısı pafta başlığı olur; büyük dosya yolunda (akış) tarama sınırları da kırpılır."""
    import ezdxf
    from app.parser.sheets import crop_sheets, scan_sheets
    from app.parser.loader import load_dxf
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    msp = doc.modelspace()
    antet = doc.blocks.new("ANTET")
    antet.add_lwpolyline([(0, 0), (30, 0), (30, 10), (0, 10)], close=True)
    antet.add_text("ZEMİN KAT KALIP PLANI", dxfattribs={"height": 3.0}).set_placement((2, 4))
    for i, (x0, name) in enumerate(((0.0, "A"), (200.0, "B"))):
        msp.add_lwpolyline([(x0, 0), (x0 + 150, 0), (x0 + 150, 100), (x0, 100)], close=True, dxfattribs={"layer": "CERCEVE"})
        for k in range(40):
            msp.add_line((x0 + 10 + k, 20), (x0 + 10 + k, 60), dxfattribs={"layer": "KOLON"})
            msp.add_text(f"S{k}", dxfattribs={"height": 1.0}).set_placement((x0 + 10 + k, 62))
        msp.add_blockref("ANTET", (x0 + 110, 5), dxfattribs={"layer": "ANTET"})
        h = msp.add_hatch(dxfattribs={"layer": "brn_hatch_gazbeton"})
        h.paths.add_polyline_path([(x0 + 20, 70), (x0 + 40, 70), (x0 + 40, 80), (x0 + 20, 80)], is_closed=True)
    src = tmp_path / "antet.dxf"; doc.saveas(src)
    scan = scan_sheets(src)
    assert len(scan.sheets) == 2 and all(sh.titled and "KALIP PLANI" in sh.title for sh in scan.sheets)
    da = tmp_path / "a.dxf"
    crop_sheets(src, [(scan.sheets[0].bbox, da)], stream_min_bytes=0)     # 100 MB üstü dosya yolu (akış) zorlanır
    dr = load_dxf(str(da))
    polys = [e for e in dr.entities if e.layer == "brn_hatch_gazbeton" and e.kind == "polygon"]
    assert len(polys) == 1 and abs(abs((polys[0].points[1][0] - polys[0].points[0][0]) * (polys[0].points[2][1] - polys[0].points[1][1])) - 0.02) < 1e-6   # 20 × 10 cm
