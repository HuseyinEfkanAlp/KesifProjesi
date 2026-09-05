"""Router'ların paylaştığı iş mantığı: analiz + kaydetme, proje metrajı / keşfi, fiyat tohumlama, maliyet."""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from .cost.pricing import PriceItem as PriceData, compute_cost, default_price_items
from .models import Drawing, Element, PriceItem, Project
from .parser.analyzer import analyze_file
from .parser.detectors.base import DetectParams
from .db import DATA_DIR
from .parser.layer_profile import (DEFAULT_DISCIPLINE, REBAR_DISCIPLINE, STANDARD_DISCIPLINE, STRUCTURAL_TYPES, TYPE_DISCIPLINE,
                                   LayerProfile)
from .parser.rebar_tables import kot_from_label
from .quantity.boq import (KIND_ORDER, BoqItem, architectural_items, boq_summary, effective_params, electrical_items,
                           sort_items, standard_items, structural_items)
from .standard.catalog import Catalog
from .quantity.engine import ElementData, QuantityLine, QuantityParams, compute_all
from .quantity.summary import summarize

MIN_INCLUDED_CONFIDENCE = 0.4   # altı: eleman listede kalır ama metraja dahil edilmez (kullanıcı açabilir)


def project_profile(project: Project) -> LayerProfile:
    return LayerProfile(project.layer_profile or None)


def detect_params(project: Project) -> DetectParams:
    return DetectParams(default_slab_thickness=project.slab_thickness)


def project_params(project: Project) -> dict:
    return effective_params(project.params or {})


CATALOG_PATH = DATA_DIR / "catalog.json"


def load_catalog() -> Catalog:
    """KÇS kataloğu: varsayılan + DATA_DIR/catalog.json içindeki kullanıcı değişiklikleri."""
    return Catalog.load(CATALOG_PATH)


def save_catalog(cat: Catalog) -> None:
    cat.save(CATALOG_PATH)


def analyze_and_store(drawing: Drawing, project: Project, session: Session) -> Drawing:
    """Çizimi (yeniden) analiz eder; otomatik elemanları yeniler, elle eklenenleri korur."""
    result = analyze_file(drawing.stored_path, project_profile(project), detect_params(project),
                          unit_override=drawing.unit_override, discipline=drawing.discipline or DEFAULT_DISCIPLINE,
                          catalog=load_catalog(), label=drawing.label or drawing.filename)

    for old in session.exec(select(Element).where(Element.drawing_id == drawing.id, Element.manual == False)):  # noqa: E712
        session.delete(old)
    for det in result.elements:
        session.add(Element(
            drawing_id=drawing.id, etype=det.etype, subtype=det.subtype, name=det.name, layer=det.layer,
            b=det.b, h=det.h, thickness=det.thickness, area=det.area, length=det.length,
            perimeter=det.perimeter, count=det.count, confidence=det.confidence, warnings=det.warnings,
            label_raw=det.label_raw, source=det.source, handle=det.handle,
            points=[[round(x, 4), round(y, 4)] for x, y in det.points],
            included=det.confidence >= MIN_INCLUDED_CONFIDENCE, meta=det.meta or {},
        ))
    drawing.unit = result.unit
    drawing.unit_detected = result.unit_detected
    drawing.layers = [l.to_dict() for l in result.layers]
    drawing.warnings = result.warnings
    drawing.analyzed_at = datetime.utcnow()
    session.add(drawing)
    session.commit()
    session.refresh(drawing)
    return drawing


def recompute_derived(el: Element) -> None:
    """Kullanıcı b/h/uzunluk değiştirdiğinde türetilen alan/çevreyi günceller."""
    if el.etype == "column" and el.b and el.h:
        el.area = el.b * el.h
        el.perimeter = 2 * (el.b + el.h)
    elif el.etype == "shear_wall" and el.b and el.length:
        el.area = el.b * el.length
        el.perimeter = 2 * (el.b + el.length)
    elif el.etype == "beam" and el.b and el.length:
        el.area = el.b * el.length
    elif el.etype == "foundation" and el.subtype == "strip" and el.b and el.length:
        el.area = el.b * el.length
        el.perimeter = 2 * (el.b + el.length)
    elif el.etype == "wall" and el.b and el.length:
        el.area = el.b * el.length
    elif el.etype in ("door", "window") and el.b and el.h:
        el.area = el.b * el.h
    elif el.etype == "tray" and el.b and el.length:
        el.area = el.b * el.length


def dominant_beam_depth(elements) -> float | None:
    """Kattaki kirişlerin (uzunlukla ağırlıklı) medyan yüksekliği; kolon/perde kalıbı kiriş altına kadar hesaplanır."""
    pairs = [(float(e.h), float(e.length or 0.0)) for e in elements if e.etype == "beam" and e.h]
    if not pairs:
        return None
    pairs.sort()
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    acc = 0.0
    for h, w in pairs:
        acc += w
        if acc >= total / 2:
            return h
    return pairs[-1][0]


def _included_elements(d: Drawing, session: Session) -> list[Element]:
    return session.exec(select(Element).where(Element.drawing_id == d.id, Element.included == True)).all()  # noqa: E712


def rebar_table_rows(project: Project, session: Session) -> list[dict]:
    """Donatı paftalarından okunan tablo satırları (çap bazında kg) — özet ve keşif için."""
    rows: list[dict] = []
    for d in session.exec(select(Drawing).where(Drawing.project_id == project.id, Drawing.discipline == REBAR_DISCIPLINE)).all():
        for e in _included_elements(d, session):
            if e.etype != "rebar" or not e.meta:
                continue
            m = e.meta
            rows.append({"drawing": d.label or d.filename, "drawing_id": d.id, "kot": m.get("kot") or kot_from_label(d.label),
                         "target": m.get("target", "slab"), "dia_mm": m.get("dia_mm"), "weight_kg": m.get("weight_kg", 0.0),
                         "length_m": m.get("length_m", 0.0)})
    return rows


def project_quantities(project: Project, session: Session) -> tuple[list[QuantityLine], dict, dict]:
    """Statik metraj: (satırlar, özet, element_info) döndürür. Yalnızca statik eleman tipleri girer;
    donatı paftalarındaki tablolar demiri çap bazında verir ve ilgili eleman tipinin oran tahminini geçersiz kılar."""
    drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    lines: list[QuantityLine] = []
    info: dict = {}
    for d in drawings:
        if d.discipline == REBAR_DISCIPLINE:
            continue
        elements = [e for e in _included_elements(d, session) if e.etype in STRUCTURAL_TYPES]
        if not elements:
            continue
        net_slabs = any(e.etype == "slab" and e.subtype == "net" for e in elements)
        params = QuantityParams(storey_height=d.storey_height or project.storey_height, slab_thickness=project.slab_thickness,
                                storey_count=d.storey_count, beam_full_height=net_slabs,
                                beam_depth=dominant_beam_depth(elements),
                                rebar_ratios={**QuantityParams().rebar_ratios, **(project.rebar_ratios or {})})
        data = [ElementData.from_obj(e) for e in elements]
        for e in elements:
            info[e.id] = {"drawing": d.label or d.filename, "drawing_id": d.id, "kot": kot_from_label(d.label), "layer": e.layer,
                          "b": e.b, "h": e.h, "thickness": e.thickness, "area": round(e.area, 4), "length": round(e.length, 4),
                          "warnings": e.warnings}
        lines.extend(compute_all(data, params))
    return lines, summarize(lines, rebar_table_rows(project, session), info), info


def project_boq(project: Project, session: Session, summary: dict | None = None) -> list[BoqItem]:
    """Tüm disiplinlerin keşif listesi."""
    if summary is None:
        _, summary, _ = project_quantities(project, session)
    params = project_params(project)
    drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    arch, elec, std = [], [], []
    for d in drawings:
        elements = _included_elements(d, session)
        entry = {"label": d.label or d.filename, "storey_count": d.storey_count,
                 "storey_height": d.storey_height or project.storey_height, "slab_thickness": project.slab_thickness,
                 "elements": elements}
        if d.discipline == STANDARD_DISCIPLINE:
            std.append(entry)
            continue
        if d.discipline == REBAR_DISCIPLINE:
            continue
        if any(TYPE_DISCIPLINE.get(e.etype) == "architectural" for e in elements):
            arch.append({**entry, "elements": [e for e in elements if TYPE_DISCIPLINE.get(e.etype) == "architectural"]})
        if any(TYPE_DISCIPLINE.get(e.etype) == "electrical" for e in elements):
            elec.append({**entry, "elements": [e for e in elements if TYPE_DISCIPLINE.get(e.etype) == "electrical"]})
    items = structural_items(summary, params) + architectural_items(arch, params) + electrical_items(elec, params)
    if std:
        items += standard_items(std, params, load_catalog())
    return sort_items(items)


def ensure_price_items(project: Project, items: list[BoqItem], session: Session) -> list[PriceItem]:
    existing = {p.key: p for p in session.exec(select(PriceItem).where(PriceItem.project_id == project.id))}
    for d in default_price_items(items):
        if d.key not in existing:
            item = PriceItem(project_id=project.id, key=d.key, name=d.name, unit=d.unit)
            session.add(item)
            existing[d.key] = item
    session.commit()
    order = {k: i for i, k in enumerate(KIND_ORDER)}
    return sorted(existing.values(), key=lambda p: (order.get(p.key.split(":")[0], 99), "*" not in p.key, p.name))


def to_price_data(p: PriceItem) -> PriceData:
    return PriceData(p.key, p.name, p.unit, p.unit_price or 0.0, p.labor_price or 0.0, p.brand or "",
                     p.hours_per_unit or 0.0, p.crew_size or 0.0)


def project_cost(project: Project, session: Session) -> tuple[list[QuantityLine], dict, dict, list[BoqItem], dict]:
    lines, summary, info = project_quantities(project, session)
    items = project_boq(project, session, summary)
    prices = ensure_price_items(project, items, session)
    cost = compute_cost(items, [to_price_data(p) for p in prices], project.vat_rate,
                        hours_per_day=float(project_params(project).get("work_hours_per_day") or 8.0))
    return lines, summary, info, items, cost


def boq_payload(items: list[BoqItem]) -> dict:
    return boq_summary(items)
