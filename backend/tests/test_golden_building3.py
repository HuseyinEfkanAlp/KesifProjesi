"""Altın bina 3: 8 katlı karma yapı, statik ve mimari ayrı dosyalarda (tests/fixtures/golden_building3.py).

25 Eyl 2026'da ilk koşuda bulunan ve düzeltilen hatalar:
  - kapısız otopark MİMARİ planı (çevre perdesi + kolon izi) kalıp planı sanılıyordu: bodrum kolonu ve perdesi iki kez
  - alan çizgisi olmayan dükkân katında ortak alan "çizimde yok" sanılıyordu: bölgeler ölçülen mahallerden
  - kaba teslim projede konut katlarının tavanı kat oturumundan (duvarlar dahil, +%14)
  - kapı kanatları koridoru enine köprülüyor, koridor parçalanıyordu: açıklık blok doğrultusunda kapanır
  - koridor ucundaki dış duvarın koridora bakan yüzü kayboluyordu: kaba teslim katta ortak mahal çevresi
  - "1.-5. NORMAL KAT" planı beş katın sahibi sayılmıyor, engelleyici "3 kat eksik" uyarısı çıkıyordu
"""
import pytest

from tests.fixtures.golden_building3 import golden_truth3, make_golden_building3

_SONUC: dict = {}


@pytest.fixture
def bina(client, tmp_path_factory):
    if not _SONUC:
        from app.jobs import run_pending
        statik, mimari = make_golden_building3(tmp_path_factory.mktemp("altin3"))
        pid = client.post("/api/projects", json={"name": "Altın bina 3"}).json()["id"]
        for path in (statik, mimari):
            with open(path, "rb") as f:
                r = client.post(f"/api/projects/{pid}/drawings", files={"file": (path.name, f, "application/dxf")},
                                data={"background": "true"})
            assert r.status_code == 202, r.text
            run_pending()
        client.patch(f"/api/projects/{pid}", json={"params": {"tenant_shell": 1}}).raise_for_status()
        q = client.get(f"/api/projects/{pid}/quantities").json()
        _SONUC.update(items=[i for i in q["boq"]["items"] if not (i.get("detail") or {}).get("recipe")],
                      quality=q["quality"], truth=golden_truth3(),
                      drawings=client.get(f"/api/projects/{pid}/drawings").json())
    return _SONUC


def _q(b, kind, group=None, pre=None):
    return sum(i["quantity"] for i in b["items"] if i["kind"] == kind and (group is None or i["group"] == group)
               and (pre is None or str(i["group"]).startswith(pre)))


def test_paftalar_ve_katlar(bina):
    tip = {d["label"]: d["plan_type"] for d in bina["drawings"]}
    assert tip["2. BODRUM KAT PLANI"] == "mim_kat_plani" and tip["1. BODRUM KAT PLANI"] == "mim_kat_plani"
    sc = bina["quality"]["storey_count"]
    assert sc["total"] == 8 and sc["unowned"] == []


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
    assert _q(bina, "kapi") == t["kapi"] and _q(bina, "pencere") == t["pencere"]


def test_ince_isler_dukkan_kaba_teslim(bina):
    t = bina["truth"]
    assert _q(bina, "siva") == pytest.approx(t["siva"], rel=0.005)
    assert _q(bina, "tavan_siva_boya") == pytest.approx(t["tavan"], rel=0.005)
    assert _q(bina, "sap") == pytest.approx(t["tavan"] * 0.05, rel=0.005)
    assert _q(bina, "doseme_kaplama") == pytest.approx(t["kuru"], rel=0.005)
    assert _q(bina, "seramik_zemin") == pytest.approx(t["islak"], rel=0.005)
    assert _q(bina, "seramik_duvar") == pytest.approx(t["islak_cevre"] * 2.2 - 20 * 0.8 * 2.1, rel=0.005)
