"""Router'ların paylaştığı iş mantığı: analiz + kaydetme, proje metrajı / keşfi, fiyat tohumlama, maliyet."""
from __future__ import annotations

import re
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
                           expand_systems, slug, sort_items, standard_items, structural_items)
from .standard.catalog import Catalog, parse_layer
from .quantity.engine import ElementData, QuantityLine, QuantityParams, compute_all
from .quantity.recipes import expand_recipes
from .quantity.summary import summarize

MIN_INCLUDED_CONFIDENCE = 0.4   # altı: eleman listede kalır ama metraja dahil edilmez (kullanıcı açabilir)


def project_profile(project: Project) -> LayerProfile:
    return LayerProfile(project.layer_profile or None)


def detect_params(project: Project, session: Session | None = None) -> DetectParams:
    """Dedektör parametreleri; oturum verilirse projedeki öteki çizimlerin doğrama poz bilgisi (ölçü, kapı / pencere,
    poz önekleri) eklenir — plandaki 'EMP1' yazıları bununla kapı / pencere sayılır."""
    p = DetectParams(default_slab_thickness=project.slab_thickness)
    pp = project.params or {}
    if pp.get("roof_system"):
        p.system_overrides["CATI_KIREMIT"] = str(pp["roof_system"]).strip().upper()
    if pp.get("facade_system"):
        p.system_overrides["MANTOLAMA"] = str(pp["facade_system"]).strip().upper()
    if session is None or project.id is None:
        return p
    sizes, kinds, prefixes = {}, {}, set()
    drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    for d in drawings:
        poz = d.poz or {}
        sizes.update(poz.get("sizes") or {})
        kinds.update(poz.get("kinds") or {})
        prefixes.update(poz.get("prefixes") or [])
    ids = [d.id for d in drawings if d.id is not None]
    if ids:
        for e in session.exec(select(Element).where(Element.drawing_id.in_(ids), Element.etype == "dograma")):  # type: ignore[attr-defined]
            if not e.subtype:
                continue
            prefixes.add(re.sub(r"\d.*$", "", e.subtype))
            note = str((e.meta or {}).get("note") or "").replace("i", "İ").upper()
            if e.subtype not in kinds:
                if "KAPI" in note or "DOOR" in note:
                    kinds[e.subtype] = "door"
                elif "PENCERE" in note or "WINDOW" in note:
                    kinds[e.subtype] = "window"
    p.poz_sizes, p.poz_kinds, p.poz_prefixes = sizes, kinds, tuple(sorted(prefixes))
    return p


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
    from .planset import PLAN_TYPE_BY_CODE
    params = detect_params(project, session)
    pt = PLAN_TYPE_BY_CODE.get(drawing.plan_type or "")
    if pt is not None and not pt.analyze:
        params.auto_map = False    # kesit / detay / şema paftası: kesitteki duvar taraması plan duvarı değildir, otomatik eşleme yok
    result = analyze_file(drawing.stored_path, project_profile(project), params,
                          unit_override=drawing.unit_override, discipline=drawing.discipline or DEFAULT_DISCIPLINE,
                          catalog=load_catalog(), label=drawing.label or drawing.filename,
                          extra_disciplines=tuple(drawing.disciplines or []))
    if pt is not None and not pt.analyze:
        result.warnings.insert(0, f"{pt.label}: metraja girmez; katman adından otomatik eşleme kapalı (kesitteki duvar / sıva taraması plan miktarı değildir). "
                                  "Kesit notları çatı / cephe sistemi kanıtı ve kotlar için okunur.")

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
    drawing.rooms = result.rooms or []
    drawing.poz = result.poz or {}
    drawing.unit_verdict = result.unit_verdict
    drawing.discipline_hints = result.discipline_hints or {}
    drawing.levels = [float(v) for v in (result.levels or [])]
    drawing.kot = result.kot
    if result.ksf_height and not drawing.storey_height:
        drawing.storey_height = result.ksf_height      # KSF katman adındaki kat yüksekliği (KOLON-40x40x300 -> 3,00 m)
        result.warnings.append(f"Kat yüksekliği KSF katman adından alındı: {result.ksf_height:g} m")
    drawing.analyzed_at = datetime.utcnow()
    session.add(drawing)
    session.commit()
    session.refresh(drawing)
    return drawing


DEFAULT_STOREY_HEIGHT = 3.0


def storey_heights(project: Project, drawings: list[Drawing]) -> dict:
    """Her çizim için kat yüksekliği ve kaynağı; proje için etkin kat yüksekliği.

    Sıra: çizime elle girilen > çizimin kotu ile bir üst kat seviyesi arasındaki fark (kotlar planlardaki / kesitlerdeki kot
    yazılarından) > plan adına göre kat sırası (bodrum, zemin, birinci…) ile seviye dizisi > projeye girilen H > kat
    seviyelerinin medyan farkı > 3,0 m varsayılan."""
    from .parser.levels import floor_levels, floor_rank
    all_levels = [float(v) for d in drawings for v in (d.levels or [])]
    for d in drawings:
        if d.kot is not None:
            all_levels.append(float(d.kot))
    floors = floor_levels(all_levels)
    diffs = [round(b - a, 2) for a, b in zip(floors, floors[1:])]
    med = round(sorted(diffs)[len(diffs) // 2], 2) if diffs else None
    if project.storey_height and project.storey_height > 0:
        effective, source = float(project.storey_height), "parametre"
    elif med:
        effective, source = med, "kotlardan (medyan kat farkı)"
    else:
        effective, source = DEFAULT_STOREY_HEIGHT, "varsayılan"

    def above(level: float) -> float | None:
        ups = [f for f in floors if f > level + 0.5]
        return ups[0] if ups else None

    per: dict[int, dict] = {}
    ranked = []
    for d in drawings:
        if d.storey_height and d.storey_height > 0:
            per[d.id] = {"height": float(d.storey_height), "source": "çizime girildi", "kot": d.kot}
            continue
        if d.kot is not None:
            nxt = above(float(d.kot))
            if nxt is not None:
                per[d.id] = {"height": round(nxt - float(d.kot), 2), "source": f"kot {d.kot:+.2f} → {nxt:+.2f}", "kot": d.kot}
                continue
        r = floor_rank(d.label or d.filename)
        if r is not None and d.discipline in (DEFAULT_DISCIPLINE, "architectural", "electrical", "mechanical"):
            ranked.append((r, d))
        else:
            per[d.id] = {"height": effective, "source": source, "kot": d.kot}
    # kotu olmayan planlar: kat sırasına göre seviye dizisine oturtulur (aynı sıradaki planlar aynı seviyeyi alır)
    ranked.sort(key=lambda t: t[0])
    distinct = sorted({r for r, _ in ranked})
    rank_level = {r: floors[i] for i, r in enumerate(distinct) if i < len(floors)}
    for r, d in ranked:
        lvl = rank_level.get(r)
        nxt = above(lvl) if lvl is not None else None
        if lvl is not None and nxt is not None:
            per[d.id] = {"height": round(nxt - lvl, 2), "source": f"kat sırası → kot {lvl:+.2f} → {nxt:+.2f}", "kot": lvl}
        else:
            per[d.id] = {"height": effective, "source": source, "kot": lvl}
    return {"levels": floors, "heights": diffs, "effective": effective, "source": source, "per_drawing": per}


def storey_height_of(project: Project, d: Drawing, sh: dict | None = None) -> float:
    sh = sh or storey_heights(project, [d])
    return float(sh["per_drawing"].get(d.id, {}).get("height") or sh["effective"])


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
    sh = storey_heights(project, drawings)
    lines: list[QuantityLine] = []
    info: dict = {}
    for d in drawings:
        if d.discipline == REBAR_DISCIPLINE:
            continue
        elements = [e for e in _included_elements(d, session) if e.etype in STRUCTURAL_TYPES]
        if not elements:
            continue
        net_slabs = any(e.etype == "slab" and e.subtype == "net" for e in elements)
        params = QuantityParams(storey_height=storey_height_of(project, d, sh), slab_thickness=project.slab_thickness,
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
    catalog = load_catalog()
    drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    sh = storey_heights(project, drawings)
    els_by_id = {d.id: _included_elements(d, session) for d in drawings}
    # doğrama pozları: adet poz listesinden (proje toplamı), ölçü görünüş / doğrama paftasından, kapı-pencere ayrımı nottan
    poz_sizes, poz_kinds, sched_poz = {}, {}, set()
    for d in drawings:
        poz_sizes.update((d.poz or {}).get("sizes") or {})
        poz_kinds.update((d.poz or {}).get("kinds") or {})
        for e in els_by_id[d.id]:
            if e.etype == "dograma" and e.subtype:
                sched_poz.add(e.subtype)
                note = str((e.meta or {}).get("note") or "").replace("i", "İ").upper()
                if e.subtype not in poz_kinds and ("KAPI" in note or "DOOR" in note):
                    poz_kinds[e.subtype] = "door"

    def ksf_entry(e):
        if e.etype != "dograma":
            return e
        size = poz_sizes.get(e.subtype or "")
        kind = poz_kinds.get(e.subtype or "", "window")
        return {"etype": e.etype, "subtype": e.subtype, "name": e.name, "layer": e.layer, "count": e.count,
                "length": e.length, "area": e.area, "thickness": e.thickness,
                "b": size[0] if size else None, "h": size[1] if size else None,
                "meta": {**(e.meta or {}), "opening_kind": kind}}

    arch, elec, std = [], [], []
    for d in drawings:
        elements = els_by_id[d.id]
        entry = {"label": d.label or d.filename, "storey_count": d.storey_count,
                 "storey_height": storey_height_of(project, d, sh), "slab_thickness": project.slab_thickness,
                 "height_source": sh["per_drawing"].get(d.id, {}).get("source", sh["source"]),
                 "elements": [ksf_entry(e) for e in elements]}
        if d.discipline in (STANDARD_DISCIPLINE, MAPPED_DISCIPLINE):
            std.append(entry)
            continue
        if d.discipline == REBAR_DISCIPLINE:
            continue
        # katalog kodlu elemanlar: poz listesi (meta.ksf_code) ve sezgisel paftadaki KSF-… katmanları (her disiplinde standart kuralla ölçülür)
        ksf = [ksf_entry(e) for e in elements if (e.meta or {}).get("ksf_code") or parse_layer(e.layer or "", catalog)]
        if ksf:
            std.append({**entry, "elements": ksf})
        if any(TYPE_DISCIPLINE.get(e.etype) == "architectural" for e in elements):
            arch.append({**entry, "elements": [e for e in elements if TYPE_DISCIPLINE.get(e.etype) == "architectural"]})
        if any(TYPE_DISCIPLINE.get(e.etype) == "electrical" for e in elements):
            elec.append({**entry, "elements": [e for e in elements if TYPE_DISCIPLINE.get(e.etype) == "electrical"]})
    items = (structural_items(summary, params) + architectural_items(arch, params, schedule_poz=sched_poz)
             + electrical_items(elec, params))
    if std:
        items += standard_items(std, params, catalog)
    items += facade_items(project, session, catalog, items, drawings, params)
    items += roof_items(project, session, catalog, items, drawings, params)
    items += derived_items(project, session, catalog, items, drawings, params)[0]
    if expand:
        systems = project_systems(project, session, catalog=catalog, items=items, drawings=drawings)
        if systems["systems"]:
            items = expand_systems(items, systems["systems"], catalog)
        off = {x.strip() for x in str(params.get("derived_off") or "").split(",") if x.strip()}
        items = expand_recipes(items, catalog, storey_height=sh["effective"], off="recete" in off)
    return sort_items(items)


ROOF_KINDS = {"kenet_cati", "kiremit_cati", "teras_cati", "cati_kiremit", "cati_membran", "cati_sandvic_panel"}
ROOF_SYSTEM_EVIDENCE = ("KENET_CATI", "KIREMIT_CATI", "TERAS_CATI")


def roof_area(project: Project, session: Session, items: list[BoqItem] | None = None,
              drawings: list[Drawing] | None = None, params: dict | None = None) -> dict:
    """Çatı alanı ve sistemi. Alan: (1) çizimde ölçülen çatı kalemi, (2) roof_area_m2 parametresi, (3) tahmin: en üst
    (bodrum olmayan) kat planı oturumu. Sistem: roof_system parametresi, yoksa kesit / detay notlarındaki kanıt."""
    params = params or project_params(project)
    if drawings is None:
        drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    if items is None:
        items = project_boq(project, session, expand=False)
    measured = sum(it.quantity for it in items if it.kind in ROOF_KINDS and it.unit == "m²" and not it.detail.get("info")
                   and not it.detail.get("roof_auto"))
    out = {"area": 0.0, "source": "none", "detail": "", "system": "", "system_source": "", "candidates": []}
    if measured > 0:
        out.update(area=round(measured, 2), source="measured", detail="çizimde ölçülen çatı kalemi")
    elif params.get("roof_area_m2"):
        out.update(area=float(params["roof_area_m2"]), source="manual", detail="proje parametresi (elle girildi)")
    else:
        fps = [fp for fp in _plan_footprints(project, session, drawings) if not fp["basement"]]
        if fps:
            top = max(fps, key=lambda f: f["area"])
            out.update(area=round(top["area"], 2), source="estimated",
                       detail=f"en büyük kat planı oturumu ({top['drawing']}; tahmin, elle düzeltilebilir)")
    evidence = merge_materials([d.materials or {} for d in drawings])
    cands = [c for c in ROOF_SYSTEM_EVIDENCE if c in evidence]
    out["candidates"] = cands
    code = str(params.get("roof_system") or "").strip().upper()
    if code:
        out.update(system=code, system_source="manual")
    elif len(cands) == 1:
        out.update(system=cands[0], system_source="evidence")
    return out


def roof_items(project: Project, session: Session, catalog: Catalog, items: list[BoqItem],
               drawings: list[Drawing], params: dict) -> list[BoqItem]:
    """Çatı sistemi biliniyor ama çizimde ölçülmemişse: çatı alanı bilgi satırı + sistem kalemi (roof_auto)."""
    ra = roof_area(project, session, items, drawings, params)
    if ra["area"] <= 0 or ra["source"] == "measured" or not ra["system"]:
        return []
    sys_item = catalog.get(ra["system"])
    if not sys_item or any(i.kind == sys_item.code.lower() for i in items):
        return []
    src = {"manual": "proje parametresi", "evidence": "kesit / detay notlarından tanındı"}[ra["system_source"]]
    return [BoqItem(key="cati_alani:*", kind="cati_alani", group="*", label="Çatı alanı", unit="m²", quantity=ra["area"],
                    discipline="ksf:CAT", kind_label="Çatı alanı", discipline_label=catalog.discipline_name("CAT"),
                    notes=[f"Kaynak: {ra['detail']}", "Bilgi satırı; fiyatlanmaz"], detail={"info": True, "source": ra["source"]}),
            BoqItem(key=f"{sys_item.code.lower()}:*", kind=sys_item.code.lower(), group="*", label=sys_item.name, unit=sys_item.unit,
                    quantity=ra["area"], discipline=f"ksf:{sys_item.discipline}", kind_label=sys_item.name,
                    discipline_label=catalog.discipline_name(sys_item.discipline),
                    notes=[f"Miktar = çatı alanı ({ra['detail']}); sistem: {src}"], detail={"roof_auto": True})]


DERIVED_RULES = ("astar", "tavan", "sap", "kaplama", "temel_yalitim", "grobeton", "koruma_sapi")
DEFAULT_FINISH_KEYWORDS = "LOBİ,LOBI,VİTRİN,VITRIN,GİRİŞ,GIRIS,HOL,KORİDOR,KORIDOR,FUAYE"


def finish_area(project: Project, drawings: list[Drawing], params: dict | None = None) -> dict:
    """Şap / döşeme kaplaması alanı: (1) finish_area_m2 parametresi, (2) planlardaki mahal alanı yazılarından seçili
    mahal türleri (finish_rooms anahtar kelimeleri; kiracı mağazaları gibi diğerleri dışarıda kalır)."""
    from .planset import normalize_title
    params = params or project_params(project)
    kws = [k.strip() for k in str(params.get("finish_rooms") or DEFAULT_FINISH_KEYWORDS).split(",") if k.strip()]
    kws_n = [normalize_title(k) for k in kws]
    out = {"area": 0.0, "source": "none", "detail": "", "keywords": kws, "rooms": [], "excluded": [], "excluded_area": 0.0}
    if params.get("finish_area_m2"):
        out.update(area=float(params["finish_area_m2"]), source="manual", detail="şap / kaplama alanı (elle girildi)")
        return out
    total = 0.0
    for d in drawings:
        mult = max(1, d.storey_count or 1)
        for r in (d.rooms or []):
            name_n = normalize_title(r.get("name") or "")
            hit = any(k and k in name_n for k in kws_n)
            row = {"drawing": d.label or d.filename, "name": r.get("name"), "area_m2": r.get("area_m2", 0.0), "included": hit}
            out["rooms"].append(row)
            if hit:
                total += float(r.get("area_m2") or 0.0) * mult
            else:
                out["excluded"].append(f"{r.get('name')} {r.get('area_m2', 0):,.0f} m²")
                out["excluded_area"] += float(r.get("area_m2") or 0.0) * mult
    if total > 0:
        n = sum(1 for r in out["rooms"] if r["included"])
        out.update(area=round(total, 2), source="rooms", detail=f"seçili mahaller ({n} mahal: {', '.join(kws[:4])}…) toplamı")
    return out


def derived_items(project: Project, session: Session, catalog: Catalog, items: list[BoqItem],
                  drawings: list[Drawing], params: dict) -> tuple[list[BoqItem], list[dict]]:
    """Keşifte gözden kaçmasın diye türetilen kalemler ve tamlık kontrol listesi.

    Türetilen (fiyatlanır, detail.derived): boya varsa astar; kat planı oturumundan tavan sıva+boya, şap, döşeme kaplaması;
    temel varsa temel su yalıtımı, grobeton, koruma şapı. derived_off parametresiyle kural kapatılır.
    Kontrol listesi (miktar türetilemeyen ama olması gereken işler): çatı / cephe sistemi seçimi, söve-denizlik, cam,
    korkuluk, ıslak hacim, drenaj…"""
    off = {x.strip().lower() for x in str(params.get("derived_off") or "").split(",") if x.strip()}
    kinds = {it.kind for it in items}
    qty = lambda k: sum(it.quantity for it in items if it.kind == k)   # noqa: E731
    out: list[BoqItem] = []
    check: list[dict] = []

    def add(code: str, spec: str, q: float, note: str, rule: str):
        it = catalog.get(code)
        if not it or q <= 0 or rule in off:
            return
        group = slug(spec) if spec else "*"
        out.append(BoqItem(key=f"{it.code.lower()}:{group}", kind=it.code.lower(), group=group,
                           label=it.name + (f" {spec}" if spec else ""), unit=it.unit, quantity=round(q, 3),
                           discipline=f"ksf:{it.discipline}", kind_label=it.name, discipline_label=catalog.discipline_name(it.discipline),
                           notes=[f"Türetildi: {note}"], detail={"derived": True, "rule": rule}))

    def ask(code: str, text: str, level: str = "required"):
        check.append({"code": code, "text": text, "level": level})

    # 1) boya -> astar
    boya = qty("boya")
    if boya > 0 and "astar" not in kinds:
        add("ASTAR", "", boya, "boya alanı kadar astar (duvar)", "astar")
    # 2) kat planı oturumu -> tavan; şap ve döşeme kaplaması yalnız seçili mahallerde (lobi, vitrin…)
    fps = _plan_footprints(project, session, drawings)
    floor = sum(fp["area"] * max(1, fp["storey_count"]) for fp in fps)
    if floor > 0 and "tavan_siva_boya" not in kinds:
        src = ", ".join(f"{fp['drawing']} {fp['area']:,.0f} m²" for fp in fps[:4]) + ("…" if len(fps) > 4 else "")
        add("TAVAN_SIVA_BOYA", "", floor, f"kat oturumu × kat sayısı ({src}); asma tavanlı mahalleri düşün", "tavan")
    fin = finish_area(project, drawings, params)
    if fin["area"] > 0:
        if "sap" not in kinds:
            t = float(params.get("screed_cm") or 5.0)
            add("SAP", f"{t:g}", fin["area"] * t / 100.0, f"{fin['detail']} × {t:g} cm", "sap")
        if "doseme_kaplama" not in kinds and not any(k in kinds for k in ("seramik_zemin", "laminat", "epoksi")):
            add("DOSEME_KAPLAMA", "", fin["area"], f"{fin['detail']}; tip seçin (seramik / parke / epoksi)", "kaplama")
    if fin["source"] == "none":
        ask("kaplama_alani", "Şap / döşeme kaplaması için alan yok: planda mahal alanı yazısı (LOBİ 45 m²) bulunamadı ya da seçili mahal "
                            "türleri (" + ", ".join(fin["keywords"]) + ") geçmiyor. Proje parametrelerinden mahal türlerini ya da alanı elle girin.")
    elif fin["excluded"]:
        ask("kaplama_disi", f"Şap / kaplama dışı bırakılan mahaller ({fin['excluded_area']:,.0f} m²): " + ", ".join(fin["excluded"][:8])
                            + ("…" if len(fin["excluded"]) > 8 else "") + " — kiracı işi değilse mahal türlerine ekleyin.", "optional")
    # 3) temel -> su yalıtımı, grobeton, koruma şapı
    found_area = 0.0
    for d in drawings:
        if d.discipline == DEFAULT_DISCIPLINE:
            found_area += sum((e.area or 0.0) for e in _included_elements(d, session) if e.etype == "foundation")
    if found_area > 0:
        if "temel_su_yalitimi" not in kinds and "su_yalitim_membran" not in kinds:
            add("TEMEL_SU_YALITIMI", "", found_area, f"temel alanı {found_area:,.0f} m² (radye / sürekli temel)", "temel_yalitim")
        if "grobeton" not in kinds:
            t = float(params.get("lean_concrete_cm") or 10.0)
            add("GROBETON", f"{t:g}", found_area * t / 100.0, f"temel alanı × {t:g} cm", "grobeton")
        if "koruma_sapi" not in kinds:
            add("KORUMA_SAPI", "5", found_area, "temel yalıtımı üstü koruma şapı 5 cm", "koruma_sapi")
        depth = float(params.get("excavation_depth_m") or 0.0)
        if depth > 0 and "kazi" not in kinds:
            margin = float(params.get("excavation_margin") or 1.0)
            exc = found_area * depth * margin
            add("KAZI", f"{depth*100:.0f}", exc, f"temel alanı {found_area:,.0f} m² × derinlik {depth:g} m × şev / çalışma payı {margin:g}", "kazi")
            found_conc = sum(it.quantity for it in items if it.kind == "beton" and it.group == "foundation")
            lean = float(params.get("lean_concrete_cm") or 0.0) / 100.0 * found_area
            back = exc - found_conc - lean
            if back > 0:
                add("GERI_DOLGU", "", back, f"kazı {exc:,.0f} m³ − temel betonu {found_conc:,.0f} m³ − grobeton {lean:,.0f} m³", "geri_dolgu")
        if "drenaj" not in kinds:
            ask("drenaj", f"Temel var ({found_area:,.0f} m²): perimetre drenajı (drenaj borusu + levha) gerekiyorsa ekleyin.", "optional")
    # 4) çatı
    ra = roof_area(project, session, items, drawings, params)
    if ra["area"] > 0 and not ra["system"] and not any(k in kinds for k in ROOF_KINDS):
        hint = " Kesitte " + " / ".join(ra["candidates"]) + " notu var." if ra["candidates"] else ""
        ask("cati_sistemi", f"Çatı alanı {ra['area']:,.0f} m² ({ra['detail']}) ama çatı sistemi seçilmedi.{hint} Betonarme teras ise: eğim betonu, "
                            "buhar kesici, ısı yalıtımı (XPS), su yalıtımı, koruma betonu; kenet / kiremit çatı ise ilgili sistemi seçin.")
    elif ra["area"] > 0 and len(ra["candidates"]) > 1 and ra["system_source"] != "manual":
        ask("cati_sistemi", f"Kesit notlarında birden çok çatı sistemi geçiyor ({', '.join(ra['candidates'])}); proje parametrelerinden seçin.")
    # 5) cephe
    fa = facade_area(project, session, items, drawings, params)
    facade_kinds = {"mantolama_sistem", "kompozit_panel", "giydirme_cephe", "cephe_tasi", "cephe_boya", "prekast_panel", "cephe_brut", "mantolama"}
    if fa["gross"] > 0 and not str(params.get("facade_system") or "").strip() and not (kinds & facade_kinds):
        ask("cephe_sistemi", f"Cephe brüt alanı {fa['gross']:,.0f} m² ({fa['detail']}) ama cephe sistemi seçilmedi (mantolama + boya / kompozit / "
                             "prekast / cephe taşı). Cephe boyası ve astarı da bu seçimden gelir.")
    openings = qty("pencere") + qty("dograma")
    evidence = merge_materials([d.materials or {} for d in drawings])
    layer_names = {l.get("name", "").upper() for d in drawings for l in (d.layers or [])}
    has_sove = "sove" in kinds or "SOVE" in evidence or any("SÖVE" in n or "SOVE" in n for n in layer_names)
    if openings > 0 and not has_sove:
        ask("sove_denizlik", f"{openings:,.0f} adet pencere / doğrama var: söve, denizlik ve kat silmesi çizimde yok. Cephede varsa "
                             "(görünüşte katman eşleyerek ya da elle) ekleyin.", "optional")
    if (qty("pencere") > 0 or qty("dograma") > 0) and "cam" not in kinds:
        ask("cam", "Pencere / doğrama adedi var ama cam m² yok (ölçü etiketi ya da poz listesinde boyut yok); doğrama fiyatı camı kapsamıyorsa ekleyin.", "optional")
    # 6) çok katlı -> korkuluk / merdiven
    storeys = sum(max(1, d.storey_count) for d in drawings if d.discipline in (DEFAULT_DISCIPLINE, "architectural")
                  and any(e.etype in ("column", "wall") for e in _included_elements(d, session)))
    if storeys >= 2 and "korekuyu" not in kinds:
        ask("korkuluk", "Çok katlı bina: merdiven korkuluğu / küpeşte ve balkon-teras korkuluğu keşifte yok; ekleyin.", "optional")
    # 7) ıslak hacim
    wet = any(any(k in n for k in ("VITRIFIYE", "WC", "BANYO", "ISLAK")) for n in layer_names)
    if wet and "seramik_duvar" not in kinds:
        ask("islak_hacim", "Planda ıslak hacim (vitrifiye / WC) var: duvar seramiği, ıslak hacim su yalıtımı ve vitrifiye adetleri keşifte yok.", "optional")
    return out, check


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
             if e.etype in ("slab", "beam", "column", "shear_wall", "wall") and len(e.points or []) >= 3]
    polys = [g for g in polys if not g.is_empty and g.is_valid and g.area > 1e-4]
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
    big = max(parts, key=lambda g: g.area)    # bina oturumu: en büyük parça (uzak aykırı nesneler elenir)
    return float(big.area), float(big.exterior.length)


def _plan_footprints(project: Project, session: Session, drawings: list[Drawing]) -> list[dict]:
    """Kat planlarının (statik kalıp ya da mimari) bina oturumu: aynı kat için statik varsa mimari sayılmaz.
    Bodrum / temel paftaları cephe için atlanır (yer altı)."""
    out = []
    labels_struct = set()
    for d in drawings:
        if d.discipline == DEFAULT_DISCIPLINE:
            els = _included_elements(d, session)
            if not any(e.etype in ("column", "shear_wall") for e in els):
                continue
            fp = building_footprint(els)
            if fp and fp[0] >= 10:
                labels_struct.add(kot_from_label(d.label))
                out.append({"drawing": d.label or d.filename, "drawing_id": d.id, "area": round(fp[0], 2), "perimeter": round(fp[1], 2),
                            "storey_height": storey_height_of(project, d), "storey_count": d.storey_count,
                            "basement": "BODRUM" in (d.label or "").upper(), "source": "structural"})
    for d in drawings:
        if d.discipline == "architectural":
            els = _included_elements(d, session)
            if not any(e.etype == "wall" for e in els):
                continue
            if kot_from_label(d.label) and kot_from_label(d.label) in labels_struct:
                continue
            fp = building_footprint(els)
            if fp and fp[0] >= 10:
                out.append({"drawing": d.label or d.filename, "drawing_id": d.id, "area": round(fp[0], 2), "perimeter": round(fp[1], 2),
                            "storey_height": storey_height_of(project, d), "storey_count": d.storey_count,
                            "basement": "BODRUM" in (d.label or "").upper(), "source": "architectural"})
    return out


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
        for fp in _plan_footprints(project, session, drawings):
            if fp["basement"]:
                continue   # yer altı: cephe yok
            a = fp["perimeter"] * fp["storey_height"] * max(1, fp["storey_count"])
            total += a
            out["per_drawing"].append({**fp, "area": round(a, 2)})
        if total > 0:
            out.update(gross=total, source="estimated",
                       detail="kat planı dış hattı (kolon / perde / duvar) çevresi × kat yüksekliği × kat sayısı (tahmin; elle düzeltilebilir)")
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
    params = project_params(project)
    base = [it for it in items if not it.detail.get("derived")]   # türetilmişler listede olsa da kurallar yeniden hesaplanır
    derived, checklist = derived_items(project, session, catalog, base, drawings, params)
    return {"systems": out, "warnings": warnings,
            "missing": sum(len(sy["missing"]) for sy in out),
            "evidence_codes": sorted(evidence),
            "facade": facade_area(project, session, items, drawings, params),
            "roof": roof_area(project, session, items, drawings, params),
            "finish": finish_area(project, drawings, params),
            "derived": [{"key": it.key, "label": it.label, "quantity": it.quantity, "unit": it.unit, "rule": it.detail.get("rule"),
                         "note": it.notes[0] if it.notes else ""} for it in derived],
            "derived_off": sorted({x.strip() for x in str(params.get("derived_off") or "").split(",") if x.strip()}),
            "checklist": checklist}


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
