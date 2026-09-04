"""Router'ların paylaştığı iş mantığı: analiz + kaydetme, proje metrajı, fiyat tohumlama."""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from .cost.pricing import PriceItem as PriceData, compute_cost, default_price_items
from .models import Drawing, Element, PriceItem, Project
from .parser.analyzer import analyze_file
from .parser.detectors.base import DetectParams
from .parser.layer_profile import LayerProfile
from .quantity.engine import ElementData, QuantityLine, QuantityParams, compute_all
from .quantity.summary import summarize

MIN_INCLUDED_CONFIDENCE = 0.4   # altı: eleman listede kalır ama metraja dahil edilmez (kullanıcı açabilir)


def project_profile(project: Project) -> LayerProfile:
    return LayerProfile(project.layer_profile or None)


def detect_params(project: Project) -> DetectParams:
    return DetectParams(default_slab_thickness=project.slab_thickness)


def analyze_and_store(drawing: Drawing, project: Project, session: Session) -> Drawing:
    """Çizimi (yeniden) analiz eder; otomatik elemanları yeniler, elle eklenenleri korur."""
    result = analyze_file(drawing.stored_path, project_profile(project), detect_params(project),
                          unit_override=drawing.unit_override)

    for old in session.exec(select(Element).where(Element.drawing_id == drawing.id, Element.manual == False)):  # noqa: E712
        session.delete(old)
    for det in result.elements:
        session.add(Element(
            drawing_id=drawing.id, etype=det.etype, subtype=det.subtype, name=det.name, layer=det.layer,
            b=det.b, h=det.h, thickness=det.thickness, area=det.area, length=det.length,
            perimeter=det.perimeter, count=det.count, confidence=det.confidence, warnings=det.warnings,
            label_raw=det.label_raw, source=det.source, handle=det.handle,
            points=[[round(x, 4), round(y, 4)] for x, y in det.points],
            included=det.confidence >= MIN_INCLUDED_CONFIDENCE,
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


def project_quantities(project: Project, session: Session) -> tuple[list[QuantityLine], dict, dict]:
    """(satırlar, özet, element_info) döndürür."""
    drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    lines: list[QuantityLine] = []
    info: dict = {}
    for d in drawings:
        elements = session.exec(select(Element).where(Element.drawing_id == d.id, Element.included == True)).all()  # noqa: E712
        net_slabs = any(e.etype == "slab" and e.subtype == "net" for e in elements)
        params = QuantityParams(storey_height=d.storey_height or project.storey_height, slab_thickness=project.slab_thickness,
                                storey_count=d.storey_count, beam_full_height=net_slabs,
                                beam_depth=dominant_beam_depth(elements),
                                rebar_ratios={**QuantityParams().rebar_ratios, **(project.rebar_ratios or {})})
        data = [ElementData.from_obj(e) for e in elements]
        for e in elements:
            info[e.id] = {"drawing": d.label or d.filename, "drawing_id": d.id, "layer": e.layer, "b": e.b, "h": e.h,
                          "thickness": e.thickness, "area": round(e.area, 4), "length": round(e.length, 4),
                          "warnings": e.warnings}
        lines.extend(compute_all(data, params))
    return lines, summarize(lines), info


def ensure_price_items(project: Project, summary: dict, session: Session) -> list[PriceItem]:
    existing = {p.key: p for p in session.exec(select(PriceItem).where(PriceItem.project_id == project.id))}
    for d in default_price_items(summary):
        if d.key not in existing:
            item = PriceItem(project_id=project.id, key=d.key, name=d.name, unit=d.unit, unit_price=0.0)
            session.add(item)
            existing[d.key] = item
    session.commit()
    return sorted(existing.values(), key=lambda p: (p.key.split(":")[0], "*" not in p.key, p.key))


def project_cost(project: Project, session: Session) -> tuple[list[QuantityLine], dict, dict, dict]:
    lines, summary, info = project_quantities(project, session)
    items = ensure_price_items(project, summary, session)
    cost = compute_cost(summary, [PriceData(p.key, p.name, p.unit, p.unit_price) for p in items], project.vat_rate)
    return lines, summary, info, cost
