"""Temel 2D geometri yardımcıları. Tüm koordinatlar metre cinsindendir."""
from __future__ import annotations

import math
from typing import Sequence

from shapely.geometry import LineString, Point as SPoint, Polygon
from shapely.ops import unary_union

Point = tuple[float, float]


def polygon_area(pts: Sequence[Point]) -> float:
    """Shoelace formülü ile kapalı çokgen alanı (mutlak değer)."""
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polyline_length(pts: Sequence[Point], closed: bool = False) -> float:
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for i in range(len(pts) - 1):
        total += math.dist(pts[i], pts[i + 1])
    if closed:
        total += math.dist(pts[-1], pts[0])
    return total


def perimeter(pts: Sequence[Point]) -> float:
    return polyline_length(pts, closed=True)


def centroid(pts: Sequence[Point]) -> Point:
    if len(pts) >= 3 and polygon_area(pts) > 1e-12:
        c = Polygon(pts).centroid
        return (c.x, c.y)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def point_in_polygon(pt: Point, pts: Sequence[Point]) -> bool:
    if len(pts) < 3:
        return False
    return Polygon(pts).buffer(0).contains(SPoint(pt))


def min_area_rect(pts: Sequence[Point]) -> tuple[float, float, float]:
    """Minimum alanlı çevreleyen dikdörtgen: (uzun kenar, kısa kenar, açı_rad).

    Kenar yönlerini deneyerek hesaplar; dikdörtgen/L/U şekilli statik elemanlar için yeterlidir.
    """
    if len(pts) < 2:
        return (0.0, 0.0, 0.0)
    best = None
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        ux, uy = dx / L, dy / L
        us = [p[0] * ux + p[1] * uy for p in pts]
        vs = [-p[0] * uy + p[1] * ux for p in pts]
        w = max(us) - min(us)
        h = max(vs) - min(vs)
        area = w * h
        if best is None or area < best[0] - 1e-12:
            best = (area, max(w, h), min(w, h), math.atan2(uy, ux))
    if best is None:
        return (0.0, 0.0, 0.0)
    return (best[1], best[2], best[3])


def union_polygons(polys: list[Sequence[Point]]):
    shapes = [Polygon(p).buffer(0) for p in polys if len(p) >= 3]
    return unary_union(shapes) if shapes else None


def segment_net_length(a: Point, b: Point, obstacles_union) -> float:
    """a-b doğru parçasının, birleşik engel geometrisi (kolon vb.) dışında kalan uzunluğu."""
    seg = LineString([a, b])
    if seg.length < 1e-9:
        return 0.0
    if obstacles_union is None or obstacles_union.is_empty:
        return seg.length
    return seg.length - seg.intersection(obstacles_union).length


def distance_point_to_polygon(pt: Point, pts: Sequence[Point]) -> float:
    if len(pts) >= 3:
        return Polygon(pts).buffer(0).distance(SPoint(pt))
    return LineString(pts).distance(SPoint(pt))


def bbox(pts: Sequence[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))
