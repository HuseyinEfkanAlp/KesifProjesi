"""KSF statik katmanları (KSF-STA-KOLON-40x40x300 …) statik motora gider; başlıksız dosya tek çizimdir; dosya adı kodları plan tipi verir."""
import ezdxf
import pytest

from app.parser.analyzer import analyze_file
from app.parser.levels import floor_rank
from app.parser.sheets import scan_sheets
from app.planset import classify_title, resolve_plan
from app.standard.catalog import Catalog


def _ksf_sta_dxf(path):
    """mm: 4 kolon 40x40 (KSF-STA-KOLON_ON-40x40x300), 2 kiriş çokgeni 30 cm × 5 m (KSF-STA-KIRIS_ON-30x60),
    1 döşeme çokgeni 5x5 m (KSF-STA-DOSEME_ON-20), 1 perde 25 cm × 3 m (KSF-STA-PERDE_ON-25x300), görünüş katmanı REF_MIM_GORUNUS."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for name in ("KSF-STA-KOLON_ON-40x40x300", "KSF-STA-KIRIS_ON-30x60", "KSF-STA-DOSEME_ON-20", "KSF-STA-PERDE_ON-25x300", "REF_MIM_GORUNUS", "NOTLAR"):
        doc.layers.add(name)
    msp = doc.modelspace()
    for x, y in ((0, 0), (5000, 0), (0, 5000), (5000, 5000)):
        msp.add_lwpolyline([(x, y), (x + 400, y), (x + 400, y + 400), (x, y + 400)], close=True, dxfattribs={"layer": "KSF-STA-KOLON_ON-40x40x300"})
    for y in (0, 5000):
        msp.add_lwpolyline([(400, y + 50), (5000, y + 50), (5000, y + 350), (400, y + 350)], close=True, dxfattribs={"layer": "KSF-STA-KIRIS_ON-30x60"})
    msp.add_lwpolyline([(0, 0), (5400, 0), (5400, 5400), (0, 5400)], close=True, dxfattribs={"layer": "KSF-STA-DOSEME_ON-20"})
    msp.add_line((8000, 0), (8000, 3000), dxfattribs={"layer": "KSF-STA-PERDE_ON-25x300"})          # perde tek eksen çizgisi
    msp.add_line((0, 2500), (5000, 2500), dxfattribs={"layer": "KSF-STA-KIRIS_ON-30x60"})            # kiriş tek eksen çizgisi (çokgenlerle aynı katman)
    for i in range(30):
        msp.add_line((20000 + i * 300, 0), (20000 + i * 300, 3000), dxfattribs={"layer": "REF_MIM_GORUNUS"})
    for i in range(25):
        msp.add_text(f"NOT {i}", dxfattribs={"layer": "NOTLAR", "height": 250}).set_placement((i * 800, -2000))
    doc.saveas(path)
    return path


def test_ksf_structural_layers_go_to_structural_engine(tmp_path):
    res = analyze_file(str(_ksf_sta_dxf(tmp_path / "STA-03.dxf")), discipline="standard", catalog=Catalog())
    by = {}
    for e in res.elements:
        by.setdefault(e.etype, []).append(e)
    assert len(by["column"]) == 4 and all(e.b == pytest.approx(0.4) and e.h == pytest.approx(0.4) for e in by["column"])
    assert len(by["beam"]) >= 2 and all(e.b == pytest.approx(0.3) and e.h == pytest.approx(0.6) for e in by["beam"])
    assert len(by["slab"]) == 1 and by["slab"][0].thickness == pytest.approx(0.2)
    assert len(by["shear_wall"]) == 1 and by["shear_wall"][0].b == pytest.approx(0.25) and by["shear_wall"][0].length == pytest.approx(3.0)
    assert res.ksf_height == pytest.approx(3.0)
    assert all(e.confidence >= 0.95 for e in by["column"] + by["beam"] + by["slab"])
    assert "structural" in res.disciplines and any("katman adından alındı" in w for w in res.warnings)
    infos = {l.name: l for l in res.layers}
    assert infos["KSF-STA-KOLON_ON-40x40x300"].etype == "column" and "ön boyut" in (infos["KSF-STA-KOLON_ON-40x40x300"].etype_label or "")
    assert infos["REF_MIM_GORUNUS"].etype is None                      # görünüş referansı ölçülmez
    assert not any("Katalogda olmayan KSF" in w for w in res.warnings)   # statik kodlar 'katalogda yok' sayılmaz


def test_untitled_scattered_file_is_single_drawing(tmp_path):
    scan = scan_sheets(_ksf_sta_dxf(tmp_path / "STA-03.dxf"))
    assert not scan.multi_sheet            # plan + görünüş + notlar yan yana: başlık yoksa tek çizim, pafta seçimi yok


@pytest.mark.parametrize("title,code", [
    ("STA-TEM", "sta_temel_kalip"), ("STA-03", "sta_kat_kalip"), ("MIM-01", "mim_kat_plani"), ("ELK-02", "elk_genel"),
    ("MEK-00", "mek_isitma"), ("HAV-01", "mek_hav"), ("SIH-01", "mek_sihhi"), ("YAN-01", "mek_yangin"), ("PEY-00", "pey_peyzaj"),
])
def test_filename_codes_give_plan_type(title, code):
    assert classify_title(title).code == code


def test_ksf_layers_give_plan_type_and_floor_rank():
    layers = {"KSF-STA-KOLON_ON-40x40x300": 64, "KSF-STA-KIRIS_ON-30x60": 98, "REF_MIM_GORUNUS": 216, "NOTLAR": 88}
    assert resolve_plan(["Pafta 1 (başlıksız, 130 nesne)"], layers) == ("sta_kat_kalip", "standard")
    assert resolve_plan([""], {"KSF-MIM-DUVAR_YTONG-20": 40, "KSF-MIM-KAPI-K1": 12}) == ("mim_kat_plani", "standard")
    assert floor_rank("STA-03") == 3 and floor_rank("STA-00") == 0 and floor_rank("STA-TEM") == -100


def test_ksf_sta_file_upload_end_to_end(client, tmp_path):
    pid = client.post("/api/projects", json={"name": "KSF statik", "storey_height": 3.0, "slab_thickness": 0.2}).json()["id"]
    path = _ksf_sta_dxf(tmp_path / "STA-03.dxf")
    with open(path, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("STA-03.dxf", f, "application/dxf")}, data={"discipline": "auto"})
    assert r.status_code == 201, r.text                        # başlıksız dosya: pafta seçimi sorulmadan tek çizim
    d = r.json()
    assert d["plan_type"] == "sta_kat_kalip" and d["discipline"] == "standard" and d["element_count"] >= 8
    assert d["storey_height"] == pytest.approx(3.0)             # KOLON-40x40x300 -> kat yüksekliği 3,00 m
    q = client.get(f"/api/projects/{pid}/quantities").json()
    assert q["summary"]["totals"]["concrete_m3"] > 5 and q["summary"]["totals"]["formwork_m2"] > 20
    groups = {g["etype"]: g for g in q["summary"]["groups"]}
    assert groups["column"]["concrete_m3"] == pytest.approx(4 * 0.4 * 0.4 * (3.0 - 0.2), rel=0.05)
