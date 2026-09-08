"""Poz yazısıyla işaretlenen kapı / pencereler (EMP1…), ölçünün görünüş / ölçü yazısından okunması,
aynı dosyanın paftaları arasında birim oylaması, başlıksız küçük kümelerin plan sayılmaması."""
from pathlib import Path

import ezdxf
import pytest

from app.parser.analyzer import analyze_file
from app.parser.detectors.base import DetectParams
from app.parser.detectors.openings import parse_poz
from app.quantity.boq import architectural_items, standard_items
from app.standard.catalog import Catalog


def _plan_with_poz(path: Path, with_schedule: bool = True, with_dims: bool = True) -> Path:
    """cm çizim: 1000x600 dış duvar (YTONG 20, çift çizgi), duvara yakın poz yazıları EMP1 (3 adet), EMP3 (1 adet).
    Sağ altta görünüş: brn_windows katmanında EMP1 için 140x190 dikdörtgen + yanında EMP1 yazısı (duvar yok → sayılmaz).
    EMP3 yazısının yanında düşey '130' 'x' '250' ölçü yazıları. İsteğe bağlı poz listesi: 'Poz: EMP3 / 9 Adet AÇILIR KAPI'."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for name in ("brn_duvar_gazbeton", "brn_windows", "YAZI"):
        doc.layers.add(name)
    msp = doc.modelspace()
    W, H, t = 1000, 600, 20
    outer = [(0, 0), (W, 0), (W, H), (0, H)]
    inner = [(t, t), (W - t, t), (W - t, H - t), (t, H - t)]
    for pts in (outer, inner):
        for i in range(4):
            msp.add_line(pts[i], pts[(i + 1) % 4], dxfattribs={"layer": "brn_duvar_gazbeton"})
    for i in range(30):   # birim sağlaması için yeterli yazı (plan yazıları 20 cm)
        msp.add_text(f"MAHAL {i}", dxfattribs={"layer": "YAZI", "height": 20}).set_placement((100 + i * 25, 300))
    for x in (200, 500, 800):
        msp.add_text("EMP1", dxfattribs={"layer": "YAZI", "height": 20}).set_placement((x, H + 40))
    msp.add_text("EMP3", dxfattribs={"layer": "YAZI", "height": 18}).set_placement((W + 40, 300))
    if with_dims:
        for y, s in ((255, "130"), (285, "x"), (315, "250")):   # döndürülmüş yazı: alt alta, aşağıdan yukarı
            msp.add_text(s, dxfattribs={"layer": "YAZI", "height": 18}).set_placement((W + 70, y))
    # görünüş (plandan uzakta): EMP1 doğrama dikdörtgeni 140 x 190 ve etiketi
    gx, gy = 2000, -2000
    msp.add_lwpolyline([(gx, gy), (gx + 140, gy), (gx + 140, gy + 190), (gx, gy + 190)], close=True,
                       dxfattribs={"layer": "brn_windows"})
    msp.add_text("EMP1", dxfattribs={"layer": "YAZI", "height": 20}).set_placement((gx + 40, gy - 40))
    if with_schedule:
        msp.add_mtext("Poz: EMP3\\P9 Adet AÇILIR KAPI", dxfattribs={"layer": "YAZI", "char_height": 20}).set_location((gx, gy - 300))
        msp.add_mtext("Poz: EMP1\\PAdet: 82", dxfattribs={"layer": "YAZI", "char_height": 20}).set_location((gx, gy - 400))
    doc.saveas(path)
    return path


@pytest.mark.parametrize("text,poz,prefix,note", [
    ("EMP1", "EMP1", "EMP", ""),
    ("EMP3 - KANATLI", "EMP3", "EMP", "KANATLI"),
    ("EMP4a", "EMP4A", "EMP", ""),
    ("P 12", "P12", "P", ""),
    ("+4.15", None, None, None),
    ("LOBİ 45 m2", None, None, None),
])
def test_parse_poz(text, poz, prefix, note):
    r = parse_poz(text)
    if poz is None:
        assert r is None
    else:
        assert r == (poz, prefix, note)


def test_poz_openings_from_labels_and_sizes(tmp_path):
    res = analyze_file(str(_plan_with_poz(tmp_path / "plan.dxf")), discipline="architectural", catalog=Catalog())
    openings = [e for e in res.elements if e.etype in ("door", "window")]
    by_poz = {}
    for e in openings:
        by_poz.setdefault(e.name, []).append(e)
    # plandaki 3 EMP1 + 1 EMP3; görünüşteki EMP1 yazısının yanında duvar yok -> sayılmaz
    assert len(by_poz["EMP1"]) == 3 and len(by_poz["EMP3"]) == 1
    w = by_poz["EMP1"][0]
    assert w.etype == "window" and w.source == "POZ_LABEL"
    assert w.b == pytest.approx(1.40, abs=0.01) and w.h == pytest.approx(1.90, abs=0.01)   # görünüşteki dikdörtgen
    d = by_poz["EMP3"][0]
    assert d.etype == "door"                                                   # poz listesi: AÇILIR KAPI
    assert d.b == pytest.approx(1.30, abs=0.01) and d.h == pytest.approx(2.50, abs=0.01)  # düşey '130 x 250'
    assert res.poz["sizes"]["EMP1"] == [1.4, 1.9] and res.poz["kinds"]["EMP3"] == "door"
    assert "EMP" in res.poz["prefixes"]
    assert any("Poz yazılarından 4 kapı / pencere" in w for w in res.warnings)
    assert res.unit_verdict == "cm"


def test_poz_openings_need_known_prefix(tmp_path):
    """Poz listesi yoksa ve önek proje bilgisinde de yoksa 'EMP1' yazıları sayılmaz; proje bilgisiyle sayılır."""
    path = str(_plan_with_poz(tmp_path / "plan2.dxf", with_schedule=False))
    res = analyze_file(path, discipline="architectural", catalog=Catalog())
    assert not [e for e in res.elements if e.etype in ("door", "window")]
    params = DetectParams(poz_prefixes=("EMP",), poz_kinds={"EMP3": "door"}, poz_sizes={"EMP1": [1.2, 1.5]})
    res = analyze_file(path, params=params, discipline="architectural", catalog=Catalog())
    openings = [e for e in res.elements if e.etype in ("door", "window")]
    assert len(openings) == 4
    emp1 = [e for e in openings if e.name == "EMP1"][0]
    assert emp1.b == pytest.approx(1.4, abs=0.01)     # çizimdeki görünüş projedeki değerden önce gelir


def test_boq_schedule_poz_not_double_counted():
    """Plandan sayılan pozlu boşluk duvardan düşülür; adet ve cam poz listesinden (dograma) gelir."""
    walls = [{"etype": "wall", "b": 0.2, "length": 10.0, "subtype": "ytong", "count": 1}]
    win = {"etype": "window", "b": 1.4, "h": 1.9, "count": 1, "name": "EMP1", "meta": {"poz": "EMP1"}}
    drawings = [{"label": "Z", "storey_count": 1, "storey_height": 3.0, "slab_thickness": 0.0, "elements": walls + [win]}]
    items = {i.key: i for i in architectural_items(drawings, {}, schedule_poz={"EMP1"})}
    assert "pencere:emp1_140x190" not in items and not any(k.startswith("cam:") for k in items)
    assert items["duvar:ytong:20"].quantity == pytest.approx(10 * 3.0 - 1.4 * 1.9)
    items = {i.key: i for i in architectural_items(drawings, {})}
    assert "pencere:emp1_140x190" in items and items["cam:140x190"].quantity == pytest.approx(1.4 * 1.9)
    # poz listesi kalemi: ölçü biliniyorsa cam m² (kapı hariç)
    cat = Catalog()
    dog = [{"etype": "dograma", "subtype": "EMP1", "name": "EMP1", "layer": "(poz listesi)", "count": 82, "length": 0, "area": 0,
            "b": 1.4, "h": 1.9, "meta": {"ksf_code": "DOGRAMA", "measure": "count", "spec": "EMP1", "opening_kind": "window"}},
           {"etype": "dograma", "subtype": "EMP3", "name": "EMP3", "layer": "(poz listesi)", "count": 9, "length": 0, "area": 0,
            "b": 1.3, "h": 2.5, "meta": {"ksf_code": "DOGRAMA", "measure": "count", "spec": "EMP3", "opening_kind": "door"}}]
    std = {i.key: i for i in standard_items([{"label": "D", "storey_count": 1, "elements": dog}], {}, cat)}
    assert std["dograma:emp1"].quantity == 82 and std["dograma:emp3"].quantity == 9
    assert std["cam:140x190"].quantity == pytest.approx(82 * 1.4 * 1.9)


def test_geometry_poor_plan_warns(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("brn_duvar_gazbeton")
    msp = doc.modelspace()
    for i in range(25):
        msp.add_text(f"MAHAL {i}\\P{100 + i}.5 m2", dxfattribs={"height": 250}).set_placement((i * 5000, 0))
    msp.add_text("duvar notu", dxfattribs={"layer": "brn_duvar_gazbeton", "height": 250}).set_placement((0, 3000))
    p = tmp_path / "yazi.dxf"
    doc.saveas(p)
    res = analyze_file(str(p), discipline="architectural", catalog=Catalog())
    assert res.warnings and res.warnings[0].startswith("Bu paftada plan geometrisi yok")
    assert not res.elements


def test_fragment_sheets_not_preselected():
    from app.api.drawings import _sheet_out
    from app.parser.sheets import Sheet
    frag = Sheet(0, "Pafta 1 (başlıksız, 50 nesne)", (0, 0, 10, 10), 50, 0, titled=False, layers={"HB-AYDINLATMA": 30})
    out = _sheet_out(frag)
    assert out["fragment"] and not out["analyze"] and out["plan_type"] == "" and out["discipline"] == ""
    big = Sheet(1, "Pafta 2 (başlıksız, 900 nesne)", (0, 0, 10, 10), 900, 0, titled=False, layers={"KOLON": 400, "KIRIS": 300})
    out = _sheet_out(big)
    assert not out["fragment"] and out["analyze"] and out["discipline"] == "structural"
    titled = Sheet(2, "ZEMİN KAT KALIP PLANI", (0, 0, 10, 10), 30, 1, titled=True, layers={"KOLON": 20})
    out = _sheet_out(titled)
    assert not out["fragment"] and out["plan_type"] == "sta_kat_kalip"


def test_majority_unit_vote():
    from app.api.drawings import majority_unit
    assert majority_unit(["cm", "cm", "mm", None, "cm"]) == ("cm", 3)
    assert majority_unit(["cm", "mm"]) is None          # çoğunluk yok
    assert majority_unit(["cm", None, None]) is None    # tek pafta yetmez
    assert majority_unit([None, None]) is None


def test_drawing_summary_status_and_note():
    from app.api.drawings import drawing_summary
    from app.models import Drawing, Element
    d = Drawing(project_id=1, filename="a.dxf", stored_path="x", plan_type="mim_kat_plani",
                warnings=["Çizim birimi 'mm' yazılı ama yazı yükseklikleri 'cm' ile uyuşuyor.", "Poz yazılarından 46 kapı / pencere sayıldı: EMP1 35"],
                rooms=[{"name": "LOBİ", "area_m2": 45.0}])
    els = [Element(drawing_id=1, etype="wall", points=[]) for _ in range(3)] + [Element(drawing_id=1, etype="window", points=[])]
    s = drawing_summary(d, els)
    assert s["status"] == "ok" and s["found"] == "3 duvar · 1 pencere · 1 mahal alanı"
    assert s["note"].startswith("Poz yazılarından")
    d2 = Drawing(project_id=1, filename="b.dxf", stored_path="x", plan_type="mim_kat_plani",
                 warnings=["Bu paftada plan geometrisi yok (113 yazı, 0 çizgi / çokgen): …"])
    assert drawing_summary(d2, [])["status"] == "problem"
    d3 = Drawing(project_id=1, filename="c.dxf", stored_path="x", plan_type="", warnings=[])
    assert drawing_summary(d3, [])["status"] == "untyped" and drawing_summary(d3, [])["note"] == ""


def test_drawing_summary_ksf_quantities():
    """KSF kalemleri özet satırında ölçü birimiyle yazılır: duvar m² (adet değil), kiriş m, kapı adet."""
    from app.api.drawings import drawing_summary
    from app.models import Drawing, Element
    from app.standard.catalog import Catalog
    d = Drawing(project_id=1, filename="a.dxf", stored_path="x", plan_type="mim_kat_plani", warnings=[])
    els = ([Element(drawing_id=1, etype="duvar_tugla", layer="KSF-MIM-DUVAR_TUGLA-13.5x300", points=[], length=4.0, area=12.0) for _ in range(3)]
           + [Element(drawing_id=1, etype="hava_kanal", layer="KSF-HAV-HAVA_KANAL-600x400", points=[], length=5.5)]
           + [Element(drawing_id=1, etype="kapi", layer="KSF-MIM-KAPI-K1_90x210", points=[], count=1) for _ in range(2)]
           + [Element(drawing_id=1, etype="wall", points=[], length=10.0)])
    s = drawing_summary(d, els, Catalog())
    assert s["found"] == "36,0 m² tuğla duvar · 2 kapı · 5,5 m havalandırma kanalı (dikdörtgen) · 1 duvar (10,0 m)"
    assert "adet" not in s["found"]
    assert drawing_summary(d, els)["found"].startswith("3 duvar tugla")     # katalogsuz: eski davranış (adet)
