"""Yapı bloğu: blok adının dosya adından tanınması, blok bilinçli plan seti kontrolü, çatı ve oturum.

Senaryo (yaygın tipoloji, kullanıcının projesi): bodrum ve zemin katlar birleşik (ortada koridor, blok = ""),
üstünde C1 / C2 / C3 / C4 blokları; statik tek ruhsat dosyası, mimari blok blok ayrı dosyalar.
"""
import pytest

from app.parser.blocks import detect_block, detect_with_known, normalize
from app.planset import plan_check


def test_block_name_from_filename():
    assert detect_block("1-KIYI İSTANBUL A4-A5 BLOK TEMEL KALIP ve DONATI PLANLARI.dwg") == "A4-A5"
    assert detect_block("C1 BLOK MİMARİ KAT PLANI.dwg") == "C1"
    assert detect_block("BLOK C2 mimari.dxf") == "C2"
    assert detect_block("C-3 BLOĞU TAVAN PLANI.dwg") == "C3"       # harf-sayı tiresi atılır
    assert detect_block("BLOK: C4 kuvvet.dwg") == "C4"
    # ortak / bloksuz planlar
    assert detect_block("ZEMİN KAT KALIP PLANI.dwg") == ""
    assert detect_block("VAZİYET PLANI.dwg") == ""
    assert detect_block("BLOKAJ DETAYI.dwg") == ""                  # "BLOKAJ" blok adı değildir
    assert normalize("a4 - a5") == "A4-A5" and normalize("c-1") == "C1"


def test_block_name_without_the_word_blok():
    """Dosya adında "BLOK" geçmeyebilir; projede zaten bilinen adlar eşleştirilir."""
    known = ["C1", "C2", "C3", "C4"]
    assert detect_with_known("C2 MİMARİ KAT PLANI.dwg", known) == "C2"
    assert detect_with_known("C-3 tavan.dwg", known) == "C3"
    assert detect_with_known("ZEMİN KAT PLANI.dwg", known) == ""
    assert detect_with_known("C10 PLANI.dwg", known) == ""          # C1 diye okunmaz


def _d(i, plan_type, block="", label=""):
    return {"id": i, "plan_type": plan_type, "block": block, "label": label or f"çizim {i}", "discipline": "architectural"}


def test_plan_check_warns_for_the_block_whose_drawing_is_missing():
    """Mimari blok blok geliyorsa eksik bir bloğun dosyası sessizce geçmemeli.

    C3'ün hiç dosyası yüklenmediyse çizimlere bakarak C3'ün varlığı anlaşılamaz: proje blokları
    (Project.blocks) tanımlı olmalıdır."""
    BLOKLAR = ["C1", "C2", "C3", "C4"]
    ds = [_d(1, "sta_kat_kalip"),                        # ortak: statik ruhsat dosyası
          _d(2, "mim_kat_plani", "C1"), _d(3, "mim_kat_plani", "C2"), _d(4, "mim_kat_plani", "C4")]   # C3 unutuldu
    r = plan_check(ds, None, BLOKLAR)
    mim = next(t for g in r["groups"] for t in g["types"] if t["code"] == "mim_kat_plani")
    assert mim["status"] == "partial" and mim["missing_blocks"] == ["C3"]
    assert any("C3" in w for w in r["warnings"])
    assert r["blocks"] == BLOKLAR and not r["complete"]

    # C3 gelince tamamlanır
    ok = plan_check(ds + [_d(5, "mim_kat_plani", "C3")], None, BLOKLAR)
    assert next(t for g in ok["groups"] for t in g["types"] if t["code"] == "mim_kat_plani")["status"] == "present"
    assert not any("C3" in w for w in ok["warnings"])


def test_block_seen_in_drawings_but_not_declared_is_reported():
    """Çizimden tanınan ama proje bloklarına eklenmemiş ad ayrıca bildirilir (yazım farkı / yeni blok)."""
    ds = [_d(1, "mim_kat_plani", "C1"), _d(2, "mim_kat_plani", "C5")]
    r = plan_check(ds, None, ["C1", "C2"])
    assert r["undeclared_blocks"] == ["C5"] and set(r["blocks"]) == {"C1", "C2", "C5"}


def test_plan_check_does_not_demand_common_plans_per_block():
    """Yalnız ortak çizilen tipler (temel, vaziyet) blok başına aranmaz — bodrum ve zemin birleşiktir."""
    ds = [_d(1, "sta_temel_kalip"), _d(2, "mim_kat_plani", "C1"), _d(3, "mim_kat_plani", "C2")]
    r = plan_check(ds, None)
    temel = next(t for g in r["groups"] for t in g["types"] if t["code"] == "sta_temel_kalip")
    assert temel["status"] == "present" and temel["missing_blocks"] == []


def test_plan_check_without_blocks_behaves_as_before():
    ds = [_d(1, "sta_kat_kalip"), _d(2, "mim_kat_plani")]
    r = plan_check(ds, None)
    assert r["blocks"] == [] and r["partial"] == 0
    assert all(t["missing_blocks"] == [] for g in r["groups"] for t in g["types"])
