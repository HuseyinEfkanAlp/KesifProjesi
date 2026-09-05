"""Kapı ve pencere tespiti (mimari).

 (a) kapı / pencere katmanlarındaki blok yerleşimleri (INSERT): her blok bir adet. Ölçü: yakın etiket ("P1 120/140"),
     yoksa blok adı ("PENCERE_120x140"), yoksa bloğun kutusu (uzun kenar = genişlik; yükseklik varsayılan).
 (b) blok olmayan etiketler: "P3 120/140" yazısı yakınında blok yoksa tek başına adet sayılır (düşük güven).
Kapı yüksekliği varsayılan 2.10 m, pencere 1.40 m (etiket yoksa); kullanıcı düzeltebilir.
"""
from __future__ import annotations

from shapely import STRtree
from shapely.geometry import Point as SPoint, Polygon

from ..geometry import min_area_rect
from ..labels_ext import OpeningLabel, opening_type_from_name, parse_opening_label, size_from_name
from ..loader import Drawing, Entity
from .base import DetectParams, DetectedElement

DEFAULT_HEIGHT = {"door": 2.10, "window": 1.40}
DEFAULT_WIDTH = {"door": 0.90, "window": 1.20}


def detect_openings(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams) -> list[DetectedElement]:
    """layers_by_type: {"door": [...], "window": [...]}"""
    labels: list[tuple[Entity, OpeningLabel]] = []
    for e in drawing.texts():
        lab = parse_opening_label(e.text, params.label_unit_scale)
        if lab.is_meaningful:
            labels.append((e, lab))
    pts = [SPoint(e.points[0]) for e, _ in labels]
    tree = STRtree(pts) if pts else None
    claimed: set[int] = set()
    elements: list[DetectedElement] = []

    def nearest_label(poly_pts, etype: str, radius: float) -> OpeningLabel | None:
        if tree is None or not poly_pts:
            return None
        poly = Polygon(poly_pts).buffer(0) if len(poly_pts) >= 3 else SPoint(poly_pts[0])
        best, best_d, best_i = None, None, None
        for i in tree.query(poly.buffer(radius + 1e-9)):
            i = int(i)
            if i in claimed:
                continue
            lab = labels[i][1]
            if lab.etype and lab.etype != etype:
                continue
            d = poly.distance(pts[i])
            if d <= radius and (best_d is None or d < best_d):
                best, best_d, best_i = lab, d, i
        if best_i is not None:
            claimed.add(best_i)
        return best

    for etype in ("door", "window"):
        layers = layers_by_type.get(etype, [])
        if not layers:
            continue
        for ins in drawing.inserts():
            if ins.layer not in layers:
                continue
            kind = opening_type_from_name(ins.block) or etype
            if kind != etype and layers_by_type.get(kind):
                continue  # kapı katmanına konmuş pencere bloğu kendi turunda sayılır
            el = DetectedElement(etype=etype, layer=ins.layer, points=list(ins.points), source="INSERT",
                                 handle=ins.handle, confidence=0.75, name=None, subtype=ins.block)
            width, height = None, None
            lab = nearest_label(ins.points, etype, params.label_search_radius)
            if lab:
                el.label_raw = lab.raw
                el.name = lab.name
                if lab.has_dims:
                    width, height = lab.width, lab.height
                    el.confidence = 0.95
            if width is None:
                bw, bh = size_from_name(ins.block, params.label_unit_scale)
                if bw:
                    width, height = bw, bh
                    el.confidence = max(el.confidence, 0.8)
            if width is None and len(ins.points) >= 3:
                long_side, short_side, _ = min_area_rect(ins.points)
                if 0.4 <= long_side <= 6.0:
                    width = long_side
                    el.warnings.append("Genişlik blok kutusundan alındı; etiket yok")
                    el.confidence = min(el.confidence, 0.6)
            if width is None:
                width = DEFAULT_WIDTH[etype]
                el.warnings.append(f"Ölçü bulunamadı; {width*100:.0f} cm varsayıldı")
                el.confidence = min(el.confidence, 0.5)
            if height is None:
                height = DEFAULT_HEIGHT[etype]
                el.warnings.append(f"Yükseklik etiketi yok; {height*100:.0f} cm varsayıldı")
            el.b, el.h = width, height
            el.area = width * height          # boşluk alanı (duvardan düşülür, pencerede cam alanı)
            if not el.name:
                el.name = ins.block
            elements.append(el)

        # (b) bloksuz etiketler: katmanda blok yoksa ya da etiket bloklardan uzaksa
        for i, (e, lab) in enumerate(labels):
            if i in claimed or lab.etype != etype or not lab.name:
                continue
            claimed.add(i)
            x, y = e.points[0]
            r = 0.3
            el = DetectedElement(etype=etype, layer=e.layer, points=[(x - r, y - r), (x + r, y - r), (x + r, y + r), (x - r, y + r)],
                                 source="TEXT", handle=e.handle, confidence=0.5, name=lab.name, label_raw=lab.raw)
            el.b = lab.width or DEFAULT_WIDTH[etype]
            el.h = lab.height or DEFAULT_HEIGHT[etype]
            el.area = el.b * el.h
            el.warnings.append("Blok bulunamadı; yalnızca etiketten sayıldı")
            if not lab.has_dims:
                el.warnings.append("Etikette ölçü yok; varsayılan ölçü kullanıldı")
            elements.append(el)
    return elements
