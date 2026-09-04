import pytest

from app.parser.text_parser import parse_label


@pytest.mark.parametrize("text,name,etype,b,h", [
    ("S1 30/60", "S1", "column", 0.30, 0.60),
    ("S101 40x40", "S101", "column", 0.40, 0.40),
    ("K101 25/50", "K101", "beam", 0.25, 0.50),
    ("K-12 30X70", "K12", "beam", 0.30, 0.70),
    ("P1 20/250", "P1", "shear_wall", 0.20, 2.50),
    ("TK1 60/80", "TK1", "foundation", 0.60, 0.80),
])
def test_name_and_dims(text, name, etype, b, h):
    lab = parse_label(text)
    assert lab.name == name
    assert lab.type_hint == etype
    assert lab.b == pytest.approx(b)
    assert lab.h == pytest.approx(h)


def test_slab_thickness():
    lab = parse_label("D101 h=15")
    assert lab.name == "D101"
    assert lab.type_hint == "slab"
    assert lab.thickness == pytest.approx(0.15)
    assert not lab.has_dims


def test_thickness_without_name():
    lab = parse_label("RADYE h=60")
    assert lab.name is None
    assert lab.thickness == pytest.approx(0.60)


def test_dims_only():
    lab = parse_label("30/60")
    assert lab.name is None
    assert lab.b == pytest.approx(0.30) and lab.h == pytest.approx(0.60)


def test_rebar_not_confused_with_dims():
    lab = parse_label("Ø8/15")
    assert not lab.has_dims
    assert lab.rebar == [{"dia_mm": 8, "spacing_cm": 15}]
    lab = parse_label("8%%c16")
    assert lab.rebar == [{"count": 8, "dia_mm": 16}]
    assert not lab.has_dims


def test_mtext_codes_stripped():
    lab = parse_label(r"\A1;S1 30/60")
    assert lab.name == "S1"


@pytest.mark.parametrize("text,name,etype,b,h", [
    ("K1001 (100/45)", "K1001", "beam", 1.00, 0.45),
    ("S1001", "S1001", "column", None, None),
    ("(100/100)", None, None, 1.00, 1.00),
    ("P1450", "P1450", "shear_wall", None, None),
    ("D1000", "D1000", "slab", None, None),
])
def test_real_drawing_labels(text, name, etype, b, h):
    lab = parse_label(text)
    assert lab.name == name and lab.type_hint == etype
    assert lab.b == (pytest.approx(b) if b else None) and lab.h == (pytest.approx(h) if h else None)


def test_thickness_variants_and_elevation():
    assert parse_label("d=12").thickness == pytest.approx(0.12)
    assert parse_label("D:20cm").thickness == pytest.approx(0.20)
    assert parse_label("D:20cm").name is None
    assert not parse_label("+4.00").is_meaningful
    assert not parse_label("3cm Ters Sehim").is_meaningful


@pytest.mark.parametrize("text,name,etype,b,h,thick", [
    ("SB033", "SB033", "column", None, None, None),          # bodrum kolonu (kat kodu B)
    ("SZ094", "SZ094", "column", None, None, None),          # zemin (Z)
    ("S1094", "S1094", "column", None, None, None),          # 1. kat (rakam sayı kısmında kalır)
    ("KZ0063 (100/50)", "KZ0063", "beam", 1.00, 0.50, None),
    ("KB0021 (60/50)", "KB0021", "beam", 0.60, 0.50, None),
    ("K10155", "K10155", "beam", None, None, None),
    ("PB0922 (30/535)", "PB0922", "shear_wall", 0.30, 5.35, None),
    ("PZ0859", "PZ0859", "shear_wall", None, None, None),
    ("DB041", "DB041", "slab", None, None, None),
    ("DDB024", "DDB024", "slab", None, None, None),          # düşük döşeme
    ("DZ002", "DZ002", "slab", None, None, None),
    ("RD1", "RD1", "foundation", None, None, None),          # radye bölgesi
    ("15cm", None, None, None, None, 0.15),                  # çıplak kalınlık yazısı
    ("70cm", None, None, None, None, 0.70),
    ("d=15cm", None, None, None, None, 0.15),
])
def test_floor_coded_labels(text, name, etype, b, h, thick):
    lab = parse_label(text)
    assert lab.name == name and lab.type_hint == etype
    assert lab.b == (pytest.approx(b) if b else None) and lab.h == (pytest.approx(h) if h else None)
    assert lab.thickness == (pytest.approx(thick) if thick else None)


def test_unknown_prefix_has_no_type():
    lab = parse_label("XB12")
    assert lab.name is None and lab.type_hint is None
    assert parse_label("RD1").merged_with(parse_label("70cm")).thickness == pytest.approx(0.70)


def test_merge_name_and_dims():
    lab = parse_label("S1001").merged_with(parse_label("(100/100)"))
    assert lab.name == "S1001" and lab.type_hint == "column" and lab.b == pytest.approx(1.0)
    lab2 = parse_label("D1000").merged_with(parse_label("d=17"))
    assert lab2.name == "D1000" and lab2.thickness == pytest.approx(0.17)


def test_plain_word_not_meaningful():
    assert not parse_label("A").is_meaningful
    assert not parse_label("MUTFAK").is_meaningful
