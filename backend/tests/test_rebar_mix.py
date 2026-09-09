"""Donatı çapı karışımı: çizim yazılarından hangi nervürlü demirin kullanıldığını çıkarma."""
import pytest

from app.cost.materials import material_of
from app.parser.rebar_mix import normalize, scan_texts, split_by_dia
from app.quantity.boq import structural_items


def test_scan_texts_formats():
    """Projelerde geçen donatı yazısı biçimleri: ƒ / Ø / %%c simgesi, çarpımlı adet, aralık, poz boyu."""
    r = scan_texts(["20ƒ14/20"])                       # 20 adet Ø14
    assert set(r) == {14} and r[14] == pytest.approx(20 * 14 ** 2)
    r = scan_texts(["4X7ƒ12/10"])                      # 4 × 7 adet Ø12
    assert r[12] == pytest.approx(28 * 12 ** 2)
    r = scan_texts(["ƒ14/18 Temel Üst Donatısı"])      # adetsiz: metre başına 100/18 çubuk
    assert r[14] == pytest.approx(100 / 18 * 14 ** 2)
    r = scan_texts(["S1 30/60 8Ø16", "%%c12", "Q10/15"])
    assert set(r) == {16, 12, 10}
    r = scan_texts(["P01 182ƒ8/10 etr. l=196"])        # boy verilmişse ağırlığa orantılı
    assert r[8] == pytest.approx(182 * 8 ** 2 * 1.96)
    assert scan_texts(["ÖLÇEK 1/100", "K101 (25/60)", "+7.95", ""]) == {}   # donatı olmayan yazılar


def test_normalize_and_split():
    mix = normalize({10: 700.0, 12: 240.0, 14: 60.0, 32: 1.0})    # %0.1'lik çap elenir
    assert set(mix) == {10, 12, 14} and sum(mix.values()) == pytest.approx(1.0)
    assert mix[10] == pytest.approx(0.7, abs=0.01)
    parts = dict(split_by_dia(1000.0, {10: 700.0, 12: 300.0}))
    assert parts[10] == pytest.approx(700.0, abs=1) and parts[12] == pytest.approx(300.0, abs=1)
    assert split_by_dia(1000.0, {}) == []


def _summary(kg: float = 1000.0) -> dict:
    return {"groups": [{"key": "column", "etype": "column", "label": "Kolon", "element_count": 4,
                        "concrete_m3": 5.0, "formwork_m2": 40.0, "rebar_kg": kg, "rebar_source": "oran",
                        "rebar_ratio_kg": kg}],
            "totals": {"concrete_m3": 5.0, "formwork_m2": 40.0, "rebar_kg": kg}}


def test_ratio_rebar_split_by_dia():
    """Oranla bulunan demir, çizimdeki çap dağılımına göre çap kalemlerine bölünür ve çap ürünlerine bağlanır."""
    mix = {"column": {12: 30.0, 26: 70.0}}
    items = {i.key: i for i in structural_items(_summary(), {"rebar_waste_pct": 0}, rebar_mix=mix)}
    assert "demir:column" not in items                      # çapsız kalem kalmaz
    assert items["demir:column:o12"].quantity == pytest.approx(300.0)
    assert items["demir:column:o26"].quantity == pytest.approx(700.0)
    assert "Ø12 %30" in items["demir:column:o12"].notes[0] and "oranı" in items["demir:column:o12"].notes[0]
    assert material_of(items["demir:column:o26"], {})[0] == "demir:o26"     # ürün: Ø26 demir

    # eleman tipine özel dağılım yoksa proje geneli ("*") kullanılır
    items2 = {i.key: i for i in structural_items(_summary(), {"rebar_waste_pct": 0}, rebar_mix={"*": {16: 100.0}})}
    assert items2["demir:column:o16"].quantity == pytest.approx(1000.0)

    # fire de aynı dağılımla bölünür
    items3 = {i.key: i for i in structural_items(_summary(), {"rebar_waste_pct": 3}, rebar_mix={"*": {16: 100.0}})}
    assert items3["demir:fire:o16"].quantity == pytest.approx(30.0)


def test_ratio_rebar_without_mix_or_off():
    """Çap dağılımı yoksa ya da kapatılmışsa eski davranış: tek 'çap karışık' kalemi."""
    items = {i.key: i for i in structural_items(_summary(), {"rebar_waste_pct": 0})}
    assert items["demir:column"].quantity == pytest.approx(1000.0)
    assert material_of(items["demir:column"], {})[0] == "demir:karisik"
    off = {i.key: i for i in structural_items(_summary(), {"rebar_waste_pct": 0, "rebar_dia_split": "off"},
                                              rebar_mix={"column": {12: 100.0}})}
    assert "demir:column" in off and "demir:column:o12" not in off


def test_project_rebar_mix_from_drawings(client, storey_dxf, beam_detail_dxf):
    """Donatı paftası yüklenince çap dağılımı çizimden okunur ve oran demiri çaplara bölünür."""
    pid = client.post("/api/projects", json={"name": "çap", "storey_height": 3.0, "slab_thickness": 0.15}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("kat.dxf", f, "application/dxf")},
                    data={"discipline": "structural"})
    boq = client.get(f"/api/projects/{pid}/quantities").json()["boq"]
    assert any(i["key"] == "demir:column" for i in boq["items"])          # henüz çap bilinmiyor

    with open(beam_detail_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("kiris.dxf", f, "application/dxf")},
                    data={"discipline": "rebar"})
    boq = client.get(f"/api/projects/{pid}/quantities").json()["boq"]
    keys = {i["key"] for i in boq["items"]}
    assert not any(k.startswith("demir:column") and ":o" not in k for k in keys)   # kolon demiri artık çap bazında
    dias = {k.rsplit(":o", 1)[1] for k in keys if k.startswith("demir:column:o")}
    assert dias and dias <= {"8", "10", "12", "14", "16", "20", "26"}
    mats = {m["key"] for m in client.get(f"/api/projects/{pid}/materials").json()}
    assert any(m.startswith("demir:o") for m in mats) and "demir:karisik" not in mats


def test_block_attributes_are_read(tmp_path):
    """Blok yerleşimine bağlı öznitelikler (ATTRIB) okunur: donatı ve poz yazıları çoğu projede orada durur."""
    import ezdxf
    from app.parser.loader import load_dxf

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    blk = doc.blocks.new("DONATI_ETIKET")
    blk.add_attdef("POZ", dxfattribs={"height": 5}).set_placement((0, 0))
    blk.add_attdef("ACIKLAMA", dxfattribs={"height": 5}).set_placement((0, -10))
    blk.add_line((0, 0), (10, 0))
    msp = doc.modelspace()
    ins = msp.add_blockref("DONATI_ETIKET", (0, 0))
    ins.add_auto_attribs({"POZ": "24ƒ14/18", "ACIKLAMA": "L=1200"})
    path = tmp_path / "attrib.dxf"
    doc.saveas(path)

    texts = [e.text for e in load_dxf(path).entities if e.kind == "text" and e.text]
    assert "24ƒ14/18" in texts and "L=1200" in texts
    assert scan_texts(texts) == {14: pytest.approx(24 * 14 ** 2)}   # boy ayrı yazıda: yalnız adet × çap²
