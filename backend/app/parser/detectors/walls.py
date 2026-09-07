"""Mimari duvar tespiti.

İki yol:
 (a) duvar katmanındaki kapalı çokgenler (tarama / kapalı polyline): dikdörtgene yakınsa kısa kenar = kalınlık,
     uzun kenar = uzunluk; L/U şekilli ya da tarama bölgesiyse kalınlık etiket/katman/varsayılandan, uzunluk = alan / kalınlık.
 (b) duvar katmanındaki paralel çizgi çiftleri: aralık = kalınlık, örtüşme = uzunluk. Kapı boşluklarında kesilen
     parçalar aynı hizadaysa birleştirilir (boşluk kapı/pencere alanıyla metrajda düşülür).
Malzeme (ytong / tuğla / bims / alçıpan...) katman adından ya da yakındaki etiketten ("YTONG 20") okunur.
"""
from __future__ import annotations

from shapely.geometry import Polygon

from ..geometry import min_area_rect, perimeter, polygon_area
from ..labels_ext import WallLabel, parse_wall_label, wall_material
from ..loader import Drawing
from .base import (DetectParams, DetectedElement, dedupe_elements, find_parallel_pairs, merge_collinear_pairs,
                   polygons_on_layers, segments_on_layers)


class WallLabelIndex:
    """Duvar etiketlerini ("YTONG 20", "20 cm TUĞLA") bir kez çözer, çokgene en yakınını verir."""

    def __init__(self, drawing: Drawing, params: DetectParams):
        self.items: list[tuple[tuple[float, float], WallLabel]] = []
        for e in drawing.texts():
            lab = parse_wall_label(e.text, params.label_unit_scale)
            if lab.is_meaningful:
                self.items.append((e.points[0], lab))

    def find(self, polygon: list, radius: float) -> WallLabel | None:
        if not self.items or len(polygon) < 3:
            return None
        poly = Polygon(polygon).buffer(0)
        if poly.is_empty:
            return None
        best, best_d = None, None
        from shapely.geometry import Point as SPoint
        for pt, lab in self.items:
            d = poly.distance(SPoint(pt))
            if d <= radius and (best_d is None or d < best_d):
                best, best_d = lab, d
        return best


def detect_walls(drawing: Drawing, layers: list[str], params: DetectParams) -> list[DetectedElement]:
    wall_labels = WallLabelIndex(drawing, params)
    elements: list[DetectedElement] = []
    lo, hi = params.wall_thickness_range

    # (a) kapalı çokgenler
    for ent in polygons_on_layers(drawing, layers):
        if ent.source == "LINES>LOOP":
            continue  # çizgi döngüleri (b) ile ele alınır
        area = polygon_area(ent.points)
        if area < params.min_wall_area:
            continue
        long_side, short_side, _ = min_area_rect(ent.points)
        per = perimeter(ent.points)
        if per > 0 and 2 * area / per > hi and short_side > hi:
            continue   # kalın "duvar" değil, bölge çokgeni (bina sınırı / mahal); duvar sayılmaz
        el = DetectedElement(etype="wall", layer=ent.layer, points=list(ent.points), area=area,
                             perimeter=perimeter(ent.points), source=ent.source, handle=ent.handle, confidence=0.6)
        lab = wall_labels.find(ent.points, params.label_search_radius)
        material = wall_material(ent.layer) or (lab.material if lab else None)
        thickness = lab.thickness if lab and lab.thickness else None
        rect_like = abs(area - long_side * short_side) / max(area, 1e-9) < 0.15 and lo <= short_side <= hi
        if rect_like:
            el.b = thickness or short_side
            el.length = long_side
            el.confidence = 0.8
        else:
            el.b = thickness or params.default_wall_thickness
            el.length = area / el.b
            el.warnings.append("Duvar bölgesi dikdörtgen değil; uzunluk = alan / kalınlık")
            el.confidence = 0.55
            if thickness is None:
                el.warnings.append(f"Kalınlık etiketi yok; {params.default_wall_thickness*100:.0f} cm alındı")
        if lab:
            el.label_raw = lab.raw
            el.confidence = min(0.95, el.confidence + 0.1)
        el.subtype = material
        elements.append(el)

    # (b) paralel çizgi çiftleri
    segs = segments_on_layers(drawing, layers)
    pairs = find_parallel_pairs(segs, params.wall_thickness_range, params.min_wall_length)
    runs = merge_collinear_pairs(pairs, gap_max=params.wall_merge_gap, width_tol=0.02)
    for run in runs:
        el = DetectedElement(etype="wall", layer=run.layer, points=run.rect, area=run.width * run.length,
                             perimeter=2 * (run.width + run.length), b=run.width, length=run.length,
                             source="PARALLEL_LINES", handle=run.handles[0], confidence=0.7)
        lab = wall_labels.find(run.rect, max(params.label_search_radius, run.width * 3))
        material = wall_material(run.layer) or (lab.material if lab else None)
        if lab:
            el.label_raw = lab.raw
            if lab.thickness and abs(lab.thickness - run.width) / run.width > 0.25:
                el.warnings.append(f"Etiket kalınlığı ({lab.thickness*100:.0f}) çizimdeki aralıkla ({run.width*100:.0f}) uyuşmuyor")
            el.confidence = 0.85
        el.subtype = material
        elements.append(el)

    for el in elements:
        if el.subtype is None:
            el.warnings.append("Duvar malzemesi bilinmiyor (katman/etiket); 'duvar' olarak listelendi")
    return dedupe_elements(elements, tol=0.6)
