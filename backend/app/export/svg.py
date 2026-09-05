"""Çizimin SVG önizlemesi: tüm çizgiler gri, tespit edilen elemanlar tipine göre renkli.

Görünüm alanı tespit edilen elemanların sınırına odaklanır (pafta/antet/detay paftaları plandan
kilometrelerce uzakta olabilir); bu alanın dışındaki çizgiler atlanır.
"""
from __future__ import annotations

from html import escape

from ..parser.loader import Drawing

COLORS = {
    "column": "#d62728",
    "shear_wall": "#9467bd",
    "beam": "#1f77b4",
    "slab": "#2ca02c",
    "foundation": "#ff7f0e",
    # mimari
    "wall": "#8c564b",
    "door": "#e377c2",
    "window": "#17becf",
    # elektrik
    "tray": "#bcbd22",
    "cable": "#ff9896",
    "conduit": "#c5b0d5",
    "fixture": "#7f7f7f",
}
MAX_ENTITIES = 60000


def _fmt(v: float) -> str:
    return f"{v:.3f}"


def _bbox(point_lists) -> tuple[float, float, float, float] | None:
    xs, ys = [], []
    for pts in point_lists:
        for p in pts:
            xs.append(p[0])
            ys.append(p[1])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def render_svg(drawing: Drawing, elements: list[dict], width: int = 1200) -> str:
    focus = _bbox([el.get("points") or [] for el in elements if len(el.get("points") or []) >= 3])
    if focus is None:
        focus = _bbox([e.points for e in drawing.entities])
    if focus is None:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'
    minx, miny, maxx, maxy = focus
    pad = max(maxx - minx, maxy - miny) * 0.04 + 0.5
    minx, maxx, miny, maxy = minx - pad, maxx + pad, miny - pad, maxy + pad
    w, h = maxx - minx, maxy - miny
    height = int(width * h / w) if w > 0 else width
    stroke = w / width * 1.0  # ~1 px

    def Y(y: float) -> float:  # SVG y aşağı doğru
        return maxy - y + miny

    def visible(pts) -> bool:
        return any(minx <= x <= maxx and miny <= y <= maxy for x, y in pts)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_fmt(minx)} {_fmt(miny)} {_fmt(w)} {_fmt(h)}" '
        f'width="{width}" height="{height}" data-unit="m">',
        f'<rect x="{_fmt(minx)}" y="{_fmt(miny)}" width="{_fmt(w)}" height="{_fmt(h)}" fill="#fafafa"/>',
        f'<g id="drawing" fill="none" stroke="#9a9a9a" stroke-width="{_fmt(stroke)}">',
    ]
    n = 0
    for e in drawing.entities:
        if e.kind in ("text", "insert") or not visible(e.points):
            continue
        n += 1
        if n > MAX_ENTITIES:
            break
        pts = " ".join(f"{_fmt(x)},{_fmt(Y(y))}" for x, y in e.points)
        tag = "polygon" if e.kind == "polygon" else "polyline"
        parts.append(f'<{tag} points="{pts}"/>')
    parts.append("</g>")

    parts.append(f'<g id="elements" stroke-width="{_fmt(stroke * 1.5)}" fill-opacity="0.35">')
    # büyük alanlar (döşeme/radye) altta, küçükler (kolon) üstte kalsın
    for el in sorted(elements, key=lambda e: -(e.get("area") or 0)):
        pts_list = el.get("points") or []
        if len(pts_list) < 3:
            continue
        color = COLORS.get(el.get("etype", ""), "#333")
        pts = " ".join(f"{_fmt(x)},{_fmt(Y(y))}" for x, y in pts_list)
        title = escape(f"{el.get('name') or ''} {el.get('etype')} ({el.get('layer')})")
        parts.append(
            f'<polygon class="el el-{el.get("etype")}" data-id="{el.get("id")}" points="{pts}" '
            f'fill="{color}" stroke="{color}"><title>{title}</title></polygon>'
        )
    parts.append("</g>")

    font = w / width * 10
    parts.append(f'<g id="texts" font-family="sans-serif" font-size="{_fmt(font)}" fill="#444">')
    for e in drawing.entities:
        if e.kind == "text" and e.text and visible(e.points):
            x, y = e.points[0]
            parts.append(f'<text x="{_fmt(x)}" y="{_fmt(Y(y))}">{escape(e.text[:40])}</text>')
    parts.append("</g></svg>")
    return "\n".join(parts)
