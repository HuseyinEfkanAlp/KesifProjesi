"""Mahal tespiti: mimari plandaki duvarlardan kapalı alanlar, yazılardan adları.

Keşif "bina toplamı" değil **mahal bazında** çıkar: "Hol: 2 kamera, 4 priz, 8,2 m²". Bunun için önce
mahallerin sınırı gerekir; mimari planda mahal sınırı ayrı çizilmez, **duvarlar** çizilir:

1. Duvar (+ kolon / perde) katmanlarındaki çizgiler ağ olarak birleştirilir ve `polygonize` ile kapalı
   yüzler bulunur. Kapı boşlukları duvarda gedik bırakır ve yüz kapanmaz; bu yüzden sarkan uçlar
   `snap_tol` (varsayılan 1,2 m ~ kapı genişliği) içinde köprülenir (`detectors/base._bridge_gaps`).
2. Duvar gövdesine denk gelen ince dilimler elenir (alan / çevre oranı küçük olanlar).
3. Çizimde ayrıca **kapalı çizilmiş** polyline'lar (daire sınırı, bağımsız bölüm sınırı) aday alan sayılır;
   bunlar yüzleri kapsadığı için hiyerarşinin üst ucunu verir.
4. Yazılar alanlara dağıtılır: bir yazı kendisini içeren EN KÜÇÜK alanın adıdır. "LOBİ 45.20 m²" gibi
   alanlı yazılar mahal adı + beyan alanı verir; "DAİRE 1", "HOL" gibi yalın adlar da mahal adıdır.
5. Hiyerarşi kapsamadan kurulur: bir alan diğerini içeriyorsa üsttür (daire → mahal). `GROUP_WORDS`
   geçen ad (DAİRE, DÜKKAN, OFİS, BLOK…) bir GRUPtur; yalnız yaprak alana denk geldiyse ve üstünde
   adsız bir alan varsa ad üste taşınır (daire sınırı çizili, yazı içindeki odaya yazılmış hali).

Sonuç `drawing.spaces` alanında saklanır; eleman → mahal ataması `services.space_breakdown` içinde yapılır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point as SPoint, Polygon
from shapely.ops import polygonize, unary_union
import shapely
import shapely.affinity

from .detectors.base import _bridge_gaps
from .loader import Drawing, Point
from .schedules import parse_room_area

# Bir GRUP (bağımsız bölüm) adı: içindeki odalar onun mahalleridir.
# "DAİRE" yalnız kendi başına bir sözcükse bağımsız bölümdür: "KAZAN DAİRESİ", "YÖNETİM DAİRESİ" bir mahaldir
# (eskiden grup sayılıyor, sıva / tavan hesabından düşüyordu).
GROUP_WORDS = re.compile(r"DA[İI]RE(?![A-ZÇĞİÖŞÜa-zçğıöşü])|D[AÜU]KKAN|MA[GĞ]AZA|OF[İI]S|B[ÜU]RO|BLOK|V[İI]LLA|BA[GĞ]IMSIZ\s*B[ÖO]L[ÜU]M"
                         r"|[İI][SŞ]\s*YER[İI]|UN[İI]TE|[ÜU]N[İI]TE", re.IGNORECASE)
# Mahal adı sayılmayan yazılar: kotlar, poz / eleman adları, ölçüler, pafta işaretleri.
_NOT_NAME = re.compile(r"^[+\-±]?\d[\d.,/xX*\s-]*$|^[SKPDTM]\d+([./]\d+)?$|KES[İI]T|DETAY|PLAN\b|[ÖO]L[ÇC]EK|KOT"
                       r"|^\d+[.,]\d+$|^[A-Z]$", re.IGNORECASE)
# Ölçü / poz notu ("30X(31 / 16.33)", "27X34", "1/100") mahal adı değildir — yazının
# herhangi bir yerinde geçebilir, bu yüzden ayrı desen ve search ile bakılır.
_MEASURE_NOTE = re.compile(r"\d\s*[xX×]\s*[\d(]|\(\s*\d|\d\s*[/:]\s*\d")
MIN_SPACE_AREA = 1.0        # m² — bundan küçük yüz mahal sayılmaz
AREA_TOLERANCE_PCT = 12.0   # ölçülen çokgen ile yazıdaki alan arasında kabul edilen azami fark (%)
MIN_NAMELESS_AREA = 4.0     # m² — adı olmayan bu kadar büyük alan "adı yazılmamış mahal" diye bildirilir
MIN_WIDTH = 0.45            # m — alan/çevre oranı bundan küçükse duvar dilimi, mahal değil
DOOR_GAP = 1.2              # m — kapı boşluğu köprüleme toleransı
MAX_NAME = 40


@dataclass
class Space:
    index: int
    name: str
    kind: str                       # "mahal" | "grup"
    points: list[Point]
    area: float                     # çizimden ölçülen alan (m²)
    label_area: float = 0.0         # yazıda beyan edilen alan (m²)
    parent: int | None = None
    evidence: str = ""
    code: str = ""                  # mahal kodu (L_Z_01) — projenin mahal listesindeki kimlik
    children: list[int] = field(default_factory=list)
    # Alan nereden: "drawing" çokgen ölçüldü ve yazıyla tutuyor, "label" yalnız yazıdan (çokgen yok /
    # tutmadı), "polygon" çokgen var ama yazıda alan yok. Karşılaştırma yapılabilen yerde fark yüzde olarak durur.
    area_source: str = "polygon"
    diff_pct: float = 0.0
    perimeter: float = 0.0          # çokgen çevresi (m) — sıva / boya / duvar seramiği bundan çıkar

    def to_dict(self) -> dict:
        return {"index": self.index, "name": self.name, "kind": self.kind, "area": round(self.area, 2),
                "label_area": round(self.label_area, 2), "parent": self.parent, "evidence": self.evidence,
                "code": self.code, "area_source": self.area_source, "diff_pct": round(self.diff_pct, 1),
                "perimeter": round(self.perimeter, 2),
                "children": list(self.children), "points": [[round(x, 3), round(y, 3)] for x, y in self.points]}


SHORT_OK = {"WC", "HOL", "ODA", "BAR", "SPA", "KAT"}     # kısa ama gerçek mahal adları


def _is_name(text: str) -> bool:
    """Mahal adı olabilir mi? İki harfli kısaltmalar (DK, TK, AK) mahal adı değil, çizim işaretidir."""
    t = (text or "").replace("\\P", " ").strip()
    if not t or len(t) > MAX_NAME or _NOT_NAME.match(t) or _MEASURE_NOTE.search(t):
        return False
    return len(t) >= 3 or t.upper() in SHORT_OK


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\\P", " ")).strip(" -:·")


# Doğrama boşluğu köprüsü: aynı doğrultudaki iki duvar çizgisi arasındaki açıklıkta kapı / pencere çizimi varsa
# açıklık duvar yüzü hizasında kapatılır. Sarkan uç köprüsü (_bridge_gaps) bunu yapamaz: gerçek çizimde duvar
# açıklıkta kapatma çizgisiyle biter (uç sarkmaz) ve pencere çoğu zaman 1,2 m'den geniştir — mahal kapanmaz.
OPENING_GAP_MAX = 4.0       # m — bundan geniş açıklık tek doğrama değildir
COLLINEAR_TOL = 0.01        # m — iki çizgi aynı doğru üstünde sayılır


def _opening_bridges(segs: list[LineString], openings: list, blocks: list | None = None) -> list[LineString]:
    """Doğrama çizimi bulunan eş doğrultulu açıklıkları kapatan köprüler.

    blocks: [(ekleme noktası, açı°)] doğrama blokları. Blok varsa açıklık yalnız bloğun DOĞRULTUSUNDA kapatılır:
    kapı kanadı açıklığa dik çizilir ve karşılıklı iki kapının uç kapanışları aynı hizaya düşer — kanat çizgisi
    "doğrama var" sayılınca koridor enine köprüleniyor, parçalanıyordu (altın bina 3)."""
    import math
    from shapely import STRtree
    blocks = blocks or []
    if not segs or (not openings and not blocks):
        return []
    otree = STRtree(openings) if openings else None
    ends: dict[tuple, list[tuple[float, int]]] = {}
    out: list[LineString] = []
    # her çizgi kendi doğrusunun anahtarıyla gruplanır: yön + doğruya olan dik uzaklık
    for i, s in enumerate(segs):
        (x0, y0), (x1, y1) = s.coords[0], s.coords[-1]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 0.05:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        if ux < -1e-9 or (abs(ux) <= 1e-9 and uy < 0):
            ux, uy = -ux, -uy
        ang = round(math.degrees(math.atan2(uy, ux)) % 180.0, 1)
        off = round((-uy * x0 + ux * y0) / COLLINEAR_TOL)
        t0, t1 = sorted((x0 * ux + y0 * uy, x1 * ux + y1 * uy))
        ends.setdefault((ang, off, ux, uy), []).append((t0, t1))
    for (ang, off, ux, uy), spans in ends.items():
        spans.sort()
        c = off * COLLINEAR_TOL
        cur_end = spans[0][1]
        for t0, t1 in spans[1:]:
            gap = t0 - cur_end
            if 0.3 <= gap <= OPENING_GAP_MAX:
                a = (cur_end * ux - c * uy, cur_end * uy + c * ux)
                b = (t0 * ux - c * uy, t0 * uy + c * ux)
                bridge = LineString([a, b])
                if blocks:
                    zone = bridge.buffer(0.35)
                    ok = any(zone.contains(SPoint(pt)) and abs(((rot - ang) + 90.0) % 180.0 - 90.0) <= 10.0
                             for pt, rot in blocks)
                else:
                    mid = bridge.interpolate(0.5, normalized=True)
                    ok = otree is not None and any(openings[int(j)].distance(mid) <= 0.35
                                                   for j in otree.query(mid.buffer(0.35)))
                if ok:
                    out.append(bridge)
            cur_end = max(cur_end, t1)
    return out


def _faces(drawing: Drawing, layers: list[str], snap_tol: float, opening_layers: list[str] | None = None) -> list[Polygon]:
    """Duvar ağından kapalı yüzler + çizimde zaten kapalı çizilmiş çokgenler."""
    segs: list[LineString] = []
    closed: list[Polygon] = []
    for e in drawing.entities:
        if e.layer not in layers or len(e.points) < 2:
            continue
        if e.is_closed_polygon:
            try:
                p = Polygon(e.points)
                if p.is_valid and p.area >= MIN_SPACE_AREA:
                    closed.append(p)
            except Exception:
                pass
        if e.kind in ("line", "polyline", "polygon"):
            pts = list(e.points) + ([e.points[0]] if e.closed else [])
            for i in range(len(pts) - 1):
                if pts[i] != pts[i + 1]:
                    segs.append(LineString([pts[i], pts[i + 1]]))
    out: list[Polygon] = []
    if segs and len(segs) < 20000:
        ops, blocks = [], []
        for lay in opening_layers or []:
            for e in drawing.by_layer(lay):
                if e.kind == "text" or not e.points:
                    continue
                if e.kind == "insert" and e.anchor is not None:
                    blocks.append((e.anchor, e.rotation))
                    continue
                ops.append(LineString(e.points) if len(e.points) >= 2 else SPoint(e.points[0]))
        try:
            segs = segs + _opening_bridges(segs, ops, blocks)
            merged = shapely.set_precision(unary_union(segs + _bridge_gaps(segs, snap_tol)), 0.001)
            for poly in polygonize(merged):
                if poly.area < MIN_SPACE_AREA or poly.area / max(poly.length, 1e-9) < MIN_WIDTH / 2:
                    continue        # duvar gövdesine denk gelen ince dilim
                out.append(poly)
        except Exception:
            pass
    for p in closed:
        if not any(p.equals(q) for q in out):
            out.append(p)
    return out


# Mahal kodu: "L_Z_01", "L_CK_M02", "A-101" gibi. Gerçek projelerde mahal etiketi ÜÇ ayrı yazıdır:
#     RESTORAN          <- ad
#     L_Z_01 : 309.49 m²  <- kod ve alan (ayrı TEXT nesneleri, aralarında ":" bile ayrı olabilir)
# Bu yüzden yakın yazılar tek etikette birleştirilir.
_CODE = re.compile(r"^[A-Z]{1,3}[_\-][A-Z0-9]{1,4}([_\-][A-Z]?\d{1,3}[A-Z]?)?$")
_PUNCT = re.compile(r"^[:;.\-–/]+$")
LABEL_REACH = 2.0           # m — ad / kod / alan yazılarının birbirine azami uzaklığı
LABEL_REACH_H = 10.0        # × yazı yüksekliği (küçük ölçekli paftada yazı küçük, aralık da küçüktür)


@dataclass
class Label:
    name: str
    area: float                 # yazıda beyan edilen alan (m²)
    pt: SPoint
    raw: str
    code: str = ""              # mahal kodu (L_Z_01)


def _labels(drawing: Drawing) -> list[Label]:
    """Mahal etiketleri. Ad, kod ve alan ayrı yazılarsa yakınlıktan birleştirilir."""
    areas: list[Label] = []     # içinde m² geçen yazılar
    names: list[tuple[str, SPoint, str]] = []
    codes: list[tuple[str, SPoint]] = []
    for e in drawing.entities:
        if e.kind != "text" or not e.text or not e.points:
            continue
        raw = _clean(e.text)
        pt = SPoint(e.points[0][:2])
        h = float(e.height or 0.0)
        r = parse_room_area(e.text)
        if r:
            # "MAHAL" = adı olmayan yalın alan yazısı ("309.49 m²"): adı komşu yazıdan gelecek
            areas.append(Label("" if r.name == "MAHAL" else r.name, r.area_m2, pt, raw))
            setattr(areas[-1], "_h", h)
            continue
        if _CODE.match(raw.upper()):
            codes.append((raw.upper(), pt))
            continue
        if _PUNCT.match(raw):
            continue
        if _is_name(raw):
            names.append((raw.upper(), pt, raw))
    used: set[int] = set()
    for lab in areas:
        reach = max(LABEL_REACH, LABEL_REACH_H * getattr(lab, "_h", 0.0))
        if not lab.name:
            cand = sorted(((lab.pt.distance(p), i) for i, (_n, p, _r) in enumerate(names) if i not in used
                           and lab.pt.distance(p) <= reach))
            if cand:
                d, i = cand[0]
                used.add(i)
                lab.name, lab.raw = names[i][0], f"{names[i][2]} {lab.raw}"
        near_code = sorted(((lab.pt.distance(p), c) for c, p in codes if lab.pt.distance(p) <= reach))
        if near_code:
            lab.code = near_code[0][1]
    out = [lab for lab in areas if lab.name]
    # adı eşleşmeyen yalın adlar (alansız mahal / bağımsız bölüm yazısı) da etiket sayılır
    out += [Label(n, 0.0, p, r) for i, (n, p, r) in enumerate(names) if i not in used]
    return out


def has_space_labels(drawing: Drawing) -> bool:
    """Bu paftada mahal aramaya değer mi: en az bir mahal alanı yazısı ("HOL 32 m²") ya da
    bağımsız bölüm adı ("DAİRE 1") olmalı. Kalıp / donatı paftasında boşuna çokgen aramayız."""
    for lab in _labels(drawing):
        if lab.area > 0 or GROUP_WORDS.search(lab.name):
            return True
    return False


# Mahal alan sınırı çokgenleri ("alan çizgisi" / "ALAN" gibi katmanlar): mimar mahal alanlarını hesaplamak
# için her mahalin sınırını ayrı çizer. Çoğu projede bu çizim planın AYRI BİR KOPYASINDA durur (alan hesabı
# paftası), yani konumları plandaki yazılarla çakışmaz. Bu yüzden önce ALAN eşleşmesiyle aday çiftler kurulur,
# aday kaymaların en sık tekrar edeni gerçek kayma kabul edilir ve çokgenler plan koordinatına taşınır.
AREA_MATCH_PCT = 1.5        # çokgen alanı mahal yazısını bu kadar tutuyorsa aynı mahaldir (%)
SHIFT_GRID = 0.5            # m — aday kayma bu ızgaraya yuvarlanıp oylanır
MIN_SHIFT_VOTES = 3         # bir kaymanın gerçek sayılması için gereken eşleşme sayısı


def _closed_polygons(drawing: Drawing) -> list[tuple[Polygon, str]]:
    out = []
    for e in drawing.entities:
        if e.kind not in ("polygon", "polyline") or len(e.points) < 3:
            continue
        try:
            poly = Polygon([q[:2] for q in e.points])
            if not poly.is_valid:
                poly = poly.buffer(0)
        except Exception:
            continue
        if poly.geom_type == "Polygon" and poly.area >= MIN_SPACE_AREA:
            out.append((poly, e.layer or ""))
    return out


def area_boundary_faces(drawing: Drawing, labels: list[Label]) -> tuple[list[Polygon], str]:
    """Mahal alanını tutan çokgenleri plan koordinatına taşıyarak döndürür. (çokgenler, açıklama)"""
    wanted = [l for l in labels if l.area > 0]
    if not wanted:
        return [], ""
    polys = _closed_polygons(drawing)
    if not polys:
        return [], ""
    pairs: list[tuple[Polygon, Label]] = []
    for poly, _lay in polys:
        for lab in wanted:
            if abs(poly.area - lab.area) / lab.area * 100.0 <= AREA_MATCH_PCT:
                pairs.append((poly, lab))
    if not pairs:
        return [], ""
    # aday kayma: yazı zaten çokgenin içindeyse kayma yok; değilse yazı − çokgen merkezi
    votes: dict[tuple[float, float], list[tuple[Polygon, Label]]] = {}
    for poly, lab in pairs:
        c = poly.centroid
        dx, dy = lab.pt.x - c.x, lab.pt.y - c.y
        key = (round(dx / SHIFT_GRID) * SHIFT_GRID, round(dy / SHIFT_GRID) * SHIFT_GRID)
        votes.setdefault(key, []).append((poly, lab))
    # kayma adayı tek tek sınanır: o kaymayla kaç yazı kendi çokgeninin içine düşüyor?
    best, best_hit = None, 0
    for (dx, dy) in list(votes) + [(0.0, 0.0)]:
        hit = 0
        for poly, lab in pairs:
            if shapely.affinity.translate(poly, dx, dy).contains(lab.pt):
                hit += 1
        if hit > best_hit:
            best, best_hit = (dx, dy), hit
    if best is None or best_hit < MIN_SHIFT_VOTES:
        return [], ""
    dx, dy = best
    moved, seen = [], set()
    for poly, lab in pairs:
        m = shapely.affinity.translate(poly, dx, dy)
        if not m.contains(lab.pt):
            continue
        k = (round(m.centroid.x, 2), round(m.centroid.y, 2), round(m.area, 2))
        if k in seen:
            continue
        seen.add(k)
        moved.append(m)
    if not moved:
        return [], ""
    nerede = "planın kendi üzerinde" if abs(dx) < 0.01 and abs(dy) < 0.01 else f"plandan ({dx:+.1f}, {dy:+.1f}) m kaydırılarak"
    return moved, f"{len(moved)} mahal sınırı alan çizgilerinden alındı ({nerede}; alanlar mahal yazısıyla tutuyor)"


def detect_spaces(drawing: Drawing, layers: list[str], snap_tol: float = DOOR_GAP,
                  opening_layers: list[str] | None = None) -> tuple[list[Space], list[str]]:
    """Mahalleri ve aralarındaki daire / mahal hiyerarşisini çıkarır. Döner: mahaller, uyarılar."""
    warnings: list[str] = []
    labels = _labels(drawing)
    # 1) mahalin alan sınırı çizilmişse onu kullan: alanı mahal yazısını tutuyor, yani kendini doğrulamış olur
    faces, note = area_boundary_faces(drawing, labels)
    if note:
        warnings.append(note)
    # 2) yoksa duvar ağından kapalı yüzler (kapı / pencere boşlukları köprülenir)
    wall_faces = _faces(drawing, layers, snap_tol, opening_layers)
    known = [f.centroid for f in faces]
    faces += [f for f in wall_faces if not any(f.contains(c) for c in known)]
    # yüz bulunamasa da mahal yazıları mahaldir (alanı yazıdan): aşağıdaki "çokgensiz etiket" adımı onları ekler
    faces.sort(key=lambda p: -p.area)
    spaces = [Space(index=i, name="", kind="mahal", points=[(x, y) for x, y in p.exterior.coords[:-1]],
                    area=p.area, perimeter=p.length)   # iç halkalar dahil: serbest kolonun yüzleri de sıvanır
              for i, p in enumerate(faces)]
    # 1) hiyerarşi: bir alanı içeren en küçük alan onun üstüdür
    for i, p in enumerate(faces):
        best, best_area = None, None
        for j, q in enumerate(faces):
            if i == j or q.area <= p.area:
                continue
            if q.contains(p.representative_point()) and (best_area is None or q.area < best_area):
                best, best_area = j, q.area
        spaces[i].parent = best
        if best is not None:
            spaces[best].children.append(i)
    # 2) yazılar: her yazı kendisini içeren EN KÜÇÜK alanın adı olur
    for lab in labels:
        name, label_area, pt, raw = lab.name, lab.area, lab.pt, lab.raw
        # yazıyı içeren yüzlerden ALANI TUTANI seç (mobilya / tefriş çizgisi de yazıyı içerebilir);
        # yazıda alan yoksa en küçük yüz.
        cont = [i for i, p in enumerate(faces) if p.contains(pt)]
        if not cont:
            continue
        if label_area > 0:
            hit = min(cont, key=lambda i: abs(faces[i].area - label_area) / label_area)
            if abs(faces[hit].area - label_area) / label_area * 100.0 > AREA_TOLERANCE_PCT:
                hit = min(cont, key=lambda i: faces[i].area)
        else:
            hit = min(cont, key=lambda i: faces[i].area)
        sp = spaces[hit]
        group = bool(GROUP_WORDS.search(name))
        # daire sınırı çizili ama yazı içindeki odaya yazılmış: adı adsız üst alana taşı
        if group and not sp.children and sp.parent is not None and not spaces[sp.parent].name:
            sp = spaces[sp.parent]
        if sp.name and not group:
            continue                       # alanın adı var: ilk yazı geçerli (grup adı üste yazabilir)
        sp.name = name
        sp.kind = "grup" if group else sp.kind
        sp.evidence = raw
        sp.code = lab.code or sp.code
        if label_area > 0:
            sp.label_area = label_area
    # 3) grup YALNIZ adından belli olur (DAİRE, DÜKKAN, OFİS…): bir mahalin içinde başka mahal olması
    # (teras içinde havuz) onu bağımsız bölüm yapmaz.
    # Çokgeni yazıdaki alanla DOĞRULA: mimari plan mahalin alanını zaten yazıyor, bu bizim ölçtüğümüzün
    # denetimidir. Tutmuyorsa çokgen atılır (duvar ağı kapanmamış, komşu mahalle taşmış demektir) ve
    # mahal yazıdaki alanıyla listede kalır — mahal listesi eksilmez.
    for sp in spaces:
        if not sp.name:
            continue
        if sp.label_area > 0 and sp.area > 0:
            sp.diff_pct = abs(sp.area - sp.label_area) / sp.label_area * 100.0
            if sp.diff_pct <= AREA_TOLERANCE_PCT:
                sp.area_source = "drawing"
            else:
                sp.area, sp.area_source, sp.points, sp.perimeter = sp.label_area, "label", [], 0.0
        elif sp.label_area > 0:
            sp.area, sp.area_source = sp.label_area, "label"
    # hiçbir çokgene düşmemiş etiketler de mahaldir (çokgensiz): liste projedeki mahal listesiyle aynı olmalı
    def same(a: float, b: float) -> bool:
        return abs(a - b) <= max(0.05, 0.01 * max(a, b))     # aynı mahal iki kez yazılmış olabilir

    def dup(n1: str, a1: float, c1: str, n2: str, a2: float, c2: str) -> bool:
        """Aynı mahalin ikinci yazısı mı? Kodları farklıysa AYRI mahaldir (aynı alanlı iki merdiven gibi)."""
        return n1 == n2 and same(a1, a2) and (not c1 or not c2 or c1 == c2)

    placed = [(sp.name, sp.label_area, sp.code) for sp in spaces if sp.name]
    nxt = len(spaces)
    for lab in labels:
        if not lab.name or lab.area <= 0 or any(dup(n, a, c, lab.name, lab.area, lab.code) for n, a, c in placed):
            continue
        placed.append((lab.name, lab.area, lab.code))
        spaces.append(Space(index=nxt, name=lab.name, kind="grup" if GROUP_WORDS.search(lab.name) else "mahal",
                            points=[], area=lab.area, label_area=lab.area, evidence=lab.raw, code=lab.code,
                            area_source="label"))
        nxt += 1
    def apart(s1: Space, s2: Space) -> bool:
        """İkisinin de sınırı çizimden ölçülmüş ve çokgenleri örtüşmüyorsa ayrı mahallerdir: aynı katta iki eş daire
        aynı adlı, aynı alanlı yatak odası taşır ve ikisi de sayılmalıdır."""
        if s1.area_source != "drawing" or s2.area_source != "drawing" or len(s1.points) < 3 or len(s2.points) < 3:
            return False
        try:
            p1, p2 = Polygon(s1.points), Polygon(s2.points)
            return p1.intersection(p2).area < 0.1 * min(p1.area, p2.area)
        except Exception:
            return False

    seen_named: list[Space] = []
    for sp in sorted([x for x in spaces if x.name], key=lambda x: (not x.code, x.area_source != "drawing", -x.area)):
        if sp.label_area > 0 and any(dup(o.name, o.label_area, o.code, sp.name, sp.label_area, sp.code)
                                     and not apart(o, sp) for o in seen_named):
            sp.name = ""                      # aynı mahalin ikinci yazısı: tek satır kalsın
            continue
        seen_named.append(sp)
    named = [s for s in spaces if s.name]
    if not named:
        return [], [f"Mahal sınırı bulundu ({len(spaces)} kapalı alan) ama hiçbirinin içinde mahal adı yazmıyor: "
                    "mahaller adlandırılamadı."]
    def has_named_desc(sp: Space, guard: int = 0) -> bool:
        return guard < 8 and any(spaces[c].name or has_named_desc(spaces[c], guard + 1)
                                 for c in sp.children if c < len(spaces))

    unnamed = [s for s in spaces if not s.name and not has_named_desc(s) and s.area >= MIN_NAMELESS_AREA]
    # Adı olmayan yüz mahal değildir: listeye girmez. Çocukları en yakın ADLI üste bağlanır.
    def named_ancestor(sp: Space, guard: int = 0) -> int | None:
        if sp.parent is None or sp.parent >= len(spaces) or guard > 8:
            return None
        up = spaces[sp.parent]
        return up.index if up.name else named_ancestor(up, guard + 1)

    for sp in spaces:
        sp.parent = named_ancestor(sp)
    keep = {sp.index for sp in spaces if sp.name}
    for sp in spaces:
        sp.children = [c for c in sp.children if c in keep]
    out = [s for s in spaces if s.name]
    groups = [s for s in out if s.kind == "grup"]
    ver = len([s for s in out if s.area_source == "drawing"])
    lab_only = len([s for s in out if s.area_source == "label"])
    warnings.append(f"Mahal okundu: {len([s for s in out if s.kind == 'mahal'])} mahal"
                    + f" ({ver} tanesinin sınırı çizimden ölçüldü ve yazıdaki alanla tutuyor"
                    + (f", {lab_only} tanesi yalnız mahal yazısından" if lab_only else "") + ")"
                    + (f", {len(groups)} bağımsız bölüm ({', '.join(g.name for g in groups[:4])}…)" if groups else "")
                    + f"; toplam {sum(s.area for s in out if s.kind == 'mahal'):,.0f} m².")
    if unnamed:
        warnings.append(f"{len(unnamed)} kapalı alanın ({sum(s.area for s in unnamed):,.0f} m²) içinde mahal adı yok; "
                        "mahal listesine girmedi — adı yazılmamış ya da duvarı kapanmamış olabilir.")
    return out, warnings


def space_of(spaces: list[dict], pt: tuple[float, float]) -> dict | None:
    """Bir noktanın düştüğü EN KÜÇÜK mahal (grup değil mahal; yoksa grup)."""
    hit = None
    for s in spaces:
        if len(s.get("points") or []) < 3:
            continue
        try:
            if Polygon(s["points"]).contains(SPoint(pt)):
                if hit is None or s["area"] < hit["area"]:
                    hit = s
        except Exception:
            continue
    return hit
