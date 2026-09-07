"""Router'ların paylaştığı iş mantığı: analiz + kaydetme, proje metrajı / keşfi, fiyat tohumlama, maliyet."""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from .cost.pricing import PriceItem as PriceData, compute_cost, default_price_items
from .models import Drawing, Element, PriceItem, Project
from .parser.analyzer import analyze_file
from .parser.detectors.base import DetectParams
from .db import DATA_DIR
from .parser.layer_profile import (DEFAULT_DISCIPLINE, MAPPED_DISCIPLINE, REBAR_DISCIPLINE, STANDARD_DISCIPLINE, STRUCTURAL_TYPES,
                                   TYPE_DISCIPLINE, LayerProfile)
from .parser.rebar_tables import kot_from_label
from .parser.materials import merge_materials
from .quantity.boq import (KIND_ORDER, BoqItem, architectural_items, boq_summary, effective_params, electrical_items,
                           expand_systems, sort_items, standard_items, structural_items)
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
    drawing.materials = result.materials or {}
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
        if d.discipline in (REBAR_DISCIPLINE, MAPPED_DISCIPLINE, STANDARD_DISCIPLINE):
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


def project_boq(project: Project, session: Session, summary: dict | None = None, expand: bool = True) -> list[BoqItem]:
    """Tüm disiplinlerin keşif listesi. expand=True: katmanlı sistemler bileşenlerine açılır (project_systems kararıyla)."""
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
        if d.discipline in (STANDARD_DISCIPLINE, MAPPED_DISCIPLINE):
            std.append(entry)
            continue
        if d.discipline == REBAR_DISCIPLINE:
            continue
        ksf = [e for e in elements if (e.meta or {}).get("ksf_code")]   # poz listesi gibi katalog kodlu elemanlar
        if ksf:
            std.append({**entry, "elements": ksf})
        if any(TYPE_DISCIPLINE.get(e.etype) == "architectural" for e in elements):
            arch.append({**entry, "elements": [e for e in elements if TYPE_DISCIPLINE.get(e.etype) == "architectural"]})
        if any(TYPE_DISCIPLINE.get(e.etype) == "electrical" for e in elements):
            elec.append({**entry, "elements": [e for e in elements if TYPE_DISCIPLINE.get(e.etype) == "electrical"]})
    items = structural_items(summary, params) + architectural_items(arch, params) + electrical_items(elec, params)
    catalog = load_catalog()
    if std:
        items += standard_items(std, params, catalog)
    items += facade_items(project, session, catalog, items, drawings, params)
    if expand:
        systems = project_systems(project, session, catalog=catalog, items=items, drawings=drawings)
        if systems["systems"]:
            items = expand_systems(items, systems["systems"], catalog)
    return sort_items(items)


FACADE_HULL_RATIO = 0.7
FACADE_HULL_MARGIN = 0.15   # m: kolon dış yüzünden cephe yüzeyine (duvar + kaplama) pay
FACADE_GAP_CLOSE = 0.6      # m: döşeme / kiriş / kolon çokgenleri arasındaki boşluklar bu ölçüye kadar kapatılır


def building_footprint(elements) -> "tuple[float, float] | None":
    """Kat planındaki döşeme / kiriş / kolon / perde çokgenlerinden bina oturumu: (alan m², dış çevre m).

    Çokgenler birleştirilir, aralardaki küçük boşluklar kapatılır, delikler doldurulur (dış hat = cephe). Döşeme yoksa
    (yalnız kolon), kolonların concave hull'u alınır."""
    from shapely import concave_hull
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = [Polygon(e.points).buffer(0) for e in elements
             if e.etype in ("slab", "beam", "column", "shear_wall") and len(e.points or []) >= 3]
    polys = [g for g in polys if not g.is_empty and g.is_valid]
    if len(polys) < 3:
        return None
    try:
        u = unary_union(polys)
        u = u.buffer(FACADE_GAP_CLOSE, join_style=2).buffer(-FACADE_GAP_CLOSE, join_style=2)
        has_plate = any(e.etype in ("slab", "beam") for e in elements)
        if not has_plate:
            u = concave_hull(u, ratio=FACADE_HULL_RATIO)
        u = u.buffer(FACADE_HULL_MARGIN, join_style=2)
        parts = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
        parts = [Polygon(g.exterior) for g in parts if g.geom_type == "Polygon" and not g.is_empty]
    except Exception:
        return None
    if not parts:
        return None
    return float(sum(g.area for g in parts)), float(sum(g.exterior.length for g in parts))


def facade_area(project: Project, session: Session, items: list[BoqItem] | None = None,
                drawings: list[Drawing] | None = None, params: dict | None = None) -> dict:
    """Cephe brüt / net alanı ve kaynağı.

    Öncelik: (1) görünüşte ölçülen CEPHE_BRUT kalemi, (2) proje parametresi facade_gross_m2, (3) tahmin: kalıp planındaki
    kolon / perde dış hattı (concave hull) çevresi × kat yüksekliği × kat sayısı, her kat planı için toplanır.
    Net = brüt − cam alanı (CAM kalemi varsa)."""
    params = params or project_params(project)
    if drawings is None:
        drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    if items is None:
        items = project_boq(project, session, expand=False)
    measured = sum(it.quantity for it in items if it.kind == "cephe_brut" and not it.detail.get("info"))
    glass = sum(it.quantity for it in items if it.kind == "cam" and it.unit == "m²")
    out = {"gross": 0.0, "net": 0.0, "source": "none", "detail": "", "glass": round(glass, 2), "per_drawing": []}
    if measured > 0:
        out.update(gross=measured, source="measured", detail="görünüşteki cephe brüt alanı kalemi (CEPHE_BRUT)")
    elif params.get("facade_gross_m2"):
        out.update(gross=float(params["facade_gross_m2"]), source="manual", detail="proje parametresi (elle girildi)")
    else:
        total = 0.0
        for d in drawings:
            if d.discipline != DEFAULT_DISCIPLINE:
                continue
            els = _included_elements(d, session)
            if not any(e.etype in ("column", "shear_wall") for e in els):
                continue   # yalnız temel paftası: cephe vermez
            fp = building_footprint(els)
            if not fp or fp[0] < 10:
                continue
            per = fp[1]
            h = d.storey_height or project.storey_height
            a = per * h * max(1, d.storey_count)
            total += a
            out["per_drawing"].append({"drawing": d.label or d.filename, "drawing_id": d.id, "perimeter": round(per, 2),
                                       "storey_height": h, "storey_count": d.storey_count, "area": round(a, 2)})
        if total > 0:
            out.update(gross=total, source="estimated",
                       detail="kalıp planı kolon / perde dış hattı çevresi × kat yüksekliği × kat sayısı (tahmin; elle düzeltilebilir)")
    out["gross"] = round(out["gross"], 2)
    out["net"] = round(max(out["gross"] - glass, 0.0), 2)
    return out


def facade_items(project: Project, session: Session, catalog: Catalog, items: list[BoqItem],
                 drawings: list[Drawing], params: dict) -> list[BoqItem]:
    """Cephe sistemi seçildiyse: cephe brüt alanı bilgi satırı (fiyatlanmaz) + sistem kalemi (miktar = net cephe alanı).
    Sistem seçilmediyse keşfe bir şey eklenmez; alan yalnız sistem panelinde bilgi olarak görünür."""
    code = str(params.get("facade_system") or "").strip().upper()
    if not code:
        return []
    fa = facade_area(project, session, items, drawings, params)
    if fa["gross"] <= 0:
        return []
    out: list[BoqItem] = []
    if fa["source"] != "measured":
        it = BoqItem(key="cephe_brut:*", kind="cephe_brut", group="*", label="Cephe brüt alanı", unit="m²",
                     quantity=fa["gross"], discipline="ksf:CEP", kind_label="Cephe brüt alanı", discipline_label=catalog.discipline_name("CEP"),
                     notes=[f"Kaynak: {fa['detail']}", "Bilgi satırı; fiyatlanmaz"], detail={"info": True, "source": fa["source"]})
        out.append(it)
    sys_item = catalog.get(code)
    if sys_item and not any(i.kind == sys_item.code.lower() for i in items):
        note = f"Miktar = net cephe alanı ({fa['gross']:,.0f} m² brüt − {fa['glass']:,.0f} m² cam); kaynak: {fa['detail']}"
        out.append(BoqItem(key=f"{sys_item.code.lower()}:*", kind=sys_item.code.lower(), group="*", label=sys_item.name,
                           unit=sys_item.unit, quantity=fa["net"], discipline=f"ksf:{sys_item.discipline}", kind_label=sys_item.name,
                           discipline_label=catalog.discipline_name(sys_item.discipline), notes=[note],
                           detail={"facade_source": fa["source"]}))
    return out


COMPONENT_SOURCES = ("project", "manual", "default", "missing", "excluded")


def project_systems(project: Project, session: Session, catalog: Catalog | None = None,
                    items: list[BoqItem] | None = None, drawings: list[Drawing] | None = None) -> dict:
    """Projedeki katmanlı sistemler (kenet çatı, mantolama…) ve bileşen kararları.

    Bir sistem, bir çizimde o kalem koduyla ölçülmüşse (katman eşlemesi ya da KSF katmanı) projede vardır; miktarı
    keşif listesinden gelir. Her bileşen için karar sırası: kullanıcı kararı (project.systems) > çizim yazılarında
    kanıt (drawing.materials: "projede yazıyor") > yok ("projede yok": kullanıcı ekler ya da yok sayar).
    """
    catalog = catalog or load_catalog()
    if drawings is None:
        drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    if items is None:
        items = project_boq(project, session, expand=False)
    evidence = merge_materials([d.materials or {} for d in drawings])
    overrides = project.systems or {}
    out: list[dict] = []
    warnings: list[str] = []
    for it in items:
        sys_item = catalog.get(it.kind)
        if not sys_item or not sys_item.is_system:
            continue
        ov = overrides.get(sys_item.code) or {}
        comps = []
        missing = []
        for comp in sys_item.components:
            citem = catalog.get(comp["code"])
            ev = evidence.get(comp["code"]) or {}
            user = ov.get(comp["code"]) or {}
            has_ev = bool(ev.get("evidence"))
            if "include" in user:
                include = bool(user["include"])
                source = ("project" if has_ev else "manual") if include else "excluded"
            else:
                include = has_ev
                source = "project" if has_ev else "missing"
            spec = (user.get("spec") or ev.get("spec") or comp.get("spec") or "").strip()
            row = {"code": comp["code"], "name": citem.name if citem else comp["code"], "unit": citem.unit if citem else "",
                   "discipline": citem.discipline if citem else sys_item.discipline, "factor": comp["factor"],
                   "default_spec": comp.get("spec") or "", "spec": spec, "include": include, "source": source,
                   "evidence": list(ev.get("evidence") or []), "quantity": round(it.quantity * comp["factor"], 3)}
            comps.append(row)
            if source == "missing":
                missing.append(row["name"])
        out.append({"code": sys_item.code, "name": sys_item.name, "discipline": sys_item.discipline,
                    "discipline_label": catalog.discipline_name(sys_item.discipline), "unit": sys_item.unit,
                    "quantity": round(it.quantity, 3), "spec": it.group if it.group != "*" else "", "key": it.key,
                    "components": comps, "missing": missing,
                    "system_evidence": list((evidence.get(sys_item.code) or {}).get("evidence") or [])})
        if missing:
            warnings.append(f"{sys_item.name} ({it.quantity:,.0f} {sys_item.unit}): projede yazmıyor → {', '.join(missing)}. "
                            "Projede varsa ekleyin, yoksa 'yok' bırakın.")
    return {"systems": out, "warnings": warnings,
            "missing": sum(len(sy["missing"]) for sy in out),
            "evidence_codes": sorted(evidence),
            "facade": facade_area(project, session, items, drawings)}


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
