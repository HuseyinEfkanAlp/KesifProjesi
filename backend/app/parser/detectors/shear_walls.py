"""Perde tespiti: perde katmanlarındaki kapalı çokgenler (dikdörtgen, L, U şekilleri)."""
from __future__ import annotations

from ..geometry import min_area_rect, perimeter, polygon_area
from ..loader import Drawing
from .base import DetectParams, DetectedElement, LabelIndex, dedupe_elements, polygons_on_layers


def detect_shear_walls(drawing: Drawing, layers: list[str], labels: LabelIndex, params: DetectParams) -> list[DetectedElement]:
    elements: list[DetectedElement] = []
    for ent in polygons_on_layers(drawing, layers):
        area = polygon_area(ent.points)
        if area < params.min_column_area:
            continue
        per = perimeter(ent.points)
        long_side, short_side, _ = min_area_rect(ent.points)
        el = DetectedElement(
            etype="shear_wall", layer=ent.layer, points=list(ent.points),
            area=area, perimeter=per, source=ent.source, handle=ent.handle, confidence=0.7,
        )
        lab = labels.find(ent.points, "shear_wall", area=area)
        thickness = short_side
        if lab:
            el.label_raw = lab.raw
            el.name = lab.name
            if lab.has_dims:
                thickness = min(lab.b, lab.h)
                el.confidence = 0.9
            else:
                el.confidence = 0.8
        else:
            el.warnings.append("Etiket bulunamadı; kalınlık çizimden alındı")
        # L/U şekilli perdelerde uzunluk = (çevre - 2*kalınlık)/2 ; dikdörtgende uzun kenara eşit
        length = max((per - 2 * thickness) / 2.0, long_side)
        el.b = thickness
        el.h = length
        el.length = length
        # dikdörtgen ise alanı kalınlık*uzunluk ile tutarlı olmalı
        if abs(area - thickness * length) / max(area, 1e-9) > 0.25:
            el.warnings.append("Şekil dikdörtgen değil; alan çizimden, uzunluk çevreden hesaplandı")
        elements.append(el)
    return dedupe_elements(elements)
