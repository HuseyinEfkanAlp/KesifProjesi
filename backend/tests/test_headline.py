"""Ana kalemler: her kalem için toplam, ölçülen / tahmin / fire ayrımı ve döküm."""
from app.quantity import headline
from app.quantity.boq import BoqItem


def _it(kind, group, label, qty, unit, count=0.0, **detail):
    return BoqItem(key=f"{kind}:{group}", kind=kind, group=group, label=label, unit=unit,
                   quantity=qty, discipline="structural", count=count, detail=detail)


ITEMS = [
    _it("beton", "column", "Beton - Kolon", 1370.1, "m³", count=457),
    _it("beton", "slab", "Beton - Döşeme", 3128.0, "m³", count=368),
    _it("beton", "fire", "Beton fire (%3)", 436.3, "m³"),
    _it("kalip", "slab", "Kalıp - Döşeme", 21106.1, "m²", count=368),
    _it("beton_iscilik", "*", "Beton yerleştirme işçiliği", 15349.0, "saat"),
    _it("vibrator", "*", "Vibratör (beton sıkıştırma)", 4362.6, "saat"),
    _it("beton_kur", "*", "Beton kürü", 14542.0, "m²"),
    _it("duvar", "ytong:25", "Ytong / gazbeton 25 cm", 757.5, "m²",
        gross_m2=757.5, openings_m2=0.0, openings_already_net_m2=202.5),
    _it("duvar", "ytong:20", "Ytong / gazbeton 20 cm", 380.0, "m²",
        gross_m2=391.5, openings_m2=11.5, openings_review_required=True),
    _it("duvar_iscilik", "*", "Duvar örgü işçiliği", 1477.4, "saat"),
]


def _sec(kind, items=None):
    return next(s for s in headline.build(items or ITEMS, {}) if s["kind"] == kind)


def test_beton_fire_toplamdan_ayri_durur():
    """Sipariş = ölçülen + fire; ikisi karışırsa ne sipariş ne metraj kontrolü doğru olur."""
    b = _sec("beton")
    assert b["net"] == 4498.1 and b["waste"] == 436.3
    assert round(b["total"], 1) == 4934.4
    assert [r["label"] for r in b["rows"]] == ["Beton - Döşeme", "Beton - Kolon"]   # büyükten küçüğe
    assert next(r for r in b["rows"] if r["label"] == "Beton - Kolon")["count"] == 457


def test_firesiz_kalemde_toplam_olculene_esit():
    k = _sec("kalip")
    assert k["waste"] == 0.0 and k["total"] == k["net"] == 21106.1


def test_duvar_brut_dusulen_ve_zaten_net_ayri():
    """Net = brüt − düşülen. "Zaten net" düşülen değildir: çizimde duvar kesilerek gösterilmiş demektir,
    ikinci kez düşülürse metraj eksik çıkar."""
    d = _sec("duvar")
    assert d["net"] == d["total"] == 1137.5           # 757,5 + 380,0
    assert d["gross"] == 1149.0 and d["deducted"] == 11.5
    assert d["already_net"] == 202.5
    y25 = next(r for r in d["rows"] if "25 cm" in r["label"])
    assert y25["already_net_m2"] == 202.5 and y25["openings_m2"] == 0.0 and not y25["review"]
    y20 = next(r for r in d["rows"] if "20 cm" in r["label"])
    assert y20["openings_m2"] == 11.5 and y20["review"] is True


def test_iscilik_ve_sarf_kaleme_baglanir():
    b = _sec("beton")
    assert round(b["labour_hours"], 1) == 19711.6
    assert [l["key"] for l in b["labour"]] == ["beton_iscilik", "vibrator"]
    assert [e["key"] for e in b["extras"]] == ["beton_kur"]
    assert _sec("duvar")["labour_hours"] == 1477.4


def test_miktari_olmayan_kalem_listeye_girmez():
    kinds = [s["kind"] for s in headline.build(ITEMS, {})]
    assert "demir" not in kinds and "siva" not in kinds
    assert kinds == ["beton", "kalip", "duvar"]        # SECTIONS sırası korunur


def test_bos_liste_cokmeden_doner():
    assert headline.build([], {}) == []
