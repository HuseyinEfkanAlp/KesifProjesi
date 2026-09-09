"""Kiriş tespiti.

İki yol:
 (a) kiriş katmanındaki kapalı çokgenler (dikdörtgen) -> uzun kenar = uzunluk, kısa kenar = b
 (b) kiriş katmanındaki paralel çizgi çiftleri -> aralık = b, örtüşme = uzunluk.
     Kolon geçişlerinde kesilen parçalar aynı hizada ise birleştirilir; sonra üzerindeki
     etiketlere ("K1001 (100/45)") göre kirişlere bölünür.
Kesit yüksekliği h etiketten gelir; etiket yoksa uyarı verilir.
Net uzunluk: kolon/perde içine giren kısım düşülür.
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Polygon

from ..geometry import min_area_rect, perimeter, polygon_area, segment_net_length, union_polygons
from ..loader import Drawing
from .base import (DetectParams, DetectedElement, LabelIndex, ParallelPair, dedupe_elements, find_parallel_pairs,
                   merge_collinear_pairs, polygons_on_layers, segments_on_layers)


def detect_beams(drawing: Drawing, layers: list[str], labels: LabelIndex, params: DetectParams,
                 supports: list[list] | None = None) -> list[DetectedElement]:
    """supports: kolon/perde çokgenleri (net uzunluk için düşülür)."""
    support_union = union_polygons(supports or [])
    elements: list[DetectedElement] = []

    # (a) kapalı çokgenler
    for ent in polygons_on_layers(drawing, layers):
        if ent.source == "LINES>LOOP":
            continue  # çizgi döngüleri kirişte güvenilmez; (b) ile ele alınır
        area = polygon_area(ent.points)
        long_side, short_side, _ = min_area_rect(ent.points)
        if not (params.beam_width_range[0] <= short_side <= params.beam_width_range[1]) or long_side < params.min_beam_length:
            continue
        el = DetectedElement(etype="beam", layer=ent.layer, points=list(ent.points), area=area,
                             perimeter=perimeter(ent.points), b=short_side, length=long_side,
                             source=ent.source, handle=ent.handle, confidence=0.6)
        _apply_label(el, labels, ent.points, params)
        el.length = _net_length_of_rect(ent.points, support_union, long_side)
        elements.append(el)

    # (b) paralel çizgi çiftleri -> hizalı parçaları birleştir -> etiketlere göre böl
    segs = segments_on_layers(drawing, layers)
    pairs = find_parallel_pairs(segs, params.beam_width_range, params.min_beam_length)
    runs = merge_collinear_pairs(pairs, gap_max=params.beam_merge_gap)
    for run in runs:
        for piece, lab in _split_run_by_labels(run, labels, params):
            el = DetectedElement(etype="beam", layer=piece.layer, points=piece.rect,
                                 area=piece.width * piece.length, perimeter=2 * (piece.width + piece.length),
                                 b=piece.width, length=piece.length, source="PARALLEL_LINES",
                                 handle=piece.handles[0], confidence=0.55)
            if lab is not None:
                _use_label(el, lab)
            else:
                el.warnings.append("Etiket bulunamadı; kiriş yüksekliği girilmeli")
                el.confidence = min(el.confidence, 0.5)
            el.length = segment_net_length(piece.center_a, piece.center_b, support_union)
            if el.length < params.min_beam_length:
                continue
            elements.append(el)

    elements = dedupe_elements(elements, tol=0.6)
    _deduct_intersections(elements)
    return elements


def _deduct_intersections(elements: list[DetectedElement]) -> None:
    """Kesişen kirişlerde ortak hacim iki kez sayılmasın: dar olan kirişin uzunluğundan (kesişim alanı / b) düşülür."""
    polys = []
    for e in elements:
        try:
            polys.append(Polygon(e.points).buffer(0) if len(e.points) >= 3 else None)
        except Exception:
            polys.append(None)
    from shapely import STRtree
    valid = [(i, g) for i, g in enumerate(polys) if g is not None and not g.is_empty]
    if len(valid) < 2:
        return
    tree = STRtree([g for _, g in valid])
    idx = [i for i, _ in valid]
    cut: dict[int, float] = {}
    seen: set[tuple[int, int]] = set()
    for k, (i, gi) in enumerate(valid):
        for j in tree.query(gi):
            j = int(j)
            jj = idx[j]
            if jj == i or (min(i, jj), max(i, jj)) in seen:
                continue
            seen.add((min(i, jj), max(i, jj)))
            inter = gi.intersection(polys[jj]).area
            if inter < 1e-4:
                continue
            a, b = elements[i], elements[jj]
            narrow = a if (a.b or 1.0) <= (b.b or 1.0) else b
            ni = i if narrow is a else jj
            cut[ni] = cut.get(ni, 0.0) + inter / max(narrow.b or 0.25, 0.05)
    for i, dl in cut.items():
        e = elements[i]
        if dl <= 0 or e.length <= 0:
            continue
        e.length = max(e.length - dl, 0.0)
        e.warnings.append(f"Kesişen kirişlerle ortak {dl:.2f} m düşüldü (beton çift sayılmasın)")


def _split_run_by_labels(run: ParallelPair, labels: LabelIndex, params: DetectParams):
    """Birleşik kiriş hattı üzerindeki kiriş etiketlerini bulur; etiket sayısı kadar parçaya böler."""
    poly = Polygon(run.rect).buffer(max(0.05, run.width * 0.25))
    ux = (run.center_b[0] - run.center_a[0]) / max(run.length, 1e-9)
    uy = (run.center_b[1] - run.center_a[1]) / max(run.length, 1e-9)
    found: list[tuple[float, int]] = []   # (eksen konumu, etiket indeksi)
    for d, i in labels._candidates(run.rect, radius=max(0.05, run.width * 0.25)):
        lab = labels.items[i][1]
        if lab.type_hint == "beam" and lab.name:
            pt = labels.items[i][0].points[0]
            t = (pt[0] - run.center_a[0]) * ux + (pt[1] - run.center_a[1]) * uy
            found.append((t, i))
    found.sort()
    if not found:
        # adı olmayan ama kesiti olan tek bir "(100/45)" etiketi olabilir
        lab = labels.find(run.rect, "beam", radius=max(0.05, run.width * 0.25), area=None)
        if lab is None:
            # etiket kirişin biraz uzağına yazılmış olabilir: daha geniş yarıçap, yalnız kiriş ipuçlu adlı etiket
            for d, i in labels._candidates(run.rect, radius=max(0.6, run.width)):
                cand = labels.items[i][1]
                if cand.type_hint == "beam" and cand.name and cand.has_dims:
                    labels.claimed.add(i)
                    lab = cand
                    break
        return [(run, lab)]
    if len(found) == 1:
        labels.claimed.add(found[0][1])
        lab = labels.items[found[0][1]][1]
        if not lab.has_dims:
            lab = lab.merged_with(labels.find(run.rect, "beam", radius=max(0.05, run.width * 0.25)))
        return [(run, lab)]
    pieces = []
    cuts = [0.0] + [(found[k][0] + found[k + 1][0]) / 2.0 for k in range(len(found) - 1)] + [run.length]
    for k, (_, i) in enumerate(found):
        lo, hi = cuts[k], cuts[k + 1]
        ca = (run.center_a[0] + ux * lo, run.center_a[1] + uy * lo)
        cb = (run.center_a[0] + ux * hi, run.center_a[1] + uy * hi)
        from .base import _rect_from_centerline
        piece = ParallelPair(ca, cb, run.width, run.layer, _rect_from_centerline(ca, cb, run.width), run.handles)
        labels.claimed.add(i)
        lab = labels.items[i][1]
        if not lab.has_dims:
            lab = lab.merged_with(labels.find(piece.rect, "beam", radius=max(0.05, run.width * 0.25)))
        pieces.append((piece, lab))
    return pieces


def _use_label(el: DetectedElement, lab) -> None:
    el.label_raw = lab.raw
    el.name = lab.name
    if lab.has_dims:
        b_lab, h_lab = lab.b, lab.h
        # kiriş etiketi b/h: genişlik çizimdeki aralığa yakın olan
        if el.b and abs(b_lab - el.b) > abs(h_lab - el.b):
            b_lab, h_lab = h_lab, b_lab
        if el.b and abs(b_lab - el.b) / el.b > 0.2:
            el.warnings.append(f"Etiket genişliği ({b_lab*100:.0f}) çizimdeki aralıkla ({el.b*100:.0f}) uyuşmuyor")
            el.confidence = min(el.confidence, 0.5)
        else:
            el.confidence = 0.9
        el.b, el.h = b_lab, h_lab
    else:
        el.confidence = max(el.confidence, 0.65)
        el.warnings.append("Etikette kesit yok; kiriş yüksekliği girilmeli")
    if el.h is None:
        el.confidence = min(el.confidence, 0.5)


def _apply_label(el: DetectedElement, labels: LabelIndex, polygon, params: DetectParams) -> None:
    lab = labels.find(polygon, "beam", radius=max(params.label_search_radius, 0.5))
    if lab:
        _use_label(el, lab)
    else:
        el.warnings.append("Etiket bulunamadı; kiriş yüksekliği girilmeli")
        el.confidence = min(el.confidence, 0.5)


def _net_length_of_rect(points, support_union, gross_length: float) -> float:
    """Dikdörtgen kirişin uzun ekseni boyunca merkez hattını alır ve destekleri düşer."""
    long_side, short_side, ang = min_area_rect(points)
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    best, chosen = 0.0, None
    body = Polygon(points).buffer(1e-6)
    for a in (ang, ang + math.pi / 2):
        ux, uy = math.cos(a), math.sin(a)
        pa = (cx - ux * long_side / 2, cy - uy * long_side / 2)
        pb = (cx + ux * long_side / 2, cy + uy * long_side / 2)
        inside = LineString([pa, pb]).intersection(body).length
        if inside > best:
            best, chosen = inside, (pa, pb)
    if chosen is None:
        return gross_length
    return segment_net_length(chosen[0], chosen[1], support_union)
