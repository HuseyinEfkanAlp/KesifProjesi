"""Dedektörlerin ortak veri yapıları ve yardımcıları."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely import STRtree
from shapely.geometry import LineString, Point as SPoint, Polygon
from shapely.ops import polygonize, unary_union

from ..geometry import Point
from ..loader import Drawing, Entity
from ..text_parser import Label, parse_label


@dataclass
class DetectParams:
    label_unit_scale: float = 0.01          # etiketlerdeki sayılar cm
    label_search_radius: float = 1.5        # etiket arama yarıçapı (m)
    default_slab_thickness: float = 0.15
    default_foundation_thickness: float = 0.50
    beam_width_range: tuple[float, float] = (0.12, 1.50)   # paralel çizgi çifti kiriş genişliği aralığı
    strip_width_range: tuple[float, float] = (0.30, 3.00)  # sürekli temel genişliği aralığı
    min_beam_length: float = 0.30
    beam_merge_gap: float = 1.60            # aynı doğrultudaki kiriş parçalarını birleştirme boşluğu (kolon geçişi)
    min_column_area: float = 0.02           # m² (15x15 altı kolon değildir)
    max_column_area: float = 4.0            # m² (üstü perde/temel)
    min_slab_area: float = 1.0              # m²
    max_slab_area: float = 400.0            # m² (üstü: birden çok döşeme etiketi içeriyorsa birleşik panel, yoksa dış çevre)
    support_snap: float = 0.05              # m: döşeme hücreleri için kolon/perde tamponu
    raft_margin: float = 1.0                # m: radye dış sınırı çizilmemişse kolon/perde dış hattına eklenen pay
    raft_line_snap: float = 2.5             # m: temel bölge sınır çizgilerindeki boşluklar bu kadar ise köprülenir (gerçek çizimde 2 m görüldü)
    # mimari
    wall_thickness_range: tuple[float, float] = (0.05, 0.60)   # duvar kalınlığı aralığı (paralel çizgi çifti)
    default_wall_thickness: float = 0.20
    min_wall_length: float = 0.30
    min_wall_area: float = 0.05             # m² (plan alanı)
    wall_merge_gap: float = 1.30            # kapı boşluğu: aynı hizadaki duvar parçaları birleştirilir
    # elektrik
    elec_label_unit_scale: float = 0.001    # etiketlerdeki sayılar mm
    elec_label_radius: float = 0.8          # hat etiketi arama yarıçapı (m); etiket hattın hemen üstünde yazılır
    tray_width_range: tuple[float, float] = (0.05, 0.80)
    min_line_length: float = 0.20
    chain_tol: float = 0.02                 # uç uca değen hat parçalarını zincirleme toleransı (m)


@dataclass
class DetectedElement:
    etype: str                          # column | shear_wall | beam | slab | foundation | wall | door | window | tray | cable | conduit | fixture
    layer: str
    points: list[Point]                 # çokgen sınırı (kiriş için dikdörtgen)
    name: str | None = None
    subtype: str | None = None          # foundation: raft | strip ; slab: net ; wall: malzeme ; tray/cable/conduit: boyut/kesit ; fixture: kategori
    b: float | None = None              # kesit genişliği (m)
    h: float | None = None              # kesit yüksekliği (m)
    thickness: float | None = None      # döşeme/radye kalınlığı (m)
    area: float = 0.0                   # plan alanı (m²)
    length: float = 0.0                 # kiriş/perde/sürekli temel uzunluğu (m)
    perimeter: float = 0.0
    count: int = 1
    confidence: float = 0.5
    warnings: list[str] = field(default_factory=list)
    label_raw: str | None = None
    source: str = ""
    handle: str = ""

    def to_dict(self) -> dict:
        return {
            "etype": self.etype, "layer": self.layer, "name": self.name, "subtype": self.subtype,
            "b": self.b, "h": self.h, "thickness": self.thickness, "area": self.area,
            "length": self.length, "perimeter": self.perimeter, "count": self.count,
            "confidence": self.confidence, "warnings": self.warnings, "label_raw": self.label_raw,
            "source": self.source, "handle": self.handle,
            "points": [[round(x, 4), round(y, 4)] for x, y in self.points],
        }


class LabelIndex:
    """Çizimdeki tüm yazıları bir kez çözümler; elemanlara en yakın uygun etiketleri verir.

    Ad ("S1001") ve kesit ("(100/100)") ayrı yazılarda olabilir; find() bunları birleştirir.
    """

    def __init__(self, drawing: Drawing, params: DetectParams):
        self.params = params
        self.items: list[tuple[Entity, Label]] = []
        for e in drawing.texts():
            if not e.text:
                continue
            lab = parse_label(e.text, params.label_unit_scale)
            if lab.is_meaningful:
                self.items.append((e, lab))
        self.claimed: set[int] = set()
        self._pts = [SPoint(e.points[0]) for e, _ in self.items]
        self._tree = STRtree(self._pts) if self._pts else None

    def _candidates(self, polygon: list[Point], radius: float) -> list[tuple[float, int]]:
        """(uzaklık, indeks) listesi; çokgenin içindekiler uzaklık 0."""
        if self._tree is None or len(polygon) < 3:
            return []
        poly = Polygon(polygon).buffer(0)
        if poly.is_empty:
            return []
        idx = self._tree.query(poly.buffer(radius + 1e-9))
        out = []
        for i in idx:
            i = int(i)
            if i in self.claimed:
                continue
            d = 0.0 if poly.contains(self._pts[i]) else poly.distance(self._pts[i])
            if d <= radius:
                out.append((d, i))
        out.sort()
        return out

    def count_named(self, polygon: list[Point], etype: str) -> int:
        """Çokgenin içindeki, tipe ait adlı etiket sayısı (claim edilmişler dahil)."""
        if self._tree is None or len(polygon) < 3:
            return 0
        poly = Polygon(polygon).buffer(0)
        n = 0
        for i in self._tree.query(poly):
            lab = self.items[int(i)][1]
            if lab.name and lab.type_hint == etype and poly.contains(self._pts[int(i)]):
                n += 1
        return n

    def find(self, polygon: list[Point], etype: str, radius: float | None = None,
             claim: bool = True, require_hint: bool = False) -> Label | None:
        """Çokgenin içindeki ya da en yakınındaki, tipe uygun etiketleri (ad + kesit/kalınlık) birleştirir."""
        radius = self.params.label_search_radius if radius is None else radius
        cands = self._candidates(polygon, radius)
        if not cands:
            return None

        def score(d: float, lab: Label) -> float:
            return d - (0.5 if lab.type_hint == etype else 0.0) - (0.25 if d == 0 else 0.0)

        name_i = dims_i = thick_i = None
        best_name = best_dims = best_thick = None
        for d, i in cands:
            lab = self.items[i][1]
            if lab.type_hint and lab.type_hint != etype:
                continue
            if lab.name and lab.type_hint == etype:
                s = score(d, lab)
                if best_name is None or s < best_name:
                    best_name, name_i = s, i
            if lab.has_dims:
                s = score(d, lab)
                if best_dims is None or s < best_dims:
                    best_dims, dims_i = s, i
            if lab.thickness is not None:
                s = score(d, lab)
                if best_thick is None or s < best_thick:
                    best_thick, thick_i = s, i
        if require_hint and name_i is None:
            return None
        chosen = [i for i in (name_i, dims_i, thick_i) if i is not None]
        if not chosen:
            return None
        # ad etiketi ana, kesit ve kalınlık etiketleri eklenir
        primary = self.items[name_i][1] if name_i is not None else self.items[chosen[0]][1]
        result = primary
        for i in (dims_i, thick_i):
            if i is not None and self.items[i][1] is not primary:
                result = result.merged_with(self.items[i][1])
        if claim:
            self.claimed.update(chosen)
        return result


# ---------- Geometri yardımcıları ----------

def _bridge_gaps(segs: list[LineString], tol: float) -> list[LineString]:
    """Sarkan (başka hiçbir çizgiye değmeyen) çizgi uçlarını tol içindeki en yakın çizgiye köprüler.

    Gerçek çizimlerde bölge sınırları birkaç on cm ile 1 m arası boşluklarla çizilir; polygonize bu yüzden kapanmaz.
    - Köprü, sarkan çizginin kendi doğrultusunda uzatılarak hedef çizginin doğrusuna kadar götürülür (köşe düzgün kapanır);
      uzatma mümkün değilse en yakın noktaya çekilir.
    - Yan yana uzanan paralel çizgiler (kiriş / sürekli temel çift çizgisi) köprülenmez.
    """
    if not segs or tol <= 0:
        return []
    tree = STRtree(segs)
    bridges: list[LineString] = []

    def unit(seg: LineString):
        (x1, y1), (x2, y2) = seg.coords[0], seg.coords[-1]
        L = math.hypot(x2 - x1, y2 - y1)
        return ((x2 - x1) / L, (y2 - y1) / L) if L > 1e-9 else (1.0, 0.0)

    def side_by_side(a: LineString, b: LineString) -> bool:
        ua, ub = unit(a), unit(b)
        cross = abs(ua[0] * ub[1] - ua[1] * ub[0])
        if cross > math.sin(math.radians(5)):
            return False
        ax0 = a.coords[0]
        ta = sorted(((c[0] - ax0[0]) * ua[0] + (c[1] - ax0[1]) * ua[1]) for c in (a.coords[0], a.coords[-1]))
        tb = sorted(((c[0] - ax0[0]) * ua[0] + (c[1] - ax0[1]) * ua[1]) for c in (b.coords[0], b.coords[-1]))
        overlap = min(ta[1], tb[1]) - max(ta[0], tb[0])
        return overlap > 0.5 * min(ta[1] - ta[0], tb[1] - tb[0])

    for i, seg in enumerate(segs):
        for end in (0, -1):
            pt = SPoint(seg.coords[end])
            near = [int(j) for j in tree.query(pt.buffer(tol))]
            if any(j != i and segs[j].distance(pt) < 1e-3 for j in near):
                continue
            best, best_d = None, tol
            for j in near:
                # kendisi, zaten (öbür ucundan) bağlı olduğu komşu ve yan yana uzanan paralel çizgi aday değil
                if j == i or segs[j].distance(seg) < 1e-3 or side_by_side(seg, segs[j]):
                    continue
                d = segs[j].distance(pt)
                if d < best_d:
                    best_d, best = d, segs[j]
            if best is None:
                continue
            # uzatma: sarkan çizginin doğrusu ile hedefin doğrusunun kesişimi
            ux, uy = unit(seg)
            if end == 0:
                ux, uy = -ux, -uy
            (bx1, by1), (bx2, by2) = best.coords[0], best.coords[-1]
            vx, vy = bx2 - bx1, by2 - by1
            den = ux * vy - uy * vx
            target = None
            if abs(den) > 1e-9:
                t = ((bx1 - pt.x) * vy - (by1 - pt.y) * vx) / den      # sarkan çizgi boyunca mesafe
                if 0 <= t <= tol:
                    X = SPoint(pt.x + ux * t, pt.y + uy * t)
                    if best.distance(X) <= tol:
                        target = X
            if target is None:
                target = best.interpolate(best.project(pt))
            if target.distance(pt) > 1e-6:
                bridges.append(LineString([pt, target]))
            if best.distance(target) > 1e-6:            # uzatma hedefin ucunu aştıysa ucu da bağla
                q = best.interpolate(best.project(target))
                bridges.append(LineString([target, q]))
    return bridges


def polygons_on_layers(drawing: Drawing, layers: list[str], close_open: bool = False,
                       min_area: float = 0.0, snap_tol: float = 0.0) -> list[Entity]:
    """Katmanlardaki kapalı çokgenler + çizgilerden oluşan kapalı döngüler (polygonize).

    close_open: çizgi ve açık polyline'lar birlikte ağ olarak kapatılır (L şeklinde açık polyline + kapatan çizgi
    gibi). snap_tol: sarkan çizgi uçları bu mesafedeki en yakın çizgiye köprülenir (bölge sınırlarındaki boşluklar). Hiçbir yüzeye girmeyen en az 4 noktalı açık polyline'lar uçları birleştirilerek çokgen sayılır
    (pafta sınırında kesilmiş radye sınırı gibi); yalnızca geçerli (kendini kesmeyen) ve min_area üstü olanlar alınır.
    """
    result: list[Entity] = [e for e in drawing.entities if e.layer in layers and e.is_closed_polygon]
    open_lines = [e for e in drawing.entities if e.layer in layers and e.kind in ("line", "polyline")]
    loops: list[Polygon] = []
    if open_lines and len(open_lines) < 5000:
        segs = []
        for e in open_lines:
            for i in range(len(e.points) - 1):
                segs.append(LineString([e.points[i], e.points[i + 1]]))
        try:
            merged = unary_union(segs + _bridge_gaps(segs, snap_tol))
            for poly in polygonize(merged):
                if poly.area < max(min_area, 1e-9):
                    continue
                pts = [(x, y) for x, y in poly.exterior.coords[:-1]]
                if len(pts) >= 3 and not _duplicate(pts, result):
                    result.append(Entity("polygon", open_lines[0].layer, pts, closed=True, source="LINES>LOOP"))
                    loops.append(poly)
        except Exception:
            pass
    if close_open:
        loop_union = unary_union(loops) if loops else None
        for e in open_lines:
            if e.kind != "polyline" or len(e.points) < 4:
                continue
            try:
                poly = Polygon(e.points)
            except Exception:
                continue
            if not poly.is_valid or poly.area < min_area or _duplicate(list(e.points), result):
                continue
            # polyline zaten bir yüzeyin sınırındaysa (ağ ile kapanmış) tekrar kapatılmaz
            if loop_union is not None and LineString(e.points).buffer(1e-3).intersection(loop_union.boundary).length > 0.5 * LineString(e.points).length:
                continue
            result.append(Entity("polygon", e.layer, list(e.points), closed=True, handle=e.handle,
                                 source="POLYLINE>CLOSED", block=e.block))
    return result


def _duplicate(pts: list[Point], existing: list[Entity], tol: float = 0.9) -> bool:
    p = Polygon(pts).buffer(0)
    if p.area < 1e-9:
        return True
    for e in existing:
        q = Polygon(e.points).buffer(0)
        if q.area < 1e-9:
            continue
        inter = p.intersection(q).area
        if inter / max(p.area, q.area) > tol:
            return True
    return False


def dedupe_elements(elements: list[DetectedElement], tol: float = 0.9) -> list[DetectedElement]:
    """Aynı yeri kaplayan (hatch + polyline gibi) tekrar elemanları eler; büyük olanı tutar."""
    kept: list[DetectedElement] = []
    kept_polys: list[Polygon] = []
    tree: STRtree | None = None
    for el in sorted(elements, key=lambda e: -e.area):
        p = Polygon(el.points).buffer(0)
        dup = False
        if kept_polys and p.area > 1e-9:
            tree = STRtree(kept_polys)
            for j in tree.query(p):
                k = kept[int(j)]
                q = kept_polys[int(j)]
                if k.etype != el.etype or q.area < 1e-9:
                    continue
                if p.intersection(q).area / min(p.area, q.area) > tol:
                    dup = True
                    break
        if not dup:
            kept.append(el)
            kept_polys.append(p)
    return kept


@dataclass
class Segment:
    a: Point
    b: Point
    layer: str
    handle: str = ""

    @property
    def length(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def angle(self) -> float:
        ang = math.atan2(self.b[1] - self.a[1], self.b[0] - self.a[0])
        return ang % math.pi  # yön bağımsız


def segments_on_layers(drawing: Drawing, layers: list[str]) -> list[Segment]:
    segs: list[Segment] = []
    for e in drawing.entities:
        if e.layer not in layers or e.kind not in ("line", "polyline"):
            continue
        for i in range(len(e.points) - 1):
            s = Segment(e.points[i], e.points[i + 1], e.layer, e.handle)
            if s.length > 1e-6:
                segs.append(s)
    return segs


@dataclass
class ParallelPair:
    center_a: Point
    center_b: Point
    width: float
    layer: str
    rect: list[Point]
    handles: tuple[str, str]

    @property
    def length(self) -> float:
        return math.dist(self.center_a, self.center_b)

    @property
    def angle(self) -> float:
        return math.atan2(self.center_b[1] - self.center_a[1], self.center_b[0] - self.center_a[0]) % math.pi


def _rect_from_centerline(ca: Point, cb: Point, width: float) -> list[Point]:
    L = math.dist(ca, cb)
    if L < 1e-9:
        return [ca, cb, cb, ca]
    ux, uy = (cb[0] - ca[0]) / L, (cb[1] - ca[1]) / L
    nx, ny, hw = -uy, ux, width / 2.0
    return [(ca[0] + nx * hw, ca[1] + ny * hw), (cb[0] + nx * hw, cb[1] + ny * hw),
            (cb[0] - nx * hw, cb[1] - ny * hw), (ca[0] - nx * hw, ca[1] - ny * hw)]


def find_parallel_pairs(segs: list[Segment], width_range: tuple[float, float],
                        min_length: float, angle_tol: float = math.radians(1.5)) -> list[ParallelPair]:
    """Paralel, karşılıklı örtüşen çizgi çiftlerinden dikdörtgen elemanlar (kiriş/sürekli temel) çıkarır.

    Komşu arama STRtree ile yapılır (O(n log n)); her çizgi en iyi (en yakın, en uzun örtüşen) eşiyle eşlenir.
    """
    if not segs:
        return []
    lines = [LineString([s.a, s.b]) for s in segs]
    tree = STRtree(lines)
    cands: list[tuple[float, float, int, int, ParallelPair]] = []
    seen: set[tuple[int, int]] = set()
    for i, si in enumerate(segs):
        ux = (si.b[0] - si.a[0]) / si.length
        uy = (si.b[1] - si.a[1]) / si.length
        for j in tree.query(lines[i].buffer(width_range[1] + 1e-6)):
            j = int(j)
            if j == i or (min(i, j), max(i, j)) in seen:
                continue
            seen.add((min(i, j), max(i, j)))
            sj = segs[j]
            da = abs(si.angle - sj.angle)
            da = min(da, math.pi - da)
            if da > angle_tol:
                continue
            vx, vy = sj.a[0] - si.a[0], sj.a[1] - si.a[1]
            dist = abs(-vx * uy + vy * ux)
            if not (width_range[0] <= dist <= width_range[1]):
                continue
            ti = (0.0, si.length)
            tj = sorted([(sj.a[0] - si.a[0]) * ux + (sj.a[1] - si.a[1]) * uy,
                         (sj.b[0] - si.a[0]) * ux + (sj.b[1] - si.a[1]) * uy])
            lo, hi = max(ti[0], tj[0]), min(ti[1], tj[1])
            overlap = hi - lo
            if overlap < min_length:
                continue
            off = (-vx * uy + vy * ux) / 2.0
            nx, ny = -uy, ux
            ca = (si.a[0] + ux * lo + nx * off, si.a[1] + uy * lo + ny * off)
            cb = (si.a[0] + ux * hi + nx * off, si.a[1] + uy * hi + ny * off)
            pair = ParallelPair(ca, cb, dist, si.layer, _rect_from_centerline(ca, cb, dist), (si.handle, sj.handle))
            cands.append((dist, -overlap, i, j, pair))
    cands.sort(key=lambda c: (c[0], c[1]))
    used: set[int] = set()
    out: list[ParallelPair] = []
    for _, _, i, j, pair in cands:
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)
        out.append(pair)
    return out


def merge_collinear_pairs(pairs: list[ParallelPair], gap_max: float, width_tol: float = 0.03,
                          offset_tol: float = 0.06, angle_tol: float = math.radians(1.5)) -> list[ParallelPair]:
    """Aynı doğrultu, aynı genişlik ve aynı hizadaki parçaları (kolon geçişlerindeki boşluklara rağmen) birleştirir."""
    if not pairs:
        return []
    groups: list[list[ParallelPair]] = []
    keys: list[tuple[float, float, float, float, float]] = []   # (angle, width, offset, ux, uy)
    for p in pairs:
        ang = p.angle
        ux, uy = math.cos(ang), math.sin(ang)
        off = -p.center_a[0] * uy + p.center_a[1] * ux   # eksene dik konum
        placed = False
        for g, (ka, kw, ko, _, _) in zip(groups, keys):
            da = abs(ang - ka)
            da = min(da, math.pi - da)
            if da <= angle_tol and abs(p.width - kw) <= width_tol and abs(off - ko) <= offset_tol:
                g.append(p)
                placed = True
                break
        if not placed:
            groups.append([p])
            keys.append((ang, p.width, off, ux, uy))
    out: list[ParallelPair] = []
    for g, (ang, w, _, ux, uy) in zip(groups, keys):
        items = []
        for p in g:
            t1 = p.center_a[0] * ux + p.center_a[1] * uy
            t2 = p.center_b[0] * ux + p.center_b[1] * uy
            items.append((min(t1, t2), max(t1, t2), p))
        items.sort(key=lambda t: (t[0], t[1]))
        cur_lo, cur_hi, cur = items[0]
        merged_handles = [cur.handles]
        for lo, hi, p in items[1:]:
            if lo - cur_hi <= gap_max:
                cur_hi = max(cur_hi, hi)
                merged_handles.append(p.handles)
            else:
                out.append(_pair_from_axis(cur, cur_lo, cur_hi, ux, uy, w))
                cur_lo, cur_hi, cur = lo, hi, p
                merged_handles = [p.handles]
        out.append(_pair_from_axis(cur, cur_lo, cur_hi, ux, uy, w))
    return out


def _pair_from_axis(ref: ParallelPair, lo: float, hi: float, ux: float, uy: float, w: float) -> ParallelPair:
    # ref merkez hattının eksene dik bileşeni korunur
    off = -ref.center_a[0] * uy + ref.center_a[1] * ux
    nx, ny = -uy, ux
    ca = (ux * lo + nx * off, uy * lo + ny * off)
    cb = (ux * hi + nx * off, uy * hi + ny * off)
    return ParallelPair(ca, cb, w, ref.layer, _rect_from_centerline(ca, cb, w), ref.handles)


def faces_from_network(segs: list[Segment], polygons: list[list[Point]], snap: float = 0.05) -> list[Polygon]:
    """Kiriş çizgileri + kolon/perde çokgen sınırlarından kapalı yüzeyler (döşeme panelleri) üretir.

    snap: kolon/perde çokgenleri bu kadar (m) tamponlanır; kiriş çizgileri kolon yüzüne birkaç cm uzaktan biterse
    hücre yine kapanır (gerçek çizimlerde yaygın; tamponsuz hücrelerin çoğu birleşip devasa yüzey olur).
    """
    geoms = [LineString([s.a, s.b]) for s in segs]
    for pts in polygons:
        if len(pts) >= 3:
            poly = Polygon(pts).buffer(0)
            geoms.append((poly.buffer(snap, join_style=2) if snap > 0 else poly).exterior)
    if not geoms:
        return []
    try:
        merged = unary_union(geoms)
        return list(polygonize(merged))
    except Exception:
        return []
