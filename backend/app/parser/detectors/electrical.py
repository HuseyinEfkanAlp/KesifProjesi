"""Elektrik pafta dedektörleri: kablo tavası, kablo, boru (hat uzunlukları) ve armatür/priz/anahtar (adet).

Tava:   tava katmanındaki polyline / çizgi hatları. Çift çizgi çizilmişse paralel çift -> aralık = genişlik.
        Boyut ("200x60") en yakın etiketten ya da katman adından ("E-TAVA-200x60").
Kablo:  kablo katmanındaki polyline / çizgi hatları; kesit ("NYY 4x16") en yakın etiketten ya da katman adından.
        Aynı katmandaki uç uca değen parçalar tek hat sayılır (etiket hat üzerinde bir kez yazılır).
Boru:   boru katmanındaki hatlar; çap ("Ø20 PVC") etiket/katmandan.
Armatür: armatür katmanlarındaki blok yerleşimleri; kategori blok/katman adından (priz, anahtar, armatür...).
"""
from __future__ import annotations

import math

from shapely import STRtree
from shapely.geometry import LineString, Point as SPoint

from ..geometry import polyline_length
from ..labels_ext import ElecLabel, fixture_category, parse_elec_label
from ..loader import Drawing, Entity
from .base import DetectParams, DetectedElement, _rect_from_centerline, find_parallel_pairs, segments_on_layers

LINE_KINDS = {"tray": "tava", "cable": "kablo", "conduit": "boru"}


class ElecLabelIndex:
    def __init__(self, drawing: Drawing, params: DetectParams):
        self.items: list[tuple[Entity, ElecLabel]] = []
        for e in drawing.texts():
            lab = parse_elec_label(e.text, params.elec_label_unit_scale)
            if lab.is_meaningful:
                self.items.append((e, lab))
        self._pts = [SPoint(e.points[0]) for e, _ in self.items]
        self._tree = STRtree(self._pts) if self._pts else None

    def find(self, geom, kind: str, radius: float) -> ElecLabel | None:
        if self._tree is None:
            return None
        best, best_d = None, None
        for i in self._tree.query(geom.buffer(radius + 1e-9)):
            i = int(i)
            lab = self.items[i][1]
            if lab.kind != kind:
                continue
            d = geom.distance(self._pts[i])
            if d <= radius and (best_d is None or d < best_d):
                best, best_d = lab, d
        return best

    def all_of(self, kind: str) -> list[tuple[Entity, ElecLabel]]:
        return [(e, l) for e, l in self.items if l.kind == kind]


def _line_entities(drawing: Drawing, layers: list[str]) -> list[Entity]:
    return [e for e in drawing.entities if e.layer in layers and e.kind in ("line", "polyline", "polygon")]


def _chain(entities: list[Entity], tol: float) -> list[list[Entity]]:
    """Uç noktaları birbirine değen parçaları zincirler (tek hat = tek eleman)."""
    if not entities:
        return []
    ends: list[SPoint] = []
    for e in entities:
        ends.append(SPoint(e.points[0]))
        ends.append(SPoint(e.points[-1]))
    tree = STRtree(ends)
    parent = list(range(len(entities)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # dallanma noktası (bir noktada ≥ 3 parça ucu): zincir orada kesilir, her dal ayrı hat (farklı kesit / iniş payı)
    touching: list[set[int]] = []
    for k, pt in enumerate(ends):
        i = k // 2
        touching.append({int(j) // 2 for j in tree.query(pt.buffer(tol)) if int(j) // 2 != i and pt.distance(ends[int(j)]) <= tol})
    for k, pt in enumerate(ends):
        i = k // 2
        if len(touching[k]) >= 2:
            continue
        for other in touching[k]:
            # karşı ucun da dallanma noktası olmaması gerekir
            if any(len(touching[m]) >= 2 for m in (2 * other, 2 * other + 1) if pt.distance(ends[m]) <= tol):
                continue
            ri, rj = find(i), find(other)
            if ri != rj:
                parent[ri] = rj
    groups: dict[int, list[Entity]] = {}
    for i, e in enumerate(entities):
        groups.setdefault(find(i), []).append(e)
    return list(groups.values())


def _thin_rect(pts, width: float) -> list:
    if len(pts) >= 3 and pts[0] != pts[-1]:
        return list(pts)
    return _rect_from_centerline(pts[0], pts[-1], max(width, 0.05)) if len(pts) >= 2 else list(pts)


def detect_lines(drawing: Drawing, layers: list[str], kind: str, labels: ElecLabelIndex,
                 params: DetectParams) -> list[DetectedElement]:
    """kind: tray | cable | conduit. Her hat (zincir) bir eleman; uzunluk = parça uzunlukları toplamı."""
    elements: list[DetectedElement] = []
    if not layers:
        return elements
    ents = _line_entities(drawing, layers)
    used: set[int] = set()

    # çift çizgi tava: paralel çiftler
    if kind == "tray":
        segs = segments_on_layers(drawing, layers)
        pairs = find_parallel_pairs(segs, params.tray_width_range, params.min_line_length)
        handles = {h for p in pairs for h in p.handles if h}
        for p in pairs:
            geom = LineString([p.center_a, p.center_b])
            lab = labels.find(geom, "tray", params.elec_label_radius)
            spec = lab.spec if lab and lab.spec else f"{round(p.width * 1000 / 50) * 50:.0f}"
            el = DetectedElement(etype="tray", layer=p.layer, points=p.rect, area=p.width * p.length,
                                 length=p.length, b=p.width, h=lab.height if lab else None, subtype=spec,
                                 source="PARALLEL_LINES", handle=p.handles[0], confidence=0.75 if lab else 0.55)
            if lab:
                el.label_raw = lab.raw
            else:
                el.warnings.append(f"Tava boyutu etiketi yok; genişlik çizimden ({p.width*1000:.0f} mm)")
            elements.append(el)
        for i, e in enumerate(ents):
            if e.handle and e.handle in handles:
                used.add(i)

    layer_spec = {l: parse_elec_label(l, params.elec_label_unit_scale) for l in layers}
    remaining = [e for i, e in enumerate(ents) if i not in used and polyline_length(e.points, e.closed) > 1e-6]
    chains = [c for c in _chain(remaining, params.chain_tol)
              if sum(polyline_length(e.points, e.kind == "polygon") for e in c) >= params.min_line_length]
    geoms = [LineString([pt for e in c for pt in e.points]) for c in chains]

    # Etiket -> hat ataması: her etiket bir kez kullanılır, en yakın çift önce (katman adında kesit varsa etiket aranmaz)
    assigned: dict[int, ElecLabel] = {}
    cands: list[tuple[float, int, int]] = []
    for ci, (chain, geom) in enumerate(zip(chains, geoms)):
        ls = layer_spec.get(chain[0].layer)
        if ls and ls.kind == kind and ls.spec:
            continue
        for li, (ent, lab) in enumerate(labels.items):
            if lab.kind != kind:
                continue
            d = geom.distance(SPoint(ent.points[0]))
            if d <= params.elec_label_radius:
                cands.append((d, ci, li))
    cands.sort()
    used_labels: set[int] = set()
    for d, ci, li in cands:
        if ci in assigned or li in used_labels:
            continue
        assigned[ci] = labels.items[li][1]
        used_labels.add(li)

    for ci, chain in enumerate(chains):
        length = sum(polyline_length(e.points, e.kind == "polygon") for e in chain)
        ls = layer_spec.get(chain[0].layer)
        lab = assigned.get(ci)
        spec = (ls.spec if ls and ls.kind == kind and ls.spec else None) or (lab.spec if lab and lab.spec else None)
        longest = max(chain, key=lambda e: polyline_length(e.points))
        width = (lab.width if lab and lab.width else None) or (ls.width if ls and ls.width else None)
        el = DetectedElement(etype=kind, layer=chain[0].layer, points=_thin_rect(longest.points, width or 0.1),
                             length=length, b=width, h=lab.height if lab and lab.height else None, subtype=spec,
                             source="LINES", handle=chain[0].handle, confidence=0.85 if spec else 0.5)
        el.area = 0.0
        if lab:
            el.label_raw = lab.raw
        if not spec:
            el.warnings.append({"tray": "Tava boyutu bulunamadı", "cable": "Kablo kesiti bulunamadı",
                                "conduit": "Boru çapı bulunamadı"}[kind] + "; etiket ya da katman adından okunamadı")
        elements.append(el)
    return elements


def detect_fixtures(drawing: Drawing, layers: list[str], params: DetectParams) -> list[DetectedElement]:
    elements: list[DetectedElement] = []
    if not layers:
        return elements
    for ins in drawing.inserts():
        if ins.layer not in layers:
            continue
        cat = fixture_category(ins.block, ins.layer) or "diger"
        el = DetectedElement(etype="fixture", layer=ins.layer, points=list(ins.points), name=ins.block, subtype=cat,
                             source="INSERT", handle=ins.handle, confidence=0.9 if cat != "diger" else 0.6, count=1)
        if cat == "diger":
            el.warnings.append("Kategori blok/katman adından anlaşılamadı")
        elements.append(el)
    # blok olmayan semboller: aynı katmandaki küçük daireler (polygon, ~armatür simgesi)
    if not elements:
        for e in drawing.entities:
            if e.layer in layers and e.kind == "polygon" and len(e.points) >= 8:
                xs = [p[0] for p in e.points]
                ys = [p[1] for p in e.points]
                size = max(max(xs) - min(xs), max(ys) - min(ys))
                if 0.05 <= size <= 0.8:
                    cat = fixture_category(e.layer) or "diger"
                    el = DetectedElement(etype="fixture", layer=e.layer, points=list(e.points), name=e.layer, subtype=cat,
                                         source=e.source, handle=e.handle, confidence=0.5, count=1)
                    el.warnings.append("Blok değil; daire simgesi sayıldı")
                    elements.append(el)
    return elements


def detect_electrical(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams) -> list[DetectedElement]:
    labels = ElecLabelIndex(drawing, params)
    out: list[DetectedElement] = []
    for kind in ("tray", "cable", "conduit"):
        out.extend(detect_lines(drawing, layers_by_type.get(kind, []), kind, labels, params))
    out.extend(detect_fixtures(drawing, layers_by_type.get("fixture", []), params))
    return out
