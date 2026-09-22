"""Kat sayısı kullanıcıya sorulmaz, çizimden türetilir (app/derive.py).

Bu, metrajı mertebe olarak kaydıran varsayımdır: tip kat planı 5 katı temsil ediyorsa beton, kalıp,
demir ve duvar beş katıdır. Testler kanıt zincirinin her basamağını ve çıkarılamadığında **susmadığını**
sabitler.
"""
from app.derive import storey_counts
from app.models import Drawing, Project
from app.parser.levels import is_typical_floor, storey_count_in_label, storey_span


def cizim(i, label, kot=None, levels=None, discipline="architectural", manual=None):
    d = Drawing(project_id=1, filename=f"{i}.dxf", stored_path="", label=label,
                discipline=discipline, kot=kot, levels=levels or [])
    d.id = i
    d.storey_manual = manual
    return d


PROJE = Project(name="t")


# ------------------------------------------------------------------ pafta başlığı okuması

def test_pafta_basligindaki_kat_araligi_okunur():
    assert storey_span("1.-5. NORMAL KAT PLANI") == (1, 5)
    assert storey_span("2-7. KAT PLANI") == (2, 7)
    assert storey_span("1.–4. KAT") == (1, 4)          # en tire
    assert storey_span("3. KAT PLANI") is None          # tek kat aralık değildir
    assert storey_span("A-101 1/5 ÖLÇEK") is None       # ölçek kat aralığı değildir


def test_baslikta_acikca_yazan_kat_adedi_okunur():
    assert storey_count_in_label("TİP KAT (5 KAT)") == 5
    assert storey_count_in_label("5 KATLI BİNA") == 5
    assert storey_count_in_label("ZEMİN KAT PLANI") is None


def test_tip_kat_plani_taninir():
    assert is_typical_floor("1.-5. NORMAL KAT PLANI")
    assert is_typical_floor("Tip kat planı")
    assert not is_typical_floor("ZEMİN KAT PLANI")


# ------------------------------------------------------------------ kanıt zinciri

def test_baslikta_aralik_varsa_kat_sayisi_ondan_gelir():
    d = cizim(1, "1.-5. NORMAL KAT PLANI")
    sc = storey_counts(PROJE, [d])
    assert sc["per_drawing"][1]["value"] == 5
    assert sc["per_drawing"][1]["kind"] == "drawing"
    assert "1.–5. kat" in sc["per_drawing"][1]["source"]


def test_tip_kat_plani_sahipsiz_kotlari_ustlenir():
    """Kotlarda 5 kat var, zemin ve çatının planı ayrı yüklenmiş → tip kat planı kalan 3 katı temsil eder."""
    kotlar = [0.0, 3.3, 6.6, 9.9, 13.2]
    ds = [cizim(1, "ZEMİN KAT PLANI", kot=0.0, levels=kotlar),
          cizim(2, "ÇATI KATI PLANI", kot=13.2, levels=kotlar),
          cizim(3, "NORMAL KAT PLANI", levels=kotlar)]
    sc = storey_counts(PROJE, ds)
    assert sc["total"] == 5
    assert sc["per_drawing"][1]["value"] == 1
    assert sc["per_drawing"][2]["value"] == 1
    assert sc["per_drawing"][3]["value"] == 3      # planı yüklenmemiş 3 seviyeyi üstlenir
    assert sc["per_drawing"][3]["kind"] == "drawing"


def test_kullanicinin_girdigi_kat_sayisi_ezilmez():
    kotlar = [0.0, 3.3, 6.6, 9.9]
    ds = [cizim(1, "ZEMİN KAT PLANI", kot=0.0, levels=kotlar),
          cizim(2, "NORMAL KAT PLANI", levels=kotlar, manual=2)]
    sc = storey_counts(PROJE, ds)
    assert sc["per_drawing"][2]["value"] == 2
    assert sc["per_drawing"][2]["kind"] == "user"


def test_cikarilamayan_kat_sayisi_varsayim_olarak_isaretlenir():
    """Susmak yasak: 1 kat kabul edildiyse bunun bir varsayım olduğu söylenir."""
    sc = storey_counts(PROJE, [cizim(1, "PLAN")])
    assert sc["per_drawing"][1]["value"] == 1
    assert sc["per_drawing"][1]["kind"] == "default"
    assert any(w["code"] == "storey_count_default" for w in sc["warnings"])


def test_plani_yuklenmemis_kat_blocking_uyari_verir():
    """Kotlarda 4 kat var, 2'sinin planı yok ve tip kat planı da yok → metraj mertebe olarak eksik."""
    kotlar = [0.0, 3.3, 6.6, 9.9]
    ds = [cizim(1, "ZEMİN KAT PLANI", kot=0.0, levels=kotlar),
          cizim(2, "3. KAT PLANI", kot=9.9, levels=kotlar)]
    sc = storey_counts(PROJE, ds)
    assert sc["unowned"] == [3.3, 6.6]
    w = [x for x in sc["warnings"] if x["code"] == "storey_missing_plans"]
    assert w and w[0]["severity"] == "blocking"


def test_kot_kanitli_tek_kat_varsayim_sayilmaz():
    kotlar = [0.0, 3.3]
    ds = [cizim(1, "ZEMİN KAT PLANI", kot=0.0, levels=kotlar),
          cizim(2, "1. KAT PLANI", kot=3.3, levels=kotlar)]
    sc = storey_counts(PROJE, ds)
    assert [sc["per_drawing"][i]["kind"] for i in (1, 2)] == ["drawing", "drawing"]
    assert not sc["warnings"]


def test_kot_yoksa_toplam_kat_uydurulmaz():
    sc = storey_counts(PROJE, [cizim(1, "PLAN"), cizim(2, "PLAN 2", discipline="structural")])
    assert sc["total"] is None


def test_antetle_celisen_kat_sayisi_bildirilir():
    p = Project(name="t")
    p.titleblock = {"storey_count": 8}
    kotlar = [0.0, 3.3, 6.6]
    ds = [cizim(1, "ZEMİN KAT PLANI", kot=0.0, levels=kotlar),
          cizim(2, "NORMAL KAT PLANI", levels=kotlar)]
    sc = storey_counts(p, ds)
    w = [x for x in sc["warnings"] if x["code"] == "storey_count_titleblock"]
    assert w and "8 kat" in w[0]["message"]
