"""Kendini yanlışlayan kontroller.

En önemli test `test_dairesel_kontrol_asla_desteklemez`: demiri betondan türettiğimiz bir kalemde oran
kontrolü kendi kendini onaylar. Böyle bir kontrol `destekliyor` derse sistem kendini kandırıyor demektir.
"""
from app import selfcheck


def grup(etype, label, beton, demir, kalip=0.0, kaynak="tablo"):
    return {"etype": etype, "label": label, "concrete_m3": beton, "rebar_kg": demir,
            "formwork_m2": kalip, "rebar_source": kaynak}


def ozet(gruplar, **kw):
    tot = {"concrete_m3": sum(g["concrete_m3"] for g in gruplar),
           "formwork_m2": sum(g["formwork_m2"] for g in gruplar),
           "rebar_kg": sum(g["rebar_kg"] for g in gruplar)}
    return {"groups": gruplar, "totals": tot, "rebar_by_dia": kw.get("rebar_by_dia", []),
            "by_drawing": kw.get("by_drawing", []), "warnings": []}


def bul(rapor, kod, kapsam=None):
    return [c for c in rapor.checks if c.kod == kod and (kapsam is None or c.kapsam == kapsam)]


# ---- dairesellik: sistemin kendini kandırmaması ----

def test_dairesel_kontrol_asla_desteklemez():
    """Demir = beton × 140 ise "oran 140 çıktı" bir kanıt değildir; kontrol kararsız kalmalı."""
    r = selfcheck.build(ozet([grup("shear_wall", "Perde", 100.0, 14000.0, kalip=500.0, kaynak="oran")]))
    c = bul(r, "demir_orani", "Perde")[0]
    assert c.sonuc == "kararsiz"
    assert "YOK" in c.bagimsizlik
    assert not r.destekleyen or all(x.kapsam != "Perde" for x in r.destekleyen if x.kod == "demir_orani")


def test_bagimsiz_kaynakta_ayni_oran_destekler():
    """Aynı sayı, ama demir tablodan gelirse kontrol artık bir şey kanıtlar."""
    r = selfcheck.build(ozet([grup("shear_wall", "Perde", 100.0, 14000.0, kalip=500.0, kaynak="tablo")]))
    c = bul(r, "demir_orani", "Perde")[0]
    assert c.sonuc == "destekliyor"
    assert "tablo" in c.bagimsizlik


# ---- yanlışlama: gerçek hatanın yakalanması ----

def test_fiziksel_olmayan_kolon_orani_celiskidir():
    """A4-A5'te ölçülen gerçek durum: kat yüksekliği yanlışken kolon 462 kg/m³ çıkıyordu (TS500 tavanı ~400)."""
    r = selfcheck.build(ozet([grup("column", "Kolon", 1370.0, 632953.0, kalip=4669.0)]))
    c = bul(r, "demir_orani", "Kolon")[0]
    assert c.sonuc == "celisiyor"
    assert round(c.olculen) == 462
    assert "kolon betonu" in c.aciklama and "az ölçüldü" in c.aciklama


def test_dogru_yukseklikle_ayni_kalem_destekler():
    """Kotlardan gelen doğru yükseklikle kolon betonu 1.708 m³ -> 370 kg/m³; çelişki kapanır."""
    r = selfcheck.build(ozet([grup("column", "Kolon", 1708.0, 632953.0, kalip=5800.0)]))
    assert bul(r, "demir_orani", "Kolon")[0].sonuc == "destekliyor"


def test_dusuk_oran_da_celiskidir():
    """Bant iki taraflıdır: demir eksik toplandıysa da yakalanmalı."""
    c = bul(selfcheck.build(ozet([grup("column", "Kolon", 1700.0, 85000.0, kalip=5800.0)])), "demir_orani")[0]
    assert c.sonuc == "celisiyor" and "eksik" in c.aciklama


# ---- geometriden türeyen sağlamalar ----

def test_doseme_kalinligi_beton_bolu_kaliptan_turer():
    r = selfcheck.build(ozet([grup("slab", "Döşeme", 3128.0, 272346.0, kalip=21106.0)]))
    c = bul(r, "doseme_kalinlik")[0]
    assert c.sonuc == "destekliyor" and 14.0 < c.olculen < 15.5


def test_imkansiz_doseme_kalinligi_yakalanir():
    """Birim 10 kat yanlış okunduğunda kalınlık 1,5 m çıkar — bu bir döşeme olamaz."""
    c = bul(selfcheck.build(ozet([grup("slab", "Döşeme", 31280.0, 272346.0, kalip=21106.0)])), "doseme_kalinlik")[0]
    assert c.sonuc == "celisiyor" and "olamaz" in c.aciklama


def test_kalip_beton_orani_bant_disi_yakalanir():
    c = bul(selfcheck.build(ozet([grup("beam", "Kiriş", 100.0, 14000.0, kalip=9000.0)])), "kalip_beton")[0]
    assert c.sonuc == "celisiyor"


# ---- çapraz kaynak: çap dökümü ----

def test_cizimde_yazmayan_cap_celiskidir():
    s = ozet([grup("slab", "Döşeme", 100.0, 8000.0, kalip=700.0)],
             rebar_by_dia=[{"dia_mm": 12}, {"dia_mm": 32}])
    c = bul(selfcheck.build(s, rebar_mix={"*": {12: 1.0, 14: 0.5}}), "cap_tutarliligi")[0]
    assert c.sonuc == "celisiyor" and "Ø32" in c.aciklama


def test_cap_kaynagi_yoksa_kararsiz():
    s = ozet([grup("slab", "Döşeme", 100.0, 8000.0, kalip=700.0)], rebar_by_dia=[{"dia_mm": 12}])
    c = bul(selfcheck.build(s, rebar_mix={}), "cap_tutarliligi")[0]
    assert c.sonuc == "kararsiz"


# ---- katlar arası ve aritmetik ----

def test_asiri_sapan_kat_yakalanir():
    kats = [{"drawing": "zemin", "concrete_m3": 500.0}, {"drawing": "1. kat", "concrete_m3": 520.0},
            {"drawing": "2. kat", "concrete_m3": 510.0}, {"drawing": "bodrum", "concrete_m3": 9000.0}]
    c = bul(selfcheck.build(ozet([grup("slab", "Döşeme", 100.0, 8000.0, kalip=700.0)], by_drawing=kats)),
            "kat_tutarliligi")[0]
    assert c.sonuc == "celisiyor" and "bodrum" in c.aciklama


def test_az_kat_varken_karar_verilmez():
    kats = [{"drawing": "zemin", "concrete_m3": 500.0}]
    c = bul(selfcheck.build(ozet([grup("slab", "D", 100.0, 8000.0, kalip=700.0)], by_drawing=kats)),
            "kat_tutarliligi")[0]
    assert c.sonuc == "kararsiz"


def test_toplam_tutmuyorsa_program_hatasi_bildirilir():
    s = ozet([grup("slab", "Döşeme", 100.0, 8000.0, kalip=700.0)])
    s["totals"]["concrete_m3"] = 150.0
    c = [x for x in bul(selfcheck.build(s), "toplam_saglama") if "Beton" in x.ad][0]
    assert c.sonuc == "celisiyor" and "program hatasıdır" in c.aciklama


# ---- rapor ----

def test_ozet_celiskiyi_one_alir():
    r = selfcheck.build(ozet([grup("column", "Kolon", 1370.0, 632953.0, kalip=4669.0)]))
    d = r.to_dict()
    assert d["celisen"] >= 1 and "çelişiyor" in d["ozet"]


def test_hepsi_destekliyorsa_bile_dogruluk_iddia_edilmez():
    r = selfcheck.build(ozet([grup("slab", "Döşeme", 3128.0, 272346.0, kalip=21106.0)]))
    d = r.to_dict()
    assert d["celisen"] == 0
    assert "doğru olduğunu kanıtlamaz" in d["notice"]
