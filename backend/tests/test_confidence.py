"""Güven rozeti: sayının nereden geldiği (app/confidence.py).

Ürünün sözü şu: **tahmin, ölçüm gibi sunulmaz.** Testler "en kötü girdi kazanır" kuralını,
kademenin birikmediğini ve rozetin dahil/hariç kararına karışmadığını sabitler.
"""
from app.confidence import (OLCULDU, TAHMIN, TANINDI, TURETILDI, distribution, element_tier,
                            grade, merge, shift, worse)
from app.quantity.boq import BoqItem


class El:
    """Eleman benzeri: detektörün bıraktığı kimlik kanıtı."""
    def __init__(self, confidence=0.9, meta=None, manual=False, source="POLYLINE"):
        self.confidence, self.meta, self.manual, self.source = confidence, meta or {}, manual, source


def test_en_kotu_girdi_kazanir():
    assert worse(OLCULDU, TANINDI) == TANINDI
    assert worse(TURETILDI, OLCULDU, TAHMIN) == TAHMIN
    assert worse(None, None) == OLCULDU


def test_elle_girilen_eleman_olculdu_sayilir():
    assert element_tier(El(confidence=0.2, manual=True)) == OLCULDU


def test_katman_adindan_otomatik_eslenen_taninmis_sayilir():
    """detect_mapped'in `auto_mapped` kalemi: geometri plandan ama kimlik yalnız addan."""
    assert element_tier(El(confidence=0.55, meta={"auto_mapped": True, "ksf_code": "SIVA"})) == TANINDI


def test_ksf_kodlu_eleman_olculdu_sayilir():
    assert element_tier(El(confidence=0.55, meta={"ksf_code": "SIVA"})) == OLCULDU


def test_oturum_hattindan_tahmin_edilen_eleman_tahmindir():
    assert element_tier(El(confidence=0.5, source="FOOTPRINT_ESTIMATE")) == TAHMIN


def test_dusuk_guvenli_eleman_adindan_taninmis_sayilir():
    assert element_tier(El(confidence=0.5)) == TANINDI
    assert element_tier(El(confidence=0.9)) == OLCULDU


# ------------------------------------------------------------------ rozet

def test_rozet_miktari_sifir_olmayan_en_kotu_kademeyi_alir():
    g = grade({OLCULDU: 900.0, TANINDI: 12.0})
    assert g["code"] == TANINDI
    assert g["shares"][OLCULDU] > g["shares"][TANINDI]


def test_sifir_miktarli_kanit_rozeti_dusurmez():
    assert grade({OLCULDU: 100.0, TAHMIN: 0.0})["code"] == OLCULDU


def test_kaniti_olmayan_kalem_olculmus_sayilmaz():
    assert grade(None)["code"] == TURETILDI
    assert grade({}, fallback=TAHMIN)["code"] == TAHMIN


def test_turetme_kademesi_birikmez():
    """Üç basamaklı reçete zinciri kendiliğinden kırmızıya düşmemeli: belirsizlik her adımda yeniden doğmaz."""
    ev = {OLCULDU: 100.0}
    for _ in range(3):
        ev = shift(ev, tier=TURETILDI)
    assert grade(ev)["code"] == TURETILDI


def test_turetme_kotu_girdiyi_duzeltmez():
    assert grade(shift({TAHMIN: 50.0}, tier=TURETILDI))["code"] == TAHMIN


def test_kanit_toplanir():
    ev = merge(merge(None, OLCULDU, 10.0), {TANINDI: 4.0})
    assert ev == {OLCULDU: 10.0, TANINDI: 4.0}


# ------------------------------------------------------------------ kalem ve dağılım

def _item(key, ev=None, **detail):
    return BoqItem(key=key, kind=key.split(":")[0], group="*", label=key, unit="m²", quantity=1.0,
                   discipline="architectural", detail={**detail, **({"evidence": ev} if ev else {})})


def test_boq_kalemi_rozetini_kanittan_okur():
    assert _item("siva:*", {OLCULDU: 5.0}).confidence["code"] == OLCULDU
    assert _item("siva:*", {OLCULDU: 5.0, TAHMIN: 1.0}).confidence["code"] == TAHMIN


def test_pafta_belirsizligi_rozetin_gerekcesine_yazilir():
    it = _item("armatur:*", {TAHMIN: 16.0}, confidence_notes=["Bu paftanın kaç katı temsil ettiği çizimden çıkarılamadı."])
    assert "kaç katı temsil ettiği" in it.confidence["note"]


def test_dagilim_cumlesi_uretilir():
    d = distribution([_item("a:*", {OLCULDU: 1.0}), _item("b:*", {OLCULDU: 1.0}),
                      _item("c:*", {TAHMIN: 1.0}), _item("d:*", {TURETILDI: 1.0})])
    assert d["total"] == 4
    assert d["counts"][OLCULDU] == 2
    assert d["sentence"].startswith("Metrajın kaynağı: %50 çizimden ölçüldü")
