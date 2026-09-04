import math

from app.parser.geometry import (min_area_rect, perimeter, point_in_polygon, polygon_area, segment_net_length,
                                 union_polygons)


def test_polygon_area_rect():
    assert polygon_area([(0, 0), (0.3, 0), (0.3, 0.6), (0, 0.6)]) == 0.18


def test_perimeter_rect():
    assert abs(perimeter([(0, 0), (0.3, 0), (0.3, 0.6), (0, 0.6)]) - 1.8) < 1e-9


def test_min_area_rect_rotated():
    ang = math.radians(30)
    c, s = math.cos(ang), math.sin(ang)
    base = [(0, 0), (2.5, 0), (2.5, 0.2), (0, 0.2)]
    rot = [(x * c - y * s, x * s + y * c) for x, y in base]
    long_side, short_side, _ = min_area_rect(rot)
    assert abs(long_side - 2.5) < 1e-6
    assert abs(short_side - 0.2) < 1e-6


def test_point_in_polygon():
    sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert point_in_polygon((0.5, 0.5), sq)
    assert not point_in_polygon((1.5, 0.5), sq)


def test_segment_net_length_subtracts_columns():
    cols = union_polygons([[(0, 0), (0.3, 0), (0.3, 0.6), (0, 0.6)], [(5, 0), (5.3, 0), (5.3, 0.6), (5, 0.6)]])
    # merkez hattı kolon merkezinden kolon merkezine: 0.15 -> 5.15, kolon içleri 0.15 + 0.15 düşülür
    assert abs(segment_net_length((0.15, 0.3), (5.15, 0.3), cols) - 4.7) < 1e-6
