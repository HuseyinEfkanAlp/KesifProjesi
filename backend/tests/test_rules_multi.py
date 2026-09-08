"""Ölçü kuralları (ÇŞB tarifleri), iş grupları / poz eşlemesi ve aynı paftada çok disiplin."""
from pathlib import Path

import ezdxf
import pytest

from app.parser.analyzer import analyze_file
from tests.test_api import client  # noqa: F401  (API istemcisi fikstürü)
from app.quantity.boq import architectural_items, boq_summary, structural_items
from app.standard.catalog import Catalog
from app.standard.rules import WALL_OPENING_MIN_M2, default_poz, work_group_of


def test_wall_small_openings_not_deducted_but_plaster_deducts_all():
    walls = [{"etype": "wall", "b": 0.2, "length": 10.0, "subtype": "ytong", "count": 1}]
    big = {"etype": "window", "b": 1.2, "h": 1.4, "count": 1, "name": "P1"}
    small = {"etype": "window", "b": 0.3, "h": 0.3, "count": 2, "name": "P2"}     # 0,09 m² < 0,10: duvardan düşülmez
    assert 0.3 * 0.3 < WALL_OPENING_MIN_M2
    drawings = [{"label": "Z", "storey_count": 1, "storey_height": 3.0, "slab_thickness": 0.0, "elements": walls + [big, small]}]
    items = {i.key: i for i in architectural_items(drawings, {"plaster_sides": 1, "paint_sides": 2})}
    gross = 10 * 3.0
    assert items["duvar:ytong:20"].quantity == pytest.approx(gross - 1.2 * 1.4)
    assert any("0,10 m²" in n for n in items["duvar:ytong:20"].notes)
    assert items["siva:*"].quantity == pytest.approx((gross - 1.2 * 1.4 - 2 * 0.09) * 1)
    assert items["boya:*"].quantity == pytest.approx((gross - 1.2 * 1.4 - 2 * 0.09) * 2)
    assert items["duvar:ytong:20"].poz == "15.225.1010" and items["siva:*"].poz == "15.280.1008" and items["boya:*"].poz == "15.540.1509"
    assert items["duvar:ytong:20"].work_group == "INCE"


def test_default_poz_and_work_groups():
    assert default_poz("beton", "kolon") == ("15.150.1006", "C 30/37 hazır beton, pompalı")
    assert default_poz("demir", "o12")[0] == "15.160.1003" and default_poz("demir", "o16")[0] == "15.160.1004"
    assert default_poz("kalip", "x")[0] == "15.180.1003"
    assert default_poz("armatur", "led") is None
    assert work_group_of("structural") == "KABA" and work_group_of("ksf:HAV") == "MEK" and work_group_of("ksf:ZAY") == "ELK"
    assert work_group_of("ksf:PEY") == "ALT" and work_group_of("architectural") == "INCE"
    summary = {"groups": [{"key": "kolon", "label": "Kolon", "concrete_m3": 10, "formwork_m2": 80, "rebar_kg": 0, "element_count": 4}],
               "totals": {"concrete_m3": 10, "formwork_m2": 80, "rebar_kg": 0}, "rebar_by_dia": []}
    out = boq_summary(structural_items(summary, {}))
    assert out["by_group"][0]["group"] == "KABA" and all(i["work_group"] == "KABA" for i in out["items"])
    assert "wall_opening" in out["rules"]
    beton = next(i for i in out["items"] if i["kind"] == "beton")
    assert beton["poz"] == "15.150.1006" and "hacim" in beton["notes"][0]


def _mixed_dxf(path: Path) -> Path:
    """Aynı paftada mimari duvarlar (cm, YTONG 20) + elektrik kablo hattı ve armatür blokları + bir KSF katmanı."""
    from tests.fixtures.make_dxf import make_arch_dxf
    make_arch_dxf(path)
    doc = ezdxf.readfile(str(path))
    for name in ("E-KABLO", "E-ARMATUR", "KSF-YAN-SPRINKLER-K80"):
        doc.layers.add(name)
    msp = doc.modelspace()
    for y in (100, 200, 300):
        msp.add_line((0, y), (900, y), dxfattribs={"layer": "E-KABLO"})          # 3 × 9 m kablo
    msp.add_text("NYY 4x16", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((450, 110))
    blk = doc.blocks.new("LED_PANEL")
    blk.add_lwpolyline([(0, 0), (60, 0), (60, 60), (0, 60)], close=True)
    for i in range(4):
        msp.add_blockref("LED_PANEL", (200 + i * 150, 400), dxfattribs={"layer": "E-ARMATUR"})
    spr = doc.blocks.new("SPR")
    spr.add_circle((0, 0), 10)
    for i in range(5):
        msp.add_blockref("SPR", (150 + i * 150, 600), dxfattribs={"layer": "KSF-YAN-SPRINKLER-K80"})
    doc.saveas(path)
    return path


def test_multi_discipline_same_sheet(tmp_path):
    path = str(_mixed_dxf(tmp_path / "karma.dxf"))
    cat = Catalog()
    only_arch = analyze_file(path, discipline="architectural", catalog=cat)
    types = {e.etype for e in only_arch.elements}
    assert "wall" in types and "cable" not in types
    assert only_arch.discipline_hints.get("electrical", 0) >= 3            # elektrik katmanları var, açılmamış
    assert any("Elektrik" in w and "ek disiplin" in w for w in only_arch.warnings)
    assert "sprinkler" in types                                            # KSF katmanı her disiplinde standart kuralla ölçülür
    assert sum(e.count for e in only_arch.elements if e.etype == "sprinkler") == 5
    both = analyze_file(path, discipline="architectural", catalog=cat, extra_disciplines=("electrical",))
    types = {e.etype for e in both.elements}
    assert {"wall", "cable", "fixture", "sprinkler"} <= types
    assert both.disciplines == ["architectural", "electrical"] and "electrical" not in both.discipline_hints
    cables = [e for e in both.elements if e.etype == "cable"]
    assert sum(e.length for e in cables) == pytest.approx(27.0, abs=0.1)
    assert sum(e.count for e in both.elements if e.etype == "fixture") == 4
    wall_len_only = sum(e.length for e in only_arch.elements if e.etype == "wall")
    wall_len_both = sum(e.length for e in both.elements if e.etype == "wall")
    assert wall_len_only == pytest.approx(wall_len_both)                  # ek disiplin mimariyi bozmaz


def test_api_extra_discipline(client, tmp_path):
    path = _mixed_dxf(tmp_path / "karma_api.dxf")
    pid = client.post("/api/projects", json={"name": "Karma pafta", "storey_height": 3.0, "slab_thickness": 0.15}).json()["id"]
    with open(path, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("karma.dxf", f, "application/dxf")},
                        data={"label": "Zemin", "discipline": "architectural"})
    if r.status_code == 200 and r.json().get("needs_sheet_selection"):   # dağınık sentetik çizim küme sanılırsa: bütün olarak ekle
        r = client.post(f"/api/projects/{pid}/drawings/from-source",
                        json={"token": r.json()["source"]["token"], "whole": True, "discipline": "architectural"})
        assert r.status_code == 201, r.text
        d = r.json()[0]
    else:
        assert r.status_code == 201, r.text
        d = r.json()
    assert d["discipline_hints"].get("electrical") and d["disciplines"] == []
    r = client.patch(f"/api/drawings/{d['id']}", json={"disciplines": ["electrical"]})
    assert r.status_code == 200 and r.json()["disciplines"] == ["electrical"] and not r.json()["discipline_hints"].get("electrical")
    q = client.get(f"/api/projects/{pid}/quantities").json()
    kinds = {i["kind"] for i in q["boq"]["items"]}
    assert {"duvar", "kablo", "armatur", "sprinkler"} <= kinds
    groups = {g["group"] for g in q["boq"]["by_group"]}
    assert {"INCE", "ELK", "MEK"} <= groups
    assert client.patch(f"/api/drawings/{d['id']}", json={"disciplines": ["mapped"]}).status_code == 400
