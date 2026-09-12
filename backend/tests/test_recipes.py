"""Reçete açılımı: kalıp → iskele × H, çelik çatı → çelik konstrüksiyon → ankraj → tij / somun / pul, cephe → iş iskelesi,
pencere → lento / montaj; zincir derinliği ve tekrar koruması; reçete kapatma."""
import pytest

from app.quantity.boq import BoqItem, architectural_items, standard_items, structural_items
from app.quantity.recipes import expand_recipes
from app.standard.catalog import Catalog


def _keys(items):
    return {i.key: i for i in items}


def test_formwork_scaffold_from_slab_area():
    """Kalıp iskelesi reçeteden değil döşeme alanı × (H − d) ile yazılır (ÇŞB 15.185): kolon / kiriş yan kalıbı iskele istemez."""
    from app.quantity.engine import ElementData, QuantityParams, compute_all
    from app.quantity.summary import summarize
    p = QuantityParams(storey_height=3.2, slab_thickness=0.2, storey_count=2)
    lines = compute_all([ElementData(id=1, etype="slab", area=100.0, thickness=0.2), ElementData(id=2, etype="column", area=0.16, perimeter=1.6)], p)
    info = {i: {"drawing": "kat", "drawing_id": 1, "kot": None, "area": a, "storey_height": 3.2, "slab_thickness": 0.2} for i, a in ((1, 100.0), (2, 0.16))}
    summary = summarize(lines, [], info)
    assert summary["totals"]["scaffold_m3"] == pytest.approx(100.0 * 2 * 3.0)
    cat = Catalog()
    items = expand_recipes(structural_items(summary, {}), cat, storey_height=3.2)
    k = _keys(items)
    assert k["kalip_iskelesi:*"].quantity == pytest.approx(600.0)
    assert k["kalip_iskelesi:*"].poz == "15.185.1001" and k["kalip_iskelesi:*"].work_group == "KABA"
    assert not k["kalip_iskelesi:*"].detail.get("recipe")
    assert k["beton_pompaj:*"].quantity == pytest.approx(summary["totals"]["concrete_m3"])
    # kalıp reçetesi artık iskele üretmez
    summary2 = {"groups": [{"key": "kolon", "label": "Kolon", "concrete_m3": 10, "formwork_m2": 80, "rebar_kg": 0, "element_count": 4}],
                "totals": {"concrete_m3": 10, "formwork_m2": 80, "rebar_kg": 0}, "rebar_by_dia": []}
    assert "kalip_iskelesi:*" not in _keys(expand_recipes(structural_items(summary2, {}), cat, storey_height=3.2))
    assert len(expand_recipes(structural_items(summary2, {}), cat, storey_height=3.2, off=True)) == len(structural_items(summary2, {}))


def test_steel_roof_chain():
    cat = Catalog()
    roof = [{"etype": "celik_cati", "subtype": "SANDVIC_PANEL", "name": "çatı", "layer": "KSF-CAT-CELIK_CATI-SANDVIC_PANEL",
             "count": 1, "length": 0, "area": 1000.0, "meta": {}}]
    base = standard_items([{"label": "Çatı", "storey_count": 1, "elements": roof}], {}, cat)
    # sistem bileşenleri (expand_systems) burada elle: çelik konstrüksiyon 25 kg/m²
    steel = BoqItem(key="celik_konstruksiyon:s275", kind="celik_konstruksiyon", group="s275", label="Çelik konstrüksiyon S275",
                    unit="kg", quantity=25000.0, discipline="ksf:STA")
    items = expand_recipes(base + [steel], cat, storey_height=3.0)
    k = _keys(items)
    assert k["ankraj_bulonu:m20"].quantity == pytest.approx(250)
    assert k["tij:m20"].quantity == pytest.approx(250) and k["somun:m20"].quantity == pytest.approx(500) and k["pul:m20"].quantity == pytest.approx(500)
    assert k["kaynak:*"].quantity == pytest.approx(1000) and k["antipas:*"].quantity == pytest.approx(500)
    assert k["celik_montaj:*"].quantity == pytest.approx(750) and k["celik_montaj:*"].unit == "saat"
    assert k["vinc:*"].quantity == pytest.approx(100) and k["vinc:*"].unit == "saat"
    assert k["tij:m20"].detail["parent"] == "ankraj_bulonu:m20" and k["tij:m20"].detail["depth"] == 2
    assert all(i.work_group == "KABA" for i in (k["tij:m20"], k["kaynak:*"], k["celik_montaj:*"]))


def test_facade_scaffold_and_openings_recipe():
    cat = Catalog()
    facade = [{"etype": "cephe_boya", "subtype": None, "name": "boya", "layer": "KSF-CEP-CEPHE_BOYA", "count": 1, "length": 0, "area": 600.0, "meta": {}}]
    items = expand_recipes(standard_items([{"label": "Cephe", "storey_count": 1, "elements": facade}], {}, cat), cat, storey_height=3.0)
    k = _keys(items)
    assert "is_iskelesi:*" not in k          # cephe iskelesi reçeteden değil, cephe brüt alanından tek kez türetilir (services.derived_items)
    walls = [{"etype": "wall", "b": 0.2, "length": 10.0, "subtype": "ytong", "count": 1}]
    win = {"etype": "window", "b": 1.2, "h": 1.4, "count": 3, "name": "P1"}
    arch = architectural_items([{"label": "Z", "storey_count": 1, "storey_height": 3.0, "slab_thickness": 0.0, "elements": walls + [win]}], {})
    k = _keys(expand_recipes(arch, cat, storey_height=3.0))
    assert k["lento:*"].quantity == pytest.approx(3) and k["dograma_montaj:*"].quantity == pytest.approx(3) and k["montaj_kopugu:*"].quantity == pytest.approx(3)
    assert k["duvar_tutkal:*"].quantity == pytest.approx((30 - 3 * 1.2 * 1.4) * 4.0)


def test_recipe_does_not_double_measured_item():
    """Çizimde iskele zaten ölçülmüşse reçete üstüne eklemez, not düşer."""
    cat = Catalog()
    facade = [{"etype": "kompozit_panel", "subtype": "4MM", "name": "panel", "layer": "KSF-CEP-KOMPOZIT_PANEL-4MM", "count": 1, "length": 0, "area": 100.0, "meta": {}},
              {"etype": "ankraj_bulonu", "subtype": "M10", "name": "ankraj", "layer": "KSF-STA-ANKRAJ_BULONU-M10", "count": 1, "length": 0, "area": 0, "meta": {}}] \
             + [{"etype": "ankraj_bulonu", "subtype": "M10", "name": "ankraj", "layer": "KSF-STA-ANKRAJ_BULONU-M10", "count": 1, "length": 0, "area": 0, "meta": {}} for _ in range(99)]
    items = expand_recipes(standard_items([{"label": "Cephe", "storey_count": 1, "elements": facade}], {}, cat), cat, storey_height=3.0)
    k = _keys(items)
    assert k["ankraj_bulonu:m10"].quantity == pytest.approx(100) and any("Reçete de" in n for n in k["ankraj_bulonu:m10"].notes)


def test_catalog_recipe_text_format():
    cat = Catalog()
    it = cat.upsert_item({"code": "TEST_KALEM", "discipline": "STA", "name": "Test", "measure": "area",
                          "recipe": "IS_ISKELESI×1; ANKRAJ_BULONU×1.5:M12; KALIP_ISKELESI×1H"})
    assert it.recipe[0] == {"code": "IS_ISKELESI", "factor": 1.0, "spec": ""}
    assert it.recipe[1] == {"code": "ANKRAJ_BULONU", "factor": 1.5, "spec": "M12"}
    assert it.recipe[2] == {"code": "KALIP_ISKELESI", "factor": 1.0, "spec": "", "times": "H"}
    with pytest.raises(ValueError):
        cat.upsert_item({"code": "X", "discipline": "STA", "name": "x", "measure": "area", "recipe": "YOK_BOYLE_KALEM×1"})


def test_openings_recipe_uses_perimeter_and_width():
    """Pencere: körkasa adet, fitil / silikon / mastik çevre, denizlik genişlik; kapı: kasa, pervaz çevre, menteşe 3, kilit, kol, eşik."""
    cat = Catalog()
    walls = [{"etype": "wall", "b": 0.2, "length": 10.0, "subtype": "ytong", "count": 1}]
    win = {"etype": "window", "b": 1.2, "h": 1.4, "count": 3, "name": "P1"}
    door = {"etype": "door", "b": 0.9, "h": 2.1, "count": 2, "name": "K1"}
    arch = architectural_items([{"label": "Z", "storey_count": 1, "storey_height": 3.0, "slab_thickness": 0.0, "elements": walls + [win, door]}], {})
    k = _keys(expand_recipes(arch, cat, storey_height=3.0))
    assert k["korkasa:120x140"].quantity == pytest.approx(3) and k["korkasa_montaj:*"].quantity == pytest.approx(1.5)
    assert k["korkasa_profil:*"].quantity == pytest.approx(3 * 2 * (1.2 + 1.4))          # profil metresi = çevre
    assert k["cam_fitil:*"].quantity == pytest.approx(3 * 2 * (1.2 + 1.4))
    assert k["mastik:*"].quantity == pytest.approx(3 * 5.2) and k["denizlik:*"].quantity == pytest.approx(3 * 1.2)
    assert k["silikon:*"].quantity == pytest.approx(3 * 5.2 + 2 * 2 * (0.9 + 2.1))        # pencere + kapı derzi
    assert k["kapi_kasasi:90x210"].quantity == pytest.approx(2) and k["mentese:*"].quantity == pytest.approx(6)
    assert k["pervaz:*"].quantity == pytest.approx(2 * 6.0) and k["esik:*"].quantity == pytest.approx(2 * 0.9)
    assert k["kilit:*"].quantity == pytest.approx(2) and k["kapi_kolu:*"].quantity == pytest.approx(2) and k["stoper:*"].quantity == pytest.approx(2)
    assert k["dubel_vida:*"].quantity == pytest.approx(3 * 8 + 2 * 6)


def test_dograma_recipe_by_opening_kind():
    """Poz listesi: pencere pozuna körkasa + cam izolasyonu, kapı pozuna kasa + aksesuar; ölçüsüz pozda çevre kalemleri yazılmaz."""
    cat = Catalog()
    dog = [{"etype": "dograma", "subtype": "EMP1", "name": "EMP1", "layer": "(poz listesi)", "count": 10, "length": 0, "area": 0,
            "b": 1.4, "h": 1.9, "meta": {"ksf_code": "DOGRAMA", "measure": "count", "spec": "EMP1", "opening_kind": "window"}},
           {"etype": "dograma", "subtype": "EMP3", "name": "EMP3", "layer": "(poz listesi)", "count": 4, "length": 0, "area": 0,
            "b": 1.4, "h": 2.4, "meta": {"ksf_code": "DOGRAMA", "measure": "count", "spec": "EMP3", "opening_kind": "door"}},
           {"etype": "dograma", "subtype": "EMP8", "name": "EMP8", "layer": "(poz listesi)", "count": 5, "length": 0, "area": 0,
            "b": None, "h": None, "meta": {"ksf_code": "DOGRAMA", "measure": "count", "spec": "EMP8", "opening_kind": "window"}}]
    std = standard_items([{"label": "D", "storey_count": 1, "elements": dog}], {}, cat)
    k = _keys(expand_recipes(std, cat, storey_height=3.0))
    assert k["korkasa:140x190"].quantity == pytest.approx(10) and k["korkasa:*"].quantity == pytest.approx(5)   # ölçülü poz ölçüsüyle, ölçüsüz poz adet
    assert k["cam_fitil:*"].quantity == pytest.approx(10 * 2 * (1.4 + 1.9))   # yalnız ölçülü pencere pozu
    assert k["kapi_kasasi:140x240"].quantity == pytest.approx(4) and k["mentese:*"].quantity == pytest.approx(12)
    assert k["pervaz:*"].quantity == pytest.approx(4 * 2 * (1.4 + 2.4)) and k["esik:*"].quantity == pytest.approx(4 * 1.4)
    assert "kilit:*" in k and k["kilit:*"].quantity == pytest.approx(4)
    assert k["cam:140x190"].quantity == pytest.approx(10 * 1.4 * 1.9)


def test_grandchildren_not_multiplied_by_parent_count():
    """Aynı alt kalem (lento) birçok üst kalemden (14 doğrama pozu) gelse de torun kalemler (lento betonu, demiri, kalıbı)
    yalnız toplanmış lento adediyle çarpılır."""
    cat = Catalog()
    dog = [{"etype": "dograma", "subtype": f"EMP{i}", "name": f"EMP{i}", "layer": "(poz listesi)", "count": 10, "length": 0, "area": 0,
            "b": 1.4, "h": 1.9, "meta": {"ksf_code": "DOGRAMA", "measure": "count", "spec": f"EMP{i}", "opening_kind": "window"}} for i in range(14)]
    std = standard_items([{"label": "D", "storey_count": 1, "elements": dog}], {}, cat)
    k = {i.key: i for i in expand_recipes(std, cat, storey_height=3.0)}
    assert k["lento:*"].quantity == pytest.approx(140)
    assert k["beton:25"].quantity == pytest.approx(140 * 0.03) and k["demir:12"].quantity == pytest.approx(140 * 3)
    assert k["kalip:*"].quantity == pytest.approx(140 * 0.3)
    assert k["beton_pompaj:*"].quantity == pytest.approx(140 * 0.03)              # torunun torunu da tek kez
    assert "kalip_iskelesi:*" not in k                                              # lento kalıbı iskele istemez (ÇŞB 15.185)


def test_labor_hours_come_from_recipe_without_price_entry():
    """Birimi "saat" olan reçete kalemlerinde miktar zaten adam-saattir: fiyat girilmeden süre çıkar."""
    from app.cost.pricing import compute_cost, default_price_items
    it = BoqItem(key="kalip:column", kind="kalip", group="column", label="Kolon kalıbı", unit="m²",
                 quantity=1000.0, discipline="structural", kind_label="Kalıp", discipline_label="Statik")
    items = expand_recipes([it], Catalog())
    labor = _keys(items)["kalip_kurma:*"]
    assert labor.unit == "saat" and labor.quantity == pytest.approx(750.0)    # 1000 m² kolon × 0,75 saat
    assert labor.detail["parent_keys"] == ["kalip:column"]

    cost = compute_cost(items, default_price_items(items), hours_per_day=8.0)
    line = next(l for l in cost["lines"] if l["key"] == "kalip_kurma:*")
    assert line["hours"] == pytest.approx(750.0) and line["hours_source"] == "birim saat"
    # imalat (0,35 / 5 kullanım) + kurma 0,75 + söküm 0,35 = 1,17 sa/m²
    assert cost["duration"]["total_hours"] == pytest.approx(1170.0)
    assert cost["duration"]["man_days"] == pytest.approx(1170.0 / 8, abs=0.2)
    assert "kalip_kurma:*" not in cost["duration"]["missing_rates"]
    # Ekip artık programın normundan gelir (rules.CREW_SIZE: kalıp ekibi 3 kişi); kullanıcı girişi değildir,
    # o yüzden "norm_crew" listesinde görünür ve doğrulanması beklenir.
    assert "kalip_kurma:*" not in cost["duration"]["missing_crew"]
    assert "kalip_kurma:*" in cost["duration"]["norm_crew"]

    # ekip girilince gün takvim günüdür
    prices = default_price_items(items)
    next(p for p in prices if p.key == "kalip_kurma:*").crew_size = 10
    cost = compute_cost(items, prices, hours_per_day=8.0)
    assert next(l for l in cost["lines"] if l["key"] == "kalip_kurma:*")["days"] == pytest.approx(9.375, abs=0.01)


def test_explicit_hours_on_parent_are_not_counted_twice():
    """Üst kaleme adam-saat/birim girilirse aynı iş reçete işçiliğinde tekrar sayılmaz."""
    from app.cost.pricing import compute_cost, default_price_items
    it = BoqItem(key="kalip:column", kind="kalip", group="column", label="Kolon kalıbı", unit="m²",
                 quantity=1000.0, discipline="structural", kind_label="Kalıp", discipline_label="Statik")
    items = expand_recipes([it], Catalog())
    prices = default_price_items(items)
    next(p for p in prices if p.key == "kalip:column").hours_per_unit = 1.5

    cost = compute_cost(items, prices, hours_per_day=8.0)
    parent = next(l for l in cost["lines"] if l["key"] == "kalip:column")
    assert parent["hours"] == pytest.approx(1500.0)
    for key in ("kalip_imalat:*", "kalip_kurma:*", "kalip_sokum:*"):
        child = next(l for l in cost["lines"] if l["key"] == key)
        assert child["hours"] == 0.0 and child["hours_source"] == "üst kalemde sayıldı"
        assert key not in cost["duration"]["missing_rates"]
    assert cost["duration"]["total_hours"] == pytest.approx(1500.0)           # 1500 + 1170 değil


# ---------------------------------------------------------------- demir işçiliği: çap / kat / hazır demir

def _rebar(group: str, kg: float, layers: str = ""):
    return BoqItem(key=f"demir:{group}", kind="demir", group=group, label=f"Demir {group}", unit="kg",
                   quantity=kg, discipline="structural", kind_label="Demir", discipline_label="Statik",
                   detail={"rebar_layers": layers} if layers else {})


def test_rebar_labor_depends_on_diameter():
    """Aynı tonaj, farklı çap: ince demir ton başına çok daha fazla işçilik ister."""
    cat = Catalog()
    thin = {i.kind: i.quantity for i in expand_recipes([_rebar("o8", 1000.0)], cat)}
    thick = {i.kind: i.quantity for i in expand_recipes([_rebar("o26", 1000.0)], cat)}
    assert thin["demir_montaj"] == pytest.approx(24.0)    # 1 ton Ø8  -> 24 saat montaj
    assert thick["demir_montaj"] == pytest.approx(8.0)    # 1 ton Ø26 ->  8 saat
    assert thin["demir_hazirlik"] > thick["demir_hazirlik"]
    # eski tek kalem artık yazılmaz
    assert "demir_iscilik" not in thin


def test_rebar_double_layer_adds_chairs_and_hours():
    """Çift kat (alt + üst) donatı: üst hasır havada bağlanır, sehpa (poz) demiri gerekir."""
    cat = Catalog()
    tek = {i.kind: i.quantity for i in expand_recipes([_rebar("o20", 1000.0, "tek")], cat)}
    cift = {i.kind: i.quantity for i in expand_recipes([_rebar("o20", 1000.0, "cift")], cat)}
    # montaj = demirin kendisi × 1,15 + sehpa demirinin yerine konması (25 kg × 0,020 sa/kg)
    assert cift["demir_montaj"] == pytest.approx(tek["demir_montaj"] * 1.15 + 25 * 0.020)
    assert cift["demir_tasima"] == pytest.approx(tek["demir_tasima"])      # taşıma kattan etkilenmez
    assert "sehpa_demiri" not in tek
    assert cift["sehpa_demiri"] == pytest.approx(25.0)                     # 25 kg / ton
    # sehpa demirinin kendi işçiliği de var (kesme-bükme + yerine koyma)
    assert cift["demir_hazirlik"] > tek["demir_hazirlik"]


def test_rebar_prefab_removes_site_preparation():
    """Demir hazır kesilmiş / bükülmüş geliyorsa kesme - bükme sahada yapılmaz."""
    cat = Catalog()
    site = {i.kind: i.quantity for i in expand_recipes([_rebar("o14", 1000.0)], cat, params={})}
    ready = {i.kind: i.quantity for i in expand_recipes([_rebar("o14", 1000.0)], cat,
                                                        params={"rebar_prefab_pct": 100.0})}
    assert site["demir_hazirlik"] == pytest.approx(8.0)
    assert "demir_hazirlik" not in ready                                   # tamamen ortadan kalkar
    assert ready["demir_montaj"] == pytest.approx(site["demir_montaj"])     # montaj ve taşıma değişmez
    assert ready["demir_tasima"] == pytest.approx(site["demir_tasima"])
    half = {i.kind: i.quantity for i in expand_recipes([_rebar("o14", 1000.0)], cat,
                                                       params={"rebar_prefab_pct": 50.0})}
    assert half["demir_hazirlik"] == pytest.approx(4.0)


def test_rebar_layer_verdict_from_real_drawing_texts():
    """Alt / üst donatı kanıtı yazıdan ve katman adından okunur; kot yazıları kanıt değildir."""
    from app.parser.rebar_mix import layer_verdict, scan_layer_tags
    real = ([("(70cm)ƒ20/18 (Üst)", "VM Üst Donatı")] * 12 + [("(40cm)ƒ14/18 (Alt)", "VOLKAN-DONATI ALT")] * 9
            + [("ƒ20/18 Temel Alt Donatısı (X Yönü)", "DONATI")] * 3
            + [("+0.82 (TEMEL ÜST KOT)", "KOT")] * 15 + [("D.A.K. = DELİK ALT KOTU", "LEJANT")])
    tags = scan_layer_tags(real)
    assert tags == {"ust": 12, "alt": 12} and layer_verdict(tags) == "cift"
    # yalnız ilave alt donatı paftası: çift kat kanıtı değil
    assert layer_verdict(scan_layer_tags([("(ALT-EK)", "DONATI")] * 30)) == "tek"
    assert layer_verdict(scan_layer_tags([("ƒ12/20", "DONATI")] * 30)) == ""   # kanıt yok


# ---------------------------------------------------------------- kalıp işçiliği: eleman tipi / malzeme / tekrar

def _kalip(group: str, m2: float):
    return BoqItem(key=f"kalip:{group}", kind="kalip", group=group, label=f"Kalıp {group}", unit="m²",
                   quantity=m2, discipline="structural", kind_label="Kalıp", discipline_label="Statik")


def _hours(items):
    return {i.kind: i.quantity for i in items if i.unit == "saat"}


def test_formwork_labor_depends_on_element_shape():
    """Aynı 1 m² kalıp: kolonda dört köşe + şakül, perdede düz pano, temelde yerde düz kenar."""
    cat = Catalog()
    par = {"formwork_reuse": 1.0}   # imalatı bölme, saf normu gör
    kolon = _hours(expand_recipes([_kalip("column", 100.0)], cat, params=par))
    perde = _hours(expand_recipes([_kalip("shear_wall", 100.0)], cat, params=par))
    kiris = _hours(expand_recipes([_kalip("beam", 100.0)], cat, params=par))
    temel = _hours(expand_recipes([_kalip("foundation:raft", 100.0)], cat, params=par))
    merdiven = _hours(expand_recipes([_kalip("stair", 100.0)], cat, params=par))
    top = lambda h: sum(h.values())
    assert top(temel) < top(perde) < top(kolon) < top(kiris) < top(merdiven)
    assert kolon["kalip_kurma"] == pytest.approx(75.0)     # 100 m² × 0,75
    assert temel["kalip_kurma"] == pytest.approx(40.0)
    # radye alt tipi de temel bandına düşer
    assert temel == _hours(expand_recipes([_kalip("foundation", 100.0)], cat, params=par))
    assert "kalip_iscilik" not in kolon                     # eski tek kalem artık yazılmaz


def test_formwork_panel_system_removes_manufacturing():
    """Hazır çelik pano / tünel kalıpta pano imalatı yoktur, kurma ve söküm hızlanır."""
    cat = Catalog()
    ply = _hours(expand_recipes([_kalip("shear_wall", 100.0)], cat, params={"formwork_reuse": 1.0}))
    steel = _hours(expand_recipes([_kalip("shear_wall", 100.0)], cat,
                                  params={"formwork_material": "celik", "formwork_reuse": 1.0}))
    tunel = _hours(expand_recipes([_kalip("shear_wall", 100.0)], cat,
                                  params={"formwork_material": "tunel", "formwork_reuse": 1.0}))
    assert ply["kalip_imalat"] == pytest.approx(25.0)
    assert "kalip_imalat" not in steel and "kalip_imalat" not in tunel
    assert steel["kalip_kurma"] == pytest.approx(ply["kalip_kurma"] * 0.70)
    assert sum(tunel.values()) < sum(steel.values()) < sum(ply.values())


def test_formwork_reuse_divides_panel_manufacturing():
    """Pano bir kez yapılır, N kez kullanılır: imalat saati kullanım sayısına bölünür, kurma / söküm değişmez."""
    cat = Catalog()
    bir = _hours(expand_recipes([_kalip("column", 100.0)], cat, params={"formwork_reuse": 1.0}))
    bes = _hours(expand_recipes([_kalip("column", 100.0)], cat, params={"formwork_reuse": 5.0}))
    assert bir["kalip_imalat"] == pytest.approx(35.0)
    assert bes["kalip_imalat"] == pytest.approx(7.0)
    assert bes["kalip_kurma"] == pytest.approx(bir["kalip_kurma"])
    assert bes["kalip_sokum"] == pytest.approx(bir["kalip_sokum"])
