"""Kot yazılarından kat seviyeleri ve kat yüksekliği; proje H girilmemişse kotlardan türetme."""
import pytest

from app.parser.levels import floor_levels, floor_rank, kot_from_label, parse_levels


def test_parse_levels_two_systems():
    texts = ["-4.15 (+0.00)", "+0.00 (+4.15 sıfır kotu)", "+3.80(+7.95)", "+6.50 (+10.65)", "+11.50 (+15.65)", "+13.30 (+17.45)",
             "+0.82", "+0.42", "+0.12", "+4.15", "+15.65 MEKANİK PLATFORM İZİ", "+4.00", "+1.00 KOTU", "+0.05(+4.20 peyzaj kotu)", "LOBİ 45 m2"]
    sc = parse_levels(texts)
    assert sc.offset == pytest.approx(4.15)
    assert sc.floors == [0.0, 4.15, 7.95, 10.65, 15.65]          # 0.82 / 1.00 / 4.20 / 17.45: kat aralığı altı, elenir
    assert sc.storey_heights == [4.15, 3.8, 2.7, 5.0]
    assert sc.kot is None                                          # "sıfır kotu" referans, "+1.00 KOTU" kat seviyesi değil: pafta kotu yok
    assert parse_levels(texts + ["+7.95 DÖŞEME KOTU"]).kot == pytest.approx(7.95)
    assert 8.15 not in sc.levels                                   # belirsiz sistemdeki çıplak "+4.00" sayılmaz


def test_parse_levels_single_system_and_label():
    sc = parse_levels(["±0,00", "+3,20", "+6,40", "+9,60", "+0,10", "ÇATI +12,80"], label="+3.20 KOTU KALIP PLANI")
    assert sc.floors == [0.0, 3.2, 6.4, 9.6, 12.8] and sc.storey_heights == [3.2, 3.2, 3.2, 3.2]
    assert sc.kot == pytest.approx(3.2)
    assert kot_from_label("B2 BLOK / 15.65 KOTU PLANI") == pytest.approx(15.65) and kot_from_label("ZEMİN KAT PLANI") is None
    assert floor_levels([0, 0.1, 0.5, 3.2, 3.3, 6.4]) == [0.0, 3.2, 6.4]


@pytest.mark.parametrize("label,rank", [
    ("TEMEL KALIP PLANI", -100), ("2. BODRUM KAT PLANI", -2), ("BODRUM KAT KALIP PLANI", -1), ("ZEMİN KAT PLANI", 0),
    ("ASMA KAT PLANI", 0.5), ("BİRİNCİ KAT PLANI", 1), ("3. NORMAL KAT KALIP PLANI", 3), ("ÇATI KATI PLANI", 99), ("KESİTLER", None),
])
def test_floor_rank(label, rank):
    assert floor_rank(label) == rank


def test_storey_height_from_levels_api(client, storey_dxf):
    """H = 0 girilen projede kat kalıp planlarının kotlarından kat yüksekliği türer ve H = 3,2 girilen projeyle aynı metraj çıkar."""
    def project(h):
        pid = client.post("/api/projects", json={"name": f"Kot {h}", "storey_height": h, "slab_thickness": 0.15}).json()["id"]
        for kot in ("+0.00", "+3.20"):
            with open(storey_dxf, "rb") as f:
                r = client.post(f"/api/projects/{pid}/drawings", files={"file": (f"{kot} KOTU KALIP PLANI.dxf", f, "application/dxf")},
                                data={"label": f"{kot} KOTU KALIP PLANI", "discipline": "structural"})
            assert r.status_code == 201, r.text
        return pid
    a, b = project(0), project(3.2)
    pa = client.get(f"/api/projects/{a}").json()
    assert pa["levels"]["levels"] == [0.0, 3.2] and pa["levels"]["effective"] == pytest.approx(3.2) and "kot" in pa["levels"]["source"]
    per = pa["levels"]["per_drawing"]
    assert any(v["height"] == pytest.approx(3.2) and v["source"].startswith("kot") for v in per.values())
    qa = client.get(f"/api/projects/{a}/quantities").json()["summary"]["totals"]
    qb = client.get(f"/api/projects/{b}/quantities").json()["summary"]["totals"]
    assert qa["concrete_m3"] == pytest.approx(qb["concrete_m3"], rel=1e-6) and qa["formwork_m2"] == pytest.approx(qb["formwork_m2"], rel=1e-6)
