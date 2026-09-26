"""Altın bina 4: merdivenli ve teras çatılı 3 katlı konut (tests/fixtures/golden_building4.py).

26 Eyl 2026'da ilk koşuda bulunan ve düzeltilen:
  - merdiven hiç ölçülmüyordu (merdiven katmanı yok sayılıyordu): beton, kalıp, demir, basamak kaplaması, korkuluk,
    merdiven altı sıva-boya yoktu → detectors/stairs.py + engine.stair_geometry
  - merdiven holünün şap / kaplaması ve (üstünde kat varsa) tavanı merdivenin kapladığı yer kadar fazlaydı
  - parapet etiketi bir kez yazılınca öteki kenarlar 15 cm sayılıyordu (parapet betonu −%61)
  - teras çatı dış hattan (parapet dahil) ölçülüyordu (+%7,5): parapetin iç çizgisi esas
"""
import pytest

from tests.fixtures.golden_building4 import golden_truth4, make_golden_building4

_SONUC: dict = {}


@pytest.fixture
def bina(client, tmp_path_factory):
    if not _SONUC:
        from app.jobs import run_pending
        path = make_golden_building4(tmp_path_factory.mktemp("altin4") / "altin4.dxf")
        pid = client.post("/api/projects", json={"name": "Altın bina 4"}).json()["id"]
        with open(path, "rb") as f:
            r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("altin4.dxf", f, "application/dxf")},
                            data={"background": "true"})
        assert r.status_code == 202, r.text
        run_pending()
        q = client.get(f"/api/projects/{pid}/quantities").json()
        _SONUC.update(items=[i for i in q["boq"]["items"] if not (i.get("detail") or {}).get("recipe")],
                      quality=q["quality"], truth=golden_truth4())
    return _SONUC


def _q(b, kind, group=None, pre=None):
    return sum(i["quantity"] for i in b["items"] if i["kind"] == kind and (group is None or i["group"] == group)
               and (pre is None or str(i["group"]).startswith(pre)))


def test_betonarme_ve_merdiven(bina):
    t = bina["truth"]
    for kind, grp, key in (("beton", "column", "kolon"), ("beton", "beam", "kiris"), ("beton", "slab", "doseme"),
                           ("beton", "stair", "merdiven_beton"), ("kalip", "stair", "merdiven_kalip"),
                           ("beton", "parapet", "parapet_beton"), ("kalip", "parapet", "parapet_kalip")):
        assert _q(bina, kind, grp) == pytest.approx(t[key], rel=0.005), key
    assert _q(bina, "demir", "stair") == pytest.approx(t["merdiven_beton"] * 120.0, rel=0.005)


def test_merdiven_ince_isleri(bina):
    t = bina["truth"]
    assert _q(bina, "merdiven_kaplama") == pytest.approx(t["merdiven_kaplama"], rel=0.005)
    assert _q(bina, "korekuyu") == pytest.approx(t["korkuluk"], rel=0.005)
    assert _q(bina, "tavan_siva_boya") == pytest.approx(t["tavan"], rel=0.005)
    assert _q(bina, "doseme_kaplama") == pytest.approx(t["kuru"], rel=0.005)


def test_teras_cati_parapet_ici(bina):
    assert _q(bina, "teras_cati") == pytest.approx(bina["truth"]["cati"], rel=0.005)
