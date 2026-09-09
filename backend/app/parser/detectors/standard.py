"""KÇS (Keşif Çizim Standardı) çizimleri: katman adı kendini tanıtır, ölçüm kuralı katalogdan gelir.

Her KSF-… katmanı için:
  count      üst düzey bloklar (INSERT) -> her blok 1 adet (blok yoksa küçük kapalı semboller sayılır)
  length     çizgi / polyline -> uzunluk (m); kapalı polyline ise çevre
  area       kapalı çokgen / tarama -> alan (m²); üst üste binen kopyalar elenir
  wall_area  çizgi uzunluğu; alan = uzunluk × yükseklik (yükseklik ÖZELLİK'ten, 20x300 -> 3 m; yoksa proje duvar yüksekliği)
  volume     kapalı çokgen alanı; hacim = alan × kalınlık (keşif aşamasında)
Katalogda olmayan kod: geometriye göre ölçülür (blok->adet, çizgi->m, alan->m²), uyarı verilir.
Eleman: etype = kalem kodu (küçük harf), subtype = ÖZELLİK, layer = tam katman adı, name = blok adı / kalem adı.
"""
from __future__ import annotations

import re

from ...standard.catalog import Catalog, ParsedLayer, parse_layer, spec_numbers
from ..geometry import min_area_rect, perimeter, polygon_area, polyline_length
from ..loader import Drawing
from .base import DetectParams, DetectedElement, dedupe_elements

GEOMETRY_MEASURE = {"insert": "count", "line": "length", "polyline": "length", "polygon": "area"}


_LABEL_SKIP = re.compile(r"^[+\-±]?\d[\d.,]*(\s*\(.*\))?$|^[+\-±]\d")   # kot ("+4.15", "-4.03 (+0.12)") ve sayı
_LABEL_MARKER = re.compile(r"KES[İI]T|DETAY|PLAN|G[ÖO]R[ÜU]N[ÜU][SŞ]|[ÖO]L[ÇC]EK|\d+-\d+\s*KES", re.IGNORECASE)   # pafta işaretleri


def _label_text(text: str) -> str:
    """Etiket sayımı için yazı: kısaltılır, kot / sayı / tek karakter elenir."""
    t = (text or "").strip()
    if not t or len(t) > 40 or len(t) < 2 or _LABEL_SKIP.match(t) or _LABEL_MARKER.search(t):
        return ""
    return t


def standard_layers(drawing: Drawing, catalog: Catalog) -> dict[str, ParsedLayer]:
    out = {}
    for layer in drawing.layers:
        p = parse_layer(layer, catalog)
        if p:
            out[layer] = p
    return out


def measure_layer(drawing: Drawing, layer: str, code: str, item, measure: str | None, spec: str | None,
                  params: DetectParams, base_conf: float = 0.95, meta: dict | None = None,
                  label_pattern: str | None = None) -> tuple[list[DetectedElement], list[str]]:
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
    if measure == "label_count":
        # Katmandaki her yazı bir etiket: "GP-4" -> prekast panel GP-4, 1 adet. Kot / ölçü / tek karakter / kesit işareti atlanır;
        # desen verilmişse yalnız ona uyanlar sayılır.
        n = 0
        rx = None
        if label_pattern:
            try:
                rx = re.compile(label_pattern, re.IGNORECASE)
            except re.error:
                warnings.append(f"{layer}: etiket deseni geçersiz ({label_pattern}); desensiz sayıldı")
        for e in ents:
            if e.kind != "text":
                continue
            label = _label_text(e.text)
            if not label or (rx and not rx.search(label)):
                continue
            elements.append(DetectedElement(etype=etype, layer=layer, points=list(e.points), name=label, subtype=label,
                                            count=1, source=e.source or "TEXT", handle=e.handle, confidence=base_conf,
                                            label_raw=e.text, meta=meta))
            n += 1
        if not n:
            warnings.append(f"{layer}: etiket sayımı için yazı yok")
        return elements, warnings
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
            poly_note = None
            width_from_poly = None
            if e.kind == "polygon" and len(e.points) >= 3:
                # Standart tek eksen çizgisi ister; ama duvar / kanal dış hatla (kapalı çokgen) çizilmişse çevre alınınca
                # uzunluk 2× çıkar. İnce-uzun çokgende eksen uzunluğu = alan / kısa kenar (L şekilli de doğru).
                long_side, short_side, _ = min_area_rect(e.points)
                nums0 = spec_numbers(spec)
                t_hint = (nums0[0] / 100.0 if m == "wall_area" and nums0 and 0 < nums0[0] <= 60 else None)
                if short_side <= max(0.6, 3 * (t_hint or 0.2)) and long_side >= 2 * short_side and short_side > 1e-6:
                    L = polygon_area(e.points) / short_side
                    width_from_poly = short_side
                    poly_note = "Kapalı çokgen; eksen uzunluğu alan / kalınlık ile alındı (standart: tek eksen çizgisi)"
                else:
                    L = perimeter(e.points)
            else:
                L = polyline_length(e.points)
            if L < params.min_line_length:
                continue
            h = t = None
            area = 0.0
            if m == "wall_area":
                # ÖZELLİK "13.5x300": kalınlık 13,5 cm, yükseklik 300 cm -> duvar alanı = uzunluk × yükseklik (m²);
                # yükseklik yazılmamışsa alan kaydederken proje duvar yüksekliğiyle tamamlanır (services.fill_wall_areas)
                nums = spec_numbers(spec)
                if nums and 0 < nums[0] <= 60:
                    t = nums[0] / 100.0
                if len(nums) >= 2 and nums[1] > 50:
                    h = nums[1] / 100.0
                    area = L * h
            el = DetectedElement(etype=etype, layer=layer, points=list(e.points), name=base_name, subtype=spec,
                                 length=L, h=h, thickness=t, area=area, source=e.source, handle=e.handle,
                                 confidence=base_conf, meta=meta)
            if width_from_poly and not t:
                el.b = width_from_poly
            if poly_note:
                el.warnings.append(poly_note)
            elements.append(el)
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


def detect_standard(drawing: Drawing, catalog: Catalog, params: DetectParams,
                    skip_layers: set[str] | None = None) -> tuple[list[DetectedElement], list[str]]:
    """skip_layers: başka yolla (statik motor) ölçülen KSF katmanları."""
    parsed = standard_layers(drawing, catalog)
    elements: list[DetectedElement] = []
    warnings: list[str] = []
    unknown: list[str] = []
    for layer, p in parsed.items():
        if skip_layers and layer in skip_layers:
            continue
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
    (r"PREKAST|PRECAST|PANEL\s*KOD", "PREKAST_PANEL"), (r"CEPHE.*(HAT|SINIR|KONTUR|BRUT|BR[ÜU]T)|OUTLINE|D[Iİ][SŞ]\s*HAT", "CEPHE_BRUT"),
    (r"S[ÖO]VE", "SOVE"), (r"S[Iİ]LME", "SILME"), (r"DEN[Iİ]ZL[Iİ]K", "DENIZLIK"), (r"KARTONP", "SILME"),
    (r"SERAMIK|SERAMİK", "SERAMIK_ZEMIN"), (r"PARKE|LAMINAT", "LAMINAT"), (r"ASMA\s*TAVAN|CEILING", "ASMA_TAVAN"),
    (r"BORD[UÜ]R", "BORDUR"), (r"BAZALT|GRAN[Iİ]T|PEYZAJ.*D[OÖ][SŞ]EME", "PEYZAJ_DOSEME"), (r"[CÇ][Iİ]M\b|GRASS", "CIM"),
    (r"A[GĞ]A[CÇ]|TREE", "AGAC"), (r"ASFALT", "ASFALT"), (r"PARKE\s*TA[SŞ]|K[Iİ]L[Iİ]T", "PARKE_TAS"),
    (r"KABLO|CABLE", "KABLO"), (r"TAVA|TRAY", "TAVA"), (r"ARMAT|LIGHT|AYDINLATMA", "ARMATUR"), (r"PR[Iİ]Z|SOCKET", "PRIZ"),
    (r"SPR[Iİ]NK", "SPRINKLER"), (r"KANAL|DUCT", "HAVA_KANAL"), (r"MENFEZ|D[Iİ]F[UÜ]Z", "MENFEZ"), (r"PPRC", "BORU_PPRC"), (r"PVC", "BORU_PVC"),
]
_SUGGEST = [(re.compile(p, re.IGNORECASE), c) for p, c in SUGGEST_RULES]


# Katman adından bulunan kalem, çizim yazıları bir katmanlı sistemi anlatıyorsa o sisteme yükseltilir:
# ÇATI katmanı + "KENET" yazısı -> KENET_CATI; MANTOLAMA katmanı -> MANTOLAMA_SISTEM (bileşenleri ayrı kalem olur).
SYSTEM_UPGRADES: dict[str, list[str]] = {
    "CATI_KIREMIT": ["KENET_CATI", "TERAS_CATI", "KIREMIT_CATI"],
    "MANTOLAMA": ["MANTOLAMA_SISTEM"],
}
# Sistem kodu -> yazıda kanıt gerekli mi (MANTOLAMA katmanı kanıtsız da sisteme yükselir)
UPGRADE_NEEDS_EVIDENCE = {"KENET_CATI": True, "TERAS_CATI": True, "KIREMIT_CATI": True, "MANTOLAMA_SISTEM": False}


def suggest_item(layer: str, catalog: Catalog, materials: dict | None = None, overrides: dict | None = None) -> str | None:
    """overrides: {öneri kodu: proje parametresiyle seçilen sistem} (roof_system → ÇATI katmanı o sisteme gider)."""
    n = layer.replace("i", "İ").upper()
    for pat, code in _SUGGEST:
        if pat.search(n) and catalog.get(code):
            if overrides and overrides.get(code) and catalog.get(overrides[code]):
                return overrides[code]
            for sys_code in SYSTEM_UPGRADES.get(code, []):
                if not catalog.get(sys_code):
                    continue
                if not UPGRADE_NEEDS_EVIDENCE.get(sys_code, True) or (materials and sys_code in materials):
                    return sys_code
            return code
    return None


def detect_mapped(drawing: Drawing, profile, catalog: Catalog, params: DetectParams,
                  materials: dict | None = None) -> tuple[list[DetectedElement], list[str], dict]:
    """Katman eşlemeli çizim: kullanıcı eşlediği katmanlar katalog kuralıyla ölçülür; eşlenmeyenlere öneri.
    Döndürür: elemanlar, uyarılar, {katman: {"code", "measure", "label", "suggested"}}."""
    from ..layer_profile import mapped_item
    elements: list[DetectedElement] = []
    warnings: list[str] = []
    info: dict = {}
    mapped_n = 0
    auto: list[tuple[str, str, int]] = []
    for layer in drawing.layers:
        if not drawing.by_layer(layer):
            continue
        m = mapped_item(profile, layer)
        if m:
            code, measure, pattern = m
            item = catalog.get(code)
            measure = measure or (item.measure if item else None)
            spec = None
            nums = re.findall(r"\d+(?:[.,]\d+)?", layer)
            if nums and item and item.measure in ("wall_area", "volume"):
                spec = nums[0]
            els, w = measure_layer(drawing, layer, code, item, measure, spec, params, base_conf=0.85,
                                   meta={"ksf_code": code, "measure": measure, "spec": spec, "discipline": item.discipline if item else "???"},
                                   label_pattern=pattern)
            elements.extend(els)
            warnings.extend(w)
            mapped_n += 1
            info[layer] = {"code": code, "measure": measure, "pattern": pattern,
                           "label": (item.name if item else code) + f" · {MEASURE_LABELS.get(measure, measure)}" + (f" · desen {pattern}" if pattern else ""),
                           "suggested": None}
        else:
            sug = suggest_item(layer, catalog, materials, getattr(params, "system_overrides", None))
            if sug and getattr(params, "auto_map", True) and not profile.is_ignored(layer) and catalog.get(sug):
                # katman adından güçlü öneri: onay beklemeden ölçülür (düşük güven, "otomatik" işaretli);
                # kullanıcı Elemanlar sayfasında değiştirir ya da "ölçülmez" yapar
                item = catalog.get(sug)
                measure = item.measure
                spec = None
                nums = re.findall(r"\d+(?:[.,]\d+)?", layer)
                if nums and item.measure in ("wall_area", "volume"):
                    spec = nums[0]
                els, w = measure_layer(drawing, layer, sug, item, measure, spec, params, base_conf=0.55,
                                       meta={"ksf_code": sug, "measure": measure, "spec": spec, "discipline": item.discipline, "auto_mapped": True})
                for el in els:
                    el.warnings.append("Katman adından otomatik eşlendi; Elemanlar sayfasında onaylayın")
                elements.extend(els)
                warnings.extend(w)
                auto.append((layer, item.name, len(els)))
                info[layer] = {"code": sug, "measure": measure, "pattern": None, "auto": True,
                               "label": f"{item.name} · {MEASURE_LABELS.get(measure, measure)} · otomatik", "suggested": sug}
            else:
                info[layer] = {"code": None, "measure": None, "label": None, "suggested": sug}
    if auto:
        warnings.append(f"Katman adından otomatik eşlendi ({len(auto)} katman): "
                        + "; ".join(f"{l} → {n} ({k})" for l, n, k in auto[:8]) + ("…" if len(auto) > 8 else "")
                        + ". Yanlışsa Elemanlar sayfasında değiştirin ya da 'ölçülmez' yapın.")
    elif not mapped_n:
        warnings.append("Katman eşlenmedi ve katman adlarından kalem tanınamadı: Elemanlar sayfasında katmanları katalog kalemine atayın.")
    return elements, warnings, info


MEASURE_LABELS = {"count": "adet", "length": "m", "area": "m²", "wall_area": "m² (uzunluk × yükseklik)", "volume": "m³",
                  "label_count": "adet (etiket)"}
