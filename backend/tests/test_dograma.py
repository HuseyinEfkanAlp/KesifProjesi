"""Doğrama zinciri: cam → doğrama → körkasa/kasa, ve ölçüsü bilinmeyen pozun kaybolmaması.

İlke: **varlık ile ölçü ayrı şeylerdir.** Bir yerde cam varsa orada doğrama da, körkasa da vardır; ölçüsü
okunamadı diye kalem silinmez — adet keşifte kalır, eksik olan ölçü açıkça bildirilir.
"""
from types import SimpleNamespace as Obj

from app.services import CURVED_WORDS, GLAZED_WORDS, _curved_joinery, _sizeless_joinery


def item(kind, label, count, size=None, group=""):
    return Obj(kind=kind, label=label, count=count, group=group or label, detail={"size": size} if size else {})


# ---- camlı kapı ----

def test_fotoselli_kapi_camli_sayilir():
    """AVM girişindeki fotoselli kapı neredeyse tamamen camdır; "KAPI" geçiyor diye camsız sayılamaz."""
    for t in ("EMP2 FOTOSELLİ KAPI", "EMP4 (FOTOSELLİ KAPI)", "VİTRİN KAPI", "CAMLI KAPI", "GİYOTİN"):
        assert GLAZED_WORDS.search(t.replace("i", "İ").upper()), t


def test_duz_kapi_camli_sayilmaz():
    for t in ("EMP3 AÇILIR KAPI", "YANGIN KAPISI", "ÇELİK KAPI"):
        assert not GLAZED_WORDS.search(t.replace("i", "İ").upper()), t


# ---- ölçüsü bilinmeyen doğrama ----

def test_olcusuz_dograma_poz_ve_adetle_bildirilir():
    """Ölçüsü olmayan poz keşiften düşmez; adetiyle listelenir ki ölçüsü girilebilsin."""
    items = [item("dograma", "Doğrama (poz listesinden) EMP8", 13),
             item("dograma", "Doğrama (poz listesinden) EMP2", 2),
             item("dograma", "Doğrama (poz listesinden) EMP1", 82, size="140x190")]
    out = _sizeless_joinery(items)
    assert out == {"EMP8": 13, "EMP2": 2}          # ölçülü olan listede yok
    assert sum(out.values()) == 15


def test_olculu_dograma_eksik_sayilmaz():
    assert _sizeless_joinery([item("dograma", "D EMP1", 5, size="140x190")]) == {}


def test_dograma_disi_kalemler_karismaz():
    assert _sizeless_joinery([item("cam", "Cam 140×190", 5), item("duvar", "Ytong 20", 100)]) == {}


# ---- kavisli doğrama ----

def test_kavisli_dograma_yazidan_taninir():
    for t in ("EMP5 KAVİSLİ PENCERE", "KEMERLİ VİTRİN", "ARCH WINDOW", "OVAL PENCERE"):
        assert CURVED_WORDS.search(t.replace("i", "İ")), t


def test_duz_dograma_kavisli_sayilmaz():
    for t in ("EMP1", "FOTOSELLİ KAPI", "AÇILIR KAPI"):
        assert not CURVED_WORDS.search(t.replace("i", "İ")), t


def test_kavisli_dograma_poz_ve_adetle_toplanir():
    class S:
        pass
    d = Obj(id=1)
    els = [Obj(etype="dograma", subtype="EMP5", name="EMP5 KAVİSLİ", meta={}, label_raw="", count=3),
           Obj(etype="dograma", subtype="EMP1", name="EMP1", meta={}, label_raw="", count=82),
           Obj(etype="dograma", subtype="EMP6", name="EMP6", meta={"note": "KEMERLİ ÜST"}, label_raw="", count=2)]
    import app.services as sv
    eski = sv._included_elements
    sv._included_elements = lambda drawing, session: els
    try:
        out = _curved_joinery([d], S())
    finally:
        sv._included_elements = eski
    assert out == {"EMP5": 3, "EMP6": 2}


def test_boardex_katalogda_var():
    """Kavisli detayda boardex gerekir; katalogda yoksa kullanıcı elle bile giremez."""
    from app.standard.catalog import Catalog
    it = Catalog().get("BOARDEX")
    assert it is not None and it.unit == "m²" and it.discipline == "IZO"
