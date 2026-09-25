"""Altın bina 2: ilkinden bilerek farklı çizim alışkanlıklarıyla 4 katlı apartman (tests/fixtures/golden_building2.py).

25 Eyl 2026'da ilk koşuda bulunan ve düzeltilen hatalar (her biri aşağıda kilitli):
  - tek poligonlu radye temel planı "boş çerçeve" sanılıp atlanıyordu (radye 123 m³ kayıp)
  - çevresinde perde olan bodrum MİMARİ planı kalıp planı sanılıyordu (kolon %25, perde %93 fazla)
  - kalıp planının kotu katın tavanıdır; bodrum 3,20 yerine 3,00 m ölçülüyordu
  - uçları kapatılmış duvarlar kolon mahal sınırına girmediği için hiçbir oda kapanmıyordu
  - iki eş dairenin aynı adlı / alanlı odaları teke iniyordu (tavan, şap, kaplama −%63)
  - konut projesinde bodrum servis katı (depo, kazan dairesi) ince işlere girmiyordu; "KAZAN DAİRESİ" daire sanılıyordu
  - tek "baskın" kiriş yüksekliği: 60'lık çevre kirişi altındaki duvar 50'lik sanılıyordu (her duvar kendi kirişinden)
  - tip kat planı "1.-2. NORMAL KAT" 2. kattan başlıyor sanılıyordu
  - birleşen duvar dik duvarın içinden geçip kesişimi iki kez sayıyordu
  - sıva duvar yüzünden: odaya taşan / serbest kolon yüzleri atlanıyordu (−%7,6) → mahal çevresinden
  - ortadan yerleşmiş kapı bloğunun kutusu kurulamıyordu
"""
import pytest

from tests.fixtures.golden_building2 import golden_truth2, make_golden_building2

_SONUC: dict = {}


@pytest.fixture
def bina(client, tmp_path_factory):
    if not _SONUC:
        from app.jobs import run_pending
        path = make_golden_building2(tmp_path_factory.mktemp("altin2") / "altin2.dxf")
        pid = client.post("/api/projects", json={"name": "Altın bina 2"}).json()["id"]
        with open(path, "rb") as f:
            r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("altin2.dxf", f, "application/dxf")},
                            data={"background": "true"})
        assert r.status_code == 202, r.text
        run_pending()
        q = client.get(f"/api/projects/{pid}/quantities").json()
        items = [i for i in q["boq"]["items"] if not (i.get("detail") or {}).get("recipe")]
        _SONUC.update(items=items, quality=q["quality"], truth=golden_truth2(),
                      drawings=client.get(f"/api/projects/{pid}/drawings").json())
    return _SONUC


def _q(b, kind, group=None, pre=None):
    return sum(i["quantity"] for i in b["items"] if i["kind"] == kind and (group is None or i["group"] == group)
               and (pre is None or str(i["group"]).startswith(pre)))


def test_paftalar_ve_kat_sayisi(bina):
    tip = {d["label"]: d["plan_type"] for d in bina["drawings"]}
    assert tip["TEMEL KALIP PLANI"] == "sta_temel_kalip"
    assert tip["BODRUM KAT PLANI"] == "mim_kat_plani"
    assert tip["A-A KESİTİ"] == "mim_kesit"
    assert bina["quality"]["storey_count"]["total"] == 4


def test_betonarme(bina):
    t = bina["truth"]
    for kind, grp, pre, key in (("beton", "column", None, "kolon"), ("beton", "beam", None, "kiris"),
                                ("beton", "shear_wall", None, "perde"), ("beton", "slab", None, "doseme"),
                                ("beton", None, "foundation", "radye"), ("grobeton", None, None, "grobeton")):
        assert _q(bina, kind, grp, pre) == pytest.approx(t[key], rel=0.005), key


def test_duvarlar_ve_dograma(bina):
    t = bina["truth"]
    assert _q(bina, "duvar", "ytong:25") == pytest.approx(t["ytong25"], rel=0.005)
    assert _q(bina, "duvar", "ytong:20") == pytest.approx(t["ytong20"], rel=0.005)
    assert _q(bina, "duvar", "tugla:10") == pytest.approx(t["tugla10"], rel=0.005)
    assert not any(i["kind"] == "duvar" and "perde" in i["group"] for i in bina["items"])
    assert _q(bina, "kapi") == t["kapi"] and _q(bina, "pencere") == t["pencere"]


def test_ince_isler(bina):
    t = bina["truth"]
    assert _q(bina, "siva") == pytest.approx(t["siva"], rel=0.005)
    assert _q(bina, "boya") == pytest.approx(t["siva"], rel=0.005)
    assert _q(bina, "tavan_siva_boya") == pytest.approx(t["tavan"], rel=0.005)
    assert _q(bina, "sap") == pytest.approx(t["sap_alan"] * 0.05, rel=0.005)
    assert _q(bina, "doseme_kaplama") == pytest.approx(t["kuru"], rel=0.005)
    assert _q(bina, "seramik_zemin") == pytest.approx(t["islak"], rel=0.005)
    assert _q(bina, "seramik_duvar") == pytest.approx(t["islak_cevre"] * 2.2 - 6 * 0.8 * 2.1, rel=0.005)
