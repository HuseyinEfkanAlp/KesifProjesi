"""KÇS (Keşif Çizim Standardı) çizimleri: katman adı kendini tanıtır, ölçüm kuralı katalogdan gelir.

Her KSF-… katmanı için:
  count      üst düzey bloklar (INSERT) -> her blok 1 adet (blok yoksa küçük kapalı semboller sayılır)
  length     çizgi / polyline -> uzunluk (m); kapalı polyline ise çevre
  area       kapalı çokgen / tarama -> alan (m²); üst üste binen kopyalar elenir
  wall_area  çizgi uzunluğu; alan = uzunluk × yükseklik (keşif aşamasında)
  volume     kapalı çokgen alanı; hacim = alan × kalınlık (keşif aşamasında)
Katalogda olmayan kod: geometriye göre ölçülür (blok->adet, çizgi->m, alan->m²), uyarı verilir.
Eleman: etype = kalem kodu (küçük harf), subtype = ÖZELLİK, layer = tam katman adı, name = blok adı / kalem adı.
"""
from __future__ import annotations

from ...standard.catalog import Catalog, ParsedLayer, parse_layer
from ..geometry import perimeter, polygon_area, polyline_length
from ..loader import Drawing
from .base import DetectParams, DetectedElement, dedupe_elements

GEOMETRY_MEASURE = {"insert": "count", "line": "length", "polyline": "length", "polygon": "area"}


def standard_layers(drawing: Drawing, catalog: Catalog) -> dict[str, ParsedLayer]:
    out = {}
    for layer in drawing.layers:
        p = parse_layer(layer, catalog)
        if p:
            out[layer] = p
    return out


def detect_standard(drawing: Drawing, catalog: Catalog, params: DetectParams) -> tuple[list[DetectedElement], list[str]]:
    parsed = standard_layers(drawing, catalog)
    elements: list[DetectedElement] = []
    warnings: list[str] = []
    unknown: list[str] = []
    for layer, p in parsed.items():
        ents = drawing.by_layer(layer)
        if not ents:
            continue
        measure = p.item.measure if p.item else None
        if p.item is None:
            unknown.append(layer)
        etype = p.code.lower()
        base_name = p.item.name if p.item else p.code
        conf = 0.95 if p.item else 0.6
        polys: list[DetectedElement] = []
        for e in ents:
            if e.kind == "text":
                continue
            m = measure or GEOMETRY_MEASURE.get(e.kind)
            if m == "count":
                if e.kind != "insert":
                    continue
                el = DetectedElement(etype=etype, layer=layer, points=list(e.points), name=e.block or base_name, subtype=p.spec,
                                     count=1, source="INSERT", handle=e.handle, confidence=conf)
                elements.append(el)
            elif m in ("length", "wall_area"):
                if e.kind not in ("line", "polyline", "polygon"):
                    continue
                L = perimeter(e.points) if e.kind == "polygon" else polyline_length(e.points)
                if L < params.min_line_length:
                    continue
                el = DetectedElement(etype=etype, layer=layer, points=list(e.points), name=base_name, subtype=p.spec,
                                     length=L, source=e.source, handle=e.handle, confidence=conf)
                elements.append(el)
            elif m in ("area", "volume"):
                if e.kind != "polygon" or len(e.points) < 3:
                    continue
                a = polygon_area(e.points)
                if a < 1e-4:
                    continue
                el = DetectedElement(etype=etype, layer=layer, points=list(e.points), name=base_name, subtype=p.spec,
                                     area=a, perimeter=perimeter(e.points), source=e.source, handle=e.handle, confidence=conf)
                polys.append(el)
        if polys:
            elements.extend(dedupe_elements(polys))
        if measure == "count" and not any(e.kind == "insert" for e in ents):
            # blok kullanılmamış: küçük kapalı semboller (daire vb.) sayılır
            n = 0
            for e in ents:
                if e.kind == "polygon" and len(e.points) >= 3:
                    xs = [q[0] for q in e.points]
                    ys = [q[1] for q in e.points]
                    if max(max(xs) - min(xs), max(ys) - min(ys)) <= 1.5:
                        el = DetectedElement(etype=etype, layer=layer, points=list(e.points), name=base_name, subtype=p.spec,
                                             count=1, source=e.source, handle=e.handle, confidence=0.5)
                        el.warnings.append("Blok değil; kapalı sembol sayıldı (standart: blok kullanın)")
                        elements.append(el)
                        n += 1
            if n:
                warnings.append(f"{layer}: blok yerine {n} kapalı sembol sayıldı")
    if unknown:
        warnings.append("Katalogda olmayan KSF kalemleri (geometriye göre ölçüldü; kataloğa ekleyin): " + ", ".join(unknown[:10]))
    non_std = [l for l in drawing.layers if l not in parsed and drawing.by_layer(l) and not l.upper().startswith("KSF")]
    if non_std and parsed:
        warnings.append("Standart dışı katmanlar (metraja girmez): " + ", ".join(non_std[:10]) + (" ..." if len(non_std) > 10 else ""))
    if not parsed:
        warnings.append("Çizimde KSF-… katmanı yok. Standart: KSF-<DİSİPLİN>-<KALEM>-<ÖZELLİK> (bkz. Standart sayfası).")
    return elements, warnings
