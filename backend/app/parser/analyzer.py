"""Tüm dedektörleri çalıştırır, birimi etiketlerle doğrular ve katman raporu üretir."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .detectors.base import DetectParams, DetectedElement, LabelIndex, polygons_on_layers, segments_on_layers
from .detectors.beams import detect_beams
from .detectors.columns import detect_columns
from .detectors.foundations import detect_foundations
from .detectors.shear_walls import detect_shear_walls
from .detectors.slabs import detect_slabs
from .geometry import polygon_area
from .layer_profile import ALL_TYPES, ELEMENT_TYPES, LayerProfile
from .loader import UNIT_SCALE, Drawing, load_dxf


@dataclass
class LayerInfo:
    name: str
    count: int
    etype: str | None

    def to_dict(self) -> dict:
        return {"name": self.name, "count": self.count, "etype": self.etype,
                "etype_label": ALL_TYPES.get(self.etype or "", None)}


@dataclass
class AnalysisResult:
    unit: str
    scale: float
    unit_detected: bool
    elements: list[DetectedElement] = field(default_factory=list)
    layers: list[LayerInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_unit: str | None = None     # etiketler başka bir birime işaret ediyorsa

    def by_type(self, etype: str) -> list[DetectedElement]:
        return [e for e in self.elements if e.etype == etype]

    def to_dict(self) -> dict:
        return {
            "unit": self.unit, "scale": self.scale, "unit_detected": self.unit_detected,
            "elements": [e.to_dict() for e in self.elements],
            "layers": [l.to_dict() for l in self.layers],
            "warnings": self.warnings, "suggested_unit": self.suggested_unit,
        }


def check_unit_against_labels(drawing: Drawing, profile: LayerProfile, params: DetectParams) -> str | None:
    """Kolon etiketlerindeki kesit ile çizilen kolon boyutunu karşılaştırır.

    Oran ~10 ya da ~0.1 ise $INSUNITS yanlış demektir (mm yazılmış ama cm çizilmiş gibi).
    Doğru birim adını döndürür, tutarlıysa None.
    """
    col_layers = [l for l in drawing.layers if profile.classify(l) == "column"]
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


def analyze_drawing(drawing: Drawing, profile: LayerProfile | None = None,
                    params: DetectParams | None = None) -> AnalysisResult:
    profile = profile or LayerProfile()
    params = params or DetectParams()
    labels = LabelIndex(drawing, params)

    counts = drawing.layer_counts()
    layer_infos = [LayerInfo(name, counts.get(name, 0), profile.classify(name)) for name in drawing.layers]
    layers_by_type: dict[str, list[str]] = {}
    for li in layer_infos:
        if li.etype:
            layers_by_type.setdefault(li.etype, []).append(li.name)

    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            layers=layer_infos, warnings=list(drawing.warnings))

    suggested = check_unit_against_labels(drawing, profile, params)
    if suggested and suggested != drawing.unit:
        result.suggested_unit = suggested
        result.warnings.append(
            f"Çizim birimi '{drawing.unit}' görünüyor ama kolon etiketleri '{suggested}' ile uyuşuyor. "
            f"Birim '{suggested}' olarak alındı; gerekirse çizim ayarlarından değiştirin."
        )

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

    result.elements = columns + walls + beams + slabs + founds

    unmapped = [li.name for li in layer_infos if li.etype is None and li.count > 0]
    if unmapped:
        result.warnings.append(
            "Eşlenmemiş katmanlar (eleman sayılmadı): " + ", ".join(unmapped[:15])
            + (" ..." if len(unmapped) > 15 else "")
        )
    for etype, label in ELEMENT_TYPES.items():
        if etype in layers_by_type and not result.by_type(etype):
            result.warnings.append(f"{label} katmanı var ama eleman tespit edilemedi: {', '.join(layers_by_type[etype])}")
    if any(e.subtype == "net" for e in slabs):
        result.warnings.append("Döşemeler kiriş ağından türetildi (kirişler arası net alan); kiriş betonu tam yükseklikle hesaplanır.")
    return result


def analyze_file(path: str, profile: LayerProfile | None = None, params: DetectParams | None = None,
                 unit_override: str | None = None, auto_unit: bool = True) -> AnalysisResult:
    """Dosyayı analiz eder; etiketler birimi yalanlıyorsa (ve kullanıcı birim seçmediyse) doğru birimle yeniden okur."""
    drawing = load_dxf(path, unit_override=unit_override)
    result = analyze_drawing(drawing, profile, params)
    if auto_unit and not unit_override and result.suggested_unit and result.suggested_unit != drawing.unit:
        drawing2 = load_dxf(path, unit_override=result.suggested_unit)
        warn = [w for w in result.warnings if "kolon etiketleri" in w]
        result = analyze_drawing(drawing2, profile, params)
        result.unit_detected = False
        result.warnings = warn + [w for w in result.warnings if "kolon etiketleri" not in w]
        result.suggested_unit = drawing2.unit
    return result
