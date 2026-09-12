"""Grup anahtarı: aynı kesitteki elemanlar tek satır, önizleme ile tablo aynı anahtarı kullanır."""
from app.export.svg import render_svg
from app.parser.loader import Drawing
from app.quantity.grouping import annotate, group_key, section_label


def _el(**kw):
    base = {"id": 1, "etype": "column", "subtype": None, "name": None, "layer": "VM Kolon",
            "b": None, "h": None, "thickness": None, "area": 0.0, "length": 0.0, "points": []}
    return {**base, **kw}


def test_kesit_etiketi_cm_yuvarlanir():
    """Çizimden 0,29999999 gelen perde ile 0,30 gelen perde aynı gruba düşer."""
    assert section_label(_el(etype="column", b=1.0, h=1.25)) == "100/125"
    assert section_label(_el(etype="shear_wall", b=0.30000000000000682)) == "30 cm"
    assert section_label(_el(etype="shear_wall", b=0.29999999999999716)) == "30 cm"
    assert group_key(_el(etype="shear_wall", b=0.3)) == group_key(_el(etype="shear_wall", b=0.300000001))


def test_temel_alt_tipi_ve_kalinligi_ayri_grup():
    """Radye 70 cm ile radye 40 cm ayrı kalemdir (ayrı m³ beton); sürekli temel radyeye karışmaz."""
    assert section_label(_el(etype="foundation", subtype="raft", thickness=0.7)) == "radye 70 cm"
    assert section_label(_el(etype="foundation", subtype="raft", thickness=0.4)) == "radye 40 cm"
    assert section_label(_el(etype="foundation", subtype="strip", b=1.9, h=0.5)) == "sürekli"
    keys = {group_key(_el(etype="foundation", subtype="raft", thickness=t)) for t in (0.7, 0.5, 0.4)}
    assert len(keys) == 3


def test_olcusuz_eleman_olculuye_karismaz():
    """b/h okunamayan kolon ayrı gruptur; yoksa ölçüsüzler ölçülü bir kesitin adedini şişirir."""
    assert section_label(_el(etype="column")) == "ölçüsüz"
    assert group_key(_el(etype="column")) != group_key(_el(etype="column", b=1.0, h=1.0))


def test_uzunluk_gruba_girmez():
    """3 m ve 4 m'lik iki 50/45 kiriş aynı kalemdir: adetleri toplanır."""
    a = _el(etype="beam", b=0.5, h=0.45, length=3.0)
    b = _el(etype="beam", b=0.5, h=0.45, length=4.0)
    assert group_key(a) == group_key(b) == "beam|50/45"


def test_annotate_alanlari_ekler_kaynagi_bozmaz():
    src = [_el(etype="beam", b=0.5, h=0.45)]
    out = annotate(src)
    assert out[0]["group"] == "beam|50/45" and out[0]["section"] == "50/45"
    assert "group" not in src[0]


def test_onizleme_cokgeni_tabloyla_ayni_anahtari_tasir():
    """SVG'deki data-group ile eleman listesindeki group birebir aynı olmalı; yoksa tabloya tıklayınca
    çizimde başka şey seçilir."""
    els = [_el(id=7, etype="foundation", subtype="raft", thickness=0.7,
               points=[[0, 0], [10, 0], [10, 10], [0, 10]], area=100.0),
           _el(id=8, etype="foundation", subtype="raft", thickness=0.7,
               points=[[20, 0], [30, 0], [30, 10], [20, 10]], area=100.0)]
    svg = render_svg(Drawing(path="t.dxf", unit="m", scale=1.0, unit_detected=True), els, width=400)
    key = annotate(els)[0]["group"]
    assert key == "foundation|radye 70 cm"
    # bölünmüş temelin iki parçası da aynı gruba düşer: önizlemede tek tıklamayla ikisi birden seçilir
    assert svg.count(f'data-group="{key}"') == 2
