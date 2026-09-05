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

import re

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


def measure_layer(drawing: Drawing, layer: str, code: str, item, measure: str | None, spec: str | None,
                  params: DetectParams, base_conf: float = 0.95, meta: dict | None = None) -> tuple[list[DetectedElement], list[str]]:
    """Bir katmandaki nesneleri katalog ölçüm kuralına göre elemanlara çevirir (count / length / area / wall_area / volume)."""
    ents = drawing.by_layer(layer)
    elements: list[DetectedElement] = []
    warnings: list[str] = []
    if not ents:
        return elements, warnings
    measure = measure or (item.measure if item else None)
    etype = code.lower()
    base_name = item.name if item else code
    polys: list[DetectedElement] = []
    meta = dict(meta or {})
    for e in ents:
        if e.kind == "text":
            continue
        m = measure or GEOMETRY_MEASURE.get(e.kind)
        if m == "count":
            if e.kind != "insert":
                continue
            elements.append(DetectedElement(etype=etype, layer=layer, points=list(e.points), name=e.block or base_name, subtype=spec,
                                            count=1, source="INSERT", handle=e.handle, confidence=base_conf, meta=meta))
        elif m in ("length", "wall_area"):
            if e.kind not in ("line", "polyline", "polygon"):
                continue
            L = perimeter(e.points) if e.kind == "polygon" else polyline_length(e.points)
            if L < params.min_line_length:
                continue
            elements.append(DetectedElement(etype=etype, layer=layer, points=list(e.points), name=base_name, subtype=spec,
                                            length=L, source=e.source, handle=e.handle, confidence=base_conf, meta=meta))
        elif m in ("area", "volume"):
            if e.kind != "polygon" or len(e.points) < 3:
                continue
            a = polygon_area(e.points)
            if a < 1e-4:
                continue
            polys.append(DetectedElement(etype=etype, layer=layer, points=list(e.points), name=base_name, subtype=spec,
                                         area=a, perimeter=perimeter(e.points), source=e.source, handle=e.handle, confidence=base_conf, meta=meta))
    if polys:
        elements.extend(dedupe_elements(polys))
    if measure == "count" and not any(e.kind == "insert" for e in ents):
        n = 0
        for e in ents:
            if e.kind == "polygon" and len(e.points) >= 3:
                xs = [q[0] for q in e.points]
                ys = [q[1] for q in e.points]
                if max(max(xs) - min(xs), max(ys) - min(ys)) <= 1.5:
                    el = DetectedElement(etype=etype, layer=layer, points=list(e.points), name=base_name, subtype=spec,
                                         count=1, source=e.source, handle=e.handle, confidence=0.5, meta=meta)
                    el.warnings.append("Blok değil; kapalı sembol sayıldı (standart: blok kullanın)")
                    elements.append(el)
                    n += 1
        if n:
            warnings.append(f"{layer}: blok yerine {n} kapalı sembol sayıldı")
    if measure in ("area", "volume") and not polys:
        warnings.append(f"{layer}: alan ölçümü için kapalı çokgen / tarama yok (açık çizgiler alan vermez)")
    return elements, warnings


def detect_standard(drawing: Drawing, catalog: Catalog, params: DetectParams) -> tuple[list[DetectedElement], list[str]]:
    parsed = standard_layers(drawing, catalog)
    elements: list[DetectedElement] = []
    warnings: list[str] = []
    unknown: list[str] = []
    for layer, p in parsed.items():
        if p.item is None:
            unknown.append(layer)
        els, w = measure_layer(drawing, layer, p.code, p.item, p.item.measure if p.item else None, p.spec, params,
                               base_conf=0.95 if p.item else 0.6)
        elements.extend(els)
        warnings.extend(w)
    if unknown:
        warnings.append("Katalogda olmayan KSF kalemleri (geometriye göre ölçüldü; kataloğa ekleyin): " + ", ".join(unknown[:10]))
    non_std = [l for l in drawing.layers if l not in parsed and drawing.by_layer(l) and not l.upper().startswith("KSF")]
    if non_std and parsed:
        warnings.append("Standart dışı katmanlar (metraja girmez): " + ", ".join(non_std[:10]) + (" ..." if len(non_std) > 10 else ""))
    if not parsed:
        warnings.append("Çizimde KSF-… katmanı yok. Standart: KSF-<DİSİPLİN>-<KALEM>-<ÖZELLİK> (bkz. Standart sayfası).")
    return elements, warnings


# Katman adından katalog kalemi önerisi (eşlemeli çizimler için; kullanıcı onaylar)
SUGGEST_RULES: list[tuple[str, str]] = [
    (r"GAZBETON|YTONG|AAC", "DUVAR_YTONG"), (r"BRICK|TU[GĞ]LA", "DUVAR_TUGLA"), (r"B[Iİ]MS", "DUVAR_BIMS"),
    (r"AL[CÇ][Iİ]PAN|DRYWALL|GYPSUM", "DUVAR_ALCIPAN"), (r"MANTOLAMA|INSUL|IZOLASYON|İZOLASYON|YALITIM", "MANTOLAMA"),
    (r"GLASS|\bCAM\b|GLAZ", "CAM"), (r"WINDOW|PENCERE|\bWIN\b", "PENCERE"), (r"DOOR|KAPI", "KAPI"),
    (r"PLASTER|SIVA|SIVA", "SIVA"), (r"PAINT|BOYA", "BOYA"), (r"TA[SŞ]\s*KAPLAMA|STONE", "CEPHE_TASI"),
    (r"KOMPOZ|ALUCOBOND|PANEL", "KOMPOZIT_PANEL"), (r"MEMBRAN", "CATI_MEMBRAN"), (r"ROOF|[CÇ]ATI", "CATI_KIREMIT"),
    (r"OLUK", "CATI_OLUK"), (r"YA[GĞ]MUR|DERE|INIS|İNİŞ", "CATI_DERE"), (r"K[UÜ]PE[SŞ]TE|KORKULUK", "KOREKUYU"),
    (r"SERAMIK|SERAMİK", "SERAMIK_ZEMIN"), (r"PARKE|LAMINAT", "LAMINAT"), (r"ASMA\s*TAVAN|CEILING", "ASMA_TAVAN"),
    (r"BORD[UÜ]R", "BORDUR"), (r"BAZALT|GRAN[Iİ]T|PEYZAJ.*D[OÖ][SŞ]EME", "PEYZAJ_DOSEME"), (r"[CÇ][Iİ]M\b|GRASS", "CIM"),
    (r"A[GĞ]A[CÇ]|TREE", "AGAC"), (r"ASFALT", "ASFALT"), (r"PARKE\s*TA[SŞ]|K[Iİ]L[Iİ]T", "PARKE_TAS"),
    (r"KABLO|CABLE", "KABLO"), (r"TAVA|TRAY", "TAVA"), (r"ARMAT|LIGHT|AYDINLATMA", "ARMATUR"), (r"PR[Iİ]Z|SOCKET", "PRIZ"),
    (r"SPR[Iİ]NK", "SPRINKLER"), (r"KANAL|DUCT", "HAVA_KANAL"), (r"MENFEZ|D[Iİ]F[UÜ]Z", "MENFEZ"), (r"PPRC", "BORU_PPRC"), (r"PVC", "BORU_PVC"),
]
_SUGGEST = [(re.compile(p, re.IGNORECASE), c) for p, c in SUGGEST_RULES]


def suggest_item(layer: str, catalog: Catalog) -> str | None:
    n = layer.replace("i", "İ").upper()
    for pat, code in _SUGGEST:
        if pat.search(n) and catalog.get(code):
            return code
    return None


def detect_mapped(drawing: Drawing, profile, catalog: Catalog, params: DetectParams) -> tuple[list[DetectedElement], list[str], dict]:
    """Katman eşlemeli çizim: kullanıcı eşlediği katmanlar katalog kuralıyla ölçülür; eşlenmeyenlere öneri.
    Döndürür: elemanlar, uyarılar, {katman: {"code", "measure", "label", "suggested"}}."""
    from ..layer_profile import mapped_item
    elements: list[DetectedElement] = []
    warnings: list[str] = []
    info: dict = {}
    mapped_n = 0
    for layer in drawing.layers:
        if not drawing.by_layer(layer):
            continue
        m = mapped_item(profile, layer)
        if m:
            code, measure = m
            item = catalog.get(code)
            measure = measure or (item.measure if item else None)
            spec = None
            nums = re.findall(r"\d+(?:[.,]\d+)?", layer)
            if nums and item and item.measure in ("wall_area", "volume"):
                spec = nums[0]
            els, w = measure_layer(drawing, layer, code, item, measure, spec, params, base_conf=0.85,
                                   meta={"ksf_code": code, "measure": measure, "spec": spec, "discipline": item.discipline if item else "???"})
            elements.extend(els)
            warnings.extend(w)
            mapped_n += 1
            info[layer] = {"code": code, "measure": measure, "label": (item.name if item else code) + f" · {MEASURE_LABELS.get(measure, measure)}",
                           "suggested": None}
        else:
            sug = suggest_item(layer, catalog)
            info[layer] = {"code": None, "measure": None, "label": None, "suggested": sug}
    if not mapped_n:
        warnings.append("Henüz katman eşlenmedi: Elemanlar sayfasında her katmanı bir katalog kalemine (ve ölçüm kuralına) atayın; "
                        "öneriler katman adından üretildi.")
    return elements, warnings, info


MEASURE_LABELS = {"count": "adet", "length": "m", "area": "m²", "wall_area": "m² (uzunluk × yükseklik)", "volume": "m³"}
