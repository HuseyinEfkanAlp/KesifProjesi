"""Dükkânlar kaba teslim (AVM): dükkân içi sıvanmaz, boyanmaz, tavanı kiracının; yalnız ortak alan ve dış cephe.

Kullanıcının kuralı (A blokları, 24 Eyl 2026): "dükkan içleri kiracı alanıdır kaba teslim edilir binanın
dükkana gelen kısımlarının sadece dış cephesi yapılır"; müteahhidin işi merdiven, lobi ve koridorlar.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from shapely.geometry import Polygon

from app.parser.zones import classify
from app.quantity.boq import finish_quantity
from app.services import shell_wall_faces, tenant_shell_on


def _r(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# ------------------------------------------------------------------ bölge türü

@pytest.mark.parametrize("pts, yazilar, tur", [
    (_r(0, 0, 25, 11), ["LOBİ", "FOTOSELLİ KAPI"], "ortak"),
    (_r(0, 0, 2.7, 6.4), ["ZEMİN KAT\n24X(30 / 16.45)"], "ortak"),          # merdiven notu
    (_r(0, 0, 43, 7.8), ["GP-1", "FOTOSELLİ KAPI"], "ortak"),                # uzun dar şerit: koridor
    (_r(0, 0, 9, 32.6), ["GP-1", "GP-3"], "dukkan"),                         # büyük adsız: bağımsız bölüm
    (_r(0, 0, 7.5, 24), ["DERİMOD"], "dukkan"),
    (_r(0, 0, 2, 2.5), ["ÇÖP TOPLAMA ODASI"], "teknik"),
    (_r(0, 0, 3, 5), [], "belirsiz"),
])
def test_bolge_turu(pts, yazilar, tur):
    kind, why = classify(Polygon(pts), yazilar)
    assert kind == tur and why and "\n" not in why


# ------------------------------------------------------------------ duvar yüzleri

def _w(i, pts, b=0.2):
    return NS(id=i, points=pts, b=b, etype="wall")


def test_kaba_teslimde_dukkana_bakan_yuz_sivanmaz():
    """Koridor 0..20 × 0..3; üstünde dükkân. Koridorla dükkân arasındaki duvar 1 yüz (koridor tarafı),
    koridorun içindeki bölme 2 yüz, dükkânın içindeki duvar 0, dış duvar 0."""
    zones = [{"kind": "ortak", "points": _r(0, 0, 20, 3)}, {"kind": "dukkan", "points": _r(0, 3.2, 20, 12)}]
    sinir = _w(1, _r(0, 3.0, 20, 3.2))
    koridor_ici = _w(2, _r(10, 0.5, 10.2, 2.5))
    dukkan_ici = _w(3, _r(5, 6, 5.2, 10))
    dis = _w(4, _r(0, 12, 20, 12.2))
    faces, note = shell_wall_faces([sinir, koridor_ici, dukkan_ici, dis], zones, exterior={4})
    assert faces == {1: 1, 2: 2, 3: 0, 4: 0}
    assert "kaba teslim" in note


def test_ortak_alan_siniri_yoksa_ic_duvar_bir_yuz_tahmin():
    faces, note = shell_wall_faces([_w(1, _r(0, 0, 5, 0.2)), _w(2, _r(0, 5, 5, 5.2))], [], exterior={2})
    assert faces == {1: 1, 2: 0} and "TAHMİN" in note


def test_yuz_sayisi_kaba_teslim_hesabinda_kullanilir():
    walls = [{"element": {"id": 1}, "gross": 30.0}, {"element": {"id": 2}, "gross": 20.0}]
    alloc = [{"all": 0.0}, {"all": 0.0}]
    q, _, note = finish_quantity(walls, alloc, {}, "plaster_sides", {2}, 1, faces={1: 1, 2: 0}, faces_note="kaba")
    assert q == pytest.approx(30.0) and note == "kaba"


def test_ayar_okunur():
    assert tenant_shell_on({"tenant_shell": 1.0}) and tenant_shell_on({"tenant_shell": True})
    assert not tenant_shell_on({"tenant_shell": None}) and not tenant_shell_on({"tenant_shell": 0})


# ------------------------------------------------------------------ kat rolleri ve merdiven

def test_kat_rolu():
    from app.services import floor_role
    assert floor_role("A2 BLOK / BODRUM KAT PLANI ÖLÇEK:1/100") == "bodrum"
    assert floor_role("A2 BLOK / ÇATI KATI PLANI ÖLÇEK:1/100") == "cati_kati"
    assert floor_role("A2 BLOK / ZEMİN KAT PLANI ÖLÇEK:1/100") == ""


def test_cati_katinda_ic_siva_boya_yok():
    """Kullanıcı: "çatı katında ise bişey yok" — ortak alan yoktur, iç yüzler yazılmaz."""
    faces, note = shell_wall_faces([_w(1, _r(0, 0, 5, 0.2)), _w(2, _r(0, 5, 5, 5.2))],
                                   [{"kind": "ortak", "points": _r(0, 0, 5, 5)}], exterior=set(), role="cati_kati")
    assert faces == {1: 0, 2: 0} and "çatı katı" in note


def test_merdiven_evi_merdiven_cizgilerinden():
    """Bodrumda (otopark) ortak alan merdiven ve önüdür; merdiven kendi katmanında çizilir."""
    from app.parser.loader import Drawing, Entity
    from app.parser.zones import STAIR_FRONT_DEPTH, scan_zones
    basamak = [Entity("line", "brn_stairs", [(0, y * 0.3), (2.0, y * 0.3)]) for y in range(21)]   # 2 × 6 m merdiven
    z = scan_zones(Drawing("x", "m", 1.0, True, entities=basamak))
    assert len(z) == 1 and z[0]["kind"] == "ortak" and z[0]["source"] == "merdiven" and z[0]["estimated"]
    assert z[0]["area"] == pytest.approx(2.0 * 6.0 + 2.0 * STAIR_FRONT_DEPTH, rel=0.05)
    assert "TAHMİN" in z[0]["why"]


def test_alan_cizgisinin_kapsadigi_merdiven_tekrar_eklenmez():
    from app.parser.loader import Drawing, Entity
    from app.parser.zones import scan_zones
    ents = [Entity("line", "brn_stairs", [(1, 1 + y * 0.3), (3.0, 1 + y * 0.3)]) for y in range(21)]
    ents.append(Entity("polygon", "brn_area", _r(0, 0, 4, 9), closed=True))
    ents.append(Entity("text", "yazi", [(2, 4)], text="ZEMİN KAT 24X(30 / 16.45)"))
    z = scan_zones(Drawing("x", "m", 1.0, True, entities=ents))
    assert [x["source"] for x in z] == ["alan_cizgisi"]


def test_koridor_siniri_yoksa_ic_duvar_bir_yuz_merdiven_duvari_hesapli():
    """Dükkân katında yalnız merdiven biliniyorsa koridora bakan duvar 0 sayılmaz (koridor yok değil, çizilmemiş)."""
    merdiven = {"kind": "ortak", "source": "merdiven", "points": _r(0, 0, 3, 6)}
    merdiven_duvari = _w(1, _r(-0.2, 0, 0, 6))            # merdivenin sol duvarı: bir yüzü merdivene bakar
    uzak = _w(2, _r(10, 0, 10.2, 6))                      # koridor duvarı olabilir: bilinmiyor
    faces, note = shell_wall_faces([merdiven_duvari, uzak], [merdiven], exterior=set(), role="")
    assert faces == {1: 1, 2: 1} and "TAHMİN" in note
    faces, _ = shell_wall_faces([merdiven_duvari, uzak], [merdiven], exterior=set(), role="bodrum")
    assert faces == {1: 1, 2: 0}                          # bodrumda ortak alan yalnız merdiven: tam bilgi
