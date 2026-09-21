"""Aynı keşif kaleminin tek satırda toplanması.

Keşif listesi ayrı üreticilerin listelerinin toplanmasıyla kurulur (sezgisel mimari / elektrik,
KÇS standart çizim, türetilmiş kalemler). Her üretici kendi `_Acc`'si içinde aynı anahtarı zaten
topluyor; bu dosya İKİ ÜRETİCİNİN aynı anahtarı doğurduğu durumu korur — gerçek örneği KÇS
duvarından türeyen sıvanın sezgisel duvarın sıvasıyla aynı `siva:*` anahtarını taşımasıdır.
"""
from __future__ import annotations

from app.quantity.boq import BoqItem, merge_duplicates


def _item(key: str, qty: float, unit: str = "m²", *, count: float = 0.0,
          note: str | None = None, **detail) -> BoqItem:
    kind, group = key.split(":", 1)
    return BoqItem(key=key, kind=kind, group=group, label="Sıva (2 yüz)", unit=unit,
                   quantity=qty, discipline="architectural", kind_label="Sıva",
                   count=count, notes=[note] if note else [], detail=dict(detail))


def test_ayni_anahtar_tek_satirda_toplanir():
    """İki üreticiden gelen `siva:*` tek satır olur, miktar toplanır."""
    out = merge_duplicates([_item("siva:*", 228.18), _item("siva:*", 36.0)])
    assert len(out) == 1
    assert out[0].quantity == 264.18                      # 228,18 + 36,00
    assert out[0].key == "siva:*"


def test_farkli_anahtar_ayri_kalir():
    out = merge_duplicates([_item("siva:*", 10.0), _item("boya:*", 20.0), _item("siva:ic", 5.0)])
    assert [i.key for i in out] == ["siva:*", "boya:*", "siva:ic"]   # sıra korunur
    assert [i.quantity for i in out] == [10.0, 20.0, 5.0]


def test_notlar_birlesir_tekrar_etmez():
    a = _item("siva:*", 10.0, note="tüm boşluklar düşülür")
    b = _item("siva:*", 5.0, note="KSF duvar alanından")
    c = _item("siva:*", 1.0, note="tüm boşluklar düşülür")      # aynı not ikinci kez
    out = merge_duplicates([a, b, c])
    assert len(out) == 1
    assert out[0].notes == ["tüm boşluklar düşülür", "KSF duvar alanından"]


def test_adet_ve_sayisal_detay_toplanir_metin_detay_ezilir():
    a = _item("kapi:k1", 1.0, unit="adet", count=2.0, opening_m2=3.5, source="sezgisel")
    b = _item("kapi:k1", 2.0, unit="adet", count=3.0, opening_m2=1.5, source="ksf")
    out = merge_duplicates([a, b])
    assert len(out) == 1
    assert out[0].quantity == 3.0
    assert out[0].count == 5.0
    assert out[0].detail["opening_m2"] == 5.0              # sayısal: toplanır
    assert out[0].detail["source"] == "ksf"                # metin: sonuncusu geçerli


def test_girdi_nesnesi_degismez():
    """İlk kalem kopyalanır — çağıran aynı listeyi başka hesapta da kullanıyor olabilir."""
    a = _item("siva:*", 10.0, note="ilk")
    out = merge_duplicates([a, _item("siva:*", 5.0, note="ikinci")])
    assert out[0].quantity == 15.0
    assert a.quantity == 10.0                              # girdi olduğu gibi durur
    assert a.notes == ["ilk"]


def test_birimi_farkli_kalem_birlesmez():
    """m² ile adet toplanamaz; böyle bir çakışma sessizce toplanırsa yanlış miktar üretir."""
    out = merge_duplicates([_item("x:y", 10.0, unit="m²"), _item("x:y", 3.0, unit="adet")])
    assert len(out) == 2
    assert [i.quantity for i in out] == [10.0, 3.0]


def test_idempotent():
    bir = merge_duplicates([_item("siva:*", 10.0), _item("siva:*", 5.0)])
    iki = merge_duplicates(bir)
    assert len(iki) == 1 and iki[0].quantity == 15.0


def test_ksf_ve_sezgisel_siva_gercek_akista_tek_satir():
    """Asıl senaryo: aynı projede hem sezgisel mimari duvar hem KÇS duvarı olunca
    `siva:*` ve `boya:*` ikişer kez doğuyordu (boq.py'de iki ayrı üretici)."""
    items = [
        _item("siva:*", 228.18, note="× yüz sayısı"),
        _item("boya:*", 228.18, note="× yüz sayısı"),
        _item("siva:*", 36.0, note="KSF duvar alanından (alçıpan hariç)"),
        _item("boya:*", 36.0, note="KSF duvar alanından"),
    ]
    out = merge_duplicates(items)
    anahtarlar = [i.key for i in out]
    assert anahtarlar == ["siva:*", "boya:*"]              # dörtten ikiye
    assert len(set(anahtarlar)) == len(anahtarlar)         # React key çakışması kalmadı
    assert {i.key: round(i.quantity, 2) for i in out} == {"siva:*": 264.18, "boya:*": 264.18}
