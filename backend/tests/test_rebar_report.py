"""Demir raporu: "toplamda kaç ton, hangi çaptan kaç kilo" — üç kaynağın (metraj / oran / fire) ayrı durması."""
from app.quantity import rebar_report
from app.quantity.boq import BoqItem


def _it(kind, group, label, qty, unit="kg", **detail):
    """detail'e `rebar_source="oran"` verilirse kalem oran tahmini sayılır (bkz. rebar_report._bucket)."""
    return BoqItem(key=f"{kind}:{group}", kind=kind, group=group, label=label, unit=unit,
                   quantity=qty, discipline="structural", detail=detail)


# A4-A5'ten Ø12: tablodan 367.261 kg, perde+parapet oranından 1.467 kg, %3 fire 6.419 kg
ITEMS = [
    _it("demir", "o12", "Demir Ø12", 367261.2),
    _it("demir", "shear_wall:o12", "Demir - Perde (oranla) Ø12", 871.0, rebar_source="oran"),
    _it("demir", "parapet:o12", "Demir - Parapet (oranla) Ø12", 596.0, rebar_source="oran"),
    _it("demir", "fire:o12", "Demir fire (kesim / artık, %3) Ø12", 6418.8),
    _it("demir", "o20", "Demir Ø20", 595492.7),
    _it("demir", "fire:o20", "Demir fire (kesim / artık, %3) Ø20", 11620.1),
    _it("demir_hazirlik", "*", "Demir düzeltme - kesme - bükme (hazırlık)", 18755.3, "saat"),
    _it("demir_montaj", "*", "Demir yerleştirme - bağlama (montaj)", 35934.9, "saat"),
    _it("demir_tasima", "*", "Demir taşıma - istifleme - kata dağıtım", 10032.9, "saat"),
    _it("bag_teli", "*", "Bağ teli", 17282.3),
    _it("sehpa_demiri", "o12", "Sehpa / poz demiri Ø12", 9379.0),
    _it("sehpa_demiri", "o20", "Sehpa / poz demiri Ø20", 15244.0),
    _it("beton", "column", "Beton - Kolon", 1370.1, "m³"),        # demir dışı kalem rapora girmemeli
]
SUMMARY = {"rebar_by_dia": [
    {"dia_mm": 12, "weight_kg": 367261.2, "length_m": 413596.9,
     "targets": {"column": 256223.9, "slab": 64021.7}, "sources": {"tablo": 320245.6, "poz": 47015.6}},
    {"dia_mm": 20, "weight_kg": 595492.7, "length_m": 241481.2,
     "targets": {"foundation": 489599.3}, "sources": {"tablo": 495633.4, "poz": 99859.3}},
]}


def test_cap_bazinda_uc_kaynak_ayri_durur():
    """Sipariş = metraj + oranla tahmin + fire; üçü ayrı sütunda kalır ki hangisinin kanıtı olduğu görülsün."""
    r = rebar_report.build(ITEMS, SUMMARY)
    o12 = next(x for x in r["rows"] if x["dia_mm"] == 12)
    assert o12["metraj_kg"] == 367261.2
    assert round(o12["ratio_kg"], 1) == 1467.0          # perde 871 + parapet 596
    assert o12["fire_kg"] == 6418.8
    assert round(o12["order_kg"], 1) == 375147.0
    assert o12["length_m"] == 413596.9
    assert o12["targets"] == {"Kolon": 256223.9, "Döşeme": 64021.7}
    assert o12["sources"] == {"donatı tablosu": 320245.6, "poz yazıları": 47015.6}


def test_toplam_kalemlerin_toplamina_esit():
    r = rebar_report.build(ITEMS, SUMMARY)
    demir = sum(i.quantity for i in ITEMS if i.kind == "demir")
    assert round(r["totals"]["order_kg"], 1) == round(demir, 1)
    assert round(r["totals"]["metraj_kg"] + r["totals"]["ratio_kg"] + r["totals"]["fire_kg"], 1) == round(demir, 1)


def test_capa_bolunemeyen_demir_gizlenmez():
    """Çizimde donatı yazısı yoksa oran demiri çapa bölünemez; toplama girer ama hangi çaptan sipariş
    verileceği bilinmez — bu bilgi kaybolmamalı."""
    items = ITEMS + [_it("demir", "shear_wall", "Demir - Perde (oranla)", 5000.0, rebar_source="oran")]
    r = rebar_report.build(items, SUMMARY)
    assert r["unsized"] is not None
    assert r["unsized"]["ratio_kg"] == 5000.0
    assert "Demir - Perde (oranla)" in r["unsized"]["groups"]
    assert round(r["totals"]["order_kg"], 1) == round(sum(i.quantity for i in items if i.kind == "demir"), 1)
    assert rebar_report.build(ITEMS, SUMMARY)["unsized"] is None


def test_iscilik_ve_sarf_toplanir():
    """Sarf kalemleri çapa bölünmüş gelebilir (sehpa demiri Ø başına bir satır); türe göre tek satır olur."""
    r = rebar_report.build(ITEMS, SUMMARY)
    assert round(r["labour_hours"], 1) == 64723.1
    assert [l["key"] for l in r["labour"]] == ["demir_hazirlik", "demir_tasima", "demir_montaj"]
    sehpa = next(e for e in r["extras"] if e["key"] == "sehpa_demiri")
    assert sehpa["quantity"] == 24623.0 and sehpa["unit"] == "kg"


def test_demir_disi_kalem_rapora_girmez():
    r = rebar_report.build(ITEMS, SUMMARY)
    assert all(x["dia_mm"] in (12, 20) for x in r["rows"])
    assert round(r["totals"]["order_kg"], 1) != 1370.1


def test_bos_liste_cokmeden_doner():
    r = rebar_report.build([], {})
    assert r["rows"] == [] and r["totals"]["order_kg"] == 0 and r["unsized"] is None
