"""Parapet tespiti (kalıp planı): parapet katmanındaki çizgi / polyline / tarama sınırı hattı = uzunluk;
kesit "Parapet (b/h)" etiketinden (b genişlik, h yükseklik, cm). Çift çizgi çizilmişse aralık = b.
Beton = b × h × L, kalıp = 2 × h × L (engine). Etiket yoksa varsayılan 20/15 cm (uyarı, düşük güven)."""
from __future__ import annotations

from shapely.geometry import LineString, Polygon

from ..geometry import polyline_length
from ..loader import Drawing
from .base import DetectParams, DetectedElement, LabelIndex, find_parallel_pairs, merge_collinear_pairs, segments_on_layers

PARAPET_WIDTH_RANGE = (0.08, 0.45)
DEFAULT_B, DEFAULT_H = 0.20, 0.15


def detect_parapets(drawing: Drawing, layers: list[str], labels: LabelIndex, params: DetectParams) -> list[DetectedElement]:
    out: list[DetectedElement] = []
    if not layers:
        return out
    segs = segments_on_layers(drawing, layers)
    used: set[str] = set()
    pairs = find_parallel_pairs(segs, PARAPET_WIDTH_RANGE, params.min_line_length)
    for run in merge_collinear_pairs(pairs, gap_max=0.6, width_tol=0.03):
        el = DetectedElement(etype="parapet", layer=run.layer, points=run.rect, area=run.width * run.length,
                             perimeter=2 * (run.width + run.length), b=run.width, length=run.length,
                             source="PARALLEL_LINES", handle=run.handles[0], confidence=0.6)
        _label(el, labels, run.rect)
        out.append(el)
        used.update(h for h in run.handles if h)
    # tek çizgi / polyline / kapalı tarama sınırı: uzunluk (kapalı ince çokgende çevre / 2)
    for e in drawing.entities:
        if e.layer not in layers or e.kind not in ("line", "polyline", "polygon") or e.handle in used:
            continue
        L = polyline_length(e.points, e.kind == "polygon")
        if e.kind == "polygon":
            L = L / 2.0    # ince kapalı dış hat: iki uzun kenar
        if L < params.min_line_length:
            continue
        pts = list(e.points) if len(e.points) >= 3 else list(LineString(e.points).buffer(0.1, cap_style=2).exterior.coords[:-1])
        el = DetectedElement(etype="parapet", layer=e.layer, points=pts, length=L, source=e.source, handle=e.handle, confidence=0.5)
        _label(el, labels, pts)
        out.append(el)
    return out


def _label(el: DetectedElement, labels: LabelIndex, pts) -> None:
    best = None
    for d, i in labels._candidates(pts, radius=1.5):
        lab = labels.items[i][1]
        if lab.type_hint == "parapet" and lab.has_dims:
            best = lab
            labels.claimed.add(i)
            break
    if best:
        el.label_raw = best.raw
        el.name = "Parapet"
        b, h = best.b, best.h
        if el.b and abs(h - el.b) < abs(b - el.b):
            b, h = h, b
        el.b, el.h = b, h
        el.confidence = max(el.confidence, 0.85)
    else:
        el.b = el.b or DEFAULT_B
        el.h = DEFAULT_H
        el.warnings.append(f"Parapet kesit etiketi yok; {DEFAULT_B*100:.0f}/{DEFAULT_H*100:.0f} cm varsayıldı")
        el.confidence = min(el.confidence, 0.45)
    el.area = (el.b or 0.0) * el.length
