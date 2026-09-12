"""Ekip büyüklüğü ve süre: "21.146 adam-gün" gibi bir sayı kullanıcıya hiçbir şey söylemez.

Ayrım şu: **bir ekipteki kişi sayısı bir normdur** (kalıpta 2 marangoz + 1 amele), **kaç ekibin aynı anda
çalışacağı ise saha kararıdır**. Program normu verir, ekip sayısını kullanıcı söyler; ikisi çarpılır.
Süreyle birlikte "bu süre için sahada ortalama kaç kişi gerekir" da yazılır — gerçekçiliği o gösterir.
"""
import pytest

from app.standard.rules import CREW_DEFAULT, CREW_SIZE, crew_size


def test_bilinen_islerin_ekip_normu_vardir():
    for kind in ("demir_montaj", "kalip_kurma", "siva_iscilik", "beton_iscilik"):
        assert crew_size(kind) >= 2.0, kind


def test_taninmayan_is_usta_yardimci_varsayar():
    assert crew_size("bilinmeyen_is") == CREW_DEFAULT == 2.0


def test_ekip_normlari_makul_aralikta():
    """Tek kişilik ekip yoktur; 10 kişilik tek ekip de yoktur (o birden çok ekiptir)."""
    for kind, n in CREW_SIZE.items():
        assert 2.0 <= n <= 8.0, f"{kind}: {n}"


def test_ekip_sayisi_sureyi_boler(client, storey_dxf):
    """Eşzamanlı ekip sayısı iki katına çıkınca takvim süresi yarıya iner, adam-saat değişmez."""
    pid = client.post("/api/projects", json={"name": "Süre", "storey_height": 3.0}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("KALIP PLANI.dxf", f, "application/dxf")})

    client.patch(f"/api/projects/{pid}", json={"params": {"crew_count": 1}})
    bir = client.get(f"/api/projects/{pid}/cost").json()["cost"]["duration"]
    client.patch(f"/api/projects/{pid}", json={"params": {"crew_count": 2}})
    iki = client.get(f"/api/projects/{pid}/cost").json()["cost"]["duration"]

    assert iki["total_hours"] == pytest.approx(bir["total_hours"])      # iş miktarı değişmez
    assert iki["parallel_days"] == pytest.approx(bir["parallel_days"] / 2, rel=0.02)
    assert iki["implied_headcount"] == pytest.approx(bir["implied_headcount"] * 2, rel=0.02)


def test_gereken_kisi_sayisi_sureden_turer(client, storey_dxf):
    """implied_headcount = toplam saat / (takvim günü × günlük saat): kullanıcı gerçekçiliği buradan görür."""
    pid = client.post("/api/projects", json={"name": "Kişi", "storey_height": 3.0}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("KALIP PLANI.dxf", f, "application/dxf")})
    d = client.get(f"/api/projects/{pid}/cost").json()["cost"]["duration"]
    assert d["parallel_days"] > 0
    assert d["implied_headcount"] == pytest.approx(
        d["total_hours"] / (d["parallel_days"] * d["hours_per_day"]), rel=0.02)


def test_norm_ekip_kullanici_girisi_sayilmaz(client, storey_dxf):
    """Norm bir program varsayılanıdır; "eksik" değildir ama kullanıcı girişi de değildir — ayrı listelenir."""
    pid = client.post("/api/projects", json={"name": "Norm", "storey_height": 3.0}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("KALIP PLANI.dxf", f, "application/dxf")})
    d = client.get(f"/api/projects/{pid}/cost").json()["cost"]["duration"]
    assert d["missing_crew"] == []
    assert d["norm_crew"], "ekip normundan gelen kalem yok"


def test_kullanicinin_girdigi_ekip_normu_ezer(client, storey_dxf):
    pid = client.post("/api/projects", json={"name": "Elle", "storey_height": 3.0}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("KALIP PLANI.dxf", f, "application/dxf")})
    prices = client.get(f"/api/projects/{pid}/prices").json()
    hedef = next((p for p in prices if p["key"] == "kalip_kurma:*"), None)
    if hedef is None:
        pytest.skip("bu sentetik planda kalıp kurma kalemi yok")
    client.put(f"/api/projects/{pid}/prices", json=[{**hedef, "crew_size": 12}])
    lines = client.get(f"/api/projects/{pid}/cost").json()["cost"]["lines"]
    satir = next(l for l in lines if l["key"] == "kalip_kurma:*")
    assert satir["crew_size"] == pytest.approx(12.0)
    assert satir["crew_source"] == "özel"
