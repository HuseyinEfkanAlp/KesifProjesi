"""Tüm dedektörleri çalıştırır, birimi etiketlerle doğrular ve katman raporu üretir.

Çizimin disiplinine göre farklı dedektör kümesi çalışır:
  structural    kolon / perde / kiriş / döşeme / temel
  architectural duvar / kapı / pencere
  electrical    kablo tavası / kablo / boru / armatür
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .detectors.base import DetectParams, DetectedElement, LabelIndex, polygons_on_layers, segments_on_layers
from .detectors.beams import detect_beams
from .detectors.columns import detect_columns
from .detectors.electrical import detect_electrical
from .detectors.foundations import detect_foundations
from .detectors.openings import detect_openings
from .detectors.shear_walls import detect_shear_walls
from .detectors.slabs import detect_slabs
from .detectors.standard import detect_mapped, detect_standard, standard_layers
from .detectors.walls import detect_walls
from .geometry import polygon_area
from .layer_profile import (ALL_TYPES, DEFAULT_DISCIPLINE, MAPPED_DISCIPLINE, REBAR_DISCIPLINE, STANDARD_DISCIPLINE, LayerProfile,
                            types_for)
from .rebar_tables import kot_from_label, parse_rebar_labels, parse_rebar_tables, target_from_label
from .loader import UNIT_SCALE, Drawing, load_dxf
from .materials import scan_materials
from .schedules import parse_rooms, parse_schedule
from ..standard.catalog import Catalog


@dataclass
class LayerInfo:
    name: str
    count: int
    etype: str | None

    etype_label: str | None = None
    suggested: str | None = None          # eşlemeli çizim: katman adından önerilen katalog kalemi
    mapped_code: str | None = None
    mapped_measure: str | None = None
    mapped_pattern: str | None = None     # etiket sayımı deseni

    def to_dict(self) -> dict:
        return {"name": self.name, "count": self.count, "etype": self.etype,
                "etype_label": self.etype_label or ALL_TYPES.get(self.etype or "", None),
                "suggested": self.suggested, "mapped_code": self.mapped_code, "mapped_measure": self.mapped_measure,
                "mapped_pattern": self.mapped_pattern}


@dataclass
class AnalysisResult:
    unit: str
    scale: float
    unit_detected: bool
    discipline: str = DEFAULT_DISCIPLINE
    elements: list[DetectedElement] = field(default_factory=list)
    layers: list[LayerInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_unit: str | None = None     # etiketler başka bir birime işaret ediyorsa
    materials: dict = field(default_factory=dict)   # yazılardan tanınan malzeme / sistem kanıtı (parser/materials.py)
    rooms: list[dict] = field(default_factory=list)  # mahal alanı yazıları (parser/schedules.py: parse_rooms)

    def by_type(self, etype: str) -> list[DetectedElement]:
        return [e for e in self.elements if e.etype == etype]

    def to_dict(self) -> dict:
        return {
            "unit": self.unit, "scale": self.scale, "unit_detected": self.unit_detected, "discipline": self.discipline,
            "elements": [e.to_dict() for e in self.elements],
            "layers": [l.to_dict() for l in self.layers],
            "warnings": self.warnings, "suggested_unit": self.suggested_unit, "materials": self.materials,
        }


def check_unit_against_labels(drawing: Drawing, profile: LayerProfile, params: DetectParams) -> str | None:
    """Kolon etiketlerindeki kesit ile çizilen kolon boyutunu karşılaştırır.

    Oran ~10 ya da ~0.1 ise $INSUNITS yanlış demektir (mm yazılmış ama cm çizilmiş gibi).
    Doğru birim adını döndürür, tutarlıysa None.
    """
    col_layers = [l for l in drawing.layers if profile.classify(l, "structural") == "column"]
    if not col_layers:
        return None
    labels = LabelIndex(drawing, params)
    ratios: list[float] = []
    for ent in polygons_on_layers(drawing, col_layers)[:400]:
        area = polygon_area(ent.points)
        if area <= 0:
            continue
        lab = labels.find(ent.points, "column", radius=params.label_search_radius * 10, claim=True)
        if lab and lab.has_dims and lab.b * lab.h > 0:
            ratios.append((area / (lab.b * lab.h)) ** 0.5)   # uzunluk oranı
    if len(ratios) < 3:
        return None
    r = statistics.median(ratios)
    factor = None
    for f in (0.001, 0.01, 0.1, 10.0, 100.0, 1000.0):
        if abs(r - f) / f < 0.15:
            factor = f
    if factor is None:
        return None
    new_scale = drawing.scale / factor
    for name, s in UNIT_SCALE.items():
        if abs(new_scale - s) / s < 1e-6:
            return name
    return None


def check_unit_by_text_height(drawing: Drawing) -> str | None:
    """Yazı yüksekliği ile birim sağlaması (mimari / eşlemeli çizimler): plan yazıları gerçek ölçekte 10–60 cm'dir.
    Medyan yazı yüksekliği bunun 10 katı altında ya da üstündeyse birim yanlış yazılmıştır (mm yazılmış, cm çizilmiş)."""
    hs = sorted(e.height for e in drawing.entities if e.kind == "text" and e.height and e.height > 0)
    if len(hs) < 20:
        return None
    med = hs[len(hs) // 2]
    for factor in (10.0, 100.0, 0.1, 0.01):
        if 0.10 <= med * factor <= 0.60 and not (0.10 <= med <= 0.60):
            new_scale = drawing.scale * factor
            for name, sc in UNIT_SCALE.items():
                if abs(new_scale - sc) / sc < 1e-6:
                    return name
    return None


def _structural(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams,
                result: AnalysisResult) -> list[DetectedElement]:
    labels = LabelIndex(drawing, params)
    columns = detect_columns(drawing, layers_by_type.get("column", []), labels, params)
    walls = detect_shear_walls(drawing, layers_by_type.get("shear_wall", []), labels, params)
    supports = [e.points for e in columns + walls]
    beam_layers = layers_by_type.get("beam", [])
    beams = detect_beams(drawing, beam_layers, labels, params, supports=supports)
    holes = [e.points for e in polygons_on_layers(drawing, layers_by_type.get("hole", []))]
    slabs = detect_slabs(drawing, layers_by_type.get("slab", []), labels, params,
                         network_segments=segments_on_layers(drawing, beam_layers) if beam_layers else None,
                         supports=supports, holes=holes)
    founds = detect_foundations(drawing, layers_by_type.get("foundation", []), labels, params, supports=supports)

    # Temel paftası: üzerindeki kolon/perdeler yerleşim izidir (aynı elemanlar bodrum kalıp planında sayılır).
    # Metraj dışı bırakılır (düşük güven); kullanıcı isterse listede açabilir.
    raft_area = sum(f.area for f in founds if f.subtype == "raft" and f.confidence >= 0.4)
    if raft_area > 0 and raft_area >= 0.5 * sum(polygon_area(c.points) for c in columns + walls) * 20:
        for e in columns + walls:
            e.confidence = min(e.confidence, 0.3)
            e.warnings.append("Temel paftasındaki kolon/perde izi; metraja alınmadı (kat planında sayılır)")
        result.warnings.append("Temel paftası: kolon/perde izleri metraj dışı bırakıldı (kat kalıp planında sayılırlar).")
    if any(e.subtype == "net" for e in slabs):
        result.warnings.append("Döşemeler kiriş ağından türetildi (kirişler arası net alan); kiriş betonu tam yükseklikle hesaplanır.")
    return columns + walls + beams + slabs + founds


def _architectural(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams,
                   result: AnalysisResult) -> list[DetectedElement]:
    walls = detect_walls(drawing, layers_by_type.get("wall", []), params)
    openings = detect_openings(drawing, {k: layers_by_type.get(k, []) for k in ("door", "window")}, params)
    if walls and not openings:
        result.warnings.append("Kapı / pencere bulunamadı: kapı ve pencere katmanlarını eşleyin (bloklar sayılır).")
    return walls + openings


def _electrical(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams,
                result: AnalysisResult) -> list[DetectedElement]:
    return detect_electrical(drawing, layers_by_type, params)


DISCIPLINE_RUNNERS = {"structural": _structural, "architectural": _architectural, "electrical": _electrical}


def analyze_standard(drawing: Drawing, catalog: Catalog, params: DetectParams) -> AnalysisResult:
    """KSF standart çizimi: katman adları kendini tanıtır; katalog ölçüm kuralını verir."""
    counts = drawing.layer_counts()
    parsed = standard_layers(drawing, catalog)
    infos = []
    for name in drawing.layers:
        p = parsed.get(name)
        label = None
        if p:
            label = (p.item.name if p.item else p.code) + (f" [{p.spec}]" if p.spec else "") + f" · {catalog.discipline_name(p.discipline)}"
        infos.append(LayerInfo(name, counts.get(name, 0), p.code.lower() if p else None, etype_label=label))
    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            discipline=STANDARD_DISCIPLINE, layers=infos, warnings=list(drawing.warnings))
    elements, warns = detect_standard(drawing, catalog, params)
    result.elements = elements
    result.warnings.extend(warns)
    return result


def analyze_rebar(drawing: Drawing, label: str = "") -> AnalysisResult:
    """Donatı paftası: yalnızca metraj tabloları okunur; her çap bir 'rebar' elemanı (meta: kg, m, hedef eleman, kot)."""
    counts = drawing.layer_counts()
    infos = [LayerInfo(name, counts.get(name, 0), None) for name in drawing.layers]
    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            discipline=REBAR_DISCIPLINE, layers=infos, warnings=list(drawing.warnings))
    tables = parse_rebar_tables(drawing)
    source = "REBAR_TABLE"
    if not tables:
        lab = parse_rebar_labels(drawing)
        if lab is not None:
            tables = [lab]
            source = "REBAR_LABELS"
    target = target_from_label(label)
    kot = kot_from_label(label)
    for ti, t in enumerate(tables):
        for d in sorted(t.columns):
            kg = t.weight.get(d, 0.0)
            if kg <= 0:
                continue
            x, y = t.anchor
            r = 0.3
            el = DetectedElement(etype="rebar", layer="(metraj tablosu)", points=[(x - r, y - r), (x + r, y - r), (x + r, y + r), (x - r, y + r)],
                                 name=f"Ø{d}", subtype=f"Ø{d}", count=1, length=t.total_length.get(d, 0.0), b=d / 1000.0,
                                 source=source, confidence=0.95 if source == "REBAR_TABLE" else 0.8)
            el.warnings.extend(t.warnings)
            el.label_raw = (f"tablo {ti + 1}: {kg:.0f} kg" if source == "REBAR_TABLE" else f"poz yazıları: {kg:.0f} kg")
            el.meta = {"dia_mm": d, "weight_kg": round(kg, 1), "length_m": round(t.total_length.get(d, 0.0), 2),
                       "target": target, "kot": kot, "table": ti + 1}
            result.elements.append(el)
    if not tables:
        result.warnings.append("Donatı metraj tablosu bulunamadı (başlıkta Ø10 / Ø12 … çap sütunları ve AĞIRLIK satırı aranır) "
                               "ve adetli poz yazısı ('P45 4Ø14 l=160') yok.")
    else:
        from .layer_profile import STRUCTURAL_TYPES
        what = f"{len(tables)} metraj tablosu okundu" if source == "REBAR_TABLE" else "poz yazılarından hesaplandı"
        result.warnings.append(f"{what}, toplam {sum(t.total_kg for t in tables):,.0f} kg; "
                               f"hedef eleman: {STRUCTURAL_TYPES.get(target, target)} (plan adından; TEMEL / KOLON / KİRİŞ / PERDE yazmıyorsa döşeme)"
                               + (f", kot {kot}" if kot else ""))
    return result


def room_rows(drawing: Drawing) -> list[dict]:
    return [r.to_dict() for r in parse_rooms([e.text for e in drawing.entities if e.kind == "text" and e.text])]


def schedule_elements(drawing: Drawing, catalog: Catalog | None, label: str = "") -> tuple[list[DetectedElement], list[str]]:
    """Çizimdeki 'Poz: EMP1 / Adet: 82' yazılarını doğrama kalemine çevirir (etype dograma, alt tip poz, adet)."""
    rows = parse_schedule([e.text for e in drawing.entities if e.kind == "text" and e.text], label)
    if not rows:
        return [], []
    item = catalog.get("DOGRAMA") if catalog else None
    els = []
    for r in rows:
        els.append(DetectedElement(etype="dograma", layer="(poz listesi)", points=[], name=f"{r.poz} {r.note}".strip(), subtype=r.poz,
                                   count=r.count, source="SCHEDULE", confidence=0.9, label_raw=r.raw,
                                   meta={"ksf_code": "DOGRAMA", "measure": "count", "spec": r.poz,
                                         "discipline": item.discipline if item else "MIM", "note": r.note}))
    total = sum(r.count for r in rows)
    return els, [f"Doğrama poz listesi okundu: {len(rows)} poz, {total} adet (" + ", ".join(f"{r.poz} {r.count}" for r in rows[:8]) + ("…" if len(rows) > 8 else "") + ")"]


def _unit_only_result(drawing: Drawing, discipline: str, suggested: str) -> AnalysisResult:
    """Birim yanlış: dedektörler çalıştırılmadan yalnız birim önerisi döner (analyze_file doğru birimle yeniden okur)."""
    r = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected, discipline=discipline)
    r.suggested_unit = suggested
    r.warnings.append(f"Çizim birimi '{drawing.unit}' yazılı ama yazı yükseklikleri '{suggested}' ile uyuşuyor. "
                      f"Birim '{suggested}' olarak alındı; gerekirse çizim ayarlarından değiştirin.")
    return r


def analyze_mapped(drawing: Drawing, profile: LayerProfile, catalog: Catalog, params: DetectParams,
                   defer_on_unit: bool = False) -> AnalysisResult:
    """Katman eşlemeli çizim (cephe görünüşü, çatı, peyzaj…): katman -> katalog kalemi + ölçüm kuralı."""
    counts = drawing.layer_counts()
    suggested = check_unit_by_text_height(drawing)
    if defer_on_unit and suggested and suggested != drawing.unit:
        return _unit_only_result(drawing, MAPPED_DISCIPLINE, suggested)
    materials = scan_materials(drawing)
    elements, warns, info = detect_mapped(drawing, profile, catalog, params, materials)
    infos = []
    for name in drawing.layers:
        i = info.get(name, {})
        infos.append(LayerInfo(name, counts.get(name, 0), (i.get("code") or "").lower() or None, etype_label=i.get("label"),
                               suggested=i.get("suggested"), mapped_code=i.get("code"), mapped_measure=i.get("measure"),
                               mapped_pattern=i.get("pattern")))
    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            discipline=MAPPED_DISCIPLINE, layers=infos, warnings=list(drawing.warnings) + warns)
    sched, sw = schedule_elements(drawing, catalog)
    result.elements = elements + sched
    result.warnings.extend(sw)
    result.materials = materials
    result.rooms = room_rows(drawing)
    if suggested and suggested != drawing.unit:
        result.suggested_unit = suggested
        result.warnings.append(f"Çizim birimi '{drawing.unit}' yazılı ama yazı yükseklikleri '{suggested}' ile uyuşuyor. "
                               f"Birim '{suggested}' olarak alındı; gerekirse çizim ayarlarından değiştirin.")
    sugg = [f"{l.name} → {l.suggested}" for l in infos if l.suggested and not l.mapped_code and l.count > 0]
    if sugg:
        result.warnings.append("Öneri (onaylamak için katmanı eşleyin): " + "; ".join(sugg[:12]) + (" …" if len(sugg) > 12 else ""))
    return result


def analyze_drawing(drawing: Drawing, profile: LayerProfile | None = None,
                    params: DetectParams | None = None, discipline: str = DEFAULT_DISCIPLINE,
                    catalog: Catalog | None = None, label: str = "", defer_on_unit: bool = False) -> AnalysisResult:
    """defer_on_unit: birim yanlış görünüyorsa dedektörleri çalıştırmadan yalnız öneriyi döndür (analyze_file ilk geçişi)."""
    profile = profile or LayerProfile()
    params = params or DetectParams()
    if discipline == STANDARD_DISCIPLINE:
        result = analyze_standard(drawing, catalog or Catalog(), params)
        result.materials = scan_materials(drawing)
        return result
    if discipline == MAPPED_DISCIPLINE:
        return analyze_mapped(drawing, profile, catalog or Catalog(), params, defer_on_unit=defer_on_unit)
    if discipline == REBAR_DISCIPLINE:
        result = analyze_rebar(drawing, label)
        result.materials = scan_materials(drawing)
        return result
    discipline = discipline if discipline in DISCIPLINE_RUNNERS else DEFAULT_DISCIPLINE

    counts = drawing.layer_counts()
    layer_infos = [LayerInfo(name, counts.get(name, 0), profile.classify(name, discipline)) for name in drawing.layers]
    layers_by_type: dict[str, list[str]] = {}
    for li in layer_infos:
        if li.etype:
            layers_by_type.setdefault(li.etype, []).append(li.name)

    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            discipline=discipline, layers=layer_infos, warnings=list(drawing.warnings),
                            materials=scan_materials(drawing))

    if discipline == "structural":
        suggested = check_unit_against_labels(drawing, profile, params)
        if suggested and suggested != drawing.unit:
            result.suggested_unit = suggested
            result.warnings.append(
                f"Çizim birimi '{drawing.unit}' görünüyor ama kolon etiketleri '{suggested}' ile uyuşuyor. "
                f"Birim '{suggested}' olarak alındı; gerekirse çizim ayarlarından değiştirin."
            )
    else:
        suggested = check_unit_by_text_height(drawing)
        if suggested and suggested != drawing.unit:
            if defer_on_unit:
                return _unit_only_result(drawing, discipline, suggested)
            result.suggested_unit = suggested
            result.warnings.append(
                f"Çizim birimi '{drawing.unit}' yazılı ama yazı yükseklikleri '{suggested}' ile uyuşuyor. "
                f"Birim '{suggested}' olarak alındı; gerekirse çizim ayarlarından değiştirin."
            )

    result.elements = DISCIPLINE_RUNNERS[discipline](drawing, layers_by_type, params, result)
    if discipline == "architectural":
        sched, sw = schedule_elements(drawing, catalog or Catalog())
        result.elements += sched
        result.warnings.extend(sw)
        result.rooms = room_rows(drawing)
        if result.rooms:
            result.warnings.append(f"Mahal alanı yazıları okundu: {len(result.rooms)} mahal, "
                                   f"{sum(r['area_m2'] for r in result.rooms):,.0f} m² (şap / kaplama mahal bazında türetilir)")

    unmapped = [li.name for li in layer_infos if li.etype is None and li.count > 0]
    if unmapped:
        result.warnings.append(
            "Eşlenmemiş katmanlar (eleman sayılmadı): " + ", ".join(unmapped[:15])
            + (" ..." if len(unmapped) > 15 else "")
        )
    for etype, label in types_for(discipline).items():
        if etype == "hole":
            continue
        if etype in layers_by_type and not result.by_type(etype):
            result.warnings.append(f"{label} katmanı var ama eleman tespit edilemedi: {', '.join(layers_by_type[etype])}")
    return result


def analyze_file(path: str, profile: LayerProfile | None = None, params: DetectParams | None = None,
                 unit_override: str | None = None, auto_unit: bool = True,
                 discipline: str = DEFAULT_DISCIPLINE, catalog: Catalog | None = None, label: str = "") -> AnalysisResult:
    """Dosyayı analiz eder; etiketler birimi yalanlıyorsa (ve kullanıcı birim seçmediyse) doğru birimle yeniden okur."""
    drawing = load_dxf(path, unit_override=unit_override)
    defer = bool(auto_unit and not unit_override)
    result = analyze_drawing(drawing, profile, params, discipline, catalog, label, defer_on_unit=defer)
    if auto_unit and not unit_override and result.suggested_unit and result.suggested_unit != drawing.unit:
        drawing2 = load_dxf(path, unit_override=result.suggested_unit)
        warn = [w for w in result.warnings if "kolon etiketleri" in w or "yazı yükseklikleri" in w]
        result = analyze_drawing(drawing2, profile, params, discipline, catalog, label)
        result.unit_detected = False
        result.warnings = warn + [w for w in result.warnings if "kolon etiketleri" not in w and "yazı yükseklikleri" not in w]
        result.suggested_unit = drawing2.unit
    return result
