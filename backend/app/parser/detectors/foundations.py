"""Temel tespiti.

- Radye (raft): temel katmanındaki büyük kapalı çokgenler; pafta sınırında kesildiği için açık kalmış
  polyline'lar da kapatılır. Kalınlık "h=60" / "70cm" etiketinden ya da varsayılan.
  * İç içe çokgen (asansör çukuru gibi): ayrı eleman sayılır, alanı dıştakinden düşülür.
  * Çokgen DIŞINDA kalan radye etiketleri varsa (ör. "RD2 40cm": ince bölge, sınırı çizilmemiş) bina oturumu
    kolon/perde dış hattından `raft_margin` kadar dışarı alınarak tahmin edilir; çokgenler düşülür, kalan
    alan o etiketlerin kalınlığıyla radye sayılır (düşük güven, kullanıcı düzeltebilir).
- Sürekli temel (strip): uzun/dar çokgen ya da paralel çizgi çifti; kesit b/h etiketten ("TK1 60/80").
"""
from __future__ import annotations

from collections import Counter

from shapely import concave_hull
from shapely.geometry import Point as SPoint, Polygon
from shapely.ops import unary_union

from ..geometry import min_area_rect, perimeter, polygon_area
from ..loader import Drawing
from .base import (DetectParams, DetectedElement, LabelIndex, dedupe_elements, find_parallel_pairs,
                   polygons_on_layers, segments_on_layers)


def detect_foundations(drawing: Drawing, layers: list[str], labels: LabelIndex, params: DetectParams,
                       supports: list[list] | None = None) -> list[DetectedElement]:
    elements: list[DetectedElement] = []
    zones: list[DetectedElement] = []
    for ent in polygons_on_layers(drawing, layers, close_open=True, min_area=2.0):
        area = polygon_area(ent.points)
        if area < 0.2:
            continue
        long_side, short_side, _ = min_area_rect(ent.points)
        el = DetectedElement(etype="foundation", layer=ent.layer, points=list(ent.points), area=area,
                             perimeter=perimeter(ent.points), source=ent.source, handle=ent.handle,
                             confidence=0.6)
        lab = labels.find(ent.points, "foundation", radius=0.0) or labels.find(ent.points, "foundation")
        is_strip = short_side <= params.strip_width_range[1] and long_side / max(short_side, 1e-9) > 4.0
        if lab:
            el.label_raw = lab.raw
            el.name = lab.name
            if lab.name and lab.name.upper().startswith(("TK", "ST")):
                is_strip = True
            if lab.name and lab.name.upper().startswith(("R", "RT", "RD")):
                is_strip = False
        if ent.source == "POLYLINE>CLOSED":
            el.warnings.append("Sınır açık çizilmiş (pafta kesimi); uçları birleştirilerek kapatıldı")
        if is_strip:
            _fill_strip(el, lab, short_side, long_side, params)
            elements.append(el)
        else:
            el.subtype = "raft"
            if lab and lab.thickness:
                el.thickness = lab.thickness
                el.confidence = 0.9
            elif lab and lab.has_dims:
                el.thickness = min(lab.b, lab.h)
                el.confidence = 0.7
            else:
                el.thickness = params.default_foundation_thickness
                el.warnings.append(f"Kalınlık etiketi yok; varsayılan {params.default_foundation_thickness*100:.0f} cm kullanıldı")
            zones.append(el)

    zones = dedupe_elements(zones, tol=0.6)
    _subtract_nested(zones)
    elements.extend(zones)

    # paralel çizgi çiftleri -> sürekli temel
    segs = segments_on_layers(drawing, layers)
    for pair in find_parallel_pairs(segs, params.strip_width_range, min_length=0.5):
        el = DetectedElement(etype="foundation", layer=pair.layer, points=pair.rect,
                             area=pair.width * pair.length, perimeter=2 * (pair.width + pair.length),
                             source="PARALLEL_LINES", handle=pair.handles[0], confidence=0.5)
        lab = labels.find(pair.rect, "foundation")
        if lab:
            el.label_raw = lab.raw
            el.name = lab.name
        _fill_strip(el, lab, pair.width, pair.length, params)
        if lab is None and pair.width < 0.4:
            # etiketsiz, dar çizgi çifti: çukur duvarı / detay çizgisi olabilir -> metraj dışı, kullanıcı karar versin
            el.confidence = 0.3
            el.warnings.append("Etiketsiz dar çizgi çifti; sürekli temel olduğundan emin değil")
        elements.append(el)

    elements = dedupe_elements(elements, tol=0.6)
    # tahmini dış bölge en sona eklenir: sınırı çokgenleri de sarar (delikli), tekrar elemeye girmemeli
    remainder = _estimate_untagged_raft(zones, labels, supports or [], params)
    if remainder is not None:
        elements.append(remainder)
    return elements


def _subtract_nested(zones: list[DetectedElement]) -> None:
    """Bir radye çokgeninin içindeki küçük çokgenler (çukurlar) dış çokgenin alanından düşülür."""
    polys = [Polygon(z.points).buffer(0) for z in zones]
    for i, outer in enumerate(polys):
        if outer.area <= 0:
            continue
        cut = 0.0
        for j, inner in enumerate(polys):
            if i == j or inner.area <= 0 or inner.area >= outer.area:
                continue
            if outer.contains(inner.representative_point()) and outer.intersection(inner).area > 0.9 * inner.area:
                cut += inner.area
                if zones[j].thickness is None:
                    zones[j].thickness = zones[i].thickness
                zones[j].warnings.append("Radye içinde iç bölge (çukur); alanı dıştaki radyeden düşüldü")
        if cut > 1e-6:
            zones[i].area = max(zones[i].area - cut, 0.0)
            zones[i].warnings.append(f"İç bölgeler düşüldü: {cut:.1f} m²")


def _estimate_untagged_raft(zones: list[DetectedElement], labels: LabelIndex, supports: list[list],
                            params: DetectParams) -> DetectedElement | None:
    """Çokgen dışında kalan radye etiketleri varsa oturumdan çokgenleri düşerek kalan radye alanını tahmin eder."""
    zone_union = unary_union([Polygon(z.points).buffer(0) for z in zones]) if zones else None
    outside: list[tuple[SPoint, object]] = []
    for ent, lab in labels.items:
        # yalnız radye tipi adlar (RD1, R2, RADYE...); sürekli temel (TK/ST) ve kesitli etiketler değil
        if lab.type_hint != "foundation" or not lab.name or lab.has_dims:
            continue
        if not lab.name.upper().startswith("R"):
            continue
        pt = SPoint(ent.points[0])
        if zone_union is not None and zone_union.contains(pt):
            continue
        # etiketin kalınlık yazısı hemen yanındadır ("RD2" + "40cm"): en yakın kalınlık etiketi
        best, best_d = None, params.label_search_radius
        for ent2, lab2 in labels.items:
            if lab2.thickness is None or lab2.name:
                continue
            dd = pt.distance(SPoint(ent2.points[0]))
            if dd <= best_d:
                best, best_d = lab2, dd
        outside.append((pt, lab.merged_with(best) if best else lab))
    if not outside or not supports:
        return None
    thick = Counter(round(l.thickness, 3) for _, l in outside if l.thickness)
    names = Counter(l.name for _, l in outside if l.name)
    geoms = [Polygon(p).buffer(0) for p in supports if len(p) >= 3] + [pt for pt, _ in outside]
    if zone_union is not None:
        geoms.append(zone_union)
    try:
        hull = concave_hull(unary_union(geoms), ratio=0.35)
        footprint = hull.buffer(params.raft_margin, join_style=2)
        if zone_union is not None:
            footprint = footprint.difference(zone_union)
    except Exception:
        return None
    if footprint.is_empty or footprint.area < params.min_slab_area:
        return None
    # en büyük parça sınır olarak saklanır (görselleştirme için); alan tüm parçaların toplamı
    parts = list(footprint.geoms) if footprint.geom_type == "MultiPolygon" else [footprint]
    biggest = max(parts, key=lambda g: g.area)
    pts = [(x, y) for x, y in biggest.exterior.coords[:-1]]
    el = DetectedElement(etype="foundation", layer="(tahmin)", points=pts, subtype="raft",
                         area=float(footprint.area), perimeter=float(sum(p.exterior.length for p in parts)),
                         source="FOOTPRINT_ESTIMATE", confidence=0.5,
                         name=names.most_common(1)[0][0] if names else None)
    if thick:
        el.thickness = thick.most_common(1)[0][0]
    else:
        el.thickness = params.default_foundation_thickness
        el.warnings.append(f"Kalınlık etiketi yok; varsayılan {params.default_foundation_thickness*100:.0f} cm kullanıldı")
    el.label_raw = ", ".join(f"{l.raw}" for _, l in outside[:3])
    el.warnings.append(
        f"Radye dış sınırı çizilmemiş: kolon/perde dış hattından {params.raft_margin:.2f} m dışarı alınarak "
        f"tahmin edildi ({len(outside)} etiket çokgen dışında). Alanı gerekirse düzeltin."
    )
    return el


def _fill_strip(el: DetectedElement, lab, width: float, length: float, params: DetectParams) -> None:
    el.subtype = "strip"
    el.b = width
    el.length = length
    if lab and lab.has_dims:
        b_lab, h_lab = lab.b, lab.h
        if abs(b_lab - width) > abs(h_lab - width):
            b_lab, h_lab = h_lab, b_lab
        el.b, el.h = b_lab, h_lab
        el.confidence = max(el.confidence, 0.85)
    elif lab and lab.thickness:
        el.h = lab.thickness
        el.confidence = max(el.confidence, 0.8)
    else:
        el.h = params.default_foundation_thickness
        el.warnings.append(f"Kesit etiketi yok; yükseklik varsayılan {params.default_foundation_thickness*100:.0f} cm")
