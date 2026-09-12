"""Boşluk–duvar ilişkisi: düşülecek mi, yoksa çizimde zaten kesilmiş mi?

Asıl risk çift düşüm. B2 blokta 93 boşluğun 86'sı duvar parçaları arasındaki açıklığa düşüyor (duvar
kesilerek çizilmiş); hepsini körlemesine düşmek duvar metrajını ~%17 eksik gösteriyordu.
"""
from app.quantity.openings import allocate_openings, geometry


def _el(points, **kw):
    return {"points": points, "id": kw.pop("id", 1), "name": kw.pop("name", "P1"), **kw}


def _deductible(area):        # ÇŞB 15.225: 0,10 m² ve üstü boşluk düşülür
    return area >= 0.10


def test_duvarin_ustundeki_bosluk_dusulur():
    """Kesiksiz duvar: kapı bloğu duvar çizgisinin üstünde (mesafe 0) — alan brüttür, düşülür."""
    duvar = [{"element": _el([(0, 0), (10, 0)], b=0.2, id=10), "gross": 30.0, "key": "ytong:20"}]
    kapi = [{"element": _el([(2, 0), (2.9, 0), (2.9, 0), (2, 0)], id=1, name="K1"),
             "width": 0.9, "height": 2.1, "count": 1}]
    alloc, issues = allocate_openings(duvar, kapi, _deductible)
    assert round(alloc[0]["deducted"], 3) == 1.89
    assert alloc[0]["already_net"] == 0.0
    assert [i["reason"] for i in issues] == []


def test_duvar_parcalari_arasindaki_bosluk_tekrar_dusulmez():
    """Duvar boşlukta kesilmiş: iki parça arasındaki açıklık zaten duvar değil. Tekrar düşülürse eksik çıkar."""
    duvar = [{"element": _el([(0, 0), (4.3, 0)], b=0.25, id=10), "gross": 12.9, "key": "ytong:25"},
             {"element": _el([(5.7, 0), (10, 0)], b=0.25, id=11), "gross": 12.9, "key": "ytong:25"}]
    # pencere işareti açıklığın ortasında, duvar ekseninden 0,5 m ötede (etiket kaydırması)
    pencere = [{"element": _el([(4.7, -0.5), (5.3, -0.5), (5.3, -0.1), (4.7, -0.1)], id=1, name="EMP1"),
                "width": 1.4, "height": 1.9, "count": 1}]
    alloc, issues = allocate_openings(duvar, pencere, _deductible)
    assert sum(a["deducted"] for a in alloc) == 0.0
    assert round(sum(a["already_net"] for a in alloc), 2) == 2.66
    assert [i["reason"] for i in issues] == ["already_net"]
    assert "zaten kesilerek çizilmiş" in issues[0]["message"]


def test_tolerans_duvar_kalinligindan_turer():
    """Sabit mesafe her ölçekte yanlıştır: 50 cm duvarın içindeki işaret duvarın üstündedir, 10 cm duvarda değil."""
    kalin = [{"element": _el([(0, 0), (10, 0)], b=0.5, id=10), "gross": 30.0, "key": "a"}]
    ince = [{"element": _el([(0, 0), (10, 0)], b=0.10, id=10), "gross": 30.0, "key": "a"}]
    isaret = [{"element": _el([(2, 0.2), (2.9, 0.2), (2.9, 0.2), (2, 0.2)], id=1), "width": 0.9, "height": 2.1, "count": 1}]
    assert allocate_openings(kalin, isaret, _deductible)[0][0]["deducted"] > 0      # 0,2 ≤ 0,5/2 + 0,05
    assert allocate_openings(ince, isaret, _deductible)[0][0]["deducted"] == 0.0    # 0,2 > 0,10/2 + 0,05


def test_yakininda_hic_duvar_olmayan_bosluk_uyari_verir():
    duvar = [{"element": _el([(0, 0), (10, 0)], b=0.2, id=10), "gross": 30.0, "key": "a"}]
    uzak = [{"element": _el([(100, 100), (100.9, 100)], id=1, name="K9"), "width": 0.9, "height": 2.1, "count": 1}]
    alloc, issues = allocate_openings(duvar, uzak, _deductible)
    assert sum(a["deducted"] + a["already_net"] for a in alloc) == 0.0
    assert issues and issues[0]["reason"] == "unmatched"


def test_kucuk_bosluk_duvardan_dusulmez_sivadan_dusulur():
    """ÇŞB 15.225: 0,10 m² altı boşluk duvardan düşülmez; sıva / boya için hepsi ("all") sayılır."""
    duvar = [{"element": _el([(0, 0), (10, 0)], b=0.2, id=10), "gross": 30.0, "key": "a"}]
    kucuk = [{"element": _el([(2, 0), (2.2, 0), (2.2, 0), (2, 0)], id=1), "width": 0.2, "height": 0.3, "count": 1}]
    alloc, _ = allocate_openings(duvar, kucuk, _deductible)
    assert alloc[0]["deducted"] == 0.0
    assert round(alloc[0]["all"], 3) == 0.06


def test_cizgiye_cokmus_blok_siniri_konum_tasir():
    """Kapı bloğunun sınırı tek bir yatay çizgiye çökebilir. None dönerse boşluk "duvar yok" sayılır ve
    hiçbir duvardan düşülmez — KSF duvarlarında 15,75 m² boşluk böyle kaybolmuştu."""
    g = geometry(_el([(2.0, 0.0), (2.9, 0.0), (2.9, 0.0), (2.0, 0.0)]))
    assert g is not None and g.geom_type == "LineString"
    assert geometry(_el([])) is None


def test_olcusu_eksik_bosluk_bildirilir():
    duvar = [{"element": _el([(0, 0), (10, 0)], b=0.2, id=10), "gross": 30.0, "key": "a"}]
    bos = [{"element": _el([(2, 0), (2.9, 0)], id=1, name="K?"), "width": 0.0, "height": 2.1, "count": 1}]
    alloc, issues = allocate_openings(duvar, bos, _deductible)
    assert alloc[0]["deducted"] == 0.0 and issues[0]["reason"] == "missing_dimensions"
