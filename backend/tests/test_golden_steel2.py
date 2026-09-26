"""Altın çelik 2: tek / çift çizgi elemanlar ve eğimli çatı (tests/fixtures/golden_steel2.py).

26 Eyl 2026 eklendi (kullanıcı: "2 ve 3'ü test çizimleriyle hazırla"):
  - tek çizgiyle çizilmiş aşık / çapraz ve çift çizgiyle çizilmiş kiriş hiç okunmuyordu (yalnız kapalı dikdörtgen)
  - eğimli makas / çapraz plandaki izdüşümden ölçülüyordu (gerçek boy √(plan² + Δh²))
  - Yat Kulübü +17.90 planında dikdörtgen elemanın yanındaki kısa çizgiler onun markasını çalıyordu → iki turlu eşleştirme
"""
import pytest

from tests.fixtures.golden_steel2 import golden_truth_steel2, make_golden_steel2

_SONUC: dict = {}


def _yukle(client, tmp_path_factory, ad: str, **kw) -> dict:
    if ad not in _SONUC:
        from app.jobs import run_pending
        path = make_golden_steel2(tmp_path_factory.mktemp(ad) / f"{ad}.dxf", **kw)
        pid = client.post("/api/projects", json={"name": ad}).json()["id"]
        with open(path, "rb") as f:
            r = client.post(f"/api/projects/{pid}/drawings", files={"file": (f"{ad}.dxf", f, "application/dxf")},
                            data={"background": "true"})
        assert r.status_code == 202, r.text
        run_pending()
        q = client.get(f"/api/projects/{pid}/quantities").json()
        _SONUC[ad] = {"items": [i for i in q["boq"]["items"] if not (i.get("detail") or {}).get("recipe")],
                      "checklist": client.get(f"/api/projects/{pid}/systems").json()["checklist"]}
    return _SONUC[ad]


@pytest.fixture
def kotlu(client, tmp_path_factory):
    return _yukle(client, tmp_path_factory, "celik2_kot", kot=True, egim_yazisi=False)


@pytest.fixture
def yazili(client, tmp_path_factory):
    return _yukle(client, tmp_path_factory, "celik2_yazi", kot=False, egim_yazisi=True)


@pytest.fixture
def egimsiz(client, tmp_path_factory):
    return _yukle(client, tmp_path_factory, "celik2_yok", kot=False, egim_yazisi=False)


def _satir(c) -> dict:
    return {i["detail"]["profile"]: i for i in c["items"] if i["kind"] == "celik_konstruksiyon"}


def _dogrula(c, truth):
    s = _satir(c)
    assert set(s) == set(truth["kg"]), sorted(s)
    for prof in truth["kg"]:
        assert s[prof]["detail"]["length_m"] == pytest.approx(truth["boy"][prof], rel=0.01), prof
        assert s[prof]["quantity"] == pytest.approx(truth["kg"][prof], rel=0.01), prof
    assert sum(i["quantity"] for i in s.values()) == pytest.approx(truth["toplam"], rel=0.005)


def test_tek_ve_cift_cizgi_elemanlar_ve_uc_kotlari(kotlu):
    """Çift çizgi IPE200, tek çizgi aşık / çapraz, markasız aşık (tahmin), tuzaklar sayılmaz; eğim uç kotlarından."""
    _dogrula(kotlu, golden_truth_steel2(egim_bilgisi=True))
    assert _satir(kotlu)["HEB160"]["count"] == golden_truth_steel2()["kolon_adet"]
    assert not [i for i in kotlu["items"] if i["kind"] in ("celik_profilsiz", "celik_egim_yok")]


def test_egim_yazisindan(yazili):
    """Kot yok, "%50" eğim yazısı: makas tam eğimle, köşegen çapraz eğim doğrultusundaki bileşeniyle uzar."""
    _dogrula(yazili, golden_truth_steel2(egim_bilgisi=True))
    assert not [c for c in yazili["checklist"] if c["code"] == "celik_egim"]


def test_egim_bilgisi_yoksa_izdusum_ve_soru(egimsiz):
    """Eğimli çatı paftası ama kot / eğim yazısı yok: izdüşümden ölçülür ve kullanıcıya sorulur (varsayılmaz)."""
    _dogrula(egimsiz, golden_truth_steel2(egim_bilgisi=False))
    soru = [c for c in egimsiz["checklist"] if c["code"] == "celik_egim"]
    assert soru and soru[0]["level"] == "required"
