"""Sabit varsayımların çizimden türetilmesi: sıva / boya yüzü, koruma şapı, kazı hacmi.

Eskiden üçü de sabitti (2 yüz, 5 cm, × 1,15). Şimdi önce çizime bakılır, varsayılan son çaredir ve
kullanıldığı her yerde "VARSAYILAN" diye yazılır. Kullanıcının açıkça girdiği değer her zaman kazanır.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from app.parser.materials import scan_texts, slope_from
from app.quantity.boq import finish_quantity, wall_faces
from app.services import exterior_wall_ids, excavation_volume, protection_screed_cm


def _dw(**mats):
    return [NS(materials={k: {"evidence": [f"{k} yazısı"], "spec": str(v)} for k, v in mats.items()})]


# ------------------------------------------------------------------ sıva / boya yüzü

def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _oda():
    """10 × 8 m oda: dört dış duvar (20 cm) + ortada bir iç bölme (10 cm) + döşeme (dış hat geometriden)."""
    t = 0.2
    walls = [
        NS(id=1, etype="wall", points=_rect(0, 0, 10, t), b=t, length=10, meta={}, layer="D"),
        NS(id=2, etype="wall", points=_rect(0, 8 - t, 10, 8), b=t, length=10, meta={}, layer="D"),
        NS(id=3, etype="wall", points=_rect(0, 0, t, 8), b=t, length=8, meta={}, layer="D"),
        NS(id=4, etype="wall", points=_rect(10 - t, 0, 10, 8), b=t, length=8, meta={}, layer="D"),
        NS(id=5, etype="wall", points=_rect(4.95, t, 5.05, 8 - t), b=0.1, length=7.6, meta={}, layer="D"),
    ]
    slab = NS(id=9, etype="slab", points=_rect(0, 0, 10, 8), b=None, length=0, meta={}, layer="S")
    return walls + [slab]


def test_dis_duvarlar_dis_hattan_bulunur():
    assert exterior_wall_ids(_oda()) == {1, 2, 3, 4}


def test_dis_hatta_dik_baglanan_ic_bolme_dis_duvar_sayilmaz():
    """İç bölme dış duvara değer ama dış hat onu yalnız kalınlığı kadar keser."""
    assert 5 not in exterior_wall_ids(_oda())


def test_dis_hat_cikarilamazsa_bilinmiyor():
    tek = [NS(id=1, etype="wall", points=_rect(0, 0, 10, 0.2), b=0.2, length=10, meta={}, layer="D")]
    assert exterior_wall_ids(tek) is None       # boş küme değil: "bilinmiyor"


def test_doseme_yoksa_dis_hat_duvarlardan_cikar():
    """Yalnız duvarı olan mimari plan: dış hat duvarların kapanışından (kapı boşlukları kapanır)."""
    yalniz_duvar = [e for e in _oda() if e.etype == "wall"]
    assert exterior_wall_ids(yalniz_duvar) == {1, 2, 3, 4}


def test_tek_uzun_hatali_cizgi_dis_hatti_bozmaz():
    """Gerçek projede zemin katta yanlış okunmuş upuzun bir 'duvar' çizgisi vardı: güvenilirlik adetle ölçülür."""
    kacak = NS(id=99, etype="wall", points=_rect(30, 50, 330, 50.2), b=0.2, length=300, meta={}, layer="D")
    assert exterior_wall_ids(_oda() + [kacak]) == {1, 2, 3, 4}


def test_kati_kaplamayan_mahaller_dis_hat_sayilmaz():
    """Mahaller katın yalnız bir köşesindeyse (Yat Kulübü çatı katı) onların dış hattı bina değildir:
    sıradaki aday (duvarlar) kullanılır."""
    kose = [{"name": "DEPO", "points": _rect(0.2, 0.2, 2.5, 2.5)}]
    assert exterior_wall_ids(_oda(), kose) == {1, 2, 3, 4}


def test_yuz_sayisi_kurali():
    assert wall_faces({}, "plaster_sides", exterior=False) == 2
    assert wall_faces({}, "plaster_sides", exterior=True) == 1
    assert wall_faces({"plaster_sides": 3}, "plaster_sides", exterior=True) == 3      # kullanıcı kararı ezilmez
    assert wall_faces({"plaster_sides": 0}, "plaster_sides", exterior=False) == 0    # 0 = sıva yok


def test_siva_dis_yuzu_iki_kez_saymaz():
    walls = [{"element": {"id": 1}, "gross": 30.0}, {"element": {"id": 2}, "gross": 20.0}]
    alloc = [{"all": 0.0}, {"all": 0.0}]
    q, ek, note = finish_quantity(walls, alloc, {}, "plaster_sides", {1}, 1)
    assert q == pytest.approx(30 * 1 + 20 * 2) and ek == "" and "1 dış duvar" in note
    q, ek, _ = finish_quantity(walls, alloc, {"plaster_sides": 2}, "plaster_sides", {1}, 1)
    assert q == pytest.approx(100) and ek == " (2 yüz)"
    q, _, note = finish_quantity(walls, alloc, {}, "plaster_sides", None, 1)
    assert q == pytest.approx(100) and "çıkarılamadı" in note


def test_mimari_projede_siva_dis_duvari_tek_yuz_sayar(client, arch_dxf):
    """Uçtan uca: 10 × 8 m mimari planda dış duvarlar içeriden tek yüz sıvanır."""
    pid = client.post("/api/projects", json={"name": "Mimari", "storey_height": 3.0, "slab_thickness": 0.15}).json()["id"]
    with open(arch_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("mimari.dxf", f, "application/dxf")},
                        data={"discipline": "architectural"})
    assert r.status_code == 201, r.text
    items = {i["key"]: i for i in client.get(f"/api/projects/{pid}/quantities").json()["boq"]["items"]}
    siva = items["siva:*"]
    assert "dış duvar" in " ".join(siva["notes"])
    duvar = sum(i["quantity"] for k, i in items.items() if k.startswith("duvar:"))
    assert duvar < siva["quantity"] < 2 * duvar        # dış duvarlar tek, iç bölme iki yüz


# ------------------------------------------------------------------ koruma şapı

def test_koruma_sapi_notu_okunur():
    ev = scan_texts(["TEMEL YALITIMI ÜSTÜ KORUMA ŞAPI 7 CM"])
    assert ev["KORUMA_SAPI"]["spec"] == "7"


def test_koruma_sapi_zinciri():
    pars = {"protection_screed_cm": 5.0}
    r = protection_screed_cm(NS(params={}), _dw(KORUMA_SAPI=7), pars)
    assert r["cm"] == 7 and r["source"] == "drawing"
    assert protection_screed_cm(NS(params={"protection_screed_cm": 6}), _dw(), pars)["source"] == "param"
    r = protection_screed_cm(NS(params={}), _dw(), pars)
    assert r["cm"] == 5 and r["source"] == "default" and "VARSAYILAN" in r["detail"]


# ------------------------------------------------------------------ kazı

KARE = [_rect(0, 0, 10, 10)]


def test_kazi_calisma_payi_kenara_eklenir():
    """10 × 10 temel, 2 m derinlik, 0,60 m çalışma payı, dik kazı: 11,2² × 2."""
    r = excavation_volume(NS(params={}), _dw(), {"excavation_work_m": 0.6}, KARE, 100.0, 2.0)
    assert r["m3"] == pytest.approx(11.2 ** 2 * 2) and r["work_source"] == "default"
    assert "VARSAYILAN" in r["detail"] and "dik kazı" in r["detail"]


def test_kazi_sevi_hacmi_buyutur():
    """Şev 1:1 → taban 11,2², orta 13,2², ağız 15,2² (Simpson)."""
    r = excavation_volume(NS(params={}), _dw(KAZI_SEV=1), {"excavation_work_m": 0.6}, KARE, 100.0, 2.0)
    assert r["m3"] == pytest.approx(2 / 6 * (11.2 ** 2 + 4 * 13.2 ** 2 + 15.2 ** 2)) and r["slope"] == 1


def test_kazi_calisma_payi_cizimden():
    r = excavation_volume(NS(params={}), _dw(KAZI_CALISMA_PAYI=100), {"excavation_work_m": 0.6}, KARE, 100.0, 2.0)
    assert r["m3"] == pytest.approx(12.0 ** 2 * 2) and r["work_source"] == "drawing" and r["work_m"] == 1.0


def test_yakin_tekil_temellerin_cukurlari_birlesir():
    """1 m arayla iki 2 × 2 temel: 0,60 m pay ile çukurlar birleşir, ara iki kez sayılmaz."""
    iki = [_rect(0, 0, 2, 2), _rect(3, 0, 5, 2)]
    r = excavation_volume(NS(params={}), _dw(), {"excavation_work_m": 0.6}, iki, 8.0, 1.0)
    assert r["m3"] == pytest.approx(6.2 * 3.2)


def test_kullanici_carpani_eski_hesabi_kullanir():
    r = excavation_volume(NS(params={"excavation_margin": 1.15}), _dw(), {}, KARE, 100.0, 2.0)
    assert r["m3"] == pytest.approx(100 * 2 * 1.15) and r["work_source"] == "param"


def test_sev_yazisi():
    assert slope_from(["ŞEV 1:1,5"])[0] == 1.5
    assert slope_from(["1/1 ŞEV"])[0] == 1.0
    assert slope_from(["ŞEV AÇISI 60°"])[0] == pytest.approx(0.577, abs=1e-3)
    assert slope_from(["ÖLÇEK 1/50"])[0] is None        # şev kelimesi yoksa oran şev değildir


def test_derin_kazida_sev_sorulur(client, foundation_dxf):
    """Şev notu olmayan derin kazı dik kabul edilir ama bu kontrol listesinde söylenir."""
    pid = client.post("/api/projects", json={"name": "Kazı", "storey_height": 3.0,
                                             "params": {"excavation_depth_m": 2.5}}).json()["id"]
    with open(foundation_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("TEMEL KALIP PLANI.dxf", f, "application/dxf")})
    sy = client.get(f"/api/projects/{pid}/systems").json()
    assert any(c["code"] == "kazi_sev" for c in sy["checklist"])
    q = client.get(f"/api/projects/{pid}/quantities").json()
    kazi = next(i for i in q["boq"]["items"] if i["kind"] == "kazi")
    assert "çalışma payı" in kazi["notes"][0]
    keys = {a["key"]: a["source"] for a in q["quality"]["assumptions"]}
    assert keys.get("excavation_work_m") == "default" and "excavation_margin" not in keys
