"""Maliyet bileşenleri ve metraj ↔ fiyat ayrımı (app/cost/pricing.py, app/quality.py).

İki ayrı iş: keşif hiç fiyat girilmeden de tamamlanmış olabilir — müteahhit metrajı alıp kendi
fiyatını koyar. Eksik fiyatı metraj sayfasında "eksik" diye göstermek doğru çıkmış bir metrajı
kusurlu gösterir.
"""
from app.cost.pricing import PriceItem, compute_cost
from app.quality import build_quality
from app.quantity.boq import BoqItem


def _item(key="beton:kolon", kind="beton", qty=100.0, unit="m³"):
    return BoqItem(key=key, kind=kind, group=key.split(":", 1)[1], label=key, unit=unit,
                   quantity=qty, discipline="structural")


def _fiyat(key="beton:kolon", **alanlar):
    return PriceItem(key, key, "m³", set_fields=tuple(alanlar), **alanlar)


# ------------------------------------------------------------------ doğrudan bileşenler

def test_ekipman_bedeli_ayri_toplanir():
    c = compute_cost([_item()], [_fiyat(labor_price=300.0, equipment_price=150.0)])
    assert c["labor_subtotal"] == 30000.0
    assert c["equipment_subtotal"] == 15000.0
    assert c["direct_subtotal"] == 45000.0


def test_taseron_bedeli_digerlerinin_yerine_gecer():
    """Taşeron kendi malzemesini, işçiliğini ve makinesini getirir: üstüne eklemek iki kez saymaktır."""
    c = compute_cost([_item()], [_fiyat(labor_price=300.0, equipment_price=150.0, subcontract_price=2500.0)])
    assert c["subcontract_subtotal"] == 250000.0
    assert c["labor_subtotal"] == 0.0 and c["equipment_subtotal"] == 0.0
    assert c["direct_subtotal"] == 250000.0


def test_poz_bedeli_ekipmani_da_kapsar():
    c = compute_cost([_item()], [_fiyat(labor_price=300.0, equipment_price=150.0, poz_price=2000.0)])
    assert c["equipment_subtotal"] == 0.0
    assert c["direct_subtotal"] == 200000.0


# ------------------------------------------------------------------ dolaylı bileşenler

def test_dolayli_oranlar_sirayla_uygulanir():
    """Genel gider nakliyeyi, kâr da genel gideri kapsar — hepsi aynı tabana uygulanamaz."""
    c = compute_cost([_item()], [_fiyat(labor_price=1000.0)],
                     params={"transport_pct": 10.0, "overhead_pct": 10.0})
    assert c["direct_subtotal"] == 100000.0
    nakliye, genel = c["indirect_lines"]
    assert nakliye["total"] == 10000.0 and nakliye["base"] == 100000.0
    assert genel["base"] == 110000.0 and genel["total"] == 11000.0
    assert c["indirect_subtotal"] == 21000.0
    assert c["subtotal"] == 121000.0


def test_oran_girilmediyse_toplam_degismez():
    c = compute_cost([_item()], [_fiyat(labor_price=1000.0)])
    assert c["indirect_subtotal"] == 0.0 and c["indirect_lines"] == []
    assert c["subtotal"] == c["direct_subtotal"] == 100000.0


def test_kdv_dolayli_bedelin_uzerine_biner():
    c = compute_cost([_item()], [_fiyat(labor_price=1000.0)], vat_rate=0.20,
                     params={"profit_pct": 10.0})
    assert c["subtotal"] == 110000.0
    assert c["vat"] == 22000.0 and c["grand_total"] == 132000.0


# ------------------------------------------------------------------ metraj ↔ fiyat ayrımı

def _kalite(cost_required):
    cost = {"missing_materials": ["beton_c30"], "missing_labor": ["beton:kolon"]}
    return build_quality([], [], [_item()], {}, {}, {"warnings": []}, cost, cost_required=cost_required)


def test_metraj_yolunda_eksik_fiyat_engelleyici_degil():
    q = _kalite(cost_required=False)
    eksik = [i for i in q["issues"] if i["code"] in ("missing_materials", "missing_labor")]
    assert eksik and all(i["severity"] == "review" for i in eksik)


def test_maliyet_yolunda_eksik_fiyat_engelleyici_kalir():
    q = _kalite(cost_required=True)
    eksik = [i for i in q["issues"] if i["code"] in ("missing_materials", "missing_labor")]
    assert eksik and all(i["severity"] == "blocking" for i in eksik)
    assert q["status"] == "incomplete"
