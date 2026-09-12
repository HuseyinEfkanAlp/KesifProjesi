"""Plandan donatı metrajı: adetli çağrı × çizilen kol boyu, ve etriye hesabı.

Buradaki sayılar elle sağlanabilir olsun diye seçildi; gerçek dosya doğrulaması ayrıca yapıldı
(A4-A5'in 11 donatı paftasında plan hesabı 906.504 kg, müellif tabloları 907.891 kg — %0,2 fark).
"""
from types import SimpleNamespace as Obj

import pytest

from app.parser import rebar_plan as rp


def ent(kind, layer, points, text=""):
    return Obj(kind=kind, layer=layer, points=points, text=text, handle="", source="", closed=False, height=0.0)


def drawing(entities, unit="cm", scale=0.01):
    d = Obj(entities=entities, unit=unit, scale=scale, layers=sorted({e.layer for e in entities}), warnings=[])
    d.texts = lambda: [e for e in d.entities if e.kind == "text"]
    return d


def bar(x0, y0, x1, y1, layer="VM Üst Donatı"):
    return ent("line", layer, [(x0, y0), (x1, y1)])


def callout(x, y, text, layer="0"):
    return ent("text", layer, [(x, y)], text)


# ---- birim ağırlık ----

def test_birim_agirlik_celik_yogunlugundan():
    assert rp.unit_weight(12) == pytest.approx(0.888, abs=0.002)      # Ø12 = 0,888 kg/m
    assert rp.unit_weight(8) == pytest.approx(0.395, abs=0.002)
    assert rp.unit_weight(26) == pytest.approx(4.168, abs=0.005)


# ---- çağrı × kol boyu ----

def test_tek_grup_adet_carpi_cizilen_boy():
    """21ƒ10/18 + 4,95 m çizili çubuk -> 21 × 4,95 × 0,617 = 64,2 kg."""
    d = drawing([bar(0, 0, 4.95, 0), callout(2.4, 0.1, "21ƒ10/18")])
    r = rp.plan_bar_groups(d)
    assert len(r.groups) == 1
    g = r.groups[0]
    assert g.adet == 21 and g.dia_mm == 10 and g.aralik_cm == 18
    assert g.kol_boyu_m == pytest.approx(4.95, abs=0.01)
    assert r.toplam_kg == pytest.approx(21 * 4.95 * rp.unit_weight(10), rel=1e-6)


def test_kirik_cubukta_kollar_toplanir():
    """Kırık (L) çubukta her kol ayrı çizgidir; bir çubuğun boyu kolların toplamıdır."""
    d = drawing([bar(0, 0, 3.0, 0), bar(3.0, 0, 3.0, 1.5), callout(1.5, 0.1, "10ƒ12/15")])
    g = rp.plan_bar_groups(d).groups[0]
    assert g.kol_sayisi == 2
    assert g.kol_boyu_m == pytest.approx(4.5, abs=0.01)


def test_carpimli_adet_okunur():
    d = drawing([bar(0, 0, 2.0, 0), callout(1.0, 0.1, "4X7ƒ12/10")])
    g = rp.plan_bar_groups(d).groups[0]
    assert g.adet == 7 and g.carpan == 4
    assert g.toplam_boy_m == pytest.approx(4 * 7 * 2.0, rel=1e-6)


def test_uzaktaki_cizgi_baglanmaz():
    """Aks / çerçeve çizgisi demire dönüşmemeli: çağrıdan uzak parça sayılmaz."""
    d = drawing([bar(0, 0, 3.0, 0), bar(0, 50.0, 3.0, 50.0), callout(1.5, 0.1, "10ƒ12/15")])
    r = rp.plan_bar_groups(d)
    assert r.baglanmamis_cizgi == 1
    assert r.groups[0].kol_sayisi == 1


def test_marka_ve_poz_katmanlari_cubuk_sayilmaz():
    """'VM Donatı Markası' yalnız yazı taşır; oradaki çizgi çubuk sayılırsa uydurma tonaj çıkar."""
    d = drawing([bar(0, 0, 3.0, 0, layer="VM Donatı Markası"), callout(1.5, 0.1, "10ƒ12/15")])
    r = rp.plan_bar_groups(d)
    assert not r.groups
    assert any("çizili çubuk bulunamadı" in w for w in r.warnings)

    # aynı çizgi gerçek donatı katmanındayken sayılır (kontrol grubu)
    d2 = drawing([bar(0, 0, 3.0, 0), callout(1.5, 0.1, "10ƒ12/15")])
    assert rp.plan_bar_groups(d2).groups


def test_cok_kisa_ve_cok_uzun_cizgiler_elenir():
    d = drawing([bar(0, 0, 0.2, 0), bar(0, 0.5, 30.0, 0.5), callout(0.1, 0.05, "10ƒ12/15")])
    assert not rp.plan_bar_groups(d).groups


def test_cubuk_yoksa_hesap_yapilmaz_ve_sebebi_yazilir():
    d = drawing([callout(1.0, 1.0, "21ƒ10/18")])
    r = rp.plan_bar_groups(d)
    assert not r.groups
    assert any("çizili çubuk bulunamadı" in w for w in r.warnings)


def test_cap_bazinda_dokum():
    d = drawing([bar(0, 0, 2.0, 0), callout(1.0, 0.1, "10ƒ10/15"),
                 bar(0, 5.0, 2.0, 5.0), callout(1.0, 5.1, "10ƒ12/15")])
    by = rp.plan_bar_groups(d).by_dia()
    assert set(by) == {10, 12}
    assert by[12] > by[10]                    # aynı adet ve boy, kalın çap daha ağır


# ---- birim sağlaması ----

def test_yazilan_boy_olculen_boyla_tutmuyorsa_hesap_yapilmaz():
    """Çizim çubuk boylarını cm yazar; 10 kat sapma birim hatasıdır ve tonaj üretilmemelidir."""
    ents = []
    for i in range(12):
        ents += [bar(0, i, 0.495, i), ent("text", "VM Poz Kollar", [(0.2, i + 0.02)], "495"),
                 callout(0.2, i + 0.1, "21ƒ10/18")]
    r = rp.plan_bar_groups(drawing(ents, unit="mm", scale=0.001))
    assert not r.groups
    assert any("birimi 'mm'" in w and "10 katı" in w for w in r.warnings)


def test_birim_dogruysa_uyari_cikmaz():
    ents = []
    for i in range(12):
        ents += [bar(0, i, 4.95, i), ent("text", "VM Poz Kollar", [(2.4, i + 0.02)], "495"),
                 callout(2.4, i + 0.1, "21ƒ10/18")]
    r = rp.plan_bar_groups(drawing(ents))
    assert r.groups and not any("çelişiyor" in w for w in r.warnings)


def test_onerilen_birim_olcekten_turetilir():
    ents = []
    for i in range(12):
        ents += [bar(0, i, 0.495, i), ent("text", "VM Poz Kollar", [(0.2, i + 0.02)], "495")]
    assert rp.suggested_unit(drawing(ents, unit="mm", scale=0.001)) == "cm"


# ---- etriye ----

def test_etriye_agirligi_elle_saglanabilir():
    """80/30 kolon, H=3,95 m, Ø12/10: adet 40, çevre 2×(0,8+0,3) − 8×0,025 + 2×0,10 = 2,20 m."""
    kg, det = rp.stirrup_weight(0.80, 0.30, 3.95, rp.StirrupSpec(12, 0.10, "Ø12/10"))
    assert det["adet"] == 40
    assert det["cevre_m"] == pytest.approx(2.20, abs=0.001)
    assert kg == pytest.approx(40 * 2.20 * rp.unit_weight(12), rel=1e-6)


def test_etriye_yazisi_etr_kelimesi_ister():
    """'ƒ12/15' tek başına döşeme donatısı olabilir; etriye sayılması için ETR yazmalı."""
    d = drawing([callout(0, 0, "ƒ12/15"), callout(0, 1, "ƒ12/15"), callout(0, 2, "ƒ12/15")])
    assert rp.find_stirrup_spec(d) is None
    d2 = drawing([callout(0, 0, "GÖVDE ETR. ƒ12/15")])
    sp = rp.find_stirrup_spec(d2)
    assert sp and sp.dia_mm == 12 and sp.aralik_m == pytest.approx(0.15)


def test_yakindaki_etriye_yazisi_baskin_olana_tercih_edilir():
    d = drawing([callout(0, 0, "BAŞLIK ETR. ƒ14/10"), callout(50, 50, "GÖVDE ETR. ƒ8/20"),
                 callout(51, 50, "GÖVDE ETR. ƒ8/20"), callout(52, 50, "GÖVDE ETR. ƒ8/20")])
    assert rp.find_stirrup_spec(d, point=(0.2, 0.2)).dia_mm == 14      # yakındaki
    assert rp.find_stirrup_spec(d).dia_mm == 8                          # baskın olan


def test_kesit_yoksa_etriye_hesaplanmaz():
    """Uydurma kesitle sayı üretmektense hesap yapmamak doğrudur."""
    kg, det = rp.stirrup_weight(0.0, 0.30, 3.0, rp.StirrupSpec(8, 0.10, "x"))
    assert kg == 0.0 and det == {}
