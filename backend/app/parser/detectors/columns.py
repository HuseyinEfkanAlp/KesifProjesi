"""Kolon tespiti: kolon katmanlarındaki kapalı çokgenler."""
from __future__ import annotations

from ..geometry import min_area_rect, perimeter, polygon_area
from ..loader import Drawing
from .base import DetectParams, DetectedElement, LabelIndex, dedupe_elements, polygons_on_layers


def detect_columns(drawing: Drawing, layers: list[str], labels: LabelIndex, params: DetectParams) -> list[DetectedElement]:
    elements: list[DetectedElement] = []
    for ent in polygons_on_layers(drawing, layers):
        area = polygon_area(ent.points)
        if area < params.min_column_area:
            continue
        long_side, short_side, _ = min_area_rect(ent.points)
        el = DetectedElement(
            etype="column", layer=ent.layer, points=list(ent.points),
            area=area, perimeter=perimeter(ent.points),
            b=short_side, h=long_side, source=ent.source, handle=ent.handle,
        )
        if area > params.max_column_area:
            el.warnings.append("Alan kolon için çok büyük; perde/temel olabilir")
            el.confidence = 0.3
        else:
            el.confidence = 0.7
        lab = labels.find(ent.points, "column")
        if lab:
            el.label_raw = lab.raw
            el.name = lab.name
            if lab.has_dims:
                geo_area = area
                lab_area = lab.b * lab.h
                if abs(geo_area - lab_area) / max(lab_area, 1e-9) < 0.15:
                    el.confidence = 0.95
                else:
                    el.warnings.append(
                        f"Etiket kesiti ({lab.b*100:.0f}/{lab.h*100:.0f}) çizim alanı ile uyuşmuyor"
                    )
                    el.confidence = 0.6
                # etiket boyutları asıl kabul edilir
                el.b, el.h = min(lab.b, lab.h), max(lab.b, lab.h)
            else:
                el.confidence = max(el.confidence, 0.8)
        else:
            el.warnings.append("Etiket bulunamadı; kesit çizimden alındı")
        if area > params.max_column_area:
            # kolon katmanına çizilmiş büyük bölge (döşeme/perde izi vb.): metraja girmesin, kullanıcı karar versin
            el.confidence = min(el.confidence, 0.3)
            el.b = el.h = None
        elements.append(el)
    return dedupe_elements(elements)
