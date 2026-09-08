"""Tüm dedektörleri çalıştırır, birimi etiketlerle doğrular ve katman raporu üretir.

Çizimin disiplinine göre farklı dedektör kümesi çalışır:
  structural    kolon / perde / kiriş / döşeme / temel
  architectural duvar / kapı / pencere
  electrical    kablo tavası / kablo / boru / armatür
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field

from .detectors.base import DetectParams, DetectedElement, LabelIndex, polygons_on_layers, segments_on_layers
from .detectors.beams import detect_beams
from .detectors.columns import detect_columns
from .detectors.electrical import detect_electrical
from .detectors.foundations import detect_foundations
from .detectors.openings import detect_openings, detect_poz_openings, poz_catalog
from .detectors.shear_walls import detect_shear_walls
from .detectors.slabs import detect_slabs
from .detectors.standard import detect_mapped, detect_standard, standard_layers
from .detectors.walls import detect_walls
from .geometry import polygon_area
from .layer_profile import (ALL_TYPES, DEFAULT_DISCIPLINE, DISCIPLINES, MAPPED_DISCIPLINE, REBAR_DISCIPLINE, STANDARD_DISCIPLINE,
                            LayerProfile, types_for)
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
    poz: dict = field(default_factory=dict)          # doğrama pozları: sizes / kinds / prefixes (detectors/openings.py: poz_catalog)
    unit_verdict: str | None = None       # yazı yükseklikleri / etiketlerin desteklediği birim (yeterli kanıt yoksa None)
    disciplines: list[str] = field(default_factory=list)      # bu paftada çalıştırılan sezgisel disiplinler (ana + ek)
    discipline_hints: dict = field(default_factory=dict)      # çalıştırılmayan ama katmanlarında kanıt olan disiplinler -> nesne sayısı

    def by_type(self, etype: str) -> list[DetectedElement]:
        return [e for e in self.elements if e.etype == etype]

    def to_dict(self) -> dict:
        return {
            "unit": self.unit, "scale": self.scale, "unit_detected": self.unit_detected, "discipline": self.discipline,
            "elements": [e.to_dict() for e in self.elements],
            "layers": [l.to_dict() for l in self.layers],
            "warnings": self.warnings, "suggested_unit": self.suggested_unit, "materials": self.materials,
            "poz": self.poz, "unit_verdict": self.unit_verdict,
            "disciplines": self.disciplines, "discipline_hints": self.discipline_hints,
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


MIN_TEXTS_FOR_UNIT = 20


def text_count(drawing: Drawing) -> int:
    return sum(1 for e in drawing.entities if e.kind == "text" and e.height and e.height > 0)


def check_unit_by_text_height(drawing: Drawing) -> str | None:
    """Yazı yüksekliği ile birim sağlaması (mimari / eşlemeli çizimler): plan yazıları gerçek ölçekte 10–60 cm'dir.
    Medyan yazı yüksekliği bunun 10 katı altında ya da üstündeyse birim yanlış yazılmıştır (mm yazılmış, cm çizilmiş)."""
    hs = sorted(e.height for e in drawing.entities if e.kind == "text" and e.height and e.height > 0)
    if len(hs) < MIN_TEXTS_FOR_UNIT:
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


MIN_PLAN_GEOMETRY = 60   # bu kadar az çizgi / çokgen olan mimari paftada plan çizilmemiştir (yalnız yazı / xref izi)


def _architectural(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams,
                   result: AnalysisResult) -> list[DetectedElement]:
    walls = detect_walls(drawing, layers_by_type.get("wall", []), params)
    openings = detect_openings(drawing, {k: layers_by_type.get(k, []) for k in ("door", "window")}, params)
    # poz yazısıyla işaretlenen kapı / pencereler ("EMP1"): ölçü görünüşlerden ya da doğrama paftasından
    cat = poz_catalog(drawing, layers_by_type, params)
    result.poz = cat
    poz_openings = detect_poz_openings(drawing, walls, openings, params, cat)
    if poz_openings:
        counts = Counter(e.name for e in poz_openings)
        result.warnings.append(f"Poz yazılarından {len(poz_openings)} kapı / pencere sayıldı: "
                               + ", ".join(f"{k} {v}" for k, v in counts.most_common(8)) + ("…" if len(counts) > 8 else ""))
        unsized = sorted({e.name for e in poz_openings if any("ölçüsü bulunamadı" in w for w in e.warnings)})
        if unsized:
            result.warnings.append("Ölçüsü bilinmeyen pozlar (varsayılan ölçü alındı): " + ", ".join(unsized[:10])
                                   + " — görünüş ya da doğrama paftası yüklenince ölçüler oradan gelir.")
        openings = openings + poz_openings
    if cat.get("sizes"):
        result.warnings.append("Doğrama ölçüleri okundu: " + ", ".join(f"{p} {w*100:.0f}×{h*100:.0f}" for p, (w, h) in list(cat["sizes"].items())[:8])
                               + ("…" if len(cat["sizes"]) > 8 else ""))
    geometry = sum(1 for e in drawing.entities if e.kind in ("line", "polyline", "polygon"))
    if not walls and geometry < MIN_PLAN_GEOMETRY:
        result.warnings.insert(0, f"Bu paftada plan geometrisi yok ({len(drawing.texts())} yazı, {geometry} çizgi / çokgen): duvar, kapı ve "
                                  "pencere çizgileri dış referans (xref) dosyasında kalmış olabilir. DWG'yi xref'leri bağlayarak "
                                  "(Bind) kaydedip yeniden yükleyin.")
    elif walls and not openings:
        result.warnings.append("Kapı / pencere bulunamadı: kapı ve pencere katmanlarını eşleyin (bloklar sayılır).")
    return walls + openings


def _electrical(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams,
                result: AnalysisResult) -> list[DetectedElement]:
    return detect_electrical(drawing, layers_by_type, params)


DISCIPLINE_RUNNERS = {"structural": _structural, "architectural": _architectural, "electrical": _electrical}
HEURISTIC_DISCIPLINES = tuple(DISCIPLINE_RUNNERS)
MIN_HINT_OBJECTS = 8    # başka bir disiplinin katmanlarında en az bu kadar geometrik nesne varsa "ek disiplin" önerilir


def discipline_hints(drawing: Drawing, profile: LayerProfile, active: list[str]) -> dict[str, int]:
    """Çalıştırılmayan sezgisel disiplinlerin katman kanıtı: disiplin -> o disiplinin tanıdığı katmanlardaki geometrik nesne sayısı.
    Aynı paftada mimari + elektrik (ya da elektrik + mekanik) çizilmiş olabilir; kullanıcı ek disiplini açar."""
    counts: dict[str, int] = {}
    for e in drawing.entities:
        if e.kind != "text":
            counts[e.layer] = counts.get(e.layer, 0) + 1
    out: dict[str, int] = {}
    for d in HEURISTIC_DISCIPLINES:
        if d in active:
            continue
        n = sum(c for layer, c in counts.items() if profile.classify(layer, d))
        if n >= MIN_HINT_OBJECTS:
            out[d] = n
    return out


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
    r.unit_verdict = suggested
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
    result.unit_verdict = suggested or (drawing.unit if text_count(drawing) >= MIN_TEXTS_FOR_UNIT else None)
    result.poz = poz_catalog(drawing, {}, params)
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
                    catalog: Catalog | None = None, label: str = "", defer_on_unit: bool = False,
                    extra_disciplines: tuple[str, ...] | list[str] = ()) -> AnalysisResult:
    """defer_on_unit: birim yanlış görünüyorsa dedektörleri çalıştırmadan yalnız öneriyi döndür (analyze_file ilk geçişi).
    extra_disciplines: ana disipline ek olarak aynı paftada çalıştırılacak sezgisel disiplinler (mimari + elektrik gibi).
    Her katman ilk tanıyan disipline gider (sıra: ana, sonra ekler). KSF-… katmanları her zaman standart kuralla ölçülür."""
    profile = profile or LayerProfile()
    params = params or DetectParams()
    catalog = catalog or Catalog()
    if discipline == STANDARD_DISCIPLINE:
        result = analyze_standard(drawing, catalog, params)
        result.materials = scan_materials(drawing)
        result.disciplines = [STANDARD_DISCIPLINE]
        return result
    if discipline == MAPPED_DISCIPLINE:
        return analyze_mapped(drawing, profile, catalog, params, defer_on_unit=defer_on_unit)
    if discipline == REBAR_DISCIPLINE:
        result = analyze_rebar(drawing, label)
        result.materials = scan_materials(drawing)
        result.disciplines = [REBAR_DISCIPLINE]
        return result
    discipline = discipline if discipline in DISCIPLINE_RUNNERS else DEFAULT_DISCIPLINE
    discs = [discipline] + [d for d in extra_disciplines if d in DISCIPLINE_RUNNERS and d != discipline and d not in ()]
    discs = list(dict.fromkeys(discs))

    counts = drawing.layer_counts()
    ksf = standard_layers(drawing, catalog)
    layer_infos: list[LayerInfo] = []
    layers_by_disc: dict[str, dict[str, list[str]]] = {d: {} for d in discs}
    for name in drawing.layers:
        if name in ksf:
            p = ksf[name]
            lbl = (p.item.name if p.item else p.code) + (f" [{p.spec}]" if p.spec else "") + f" · {catalog.discipline_name(p.discipline)}"
            layer_infos.append(LayerInfo(name, counts.get(name, 0), p.code.lower(), etype_label=lbl))
            continue
        etype = None
        for d in discs:
            etype = profile.classify(name, d)
            if etype:
                layers_by_disc[d].setdefault(etype, []).append(name)
                break
        layer_infos.append(LayerInfo(name, counts.get(name, 0), etype))
    layers_by_type = layers_by_disc[discipline]

    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            discipline=discipline, layers=layer_infos, warnings=list(drawing.warnings),
                            materials=scan_materials(drawing), disciplines=list(discs))

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
        result.unit_verdict = suggested or (drawing.unit if text_count(drawing) >= MIN_TEXTS_FOR_UNIT else None)
        if suggested and suggested != drawing.unit:
            if defer_on_unit:
                return _unit_only_result(drawing, discipline, suggested)
            result.suggested_unit = suggested
            result.warnings.append(
                f"Çizim birimi '{drawing.unit}' yazılı ama yazı yükseklikleri '{suggested}' ile uyuşuyor. "
                f"Birim '{suggested}' olarak alındı; gerekirse çizim ayarlarından değiştirin."
            )

    result.elements = []
    for d in discs:
        result.elements += DISCIPLINE_RUNNERS[d](drawing, layers_by_disc[d], params, result)
    if ksf:
        # standarda uygun katmanlar (KSF-…) hangi disiplinde olursa olsun katalog kuralıyla ölçülür
        std_elements, std_warns = detect_standard(drawing, catalog, params)
        result.elements += std_elements
        result.warnings.extend(std_warns)
        result.warnings.append(f"KÇS katmanları okundu: {len(ksf)} katman, {len(std_elements)} kalem (katalog ölçüm kuralıyla)")
    if "architectural" in discs:
        sched, sw = schedule_elements(drawing, catalog)
        result.elements += sched
        result.warnings.extend(sw)
        result.rooms = room_rows(drawing)
        if result.rooms:
            result.warnings.append(f"Mahal alanı yazıları okundu: {len(result.rooms)} mahal, "
                                   f"{sum(r['area_m2'] for r in result.rooms):,.0f} m² (şap / kaplama mahal bazında türetilir)")

    result.discipline_hints = discipline_hints(drawing, profile, discs)
    for d, n in result.discipline_hints.items():
        note = " (mimari paftadaki kolon / kiriş izleri statik planda sayılır; ayrıca açmayın)" if d == "structural" else ""
        result.warnings.append(f"Bu paftada {DISCIPLINES.get(d, d)} katmanları da var ({n} nesne): aynı paftada birden çok disiplin "
                               f"çizilmişse çizim ayarlarından ek disiplin olarak açın{note}.")

    unmapped = [li.name for li in layer_infos if li.etype is None and li.count > 0]
    if unmapped:
        result.warnings.append(
            "Eşlenmemiş katmanlar (eleman sayılmadı): " + ", ".join(unmapped[:15])
            + (" ..." if len(unmapped) > 15 else "")
        )
    for d in discs:
        for etype, lbl in types_for(d).items():
            if etype == "hole":
                continue
            if etype in layers_by_disc[d] and not result.by_type(etype):
                result.warnings.append(f"{lbl} katmanı var ama eleman tespit edilemedi: {', '.join(layers_by_disc[d][etype])}")
    return result


def analyze_file(path: str, profile: LayerProfile | None = None, params: DetectParams | None = None,
                 unit_override: str | None = None, auto_unit: bool = True,
                 discipline: str = DEFAULT_DISCIPLINE, catalog: Catalog | None = None, label: str = "",
                 extra_disciplines: tuple[str, ...] | list[str] = ()) -> AnalysisResult:
    """Dosyayı analiz eder; etiketler birimi yalanlıyorsa (ve kullanıcı birim seçmediyse) doğru birimle yeniden okur."""
    drawing = load_dxf(path, unit_override=unit_override)
    defer = bool(auto_unit and not unit_override)
    result = analyze_drawing(drawing, profile, params, discipline, catalog, label, defer_on_unit=defer,
                             extra_disciplines=extra_disciplines)
    if unit_override and result.suggested_unit and result.suggested_unit != drawing.unit:
        # kullanıcı (ya da pafta oylaması) birimi seçti: yazı kanıtı aksini söylese de yeniden okunmaz, yalnız not düşülür
        result.warnings = [w for w in result.warnings if "yazı yükseklikleri" not in w and "kolon etiketleri" not in w]
        result.warnings.append(f"Birim elle '{unit_override}' seçildi; bu paftanın yazı yükseklikleri '{result.suggested_unit}' ile uyuşuyor "
                               "(görünüş / detay yazıları farklı ölçekte olabilir).")
    if auto_unit and not unit_override and result.suggested_unit and result.suggested_unit != drawing.unit:
        drawing2 = load_dxf(path, unit_override=result.suggested_unit)
        warn = [w for w in result.warnings if "kolon etiketleri" in w or "yazı yükseklikleri" in w]
        result = analyze_drawing(drawing2, profile, params, discipline, catalog, label, extra_disciplines=extra_disciplines)
        result.unit_detected = False
        result.unit_verdict = drawing2.unit
        result.warnings = warn + [w for w in result.warnings if "kolon etiketleri" not in w and "yazı yükseklikleri" not in w]
        result.suggested_unit = drawing2.unit
    return result
