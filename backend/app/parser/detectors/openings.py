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
from ..labels_ext import OPENING_PREFIXES, OpeningLabel, opening_type_from_name, parse_opening_label, size_from_name
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


# ---------------------------------------------------------------- poz yazılarından kapı / pencere
#
# Bazı ofisler kapı ve pencereyi blok yerine yalnızca poz yazısıyla ("EMP1", "EMP3 - KANATLI") işaretler; adet ve
# açıklama ayrı bir doğrama paftasındaki poz listesinde ("Poz: EMP3 / 9 Adet AÇILIR KAPI"), ölçü ise görünüşlerdeki
# doğrama dikdörtgenlerinde ya da yazının yanındaki "130 x 250" ölçü yazılarında durur.
#  - poz_catalog: bu çizimden poz -> (genişlik, yükseklik) ve poz -> kapı/pencere bilgisini toplar
#  - detect_poz_openings: bir duvara yakın (plandaki) poz yazılarını kapı / pencere elemanı yapar; görünüşteki
#    poz yazılarının yanında duvar olmadığından sayılmaz.

import re

from ..schedules import parse_schedule

_POZ = re.compile(r"^\s*(?P<prefix>[A-ZÇĞİÖŞÜ]{1,4})\s*-?\s*(?P<num>\d{1,3})(?P<suf>[A-Za-zçğışöü]?)['’]?"
                  r"\s*(?:[-–:]\s*(?P<note>.{1,40}))?\s*$")
_DIM_PAIR = re.compile(r"(?<![\d.,])(?P<b>\d{2,3}(?:[.,]\d)?)\s*[xX×/*]\s*(?P<h>\d{2,3}(?:[.,]\d)?)(?![\d.,])")
_DIM_ONLY = re.compile(r"^\s*\d{2,3}(?:[.,]\d)?\s*$")
_DIM_SEP = re.compile(r"^\s*[xX×/*]\s*$")


def _up(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def parse_poz(text: str) -> tuple[str, str, str] | None:
    """'EMP3 - KANATLI' -> (poz 'EMP3', önek 'EMP', not 'KANATLI'); poz deseni değilse None."""
    t = (text or "").replace("\\P", " ").strip()
    if "\n" in t:
        t = t.split("\n", 1)[0].strip()
    m = _POZ.match(t)
    if not m:
        return None
    prefix = _up(m.group("prefix"))
    poz = f"{prefix}{m.group('num')}{_up(m.group('suf') or '')}"
    return poz, prefix, (m.group("note") or "").strip()


def _dims_m(b: str, h: str, unit_scale: float) -> tuple[float, float] | None:
    w, hh = float(b.replace(",", ".")) * unit_scale, float(h.replace(",", ".")) * unit_scale
    if 0.3 <= w <= 8.0 and 0.3 <= hh <= 4.5:
        return w, hh
    return None


def _joined_dim_texts(texts: list[Entity], unit_scale: float) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """'130' 'x' '250' gibi parçalı ölçü yazılarını birleştirir -> [(konum, (a, b))].

    Parçalar yatay (yan yana, soldan sağa okunur) ya da döndürülmüş yazıda düşey (alt alta, aşağıdan yukarı okunur)
    olabilir; sıra okuma yönüne göredir ama yazı 180° dönükse ters çıkabilir — kapı pozlarında yükseklik büyük olan alınır."""
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for e in texts:
        m = _DIM_PAIR.search(e.text)
        if m:
            d = _dims_m(m.group("b"), m.group("h"), unit_scale)
            if d:
                out.append((e.points[0], d))
    nums = [e for e in texts if _DIM_ONLY.match(e.text)]
    seps = [e for e in texts if _DIM_SEP.match(e.text)]
    if not nums or not seps:
        return out
    for s in seps:
        sx, sy = s.points[0]
        tol = max(s.height * 1.5, 0.15)
        reach = max(s.height * 6, 1.0)
        # yatay satır: soldan sağa
        row = sorted((e for e in nums if abs(e.points[0][1] - sy) <= tol and abs(e.points[0][0] - sx) <= reach),
                     key=lambda e: e.points[0][0])
        first = [e for e in row if e.points[0][0] < sx]
        second = [e for e in row if e.points[0][0] > sx]
        if not (first and second):
            # düşey sütun: aşağıdan yukarı
            col = sorted((e for e in nums if abs(e.points[0][0] - sx) <= tol and abs(e.points[0][1] - sy) <= reach),
                         key=lambda e: e.points[0][1])
            first = [e for e in col if e.points[0][1] < sy]
            second = [e for e in col if e.points[0][1] > sy]
        if first and second:
            d = _dims_m(first[-1].text, second[0].text, unit_scale)
            if d:
                out.append(((sx, sy), d))
    return out


def poz_catalog(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams) -> dict:
    """Bu çizimdeki poz bilgisi: {"sizes": {poz: [g, y]}, "kinds": {poz: door|window}, "prefixes": [...]}.

    Ölçü kaynakları (öncelik sırasıyla): poz yazısındaki ölçü ("EMP3 130/250"), yazının yanındaki ölçü yazısı
    ("130 x 250"), yazının yanındaki kapı / pencere katmanı dikdörtgeni (görünüş: genişlik = yatay, yükseklik = düşey).
    Kapı / pencere ayrımı: poz listesindeki açıklama (KAPI / PENCERE) ya da yazının notu."""
    texts = [e for e in drawing.texts() if e.text]
    poz_texts: list[tuple[Entity, str, str, str]] = []
    for e in texts:
        p = parse_poz(e.text)
        if p:
            poz_texts.append((e, *p))
    sizes: dict[str, list[tuple[float, float]]] = {}       # ölçü yazılarından (sıra yazı yönüne bağlı, belirsiz)
    rect_sizes: dict[str, list[tuple[float, float]]] = {}  # görünüş dikdörtgenlerinden (genişlik yatay, yükseklik düşey: kesin)
    kinds: dict[str, str] = dict(params.poz_kinds)          # proje geneli (poz listesi) > bu çizim
    prefixes: set[str] = set()
    for row in parse_schedule([e.text for e in texts]):
        prefixes.add(re.sub(r"\d.*$", "", row.poz))
        note = _up(row.note)
        if "KAPI" in note or "DOOR" in note:
            kinds[row.poz] = "door"
        elif "PENCERE" in note or "WINDOW" in note or "CAM" in note:
            kinds[row.poz] = "window"
    if not poz_texts:
        return {"sizes": {}, "kinds": {k: v for k, v in kinds.items() if k not in params.poz_kinds or params.poz_kinds[k] != v},
                "prefixes": sorted(prefixes)}
    for e, poz, prefix, note in poz_texts:
        n = _up(note)
        if "KAPI" in n or "DOOR" in n:
            kinds.setdefault(poz, "door")
        m = _DIM_PAIR.search(e.text)
        if m:
            d = _dims_m(m.group("b"), m.group("h"), params.label_unit_scale)
            if d:
                sizes.setdefault(poz, []).append(d)
    # yanındaki ölçü yazıları (poz yazısının hemen yanında: birkaç yazı yüksekliği)
    dims = _joined_dim_texts([e for e in texts if not parse_poz(e.text)], params.label_unit_scale)
    if dims:
        dtree = STRtree([SPoint(p) for p, _ in dims])
        for e, poz, _, _ in poz_texts:
            pt = SPoint(e.points[0])
            reach = max(e.height * 4, 0.6)
            best, best_d = None, reach
            for i in dtree.query(pt.buffer(reach)):
                d = pt.distance(SPoint(dims[int(i)][0]))
                if d < best_d:
                    best, best_d = dims[int(i)][1], d
            if best:
                sizes.setdefault(poz, []).append(best)
    # görünüşteki doğrama dikdörtgenleri (kapı / pencere katmanları): yazıya en yakın, en büyük dikdörtgen
    layers = [l for k in ("door", "window") for l in layers_by_type.get(k, [])]
    rects: list[tuple[Polygon, float, float]] = []
    for ent in drawing.entities:
        if ent.layer in layers and ent.is_closed_polygon:
            xs = [p[0] for p in ent.points]
            ys = [p[1] for p in ent.points]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            if 0.3 <= w <= 8.0 and 0.3 <= h <= 4.5:
                poly = Polygon(ent.points).buffer(0)
                if not poly.is_empty and poly.area >= 0.6 * w * h:
                    rects.append((poly, w, h))
    if rects:
        rtree = STRtree([r[0] for r in rects])
        for e, poz, _, _ in poz_texts:
            pt = SPoint(e.points[0])
            cands = []
            for i in rtree.query(pt.buffer(1.5)):
                poly, w, h = rects[int(i)]
                if poly.distance(pt) <= 1.5:
                    cands.append((w * h, w, h))
            if cands:
                _, w, h = max(cands)
                rect_sizes.setdefault(poz, []).append((w, h))

    def median_size(lst: list[tuple[float, float]]) -> list[float]:
        ws = sorted(w for w, _ in lst)
        hs = sorted(h for _, h in lst)
        return [round(ws[len(ws) // 2], 3), round(hs[len(hs) // 2], 3)]

    for poz in list(sizes) + list(rect_sizes) + [p for _, p, _, _ in poz_texts]:
        if poz not in kinds and poz[:-1] in kinds and poz[-1].isalpha():
            kinds[poz] = kinds[poz[:-1]]  # EMP3A, EMP3 ile aynı türdür (varyant)
    out_sizes: dict[str, list[float]] = {}
    for poz, lst in rect_sizes.items():
        out_sizes[poz] = median_size(lst)
    for poz, lst in sizes.items():
        if poz in out_sizes:
            continue
        if kinds.get(poz) == "door":
            lst = [(min(a, b), max(a, b)) for a, b in lst]   # kapıda yükseklik büyük olandır (yazı yönü belirsiz)
        out_sizes[poz] = median_size(lst)
    for poz, (w, h) in out_sizes.items():
        if poz not in kinds and h >= 1.95 and w <= 3.0:
            kinds[poz] = "door"           # ölçüsü kapı ölçüsü (yükseklik ≥ 195 cm)
    for poz in list(sizes) + list(rect_sizes) + [p for _, p, _, _ in poz_texts]:
        if poz not in kinds and poz[:-1] in kinds and poz[-1].isalpha():
            kinds[poz] = kinds[poz[:-1]]  # EMP3A, EMP3 ile aynı türdür (varyant)
    prefixes.update(p for _, _, p, _ in poz_texts if p in OPENING_PREFIXES)
    local_kinds = {k: v for k, v in kinds.items() if params.poz_kinds.get(k) != v}
    return {"sizes": out_sizes, "kinds": local_kinds, "prefixes": sorted(prefixes)}


def detect_poz_openings(drawing: Drawing, walls: list[DetectedElement], existing: list[DetectedElement],
                        params: DetectParams, catalog: dict) -> list[DetectedElement]:
    """Plandaki poz yazılarını kapı / pencere elemanı yapar.

    Yalnız bilinen önekler (proje poz listesi, bu çizimdeki poz listesi, standart K/P önekleri) sayılır; yazı bir
    duvara params.poz_wall_radius içinde olmalıdır (görünüşlerdeki poz yazılarının yanında duvar yoktur).
    Ölçü: catalog / params.poz_sizes; yoksa varsayılan (uyarıyla). Aynı noktadaki mükerrer yazılar bir kez sayılır."""
    prefixes = set(params.poz_prefixes) | set(catalog.get("prefixes", [])) | set(OPENING_PREFIXES)
    if not walls or not prefixes:
        return []
    sizes = {**params.poz_sizes, **catalog.get("sizes", {})}
    kinds = {**params.poz_kinds, **catalog.get("kinds", {})}
    wall_polys = [Polygon(w.points).buffer(0) for w in walls if len(w.points) >= 3]
    wall_polys = [p for p in wall_polys if not p.is_empty]
    if not wall_polys:
        return []
    wtree = STRtree(wall_polys)
    taken = [SPoint(e.points[0]) if e.points else None for e in existing]
    taken = [p for p in taken if p is not None]
    ttree = STRtree(taken) if taken else None
    seen: set[tuple[str, int, int]] = set()
    out: list[DetectedElement] = []
    r = params.poz_wall_radius
    for e in drawing.texts():
        p = parse_poz(e.text)
        if not p:
            continue
        poz, prefix, note = p
        if prefix not in prefixes:
            continue
        x, y = e.points[0]
        key = (poz, round(x / 0.1), round(y / 0.1))
        if key in seen:
            continue
        pt = SPoint(x, y)
        near = [int(i) for i in wtree.query(pt.buffer(r)) if wall_polys[int(i)].distance(pt) <= r]
        if not near:
            continue
        if ttree is not None and any(taken[int(i)].distance(pt) <= 0.5 for i in ttree.query(pt.buffer(0.5))):
            continue   # blok ya da etiketle zaten sayılmış boşluk
        seen.add(key)
        kind = (kinds.get(poz) or (kinds.get(poz[:-1]) if poz[-1].isalpha() else None) or OPENING_PREFIXES.get(prefix)
                or ("door" if "KAPI" in _up(note) else "window"))
        el = DetectedElement(etype=kind, layer=e.layer, points=[(x - 0.3, y - 0.3), (x + 0.3, y - 0.3), (x + 0.3, y + 0.3), (x - 0.3, y + 0.3)],
                             source="POZ_LABEL", handle=e.handle, confidence=0.7, name=poz, subtype=poz,
                             label_raw=e.text.strip()[:40], meta={"poz": poz})
        size = sizes.get(poz)
        if size:
            el.b, el.h = float(size[0]), float(size[1])
            el.confidence = 0.85
        else:
            el.b, el.h = DEFAULT_WIDTH[kind], DEFAULT_HEIGHT[kind]
            el.warnings.append(f"{poz} ölçüsü bulunamadı (görünüş / doğrama paftası); {el.b*100:.0f}×{el.h*100:.0f} cm varsayıldı")
        el.area = el.b * el.h
        out.append(el)
    return out
