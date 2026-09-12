"""Sessizce ölçülmeden kalan içeriği görünür kılan kontroller.

İki gerçek dosyadan çıktı:
  * A4-A5 kalıp paftalarında aynı döşeme markası ("D1000") 528 kez yazılmıştı; 26 döşemeye atanmıştı ama kalan
    kopyalar "hücreye düşmedi" diye eksik sayılıp dört paftayı da engelliyordu (yanlış alarm).
  * B2 BLOK'un "BİRİNCİ KAT PLANI" paftasında FB_Prekast katmanı 177.592 nesne (paftanın %94'ü) tutuyor ve
    hiçbir kalem üretmiyordu; uyarı listesinde 3 nesnelik katmanlarla aynı görünüyordu.
"""
from types import SimpleNamespace as Obj

from app.parser.analyzer import _dominant_unmapped, _unclaimed_labels
from app.parser.detectors.standard import measure_layer
from app.quality import build_quality
from datetime import datetime


def label(name, x, y, b=None, h=None, hint="beam"):
    lab = Obj(name=name, type_hint=hint, b=b, h=h, has_dims=b is not None)
    return (Obj(points=[(x, y)]), lab)


def index(items, claimed=()):
    return Obj(items=items, claimed=set(claimed))


def element(name=None, b=None, h=None, box=None):
    return Obj(name=name, b=b, h=h, points=box or [])


def rect(x, y, w=1.0, d=1.0):
    return [(x, y), (x + w, y), (x + w, y + d), (x, y + d)]


def test_marka_olculen_elemanda_geciyorsa_eksik_sayilmaz():
    """Aynı marka planda defalarca yazılır; adı ölçülen bir elemanda geçiyorsa ortada eksik miktar yoktur."""
    labels = index([label("D1000", 50.0, 50.0, hint="slab")])
    slabs = [element(name="D1000", box=rect(0, 0, 10, 10))]
    assert _unclaimed_labels(labels, slabs, "slab") == ([], [])


def test_yakininda_ayni_kesit_olculmusse_ad_eslesmesi_sayilir():
    """Uzun kiriş hattı komşu markayı alınca etiket boşta kalır; miktar sayılmıştır, yalnız ad eşleşmemiştir."""
    labels = index([label("K2032", 1.0, 2.2, b=1.0, h=0.45)])
    beams = [element(name="K2378", b=1.0, h=0.45, box=rect(0, 0, 6, 2))]   # etiket kenardan 0,20 m
    gap, renamed = _unclaimed_labels(labels, beams, "beam", require_dims=True)
    assert gap == [] and renamed == ["K2032"]


def test_yakininda_hicbir_sey_yoksa_gercek_bosluk():
    labels = index([label("K2032", 100.0, 100.0, b=1.0, h=0.45)])
    beams = [element(name="K2378", b=1.0, h=0.45, box=rect(0, 0, 6, 2))]
    gap, renamed = _unclaimed_labels(labels, beams, "beam", require_dims=True)
    assert gap == ["K2032"] and renamed == []


def test_farkli_kesitli_komsu_bosluk_sayilir():
    """Yanındaki kiriş başka kesitteyse etiketin kirişi ölçülmüş sayılmaz."""
    labels = index([label("K2032", 1.0, 2.2, b=1.0, h=0.45)])
    beams = [element(name="K2378", b=0.4, h=0.6, box=rect(0, 0, 6, 2))]
    gap, renamed = _unclaimed_labels(labels, beams, "beam", require_dims=True)
    assert gap == ["K2032"] and renamed == []


def test_atanmis_etiket_hic_sorgulanmaz():
    labels = index([label("K1", 1.0, 2.2, b=1.0, h=0.45)], claimed=[0])
    assert _unclaimed_labels(labels, [element(name="K1")], "beam", require_dims=True) == ([], [])


def test_paftanin_cogunu_tutan_eslenmemis_katman_bildirilir():
    infos = [Obj(name="FB_Prekast", count=177592, etype=None), Obj(name="brn_windows", count=31, etype=None),
             Obj(name="brn_duvar_gazbeton", count=11000, etype="wall")]
    unmapped = sorted((li for li in infos if li.etype is None), key=lambda li: -li.count)
    out = _dominant_unmapped(unmapped, infos)
    assert len(out) == 1
    assert "FB_Prekast" in out[0] and "%94" in out[0] and "177.592" in out[0]


def test_kucuk_eslenmemis_katman_icin_ayrica_uyari_cikmaz():
    infos = [Obj(name="notlar", count=5, etype=None), Obj(name="duvar", count=500, etype="wall")]
    assert _dominant_unmapped([infos[0]], infos) == []


def test_etiket_kurali_yazisiz_katmanda_geometriyi_bildirir():
    """label_count yazı ister; katmanda yazı yok ama geometri varsa o geometri sessizce düşmemeli."""
    ents = [Obj(kind="polygon", points=rect(0, 0), text=None, source="LWPOLYLINE", handle="A", block=None)
            for _ in range(12)]
    drawing = Obj(by_layer=lambda layer: ents)
    item = Obj(name="Prekast cephe paneli", measure="label_count", discipline="CEP")
    els, warns = measure_layer(drawing, "FB_Prekast", "PREKAST_PANEL", item, "label_count", None,
                               Obj(min_line_length=0.1))
    assert els == []
    assert len(warns) == 1 and "12 çizim nesnesi ölçülmeden kaldı" in warns[0]


def test_olculmeden_kalan_icerik_eksik_sayilir():
    """Bu iki uyarı inceleme notu değil eksiktir: paftanın miktarı keşfe girmiyor."""
    d = Obj(id=1, label="Birinci kat", filename="k1.dxf", plan_type="mim_kat_plani", analyzed_at=datetime.now(),
            unit_detected=True, unit_override=None,
            warnings=["'FB_Prekast' katmanı bu paftanın nesnelerinin %94'ini tutuyor (177.592 nesne) "
                      "ama hiçbir keşif kalemi üretmedi.",
                      "FB_Prekast: etiket sayımı için yazı yok; buna karşılık 5.692 çizim nesnesi ölçülmeden kaldı"])
    q = build_quality([d], [], [], {}, {}, {})
    blockers = [i for i in q['issues'] if i['severity'] == 'blocking' and i['code'] == 'unresolved_geometry']
    assert len(blockers) == 2
    assert q['status'] == 'incomplete'
