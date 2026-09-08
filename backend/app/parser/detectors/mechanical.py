"""Mekanik / sıhhi / havalandırma / yangın pafta dedektörleri (sezgisel).

Boru:   boru katmanlarındaki hatlar (uç uca zincirlenir); çap etiketten ("Ø110 PVC", "DN65", "PPRC 32", '1 1/4"') ya da
        katman adından; sistem (PVC pis su / PPRC temiz su / çelik / bakır / PE / yangın) katman adı + etiketten -> katalog kodu.
Kanal:  kanal katmanlarındaki hatlar; boyut "600x400" (dikdörtgen) ya da "Ø315" (yuvarlak / flex). Çift çizgi çizilmişse
        paralel çift -> aralık = genişlik.
Cihaz:  cihaz / vitrifiye katmanlarındaki bloklar; kalem kodu blok ya da katman adından (menfez, vana, sprinkler, radyatör,
        fancoil, lavabo, klozet…). Tanınmayan blok "MEKANIK_CIHAZ" olarak sayılır (uyarıyla).

Her eleman meta.ksf_code taşır; keşifte katalog kalemi (poz, reçete, iş grubu) olarak yazılır.
"""
from __future__ import annotations

from shapely.geometry import LineString, Point as SPoint
from shapely import STRtree

from ..geometry import polyline_length
from ..labels_ext import MechLabel, mech_fixture_code, parse_mech_label, pipe_system
from ..loader import Drawing, Entity
from .base import DetectParams, DetectedElement, find_parallel_pairs, segments_on_layers
from .electrical import _chain, _line_entities, _thin_rect

DUCT_WIDTH_RANGE = (0.10, 3.0)
GENERIC_FIXTURE = "MEKANIK_CIHAZ"


class MechLabelIndex:
    def __init__(self, drawing: Drawing):
        self.items: list[tuple[Entity, MechLabel]] = []
        for e in drawing.texts():
            lab = parse_mech_label(e.text)
            if lab.is_meaningful:
                self.items.append((e, lab))
        self._pts = [SPoint(e.points[0]) for e, _ in self.items]
        self._tree = STRtree(self._pts) if self._pts else None

    def nearest(self, geom, kind: str, radius: float, used: set[int]) -> tuple[int, MechLabel] | None:
        if self._tree is None:
            return None
        best, best_d, best_i = None, None, -1
        for i in self._tree.query(geom.buffer(radius + 1e-9)):
            i = int(i)
            if i in used or self.items[i][1].kind != kind:
                continue
            d = geom.distance(self._pts[i])
            if d <= radius and (best_d is None or d < best_d):
                best, best_d, best_i = self.items[i][1], d, i
        return (best_i, best) if best is not None else None


def _element(kind: str, code: str, layer: str, points, length: float, spec: str | None, width: float | None,
             height: float | None, handle: str, conf: float, catalog_disc: str) -> DetectedElement:
    el = DetectedElement(etype=kind, layer=layer, points=points, length=length, b=width, h=height, subtype=spec,
                         source="LINES", handle=handle, confidence=conf, name=code)
    el.meta = {"ksf_code": code, "measure": "length", "spec": spec or "", "discipline": catalog_disc}
    return el


def detect_mech_lines(drawing: Drawing, layers: list[str], kind: str, labels: MechLabelIndex, params: DetectParams,
                      catalog) -> list[DetectedElement]:
    """kind: pipe | duct. Her hat zinciri bir eleman; sistem + çap / boyut etiketten ya da katmandan."""
    out: list[DetectedElement] = []
    if not layers:
        return out
    ents = [e for e in _line_entities(drawing, layers) if not e.source.startswith("INSERT")]   # blok içi çizgiler cihazdır, hat değil
    used_handles: set[str] = set()
    # çift çizgi kanal: paralel çiftler (genişlik = aralık)
    if kind == "duct":
        segs = [s for s in segments_on_layers(drawing, layers) if s.handle in {e.handle for e in ents}]
        seg_by_handle = {s.handle: s for s in segs if s.handle}
        for p in find_parallel_pairs(segs, DUCT_WIDTH_RANGE, params.min_line_length):
            sa, sb = seg_by_handle.get(p.handles[0]), seg_by_handle.get(p.handles[1])
            # çift çizgi kanal: iki çizgi aynı katmanda ve boyları örtüşmeli; yan yana iki ayrı hat çift sanılmaz
            if not sa or not sb or sa.layer != sb.layer or p.length < 0.8 * min(sa.length, sb.length):
                continue
            geom = LineString([p.center_a, p.center_b])
            hit = labels.nearest(geom, "duct", params.elec_label_radius * 2, set())
            lab = hit[1] if hit else None
            spec = lab.spec if lab and lab.spec else f"{round(p.width * 1000 / 50) * 50:.0f}"
            code = (lab.system if lab and lab.system else None) or "HAVA_KANAL"
            item = catalog.get(code)
            el = _element("duct", code, p.layer, p.rect, p.length, spec, p.width, lab.height if lab else None, p.handles[0],
                          0.75 if lab else 0.55, item.discipline if item else "HAV")
            el.area = p.width * p.length
            if not lab:
                el.warnings.append(f"Kanal boyutu etiketi yok; genişlik çizimden ({p.width*1000:.0f} mm)")
            out.append(el)
            used_handles.update(h for h in p.handles if h)
    remaining = [e for e in ents if e.handle not in used_handles and polyline_length(e.points, e.closed) > 1e-6]
    chains = [c for c in _chain(remaining, params.chain_tol)
              if sum(polyline_length(e.points, e.kind == "polygon") for e in c) >= params.min_line_length]
    used_labels: set[int] = set()
    for chain in chains:
        layer = chain[0].layer
        geom = LineString([pt for e in chain for pt in e.points])
        layer_lab = parse_mech_label(layer)
        hit = labels.nearest(geom, kind, params.elec_label_radius * 2, used_labels)
        lab = hit[1] if hit else None
        if hit:
            used_labels.add(hit[0])
        spec = (lab.spec if lab and lab.spec else None) or (layer_lab.spec if layer_lab.kind == kind else None)
        width = (lab.width if lab else None) or (layer_lab.width if layer_lab.kind == kind else None)
        height = (lab.height if lab else None) or (layer_lab.height if layer_lab.kind == kind else None)
        if kind == "pipe":
            code = pipe_system(layer) or (lab.system if lab else None) or pipe_system(lab.raw if lab else "") or "BORU_CELIK"
        else:
            code = (lab.system if lab and lab.system else None) or (layer_lab.system if layer_lab.kind == "duct" else None) or "HAVA_KANAL"
            if code == "HAVA_KANAL" and spec and "x" not in spec.lower():
                code = "HAVA_KANAL_YUVARLAK"
        item = catalog.get(code)
        length = sum(polyline_length(e.points, e.kind == "polygon") for e in chain)
        longest = max(chain, key=lambda e: polyline_length(e.points))
        el = _element(kind, code, layer, _thin_rect(longest.points, width or 0.1), length, spec, width, height, chain[0].handle,
                      0.85 if spec else 0.5, item.discipline if item else ("HAV" if kind == "duct" else "MEK"))
        el.area = 0.0
        if lab:
            el.label_raw = lab.raw
        if not spec:
            el.warnings.append(("Boru çapı" if kind == "pipe" else "Kanal boyutu") + " bulunamadı; etiket ya da katman adından okunamadı")
        if kind == "pipe" and not (pipe_system(layer) or (lab and lab.system)):
            el.warnings.append("Boru sistemi (PVC / PPRC / çelik…) anlaşılamadı; çelik boru sayıldı")
        out.append(el)
    return out


def detect_mech_fixtures(drawing: Drawing, layers: list[str], catalog, line_layers: list[str] | None = None) -> list[DetectedElement]:
    """layers: cihaz katmanları (her blok sayılır). line_layers: boru / kanal katmanları (yalnız adı tanınan bloklar: menfez, vana…)."""
    out: list[DetectedElement] = []
    line_layers = line_layers or []
    if not layers and not line_layers:
        return out
    for ins in drawing.inserts():
        if ins.layer in layers:
            code = mech_fixture_code(ins.block, ins.layer) or GENERIC_FIXTURE
        elif ins.layer in line_layers:
            code = mech_fixture_code(ins.block) or ""
            if not code:
                continue
        else:
            continue
        item = catalog.get(code)
        el = DetectedElement(etype="mech_fixture", layer=ins.layer, points=list(ins.points), name=item.name if item else code,
                             subtype=None, source="INSERT", handle=ins.handle, confidence=0.9 if code != GENERIC_FIXTURE else 0.55, count=1)
        el.meta = {"ksf_code": code, "measure": "count", "spec": "", "discipline": item.discipline if item else "MEK", "block": ins.block}
        if code == GENERIC_FIXTURE:
            el.warnings.append(f"Cihaz türü blok adından anlaşılamadı ({ins.block[:30]}); genel mekanik cihaz sayıldı")
        out.append(el)
    return out


def detect_mechanical(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams, catalog=None) -> list[DetectedElement]:
    from ...standard.catalog import Catalog
    catalog = catalog or Catalog()
    labels = MechLabelIndex(drawing)
    out: list[DetectedElement] = []
    out.extend(detect_mech_lines(drawing, layers_by_type.get("pipe", []), "pipe", labels, params, catalog))
    out.extend(detect_mech_lines(drawing, layers_by_type.get("duct", []), "duct", labels, params, catalog))
    out.extend(detect_mech_fixtures(drawing, layers_by_type.get("mech_fixture", []), catalog,
                                    line_layers=layers_by_type.get("pipe", []) + layers_by_type.get("duct", [])))
    return out
