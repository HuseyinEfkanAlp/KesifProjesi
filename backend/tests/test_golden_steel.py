"""Altın çelik: çelik plan paftalarından profil bazında kg (tests/fixtures/golden_steel.py).

26 Eyl 2026 (Yat Kulübü aynalı tonoz ve çatılar çelik projeleri üzerine) eklendi:
  - çelik planı betonarme sanılıyordu (kolon / kiriş / perde betonu çıkıyordu) → çelik disiplini (detectors/steel.py)
  - kolon planda kesittir: boyu kotlardan (yerleşim ±0.00 → kiriş planı +4.50), iki paftada görünse de bir kez sayılır
"""
import pytest

from tests.fixtures.golden_steel import golden_truth_steel, make_golden_steel

_SONUC: dict = {}


@pytest.fixture
def celik(client, tmp_path_factory):
    if not _SONUC:
        from app.jobs import run_pending
        path = make_golden_steel(tmp_path_factory.mktemp("altin_celik") / "altin_celik.dxf")
        pid = client.post("/api/projects", json={"name": "Altın çelik"}).json()["id"]
        with open(path, "rb") as f:
            r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("altin_celik.dxf", f, "application/dxf")},
                            data={"background": "true"})
        assert r.status_code == 202, r.text
        run_pending()
        q = client.get(f"/api/projects/{pid}/quantities").json()
        _SONUC.update(items=q["boq"]["items"], truth=golden_truth_steel(),
                      drawings=client.get(f"/api/projects/{pid}/drawings").json(),
                      systems=client.get(f"/api/projects/{pid}/systems").json())
    return _SONUC


def _ana(c):
    return [i for i in c["items"] if not (i.get("detail") or {}).get("recipe")]


def test_paftalar_celik_plani(celik):
    tipler = sorted(d["plan_type"] for d in celik["drawings"])
    assert tipler == ["sta_celik", "sta_celik"], tipler


def test_betonarme_yok(celik):
    kinds = {i["kind"] for i in _ana(celik)}
    assert not kinds & {"beton", "kalip", "demir"}, kinds


def test_profil_bazinda_kg(celik):
    t = celik["truth"]
    satir = {i["detail"]["profile"]: i for i in _ana(celik) if i["kind"] == "celik_konstruksiyon"}
    assert set(satir) == set(t["kg"]), sorted(satir)
    for prof, kg in t["kg"].items():
        assert satir[prof]["quantity"] == pytest.approx(kg, rel=0.01), prof
        assert satir[prof]["detail"]["length_m"] == pytest.approx(t["boy"][prof], rel=0.01), prof
    assert sum(i["quantity"] for i in satir.values()) == pytest.approx(t["toplam"], rel=0.005)


def test_kolon_bir_kez_ve_kottan(celik):
    kolon = next(i for i in _ana(celik) if i["kind"] == "celik_konstruksiyon" and i["detail"]["profile"] == "HEB200")
    assert kolon["count"] == celik["truth"]["kolon_adet"]
    assert any("4.50" in n for n in kolon["notes"]), kolon["notes"]
    assert not [i for i in _ana(celik) if i["kind"] in ("celik_kolon_boysuz", "celik_profilsiz")]


def test_iscilik_ve_sarf_receteden(celik):
    kinds = {i["kind"] for i in celik["items"] if (i.get("detail") or {}).get("recipe")}
    assert {"celik_montaj", "kaynak", "antipas"} <= kinds, kinds


def test_kontrol_listesi(celik):
    kodlar = {c["code"] for c in celik["systems"]["checklist"]}
    assert "celik_kapsam" in kodlar
    assert not kodlar & {"celik_kolon_boyu", "celik_profilsiz", "celik_kolon_egimli"}, kodlar
