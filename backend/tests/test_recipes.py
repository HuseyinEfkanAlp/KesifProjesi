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
