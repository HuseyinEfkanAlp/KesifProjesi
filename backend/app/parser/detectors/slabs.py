"""Döşeme tespiti.

 (a) Döşeme katmanındaki kapalı çokgenler (brüt alan).
 (b) Döşeme çokgeni yoksa (Türkçe kalıp planlarında yaygın): kiriş çizgileri + kolon/perde sınırlarından
     kapalı yüzeyler (paneller) üretilir; içinde döşeme etiketi ("D1000", "d=12") olan yüzey döşemedir.
     Bu alan kirişler arası NET alandır; subtype="net" işaretlenir ve metrajda kiriş tam yükseklikle alınır.
Boşluk (şaft) çokgenleri döşeme alanından düşülür.
"""
from __future__ import annotations

from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..geometry import perimeter, polygon_area
from ..loader import Drawing
from .base import (DetectParams, DetectedElement, LabelIndex, Segment, dedupe_elements, faces_from_network,
                   polygons_on_layers)


def detect_slabs(drawing: Drawing, layers: list[str], labels: LabelIndex, params: DetectParams,
                 network_segments: list[Segment] | None = None, supports: list[list] | None = None,
                 holes: list[list] | None = None) -> list[DetectedElement]:
    hole_union = unary_union([Polygon(h).buffer(0) for h in (holes or []) if len(h) >= 3]) if holes else None
    elements: list[DetectedElement] = []

    # (a) çokgenler
    for ent in polygons_on_layers(drawing, layers):
        area = polygon_area(ent.points)
        if area < params.min_slab_area:
            continue
        el = _make(ent.layer, list(ent.points), area, ent.source, ent.handle, labels, params, hole_union)
        elements.append(el)
    elements = dedupe_elements(elements)

    # (b) kiriş ağından paneller
    if not elements and network_segments:
        faces = faces_from_network(network_segments, supports or [], snap=params.support_snap)
        for face in faces:
            area = face.area
            if area < params.min_slab_area:
                continue
            pts = [(x, y) for x, y in face.exterior.coords[:-1]]
            # yüzeyin içinde döşeme etiketi olmalı (kiriş gövdeleri, dış çevre vb. elenir)
            lab = labels.find(pts, "slab", radius=0.0, claim=False, require_hint=True)
            if lab is None:
                continue
            n_labels = 1
            big = area > params.max_slab_area
            if big:
                n_labels = labels.count_named(pts, "slab")
            el = _make("(kiriş ağı)", pts, area, "BEAM_NETWORK", "", labels, params, hole_union)
            el.subtype = "net"
            if big and n_labels >= 2:
                el.warnings.append(f"Birleşik panel: {n_labels} döşeme etiketi tek yüzeyde (kiriş çizgileri hücreleri kapatmıyor); "
                                   "alan içindeki kiriş gövdeleri de dahil")
                el.confidence = min(el.confidence, 0.6)
            elif big:
                # tek etiketli büyük panel (otopark / bodrum döşemesi): atılmaz, düşük güvenle alınır; sınır kontrol edilmeli
                el.warnings.append(f"Büyük panel ({area:,.0f} m², tek etiket): sınırını kontrol edin (dış çerçeve çizgisi hücreye karışmış "
                                   "olabilir); metraj dışı bırakıldı, gerçek döşemeyse listeden açın")
                el.confidence = min(el.confidence, 0.35)
            elements.append(el)
    return elements


def _make(layer, pts, area, source, handle, labels: LabelIndex, params: DetectParams, hole_union) -> DetectedElement:
    el = DetectedElement(etype="slab", layer=layer, points=pts, area=area, perimeter=perimeter(pts),
                         source=source, handle=handle, confidence=0.6)
    lab = labels.find(pts, "slab", radius=0.0)  # döşeme etiketi bölgenin içindedir
    if lab is None:
        lab = labels.find(pts, "slab", radius=params.label_search_radius, require_hint=True)
    if lab:
        el.label_raw = lab.raw
        el.name = lab.name
        if lab.thickness:
            el.thickness = lab.thickness
            el.confidence = 0.9
        else:
            # salt kesit yazısı ("(100/100)": yüzeyin içindeki kolon kesiti) döşeme kalınlığı DEĞİLDİR; kalınlık yalnız d= / h= / "15cm"
            el.confidence = 0.75
    if el.thickness is None:
        el.thickness = params.default_slab_thickness
        el.warnings.append(f"Kalınlık etiketi yok; varsayılan {params.default_slab_thickness*100:.0f} cm kullanıldı")
    if hole_union is not None and not hole_union.is_empty:
        cut = Polygon(pts).buffer(0).intersection(hole_union).area
        if cut > 1e-6:
            el.area = max(area - cut, 0.0)
            el.warnings.append(f"Boşluk düşüldü: {cut:.2f} m²")
    return el
