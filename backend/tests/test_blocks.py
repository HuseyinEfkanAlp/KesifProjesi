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

    Blok listesi kullanıcıdan sorulmaz, çizimden çıkar (services.project_blocks): burada statik ruhsat
    dosyasında C3'ün de paftası olduğu için C3 bilinir, eksik olan yalnız mimarisidir."""
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


def test_site_plan_blocks_are_a_reminder_not_a_missing_plan():
    """Vaziyet planı sitenin tamamını gösterir; keşif birkaç bloğu kapsayabilir — eksik sayılmaz, hatırlatılır."""
    ds = [_d(1, "mim_kat_plani", "C1"), _d(2, "mim_kat_plani", "C2")]
    r = plan_check(ds, None, ["C1", "C2"], site_missing=["C3", "N", "T"])
    assert r["site_missing"] == ["C3", "N", "T"]
    assert any("Vaziyet planında" in w and "C3" in w for w in r["warnings"])
    mim = next(t for g in r["groups"] for t in g["types"] if t["code"] == "mim_kat_plani")
    assert mim["status"] == "present" and mim["missing_blocks"] == []   # kapsam dışı blok eksik saymaz


def test_project_blocks_come_from_the_drawings():
    """Blok listesi çizimden çıkar: paftaların kendi bloğu kapsamı, vaziyet planı siteyi verir."""
    from app.models import Drawing, Project
    from app.services import project_blocks
    p = Project(name="t")
    ds = [Drawing(project_id=1, filename="statik.dxf", stored_path="", block="C1",
                  blocks_seen={"C1": 2, "C2": 1, "C3": 1, "C4": 1, "N": 3}),   # vaziyet paftası siteyi görüyor
          Drawing(project_id=1, filename="C2 mimari.dxf", stored_path="", block="C2"),
          Drawing(project_id=1, filename="zemin kalip.dxf", stored_path="", block="")]   # ortak
    r = project_blocks(p, ds)
    assert r["blocks"] == ["C1", "C2"] and r["source"] == "cizim"
    assert r["missing"] == ["C3", "C4", "N"]        # vaziyette var, planı yok -> hatırlatma
    # kullanıcı düzeltirse onun listesi geçerli
    p.blocks = ["C1", "C2", "C3", "C4"]
    assert project_blocks(p, ds)["blocks"] == ["C1", "C2", "C3", "C4"]


def test_single_block_building_has_no_blocks():
    """Tek bloklu yapıda hiçbir yerde "BLOK" geçmez: liste boş, program tek yapı gibi çalışır."""
    from app.models import Drawing, Project
    from app.services import project_blocks
    ds = [Drawing(project_id=1, filename="zemin kalip.dxf", stored_path="", block=""),
          Drawing(project_id=1, filename="mimari kat.dxf", stored_path="", block="")]
    r = project_blocks(Project(name="t"), ds)
    assert r["blocks"] == [] and r["missing"] == []
    assert plan_check([_d(1, "sta_kat_kalip"), _d(2, "mim_kat_plani")], None, r["blocks"])["partial"] == 0


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


def test_compound_block_covers_its_parts():
    """Tek çizim iki bloğu birlikte veriyorsa ("A4-A5 BLOK") vaziyetteki A4 / A5 eksik sayılmaz."""
    from app.models import Drawing, Project
    from app.parser.blocks import covered_by
    from app.services import project_blocks
    assert covered_by(["A4-A5"]) == {"A4-A5", "A4", "A5"}
    ds = [Drawing(project_id=1, filename="A4-A5 BLOK KALIP.dxf", stored_path="", block="A4-A5",
                  blocks_seen={"A4": 1, "A5": 1, "A4-A5": 1, "B1": 1, "C3": 1})]
    r = project_blocks(Project(name="t"), ds)
    assert r["blocks"] == ["A4-A5"] and r["missing"] == ["B1", "C3"]


def test_site_reminder_is_shortened_when_long():
    """Vaziyet planı bütün siteyi gösterir: uyarı ilk birkaç adı yazar, sayıyı verir."""
    many = [f"B{i}" for i in range(1, 13)]
    w = plan_check([_d(1, "mim_kat_plani", "C1")], None, ["C1"], site_missing=many)["warnings"]
    line = next(x for x in w if "Vaziyet" in x)
    assert "12 blok daha" in line and "+4" in line


def test_zincir_liste_ve_aralik_blok_adlari():
    """A blokları: statik tek dosya "VM-A1-A2-A3 BLOK STATİK PROJE" — yalnız "A2-A3" okunuyor, A1 düşüyordu."""
    from app.parser.blocks import detect_block, parts_of
    assert detect_block("VM-A1-A2-A3 BLOK STATİK PROJE 18.02.2023") == "A1-A2-A3"      # firma öneki atılır
    assert parts_of("A1-A2-A3") >= {"A1", "A2", "A3"}
    assert detect_block("A1, A2, A3 BLOK BODRUM KAT KALIP PLANI") == "A1-A2-A3"
    assert parts_of("A1-A3") >= {"A1", "A2", "A3"}                                   # aralık
    assert parts_of("A4-A5") == {"A4-A5", "A4", "A5"}
    assert detect_block("C-1 BLOĞU") == "C1" and detect_block("TEMEL BLOKAJ") == ""
