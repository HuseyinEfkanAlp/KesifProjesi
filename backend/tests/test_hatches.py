"""Taramalar ve lejant (parser/hatches.py): malzemenin çizimdeki ikinci dili.

Gerçek projede (Yat Kulübü) 445 tarama vardı ama pafta kırpılırken düz çokgene çevriliyor ve desen
adı kayboluyordu; bu testler hem okumayı hem desenin kırpmadan sağ çıkmasını sınar.
"""
from __future__ import annotations

import ezdxf
import pytest

from app.parser import sheets
from app.parser.analyzer import analyze_file
from app.parser.hatches import HatchReader, material_of_text, read_legend
from app.parser.loader import load_dxf
from app.parser.sheets import crop_sheets


def _hatch(msp, pts, pattern, layer="A-TARAMA"):
    h = msp.add_hatch(dxfattribs={"layer": layer})
    if pattern == "SOLID":
        h.set_solid_fill()
    else:
        h.set_pattern_fill(pattern, scale=1.0)
    h.paths.add_polyline_path(pts, is_closed=True)
    return h


def _plan(path, wall_pattern="AR-B816", legend=None, wall_layer="A-DUVAR"):
    """cm çizimi: 20 cm kalınlığında, 6 m boyunda malzemesi yazmayan bir duvar (çift çizgi) + içini
    dolduran tarama. legend: [(desen, yazı)] — sol kenarları hizalı bir lejant sütunu."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    msp = doc.modelspace()
    for name in (wall_layer, "A-TARAMA", "YAZI"):
        doc.layers.add(name)
    msp.add_line((0, 0), (600, 0), dxfattribs={"layer": wall_layer})
    msp.add_line((0, 20), (600, 20), dxfattribs={"layer": wall_layer})
    if wall_pattern:
        _hatch(msp, [(0, 0), (600, 0), (600, 20), (0, 20)], wall_pattern)
    for i, (pat, text) in enumerate(legend or []):
        y = 1000 - i * 60
        _hatch(msp, [(2000, y), (2040, y), (2040, y + 30), (2000, y + 30)], pat, layer="LEJANT")
        msp.add_text(text, dxfattribs={"layer": "YAZI", "height": 10}).set_placement((2060, y + 10))
    # birim tespiti için birkaç yazı
    for i in range(6):
        msp.add_text("ODA", dxfattribs={"layer": "YAZI", "height": 12}).set_placement((100 + i * 80, 300))
    doc.saveas(path)
    return path


def _walls(path):
    r = analyze_file(str(path), discipline="architectural", unit_override="cm")
    return r, [e for e in r.elements if e.etype == "wall"]


# ------------------------------------------------------------------ yükleyici

def test_yukleyici_desen_adini_tasir(tmp_path):
    p = _plan(tmp_path / "a.dxf")
    d = load_dxf(str(p), unit_override="cm")
    assert {e.pattern for e in d.entities if e.pattern} == {"AR-B816"}


def test_dolu_tarama_solid_olarak_okunur(tmp_path):
    p = _plan(tmp_path / "a.dxf", wall_pattern="SOLID")
    d = load_dxf(str(p), unit_override="cm")
    assert {e.pattern for e in d.entities if e.pattern} == {"SOLID"}


# ------------------------------------------------------------------ duvar malzemesi

def test_desen_adindan_duvar_malzemesi(tmp_path):
    r, walls = _walls(_plan(tmp_path / "a.dxf", "AR-B816"))
    assert walls and all(w.subtype == "tugla" for w in walls)
    w = walls[0]
    assert w.meta["material_source"] == "tarama-desen" and "AR-B816" in w.meta["material_note"]
    assert not any("malzemesi bilinmiyor" in x for x in w.warnings)
    assert any("taramadan okundu" in x for x in r.warnings)


def test_anlami_belirsiz_desen_malzeme_uydurmaz(tmp_path):
    """DOTS / ANSI31 gibi çizerine göre anlam değiştiren desen: 'bilmiyorum' yanlış malzemeden iyidir."""
    _, walls = _walls(_plan(tmp_path / "a.dxf", "DOTS"))
    assert walls and all(w.subtype is None for w in walls)
    assert any("malzemesi bilinmiyor" in x for x in walls[0].warnings)


def test_katman_adi_taramayi_ezer(tmp_path):
    """Duvarın katmanı malzemeyi söylüyorsa tarama ona dokunmaz."""
    _, walls = _walls(_plan(tmp_path / "a.dxf", "AR-CONC", wall_layer="A-DUVAR-YTONG"))
    assert walls and all(w.subtype == "ytong" for w in walls)


def test_lejant_desenin_anlamini_belirler(tmp_path):
    """Mimar ANSI31'i gazbeton için kullandıysa bu projede ANSI31 gazbetondur."""
    p = _plan(tmp_path / "a.dxf", "ANSI31", legend=[("ANSI31", "20 cm GAZBETON DUVAR"), ("ANSI37", "BETONARME PERDE")])
    r, walls = _walls(p)
    assert walls and all(w.subtype == "ytong" for w in walls)
    assert walls[0].meta["material_source"] == "tarama-lejant"
    assert "GAZBETON" in walls[0].meta["material_note"]
    leg = {x["pattern"]: x["material"] for x in r.hatches["legend"]}
    assert leg == {"ANSI31": "ytong", "ANSI37": "beton"}


def test_lejant_standart_anlami_ezer(tmp_path):
    p = _plan(tmp_path / "a.dxf", "AR-CONC", legend=[("AR-CONC", "TUĞLA DUVAR"), ("ANSI37", "BETONARME")])
    _, walls = _walls(p)
    assert all(w.subtype == "tugla" for w in walls)


def test_celisen_lejant_kullanilmaz(tmp_path):
    p = _plan(tmp_path / "a.dxf", "ANSI31", legend=[("ANSI31", "GAZBETON DUVAR"), ("ANSI31", "TUĞLA DUVAR")])
    r, walls = _walls(p)
    assert all(w.subtype is None for w in walls)
    assert any("birden çok malzemeyle" in x for x in r.warnings)


def test_tek_basina_kucuk_tarama_lejant_sayilmaz(tmp_path):
    """Sütun ya da başlık yoksa 'küçük tarama + yanında yazı' lejant değildir (mahal etiketi olabilir)."""
    p = _plan(tmp_path / "a.dxf", "ANSI31", legend=[("ANSI31", "GAZBETON")])
    rows, _ = read_legend(load_dxf(str(p), unit_override="cm"))
    assert rows == []


def test_duvar_olmayan_malzeme_duvara_verilmez(tmp_path):
    """EARTH (toprak) bir duvarı örtüyorsa çizim başka bir şey anlatıyordur: duvar malzemesi olmaz."""
    _, walls = _walls(_plan(tmp_path / "a.dxf", "EARTH"))
    assert all(w.subtype is None for w in walls)


def test_tarama_ozeti(tmp_path):
    r, _ = _walls(_plan(tmp_path / "a.dxf", "AR-B816", legend=[("ANSI31", "GAZBETON"), ("GRAVEL", "BLOKAJ")]))
    h = r.hatches
    assert h["total"] == 3
    by = {x["pattern"]: x for x in h["patterns"]}
    assert by["AR-B816"]["material"] == "tugla" and by["AR-B816"]["source"] == "desen"
    assert by["AR-B816"]["area_m2"] == pytest.approx(1.2)          # 6 m × 0,20 m
    assert by["ANSI31"]["source"] == "lejant"
    assert h["recognized"] == 3


def test_yazidan_malzeme():
    assert material_of_text("19 cm yatay delikli TUĞLA") == "tugla"
    assert material_of_text("5 cm TAŞYÜNÜ") == "yalitim"
    assert material_of_text("BLOKAJ") == "cakil"
    assert material_of_text("MAHAL 12") is None


# ------------------------------------------------------------------ kırpma desenle birlikte

@pytest.mark.parametrize("akis", [False, True])
def test_kirpma_deseni_korur(tmp_path, monkeypatch, akis):
    """Pafta kırpılırken tarama düz çokgene çevrilmemeli: desen adı malzemedir."""
    if akis:
        monkeypatch.setattr(sheets, "STREAM_BLOCK_MIN_BYTES", 0)    # büyük dosya yolu (ezdxf'siz akış)
    src = _plan(tmp_path / "kaynak.dxf", "AR-B816")
    out = tmp_path / "pafta.dxf"
    crop_sheets(src, [((-50.0, -50.0, 700.0, 400.0), out)])
    hs = [e for e in ezdxf.readfile(str(out)).modelspace() if e.dxftype() == "HATCH"]
    assert [h.dxf.pattern_name for h in hs] == ["AR-B816"]
    d = load_dxf(str(out), unit_override="cm")
    assert HatchReader(d).summary()["patterns"][0]["material"] == "tugla"
