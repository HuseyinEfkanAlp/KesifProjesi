"""Mahaller: mimari plandaki duvarlardan mahal sınırı, daire / mahal hiyerarşisi, mahal bazında keşif."""
from __future__ import annotations

import ezdxf
import pytest


def _daire_dxf(path):
    """Daire 1 (12×8 m) içinde SALON + HOL, yanında ORTAK KORİDOR; kameralar ve prizler yerleştirilmiş.

    HOL ile SALON arasındaki duvarda 1 m kapı boşluğu var: mahal ancak boşluk köprülenirse kapanır."""
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 6          # metre
    for n in ("DUVAR", "YAZI", "KSF-ZAY-KAMERA-DOME", "KSF-ELK-PRIZ-TOPRAKLI"):
        doc.layers.add(n)
    doc.blocks.new(name="KAM").add_circle((0, 0), 0.15)
    doc.blocks.new(name="PRZ").add_circle((0, 0), 0.10)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (12, 0), (12, 8), (0, 8)], close=True, dxfattribs={"layer": "DUVAR"})
    msp.add_line((8, 0), (8, 3.5), dxfattribs={"layer": "DUVAR"})   # SALON | HOL ayıran duvar
    msp.add_line((8, 4.5), (8, 8), dxfattribs={"layer": "DUVAR"})   # (arada 1 m kapı boşluğu)
    msp.add_lwpolyline([(13, 0), (20, 0), (20, 8), (13, 8)], close=True, dxfattribs={"layer": "DUVAR"})
    for t, (x, y) in [("DAİRE 1", (3, 7)), ("SALON\\P64.00 m2", (3, 4)),
                      ("HOL\\P32.00 m2", (10, 4)), ("ORTAK KORİDOR\\P56.00 m2", (16, 4))]:
        msp.add_text(t, dxfattribs={"layer": "YAZI", "height": 0.3}).set_placement((x, y))
    for x, y in [(9, 2), (11, 6)]:                                  # HOL: 2 kamera
        msp.add_blockref("KAM", (x, y), dxfattribs={"layer": "KSF-ZAY-KAMERA-DOME"})
    for x, y in [(2, 2), (5, 6), (6, 2)]:                           # SALON: 3 kamera
        msp.add_blockref("KAM", (x, y), dxfattribs={"layer": "KSF-ZAY-KAMERA-DOME"})
    msp.add_blockref("KAM", (16, 2), dxfattribs={"layer": "KSF-ZAY-KAMERA-DOME"})   # koridor: 1
    for x, y in [(1, 1), (2, 7), (6, 7), (7, 1)]:                   # SALON: 4 priz
        msp.add_blockref("PRZ", (x, y), dxfattribs={"layer": "KSF-ELK-PRIZ-TOPRAKLI"})
    msp.add_blockref("PRZ", (9, 7), dxfattribs={"layer": "KSF-ELK-PRIZ-TOPRAKLI"})  # HOL: 1 priz
    doc.saveas(path)
    return path


def test_detect_spaces_hierarchy(tmp_path):
    """Duvarlardan mahal: kapı boşluğu köprülenir, daire içindeki odalar onun çocuğu olur."""
    from app.parser.loader import load_dxf
    from app.parser.spaces import detect_spaces
    d = load_dxf(str(_daire_dxf(tmp_path / "daire.dxf")))
    spaces, warns = detect_spaces(d, ["DUVAR"])
    by = {s.name: s for s in spaces}
    assert set(by) == {"DAİRE 1", "SALON", "HOL", "ORTAK KORİDOR"}
    assert by["DAİRE 1"].kind == "grup" and by["SALON"].kind == "mahal"
    assert by["SALON"].parent == by["DAİRE 1"].index and by["HOL"].parent == by["DAİRE 1"].index
    assert by["ORTAK KORİDOR"].parent is None                  # daire dışında, ayrı mahal
    # çizimden ölçülen alan ile yazıdaki alan birbirini doğruluyor
    assert by["SALON"].area == pytest.approx(64.0, abs=0.5) and by["SALON"].label_area == 64.0
    assert by["HOL"].area == pytest.approx(32.0, abs=0.5)      # kapı boşluğu köprülenmeseydi kapanmazdı
    assert by["DAİRE 1"].area == pytest.approx(96.0, abs=0.5)
    assert any("Mahal okundu" in w for w in warns)


def test_space_breakdown_api(client, tmp_path):
    """Mahal bazında keşif: kamera / priz noktası hangi mahaldeyse o mahale sayılır, daire toplanır."""
    p = _daire_dxf(tmp_path / "daire.dxf")
    pid = client.post("/api/projects", json={"name": "Mahal"}).json()["id"]
    with open(p, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("ZEMİN KAT PLANI.dxf", f, "application/dxf")})
    assert r.status_code == 201, r.text
    out = client.get(f"/api/projects/{pid}/spaces").json()
    by = {s["name"]: s for s in out["spaces"]}
    assert set(by) >= {"DAİRE 1", "SALON", "HOL", "ORTAK KORİDOR"}
    assert by["HOL"]["path"] == "DAİRE 1 / HOL" and by["HOL"]["kind"] == "mahal"

    def qty(space, kind):
        return sum(i["quantity"] for i in space["items"] if i["kind"] == kind)

    assert qty(by["HOL"], "kamera") == 2 and qty(by["SALON"], "kamera") == 3
    assert qty(by["ORTAK KORİDOR"], "kamera") == 1
    assert qty(by["SALON"], "priz") == 4 and qty(by["HOL"], "priz") == 1
    # "evde 5 kamera": daire toplamı çocuklarının toplamıdır
    daire = {i["kind"]: i["quantity"] for i in by["DAİRE 1"]["total_items"]}
    assert daire["kamera"] == 5 and daire["priz"] == 5
    # koridor daireye dahil değil: proje toplamı 6 kamera
    assert sum(qty(s, "kamera") for s in out["spaces"] if s["kind"] == "mahal") == 6


def test_label_clustering_real_world(tmp_path):
    """Gerçek projede mahal etiketi PARÇALI yazılır: ad, kod ve alan ayrı TEXT nesneleridir.

    (Yat Kulübü uygulama projesinden alınan gerçek düzen: "RESTORAN" / "L_Z_01" / ":" / "309.49 m²")"""
    import ezdxf
    from app.parser.loader import load_dxf
    from app.parser.spaces import _labels
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 6
    doc.layers.add("YAZI")
    msp = doc.modelspace()
    for i, (ad, kod, alan, y) in enumerate([("RESTORAN", "L_Z_01", "309.49 m²", 0.0),
                                            ("MERDİVEN", "L_Z_M01", "32.37 m²", 40.0),
                                            ("MERDİVEN", "L_Z_M02", "32.37 m²", 80.0)]):
        msp.add_text(ad, dxfattribs={"layer": "YAZI", "height": 0.24}).set_placement((0, y + 0.64))
        msp.add_text(kod, dxfattribs={"layer": "YAZI", "height": 0.24}).set_placement((-0.89, y))
        msp.add_text(":", dxfattribs={"layer": "YAZI", "height": 0.24}).set_placement((-0.4, y))
        msp.add_text(alan, dxfattribs={"layer": "YAZI", "height": 0.24}).set_placement((0, y))
    p = tmp_path / "etiket.dxf"; doc.saveas(p)
    labs = {l.code: l for l in _labels(load_dxf(str(p))) if l.area > 0}
    assert set(labs) == {"L_Z_01", "L_Z_M01", "L_Z_M02"}
    assert labs["L_Z_01"].name == "RESTORAN" and labs["L_Z_01"].area == 309.49
    # aynı adlı ve aynı alanlı iki merdiven AYRI mahaldir: kodları farklı
    assert labs["L_Z_M01"].name == labs["L_Z_M02"].name == "MERDİVEN"
    assert labs["L_Z_M01"].area == labs["L_Z_M02"].area == 32.37


def test_area_boundary_layer_offset(tmp_path):
    """Mahal alan sınırı ayrı katmanda ve planın AYRI BİR KOPYASINDA çizilmiş olabilir.

    (Yat Kulübü projesindeki gerçek durum: 'alan çizgisi' katmanındaki çokgenler, mahal
    yazılarının 240 m altındaki alan hesabı kopyasında duruyor.) Alan eşleşmesinden kayma
    bulunup çokgenler plana taşınır; alanlar yazıyı tutmazsa çokgen kullanılmaz."""
    import ezdxf
    from app.parser.loader import load_dxf
    from app.parser.spaces import detect_spaces
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 6
    for n in ("YAZI", "alan çizgisi"):
        doc.layers.add(n)
    msp = doc.modelspace()
    DY = 240.0                                   # alan hesabı kopyasının kayması
    odalar = [("RESTORAN", "L_Z_01", 0.0, 0.0, 20.0, 15.0),      # 300 m²
              ("HOL", "L_Z_06", 22.0, 0.0, 10.0, 5.0),           # 50 m²
              ("MUTFAK", "L_Z_12", 34.0, 0.0, 8.0, 5.0)]         # 40 m²
    for ad, kod, x, y, w, h in odalar:
        msp.add_lwpolyline([(x, y - DY), (x + w, y - DY), (x + w, y + h - DY), (x, y + h - DY)],
                           close=True, dxfattribs={"layer": "alan çizgisi"})
        cx, cy = x + w / 2, y + h / 2            # etiket odanın ortasında, ASIL planda
        msp.add_text(ad, dxfattribs={"layer": "YAZI", "height": 0.24}).set_placement((cx, cy + 0.6))
        msp.add_text(kod, dxfattribs={"layer": "YAZI", "height": 0.24}).set_placement((cx - 0.9, cy))
        msp.add_text(f"{w * h:.2f} m²", dxfattribs={"layer": "YAZI", "height": 0.24}).set_placement((cx, cy))
    p = tmp_path / "alan.dxf"; doc.saveas(p)
    spaces, warns = detect_spaces(load_dxf(str(p)), ["alan çizgisi"])
    by = {s.code: s for s in spaces}
    assert set(by) == {"L_Z_01", "L_Z_06", "L_Z_12"}
    assert by["L_Z_01"].name == "RESTORAN" and by["L_Z_01"].area == pytest.approx(300.0, abs=0.5)
    # sınır çizimden ölçüldü ve yazıdaki alanı doğruluyor
    assert all(s.area_source == "drawing" for s in by.values())
    assert any("alan çizgilerinden alındı" in w and "240" in w for w in warns)


def test_mahal_name_filter():
    """Çizim işareti mahal adı sanılmasın: iki harfli kısaltma (DK), ölçü notu, kot."""
    from app.parser.spaces import _is_name
    assert _is_name("MUTFAK") and _is_name("ÇALIŞMA ODASI") and _is_name("WC") and _is_name("HOL")
    assert not _is_name("DK") and not _is_name("TK")            # çizim kısaltması
    assert not _is_name("30X(31 / 16.33)") and not _is_name("27X34")   # ölçü notu
    assert not _is_name("+4.15") and not _is_name("S1") and not _is_name("1/100")


def test_space_derived_items(client, tmp_path):
    """Mahal bazında türetme: şap / kaplama / tavan mahal alanından, sıva-boya ÖLÇÜLEN çevreden.

    HOL 4×8 m: gerçek çevre 24 m. Proje genelindeki "kare mahal" varsayımı (4·√alan) 22,6 m derdi;
    mahal sınırı bilindiğinde varsayıma gerek yok."""
    p = _daire_dxf(tmp_path / "daire.dxf")
    pid = client.post("/api/projects", json={"name": "Türetme", "storey_height": 3.0}).json()["id"]
    with open(p, "rb") as f:
        assert client.post(f"/api/projects/{pid}/drawings",
                           files={"file": ("ZEMİN KAT PLANI.dxf", f, "application/dxf")}).status_code == 201
    by = {s["name"]: s for s in client.get(f"/api/projects/{pid}/spaces").json()["spaces"]}
    hol = by["HOL"]
    assert hol["area_source"] == "drawing" and hol["perimeter"] == pytest.approx(24.0, abs=0.1)
    d = {i["kind"]: i for i in hol["derived"]}
    assert d["sap"]["quantity"] == pytest.approx(32.0 * 0.05)          # 5 cm varsayılan, notu yok
    assert "VARSAYILAN" in d["sap"]["note"]
    assert d["doseme_kaplama"]["quantity"] == pytest.approx(32.0)
    assert d["tavan_siva_boya"]["quantity"] == pytest.approx(32.0)
    # duvar yüzeyi: çevre × (kat yüksekliği − döşeme) — çevre ölçüldü, varsayılmadı
    assert d["siva"]["quantity"] == pytest.approx(24.0 * 2.85, rel=1e-3)
    assert d["boya"]["quantity"] == d["siva"]["quantity"]
    assert "ÖLÇÜLDÜ" in d["siva"]["note"]
    # bağımsız bölüm satırı çocuklarının türetilmiş kalemlerini de toplar
    daire = {i["kind"]: i["quantity"] for i in by["DAİRE 1"]["total_items"]}
    assert daire["tavan_siva_boya"] == pytest.approx(64.0 + 32.0)
