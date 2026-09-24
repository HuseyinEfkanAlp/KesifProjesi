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
from .detectors.mechanical import detect_mechanical
from .detectors.openings import detect_openings, detect_poz_openings, poz_catalog
from .detectors.shear_walls import detect_shear_walls
from .detectors.slabs import detect_slabs
from .detectors.standard import assign_roof_zones, detect_mapped, detect_standard, standard_layers
from .detectors.walls import detect_walls
from .merge import merge_area_elements
from .geometry import polygon_area
from shapely.geometry import Point as SPoint, Polygon
from .layer_profile import (ALL_TYPES, DEFAULT_DISCIPLINE, DISCIPLINES, MAPPED_DISCIPLINE, REBAR_DISCIPLINE, STANDARD_DISCIPLINE,
                            STRUCTURAL_TYPES, LayerProfile, ksf_spec_dims, ksf_structural_type, types_for)
from .levels import parse_levels
from .rebar_tables import kot_from_label, parse_rebar_label_groups, parse_rebar_tables, target_from_label
from .loader import UNIT_SCALE, Drawing, load_dxf
from .blocks import own_block_of_drawing, scan_drawing as scan_blocks
from .rebar_mix import scan_drawing as scan_rebar_mix
from .rebar_mix import scan_drawing_layers as scan_rebar_layers
from .materials import finish_of, scan_materials
from .schedules import RoomRow, parse_room_area, parse_schedule
from .spaces import detect_spaces, has_space_labels
from ..standard.catalog import Catalog, parse_layer


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
    auto: bool = False                    # eşleme kullanıcı onayı olmadan katman adından yapıldı

    def to_dict(self) -> dict:
        return {"name": self.name, "count": self.count, "etype": self.etype,
                "etype_label": self.etype_label or ALL_TYPES.get(self.etype or "", None),
                "suggested": self.suggested, "mapped_code": self.mapped_code, "mapped_measure": self.mapped_measure,
                "mapped_pattern": self.mapped_pattern, "auto": self.auto}


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
    rebar_mix: dict = field(default_factory=dict)   # donatı yazılarından çap payları (parser/rebar_mix.py)
    rebar_layers: dict = field(default_factory=dict)  # alt / üst donatı kanıt sayısı (çift kat mı; parser/rebar_mix.py)
    blocks_seen: dict = field(default_factory=dict)  # yazılarda geçen blok adları: {"A1": 1, "C2": 1} (parser/blocks.py)
    own_block: str = ""                              # paftanın kendi bloğu (en iri "… BLOK" yazısı = pafta başlığı)
    rooms: list[dict] = field(default_factory=list)  # mahal alanı yazıları + bitiş notu (room_rows)
    spaces: list[dict] = field(default_factory=list)  # mahaller: duvarlardan kapalı alanlar (parser/spaces.py)
    poz: dict = field(default_factory=dict)          # doğrama pozları: sizes / kinds / prefixes (detectors/openings.py: poz_catalog)
    unit_verdict: str | None = None       # yazı yükseklikleri / etiketlerin desteklediği birim (yeterli kanıt yoksa None)
    disciplines: list[str] = field(default_factory=list)      # bu paftada çalıştırılan sezgisel disiplinler (ana + ek)
    levels: list[float] = field(default_factory=list)          # kot yazılarından seviyeler (mutlak sistem; parser/levels.py)
    kot: float | None = None                                   # bu paftanın kat kotu (etiket ya da "… KOTU" yazısı)
    ksf_height: float | None = None                            # KSF kolon / perde katman adındaki kat yüksekliği (40x40x300 -> 3,00 m)
    discipline_hints: dict = field(default_factory=dict)      # çalıştırılmayan ama katmanlarında kanıt olan disiplinler -> nesne sayısı
    hatches: dict = field(default_factory=dict)               # tarama özeti ve lejant (parser/hatches.py)
    level_offset: float | None = None                         # yapı ±0,00'ının mutlak kotu (parantezli kot yazılarından)
    zones: list = field(default_factory=list)                 # alan çizgili bölgeler (parser/zones.py)
    usage: dict = field(default_factory=dict)                 # kullanım kanıtı: dükkân / konut / otel … (parser/usage.py)

    def by_type(self, etype: str) -> list[DetectedElement]:
        return [e for e in self.elements if e.etype == etype]

    def to_dict(self) -> dict:
        return {
            "unit": self.unit, "scale": self.scale, "unit_detected": self.unit_detected, "discipline": self.discipline,
            "elements": [e.to_dict() for e in self.elements],
            "layers": [l.to_dict() for l in self.layers],
            "warnings": self.warnings, "suggested_unit": self.suggested_unit, "materials": self.materials,
            "spaces": self.spaces,
            "rebar_mix": self.rebar_mix, "rebar_layers": self.rebar_layers,
            "blocks_seen": self.blocks_seen, "own_block": self.own_block,
            "poz": self.poz, "unit_verdict": self.unit_verdict,
            "disciplines": self.disciplines, "discipline_hints": self.discipline_hints, "hatches": self.hatches,
            "levels": self.levels, "kot": self.kot,
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
    from .detectors.parapet import detect_parapets
    parapets = detect_parapets(drawing, layers_by_type.get("parapet", []), labels, params)

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
    # kullanıcıya iş bırakan boşluklar: hiçbir elemana atanmamış etiketler.
    if beams:
        gap, renamed = _unclaimed_labels(labels, beams, "beam", require_dims=True)
        if gap:
            result.warnings.append(f"{len(gap)} kiriş etiketi hiçbir kirişe atanmadı (kiriş çizgisi bulunamadı ya da etiket uzak): "
                                   + _names(gap) + " — eksikse elle ekleyin")
        if renamed:
            result.warnings.append(f"{len(renamed)} kiriş etiketi bir kirişe bağlanamadı ama yanında aynı kesitle ölçülmüş kiriş var "
                                   f"(miktar sayıldı, ad eşleşmedi): " + _names(renamed) + " — kesitleri Elemanlar ekranından doğrulayın")
    if slabs:
        gap, renamed = _unclaimed_labels(labels, slabs, "slab")
        if gap:
            result.warnings.append(f"{len(gap)} döşeme etiketi kapalı bir hücreye düşmedi (kiriş / perde çizgileri hücreyi kapatmıyor): "
                                   + _names(gap) + " — bu döşemeleri elle ekleyin")
    return columns + walls + beams + slabs + founds + parapets


def _names(names: list[str], limit: int = 12) -> str:
    return ", ".join(names[:limit]) + ("…" if len(names) > limit else "")


def _unclaimed_labels(labels: LabelIndex, elements: list[DetectedElement], type_hint: str,
                      require_dims: bool = False, radius: float = 1.5) -> tuple[list[str], list[str]]:
    """Hiçbir elemana atanmamış etiketleri ikiye ayırır: (gerçek boşluk, yalnız adı eşleşmemiş).

    Aynı marka planda defalarca tekrar yazılır — A4-A5'in kalıp paftasında tek "D1000" döşeme markası 528 kez
    geçiyor ve 26 döşemeye atanmış; kalan kopyalar "hücreye düşmedi" diye eksiklik sayılıyordu. Bu yüzden önce
    adın ölçülen bir elemanda geçip geçmediğine bakılır: geçiyorsa ortada eksik miktar yoktur.

    Adı hiç geçmeyen etiket için ikinci soru: yakınında (radius m) etiketin kendi kesitiyle ölçülmüş bir eleman
    var mı? Varsa miktar sayılmış, yalnız ad eşleşmemiştir (uzun bir kiriş hattı komşu markayı almış olur);
    yoksa eleman gerçekten kaçmıştır ve elle eklenmelidir."""
    used = {e.name for e in elements if e.name}
    gap, renamed = set(), set()
    for i, (ent, lab) in enumerate(labels.items):
        if lab.type_hint != type_hint or not lab.name or i in labels.claimed:
            continue
        if (require_dims and not lab.has_dims) or lab.name in used:
            continue
        pt = ent.points[0] if getattr(ent, "points", None) else None
        (renamed if pt and _section_measured_near(pt, lab, elements, radius) else gap).add(lab.name)
    return sorted(gap), sorted(renamed - gap)


def _section_measured_near(pt, lab, elements: list[DetectedElement], radius: float) -> bool:
    """Etiketin yakınında, etiketin kesitiyle (b/h sırası önemsiz) ölçülmüş bir eleman var mı."""
    if not getattr(lab, "has_dims", False) or lab.b is None or lab.h is None:
        return False
    want = {round(float(lab.b), 2), round(float(lab.h), 2)}
    p = SPoint(pt[0], pt[1])
    for e in elements:
        if len(e.points or []) < 3 or {round(e.b or 0.0, 2), round(e.h or 0.0, 2)} != want:
            continue
        try:
            if Polygon(e.points).distance(p) <= radius:
                return True
        except Exception:
            continue
    return False


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


def _mechanical(drawing: Drawing, layers_by_type: dict[str, list[str]], params: DetectParams,
                result: AnalysisResult) -> list[DetectedElement]:
    els = detect_mechanical(drawing, layers_by_type, params, catalog=getattr(result, "_catalog", None))
    if els:
        codes = Counter(e.meta.get("ksf_code") for e in els)
        result.warnings.append("Mekanik: " + ", ".join(f"{c} {n}" for c, n in codes.most_common(8)) + ("…" if len(codes) > 8 else "")
                               + " (sistem ve çap katman adı / etiketten; yanlışsa Elemanlar sayfasında düzeltin)")
    return els


DISCIPLINE_RUNNERS = {"structural": _structural, "architectural": _architectural, "electrical": _electrical, "mechanical": _mechanical}
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


# Tablo yanındaki eleman adının paftanın hedefini değiştirebileceği durumlar (kolon ve perde aynı paftada çizilir)
REFINABLE: dict[str, set[str]] = {"column": {"column", "shear_wall"}, "shear_wall": {"column", "shear_wall"}}


def analyze_rebar(drawing: Drawing, label: str = "", rebar_target: str | None = None) -> AnalysisResult:
    """Donatı paftası: yalnızca metraj tabloları okunur; her çap bir 'rebar' elemanı (meta: kg, m, hedef eleman, kot)."""
    counts = drawing.layer_counts()
    infos = [LayerInfo(name, counts.get(name, 0), None) for name in drawing.layers]
    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            discipline=REBAR_DISCIPLINE, layers=infos, warnings=list(drawing.warnings))
    # Birim kanıtı: donatı planı çubuk boylarını cm yazar. $INSUNITS yanılıyorsa (A4-A5'te 8 pafta "mm"
    # yazıyor ama cm çizilmiş) bunu çizimin kendi beyanından anlarız; yazı yüksekliği tahmininden güçlüdür.
    from .rebar_plan import plan_bar_groups, suggested_unit as rebar_unit
    birim = rebar_unit(drawing)
    if birim and birim != drawing.unit:
        result.suggested_unit = birim
        result.warnings.append(f"Çizim birimi '{drawing.unit}' yazılı ama donatı boyu yazıları '{birim}' ile "
                               f"uyuşuyor (çubukların yazılı boyu ölçülen boyla ancak böyle tutuyor).")
    tables = parse_rebar_tables(drawing)
    source = "REBAR_TABLE"
    if not tables:
        tables = parse_rebar_label_groups(drawing)
        if tables:
            source = "REBAR_LABELS"
    default_target = rebar_target or target_from_label(label)
    kot = kot_from_label(label)
    src_label = "tablo" if source == "REBAR_TABLE" else "poz"
    by_target: dict[str, float] = {}
    for ti, t in enumerate(tables):
        # Tablonun yanındaki eleman adı yalnız **aynı aileden** bir hedefe çevirebilir: kolon detay paftasındaki
        # perde açılımı perdeye yazılır. Döşeme donatı paftasında tablonun yanına düşen bir kiriş adı ("K1075")
        # bütün tabloyu kirişe yazamaz — o pafta döşeme demirini gösterir (A4-A5: 226 t döşeme demiri kirişe
        # yazılıyordu).
        target = t.target if t.target in REFINABLE.get(default_target, {default_target}) else default_target
        by_target[target] = by_target.get(target, 0.0) + t.total_kg
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
                       "target": target, "kot": kot, "table": ti + 1, "source": src_label,
                       "declared_kg": t.total_kg_declared, "table_kg": round(t.total_kg, 1)}
            result.elements.append(el)
    # Plandan kendi hesabımız: adetli çağrı × çizilen kol boyu. Tablo varsa bağımsız çapraz kontroldür
    # (A4-A5'in 11 donatı paftasında toplam fark %0,2); tablo yoksa demirin **kaynağı** olur.
    plan = plan_bar_groups(drawing)
    result.warnings.extend(plan.warnings)
    if plan.groups:
        if tables:
            tablo_kg = sum(t.total_kg for t in tables)
            fark = 100.0 * (plan.toplam_kg - tablo_kg) / tablo_kg if tablo_kg else 0.0
            result.warnings.append(
                f"Plandan bağımsız hesap (adetli çağrı × çizilen kol boyu): {plan.toplam_kg:,.0f} kg — "
                f"tablonun {tablo_kg:,.0f} kg değerinden %{fark:+.1f} farklı. "
                + ("İki bağımsız yol aynı sonucu veriyor." if abs(fark) <= 5 else
                   "Fark büyük: tabloyu ve çağrı / çubuk eşleşmesini kontrol edin."))
        else:
            for d, kg in sorted(plan.by_dia().items()):
                boy = sum(g.toplam_boy_m for g in plan.groups if g.dia_mm == d)
                el = DetectedElement(etype="rebar", layer="(plan çağrıları)", points=[(0.0, 0.0), (0.3, 0.0), (0.3, 0.3), (0.0, 0.3)],
                                     name=f"Ø{d}", subtype=f"Ø{d}", count=1, length=boy, b=d / 1000.0,
                                     source="REBAR_PLAN", confidence=0.85)
                el.label_raw = f"plan çağrıları: {kg:.0f} kg"
                el.meta = {"dia_mm": d, "weight_kg": round(kg, 1), "length_m": round(boy, 2),
                           "target": default_target, "kot": kot, "source": "plan"}
                result.elements.append(el)
            result.warnings.append(
                f"Metraj tablosu yok; demir **plandan** hesaplandı: {len(plan.groups)} donatı grubu, "
                f"{plan.toplam_kg:,.0f} kg (adet çağrıdan, boy çizilen çubuktan ölçüldü).")
    if not tables and not plan.groups:
        result.warnings.append("Donatı metraj tablosu bulunamadı (başlıkta Ø10 / Ø12 … çap sütunları ve AĞIRLIK satırı aranır), "
                               "adetli poz yazısı ('P45 4Ø14 l=160') ve plandan ölçülebilir donatı çağrısı da yok.")
    if tables:
        from .layer_profile import STRUCTURAL_TYPES
        what = f"{len(tables)} metraj tablosu okundu" if source == "REBAR_TABLE" else "poz yazılarından hesaplandı"
        split = "; ".join(f"{STRUCTURAL_TYPES.get(k, k)} {v:,.0f} kg" for k, v in sorted(by_target.items(), key=lambda kv: -kv[1]))
        result.warnings.append(f"{what}, toplam {sum(t.total_kg for t in tables):,.0f} kg → {split}. Pafta hedefi "
                               f"{STRUCTURAL_TYPES.get(default_target, default_target)} "
                               + ("(plan tipinden)" if rebar_target else "(plan adından; TEMEL / KOLON / KİRİŞ / PERDE yazmıyorsa döşeme)")
                               + "; tablo / poz grubu yakınındaki eleman adına (S… kolon, P… perde) göre ayrıldı"
                               + (f", kot {kot}" if kot else ""))
        for ti, t in enumerate(tables):
            if t.total_kg_declared and abs(t.total_kg - t.total_kg_declared) / t.total_kg_declared > 0.02:
                result.warnings.append(f"Tablo {ti + 1}: genel toplam {t.total_kg_declared:,.0f} kg, çap toplamı {t.total_kg:,.0f} kg — "
                                       "uyuşmuyor, tabloyu kontrol edin")
    return result


# Mahal notunun o mahalle ait sayılması için azami uzaklık: mahal yarı genişliği (0,6·√alan), en az 2 m.
def _room_radius(area_m2: float) -> float:
    return max(2.0, 0.6 * (max(area_m2, 0.0) ** 0.5))


# Mahal sınırını çizen katmanlar: KÇS duvar / kolon / perde kalemleri ve adı duvar-kolon deseni tutan katmanlar.
SPACE_CODES = ("DUVAR", "KOLON", "PERDE")


def space_layers(drawing: Drawing, profile, catalog: Catalog | None) -> list[str]:
    """Mahal sınırı çizen katmanlar; pafta KÇS de olsa sezgisel de olsa aynı kural."""
    out: set[str] = set()
    for name in drawing.layers:
        p = parse_layer(name, catalog) if catalog else None
        if p and any(p.code.upper().startswith(c) for c in SPACE_CODES):
            out.add(name)
            continue
        if profile is not None and profile.classify(name, "architectural") in ("wall", "column", "shear_wall"):
            out.add(name)
    return sorted(out)


def scan_spaces(drawing: Drawing, profile, catalog: Catalog | None) -> tuple[list[dict], list[str]]:
    """Mahalleri çıkarır (sınır katmanı yoksa sessizce boş döner)."""
    if not has_space_labels(drawing):
        return [], []                      # mahal yazısı yok: kalıp / donatı / cephe paftası, çokgen aranmaz
    layers = space_layers(drawing, profile, catalog)
    if not layers:
        return [], []
    sps, warns = detect_spaces(drawing, layers)
    return [x.to_dict() for x in sps], warns


def room_rows(drawing: Drawing) -> list[dict]:
    """Mahal alanı yazıları + mahallin içine yazılmış döşeme bitişi notu.

    "LOBİ 45.20 m2" alanı verir; hemen altındaki "ŞAP 5 CM + SERAMİK 60x60" o mahallin kaplama tipini ve şap
    kalınlığını verir. Her not EN YAKIN mahallin sayılır; komşu mahalle taşmaz. Notu olmayan mahalin şapı
    çizimin genel notundan gelir (services._screed_fallback)."""
    rooms: list[tuple[RoomRow, tuple[float, float] | None]] = []
    notes: list[tuple[dict, tuple[float, float] | None]] = []
    for e in drawing.entities:
        if e.kind != "text" or not e.text:
            continue
        pt = tuple(e.points[0][:2]) if e.points else None
        r = parse_room_area(e.text)
        if r:
            rooms.append((r, pt))
            continue
        f = finish_of(e.text)
        if f:
            notes.append((f, pt))
    rows: list[dict] = []
    seen: set[tuple[str, float]] = set()
    pts: list[tuple[float, float] | None] = []
    for r, pt in rooms:
        key = (r.name, round(r.area_m2, 2))
        if key in seen:
            continue
        seen.add(key)
        row = r.to_dict()
        if pt is not None:
            row["x"], row["y"] = round(pt[0], 3), round(pt[1], 3)
        rows.append(row)
        pts.append(pt)
    for f, npt in notes:
        i = _nearest_room(npt, rows, pts)
        if i is None:
            continue                      # hiçbir mahalle yakın değil: pafta geneli not
        if f["code"] and "finish" not in rows[i]:
            rows[i]["finish"] = {"code": f["code"], "spec": f["spec"], "text": f["text"]}
        if f["screed_cm"] > 0 and not rows[i].get("screed_cm"):
            rows[i]["screed_cm"], rows[i]["screed_note"] = f["screed_cm"], f["text"]
    return rows


def _nearest_room(npt, rows: list[dict], pts: list) -> int | None:
    """Nota en yakın mahal (o mahallin yarıçapı içindeyse). Konumsuz yazı eşleşmez: genel nottur."""
    if npt is None:
        return None
    best, best_d = None, None
    for i, pt in enumerate(pts):
        if pt is None:
            continue
        d = ((pt[0] - npt[0]) ** 2 + (pt[1] - npt[1]) ** 2) ** 0.5
        if d <= _room_radius(rows[i].get("area_m2") or 0.0) and (best_d is None or d < best_d):
            best, best_d = i, d
    return best


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


def _centerline_elements(drawing: Drawing, layer: str, etype: str, dims: list[float]) -> list[DetectedElement]:
    """Tek eksen çizgisiyle çizilmiş KSF kiriş (b×h) / perde (kalınlık): her çizgi bir eleman, kesit katman adından."""
    from .detectors.base import _rect_from_centerline
    from .geometry import polyline_length
    out: list[DetectedElement] = []
    b = dims[0]
    for e in drawing.entities:
        if e.layer != layer or e.kind not in ("line", "polyline") or len(e.points) < 2:
            continue
        L = polyline_length(e.points)
        if L < 0.3:
            continue
        rect = _rect_from_centerline(e.points[0], e.points[-1], b)
        el = DetectedElement(etype=etype, layer=layer, points=rect, area=b * L, perimeter=2 * (b + L), length=L, b=b,
                             source="CENTERLINE", handle=e.handle, confidence=0.95, label_raw=f"KSF {layer.split('-')[-1]}")
        if etype == "beam" and len(dims) >= 2:
            el.h = dims[1]
        elif etype == "shear_wall":
            el.h = L
        out.append(el)
    return out


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
    warns += assign_roof_zones(drawing, elements, catalog)   # çatı: her kapalı alan kendi sistemini nottan alır
    infos = []
    for name in drawing.layers:
        i = info.get(name, {})
        infos.append(LayerInfo(name, counts.get(name, 0), (i.get("code") or "").lower() or None, etype_label=i.get("label"),
                               suggested=i.get("suggested"), mapped_code=i.get("code"), mapped_measure=i.get("measure"),
                               mapped_pattern=i.get("pattern"), auto=bool(i.get("auto"))))
    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            discipline=MAPPED_DISCIPLINE, layers=infos, warnings=list(drawing.warnings) + warns)
    result.unit_verdict = suggested or (drawing.unit if text_count(drawing) >= MIN_TEXTS_FOR_UNIT else None)
    result.poz = poz_catalog(drawing, {}, params)
    sched, sw = schedule_elements(drawing, catalog)
    result.elements = elements + sched
    result.warnings.extend(sw)
    result.materials = materials
    result.rebar_mix = scan_rebar_mix(drawing)
    result.rebar_layers = scan_rebar_layers(drawing)
    result.blocks_seen, result.own_block = scan_blocks(drawing), own_block_of_drawing(drawing)
    result.rooms = room_rows(drawing)
    result.spaces, sp_warns = scan_spaces(drawing, profile, catalog)
    result.warnings.extend(sp_warns)
    if suggested and suggested != drawing.unit:
        result.suggested_unit = suggested
        result.warnings.append(f"Çizim birimi '{drawing.unit}' yazılı ama yazı yükseklikleri '{suggested}' ile uyuşuyor. "
                               f"Birim '{suggested}' olarak alındı; gerekirse çizim ayarlarından değiştirin.")
    sugg = [f"{l.name} → {l.suggested}" for l in infos if l.suggested and not l.mapped_code and not l.auto and l.count > 0]
    if sugg:
        result.warnings.append("Öneri (onaylamak için katmanı eşleyin): " + "; ".join(sugg[:12]) + (" …" if len(sugg) > 12 else ""))
    return result


def analyze_drawing(drawing: Drawing, profile: LayerProfile | None = None,
                    params: DetectParams | None = None, discipline: str = DEFAULT_DISCIPLINE,
                    catalog: Catalog | None = None, label: str = "", defer_on_unit: bool = False,
                    extra_disciplines: tuple[str, ...] | list[str] = (), rebar_target: str | None = None) -> AnalysisResult:
    """defer_on_unit: birim yanlış görünüyorsa dedektörleri çalıştırmadan yalnız öneriyi döndür (analyze_file ilk geçişi).
    extra_disciplines: ana disipline ek olarak aynı paftada çalıştırılacak sezgisel disiplinler (mimari + elektrik gibi).
    Her katman ilk tanıyan disipline gider (sıra: ana, sonra ekler). KSF-… katmanları her zaman standart kuralla ölçülür."""
    profile = profile or LayerProfile()
    params = params or DetectParams()
    catalog = catalog or Catalog()
    if discipline == STANDARD_DISCIPLINE and not any(ksf_structural_type(p.code) for p in standard_layers(drawing, catalog).values()):
        result = analyze_standard(drawing, catalog, params)
        result.spaces, sp_warns = scan_spaces(drawing, profile, catalog)
        result.warnings.extend(sp_warns)
        result.materials = scan_materials(drawing)
        result.rebar_mix = scan_rebar_mix(drawing)
        result.rebar_layers = scan_rebar_layers(drawing)
        result.blocks_seen, result.own_block = scan_blocks(drawing), own_block_of_drawing(drawing)
        result.disciplines = [STANDARD_DISCIPLINE]
        return result
    if discipline == MAPPED_DISCIPLINE:
        return analyze_mapped(drawing, profile, catalog, params, defer_on_unit=defer_on_unit)
    if discipline == REBAR_DISCIPLINE:
        result = analyze_rebar(drawing, label, rebar_target)
        result.materials = scan_materials(drawing)
        result.rebar_mix = scan_rebar_mix(drawing)
        result.rebar_layers = scan_rebar_layers(drawing)
        result.blocks_seen, result.own_block = scan_blocks(drawing), own_block_of_drawing(drawing)
        result.disciplines = [REBAR_DISCIPLINE]
        return result
    is_std = discipline == STANDARD_DISCIPLINE
    if not is_std:
        discipline = discipline if discipline in DISCIPLINE_RUNNERS else DEFAULT_DISCIPLINE
    discs = ([] if is_std else [discipline]) + [d for d in extra_disciplines if d in DISCIPLINE_RUNNERS and d != discipline]
    discs = list(dict.fromkeys(discs))

    counts = drawing.layer_counts()
    ksf = standard_layers(drawing, catalog)
    layer_infos: list[LayerInfo] = []
    layers_by_disc: dict[str, dict[str, list[str]]] = {d: {} for d in discs}
    # KSF-STA kolon / kiriş / perde / döşeme / temel katmanları statik motora gider (beton, kalıp, demir); ölçü katman adından
    ksf_struct: dict[str, list[str]] = {}
    ksf_dims: dict[str, tuple[str, list[float]]] = {}
    for name in drawing.layers:
        if name in ksf:
            p = ksf[name]
            st = ksf_structural_type(p.code) if p.discipline == "STA" else None
            if st:
                ksf_struct.setdefault(st, []).append(name)
                ksf_dims[name] = (st, ksf_spec_dims(p.spec))
                layer_infos.append(LayerInfo(name, counts.get(name, 0), st, etype_label=f"{STRUCTURAL_TYPES[st]} (KSF{' ön boyut' if '_ON' in p.code.upper() else ''})"
                                             + (f" [{p.spec}]" if p.spec else "")))
                continue
            lbl = (p.item.name if p.item else p.code) + (f" [{p.spec}]" if p.spec else "") + f" · {catalog.discipline_name(p.discipline)}"
            layer_infos.append(LayerInfo(name, counts.get(name, 0), p.code.lower(), etype_label=lbl))
            continue
        if is_std:
            layer_infos.append(LayerInfo(name, counts.get(name, 0), None))
            continue
        etype = None
        for d in discs:
            etype = profile.classify(name, d)
            if etype:
                layers_by_disc[d].setdefault(etype, []).append(name)
                break
        layer_infos.append(LayerInfo(name, counts.get(name, 0), etype))
    if ksf_struct:
        if "structural" not in discs:
            discs.append("structural")
            layers_by_disc["structural"] = {}
        for st, names in ksf_struct.items():
            layers_by_disc["structural"].setdefault(st, []).extend(names)
    layers_by_type = layers_by_disc.get(discipline, {})

    result = AnalysisResult(unit=drawing.unit, scale=drawing.scale, unit_detected=drawing.unit_detected,
                            discipline=discipline, layers=layer_infos, warnings=list(drawing.warnings),
                            materials=scan_materials(drawing), rebar_mix=scan_rebar_mix(drawing),
                            rebar_layers=scan_rebar_layers(drawing), blocks_seen=scan_blocks(drawing),
                            own_block=own_block_of_drawing(drawing), disciplines=list(discs))
    result._catalog = catalog   # mekanik dedektörü kalem kodlarını katalogdan doğrular

    if discipline == "structural" or (is_std and ksf_struct):
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
    if ksf_dims:
        # KSF kiriş / perde katmanı tek eksen çizgisiyle çizilmişse (çift çizgi / çokgen yok): çizgiler kesiti katman adından alan elemanlar
        found_layers = {e.layer for e in result.elements}
        for layer, (st, dims) in ksf_dims.items():
            if st in ("beam", "shear_wall") and layer not in found_layers and dims:
                result.elements += _centerline_elements(drawing, layer, st, dims)
        heights = [dims[2] for st, dims in ksf_dims.values() if st in ("column", "shear_wall") and len(dims) >= 3 and 2.0 <= dims[2] <= 8.0]
        if heights:
            result.ksf_height = round(sorted(heights)[len(heights) // 2], 2)
        # KSF katman adındaki ölçü (40x40x300, 30x60, 20) çizimden okunan kesitin yerine geçer
        n_fix = 0
        for el in result.elements:
            spec = ksf_dims.get(el.layer)
            if not spec:
                continue
            st, dims = spec
            if el.etype == "column" and len(dims) >= 2:
                el.b, el.h = min(dims[0], dims[1]), max(dims[0], dims[1])
            elif el.etype == "beam" and len(dims) >= 2:
                el.b, el.h = dims[0], dims[1]
            elif el.etype == "shear_wall" and dims:
                el.b = dims[0]
            elif el.etype in ("slab", "foundation") and dims:
                el.thickness = dims[0]
            else:
                continue
            el.confidence = max(el.confidence, 0.95)
            el.warnings = [w for w in el.warnings if "Etiket" not in w and "etiket" not in w]
            el.label_raw = el.label_raw or f"KSF {el.layer.split('-')[-1]}"
            n_fix += 1
        if n_fix:
            result.warnings.append(f"KSF statik katmanları: {n_fix} elemanın kesiti / kalınlığı katman adından alındı "
                                   f"({', '.join(sorted({STRUCTURAL_TYPES[s] for s, _ in ksf_dims.values()}))}).")
    if ksf:
        # standarda uygun katmanlar (KSF-…) hangi disiplinde olursa olsun katalog kuralıyla ölçülür (statik katmanlar hariç)
        std_elements, std_warns = detect_standard(drawing, catalog, params, skip_layers=set(ksf_dims))
        result.elements += std_elements
        result.warnings.extend(std_warns)
        result.warnings.append(f"KÇS katmanları okundu: {len(ksf)} katman, {len(std_elements) + sum(1 for e in result.elements if e.layer in ksf_dims)} kalem")
    if "architectural" in discs:
        sched, sw = schedule_elements(drawing, catalog)
        result.elements += sched
        result.warnings.extend(sw)
        result.rooms = room_rows(drawing)
        if result.rooms:
            result.warnings.append(f"Mahal alanı yazıları okundu: {len(result.rooms)} mahal, "
                                   f"{sum(r['area_m2'] for r in result.rooms):,.0f} m² (şap / kaplama mahal bazında türetilir)")

    # mahal SINIRLARI: duvar / kolon / perde katmanlarından kapalı alanlar (keşif mahal bazında dökülsün)
    result.spaces, sp_warns = scan_spaces(drawing, profile, catalog)
    result.warnings.extend(sp_warns)
    result.discipline_hints = {} if is_std else discipline_hints(drawing, profile, discs)
    for d, n in result.discipline_hints.items():
        note = " (mimari paftadaki kolon / kiriş izleri statik planda sayılır; ayrıca açmayın)" if d == "structural" else ""
        result.warnings.append(f"Bu paftada {DISCIPLINES.get(d, d)} katmanları da var ({n} nesne): aynı paftada birden çok disiplin "
                               f"çizilmişse çizim ayarlarından ek disiplin olarak açın{note}.")

    # Eşlenmemiş katmanlar nesne sayısıyla ve çoktan aza sıralı bildirilir: 177.595 nesnelik bir katmanla
    # 3 nesnelik bir katman aynı listede aynı görünüyordu, paftanın tamamını tutan katman gözden kaçıyordu.
    unmapped = sorted((li for li in layer_infos if li.etype is None and li.count > 0),
                      key=lambda li: -li.count)
    if unmapped:
        result.warnings.append(
            "Eşlenmemiş katmanlar (eleman sayılmadı): "
            + ", ".join(f"{li.name} ({li.count:,})".replace(",", ".") for li in unmapped[:15])
            + (" ..." if len(unmapped) > 15 else "")
        )
        result.warnings.extend(_dominant_unmapped(unmapped, layer_infos))
    for d in discs:
        for etype, lbl in types_for(d).items():
            if etype == "hole":
                continue
            if etype in layers_by_disc[d] and not result.by_type(etype):
                result.warnings.append(f"{lbl} katmanı var ama eleman tespit edilemedi: {', '.join(layers_by_disc[d][etype])}")
    return result


# Bu orandan büyük bir payı tek başına tutan eşlenmemiş katman, paftanın asıl içeriğidir: sessizce atlanmamalı.
DOMINANT_LAYER_SHARE = 0.30


def _dominant_unmapped(unmapped: list, layer_infos: list) -> list[str]:
    """Paftanın nesnelerinin büyük bölümünü tek başına tutan eşlenmemiş katmanları ayrıca bildirir.

    B2 BLOK'un "BİRİNCİ KAT PLANI" paftasında FB_Prekast katmanı 177.595 nesne tutuyor (paftanın %94'ü) ve
    hiçbir kalem üretmiyordu; uyarı listesinde 3 nesnelik katmanlarla yan yana durduğu için keşfin dışında
    kaldığı fark edilmiyordu. Böyle bir katman keşfin kapsamını belirler, uyarısı da ona göre olmalı."""
    total = sum(li.count for li in layer_infos if li.count > 0)
    if total <= 0:
        return []
    out = []
    for li in unmapped:
        share = li.count / total
        if share < DOMINANT_LAYER_SHARE:
            break                      # liste çoktan aza sıralı
        out.append(f"'{li.name}' katmanı bu paftanın nesnelerinin %{share * 100:.0f}'ini tutuyor "
                   f"({li.count:,} nesne) ama hiçbir keşif kalemi üretmedi. ".replace(",", ".")
                   + "Paftanın asıl içeriği burada olabilir: Elemanlar sayfasında bu katmanı bir katalog "
                     "kalemine ve ölçüm kuralına (adet / m / m²) eşleyin ya da 'ölçülmez' yapın.")
    return out


def analyze_file(path: str, profile: LayerProfile | None = None, params: DetectParams | None = None,
                 unit_override: str | None = None, auto_unit: bool = True,
                 discipline: str = DEFAULT_DISCIPLINE, catalog: Catalog | None = None, label: str = "",
                 extra_disciplines: tuple[str, ...] | list[str] = (), rebar_target: str | None = None) -> AnalysisResult:
    """Dosyayı analiz eder; etiketler birimi yalanlıyorsa (ve kullanıcı birim seçmediyse) doğru birimle yeniden okur."""
    drawing = load_dxf(path, unit_override=unit_override)
    defer = bool(auto_unit and not unit_override)
    result = analyze_drawing(drawing, profile, params, discipline, catalog, label, defer_on_unit=defer,
                             extra_disciplines=extra_disciplines, rebar_target=rebar_target)
    scan = parse_levels([e.text for e in drawing.entities if e.kind == "text" and e.text], label)
    result.levels, result.kot, result.level_offset = scan.levels, scan.kot, scan.offset
    if unit_override and result.suggested_unit and result.suggested_unit != drawing.unit:
        # kullanıcı (ya da pafta oylaması) birimi seçti: yazı kanıtı aksini söylese de yeniden okunmaz, yalnız not düşülür
        result.warnings = [w for w in result.warnings if "yazı yükseklikleri" not in w and "kolon etiketleri" not in w]
        result.warnings.append(f"Birim elle '{unit_override}' seçildi; bu paftanın yazı yükseklikleri '{result.suggested_unit}' ile uyuşuyor "
                               "(görünüş / detay yazıları farklı ölçekte olabilir).")
    if auto_unit and not unit_override and result.suggested_unit and result.suggested_unit != drawing.unit:
        drawing = load_dxf(path, unit_override=result.suggested_unit)     # doğru birimle yeniden okunan çizim
        warn = [w for w in result.warnings if "kolon etiketleri" in w or "yazı yükseklikleri" in w]
        result = analyze_drawing(drawing, profile, params, discipline, catalog, label, extra_disciplines=extra_disciplines,
                                 rebar_target=rebar_target)
        result.levels, result.kot, result.level_offset = scan.levels, scan.kot, scan.offset
        result.unit_detected = False
        result.unit_verdict = drawing.unit
        result.warnings = warn + [w for w in result.warnings if "kolon etiketleri" not in w and "yazı yükseklikleri" not in w]
        result.suggested_unit = drawing.unit
    # Aynı kalemin bitişik parçaları tek elemanda toplanır (kirişlerle bölünmüş döşeme, parçalanmış kaplama)
    result.elements, mw = merge_area_elements(result.elements)
    result.warnings += mw
    read_hatches(drawing, result)
    from .zones import scan_zones
    result.zones = scan_zones(drawing)
    from .usage import scan_usage
    result.usage = scan_usage(drawing)
    return result


def read_hatches(drawing: Drawing, result: AnalysisResult) -> None:
    """Taramalar: malzemesi yazıdan / katmandan okunamamış duvarlara taramanın malzemesi verilir ve
    paftanın tarama özeti saklanır (bkz. parser/hatches.py). Her disiplin buradan geçer."""
    from .hatches import HatchReader, assign_wall_materials
    reader = HatchReader(drawing)
    if not reader.hatches:
        return
    n = assign_wall_materials(reader, result.elements)
    result.hatches = reader.summary()
    result.warnings.extend(reader.warnings)
    if n:
        result.warnings.append(f"{n} duvarın malzemesi taramadan okundu (yazı / katman adı malzemeyi söylemiyordu).")
