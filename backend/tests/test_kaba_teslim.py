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


def test_yuruyen_merdiven_adiyla_yazilir():
    from app.parser.loader import Drawing, Entity
    from app.parser.zones import scan_zones
    ents = [Entity("line", "brn_stairs", [(0, y * 0.5), (5.0, y * 0.5)]) for y in range(20)]
    ents.append(Entity("line", "THYSSENKRUPP", [(2, 3), (3, 3)]))
    z = scan_zones(Drawing("x", "m", 1.0, True, entities=ents))
    assert z and z[0]["why"].startswith("yürüyen merdiven")


# ------------------------------------------------------------------ mimarın ortak alan blokları

@pytest.mark.parametrize("ad, tur, blok, kat", [
    ("a2 blok zemin kat lobi", "lobi", "A2", 0),
    ("a3 1.kat lobi", "lobi", "A3", 1),
    ("a bloklar 1. kat lobi seramik", "lobi", "", 1),       # genel: blok öbeğin yerinden bulunur
    ("orta alan döş planı", "koridor", "", None),
    ("a1a2 ışıklık", "isiklik", "", None),
    ("a2 tavan çalışması_rev2", "tavan", "A2", None),
])
def test_ortak_alan_blok_adi(ad, tur, blok, kat):
    from app.parser.common_areas import block_of, floor_of, kind_of
    assert kind_of(ad) == tur and block_of(ad) == blok and floor_of(ad) == kat


def test_bloklar_basligi_blok_planlari_varken_olculmez():
    """A blokları birleşik dosyası A1–A5'i taşıyor; A1/A2/A3'ün kendi planları projede varken duvarları ikinci kez
    (ve kapsam dışı A4–A5 ile) sayılırdı."""
    from app.intake import auto_pick_sheets
    sh = NS(index=0, title="A BLOKLAR-BİRİNCİ KAT PLANI", titles=[], layers={}, kind="plan", entity_count=5000,
            titled=True, to_dict=lambda: {})
    _, rapor = auto_pick_sheets(NS(sheets=[sh]), {"A1", "A2", "A3"})
    assert rapor.picked == [] and "genel plan" in rapor.evidence[0]["reason"]
    _, rapor = auto_pick_sheets(NS(sheets=[sh]), set())          # tek kaynaksa ölçülür
    assert [e["index"] for e in rapor.picked] == [0]


def test_tavan_ortak_alan_kaydindan(client):
    """Alan çizgisi olmayan dükkân katında tavan, mimarın lobi / koridor bloklarından (blok + kat eşleşmesi)."""
    from app import db
    from app.models import Drawing, Project
    from sqlmodel import Session
    from app.services import project_boq
    pid = client.post("/api/projects", json={"name": "AVM", "params": {"tenant_shell": 1}}).json()["id"]
    with Session(db.engine) as s:
        p = s.get(Project, pid)
        p.common_areas = [{"blok": "A2", "kat": 0, "tur": "lobi", "alan": 100.0}, {"blok": "A2", "kat": 0, "tur": "koridor", "alan": 190.0},
                          {"blok": "A2", "kat": 1, "tur": "lobi", "alan": 84.0}, {"blok": "A5", "kat": 0, "tur": "lobi", "alan": 99.0}]
        s.add(p)
        s.add(Drawing(project_id=pid, filename="a2.dxf", stored_path="x", label="A2 BLOK / ZEMİN KAT PLANI", block="A2",
                      discipline="architectural", plan_type="mim_kat_plani", zones=[]))
        s.commit()
        tavan = [i for i in project_boq(s.get(Project, pid), s) if i.kind == "tavan_siva_boya"]
    assert len(tavan) == 1 and tavan[0].quantity == pytest.approx(290.0)     # A2 zemin: lobi + koridor; A5 ve 1. kat değil
    assert "bloklarından" in tavan[0].notes[0]
