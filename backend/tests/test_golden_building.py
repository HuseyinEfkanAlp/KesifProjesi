"""Altın bina: keşfin uçtan uca doğruluk kapısı.

Ölçüleri bilinen 2 katlı konut (tests/fixtures/golden_building.py) kullanıcı gibi tek DXF olarak yüklenir —
pafta seçimi, kat kotu, mahal, doğrama, kiriş derinliği hep sistemin kendisinden — ve çıkan metraj elle
hesaplanmış doğru metrajla karşılaştırılır.

25 Eyl 2026'da bu bina ilk koşulduğunda bulunan hatalar (her biri aşağıda bir satırla kilitli):
  - pencere boşluğu 1,2 m'den geniş olunca oda kapanmıyordu: 8 odadan 2'si bulundu, şap / kaplama yoktu
  - kasanın köşesi kesilmiş duvarın ucuna değince pencere iki kez düşülüyordu (gazbeton −%12)
  - duvar planda kesilince pencere altı / üstü duvar kayboluyordu
  - duvar yüksekliği kiriş altı yerine döşeme altı alınıyordu (örgü +%14)
  - birleşen duvar kolonun içinden geçip kolon genişliği kadar fazla ölçülüyordu
  - konut katında salon / oda şap ve kaplamaya girmiyordu (yalnız lobi / koridor listesi)
  - tavan kat oturumundan (duvar kalınlıkları dahil) alınıyordu (+%16)
  - geri dolguda radye betonu düşülmüyordu (107 m³ yerine 21 m³)
"""
import pytest

from tests.fixtures.golden_building import golden_truth, make_golden_building


_SONUC: dict = {}          # istemci her testte yeni veritabanı açar; bina bir kez yüklenip sonuç paylaşılır


@pytest.fixture
def golden(client, tmp_path_factory):
    if not _SONUC:
        _SONUC.update(_yukle(client, tmp_path_factory))
    return _SONUC


def _yukle(client, tmp_path_factory) -> dict:
    from app.jobs import run_pending
    path = make_golden_building(tmp_path_factory.mktemp("altin") / "altin_bina.dxf")
    pid = client.post("/api/projects", json={"name": "Altın bina"}).json()["id"]
    with open(path, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("altin_bina.dxf", f, "application/dxf")},
                        data={"background": "true"})
    assert r.status_code == 202, r.text
    run_pending()
    q = client.get(f"/api/projects/{pid}/quantities").json()
    items = [i for i in q["boq"]["items"] if not (i.get("detail") or {}).get("recipe")]

    def qty(kind, group=None):
        return sum(i["quantity"] for i in items if i["kind"] == kind and (group is None or i["group"] == group))

    return {"qty": qty, "drawings": client.get(f"/api/projects/{pid}/drawings").json(), "truth": golden_truth(),
            "quality": q["quality"]}


def test_betonarme(golden):
    q, t = golden["qty"], golden["truth"]
    assert q("beton", "column") == pytest.approx(t["kolon_beton"], rel=0.01)
    assert q("beton", "beam") == pytest.approx(t["kiris_beton"], rel=0.01)
    assert q("beton", "slab") == pytest.approx(t["doseme_beton"], rel=0.01)
    assert q("beton", "foundation:raft") == pytest.approx(t["radye_beton"], rel=0.01)
    assert q("grobeton") == pytest.approx(t["grobeton"], rel=0.01)


def test_duvar_orgusu_kiris_altina_ve_bosluklar_bir_kez(golden):
    q, t = golden["qty"], golden["truth"]
    assert q("duvar", "ytong:20") == pytest.approx(t["gazbeton"], rel=0.01)
    assert q("duvar", "tugla:10") == pytest.approx(t["tugla"], rel=0.01)


def test_dograma_adetleri(golden):
    q, t = golden["qty"], golden["truth"]
    assert q("kapi") == t["kapi"]
    assert q("pencere") == t["pencere"]


def test_ic_siva_tavana_kadar(golden):
    q, t = golden["qty"], golden["truth"]
    assert q("siva") == pytest.approx(t["siva"], rel=0.01)
    assert q("boya") == pytest.approx(t["siva"], rel=0.01)


def test_mahaller_bulunur_ve_ince_isler_mahalden(golden):
    q, t = golden["qty"], golden["truth"]
    mimari = [d for d in golden["drawings"] if d["plan_type"] == "mim_kat_plani"]
    assert len(mimari) == 2
    for d in mimari:
        assert sorted(s["name"] for s in d["spaces"]) == ["BANYO", "MUTFAK", "SALON", "YATAK ODASI"]
        assert all(s["area_source"] == "drawing" for s in d["spaces"])
    assert q("tavan_siva_boya") == pytest.approx(t["tavan"], rel=0.01)
    assert q("doseme_kaplama") == pytest.approx(t["kuru_mahal"], rel=0.01)
    assert q("seramik_zemin") == pytest.approx(t["islak_mahal"], rel=0.01)
    # şap bütün mahallere (ıslak hacim dahil: seramik şap üstüne döşenir), 5 cm
    assert q("sap") == pytest.approx((t["kuru_mahal"] + t["islak_mahal"]) * 0.05, rel=0.01)
    # banyo duvar seramiği ölçülen çevreden: çevre × 2,2 m − kapı (0,9 × 2,1)
    assert q("seramik_duvar") == pytest.approx(t["islak_cevre"] * 2.2 - 2 * 0.9 * 2.1, rel=0.02)


def test_geri_dolgu_temel_betonunu_duser(golden):
    q = golden["qty"]
    assert q("geri_dolgu") == pytest.approx(q("kazi") - q("beton", "foundation:raft") - q("grobeton"), rel=0.01)


def test_kiris_kolonlarda_acikliklara_bolunur(golden):
    """Kolonun iki yanındaki kiriş çizgileri aynı hizada birleşir; kiriş ama açıklıktır. Bölünmezse K101 / K102
    tek kiriş olur, ikinci etiket "bağlanamadı" kalır (25 Eyl: kat başına 12 yerine 6 kiriş)."""
    q, t = golden["qty"], golden["truth"]
    kalip = [d for d in golden["drawings"] if d["plan_type"] == "sta_kat_kalip"]
    assert len(kalip) == 2
    for d in kalip:
        assert d["found"].startswith("12 kiriş"), d["found"]
        assert not any("kiriş etiketi" in w for w in d["warnings"]), d["warnings"]
    assert q("beton", "beam") == pytest.approx(t["kiris_beton"], rel=0.002)


def test_kesit_paftasi_ayri_pafta_ve_kotu_plana_karismaz(golden):
    """Kendi çerçevesindeki "A-A KESİTİ" paftanın adıdır; ad alamayınca komşu 1. kat planına yapışıyor ve
    temel altı / çatı kotları o plana karışıyordu."""
    by = {d["label"]: d for d in golden["drawings"]}
    assert by["A-A KESİTİ"]["plan_type"] == "mim_kesit"
    assert by["1. KAT PLANI"]["levels"] == [3.0]


def test_perde_duvar_orgu_degil_sivasi_sayilir():
    """Mimari planın perde katmanı ("brn_perde duvar") betonarmedir: örgü metrajına girmez, yüzü sıvanır."""
    from app.quantity.boq import architectural_items
    duvar = {"etype": "wall", "b": 0.2, "length": 10.0, "subtype": "ytong", "count": 1, "id": 1,
             "points": [(0, 0), (10, 0), (10, 0.2), (0, 0.2)]}
    perde = {"etype": "wall", "b": 0.25, "length": 4.0, "subtype": "perde", "count": 1, "id": 2, "meta": {"perde": True},
             "points": [(0, 5), (4, 5), (4, 5.25), (0, 5.25)]}
    items = {i.key: i.quantity for i in architectural_items(
        [{"label": "Z", "storey_count": 1, "storey_height": 3.0, "slab_thickness": 0.15, "elements": [duvar, perde]}], {})}
    assert items["duvar:ytong:20"] == pytest.approx(10 * 2.85)
    assert not any(k.startswith("duvar:perde") for k in items)
    assert items["siva:*"] == pytest.approx((10 + 4) * 2.85 * 2)     # dış hat yok: iki yüz


def test_cati_kat_sayilmaz(golden):
    """Kotlar 0,00 / +3,00 / +6,00: +6,00 çatı döşemesidir (üstünde mimari kat planı yok), bina 2 katlıdır."""
    sc = golden["quality"]["storey_count"]
    assert sc["total"] == 2 and sc["levels"] == [0.0, 3.0] and sc["unowned"] == []
