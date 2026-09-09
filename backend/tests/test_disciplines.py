"""Mimari ve elektrik dedektörleri, keşif listesi, maliyet + süre."""
import pytest

from app.cost.materials import MaterialData
from app.cost.pricing import PriceItem, compute_cost
from app.parser.analyzer import analyze_file
from app.parser.labels_ext import parse_elec_label, parse_opening_label, parse_wall_label, wall_material
from app.parser.layer_profile import LayerProfile
from app.quantity.boq import architectural_items, electrical_items, effective_params


# ---------------------------------------------------------------- etiketler

@pytest.mark.parametrize("text,material,thick", [
    ("YTONG 20", "ytong", 0.20),
    ("20 cm GAZBETON", "ytong", 0.20),
    ("TUĞLA 13.5", "tugla", 0.135),
    ("DUVAR 10", None, 0.10),
    ("ALÇIPAN BÖLME", "alcipan", None),
])
def test_wall_label(text, material, thick):
    lab = parse_wall_label(text)
    assert lab.material == material
    if thick is None:
        assert lab.thickness is None
    else:
        assert lab.thickness == pytest.approx(thick)


@pytest.mark.parametrize("text,etype,name,w,h", [
    ("P1 120/140", "window", "P1", 1.20, 1.40),
    ("K1 90/210", "door", "K1", 0.90, 2.10),
    ("PC3 (150x220)", "window", "PC3", 1.50, 2.20),
    ("K5", "door", "K5", None, None),
])
def test_opening_label(text, etype, name, w, h):
    lab = parse_opening_label(text)
    assert lab.etype == etype and lab.name == name
    if w is None:
        assert not lab.has_dims
    else:
        assert lab.width == pytest.approx(w) and lab.height == pytest.approx(h)


@pytest.mark.parametrize("text,kind,spec", [
    ("TAVA 200x60", "tray", "200x60"),
    ("100x50", "tray", "100x50"),
    ("KT 300", "tray", "300"),
    ("NYY 4x16", "cable", "NYY 4x16"),
    ("3x2,5 NYM", "cable", "NYM 3x2.5"),
    ("N2XH 5x10 mm²", "cable", "N2XH 5x10"),
    ("4x16+16 NYY", "cable", "NYY 4x16+16"),
    ("CAT6", "cable", "CAT6"),
    ("Ø20 PVC", "conduit", "Ø20 PVC"),
    ("25mm HFT boru", "conduit", "Ø25 HFT"),
    ("+4.00", None, None),
])
def test_elec_label(text, kind, spec):
    lab = parse_elec_label(text)
    assert lab.kind == kind
    assert lab.spec == spec


def test_layer_profile_disciplines():
    p = LayerProfile()
    assert p.classify("A-DUVAR-YTONG", "architectural") == "wall"
    assert p.classify("KAPI", "architectural") == "door"
    assert p.classify("PENCERE", "architectural") == "window"
    assert p.classify("PERDE", "architectural") is None          # mimari paftada statik tipi üretilmez
    assert p.classify("KOLON", "architectural") is None
    assert p.classify("A-DUVAR-YTONG", "structural") is None     # statik paftada duvar tipi yok
    assert p.classify("DUVAR TARAMA", "architectural") == "wall"  # tarama mimaride yok sayılmaz
    assert p.classify("E-TAVA", "electrical") == "tray"
    assert p.classify("KABLO TAVASI", "electrical") == "tray"
    assert p.classify("E-KABLO-5x6", "electrical") == "cable"
    assert p.classify("E-PRIZ", "electrical") == "fixture"
    assert p.classify("MERDIVEN TAVA", "electrical") == "tray"
    assert p.classify("E-BORU", "electrical") == "conduit"
    assert p.classify("AKS", "electrical") is None
    assert wall_material("A-DUVAR-YTONG") == "ytong"


# ---------------------------------------------------------------- mimari

def test_arch_detection(arch_dxf):
    r = analyze_file(str(arch_dxf), discipline="architectural")
    assert r.discipline == "architectural"
    walls = r.by_type("wall")
    ytong = [w for w in walls if w.subtype == "ytong"]
    tugla = [w for w in walls if w.subtype == "tugla"]
    assert ytong and tugla, [w.to_dict() for w in walls]
    assert all(abs(w.b - 0.20) < 0.01 for w in ytong)
    assert all(abs(w.b - 0.10) < 0.01 for w in tugla)
    # dış çevre merkez hattı ~ 2*(9.8+7.8) = 35.2 m (çizgi uzunlukları, köşe örtüşmeleri toleranslı)
    assert sum(w.length for w in ytong) == pytest.approx(35.2, abs=1.0)
    assert sum(w.length for w in tugla) == pytest.approx(7.6, abs=0.1)
    doors = r.by_type("door")
    windows = r.by_type("window")
    assert len(doors) == 2 and len(windows) == 3
    k1 = next(d for d in doors if d.name == "K1")
    assert k1.b == pytest.approx(0.9) and k1.h == pytest.approx(2.1)
    other = next(d for d in doors if d.name != "K1")
    assert other.b == pytest.approx(0.9)              # blok adından KAPI_90
    p1 = [w for w in windows if w.name == "P1"]
    assert len(p1) == 2 and all(w.b == pytest.approx(1.2) and w.h == pytest.approx(1.4) for w in p1)
    p2 = next(w for w in windows if w.name == "P2")
    assert p2.b == pytest.approx(0.6) and p2.h == pytest.approx(0.6)
    # mobilya katmanı eşlenmemiş -> uyarı, eleman yok
    assert any("MOBILYA" in w for w in r.warnings)


def test_arch_boq(arch_dxf):
    r = analyze_file(str(arch_dxf), discipline="architectural")
    params = effective_params({"wall_height": 2.8, "plaster_sides": 2, "paint_sides": 2})
    items = architectural_items([{"label": "Zemin", "storey_count": 2, "storey_height": 3.0, "slab_thickness": 0.15,
                                  "elements": r.elements}], params)
    by = {i.key: i for i in items}
    ytong = by["duvar:ytong:20"]
    tugla = by["duvar:tugla:10"]
    gross = (sum(w.length for w in r.by_type("wall") if w.subtype == "ytong") + 7.6) * 2.8
    openings = 2 * 0.9 * 2.1 + 2 * 1.2 * 1.4 + 0.6 * 0.6
    assert ytong.quantity + tugla.quantity == pytest.approx((gross - openings) * 2, rel=0.02)
    assert by["kapi:k1_90x210"].quantity == 2       # 1 adet × 2 kat
    assert by["pencere:p1_120x140"].quantity == 4
    assert sum(i.quantity for i in by.values() if i.kind == "cam") == pytest.approx((2 * 1.2 * 1.4 + 0.36) * 2)
    assert by["cam:120x140"].quantity == pytest.approx(2 * 1.2 * 1.4 * 2)   # cam ölçü bazında
    assert by["siva:*"].quantity == pytest.approx((ytong.quantity + tugla.quantity) * 2)
    assert by["boya:*"].quantity == pytest.approx((ytong.quantity + tugla.quantity) * 2)


# ---------------------------------------------------------------- elektrik

def test_elec_detection(elec_dxf):
    r = analyze_file(str(elec_dxf), discipline="electrical")
    trays = r.by_type("tray")
    specs = sorted((t.subtype, round(t.length, 2)) for t in trays)
    assert specs == [("100x50", 10.0), ("200x60", 28.0)], specs
    cables = {c.subtype: round(c.length, 2) for c in r.by_type("cable")}
    assert cables == {"NYY 4x16": 12.0, "NYM 3x2.5": 9.0, "5x6": 5.0}, cables
    conduits = r.by_type("conduit")
    assert len(conduits) == 1 and conduits[0].subtype == "Ø20 PVC" and conduits[0].length == pytest.approx(4.0)
    fixtures = r.by_type("fixture")
    cats = {}
    for f in fixtures:
        cats[f.subtype] = cats.get(f.subtype, 0) + 1
    assert cats == {"armatur": 4, "priz": 3, "anahtar": 2}, cats


def test_elec_boq_and_cost(elec_dxf):
    r = analyze_file(str(elec_dxf), discipline="electrical")
    params = effective_params({"cable_drop": 3.0, "cable_waste_pct": 10, "tray_waste_pct": 0})
    items = electrical_items([{"label": "Zemin", "storey_count": 1, "elements": r.elements}], params)
    by = {i.key: i for i in items}
    assert by["tava:200x60"].quantity == pytest.approx(28.0)
    assert by["kablo:nyy_4x16"].quantity == pytest.approx((12 + 3) * 1.1)
    assert by["kablo:5x6"].quantity == pytest.approx((5 + 3) * 1.1)
    assert by["boru:o20_pvc"].quantity == pytest.approx(4.0)
    assert by["armatur:armatur_led_panel"].quantity == 4
    assert by["armatur:priz_priz_toprakli"].quantity == 3

    # işçilik kaleme (genel satır + kaleme özel), malzeme ürüne girilir
    prices = [
        PriceItem("kablo:*", "Kablo", "m", labor_price=10, hours_per_unit=0.05, crew_size=2),
        PriceItem("kablo:nyy_4x16", "NYY 4x16", "m", labor_price=15, hours_per_unit=0.1),
        PriceItem("tava:*", "Tava", "m", labor_price=80, hours_per_unit=0.5, crew_size=2),
        PriceItem("armatur:*", "Armatür", "adet", labor_price=150, hours_per_unit=0.75),
    ]
    materials = [
        MaterialData("kablo:nyy_4x16", "NYY 4x16 kablo", "m", 180, brand="Prysmian"),
        MaterialData("kablo:5x6", "NYM 5x6 kablo", "m", 50),
        MaterialData("tava:200x60", "Kablo tavası 200x60", "m", 300),
        MaterialData("armatur:armatur_led_panel", "LED panel armatür", "adet", 900),
    ]
    cost = compute_cost(items, prices, vat_rate=0.2, hours_per_day=8, materials=materials)
    nyy = next(l for l in cost["lines"] if l["key"] == "kablo:nyy_4x16")
    assert nyy["unit_price"] == 180 and nyy["labor_price"] == 15 and nyy["price_source"] == "ürün"
    assert nyy["brand"] == "Prysmian"                       # marka üründen
    assert nyy["material_key"] == "kablo:nyy_4x16"          # kablo kalemi zaten ürün bazında (kesit)
    assert nyy["total"] == pytest.approx(nyy["quantity"] * 195, abs=0.01)
    assert nyy["days"] == pytest.approx(nyy["quantity"] * 0.1 / (2 * 8), abs=0.01)   # ekip özelde yok -> genel (2)
    other = next(l for l in cost["lines"] if l["key"] == "kablo:5x6")
    assert other["unit_price"] == 50 and other["labor_source"] == "genel" and other["crew_size"] == 2
    assert cost["material_subtotal"] + cost["labor_subtotal"] == pytest.approx(cost["subtotal"])
    assert cost["grand_total"] == pytest.approx(cost["subtotal"] * 1.2, abs=0.05)
    assert "boru:o20_pvc" in cost["missing_prices"]
    d = cost["duration"]
    assert d["total_hours"] > 0 and d["sequential_days"] >= d["parallel_days"] > 0
    elec = next(x for x in cost["by_discipline"] if x["discipline"] == "electrical")
    assert elec["days"] == pytest.approx(d["parallel_days"], abs=0.1)


def test_unit_fix_by_text_height_and_xref_layers(arch_dxf, tmp_path):
    """mm yazılmış ama cm çizilmiş mimari plan: yazı yüksekliğinden birim düzeltilir; xref önekli katmanlar tanınır."""
    import ezdxf
    from app.parser.analyzer import analyze_file
    from app.parser.layer_profile import LayerProfile
    ref = analyze_file(str(arch_dxf), discipline="architectural")
    doc = ezdxf.readfile(str(arch_dxf))
    doc.header["$INSUNITS"] = 4       # mm yazılı (çizim cm)
    msp = doc.modelspace()
    for i in range(25):                # yeterli yazı olsun (gerçek ölçekte 20 cm yazı = 20 çizim birimi)
        msp.add_text(f"MAHAL {i}", dxfattribs={"layer": "YAZI", "height": 20}).set_placement((i * 50, -100))
    bad = tmp_path / "mm_yazili.dxf"
    doc.saveas(bad)
    r = analyze_file(str(bad), discipline="architectural")
    assert r.unit == "cm" and not r.unit_detected and any("yazı yükseklikleri" in w for w in r.warnings)
    assert len(r.by_type("wall")) == len(ref.by_type("wall"))
    assert abs(sum(e.length for e in r.by_type("wall")) - sum(e.length for e in ref.by_type("wall"))) < 0.05
    r2 = analyze_file(str(bad), discipline="architectural", unit_override="mm")   # kullanıcı zorlarsa düzeltme yok
    assert r2.unit == "mm" and r2.suggested_unit == "cm"
    prof = LayerProfile()
    assert prof.classify("PROJE-01$0$brn_doors", "architectural") == "door"       # xref öneki + AKS geçse de son parça
    assert prof.classify("BRN-C3-AKS SISTEMI$0$brn_windows", "architectural") == "window"
    assert prof.classify("brn_windows", "architectural") == "window" and prof.classify("brn_doors", "architectural") == "door"
    assert prof.classify("AKS", "architectural") is None


def test_region_polygon_is_not_wall(tmp_path):
    """Duvar katmanına çizilmiş büyük bölge çokgeni (bina sınırı) duvar sayılmaz."""
    import ezdxf
    from app.parser.analyzer import analyze_file
    from tests.fixtures.make_dxf import _rect
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 5
    doc.layers.add("DUVAR")
    msp = doc.modelspace()
    msp.add_lwpolyline(_rect(0, 0, 2000, 1500), close=True, dxfattribs={"layer": "DUVAR"})   # 20 x 15 m bölge
    msp.add_lwpolyline(_rect(0, 0, 500, 20), close=True, dxfattribs={"layer": "DUVAR"})      # 5 m x 20 cm duvar
    p = tmp_path / "bolge.dxf"; doc.saveas(p)
    r = analyze_file(str(p), discipline="architectural")
    walls = r.by_type("wall")
    assert len(walls) == 1 and abs(walls[0].length - 5.0) < 0.01 and abs(walls[0].b - 0.2) < 0.01
