"""Mekânsal çelişki kontrolleri (app/selfcheck.py).

Modülün tek kuralı burada da geçerlidir: **dairesel kontrol hiçbir şey kanıtlamaz.** Bir kontrolün
değeri girdilerinin birbirinden bağımsız olmasından gelir — mimarın yazdığı alan ile bizim
ölçtüğümüz çokgen birbirini hiç görmez, antetteki inşaat alanı ile çizimden ölçülen kat alanı da öyle.
"""
from app.selfcheck import build


def _sp(i, name, area, label_area, drawing_id=1, source="drawing", parent=None, kind="mahal"):
    return {"index": i, "name": name, "area": area, "label_area": label_area, "kind": kind,
            "area_source": source, "parent": parent, "drawing_id": drawing_id}


def _fp(drawing_id=1, area=500.0, source="structural", drawing="Kat kalıp planı", storey_count=1):
    return {"drawing_id": drawing_id, "area": area, "source": source, "drawing": drawing,
            "storey_count": storey_count}


def _sonuc(rapor, kod):
    return next(c for c in rapor.checks if c.kod == kod)


# ------------------------------------------------------------------ mahal alanı

def test_olculen_alanlar_yazidakiyle_ortusurse_destekler():
    spaces = [_sp(i, f"ODA {i}", 100.0 + i, 100.0) for i in range(5)]
    assert _sonuc(build({}, spaces=spaces), "mahal_alani").sonuc == "destekliyor"


def test_sistematik_kayma_celiski_sayilir():
    """Tek tek sapma değil, bütününe yayılan kayma: ölçek ya da birim hatasıdır ve
    kaplama / şap / tavan metrajını aynı oranda kaydırır."""
    spaces = [_sp(i, f"ODA {i}", 130.0, 100.0) for i in range(5)]
    c = _sonuc(build({}, spaces=spaces), "mahal_alani")
    assert c.sonuc == "celisiyor" and c.olculen == 30.0
    assert "ölçek ya da birim" in c.aciklama


def test_tek_mahaldeki_sapma_celiski_degil_bulgudur():
    """Bir mahalde duvar ekseni / iç yüz farkı normaldir; bütünü bozmuyorsa çelişki sayılmaz."""
    spaces = [_sp(i, f"ODA {i}", 100.0, 100.0) for i in range(5)] + [_sp(9, "HOL", 160.0, 100.0)]
    c = _sonuc(build({}, spaces=spaces), "mahal_alani")
    assert c.sonuc == "destekliyor" and "HOL" in c.aciklama


def test_alan_yazisi_olmayan_mahal_karsilastirmaya_girmez():
    spaces = [_sp(i, f"ODA {i}", 100.0, 0.0) for i in range(6)]
    assert _sonuc(build({}, spaces=spaces), "mahal_alani").sonuc == "kararsiz"


def test_siniri_olculmemis_mahal_karsilastirmaya_girmez():
    """Alanı yalnız yazıdan alınan mahalde karşılaştırılacak ikinci ölçü yoktur."""
    spaces = [_sp(i, f"ODA {i}", 100.0, 100.0, source="label") for i in range(6)]
    assert _sonuc(build({}, spaces=spaces), "mahal_alani").sonuc == "kararsiz"


# ------------------------------------------------------------------ mahaller bina içinde

def test_mahaller_dis_hatti_asarsa_celiski():
    spaces = [_sp(0, "SALON", 400.0, 400.0), _sp(1, "ODA", 200.0, 200.0)]
    c = _sonuc(build({}, spaces=spaces, footprints=[_fp(area=300.0)]), "mahal_oturum")
    assert c.sonuc == "celisiyor" and "aşıyor" in c.aciklama


def test_mahaller_dis_hattin_icindeyse_destekler():
    spaces = [_sp(0, "SALON", 400.0, 400.0)]
    assert _sonuc(build({}, spaces=spaces, footprints=[_fp(area=500.0)]), "mahal_oturum").sonuc == "destekliyor"


def test_dis_hat_mahalden_turetilmisse_kontrol_dairesel_sayilir():
    """Faz 4'te dış hattın birincil kaynağı mahal sınırları oldu; o hâlde bu karşılaştırma
    aynı sayıya iki kez bakmaktır ve mahalleri kopuk bir katta sahte çelişki üretir."""
    spaces = [_sp(0, "TERAS", 1000.0, 1000.0)]
    c = _sonuc(build({}, spaces=spaces, footprints=[_fp(area=400.0, source="spaces")]), "mahal_oturum")
    assert c.sonuc == "kararsiz" and "dairesel" in c.aciklama


def test_ic_ice_mahal_iki_kez_sayilmaz():
    spaces = [_sp(0, "SPOR SALONU", 400.0, 400.0), _sp(1, "DEPO", 100.0, 100.0, parent=0)]
    assert _sonuc(build({}, spaces=spaces, footprints=[_fp(area=420.0)]), "mahal_oturum").sonuc == "destekliyor"


# ------------------------------------------------------------------ antetteki inşaat alanı

def test_antet_alaniyla_olculen_ortusurse_destekler():
    r = build({}, footprints=[_fp(area=500.0), _fp(drawing_id=2, area=500.0)],
              titleblock={"area_m2": 1100.0})
    assert _sonuc(r, "antet_alani").sonuc == "destekliyor"


def test_birim_hatasi_antet_kontrolunde_yakalanir():
    """cm yerine mm okunan bir çizimde alanlar 100 kat çıkar; başka hiçbir kontrol bunu görmez."""
    r = build({}, footprints=[_fp(area=50000.0)], titleblock={"area_m2": 500.0})
    c = _sonuc(r, "antet_alani")
    assert c.sonuc == "celisiyor" and "birim" in c.aciklama


def test_kat_sayisi_carpani_hesaba_girer():
    """Tip kat planı 5 katı temsil ediyorsa inşaat alanı da beş katıdır (Faz 2)."""
    r = build({}, footprints=[_fp(area=200.0, storey_count=5)], titleblock={"area_m2": 1000.0})
    assert _sonuc(r, "antet_alani").sonuc == "destekliyor"


def test_antet_yoksa_kontrol_uretilmez():
    r = build({}, footprints=[_fp(area=500.0)], titleblock={})
    assert not [c for c in r.checks if c.kod == "antet_alani"]
