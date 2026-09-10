"""Bitişik ve aynı kalemdeki alan elemanlarını tek elemanda birleştirir.

Kalıp planında bir kat döşemesi kirişlerle ve aks çizgileriyle bölünmüş onlarca ayrı çokgen olarak çizilir;
keşifte bunların hepsi tek döşemedir, tek dökümdür, tek beton sınıfıdır. Aynısı kaplama, şap, yalıtım gibi
alan kalemlerinde de olur: tek bir mahal yüzlerce küçük çokgene bölünmüş gelir.

Bölünmüş bırakılırsa eleman listesi yüzlerce satır olur, plan önizlemesinde aynı beton parça parça seçilir ve
keşifte "hangi parça sayıldı, hangisi sayılmadı" belirsizleşir.

Birleştirme yalnız **aynı kalem** parçaları arasında yapılır: aynı eleman tipi, aynı alt tip, aynı kalınlık,
aynı katman — ve yalnız birbirine değen (tol kadar) çokgenler. Kolon, kiriş, perde, kapı, pencere, armatür
gibi **sayılan** elemanlar hiç birleştirilmez; iki kolonun bitişik olması onları tek kolon yapmaz.

Miktar korunur: birleşik elemanın alanı parçaların alanları toplamıdır (çokgen birleşiminin alanı değil), yani
metraj birleştirmeden etkilenmez. Parçalar üst üste biniyorsa (çift çizilmiş çokgen) bu bir uyarı olarak
bildirilir. Parçaların adları meta["parts"], sayısı meta["merged_from"] içinde durur; bilgi kaybolmaz.
"""
from __future__ import annotations

from collections import defaultdict

from shapely import STRtree
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .detectors.base import DetectedElement

# Sayılan / uzunlukla ölçülen elemanlar: bitişik olsalar da ayrı kalır
NEVER_MERGE = {"column", "shear_wall", "beam", "parapet", "stair", "wall", "door", "window",
               "tray", "cable", "conduit", "fixture", "pipe", "duct", "mech_fixture"}
MERGE_TOL = 0.02          # m: bu kadar aralık "değiyor" sayılır (çizim toleransı, kılcal boşluk)
OVERLAP_WARN = 0.02       # birleşimin alanı toplamdan bu oranda küçükse parçalar üst üste demektir


def _mergeable(el: DetectedElement) -> bool:
    if el.etype in NEVER_MERGE or el.count != 1 or len(el.points) < 3:
        return False
    if el.length:                      # uzunlukla ölçülen kalem (sürekli temel, hat)
        return False
    if el.etype == "foundation" and el.subtype != "raft":
        return False
    return el.area > 0


def _key(el: DetectedElement) -> tuple:
    return (el.etype, el.subtype or "", el.layer or "", round(el.thickness or 0.0, 4))


def _poly(el: DetectedElement) -> Polygon | None:
    p = Polygon(el.points)
    if not p.is_valid:
        p = p.buffer(0)
    if isinstance(p, MultiPolygon):
        p = max(p.geoms, key=lambda g: g.area) if p.geoms else None
    return p if isinstance(p, Polygon) and not p.is_empty and p.area > 0 else None


def _outline(polys: list[Polygon], tol: float) -> Polygon | None:
    """Parçaların ortak dış sınırı. Yalnız köşede değen parçalar birleşimde MultiPolygon verir; bu durumda
    parçalar biraz şişirilip birleştirilir ve şişirme geri alınır."""
    u = unary_union(polys)
    if isinstance(u, Polygon) and not u.is_empty:
        return u
    grown = unary_union([p.buffer(tol / 2.0, join_style=2) for p in polys]).buffer(-tol / 2.0, join_style=2)
    if isinstance(grown, Polygon) and not grown.is_empty:
        return grown
    parts = list(u.geoms) if isinstance(u, MultiPolygon) else []
    return max(parts, key=lambda g: g.area) if parts else None


def _merge_one(members: list[DetectedElement], polys: list[Polygon], tol: float,
               warnings: list[str]) -> DetectedElement:
    base = max(members, key=lambda e: e.area)
    shape = _outline(polys, tol)
    pts = [(round(x, 4), round(y, 4)) for x, y in shape.exterior.simplify(tol / 4.0).coords[:-1]] if shape else base.points
    area = sum(e.area for e in members)
    if shape is not None and area > 0 and (area - shape.area) / area > OVERLAP_WARN:
        warnings.append(f"{base.etype}: birleştirilen {len(members)} parçanın toplam alanı ({area:.1f} m²) ortak "
                        f"sınırın alanından ({shape.area:.1f} m²) büyük — parçalar üst üste çizilmiş olabilir, "
                        "metraj bu kadar fazla çıkar.")
    names = [e.name for e in members if e.name]
    el = DetectedElement(
        etype=base.etype, layer=base.layer, points=list(pts), name=names[0] if len(names) == 1 else (names[0] + f" +{len(names) - 1}" if names else None),
        subtype=base.subtype, b=base.b, h=base.h, thickness=base.thickness,
        area=area, length=0.0, perimeter=float(shape.exterior.length) if shape else base.perimeter,
        count=1, confidence=min(e.confidence for e in members),
        label_raw=base.label_raw, source=base.source, handle=base.handle,
        meta={**(base.meta or {}), "merged_from": len(members), "parts": names[:40]},
    )
    seen: list[str] = []
    for e in members:
        for w in e.warnings:
            if w not in seen:
                seen.append(w)
    el.warnings = seen[:6]
    return el


def merge_area_elements(elements: list[DetectedElement], tol: float = MERGE_TOL
                        ) -> tuple[list[DetectedElement], list[str]]:
    """Bitişik ve aynı kalemdeki alan elemanlarını birleştirir. (yeni liste, uyarılar) döner."""
    groups: dict[tuple, list[int]] = defaultdict(list)
    out: list[tuple[int, DetectedElement]] = []
    for i, el in enumerate(elements):
        if _mergeable(el):
            groups[_key(el)].append(i)
        else:
            out.append((i, el))
    warnings: list[str] = []
    merged_total = 0
    for idx in groups.values():
        members = [elements[i] for i in idx]
        if len(members) < 2:
            out.extend((i, elements[i]) for i in idx)
            continue
        polys: list[Polygon | None] = [_poly(e) for e in members]
        good = [(i, e, p) for i, e, p in zip(idx, members, polys) if p is not None]
        out.extend((i, e) for i, e, p in zip(idx, members, polys) if p is None)
        if len(good) < 2:
            out.extend((i, e) for i, e, _ in good)
            continue
        grown = [p.buffer(tol / 2.0, join_style=2) for _, _, p in good]
        union = unary_union(grown)
        comps = list(union.geoms) if isinstance(union, MultiPolygon) else [union]
        tree = STRtree(comps)
        buckets: dict[int, list[tuple[int, DetectedElement, Polygon]]] = defaultdict(list)
        for i, e, p in good:
            hit = tree.query(p.representative_point(), predicate="intersects")
            buckets[int(hit[0]) if len(hit) else -1].append((i, e, p))
        for ci, rows in buckets.items():
            if ci < 0 or len(rows) < 2:
                out.extend((i, e) for i, e, _ in rows)
                continue
            merged_total += len(rows) - 1
            out.append((min(i for i, _, _ in rows),
                        _merge_one([e for _, e, _ in rows], [p for _, _, p in rows], tol, warnings)))
    out.sort(key=lambda t: t[0])
    if merged_total:
        warnings.insert(0, f"Aynı kalemin bitişik parçaları birleştirildi: {merged_total} parça tek elemana katıldı "
                           "(kalıp planında kirişlerle bölünmüş döşeme, mahal içinde parçalanmış kaplama). "
                           "Metraj değişmez; parça adları elemanın ayrıntısında durur.")
    return [e for _, e in out], warnings
