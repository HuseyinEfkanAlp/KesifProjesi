"""Aynı kalemin bitişik parçalarının tek elemanda birleşmesi."""
from __future__ import annotations

from app.parser.detectors.base import DetectedElement
from app.parser.merge import merge_area_elements


def _slab(x0: float, y0: float, w: float, h: float, name: str | None = None, t: float = 0.20,
          layer: str = "DOSEME", etype: str = "slab") -> DetectedElement:
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    return DetectedElement(etype=etype, layer=layer, points=pts, name=name, thickness=t,
                           area=w * h, perimeter=2 * (w + h), handle=f"H{x0}{y0}")


def test_adjacent_same_slab_merges_area_preserved():
    """Kirişlerle bölünmüş bir kat döşemesi: dört bitişik parça tek döşeme olur, alan toplamı değişmez."""
    els = [_slab(0, 0, 5, 4, "D01"), _slab(5, 0, 5, 4, "D02"), _slab(0, 4, 5, 4, "D03"), _slab(5, 4, 5, 4, "D04")]
    out, warns = merge_area_elements(els)
    assert len(out) == 1
    m = out[0]
    assert m.etype == "slab" and m.thickness == 0.20
    assert m.area == 80.0                      # 4 × 20 m²
    assert m.meta["merged_from"] == 4 and m.meta["parts"] == ["D01", "D02", "D03", "D04"]
    assert m.name == "D01 +3"
    assert abs(m.perimeter - 36.0) < 0.2       # 10 × 8 dikdörtgenin çevresi (parçaların çevre toplamı değil)
    assert any("birleştirildi" in w for w in warns)


def test_gap_between_pieces_keeps_them_apart():
    """Arada gerçek boşluk varsa (ayrı mahal) parçalar birleşmez."""
    out, _ = merge_area_elements([_slab(0, 0, 5, 4, "D01"), _slab(9, 0, 5, 4, "D02")])
    assert len(out) == 2


def test_different_thickness_or_layer_never_merges():
    """Farklı kalınlık ya da farklı katman = farklı kalem: bitişik olsalar da ayrı kalır."""
    out, _ = merge_area_elements([_slab(0, 0, 5, 4, t=0.20), _slab(5, 0, 5, 4, t=0.25)])
    assert len(out) == 2
    out, _ = merge_area_elements([_slab(0, 0, 5, 4, layer="DOSEME_20"), _slab(5, 0, 5, 4, layer="DOSEME_A")])
    assert len(out) == 2


def test_counted_elements_never_merge():
    """Bitişik iki kolon tek kolon değildir; sayılan elemanlar hiç birleşmez."""
    a = DetectedElement(etype="column", layer="KOLON", points=[(0, 0), (1, 0), (1, 1), (0, 1)], b=1.0, h=1.0, area=1.0)
    b = DetectedElement(etype="column", layer="KOLON", points=[(1, 0), (2, 0), (2, 1), (1, 1)], b=1.0, h=1.0, area=1.0)
    out, warns = merge_area_elements([a, b])
    assert len(out) == 2 and not warns


def test_strip_foundation_and_walls_stay_apart():
    """Uzunlukla ölçülen kalemler (sürekli temel, duvar) birleşmez: uzunluk anlamını yitirir."""
    def strip(x0):
        return DetectedElement(etype="foundation", subtype="strip", layer="TEMEL",
                               points=[(x0, 0), (x0 + 5, 0), (x0 + 5, 1), (x0, 1)], area=5.0, length=5.0, b=1.0)
    out, _ = merge_area_elements([strip(0), strip(5)])
    assert len(out) == 2


def test_overlapping_pieces_warn_and_keep_quantity():
    """Üst üste çizilmiş iki çokgen: metraj (toplam alan) korunur ama kullanıcı uyarılır."""
    out, warns = merge_area_elements([_slab(0, 0, 5, 4, "D01"), _slab(0, 0, 5, 4, "D02")])
    assert len(out) == 1 and out[0].area == 40.0
    assert any("üst üste" in w for w in warns)


def test_area_items_of_catalog_merge():
    """Katalog (KSF / eşlemeli) alan kalemleri de birleşir: bir mahalin parçalanmış kaplaması tek kalem."""
    els = [_slab(0, 0, 3, 3, etype="seramik_zemin", t=0.0), _slab(3, 0, 3, 3, etype="seramik_zemin", t=0.0)]
    out, _ = merge_area_elements(els)
    assert len(out) == 1 and out[0].area == 18.0
