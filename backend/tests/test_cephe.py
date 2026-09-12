"""Cephenin yönlere ayrılması: ön / arka / sağ / sol cephe ayrı ayrı ölçülebilmeli.

Dış hat çokgeninin her kenarı, dışa bakan normaline göre dört yönden birine yazılır. Dik kenarlı bir binada
dört yönün toplamı **dış çevreye eşittir** — bu, hesabın kendi sağlamasıdır.
"""
from types import SimpleNamespace as Obj

import pytest

from app.services import FACADE_SIDES, footprint_sides, building_footprint, footprint_polygon


def el(points, etype="slab"):
    return Obj(etype=etype, points=points, b=None, h=None)


def kutu(x0, y0, x1, y1, etype="slab"):
    return el([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], etype)


def parcali_kutu(x0, y0, x1, y1, n=4, etype="slab"):
    """Aynı dikdörtgeni n parçaya böler: dedektör çıktısı tek çokgen değil, birleşmesi gerekir."""
    w = (x1 - x0) / n
    return [kutu(x0 + i * w, y0, x0 + (i + 1) * w, y1, etype) for i in range(n)]


def test_dikdortgen_binada_kenarlar_cevreyi_verir():
    """40 × 20 m bina: sağ/sol 20'şer, üst/alt 40'ar; toplam 120 m = çevre."""
    sides = footprint_sides(parcali_kutu(0, 0, 40, 20))
    assert sides["+X"] == pytest.approx(20, abs=0.6)
    assert sides["-X"] == pytest.approx(20, abs=0.6)
    assert sides["+Y"] == pytest.approx(40, abs=0.6)
    assert sides["-Y"] == pytest.approx(40, abs=0.6)
    toplam = sum(sides[k] for k in FACADE_SIDES)
    cevre = building_footprint(parcali_kutu(0, 0, 40, 20))[1]
    assert toplam == pytest.approx(cevre, rel=0.03)


def test_karsilikli_cepheler_esittir():
    """Kapalı bir çokgende +X ile −X izdüşümleri zorunlu olarak eşittir; eşit değilse dış hat kapanmamıştır."""
    sides = footprint_sides(parcali_kutu(0, 0, 60, 24))
    assert sides["+X"] == pytest.approx(sides["-X"], rel=1e-6)
    assert sides["+Y"] == pytest.approx(sides["-Y"], rel=1e-6)


def test_cikintili_bina_cikintiyi_de_sayar():
    """L şeklinde binada girinti-çıkıntı yüzeyleri de cephedir; izdüşüm toplamı yine çevreye eşittir."""
    els = parcali_kutu(0, 0, 40, 20) + parcali_kutu(40, 0, 60, 8)
    sides = footprint_sides(els)
    cevre = building_footprint(els)[1]
    assert sum(sides[k] for k in FACADE_SIDES) == pytest.approx(cevre, rel=0.05)
    assert sides["+X"] > 19                      # sağ cephe hem 20 m'lik hem 8 m'lik kısımdan görünür


def test_egik_cephe_iki_yone_paylastirilir_ve_pay_bildirilir():
    """45°'lik bir cephe hem +X hem +Y görünüşünde yer alır; izdüşümler toplamı kenar boyunu aşar."""
    # aynı eğik çokgen üç kez: birleşim yine eğik hat (fonksiyon en az üç çokgen ister)
    egik = [(0, 0), (30, 0), (30, 10), (20, 20), (0, 20)]
    sides = footprint_sides([el(egik), el(egik), el(egik)])
    assert sides["+X"] > 0 and sides["+Y"] > 0
    assert sides["egik_fazla"] > 0               # iki yönde birden sayılan pay bildirilir
    kenar = ((30 - 20) ** 2 + (20 - 10) ** 2) ** 0.5          # eğik kenarın gerçek boyu
    assert sides["egik_fazla"] == pytest.approx(kenar * (2 ** 0.5 - 1), abs=0.5)


def test_dik_kenarli_binada_egik_fazla_sifirdir():
    assert footprint_sides(parcali_kutu(0, 0, 40, 20))["egik_fazla"] == 0.0


def test_alan_cevre_ve_kenarlar_ayni_cokgenden_gelir():
    """İki ayrı yerde ayrı kuralla hesaplanırsa kenar toplamı çevreyi tutmaz (ölçüldü: 40 m / 163 m)."""
    els = parcali_kutu(0, 0, 40, 20, etype="wall")
    g = footprint_polygon(els)
    assert g is not None
    assert building_footprint(els)[1] == pytest.approx(g.exterior.length, rel=1e-9)
    assert sum(footprint_sides(els)[k] for k in FACADE_SIDES) == pytest.approx(g.exterior.length, rel=0.03)


def test_gecersiz_girdide_bos_doner():
    assert footprint_sides([]) == {}
    assert footprint_sides([kutu(0, 0, 1, 1)]) == {}          # 3'ten az çokgen: bina oturumu sayılmaz


# ---- cephe alanının yönlere dağılımı ve sistem kalemleri ----

class _FakeSession:
    def exec(self, *a, **k):
        return []


def _fa(gross=1000.0, glass=200.0, sides=None):
    """facade_area çıktısının yön dağılımını taklit eder (gerçek hesabı yukarıdaki testler doğruluyor)."""
    sides = sides or {"+X": 200.0, "-X": 200.0, "+Y": 300.0, "-Y": 300.0}
    net_sides = {k: round(v - glass * v / gross, 2) for k, v in sides.items()}
    return {"gross": gross, "glass": glass, "net": gross - glass, "source": "estimated",
            "detail": "test", "sides": sides, "sides_net": net_sides, "per_drawing": []}


def test_yon_netleri_toplami_proje_netine_esittir():
    fa = _fa()
    assert sum(fa["sides_net"].values()) == pytest.approx(fa["net"], abs=0.05)


def test_cephe_sistemi_secilince_her_yon_ayri_kalem_olur(monkeypatch):
    import app.services as sv
    from app.standard.catalog import Catalog
    monkeypatch.setattr(sv, "facade_area", lambda *a, **k: _fa())
    out = sv.facade_items(Obj(id=1, params={}), _FakeSession(), Catalog(), [], [],
                          {"facade_system": "MANTOLAMA_SISTEM"})
    sistem = [i for i in out if i.kind == "mantolama_sistem"]
    assert len(sistem) == 4                                   # dört cephe ayrı satır
    assert {i.detail["facade_side"] for i in sistem} == set(FACADE_SIDES)
    assert sum(i.quantity for i in sistem) == pytest.approx(800.0, abs=0.1)   # net = 1000 − 200
    assert any("Üstteki cephe" in i.label for i in sistem)


def test_cam_dagitimi_kabul_olarak_yazilir():
    """Hangi doğramanın hangi cephede olduğu bilinmiyorsa bu bir kabuldür; kalemin notunda geçmeli."""
    import app.services as sv
    from app.standard.catalog import Catalog
    eski = sv.facade_area
    sv.facade_area = lambda *a, **k: _fa()
    try:
        out = sv.facade_items(Obj(id=1, params={}), _FakeSession(), Catalog(), [], [],
                              {"facade_system": "MANTOLAMA_SISTEM"})
    finally:
        sv.facade_area = eski
    notlar = " ".join(n for i in out for n in i.notes)
    assert "brüt payıyla dağıtıldı" in notlar and "bilinmiyor" in notlar


def test_yon_ayrimi_cikmazsa_tek_satir_kalir():
    """Dış hat okunamadıysa cephe tek kalem olarak verilir; uydurma yön üretilmez."""
    import app.services as sv
    from app.standard.catalog import Catalog
    eski = sv.facade_area
    sv.facade_area = lambda *a, **k: {**_fa(), "sides": {k: 0.0 for k in FACADE_SIDES},
                                      "sides_net": {k: 0.0 for k in FACADE_SIDES}}
    try:
        out = sv.facade_items(Obj(id=1, params={}), _FakeSession(), Catalog(), [], [],
                              {"facade_system": "MANTOLAMA_SISTEM"})
    finally:
        sv.facade_area = eski
    sistem = [i for i in out if i.kind == "mantolama_sistem"]
    assert len(sistem) == 1 and sistem[0].group == "*"


def test_sistem_secilmemisse_kesfe_kalem_eklenmez():
    import app.services as sv
    from app.standard.catalog import Catalog
    assert sv.facade_items(Obj(id=1, params={}), _FakeSession(), Catalog(), [], [], {"facade_system": ""}) == []
