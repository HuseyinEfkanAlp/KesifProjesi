"""Router'ların paylaştığı iş mantığı: analiz + kaydetme, proje metrajı / keşfi, fiyat tohumlama, maliyet."""
from __future__ import annotations

import copy
import re
from datetime import datetime

from sqlmodel import Session, select

from .confidence import TAHMIN, TURETILDI
from .scope import GENEL, MAHAL
from .cost.materials import MaterialData, material_lines
from .cost.pricebook import lookup as book_lookup
from .cost.pricing import PriceItem as PriceData, compute_cost, default_price_items
from .models import Drawing, Element, MaterialPrice, PriceBookItem, PriceItem, Project
from .parser.analyzer import analyze_file
from .parser.detectors.base import DetectParams
from .db import DATA_DIR
from .parser.layer_profile import (DEFAULT_DISCIPLINE, MAPPED_DISCIPLINE, REBAR_DISCIPLINE, STANDARD_DISCIPLINE, STRUCTURAL_TYPES,
                                   TYPE_DISCIPLINE, LayerProfile)
from .parser.rebar_tables import REBAR_TARGET_BY_PLAN, TARGET_WORDS, kot_from_label, rebar_target_for
from .parser.materials import merge_materials
from .parser.blocks import covered_by as block_parts
from .parser.rebar_mix import layer_verdict as rebar_layer_verdict
from .parser.rebar_mix import scan_texts as scan_rebar_texts
from .quantity.boq import (KIND_ORDER, BoqItem, architectural_items, boq_summary, effective_params, electrical_items,
                           expand_systems, merge_duplicates, slug, sort_items, standard_items, structural_items)
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
                          extra_disciplines=tuple(drawing.disciplines or []),
                          rebar_target=rebar_target_for(drawing.plan_type, drawing.label or "", drawing.filename or ""))
    if pt is not None and not pt.analyze:
        result.warnings.insert(0, f"{pt.label}: metraja girmez; katman adından otomatik eşleme kapalı (kesitteki duvar / sıva taraması plan miktarı değildir). "
                                  "Kesit notları çatı / cephe sistemi kanıtı ve kotlar için okunur.")

    if result.ksf_height and not drawing.storey_height:
        drawing.storey_height = result.ksf_height      # KSF katman adındaki kat yüksekliği (KOLON-40x40x300 -> 3,00 m)
        result.warnings.append(f"Kat yüksekliği KSF katman adından alındı: {result.ksf_height:g} m")
    fill_wall_areas(result.elements, project, drawing, session, load_catalog())

    # Elle düzenlenen (manual) elemanlar korunur; dedektör aynı nesneyi (handle) yeniden bulursa ikinci kez eklenmez.
    # Metraj dışı bırakılan (included=False) otomatik elemanların işareti yeni bulunan aynı nesneye taşınır.
    old_all = list(session.exec(select(Element).where(Element.drawing_id == drawing.id)))

    def _centroid(pts) -> tuple[float, float]:
        if not pts:
            return (0.0, 0.0)
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    def _key(etype: str, layer: str, handle: str, pts) -> str:
        """Eşleme anahtarı: DXF handle; yoksa (çizgilerden kapatılmış dikdörtgen gibi) tip + katman + konum."""
        if handle:
            return handle
        cx, cy = _centroid(pts or [])
        return f"geo:{etype}:{layer}:{cx:.1f}:{cy:.1f}"

    kept_manual = [e for e in old_all if e.manual]
    excluded_handles: dict[str, list[Element]] = {}
    for e in old_all:
        if e.manual:
            continue
        if not e.included:
            excluded_handles.setdefault(_key(e.etype, e.layer or "", e.handle or "", e.points), []).append(e)
        session.delete(e)
    manual_by_handle: dict[str, list[Element]] = {}
    for e in kept_manual:
        if e.source != "MANUAL":
            manual_by_handle.setdefault(_key(e.etype, e.layer or "", e.handle or "", e.points), []).append(e)

    def _claim(pool: dict[str, list[Element]], det) -> Element | None:
        """Aynı handle'lı eski elemanlardan konumca en yakını alır (bir kiriş çifti birden çok kirişe bölünmüş olabilir)."""
        cands = pool.get(_key(det.etype, det.layer or "", det.handle or "", det.points))
        if not cands:
            return None
        cx, cy = _centroid(det.points)
        best = min(cands, key=lambda e: (_centroid(e.points or [])[0] - cx) ** 2 + (_centroid(e.points or [])[1] - cy) ** 2)
        bx, by = _centroid(best.points or [])
        xs = [p[0] for p in det.points] or [cx]
        ys = [p[1] for p in det.points] or [cy]
        tol = max(0.5, max(xs) - min(xs), max(ys) - min(ys))   # blok kopyaları aynı handle'ı taşır: konum da tutmalı
        if ((bx - cx) ** 2 + (by - cy) ** 2) ** 0.5 > tol:
            return None
        cands.remove(best)
        return best

    for det in result.elements:
        kept = _claim(manual_by_handle, det)
        if kept is not None:
            kept.points = [[round(x, 4), round(y, 4)] for x, y in det.points]   # geometri güncel kalsın, ölçüler kullanıcının
            session.add(kept)
            continue
        excl = _claim(excluded_handles, det)
        session.add(Element(
            drawing_id=drawing.id, etype=det.etype, subtype=det.subtype, name=det.name, layer=det.layer,
            b=det.b, h=det.h, thickness=det.thickness, area=det.area, length=det.length,
            perimeter=det.perimeter, count=det.count, confidence=det.confidence, warnings=det.warnings,
            label_raw=det.label_raw, source=det.source, handle=det.handle,
            points=[[round(x, 4), round(y, 4)] for x, y in det.points],
            included=(det.confidence >= MIN_INCLUDED_CONFIDENCE) and excl is None, meta=det.meta or {},
        ))
    first_analysis = drawing.analyzed_at is None
    drawing.unit = result.unit
    drawing.unit_detected = result.unit_detected
    drawing.layers = [l.to_dict() for l in result.layers]
    drawing.warnings = result.warnings
    drawing.materials = result.materials or {}
    drawing.rebar_mix = {str(k): float(v) for k, v in (result.rebar_mix or {}).items()}
    drawing.rebar_layers = {str(k): float(v) for k, v in (result.rebar_layers or {}).items()}
    drawing.blocks_seen = {str(k): int(v) for k, v in (result.blocks_seen or {}).items()}
    if not drawing.block and first_analysis and result.own_block:
        drawing.block = result.own_block   # pafta başlığındaki "A4-A5 BLOK"; kullanıcı sonradan değiştirirse korunur
    drawing.rooms = result.rooms or []
    drawing.poz = result.poz or {}
    drawing.unit_verdict = result.unit_verdict
    drawing.discipline_hints = result.discipline_hints or {}
    drawing.spaces = result.spaces or []
    drawing.levels = [float(v) for v in (result.levels or [])]
    drawing.kot = result.kot
    drawing.analyzed_at = datetime.utcnow()
    session.add(drawing)
    session.commit()
    session.refresh(drawing)
    return drawing


DEFAULT_STOREY_HEIGHT = 3.0


# Çizimden okunan kat yükseklikleri bu kadar ayrışıyorsa bina değişken katlıdır ve tek bir H uygulanamaz.
VARIABLE_HEIGHT_SPREAD = 0.30


def storey_heights(project: Project, drawings: list[Drawing]) -> dict:
    """Her çizim için kat yüksekliği ve kaynağı; proje için etkin kat yüksekliği.

    Sıra: çizime elle girilen > projeye açıkça girilen H > çizimin kotu ile bir üst kat seviyesi arasındaki fark
    > plan adına göre kat sırası (bodrum, zemin, birinci…) ile seviye dizisi > kat
    seviyelerinin medyan farkı > 3,0 m varsayılan.

    **Tek istisna (kanıt sıralaması):** projeye girilen tek bir H, çizimden okunan kotlar kat kat
    değişiyorsa (yayılım > 0,30 m) hiçbir katta doğru olamaz — tek sayı değişken bir binayı anlatamaz.
    O durumda proje H'si uygulanmaz, her pafta kendi kotundan hesaplanır. Bu bir tahmin değildir: zayıf
    kanıt (elle girilen ya da form varsayılanı tek sayı) yerine güçlü kanıt (çizimin kendi kotları)
    kullanılır. Paftaya **elle girilmiş** yükseklik her zaman üstündür; kullanıcının pafta bazındaki
    kararı değişmez."""
    from .parser.levels import floor_levels, floor_rank, level_for_rank
    all_levels = [float(v) for d in drawings for v in (d.levels or [])]
    for d in drawings:
        if d.kot is not None:
            all_levels.append(float(d.kot))
    floors = floor_levels(all_levels)
    diffs = [round(b - a, 2) for a, b in zip(floors, floors[1:])]
    med = round(sorted(diffs)[len(diffs) // 2], 2) if diffs else None
    def above(level: float) -> float | None:
        ups = [f for f in floors if f > level + 0.5]
        return ups[0] if ups else None

    # Çizimin kendi kanıtı: her paftanın kotundan çıkan yükseklik. Proje H'sinden bağımsız hesaplanır,
    # çünkü kararı veren şey bu dizinin kendi içinde değişip değişmediğidir.
    kot_h = [round(above(float(d.kot)) - float(d.kot), 2) for d in drawings
             if d.kot is not None and above(float(d.kot)) is not None]
    degisken = bool(kot_h) and (max(kot_h) - min(kot_h)) > VARIABLE_HEIGHT_SPREAD
    proje_h = float(project.storey_height or 0)
    # Tek bir H, kat kat değişen bir binada hiçbir katta doğru olamaz: çizimin kotları esas alınır.
    proje_h_gecerli = proje_h > 0 and not degisken

    if proje_h_gecerli:
        effective, source = proje_h, "parametre"
    elif med:
        effective, source = med, ("kotlardan (medyan kat farkı; projeye girilen "
                                  f"{proje_h:g} m çizimdeki değişken kotlarla çelişiyor)" if proje_h > 0
                                  else "kotlardan (medyan kat farkı)")
    else:
        effective, source = DEFAULT_STOREY_HEIGHT, "varsayılan"

    per: dict[int, dict] = {}
    ranked = []
    for d in drawings:
        if d.storey_height and d.storey_height > 0:
            per[d.id] = {"height": float(d.storey_height), "source": "çizime girildi", "kot": d.kot}
            continue
        # H=0 otomatik modu seçer. Açık kullanıcı yüksekliği, çizimdeki kiriş altı / ara kot gibi sezgisel
        # seviyeler tarafından sessizce değiştirilemez — ama kotlar kat kat değişiyorsa tek bir H zaten
        # uygulanamaz (proje_h_gecerli), o zaman çizimin kanıtı kullanılır.
        if proje_h_gecerli:
            per[d.id] = {"height": proje_h, "source": "projeye girildi", "kot": d.kot}
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
    for r, d in ranked:
        lvl = level_for_rank(floors, r)
        nxt = above(lvl) if lvl is not None else None
        if lvl is not None and nxt is not None:
            per[d.id] = {"height": round(nxt - lvl, 2), "source": f"kat sırası → kot {lvl:+.2f} → {nxt:+.2f}", "kot": lvl}
        else:
            per[d.id] = {"height": effective, "source": source, "kot": lvl}
    return {"levels": floors, "heights": diffs, "effective": effective, "source": source, "per_drawing": per}


def apply_storey_counts(project: Project, session: Session) -> dict:
    """Projenin bütün paftalarının kat sayısını çizimden türetir ve kaydeder.

    Kat sayısı kullanıcıya **sorulmaz** (ürün prensibi); `derive.storey_counts` kanaat zincirini
    yürütür. Sonuç `Drawing.storey_count`'a yazılır: metrajı üreten 10 yer ve `quantity/boq.py`
    bugünkü gibi tek alanı okumaya devam eder, değer artık varsayım değil kanıttır.

    Her yüklemeden sonra **proje geneli** çalışır, tek pafta için değil: kot dizisi kanıtı bütün
    paftalara bakar — yeni bir kat planı yüklenince tip kat planının temsil ettiği kat sayısı azalır."""
    from .derive import storey_counts
    drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    if not drawings:
        return {"per_drawing": {}, "warnings": []}
    sc = storey_counts(project, drawings)
    degisen = False
    for d in drawings:
        v = max(1, int(sc["per_drawing"].get(d.id, {}).get("value") or 1))
        if d.storey_count != v:
            d.storey_count = v
            session.add(d)
            degisen = True
    if degisen:
        session.commit()
    return sc


def storey_height_of(project: Project, d: Drawing, sh: dict | None = None) -> float:
    sh = sh or storey_heights(project, [d])
    return float(sh["per_drawing"].get(d.id, {}).get("height") or sh["effective"])


def wall_height_default(project: Project, drawing: Drawing, session: Session | None = None) -> float:
    """Katman adında yüksekliği olmayan duvarın alanı için yükseklik: proje 'wall_height' parametresi, yoksa
    paftanın kat yüksekliği − döşeme kalınlığı (keşif listesindeki standard_items ile aynı kural)."""
    p = project_params(project)
    if p.get("wall_height"):
        return float(p["wall_height"])
    drawings = list(session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()) if session else []
    if drawing not in drawings:
        drawings.append(drawing)
    h = storey_height_of(project, drawing, storey_heights(project, drawings))
    return max(h - (project.slab_thickness or 0.0), 0.0)


def fill_wall_areas(elements, project: Project, drawing: Drawing, session: Session | None, catalog: Catalog) -> int:
    """Duvar (wall_area ölçü kuralı) elemanlarında alan = uzunluk × yükseklik. Dedektör yüksekliği katman adından
    (DUVAR_YTONG-20x300 -> 3 m) alır; yazılmamışsa burada proje duvar yüksekliğiyle tamamlanır ki Elemanlar
    sayfası ve pafta özeti duvarı adet değil m² göstersin. Döndürür: tamamlanan eleman sayısı."""
    h_default: float | None = None
    n = 0
    for det in elements:
        if det.area or not det.length:
            continue
        measure = (det.meta or {}).get("measure")
        if not measure:
            p = parse_layer(det.layer or "", catalog)
            measure = p.item.measure if p and p.item else None
        if measure != "wall_area":
            continue
        if h_default is None:
            h_default = wall_height_default(project, drawing, session)
        det.area = det.length * h_default
        n += 1
    return n


def refresh_wall_areas(project: Project, session: Session, drawings: list[Drawing] | None = None) -> int:
    """Kat yüksekliği / duvar yüksekliği değişince: katman adında yüksekliği olmayan (h boş) duvar elemanlarının alanı
    yeniden uzunluk × yükseklik. Elle düzenlenen (manual) elemanlara dokunulmaz. Döndürür: güncellenen eleman sayısı."""
    catalog = load_catalog()
    if drawings is None:
        drawings = list(session.exec(select(Drawing).where(Drawing.project_id == project.id)).all())
    n = 0
    for d in drawings:
        h = None
        for e in session.exec(select(Element).where(Element.drawing_id == d.id)):
            if e.manual or e.h or not e.length:
                continue
            measure = (e.meta or {}).get("measure")
            if not measure:
                p = parse_layer(e.layer or "", catalog)
                measure = p.item.measure if p and p.item else None
            if measure != "wall_area":
                continue
            if h is None:
                h = wall_height_default(project, d, session)
            e.area = e.length * h
            session.add(e)
            n += 1
    session.commit()
    return n


def cleanup_uploads(max_age_hours: float = 24.0) -> int:
    """Pafta seçimi için saklanan kaynak dosyalar (src_<token>_*.dxf, .sheets.json) seçilmeden bırakılınca diskte kalır;
    son erişimi max_age_hours'u geçenler açılışta silinir. Döndürür: silinen dosya sayısı."""
    import time
    now = time.time()
    n = 0
    for f in UPLOAD_DIR.glob("src_*"):
        try:
            if now - f.stat().st_mtime > max_age_hours * 3600:
                f.unlink()
                n += 1
        except OSError:
            continue
    return n


def _drawing_kot(d) -> str | None:
    """Paftanın kotu: önce başlığından ("+7.95 KOTU KALIP PLANI"), yoksa çizimden okunan kot.

    Bazı paftaların adında kot yazmaz ("KALIP PLANI", "TEMEL KALIP PLANI") ama kot çizimin içinden okunmuştur
    (drawing.kot). Kot olmadan o katın betonu hiçbir donatı paftasıyla eşleşemez ve demiri hem tablodan hem
    oranla sayılır (A4-A5 kolonlarında 120 t fazla)."""
    return kot_from_label(d.label) or (f"{float(d.kot):+.2f}" if d.kot is not None else None)


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


def dominant_slab_thickness(elements) -> float | None:
    """Kattaki döşemelerin alanla ağırlıklı baskın kalınlığı: kolon / perde beton yüksekliği ve kiriş gövdesi bu d ile düşülür
    (proje parametresi yalnız döşemesi olmayan paftada kullanılır)."""
    pairs = [(float(e.thickness), float(e.area or 0.0)) for e in elements if e.etype == "slab" and e.thickness]
    if not pairs:
        return None
    pairs.sort()
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    acc = 0.0
    for t, w in pairs:
        acc += w
        if acc >= total / 2:
            return t
    return pairs[-1][0]


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


def _floor_label(rank: float) -> str:
    """Kat sırasının okunur adı: -100 temel, -2 2. bodrum, 0 zemin, 0,5 asma kat, 99 çatı, 3 -> 3. kat."""
    if rank <= -100:
        return "temel"
    if rank < 0:
        return f"{abs(int(rank))}. bodrum"
    if rank == 0:
        return "zemin kat"
    if rank == 0.5:
        return "asma kat"
    if rank >= 99:
        return "çatı"
    return f"{rank:g}. kat"


def _floor_identity(drawings: list[Drawing]) -> dict[int, tuple[str | None, str]]:
    """Pafta -> (kat anahtarı, görünen ad). Aynı katı gösteren paftalar aynı anahtarı taşır.

    Kat kimliği **kullanıcıdan istenmez, çizimden okunur** — iki bağımsız kanıt vardır ve ikisi de tek başına
    yeterlidir: kot ("+7.95 KOTU KALIP PLANI", ya da çizimden okunan kot) ve plan adındaki kat sırası
    ("2. KAT AYDINLATMA PLANI", "BODRUM KALIP"). Elektrik / mekanik paftalarında kot çoğu zaman yazmaz; kat
    adı yazar. İkisini birden taşıyan bir pafta ("2. KAT (+7.95) KALIP PLANI") iki kimliği birbirine bağlar,
    böylece kotla adlandırılmış statik pafta ile adla adlandırılmış elektrik paftası aynı kata düşer.
    Hiçbir kanıt yoksa anahtar None'dur: o paftada hiçbir miktar düşürülmez."""
    from .parser.levels import floor_rank
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    nodes: dict[int, list[tuple[str, str]]] = {}
    kots: dict[tuple[str, str], str] = {}
    for d in drawings:
        ns: list[tuple[str, str]] = []
        kot = _drawing_kot(d)
        if kot:
            ns.append(("kot", kot))
            kots[("kot", kot)] = kot
        r = floor_rank(d.label or d.filename or "")
        if r is not None:
            ns.append(("kat", f"{r:g}"))
        for n in ns:
            find(n)
        if len(ns) == 2:
            union(ns[0], ns[1])     # aynı pafta hem kotu hem kat adını taşıyor: ikisi aynı kattır
        nodes[d.id] = ns

    # her kimlik kümesi için görünen ad: varsa kot, yoksa kat adı
    label_of: dict[tuple[str, str], str] = {}
    for n in list(parent):
        root = find(n)
        if n[0] == "kot":
            label_of.setdefault(root, kots[n])
    out: dict[int, tuple[str | None, str]] = {}
    for d in drawings:
        ns = nodes.get(d.id) or []
        if not ns:
            out[d.id] = (None, "")
            continue
        root = find(ns[0])
        ad = label_of.get(root) or next((_floor_label(float(n[1])) for n in ns if n[0] == "kat"), "")
        out[d.id] = (f"{root[0]}:{root[1]}", ad)
    return out


def scope_resolution(project: Project, drawings: list[Drawing], els_by_id: dict[int, list[Element]]):
    """Kapsam sahipliği: aynı kotta aynı nesneyi ikinci kez çizen pafta onu tekrar saymaz (quantity/scope.py).

    Sahiplik yalnız hesaba giren paftalar arasında kurulur; tek pafta metrajında (drawing_boq) o paftanın kendi
    ölçümü görünür, proje toplamında ise ikinci kez çizilen nesne düşer. Proje parametresi `scope_off` kapatır."""
    from .planset import PLAN_TYPE_BY_CODE
    from .quantity.scope import Resolution, ScopeDrawing, ScopeElement, resolve
    if str((project.params or {}).get("scope_off") or "").strip() in ("1", "true", "evet"):
        return Resolution()

    def contributes(d: Drawing) -> bool:
        """Metraja girmeyen pafta sahiplik de kuramaz: donatı paftasının altlığındaki kalıp planı hiçbir zaman
        kalıp planının kendisini düşüremez (kesit / detay paftaları da öyle)."""
        pt = PLAN_TYPE_BY_CODE.get(d.plan_type or "")
        return d.discipline != REBAR_DISCIPLINE and (pt is None or pt.analyze)

    drawings = [d for d in drawings if contributes(d)]
    kat = _floor_identity(drawings)
    sds = [ScopeDrawing(id=d.id, label=d.label or d.filename, block=d.block or "",
                        floor=kat[d.id][0], floor_label=kat[d.id][1],
                        plan_type=d.plan_type or "", discipline=d.discipline or "",
                        elements=[ScopeElement(id=e.id, etype=e.etype, subtype=e.subtype, points=e.points or (),
                                               length=e.length or 0.0, area=e.area or 0.0, count=e.count or 1,
                                               manual=e.manual) for e in els_by_id.get(d.id, [])])
           for d in drawings]
    return resolve(sds)


def measured_elements(project: Project, session: Session, drawings: list[Drawing]):
    """Metraja giren elemanlar (pafta -> eleman listesi) ve kapsam raporu: ikinci kez çizilen nesne listede yoktur."""
    els = {d.id: _included_elements(d, session) for d in drawings}
    res = scope_resolution(project, drawings, els)
    if not res.dropped:
        return els, res
    return {did: [e for e in lst if e.id not in res.dropped] for did, lst in els.items()}, res


def rebar_table_rows(project: Project, session: Session) -> list[dict]:
    """Donatı paftalarından okunan tablo / poz yazısı satırları (çap bazında kg) — özet ve keşif için.

    Tip kat çarpanı: "3 kat temsil ediyor" denen donatı paftasının demiri de 3 ile çarpılır (kalıp planındaki beton gibi);
    temel hedefli satırlar hiçbir zaman çarpılmaz. Elle girilen demir (manual, meta'sız) `weight_kg` alanı b/length'ten değil
    `meta.weight_kg`'den okunur; yoksa `length` (m) × birim ağırlık."""
    from .parser.rebar_tables import unit_weight
    rows: list[dict] = []
    for d in session.exec(select(Drawing).where(Drawing.project_id == project.id, Drawing.discipline == REBAR_DISCIPLINE)).all():
        mult = max(int(d.storey_count or 1), 1)
        for e in _included_elements(d, session):
            if e.etype != "rebar":
                continue
            m = e.meta or {}
            dia = m.get("dia_mm") or (round(e.b * 1000) if e.b else None)
            kg = float(m.get("weight_kg") or 0.0)
            length_m = float(m.get("length_m") or e.length or 0.0)
            if kg <= 0 and dia and length_m > 0:
                kg = length_m * unit_weight(int(dia))
            if kg <= 0 or not dia:
                continue
            target = m.get("target") or rebar_target_for(d.plan_type, d.label or "", d.filename or "")
            k = 1 if target == "foundation" else mult
            rows.append({"drawing": d.label or d.filename, "drawing_id": d.id, "kot": m.get("kot") or _drawing_kot(d),
                         "target": target, "dia_mm": int(dia), "weight_kg": kg * k, "length_m": length_m * k,
                         "source": ("elle" if e.manual else m.get("source", "tablo")), "confidence": e.confidence,
                         "storey_count": k})
    return rows


def project_quantities(project: Project, session: Session, drawings: list[Drawing] | None = None) -> tuple[list[QuantityLine], dict, dict]:
    """Statik metraj: (satırlar, özet, element_info) döndürür. Yalnızca statik eleman tipleri girer;
    donatı paftalarındaki tablolar demiri çap bazında verir ve ilgili eleman tipinin oran tahminini geçersiz kılar.
    drawings: yalnız bu paftalar (tek pafta metrajı); kat yükseklikleri yine projenin tüm paftalarından."""
    from .confidence import element_tier
    all_drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    sh = storey_heights(project, all_drawings)
    if drawings is None:
        drawings = all_drawings
    lines: list[QuantityLine] = []
    info: dict = {}
    els_by_id, _scope = measured_elements(project, session, drawings)
    for d in drawings:
        if d.discipline == REBAR_DISCIPLINE:
            continue
        elements = [e for e in els_by_id.get(d.id, []) if e.etype in STRUCTURAL_TYPES]
        if not elements:
            continue
        net_slabs = any(e.etype == "slab" and e.subtype == "net" for e in elements)
        params = QuantityParams(storey_height=storey_height_of(project, d, sh),
                                slab_thickness=dominant_slab_thickness(elements) or project.slab_thickness,
                                storey_count=d.storey_count, beam_full_height=net_slabs,
                                beam_depth=dominant_beam_depth(elements),
                                rebar_ratios={**QuantityParams().rebar_ratios, **(project.rebar_ratios or {})})
        data = [ElementData.from_obj(e) for e in elements]
        for e in elements:
            info[e.id] = {"tier": element_tier(e), "drawing": d.label or d.filename, "drawing_id": d.id, "kot": _drawing_kot(d), "layer": e.layer,
                          "b": e.b, "h": e.h, "thickness": e.thickness, "area": round(e.area, 4), "length": round(e.length, 4),
                          "warnings": e.warnings, "storey_height": params.storey_height, "slab_thickness": params.slab_thickness}
        lines.extend(compute_all(data, params))
    return lines, summarize(lines, rebar_table_rows(project, session), info), info


# Pafta metrajında yazılmayan kalemler: proje toplamından türeyen fire ve sarf (keşif listesinde kalır)
_NOT_MEASURED_KINDS = {"plywood", "bag_teli", "kalip_yagi", "civi", "kalip_iskelesi"}


def project_rebar_mix(project: Project, session: Session, drawings: list[Drawing]) -> dict[str, dict[int, float]]:
    """Eleman tipi -> çap -> ham pay (parser/rebar_mix.py). "*" bütün paftaların ortak havuzudur.

    İki kaynak birleşir: (1) donatı / kolon / temel paftalarının bütün yazıları — paftanın hedef eleman tipine
    yazılır, (2) elemanların kendi etiketleri ("S1 30/60 8Ø16") — doğrudan o elemanın tipine yazılır."""
    out: dict[str, dict[int, float]] = {}

    def add(etype: str, dia: int, v: float) -> None:
        if v <= 0:
            return
        out.setdefault(etype, {})[dia] = out.setdefault(etype, {}).get(dia, 0.0) + v
        if etype != "*":
            out.setdefault("*", {})[dia] = out.setdefault("*", {}).get(dia, 0.0) + v

    for d in drawings:
        mix = {int(k): float(v) for k, v in (d.rebar_mix or {}).items()}
        if not mix:
            continue
        target = rebar_mix_target(d)
        for dia, v in mix.items():
            add(target, dia, v)
    for d in drawings:
        for e in _included_elements(d, session):
            if not e.label_raw or e.etype not in STRUCTURAL_TYPES:
                continue
            for dia, v in scan_rebar_texts([e.label_raw]).items():
                add(e.etype, dia, v * max(int(e.count or 1), 1))
    return out


def project_rebar_layers(project: Project, drawings: list[Drawing]) -> dict[str, str]:
    """Eleman tipi -> "cift" / "tek" / "" (bilinmiyor): donatı tek sıra mı, alt + üst iki sıra mı.

    Ton başına demir işçiliğini değiştirir (üst hasır sehpa üstünde, havada bağlanır) ve çift katta sehpa
    (poz) demiri gerektirir. Kanıt paftadaki alt / üst donatı yazıları ve katman adlarıdır; paftanın hedef
    eleman tipine yazılır ("*" genel havuz). Proje parametresi `rebar_layers` "auto" değilse o geçerlidir."""
    forced = str((project.params or {}).get("rebar_layers") or "auto").lower()
    if forced in ("cift", "tek"):
        return {"*": forced}
    tags: dict[str, dict[str, float]] = {}
    for d in drawings:
        t = {str(k): float(v) for k, v in (d.rebar_layers or {}).items()}
        if not t:
            continue
        for target in {rebar_mix_target(d), "*"}:
            acc = tags.setdefault(target, {})
            for k, v in t.items():
                acc[k] = acc.get(k, 0.0) + v
    return {et: v for et, t in tags.items() if (v := rebar_layer_verdict(t))}


def project_blocks(project: Project, drawings: list[Drawing]) -> dict:
    """Projenin blokları — kullanıcıdan sorulmaz, çizimden çıkar.

    İki ayrı kanıt: paftanın **kendi bloğu** (dosya adı / pafta başlığındaki "A4-A5 BLOK") keşfin kapsamını
    verir; **vaziyet planındaki** blok adları sitenin tamamını verir. Vaziyet genelde keşiften geniştir
    (site 22 blok, keşif 2 blok), bu yüzden kapsam = planı yüklenmiş bloklar; vaziyette görünüp planı
    olmayanlar yalnız hatırlatılır ("vaziyet planında C3 BLOK da var, planı yüklenmedi").

    Tek bloklu yapıda hiçbir yerde "BLOK" geçmez: liste boş kalır ve program tek yapı gibi çalışır.
    Project.blocks doluysa (kullanıcı düzeltmesi) kapsam odur.

    Döndürür: {"blocks": kapsam, "site": vaziyette görülen, "missing": vaziyette olup planı olmayan,
               "source": "cizim" | "elle"}"""
    own = {(d.block or "").strip() for d in drawings} - {""}
    site: dict[str, int] = {}
    for d in drawings:
        for name, n in (d.blocks_seen or {}).items():
            site[name] = site.get(name, 0) + int(n)
    forced = [b for b in (project.blocks or []) if b]
    blocks = sorted(forced) if forced else sorted(own)
    covered = block_parts(blocks) | block_parts(own)   # "A4-A5" kapsamı A4 ve A5'i de içerir
    return {"blocks": blocks, "site": sorted(site), "missing": sorted(set(site) - covered),
            "source": "elle" if forced else "cizim"}


def rebar_mix_target(d: Drawing) -> str:
    """Paftadaki donatı yazılarının hangi eleman tipine ait olduğu; belirsizse "*" (genel havuz)."""
    t = REBAR_TARGET_BY_PLAN.get(d.plan_type or "")
    if t:
        return t
    text = f"{d.label or ''} {d.filename or ''}"
    for et, pat in TARGET_WORDS:
        if pat.search(text):
            return et
    return "*"


# Kapı pozu da camlı olabilir: fotoselli / vitrin / giyotin kapılar cam yüzeydir. Bu sözcükler geçiyorsa
# kapıya da cam yazılır (yoksa AVM girişindeki bütün cam keşiften düşer).
GLAZED_WORDS = re.compile(r"FOTOSEL|V[İI]TR[İI]N|CAM\b|CAMLI|G[İI]YOT[İI]N|CURTAIN|GLAZ", re.IGNORECASE)


def project_boq(project: Project, session: Session, summary: dict | None = None, expand: bool = True,
                drawings: list[Drawing] | None = None, measured_only: bool = False) -> list[BoqItem]:
    """Tüm disiplinlerin keşif listesi. expand=True: katmanlı sistemler bileşenlerine açılır (project_systems kararıyla).
    drawings: yalnız bu paftalar. measured_only: yalnız çizimden ölçülen kalemler (beton / kalıp / demir, duvar, kapı,
    KSF kalemleri…); fire, sarf, cephe / çatı tahmini, türetilmiş kalemler ve reçeteler yazılmaz (pafta metrajı)."""
    from .derive import slab_thicknesses, storey_counts
    all_drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    if drawings is None:
        drawings = all_drawings
    if summary is None:
        _, summary, _ = project_quantities(project, session, drawings)
    params = project_params(project)
    catalog = load_catalog()
    sh = storey_heights(project, all_drawings)
    els_by_id, _scope = measured_elements(project, session, drawings)
    # doğrama pozları: adet poz listesinden (proje toplamı), ölçü görünüş / doğrama paftasından, kapı-pencere ayrımı nottan
    poz_sizes, poz_kinds, poz_glazed, sched_poz = {}, {}, set(), set()
    for d in drawings:
        poz_sizes.update((d.poz or {}).get("sizes") or {})
        poz_kinds.update((d.poz or {}).get("kinds") or {})
        for e in els_by_id[d.id]:
            if e.etype == "dograma" and e.subtype:
                sched_poz.add(e.subtype)
                note = str((e.meta or {}).get("note") or "").replace("i", "İ").upper()
                ad = str(e.name or "").replace("i", "İ").upper()
                metin = f"{note} {ad}"
                if e.subtype not in poz_kinds and ("KAPI" in metin or "DOOR" in metin):
                    poz_kinds[e.subtype] = "door"
                # Kapı olması camsız olması demek değildir: fotoselli / vitrin / cam kapı neredeyse tamamen camdır.
                if GLAZED_WORDS.search(metin):
                    poz_glazed.add(e.subtype)

    def ksf_entry(e):
        if e.etype != "dograma":
            return e
        size = poz_sizes.get(e.subtype or "")
        kind = poz_kinds.get(e.subtype or "", "window")
        return {"etype": e.etype, "subtype": e.subtype, "name": e.name, "layer": e.layer, "count": e.count,
                "length": e.length, "area": e.area, "thickness": e.thickness, "points": e.points, "id": e.id,
                "b": size[0] if size else None, "h": size[1] if size else None,
                "meta": {**(e.meta or {}), "opening_kind": kind,
                         "glazed": kind == "window" or (e.subtype or "") in poz_glazed}}

    arch, elec, std = [], [], []
    # Döşeme kalınlığı da sorulmaz: kullanıcı açıkça girmediyse her pafta kendi planında ölçülen baskın
    # kalınlığı kullanır. Duvar yüksekliği (kat yüksekliği − d) buna bağlıdır ve tek bir proje sayısı
    # bodrum perdesiyle çatı döşemesini aynı sayar.
    st = slab_thicknesses(project, drawings, lambda x: els_by_id.get(x.id, []))
    # Kat sayısı çıkarılamamış **çok katlı** bir binada paftadan gelen her miktar kat sayısı kadar yanlış
    # olabilir: o paftanın kalemleri güven rozetinde en alt kademeye (tahmin) düşer. Tek katlı projede
    # "1 kat" doğrudur, rozet düşürülmez.
    sc = storey_counts(project, all_drawings)
    riskli = {d.id for d in drawings
              if (sc["per_drawing"].get(d.id, {}).get("kind") == "default" and (sc["total"] or 1) > 1)}
    for d in drawings:
        elements = els_by_id[d.id]
        entry = {"id": d.id, "label": d.label or d.filename, "storey_count": d.storey_count,
                 "storey_height": storey_height_of(project, d, sh),
                 "slab_thickness": st["per_drawing"].get(d.id, {}).get("value") or project.slab_thickness,
                 "height_source": sh["per_drawing"].get(d.id, {}).get("source", sh["source"]),
                 "storey_risk": d.id in riskli,
                 "elements": [ksf_entry(e) for e in elements]}
        if d.discipline in (STANDARD_DISCIPLINE, MAPPED_DISCIPLINE):
            # KSF statik katmanları (KOLON_ON, DOSEME_ON…) statik motorda beton / kalıp / demir olarak ölçüldü; ikinci kez yazılmaz
            std.append({**entry, "elements": [e for e in entry["elements"] if _g_etype(e) not in STRUCTURAL_TYPES]})
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
    mix = project_rebar_mix(project, session, all_drawings)
    layers = project_rebar_layers(project, all_drawings)
    items = (structural_items(summary, params, rebar_mix=mix, rebar_layers=layers) + architectural_items(arch, params, schedule_poz=sched_poz)
             + electrical_items(elec, params))
    if std:
        items += standard_items(std, params, catalog)
    if measured_only:
        return sort_items(merge_duplicates([it for it in items if it.group != "fire" and it.kind not in _NOT_MEASURED_KINDS]))
    items += facade_items(project, session, catalog, items, drawings, params)
    items += roof_items(project, session, catalog, items, drawings, params)
    items += derived_items(project, session, catalog, items, drawings, params)[0]
    if expand:
        systems = project_systems(project, session, catalog=catalog, items=items, drawings=drawings)
        if systems["systems"]:
            items = expand_systems(items, systems["systems"], catalog)
        off = {x.strip() for x in str(params.get("derived_off") or "").split(",") if x.strip()}
        # demir işçiliği çapa / kata göre hesaplanır: reçete parametreleri (hazır demir %, genel kat kararı) geçilir
        rp = dict(params); rp["_rebar_layers_default"] = layers.get("*", "")
        items = expand_recipes(items, catalog, storey_height=sh["effective"], off="recete" in off, params=rp)
    # ayrı üreticiler (sezgisel / KÇS / türetilmiş) aynı anahtarı doğurabilir: kalem başına tek satır
    return sort_items(merge_duplicates(items))


def _g_etype(e) -> str:
    return e["etype"] if isinstance(e, dict) else e.etype


def drawing_boq(project: Project, drawing: Drawing, session: Session) -> list[BoqItem]:
    """Tek paftanın metrajı: o paftadan ölçülen kalemler (duvar malzeme bazında m², kapı adet, KSF kalemleri kendi
    birimiyle, beton / kalıp / demir); kat çarpanı uygulanır, proje genelinden türeyen kalemler yazılmaz."""
    return project_boq(project, session, drawings=[drawing], measured_only=True)


ROOF_KINDS = {"kenet_cati", "kiremit_cati", "teras_cati", "celik_cati", "cati_kiremit", "cati_membran", "cati_sandvic_panel"}
ROOF_SYSTEM_EVIDENCE = ("KENET_CATI", "KIREMIT_CATI", "TERAS_CATI", "CELIK_CATI")


def _cm_from_notes(drawings: list[Drawing], code: str) -> tuple[float, str]:
    """Çizim notlarından bir kalemin kalınlığı (cm) ve kanıt yazısı; yoksa (0, "")."""
    ev = merge_materials([d.materials or {} for d in drawings]).get(code) or {}
    spec = str(ev.get("spec") or "")
    if spec.endswith("MM"):
        spec = spec[:-2]
        try:
            return float(spec.replace(",", ".")) / 10.0, (ev.get("evidence") or [""])[0]
        except ValueError:
            return 0.0, ""
    try:
        return float(spec.replace(",", ".")), (ev.get("evidence") or [""])[0]
    except ValueError:
        return 0.0, ""


def lean_concrete_cm(project: Project, drawings: list[Drawing], params: dict) -> dict:
    """Grobeton kalınlığı (cm): çizim notu > kullanıcı parametresi > program varsayılanı."""
    cm, note = _cm_from_notes(drawings, "GROBETON")
    if cm > 0:
        return {"cm": cm, "source": "drawing", "detail": f"çizim notundan: “{note}”"}
    raw = project.params or {}
    if raw.get("lean_concrete_cm"):
        return {"cm": float(raw["lean_concrete_cm"]), "source": "param", "detail": "proje parametresi (siz girdiniz)"}
    return {"cm": float(params.get("lean_concrete_cm") or 10.0), "source": "default",
            "detail": "program varsayılanı — çizimde grobeton kalınlığı yazmıyor"}


# ---------------------------------------------------------------- mahal bazında keşif
# Eleman → mahal dağıtım kuralı (eleman türüne göre, hepsi çizimin kendi koordinatında):
#   adet   : elemanın noktası hangi mahalin içindeyse tamamı o mahalin (kamera, priz, armatür, doframa)
#   alan   : mahal çokgenleriyle kesişim oranı (döşeme, kaplama, tavan)
#   uzunluk: duvar / tava / boru mahalin *içinde* değil SINIRINDA durur; WALL_REACH kadar tampon içinde kalan
#            mahaller arasında kesişim alanı oranında bölüşülür (iki oda arasındaki duvar yarı yarıya)
WALL_REACH = 0.6          # m — duvar / hat elemanının komşu mahale erişimi
COUNT_TYPES = {"fixture", "dograma", "door", "window"}


def _space_polys(spaces: list[dict]):
    """Mahal çokgenleri. İç içe mahallerde üsttekiİN geometrisinden alttakiler DÜŞÜLÜR: spor salonunun
    içindeki havuz deposu ayrı mahaldir, alanı iki kez sayılmamalı. Üst mahal listede kalır — eskiden
    "yaprak olmayan" mahaller atamadan tamamen dışlanıyor ve 1.200 m²'lik salon hiç kalem almıyordu."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    ham = []
    for sp in spaces:
        pts = sp.get("points") or []
        if len(pts) < 3:
            continue
        try:
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.area > 0:
                ham.append((sp, poly))
        except Exception:
            continue
    out = []
    for sp, g in ham:
        icindekiler = [h for sp2, h in ham if sp2 is not sp and h.area < g.area - 1e-9
                       and g.contains(h.representative_point())]
        if icindekiler:
            try:
                net = g.difference(unary_union(icindekiler))
                if not net.is_empty and net.area > 0.5:
                    g = net
            except Exception:
                pass
        out.append((sp, g))
    return out


def _shares(el, polys, leaf_only: bool = True, offset: tuple[float, float] = (0.0, 0.0)) -> dict[int, float]:
    """Bir elemanın mahallere dağılımı: {mahal index: pay (0-1)}. Boş dönerse mahale atanamadı.
    offset: eleman başka bir paftadansa o paftanın mahal çizimine göre kayması."""
    from shapely.geometry import LineString, Point as SPoint, Polygon
    dx, dy = offset
    pts = [(p[0] + dx, p[1] + dy) for p in (el.points or []) if len(p) >= 2]
    # Tüm mahaller adaydır: "en küçük içeren mahal" kuralı zaten doğru mahali seçer ve çokgenler
    # birbirinden düşülmüş olduğu için alan çift sayılmaz.
    cand = list(polys)
    if not cand or not pts:
        return {}
    etype = el.etype or ""
    area = float(el.area or 0.0)
    length = float(el.length or 0.0)
    if etype in COUNT_TYPES or (area <= 0 and length <= 0) or len(pts) < 2:
        p = SPoint(pts[0]) if len(pts) == 1 else Polygon(pts).centroid if len(pts) >= 3 else LineString(pts).centroid
        hit = min((sp for sp, poly in cand if poly.contains(p)), key=lambda sp: sp["area"], default=None)
        return {hit["index"]: 1.0} if hit else {}
    if area > 0 and len(pts) >= 3:
        try:
            g = Polygon(pts)
            g = g if g.is_valid else g.buffer(0)
        except Exception:
            return {}
        w = {sp["index"]: g.intersection(poly).area for sp, poly in cand}
        tot = sum(w.values())
        if tot > 1e-9:
            return {i: v / tot for i, v in w.items() if v > 1e-9}
        # duvar gövdesi mahallerin dışında kalır: komşuluk kuralına düşer
    geom = Polygon(pts) if (len(pts) >= 3 and area > 0) else LineString(pts)
    try:
        reach = geom.buffer(WALL_REACH)
    except Exception:
        return {}
    w = {sp["index"]: reach.intersection(poly).area for sp, poly in cand}
    tot = sum(w.values())
    return {i: v / tot for i, v in w.items() if v > 1e-9} if tot > 1e-9 else {}


def _scaled(e, share: float) -> dict:
    """Elemanın mahale düşen payı: yalnız ölçüler ölçeklenir, **adet dokunulmaz kalır**.

    Üreticiler miktarı `uzunluk × adet` (ya da `alan × adet`) olarak hesaplıyor; payı ikisine birden
    uygulamak miktarı payın KARESIYLE çarpıyordu ve mahal toplamları keşiften eksik kalıyordu.
    Adet zaten bölünmüyor: adetle ölçülen eleman (armatür, kapı) `_shares` içinde ağırlık merkeziyle
    tek bir mahale yazılır, payı her zaman 1,0'dır."""
    return {"etype": e.etype, "subtype": e.subtype, "name": e.name, "layer": e.layer,
            "count": e.count,
            "length": (e.length or 0.0) * share, "area": (e.area or 0.0) * share,
            "thickness": e.thickness, "points": e.points, "id": e.id, "b": e.b, "h": e.h, "meta": e.meta or {}}


def _room_note_of(drawing: Drawing, sp: dict) -> dict:
    """Mahalin döşeme bitişi notu: mahal yazısından gelen satırla ad ve alandan eşleştirilir
    (ikisi de aynı etiketten okunduğu için ad + alan güvenli anahtardır)."""
    hedef = sp.get("label_area") or sp.get("area") or 0.0
    for r in (drawing.rooms or []):
        if str(r.get("name") or "").upper() != str(sp.get("name") or "").upper():
            continue
        a = float(r.get("area_m2") or 0.0)
        if hedef <= 0 or abs(a - hedef) <= max(0.05, 0.01 * max(a, hedef)):
            return r
    return {}


# Islak hacim duvarı ve etek yüksekliği (services.derived_items ile aynı kabuller)
WET_SKIRT = 0.3


def space_derived(project: Project, sp: dict, catalog: Catalog, params: dict, drawings: list[Drawing]) -> list[BoqItem]:
    """Mahalin kendi ölçülerinden türetilen kalemler: şap, döşeme kaplaması, tavan, sıva + boya.

    Alan ve **çevre mahal sınırından ölçülür**: proje genelindeki "kare mahal varsayımı 4·√alan" burada
    gerekmez. Sınırı doğrulanmamış mahalde (alan yalnız yazıdan) çevre bilinmez; duvar yüzeyi üretilmez
    ve bu açıkça yazılır."""
    out: list[BoqItem] = []
    area = float(sp.get("area") or 0.0)
    if area <= 0 or sp.get("kind") == "grup":
        return out
    cevre = float(sp.get("perimeter") or 0.0)
    olculu = sp.get("area_source") == "drawing" and cevre > 0
    h = float(params.get("wall_height") or 0.0) or max(float(params.get("storey_height") or 3.0) - float(project.slab_thickness or 0.0), 0.0)
    wet = bool(WET_ROOM.search(str(sp.get("name") or "")))

    def add(code: str, spec: str, qty: float, note: str, kaynak: str):
        it = catalog.get(code)
        if not it or qty <= 0:
            return
        group = slug(spec) if spec else "*"
        out.append(BoqItem(key=f"{it.code.lower()}:{group}", kind=it.code.lower(), group=group,
                           label=it.name + (f" {spec}" if spec else ""), unit=it.unit, quantity=round(qty, 3),
                           discipline=f"ksf:{it.discipline}", kind_label=it.name,
                           discipline_label=catalog.discipline_name(it.discipline),
                           notes=[note], detail={"derived": True, "space": True, "source": kaynak,
                                                 "evidence": {TURETILDI if sp.get("area_source") == "drawing" else TAHMIN: round(qty, 3)}}))

    kaynak = "mahal sınırından ölçüldü" if sp.get("area_source") == "drawing" else "mahal yazısındaki alandan"
    note = sp.get("finish") or {}
    if wet:
        add("SERAMIK_ZEMIN", note.get("spec", ""), area, f"ıslak hacim zemini {area:,.1f} m² ({kaynak})", kaynak)
    elif note.get("code"):
        add(note["code"], note.get("spec", ""), area,
            f"{area:,.1f} m² ({kaynak}); tip mahal notundan: “{note.get('text', '')}”", kaynak)
    else:
        add("DOSEME_KAPLAMA", "", area, f"{area:,.1f} m² ({kaynak}); tip mahal notunda yazmıyor", kaynak)
    cm = float(sp.get("screed_cm") or 0.0)
    sap = lean = _cm_from_notes(drawings, "SAP")[0] if not cm else cm
    src = "mahal notundan" if cm else ("çizim notundan" if sap else "VARSAYILAN — çizimde yazmıyor")
    if not sap:
        sap = float(params.get("screed_cm") or 5.0)
    add("SAP", f"{sap:g}", area * sap / 100.0, f"{area:,.1f} m² × {sap:g} cm; kalınlık: {src}", kaynak)
    add("TAVAN_SIVA_BOYA", "", area, f"mahal tavanı {area:,.1f} m² ({kaynak})", kaynak)
    if olculu and h > 0:
        duvar = cevre * h
        if wet:
            add("SERAMIK_DUVAR", "", duvar, f"çevre {cevre:,.1f} m × {h:g} m (çevre mahal sınırından ÖLÇÜLDÜ)", kaynak)
            add("SURME_IZOLASYON", "", area + cevre * WET_SKIRT,
                f"zemin {area:,.1f} m² + {WET_SKIRT:g} m etek × çevre {cevre:,.1f} m", kaynak)
        else:
            add("SIVA", "", duvar, f"çevre {cevre:,.1f} m × {h:g} m (çevre mahal sınırından ÖLÇÜLDÜ)", kaynak)
            add("BOYA", "", duvar, f"çevre {cevre:,.1f} m × {h:g} m (çevre mahal sınırından ÖLÇÜLDÜ)", kaynak)
    return out


# Paftalar arası hizalama. Mahaller MİMARİ plandan çıkar; elektrik / mekanik / kaplama paftası
# ayrı bir çizimdir ve koordinatı aynı olmayabilir. Aday kayma iki kaynaktan gelir: (1) aynı mahal yazısı
# iki paftada da varsa yazı konum farkı, (2) kaymasız hal (aynı modelden türetilmiş paftalarda tipik).
# Aday DOĞRULANARAK seçilir: o kaymayla kaç eleman bir mahalin içine düşüyor.
ALIGN_MIN_HIT = 0.05        # elemanların en az bu oranı mahale düşmeli (bir dosyada birden çok kat
                            # olabilir: her katın payı küçüktür; eşik düşük ama eşleşme doğrulanır)
ALIGN_MIN_COUNT = 3         # ve en az bu kadar eleman
ALIGN_BOX_MARGIN = 5.0      # m — hizalama kutusuna bu kadar pay verilir (kutu isabet eden noktalardan çıkar)
NOKTA_MAX_AREA = 4.0        # m² — bundan küçük ve uzunluğu olmayan eleman "nokta" sayılır (armatür, priz,
                            # kamera, menfez): hizalama aramaşı yalnız bunları kullanır


def _label_offsets(target: Drawing, source: Drawing) -> list[tuple[float, float]]:
    """İki paftada da geçen mahal yazılarından aday kaymalar (ad + alan eşleşmesi)."""
    src: dict[str, list[dict]] = {}
    for r in (source.rooms or []):
        if r.get("x") is not None:
            src.setdefault(str(r.get("name") or "").upper(), []).append(r)
    out: list[tuple[float, float]] = []
    for r in (target.rooms or []):
        if r.get("x") is None:
            continue
        for q in src.get(str(r.get("name") or "").upper(), []):
            a1, a2 = float(r.get("area_m2") or 0.0), float(q.get("area_m2") or 0.0)
            if a1 > 0 and a2 > 0 and abs(a1 - a2) > max(0.05, 0.01 * max(a1, a2)):
                continue
            out.append((round(q["x"] - r["x"], 2), round(q["y"] - r["y"], 2)))
    return out


def _space_points(d: Drawing) -> list[tuple[str, float, tuple[float, float]]]:
    """Paftanın mahalleri: (ad, alan, temsil noktası). Konum çokgenin merkezinden gelir."""
    from shapely.geometry import Polygon
    out = []
    for sp in (d.spaces or []):
        pts = sp.get("points") or []
        if len(pts) < 3:
            continue
        try:
            c = Polygon(pts).centroid
        except Exception:
            continue
        out.append((str(sp.get("name") or "").upper(),
                    float(sp.get("label_area") or sp.get("area") or 0.0), (c.x, c.y)))
    return out


def same_plan_offset(target: Drawing, source: Drawing) -> tuple[float, float] | None:
    """İki pafta AYNI katı mı gösteriyor? Aynı adlı ve aynı alanlı mahaller hep AYNI kaymayı
    veriyorsa evet; kayma döner.

    Elektrik / mekanik / kaplama paftası mimari altlık taşıdığı için kendi mahallerini de üretir;
    mahal listesi ikilenmesin diye bu kontrol yapılır. Farklı katlar (bodrum / zemin) eşleşmez:
    mahal adları ve alanları tutmaz."""
    t, sp = _space_points(target), _space_points(source)
    offs: list[tuple[float, float]] = []
    for n1, a1, p1 in t:
        for n2, a2, p2 in sp:
            if n1 != n2 or not n1:
                continue
            if a1 > 0 and a2 > 0 and abs(a1 - a2) > max(0.05, 0.01 * max(a1, a2)):
                continue
            offs.append((round(p2[0] - p1[0], 2), round(p2[1] - p1[1], 2)))
    offs += _label_offsets(target, source)
    if len(offs) < 2:
        return None
    say: dict[tuple[float, float], int] = {}
    for o in offs:
        say[o] = say.get(o, 0) + 1
    en_iyi, adet = max(say.items(), key=lambda kv: kv[1])
    hedef = max(len(t), sum(1 for r in (target.rooms or []) if r.get("x") is not None), 1)
    return en_iyi if adet >= 2 and adet >= 0.5 * hedef else None


def _point_clusters(pts: list[tuple[float, float]], gap: float) -> list[list[tuple[float, float]]]:
    """Noktaları x ekseninde boşluklara göre kümeler. Bir tesisat dosyasında kat planları yan yana durur;
    her kat kendi kaymasını ister, bu yüzden küme küme aday üretilir."""
    if not pts:
        return []
    sp = sorted(pts)
    out, cur = [], [sp[0]]
    for a, b in zip(sp, sp[1:]):
        (cur.append(b) if b[0] - a[0] <= gap else (out.append(cur), cur := [b]))
    out.append(cur)
    return [c for c in out if len(c) >= 5]


def _hit_count(pts, tree, polys, dx: float, dy: float, kutu: bool = False):
    """Bu kaymayla kaç nokta bir mahalin içine düşüyor. kutu=True ise isabet eden noktaların
    (ÇİZİMDEKİ özgün koordinatlarıyla) sınır kutusunu da döndürür."""
    from shapely.geometry import Point as SPoint
    n = 0
    xs: list[float] = []
    ys: list[float] = []
    for x, y in pts:
        p = SPoint(x + dx, y + dy)
        for i in tree.query(p):
            if polys[int(i)][1].contains(p):
                n += 1
                if kutu:
                    xs.append(x)
                    ys.append(y)
                break
    if not kutu:
        return n
    return n, ((min(xs), min(ys), max(xs), max(ys)) if xs else None)


def _refine(pts, tree, polys, seed: tuple[float, float], adim: float = 32.0) -> tuple[tuple[float, float], int]:
    """Aday kaymayı yerel aramayla keskinleştirir (kaba adımdan ince adıma tepe tırmanışı).

    Başlangıç adımı büyük tutulur: tohum (küme merkezi farkı) gerçek kaymadan on metrelerce uzak
    olabiliyor ve küçük adımla yola çıkınca arama yerel tepeye takılıp yanlış kata oturuyordu."""
    en_iyi, skor = seed, _hit_count(pts, tree, polys, *seed)
    while adim >= 0.25:
        gelisti = False
        for ddx, ddy in ((adim, 0), (-adim, 0), (0, adim), (0, -adim), (adim, adim), (-adim, -adim),
                         (adim, -adim), (-adim, adim)):
            aday = (round(en_iyi[0] + ddx, 2), round(en_iyi[1] + ddy, 2))
            n = _hit_count(pts, tree, polys, *aday)
            if n > skor:
                en_iyi, skor, gelisti = aday, n, True
        if not gelisti:
            adim /= 2
    return en_iyi, skor


def align_drawing(target: Drawing, source: Drawing, elements, polys) -> dict:
    """Paftayı kaynak paftanın mahal çokgenlerine hizalar (yalnız öteleme).

    Aday kaymalar: (1) kaymasız hal, (2) mahal yazıları örtüşüyorsa oradan, (3) eleman kümesinin
    merkezi ile mahal kümesinin merkezi arasındaki fark. Her aday yerel aramayla keskinleştirilir ve
    **doğrulanarak** seçilir: o kaymayla kaç eleman bir mahalin içine düşüyor. Tahmin yok."""
    from shapely import STRtree
    # Hizalama yalnız NOKTA elemanlarıyla aranır (armatür, priz, kamera, menfez, doğrama): bunlar mahalin
    # içinde durur. Kablo / boru / duvar gibi çizgisel elemanlar mahaller arasında uzanır ve aramayı yanıltır
    # — yanlış kayma, armatürleri komşu odaya yazmak demektir.
    nokta = [e for e in elements if e.points and not (getattr(e, "length", 0) or 0)
             and (getattr(e, "area", 0) or 0) <= NOKTA_MAX_AREA]
    kaynak_els = nokta or [e for e in elements if e.points]
    pts = [(e.points[0][0], e.points[0][1]) for e in kaynak_els]
    out = {"dx": 0.0, "dy": 0.0, "hit": 0, "total": len(pts), "source": "", "bbox": None}
    if not pts or not polys:
        return out
    if len(pts) > 1500:
        pts = pts[::max(1, len(pts) // 1500)]        # doğrulama için örnekleme yeter
    kaba = pts[::max(1, len(pts) // 350)]            # kaba arama daha az noktayla yapılır
    tree = STRtree([g for _sp, g in polys])
    mx = sum(g.centroid.x for _sp, g in polys) / len(polys)
    my = sum(g.centroid.y for _sp, g in polys) / len(polys)
    genislik = max(g.bounds[2] for _sp, g in polys) - min(g.bounds[0] for _sp, g in polys)
    adaylar: list[tuple[tuple[float, float], str]] = [((0.0, 0.0), "aynı koordinat sistemi")]
    for off in dict.fromkeys(_label_offsets(target, source)):
        adaylar.append((off, "mahal yazılarından"))
    # Tohumlar birden çok ölçekte kümelenerek üretilir: tek bir boşluk eşiği, yan yana duran kat
    # planlarını kimi dosyada birleştirip kimi dosyada parçalıyor. Zengin tohum = yerel tepeye takılmamak.
    gorulen: set[tuple[float, float]] = set()
    for bosluk in (20.0, 60.0, max(genislik, 20.0)):
        for kume in _point_clusters(pts, bosluk):
            cx = sum(x for x, _ in kume) / len(kume)
            cy = sum(y for _, y in kume) / len(kume)
            aday = (round(mx - cx, 2), round(my - cy, 2))
            if aday not in gorulen:
                gorulen.add(aday)
                adaylar.append((aday, "çizim konumlarından aranarak"))
    for (dx, dy), kaynak in adaylar:
        (ndx, ndy), _ = _refine(kaba, tree, polys, (dx, dy))
        hit, kutu = _hit_count(pts, tree, polys, ndx, ndy, kutu=True)
        if hit > out["hit"]:
            out = {"dx": ndx, "dy": ndy, "hit": hit, "total": len(pts), "source": kaynak, "bbox": kutu}
    return out


def space_breakdown(project: Project, session: Session, drawings: list[Drawing] | None = None) -> dict:
    """Mahal bazında keşif: her mahalin kendi kalemleri, keşifteki aynı ölçüm kurallarıyla.

    Mahaller mimari paftadan çıkar (`parser/spaces.py`); eleman ancak KENDİ paftasının mahalleriyle
    eşleşir (başka paftanın koordinatı farklıdır). Mahale düşmeyen miktar "atanmamış" satırında
    toplanır — mahal toplamları + atanmamış = keşif toplamı."""
    from .parser.levels import floor_rank
    from .quantity.boq import architectural_items, electrical_items, standard_items
    if drawings is None:
        drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    params = project_params(project)
    catalog = load_catalog()
    sh = storey_heights(project, drawings)
    els_by_id, _ = measured_elements(project, session, drawings)
    spaces: dict[str, dict] = {}        # key -> mahal
    buckets: dict[str, list[dict]] = {}  # key -> ölçeklenmiş eleman dictleri
    unassigned: list[tuple[Drawing, dict]] = []
    warnings: list[str] = []
    polys_by_src: dict[int, list] = {}
    # Birincil mahal kaynağı: sınırı doğrulanmış mahali en çok olan pafta (mimari plan).
    aday = sorted([d for d in drawings if d.spaces],
                  key=lambda x: (-sum(1 for sp in x.spaces if sp.get("area_source") == "drawing"),
                                 -sum(float(sp.get("area") or 0) for sp in x.spaces)))
    sources: list[Drawing] = []
    merged: dict[int, tuple[int, tuple[float, float]]] = {}    # pafta -> (mahal kaynağı, kayma)
    hizalama: dict[tuple, dict] = {}                            # (pafta, mahal kaynağı) -> rapor
    for d in aday:
        yer = None
        for src in sources:
            off = same_plan_offset(d, src)
            if off is not None:
                yer = (src, off)
                break
        if yer:
            merged[d.id] = (yer[0].id, yer[1])
            hizalama[(d.id, yer[0].id)] = {"drawing": d.label or d.filename,
                                           "to": yer[0].label or yer[0].filename,
                                           "dx": yer[1][0], "dy": yer[1][1], "how": "mahal örtüşmesi",
                                           "hit": 0, "total": 0}
            warnings.append(f"“{d.label or d.filename}” aynı katı gösteriyor "
                            f"(“{yer[0].label or yer[0].filename}” ile mahal yazıları örtüşüyor): "
                            "mahal listesi ikilenmedi, kalemleri o mahallere yazıldı.")
        else:
            sources.append(d)
    for d in sources:
        sps = d.spaces or []
        by_index = {sp["index"]: sp for sp in sps}
        for sp in sps:
            key = f"{d.id}:{sp['index']}"
            path, cur, guard = [sp["name"]], sp, 0
            while cur.get("parent") is not None and by_index.get(cur["parent"]) and guard < 8:
                cur = by_index[cur["parent"]]
                path.insert(0, cur["name"] or "?")
                guard += 1
            spaces[key] = {"key": key, "name": sp["name"], "kind": sp["kind"], "area": sp["area"],
                           "code": sp.get("code") or "", "area_source": sp.get("area_source") or "polygon",
                           "perimeter": sp.get("perimeter") or 0.0, "diff_pct": sp.get("diff_pct") or 0.0,
                           "label_area": sp.get("label_area") or 0.0, "drawing": d.label or d.filename,
                           # ERP ağacı: Blok → Kat → Mahal. Blok çizim adından (parser/blocks.py), kat sırası
                           # pafta başlığından gelir; sıralama bodrum → zemin → kat → çatı olsun diye sayıdır.
                           "block": d.block or "", "floor_rank": floor_rank(d.label or d.filename),
                           "drawing_id": d.id, "path": " / ".join(x for x in path if x),
                           "parent": f"{d.id}:{sp['parent']}" if sp.get("parent") is not None else None,
                           "children": [f"{d.id}:{c}" for c in (sp.get("children") or [])]}
            buckets[key] = []
        polys_by_src[d.id] = _space_polys(sps)
    # her pafta: kendi mahalleri varsa doğrudan, yoksa hizalanabildiği mimari paftaya
    for d in drawings:
        els = els_by_id[d.id]
        if not els:
            continue
        if d.id in merged:
            src_id, off = merged[d.id]
        elif d.spaces:
            src_id, off = d.id, (0.0, 0.0)
        else:
            # Bir tesisat dosyasında kat planları yan yana durabilir (aydinlatma planının bodrum / zemin /
            # çatı katı birlikte çizilmesi gibi): HER kat için ayrı kayma aranır, eleman hangi katın
            # mahaline düşüyorsa oraya yazılır.
            # (pafta, kayma, hizalama kutusu): kutu, o kaymayla mahale düşen noktaların çizimdeki
            # sınırıdır. Bir kat, başka katın bölgesindeki elemanı kapmasın diye atama bu kutuyla sınırlanır:
            # büyük bir mahal (1.200 m² spor salonu) yanlış kaymayla komşu katın armatürünü içine alabiliyor.
            kabul: list[tuple[Drawing, tuple[float, float], tuple | None]] = []
            en_iyi = None
            for src in sources:
                a = align_drawing(d, src, els, polys_by_src[src.id])
                if en_iyi is None or a["hit"] > en_iyi["hit"]:
                    en_iyi = a
                if a["hit"] >= ALIGN_MIN_COUNT and a["hit"] >= ALIGN_MIN_HIT * max(a["total"], 1):
                    kabul.append((src, (a["dx"], a["dy"]), a.get("bbox")))
                    nasil = ("aynı koordinatta" if (a["dx"], a["dy"]) == (0.0, 0.0)
                             else f"({a['dx']:+.1f}, {a['dy']:+.1f}) m kaydırılarak")
                    hizalama[(d.id, src.id)] = {"drawing": d.label or d.filename, "to": src.label or src.filename,
                                                "dx": a["dx"], "dy": a["dy"], "how": a["source"],
                                                "hit": 0, "total": 0}
                    warnings.append(f"“{d.label or d.filename}” → “{src.label or src.filename}” "
                                    f"mahallerine {nasil} hizalandı.")
            if not kabul:
                unassigned += [(d, _scaled(e, 1.0)) for e in els]
                if en_iyi and en_iyi["total"]:
                    warnings.append(f"“{d.label or d.filename}” mahallere hizalanamadı "
                                    f"({en_iyi['total']} elemandan yalnız {en_iyi['hit']}'i bir mahalin içine düştü): "
                                    "kalemleri mahal kırılımına girmedi. Pafta başka koordinatta çizilmiş olabilir.")
                continue
            for e in els:
                kondu = False
                for src, o, kutu in kabul:
                    if kutu is not None and e.points:
                        x, y = e.points[0][0], e.points[0][1]
                        pay = ALIGN_BOX_MARGIN
                        if not (kutu[0] - pay <= x <= kutu[2] + pay and kutu[1] - pay <= y <= kutu[3] + pay):
                            continue        # bu eleman o katın bölgesinde değil
                    rapor = hizalama.get((d.id, src.id))
                    if rapor is not None:
                        rapor["total"] += 1
                    share = _shares(e, polys_by_src.get(src.id) or [], offset=o)
                    if not share:
                        continue
                    if rapor is not None:
                        rapor["hit"] += 1
                    for idx, w in share.items():
                        buckets[f"{src.id}:{idx}"].append(_scaled(e, w))
                    kondu = True
                    break
                if not kondu:
                    unassigned.append((d, _scaled(e, 1.0)))
            continue
        polys = polys_by_src.get(src_id) or []
        rapor = hizalama.get((d.id, src_id))
        for e in els:
            share = _shares(e, polys, offset=off) if polys else {}
            if rapor is not None:
                rapor["total"] += 1
                rapor["hit"] += 1 if share else 0
            if not share:
                unassigned.append((d, _scaled(e, 1.0)))
                continue
            for idx, w in share.items():
                buckets[f"{src_id}:{idx}"].append(_scaled(e, w))
    if not spaces:
        return {"spaces": [], "unassigned": [], "unassigned_reason": "Mimari paftada mahal sınırı bulunamadı.",
                "warnings": ["Mahal listesi yok: mimari kat planı yükleyin (mahal sınırları duvarlardan çıkarılır)."]}

    def items_of(entries: list[dict]) -> list[dict]:
        """Verilen elemanlar için keşif kalemleri (mimari + elektrik + KSF kurallarıyla)."""
        if not entries:
            return []
        arch = [x for x in entries if TYPE_DISCIPLINE.get(_g_etype(x["e"])) == "architectural"]
        elec = [x for x in entries if TYPE_DISCIPLINE.get(_g_etype(x["e"])) == "electrical"]
        ksf = [x for x in entries if (x["e"].get("meta") or {}).get("ksf_code") or parse_layer(x["e"].get("layer") or "", catalog)]
        out: list[BoqItem] = []

        def pack(rows):
            per: dict[int, dict] = {}
            for r in rows:
                ent = per.setdefault(r["drawing"].id, {"id": r["drawing"].id, "label": r["drawing"].label or r["drawing"].filename,
                                                       "storey_count": r["drawing"].storey_count,
                                                       "storey_height": storey_height_of(project, r["drawing"], sh),
                                                       "slab_thickness": project.slab_thickness, "elements": []})
                ent["elements"].append(r["e"])
            return list(per.values())

        if arch:
            out += architectural_items(pack(arch), params)
        if elec:
            out += electrical_items(pack(elec), params)
        if ksf:
            out += standard_items(pack(ksf), params, catalog)
        # Kapsam filtresi: mahale YALNIZ mahal bazlı kalemler yazılır (app/scope.py).
        # Duvar elemanı buraya girmeye devam eder — gövdesi (genel) elenir ama sıvası ve boyası
        # (mahal) kalır; ayıklama bu yüzden eleman düzeyinde değil kalem düzeyinde yapılır.
        # Kablo / boru / tava böylece mahallere bölüşturulmez: bir kablo kattan kata uzanır,
        # geçtiği odalara bölününce kimsenin sipariş edemeyeceği sayılar çıkar.
        return [it for it in sort_items(merge_duplicates(out))
                if it.group != "fire" and it.scope == MAHAL]

    rows = []
    for key, sp in spaces.items():
        d = next(x for x in drawings if x.id == sp["drawing_id"])
        note = _room_note_of(d, sp)
        sp = {**sp, "finish": note.get("finish") or {}, "screed_cm": note.get("screed_cm") or 0.0}
        olculen = items_of([{"drawing": d, "e": e} for e in buckets[key]])
        olculen_keys = {it.key for it in olculen}
        # Türetme ÖLÇÜMÜN YEDEĞİDİR, üzerine eklenmez. Mahalin sıvası iki yoldan çıkabiliyor:
        # (1) mahale düşen duvar elemanlarının gerçek geometrisinden, (2) mahal çevresi × yükseklikten.
        # İkisi de yazılınca aynı duvar yüzü iki kez sayılıyor ve mahal toplamı keşifle tutmuyordu
        # (gerçek projede sıva +%25). Ölçülen varsa türetilen aynı kalem yazılmaz.
        turetilen = [it for it in space_derived(project, sp, catalog, params, drawings)
                     if it.scope == MAHAL and it.key not in olculen_keys]
        # reçete mahal satırında da açılır: seramik → yapıştırıcı + DERZ DOLGU, şap → şap işçiliği
        hepsi = expand_recipes(olculen + turetilen, catalog, storey_height=sh["effective"], params=params)
        sp["items"] = [it.to_dict() for it in hepsi if it.key in olculen_keys]
        sp["derived"] = [{**it.to_dict(), "derived": True,
                          "note": (it.notes[0] if it.notes else ""),
                          "source": (it.detail or {}).get("source", "reçete")}
                         for it in hepsi if it.key not in olculen_keys]
        rows.append(sp)
    # grup (daire) toplamları: kendi kalemleri + çocuklarının kalemleri
    by_key = {r["key"]: r for r in rows}
    for r in rows:
        if r["kind"] != "grup":
            continue
        kids = [by_key[k] for k in r["children"] if k in by_key]
        tot: dict[str, dict] = {}
        for src in [r] + kids:
            for it in src["items"] + [x for x in src.get("derived", [])]:
                cur = tot.setdefault(it["key"], {**it, "quantity": 0.0})
                cur["quantity"] = round(cur["quantity"] + it["quantity"], 3)
        r["total_items"] = sorted(tot.values(), key=lambda i: (i["work_group"], i["kind"], i["group"]))
        r["total_area"] = round(r["area"], 2)
    # "Atanmamış" artık yalnız **mahal bazlı olup** bir mahale düşmeyen kalemleri anlatır: bir kalemin
    # mahal kırılımında olmaması bir eksiklik değil, o kalemin doğası olabilir (beton, kablo, çatı).
    un_items = [it.to_dict() for it in items_of([{"drawing": d, "e": e} for d, e in unassigned])]
    if un_items:
        warnings.append(f"{len(un_items)} mahal bazlı kalem hiçbir mahale atanamadı: elemanı mahal sınırının "
                        "dışında ya da mahal çıkarılmayan bir paftada. Mahal toplamlarına girmez.")
    return {"spaces": rows, "unassigned": un_items, "alignment": list(hizalama.values()),
            "unassigned_reason": "Mahal sınırı dışında kalan ya da mahal çıkarılmayan paftalardaki elemanlar",
            "scope_note": ("Beton, demir, kalıp, duvar gövdesi, kablo, boru, tava, cephe ve çatı **bina geneli** "
                           "sayılır; mahal kırılımına girmez. Bir duvar iki mahalin ortak sınırıdır, gövdesini tek "
                           "mahale yazmak yanlış olurdu — ama her yüzü tek bir mahale baktığı için sıva ve boya "
                           "mahal bazlıdır."),
            "warnings": warnings}


def excavation_depth(project: Project, drawings: list[Drawing], params: dict,
                     found_kot: float | None = None, found_thickness: float = 0.0) -> dict:
    """Temel altı kazı derinliği (m) ve NEREDEN geldiği — varsayılan son çaredir.

    Sıra: (1) kesitte yazılı kazı derinliği, (2) tabii zemin kotu − kazı tabanı kotu,
    (3) tabii zemin (yoksa ±0,00) − (temel paftasının kotu − temel kalınlığı − grobeton),
    (4) kullanıcının girdiği parametre, (5) program varsayılanı (kontrol listesinde sorulur)."""
    ev = merge_materials([d.materials or {} for d in drawings])

    def val(code: str) -> tuple[float | None, str]:
        e = ev.get(code) or {}
        try:
            return float(str(e.get("spec")).replace(",", ".")), (e.get("evidence") or [""])[0]
        except (TypeError, ValueError):
            return None, ""

    depth, note = val("KAZI_DERINLIK")
    if depth and depth > 0:
        return {"m": round(depth, 2), "source": "note", "detail": f"kesitte yazılı: “{note}”"}
    ground, g_note = val("KOT_ZEMIN")
    bottom, b_note = val("KOT_KAZI_TABAN")
    if ground is not None and bottom is not None and ground - bottom > 0.2:
        return {"m": round(ground - bottom, 2), "source": "kots",
                "detail": f"tabii zemin {ground:+.2f} − kazı tabanı {bottom:+.2f} (“{g_note}”; “{b_note}”)"}
    if found_kot is not None:
        lean = float(params.get("lean_concrete_cm") or 0.0) / 100.0
        top = ground if ground is not None else 0.0
        d = top - (found_kot - found_thickness - lean)
        if d > 0.2:
            src = f"tabii zemin {ground:+.2f}" if ground is not None else "zemin ±0,00 kabulü"
            return {"m": round(d, 2), "source": "foundation_kot",
                    "detail": f"{src} − (temel kotu {found_kot:+.2f} − kalınlık {found_thickness:g} m − grobeton {lean:g} m)"}
    raw = project.params or {}
    if raw.get("excavation_depth_m"):
        return {"m": float(raw["excavation_depth_m"]), "source": "param", "detail": "proje parametresi (siz girdiniz)"}
    return {"m": float(params.get("excavation_depth_m") or 0.0), "source": "default",
            "detail": "program varsayılanı — kesitte kazı / tabii zemin kotu yazmıyor"}


def roof_zones(project: Project, session: Session, drawings: list[Drawing] | None = None) -> list[dict]:
    """Çatı planındaki bölgeler: her kapalı alanın sistemi, alanı ve kanıtı.

    Sistem bölgenin içine yazılmış nottan gelir (`detectors/standard.py: assign_roof_zones`). İçinde yazı
    olmayan bölge katmanın kalemiyle kalır ("layer"), iki sistem yazan bölge seçim bekler ("conflict")."""
    from .parser.detectors.standard import ROOF_ZONE_BASE
    if drawings is None:
        drawings = session.exec(select(Drawing).where(Drawing.project_id == project.id)).all()
    rows: list[dict] = []
    for d in drawings:
        for e in _included_elements(d, session):
            meta = e.meta or {}
            code = str(meta.get("ksf_code") or e.etype or "").upper()
            if code not in ROOF_ZONE_BASE or (e.area or 0.0) <= 0:
                continue
            rows.append({"drawing": d.label or d.filename, "system": code, "area": round(e.area, 2),
                         "note": meta.get("zone_note") or "",
                         "conflict": meta.get("zone_conflict") or [],
                         "source": "note" if meta.get("zone_note") else ("conflict" if meta.get("zone_conflict") else "layer")})
    return sorted(rows, key=lambda z: -z["area"])


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
    out = {"area": 0.0, "source": "none", "detail": "", "system": "", "system_source": "", "candidates": [],
           "zones": roof_zones(project, session, drawings)}
    if measured > 0:
        out.update(area=round(measured, 2), source="measured", detail="çizimde ölçülen çatı kalemi")
    elif params.get("roof_area_m2"):
        out.update(area=float(params["roof_area_m2"]), source="manual", detail="proje parametresi (elle girildi)")
    else:
        # Her bloğun çatısı ayrıdır: blok başına en büyük kat oturumu alınır ve bloklar toplanır.
        # (Tek blokta davranış aynıdır: katların en büyüğü.) Podyum üstünde kalan teras ayrıca yazılır.
        fps = [fp for fp in _plan_footprints(project, session, drawings) if not fp["basement"]]
        if fps:
            per_block: dict[str, dict] = {}
            for fp in fps:
                b = fp.get("block") or ""
                if fp["area"] > per_block.get(b, {"area": 0.0})["area"]:
                    per_block[b] = fp
            tops = list(per_block.values())
            common = per_block.get("")            # ortak / birleşik kat (podyum): bodrum değil, zemin
            towers = sum(f["area"] for b, f in per_block.items() if b)
            names = ", ".join(f"{f.get('block') or 'ortak'}: {f['drawing']}" for f in tops)
            if common and towers > 0:
                # Bloklar podyumun üstünde oturur: yukarıdan bakınca bütün çatı yüzeyleri podyum oturumunu kaplar.
                # Toplam = podyum oturumu; blok çatıları + aradaki teras bunun içindedir (üst üste sayılmaz).
                total = max(common["area"], towers)
                terrace = round(total - towers, 2)
                detail = (f"birleşik kat oturumu ({common['drawing']}) = blok çatıları ({towers:,.0f} m²) "
                          f"+ podyum terası ({max(terrace, 0):,.0f} m²)")
                if terrace > 1.0:
                    out["terrace"] = terrace
            elif len(tops) > 1:
                total = towers or sum(f["area"] for f in tops)
                detail = f"blok başına en büyük kat planı oturumu, {len(tops)} blok toplandı ({names})"
            else:
                total = tops[0]["area"]
                detail = f"en büyük kat planı oturumu ({tops[0]['drawing']})"
            out.update(area=round(total, 2), source="estimated", detail=detail + "; tahmin, elle düzeltilebilir")
    evidence = merge_materials([d.materials or {} for d in drawings])
    cands = [c for c in ROOF_SYSTEM_EVIDENCE if c in evidence]
    out["candidates"] = cands
    code = str(params.get("roof_system") or "").strip().upper()
    zoned = [z for z in out["zones"] if z["source"] == "note"]
    if code:
        out.update(system=code, system_source="manual")
    elif zoned:
        # bölge bazlı okundu: proje geneli tek sistem yok, her bölge kendi sistemiyle ölçüldü
        systems = sorted({z["system"] for z in out["zones"]})
        out.update(system=" + ".join(systems), system_source="zones")
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
                    notes=[f"Miktar = çatı alanı ({ra['detail']}); sistem: {src}"],
                    detail={"roof_auto": True, "evidence": {TAHMIN: round(ra["area"], 3)}})]


DEFAULT_FINISH_KEYWORDS = "LOBİ,LOBI,VİTRİN,VITRIN,GİRİŞ,GIRIS,HOL,KORİDOR,KORIDOR,FUAYE"
# Islak hacim mahal adı: zemin / duvar seramiği ve sürme izolasyon ayrı kuralla gelir, şap / kaplama kuralına girmez.
WET_ROOM = re.compile(r"\bWC\b|BANYO|DU[SŞ]\b|ISLAK|LAVABO|TUVALET|BATHROOM|TOILET", re.IGNORECASE)


def finish_area(project: Project, drawings: list[Drawing], params: dict | None = None) -> dict:
    """Şap / döşeme kaplaması: alan, kaplama TİPİ ve şap KALINLIĞI — hepsi çizimden.

    Mahal yazısının yanına yazılmış not ("ŞAP 5 CM", "SERAMİK 60x60", parser/analyzer.room_rows) o mahallin
    kaplamasını ve şap kalınlığını verir; notu olan mahal, mahal türü listesinde geçmese de kapsama girer.
    Notu olmayan mahaller için sıra: (1) finish_area_m2 parametresi, (2) mahal türü anahtar kelimeleri."""
    from .planset import normalize_title
    params = params or project_params(project)
    kws = [k.strip() for k in str(params.get("finish_rooms") or DEFAULT_FINISH_KEYWORDS).split(",") if k.strip()]
    kws_n = [normalize_title(k) for k in kws]
    out = {"area": 0.0, "source": "none", "detail": "", "keywords": kws, "rooms": [], "excluded": [], "excluded_area": 0.0,
           "by_finish": [], "by_screed": [], "untyped_area": 0.0}
    if params.get("finish_area_m2"):
        a = float(params["finish_area_m2"])
        cm, src, det = _screed_fallback(project, drawings, params)
        out.update(area=a, source="manual", detail="şap / kaplama alanı (elle girildi)", untyped_area=a,
                   by_screed=[{"cm": cm, "area": a, "rooms": [], "source": src, "detail": det}] if cm > 0 else [])
        return out
    total = 0.0
    groups: dict[tuple[str, str], dict] = {}
    screeds: dict[float, dict] = {}
    for d in drawings:
        mult = max(1, d.storey_count or 1)
        for r in (d.rooms or []):
            name = str(r.get("name") or "")
            name_n = normalize_title(name)
            note = r.get("finish") or {}
            wet = bool(WET_ROOM.search(name))
            # notu olan mahal, tür listesinde geçmese de kapsamdadır (çizim öyle diyor). Islak hacim zemini
            # ayrı kuralla (seramik + sürme izolasyon) gelir: çift saymamak için yalnız açıkça istenirse girer.
            by_note = bool(note) or bool(r.get("screed_cm"))
            by_kw = any(k and k in name_n for k in kws_n)
            hit = by_kw or (by_note and not wet)
            area = float(r.get("area_m2") or 0.0) * mult
            row = {"drawing": d.label or d.filename, "name": r.get("name"), "area_m2": r.get("area_m2", 0.0), "included": hit,
                   "finish": note.get("code", ""), "finish_spec": note.get("spec", ""), "finish_text": note.get("text", ""),
                   "screed_cm": r.get("screed_cm") or 0.0}
            out["rooms"].append(row)
            if not hit:
                out["excluded"].append(f"{name} {r.get('area_m2', 0):,.0f} m²" + (" (ıslak hacim)" if wet else ""))
                out["excluded_area"] += area
                continue
            total += area
            if note.get("code"):
                g = groups.setdefault((note["code"], note.get("spec") or ""),
                                      {"code": note["code"], "spec": note.get("spec") or "", "area": 0.0, "rooms": [], "texts": []})
                g["area"] += area
                g["rooms"].append(name)
                if note.get("text") and note["text"] not in g["texts"]:
                    g["texts"].append(note["text"])
            else:
                out["untyped_area"] += area
            cm = float(r.get("screed_cm") or 0.0)
            if cm > 0:
                sc = screeds.setdefault(cm, {"cm": cm, "area": 0.0, "rooms": [], "source": "rooms",
                                             "detail": r.get("screed_note") or ""})
                sc["area"] += area
                sc["rooms"].append(name)
    if total > 0:
        n = sum(1 for r in out["rooms"] if r["included"])
        typed = sum(g["area"] for g in groups.values())
        det = f"seçili mahaller ({n} mahal: {', '.join(kws[:4])}…) toplamı"
        if typed > 0:
            det = f"{n} mahal; {typed:,.0f} m²'sinin kaplama tipi mahal notundan okundu"
        out.update(area=round(total, 2), source="rooms", detail=det)
    out["by_finish"] = sorted(groups.values(), key=lambda g: -g["area"])
    # kalınlığı yazmayan mahaller: çizimin genel notu, yoksa kullanıcı parametresi, yoksa program varsayılanı
    rest = round(total - sum(s["area"] for s in screeds.values()), 2)
    if total > 0 and (rest > 0.01 or not screeds):
        cm, src, det = _screed_fallback(project, drawings, params)
        if cm > 0:
            sc = screeds.setdefault(cm, {"cm": cm, "area": 0.0, "rooms": [], "source": src, "detail": det})
            sc["area"] += max(rest, 0.0)
            if sc["source"] != src and rest > 0:
                # aynı kalınlık hem mahal notundan hem genel nottan geldi: ikinci kaynağı da yaz
                sc["also"] = {"area": round(rest, 2), "source": src, "detail": det}
    out["by_screed"] = sorted(screeds.values(), key=lambda s: -s["area"])
    return out


def _screed_fallback(project: Project, drawings: list[Drawing], params: dict) -> tuple[float, str, str]:
    """Mahal notu olmayan alan için şap kalınlığı: çizimin genel notu > kullanıcı parametresi > varsayılan."""
    ev = merge_materials([d.materials or {} for d in drawings]).get("SAP") or {}
    try:
        cm = float(str(ev.get("spec") or "").replace(",", "."))
    except ValueError:
        cm = 0.0
    if cm > 0:
        note = (ev.get("evidence") or [""])[0]
        return cm, "drawing", f"çizim notundan: “{note}”"
    raw = project.params or {}
    if raw.get("screed_cm"):
        return float(raw["screed_cm"]), "param", "proje parametresi (siz girdiniz)"
    return float(params.get("screed_cm") or 5.0), "default", "program varsayılanı — çizimde şap kalınlığı yazmıyor"


# Kavisli / kemerli doğrama: bu sözcükler geçen poz yazısı kemer detayı demektir.
CURVED_WORDS = re.compile(r"KAV[İI]S|KEMER|YAY\b|ARCH|RADIUS|OVAL", re.IGNORECASE)


def _curved_joinery(drawings, session) -> dict[str, float]:
    """Yazısında kavis / kemer geçen doğrama pozları: {poz: adet}."""
    out: dict[str, float] = {}
    for d in drawings:
        for e in _included_elements(d, session):
            if e.etype != "dograma":
                continue
            metin = f"{e.name or ''} {(e.meta or {}).get('note') or ''} {e.label_raw or ''}"
            if CURVED_WORDS.search(metin.replace("i", "İ")):
                k = e.subtype or e.name or "?"
                out[k] = out.get(k, 0.0) + (e.count or 1)
    return out


def _sizeless_joinery(items) -> dict[str, float]:
    """Ölçüsü bulunamamış doğrama pozları: {poz: adet}. Adet biliniyor, boyut bilinmiyor."""
    out: dict[str, float] = {}
    for it in items:
        if it.kind != "dograma" or it.detail.get("size"):
            continue
        poz = (it.label.split()[-1] if it.label else "") or it.group
        out[poz] = out.get(poz, 0.0) + (it.count or 0.0)
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

    def add(code: str, spec: str, q: float, note: str, rule: str, source: str = ""):
        """source: kalemin dayandığı parametre nereden geldi (rooms / drawing / param / default) — kalite raporu bunu kullanır."""
        it = catalog.get(code)
        if not it or q <= 0 or rule in off:
            return
        group = slug(spec) if spec else "*"
        # Kanıt kademesi kaynağına bakar: mahal notundan / kesit kotundan okunan ölçü bir türetmedir
        # ("turetildi"); parametre varsayılanı ya da "çevre = 4·√alan" gibi geometrik kabul tahmindir.
        kademe = TAHMIN if (rule == "islak" or source in ("param", "default", "")) else TURETILDI
        detail = {"derived": True, "rule": rule, "evidence": {kademe: round(q, 3)}} | ({"param_source": source} if source else {})
        out.append(BoqItem(key=f"{it.code.lower()}:{group}", kind=it.code.lower(), group=group,
                           label=it.name + (f" {spec}" if spec else ""), unit=it.unit, quantity=round(q, 3),
                           discipline=f"ksf:{it.discipline}", kind_label=it.name, discipline_label=catalog.discipline_name(it.discipline),
                           notes=[f"Türetildi: {note}"], detail=detail))

    def ask(code: str, text: str, level: str = "required"):
        check.append({"code": code, "text": text, "level": level})

    # 1) boya -> astar
    boya = qty("boya")
    if boya > 0 and "astar" not in kinds:
        add("ASTAR", "", boya, "boya alanı kadar astar (duvar)", "astar")
    # 2) kat planı oturumu -> tavan; şap ve döşeme kaplaması yalnız seçili mahallerde (lobi, vitrin…)
    fps = _plan_footprints(project, session, drawings)
    # aynı kat birden çok paftada (kat planı + yerleşim planı, iki çatı katı paftası): kot / kat sırası bazında en büyük alan
    fps_u = _unique_floor_footprints(fps)
    floor = sum(fp["area"] * max(1, fp["storey_count"]) for fp in fps_u if not fp["basement"])
    if floor > 0 and "tavan_siva_boya" not in kinds:
        above = [f for f in fps_u if not f["basement"]]
        src = ", ".join(f"{fp['drawing']} {fp['area']:,.0f} m²" for fp in above[:4]) + ("…" if len(above) > 4 else "")
        add("TAVAN_SIVA_BOYA", "", floor, f"kat oturumu × kat sayısı ({src}); bodrum (otopark) hariç, asma tavanlı mahalleri düşün", "tavan")
    base_area = sum(fp["area"] * max(1, fp["storey_count"]) for fp in fps_u if fp["basement"])
    if base_area > 0 and "tavan_siva_boya" not in kinds:
        ask("tavan_bodrum", f"Bodrum katlarının tavanı ({base_area:,.0f} m²) sıva-boya listesine alınmadı (otopark / depo). Gerekiyorsa elle ekleyin.", "optional")
    # ıslak hacimler: mahal adından (WC / BANYO / DUŞ / ISLAK / LAVABO / TUVALET) yer + duvar seramiği ve sürme izolasyon
    wet_rooms = []
    for d in drawings:
        mult = max(1, d.storey_count or 1)
        for r in (d.rooms or []):
            name = str(r.get("name") or "")
            if WET_ROOM.search(name):
                wet_rooms.append((name, float(r.get("area_m2") or 0.0), mult))
    wet_area = sum(a * m for _, a, m in wet_rooms)
    if wet_area > 0:
        wet_h = float(params.get("wet_wall_h") or 2.2)
        # çevre çizimde yok: kare mahal varsayımı 4·√alan (not düşülür); kapı boşluğu 0,9 × 2,1 düşülür
        wall = sum((4 * (a ** 0.5) * wet_h - 0.9 * min(wet_h, 2.1)) * m for _, a, m in wet_rooms)
        if "seramik_zemin" not in kinds:
            add("SERAMIK_ZEMIN", "", wet_area, f"ıslak hacim mahal alanları ({len(wet_rooms)} mahal)", "islak")
        if "seramik_duvar" not in kinds:
            add("SERAMIK_DUVAR", "", max(wall, 0.0), f"ıslak hacim çevresi × {wet_h:g} m − kapı boşluğu (çevre 4·√alan varsayımı)", "islak")
        if "surme_izolasyon" not in kinds:
            add("SURME_IZOLASYON", "", wet_area + sum(4 * (a ** 0.5) * 0.3 * m for _, a, m in wet_rooms),
                "ıslak hacim zemini + 30 cm etek", "islak")
    fin = finish_area(project, drawings, params)
    if fin["area"] > 0:
        if "sap" not in kinds:
            # kalınlık mahal notundan okunduysa her kalınlık kendi kalemi olur; okunamayan alan tek kaleme düşer
            for sc in fin["by_screed"]:
                if sc["area"] <= 0:
                    continue
                def kaynak(src_code: str, detail: str, n: int = 0) -> str:
                    return {"rooms": f"mahal notundan ({n} mahal)", "drawing": detail,
                            "param": "proje parametresi (siz girdiniz)",
                            "default": "VARSAYILAN — çizimde yazmıyor"}[src_code]
                src = kaynak(sc["source"], sc["detail"], len(sc["rooms"]))
                if sc.get("also"):
                    a = sc["also"]
                    src += f"; {a['area']:,.0f} m²'si {kaynak(a['source'], a['detail'], len(sc['rooms']))}"
                add("SAP", f"{sc['cm']:g}", sc["area"] * sc["cm"] / 100.0,
                    f"{sc['area']:,.0f} m² × {sc['cm']:g} cm; kalınlık: {src}", "sap", sc["source"])
        if "doseme_kaplama" not in kinds and not any(k in kinds for k in ("seramik_zemin", "laminat", "epoksi")):
            for g in fin["by_finish"]:
                rooms = ", ".join(g["rooms"][:4]) + ("…" if len(g["rooms"]) > 4 else "")
                add(g["code"], g["spec"], g["area"],
                    f"{g['area']:,.0f} m² — tip mahal notundan: “{'; '.join(g['texts'][:2])}” ({rooms})", "kaplama", "rooms")
            if fin["untyped_area"] > 0:
                add("DOSEME_KAPLAMA", "", fin["untyped_area"],
                    f"{fin['untyped_area']:,.0f} m² — mahal notunda kaplama tipi yazmıyor; tip seçin (seramik / parke / epoksi)", "kaplama")
    if fin["source"] == "none":
        ask("kaplama_alani", "Şap / döşeme kaplaması için alan yok: planda mahal alanı yazısı (LOBİ 45 m²) bulunamadı ya da seçili mahal "
                            "türleri (" + ", ".join(fin["keywords"]) + ") geçmiyor. Proje parametrelerinden mahal türlerini ya da alanı elle girin.")
    elif fin["excluded"]:
        ask("kaplama_disi", f"Şap / kaplama dışı bırakılan mahaller ({fin['excluded_area']:,.0f} m²): " + ", ".join(fin["excluded"][:8])
                            + ("…" if len(fin["excluded"]) > 8 else "") + " — kiracı işi değilse mahal türlerine ekleyin.", "optional")
    # 3) temel -> su yalıtımı, grobeton, koruma şapı
    found_area = 0.0
    found_kots: list[float] = []
    found_thick: list[float] = []
    for d in drawings:
        if d.discipline == DEFAULT_DISCIPLINE:
            fnd = [e for e in _included_elements(d, session) if e.etype == "foundation"]
            found_area += sum((e.area or 0.0) for e in fnd)
            if fnd and d.kot is not None:
                found_kots.append(float(d.kot))
            found_thick += [float(e.thickness) for e in fnd if e.thickness]
    if found_area > 0:
        if "temel_su_yalitimi" not in kinds and "su_yalitim_membran" not in kinds:
            add("TEMEL_SU_YALITIMI", "", found_area, f"temel alanı {found_area:,.0f} m² (radye / sürekli temel)", "temel_yalitim")
        lean = lean_concrete_cm(project, drawings, params)
        if "grobeton" not in kinds:
            t = lean["cm"]
            add("GROBETON", f"{t:g}", found_area * t / 100.0,
                f"temel alanı × {t:g} cm; kalınlık: "
                + ("VARSAYILAN — çizimde yazmıyor" if lean["source"] == "default" else lean["detail"]),
                "grobeton", lean["source"])
        if "koruma_sapi" not in kinds:
            add("KORUMA_SAPI", "5", found_area, "temel yalıtımı üstü koruma şapı 5 cm", "koruma_sapi")
        params = {**params, "lean_concrete_cm": lean["cm"]}      # kazi / geri dolgu aynı kalınlığı kullansın
        exc_d = excavation_depth(project, drawings, params, min(found_kots) if found_kots else None,
                                 max(found_thick) if found_thick else 0.0)
        depth = exc_d["m"]
        if exc_d["source"] == "default" and depth > 0:
            ask("kazi_derinligi", f"Kazı derinliği çizimden okunamadı, {depth:g} m VARSAYILDI (temel alanı {found_area:,.0f} m² ile "
                                  "çarpılıyor — metrajı doğrudan etkiler). Kesitte tabii zemin / kazı tabanı kotu varsa o paftayı yükleyin, "
                                  "yoksa proje parametrelerinden derinliği girin.")
        if depth > 0 and "kazi" not in kinds:
            margin = float(params.get("excavation_margin") or 1.0)
            exc = found_area * depth * margin
            add("KAZI", f"{depth*100:.0f}", exc,
                f"temel alanı {found_area:,.0f} m² × derinlik {depth:g} m × şev / çalışma payı {margin:g}; derinlik: "
                + ("VARSAYILAN — çizimde yazmıyor" if exc_d["source"] == "default" else exc_d["detail"]),
                "kazi", exc_d["source"])
            found_conc = sum(it.quantity for it in items if it.kind == "beton" and it.group == "foundation")
            lean = float(params.get("lean_concrete_cm") or 0.0) / 100.0 * found_area
            # bodrumlu yapıda çukuru bodrum yapısı doldurur: geri dolgu yalnız çevre şeridi
            basement_vol = sum(fp["area"] * max(1, fp["storey_count"]) * float(fp.get("storey_height") or 0.0)
                               for fp in fps_u if fp["basement"])
            back = exc - found_conc - lean - basement_vol
            if back > 0:
                add("GERI_DOLGU", "", back, f"kazı {exc:,.0f} m³ − temel betonu {found_conc:,.0f} m³ − grobeton {lean:,.0f} m³"
                    + (f" − bodrum hacmi {basement_vol:,.0f} m³" if basement_vol else ""), "geri_dolgu")
        if "drenaj" not in kinds:
            ask("drenaj", f"Temel var ({found_area:,.0f} m²): perimetre drenajı (drenaj borusu + levha) gerekiyorsa ekleyin.", "optional")
    # 4) çatı
    ra = roof_area(project, session, items, drawings, params)
    for z in ra["zones"]:
        if z["source"] == "conflict":
            ask("cati_bolge_cakisma", f"Çatıda {z['area']:,.0f} m²'lik bölgenin içinde birden çok sistem yazıyor "
                                      f"({', '.join(z['conflict'])}): hangisi geçerli? Elemanlar sayfasından seçin.")
    bos = [z for z in ra["zones"] if z["source"] == "layer"]
    if bos and any(z["source"] == "note" for z in ra["zones"]):
        ask("cati_bolge_yazisiz", f"Çatıda {len(bos)} bölgenin ({sum(z['area'] for z in bos):,.0f} m²) içinde sistem yazısı yok; "
                                  "katmanın kalemiyle ölçüldü — başka sistemse Elemanlar sayfasından seçin.", "optional")
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
    facade_work = kinds & (facade_kinds - {"cephe_brut"})
    if fa["gross"] > 0 and facade_work and "is_iskelesi" not in kinds:
        add("IS_ISKELESI", "", fa["gross"], f"cephe brüt alanı ({fa['detail']}); mantolama / boya / kaplama için tek iskele (ÇŞB 15.185.1013)", "iskele")
    openings = qty("pencere") + qty("dograma")
    evidence = merge_materials([d.materials or {} for d in drawings])
    layer_names = {l.get("name", "").upper() for d in drawings for l in (d.layers or [])}
    has_sove = "sove" in kinds or "SOVE" in evidence or any("SÖVE" in n or "SOVE" in n for n in layer_names)
    if openings > 0 and not has_sove:
        ask("sove_denizlik", f"{openings:,.0f} adet pencere / doğrama var: söve, denizlik ve kat silmesi çizimde yok. Cephede varsa "
                             "(görünüşte katman eşleyerek ya da elle) ekleyin.", "optional")
    if (qty("pencere") > 0 or qty("dograma") > 0) and "cam" not in kinds:
        ask("cam", "Pencere / doğrama adedi var ama cam m² yok (ölçü etiketi ya da poz listesinde boyut yok); doğrama fiyatı camı kapsamıyorsa ekleyin.", "optional")
    # Ölçüsü okunamayan doğrama: **adedi biliniyor**, yalnız boyutu yok. Kalem kaybolmaz (doğrama ve kasa
    # adetten çıkar) ama camı ve ölçüye bağlı alt işleri (ölçülü körkasa, denizlik) hesaplanamaz.
    # Kavisli / kemerli doğrama: kemer kuşağında taşıyıcı profil, boardex ve taşyünü olur. Kavis yüksekliği
    # çizimde yazmadığı için kemer çevresi hesaplanamaz — miktar uydurulmaz, kalem eksik olarak bildirilir.
    kavisli = _curved_joinery(drawings, session)
    if kavisli:
        ask("kavisli_dograma", f"{sum(kavisli.values()):g} adet kavisli / kemerli doğrama var "
                               f"({', '.join(f'{k} {v:g}' for k, v in sorted(kavisli.items()))}): kemer taşıyıcı profili, "
                               f"boardex ve taşyünü keşifte yok. Kemer yüksekliği çizimde yazmadığı için miktar "
                               f"hesaplanamadı; görünüşten ölçüp elle girin.", "required")
    olcusuz = _sizeless_joinery(items)
    if olcusuz:
        n = sum(olcusuz.values())
        liste = ", ".join(f"{k} {v:g} adet" for k, v in sorted(olcusuz.items(), key=lambda kv: -kv[1]))
        ask("dograma_olcusu", f"{n:g} adet doğramanın ölçüsü çizimde bulunamadı ({liste}). Adetleri keşifte var ama "
                              f"camı ve ölçüye bağlı alt işleri hesaplanamadı; ölçüleri doğrama paftasından girin.", "required")
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
# Dış hat kabul edilebilmesi için içini dolduran geometrinin en az payı. Döşemeli kat planında ~1,0,
# yalnız duvarı olan mimari planda ~0,10; dağınık parçaların kabuğunda binde birler mertebesinde kalır.
FOOTPRINT_MIN_FILL = 0.04


def footprint_polygon(elements, spaces: list[dict] | None = None):
    """Bina oturumunun dış hat çokgeni (shapely Polygon) ya da None.

    Alan / çevre ve cephe yönleri **aynı** çokgenden türemeli; iki ayrı yerde ayrı kurallarla hesaplanırsa
    kenar toplamı çevreyi tutmaz (ölçüldü: 40 m kenar, 163 m çevre).

    **En güvenilir kaynak mahal sınırlarıdır**: mimarın kendi çizdiği mahal çokgenlerinin birleşimi
    katın planının ta kendisidir (`parser/spaces.py`; alanı mahal yazısındaki alanla doğrulanmıştır).
    Mahal yoksa taşıyıcı / duvar geometrisinin dış hattına düşülür."""
    from shapely import concave_hull
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if spaces:
        try:
            u = unary_union([g for _, g in _space_polys(spaces)])
            u = u.buffer(FACADE_GAP_CLOSE, join_style=2).buffer(-FACADE_GAP_CLOSE, join_style=2)
            parts = [Polygon(g.exterior) for g in (list(u.geoms) if u.geom_type == "MultiPolygon" else [u])
                     if g.geom_type == "Polygon" and not g.is_empty]
            if parts:
                return max(parts, key=lambda g: g.area)
        except Exception:
            pass
    polys = [Polygon(e.points).buffer(0) for e in elements
             if e.etype in ("slab", "beam", "column", "shear_wall", "wall") and len(e.points or []) >= 3]
    polys = [g for g in polys if not g.is_empty and g.is_valid and g.area > 1e-4]
    if len(polys) < 3:
        return None
    try:
        u = unary_union(polys)
        u = u.buffer(FACADE_GAP_CLOSE, join_style=2).buffer(-FACADE_GAP_CLOSE, join_style=2)
        dolu = float(u.area)
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
    # Dış hat gerçekten bir bina mı, yoksa dağınık parçaların etrafına çizilmiş bir kabuk mu? Gerçek
    # bir katta döşeme / duvar geometrisi oturumun kayda değer bir kısmını doldurur. Mimarın planın
    # ikinci bir kopyasını yanına çizdiği paftada (gerçek projede ölçüldü) kabuk iki kopyayı birden
    # sarıyor ve 2.500 m2'lik kat 44.000 m2 çıkıyordu — tavan, cephe ve iskele metrajını mertebe olarak
    # kaydıran hata. Savunulamayan bir dış hat üretmektense hiç üretmemek doğrudur.
    if big.area > 0 and dolu / big.area < FOOTPRINT_MIN_FILL:
        return None
    return big


def building_footprint(elements, spaces: list[dict] | None = None) -> "tuple[float, float] | None":
    """Kat planının bina oturumu: (alan m², dış çevre m). Önce mahal sınırları, yoksa taşıyıcı geometri."""
    g = footprint_polygon(elements, spaces)
    return (float(g.area), float(g.exterior.length)) if g is not None else None


# Cephe yönleri: dış hattın her kenarı, dışa bakan normaline göre dört yönden birine yazılır. Çizimin kuzeyi
# bilinmediği için yönler **çizim eksenidir** (+X sağ, +Y yukarı); hangi cephenin "ön" olduğunu kullanıcı söyler.
FACADE_SIDES = ("+X", "-X", "+Y", "-Y")
SIDE_LABEL = {"+X": "Sağdaki cephe (+X)", "-X": "Soldaki cephe (−X)",
              "+Y": "Üstteki cephe (+Y)", "-Y": "Alttaki cephe (−Y)"}


def footprint_sides(elements, spaces: list[dict] | None = None) -> dict[str, float]:
    """Bina dış hattının kenar uzunluklarını dört yöne dağıtır: {"+X": m, "-X": m, "+Y": m, "-Y": m}.

    Her kenarın dışa bakan normali hangi eksene yakınsa o yöne yazılır; eğik kenar iki yöne bileşenleriyle
    paylaştırılır. Dik kenarlarda dört yönün toplamı dış çevreye **eşittir** — hesabın kendi sağlaması budur.

    Eğik kenarda izdüşümlerin toplamı kenarın boyundan büyüktür (45°'de 1,41 katı): eğik bir yüzey iki
    görünüşte birden yer alır, bu bir hata değil geometrinin kendisidir. Fazlalık `egik_fazla` ile ayrıca
    bildirilir ki toplam çevreyi aştığında sebebi belli olsun."""
    import math
    from shapely.geometry import Polygon
    big = footprint_polygon(elements, spaces)
    if big is None:
        return {}
    ring = list(big.exterior.coords)
    if len(ring) < 4:
        return {}
    # Dış halka saat yönünün tersine ise dışa normal (dy, -dx)'tir; tersse (-dy, dx).
    isaret = 1.0 if Polygon(ring).exterior.is_ccw else -1.0
    out = {k: 0.0 for k in FACADE_SIDES}
    egik = 0.0
    for a, b in zip(ring, ring[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        nx, ny = isaret * dy / L, -isaret * dx / L      # dışa bakan birim normal
        out["+X" if nx > 0 else "-X"] += abs(nx) * L
        out["+Y" if ny > 0 else "-Y"] += abs(ny) * L
        egik += L * max(abs(nx) + abs(ny) - 1.0, 0.0)    # eğik kenarın iki yönde birden sayılan payı
    out["egik_fazla"] = round(egik, 2)
    return {k: round(v, 2) for k, v in out.items()}


def _unique_floor_footprints(fps: list[dict]) -> list[dict]:
    """Aynı katı temsil eden paftalardan (kot ya da kat sırası aynı) en büyük oturumlu olan alınır."""
    from .parser.levels import floor_rank
    best: dict[object, dict] = {}
    for fp in fps:
        kot = kot_from_label(fp["drawing"])
        key = ("kot", kot) if kot else ("rank", floor_rank(fp["drawing"]))
        if key[1] is None:
            key = ("name", fp["drawing"])
        if key not in best or fp["area"] > best[key]["area"]:
            best[key] = fp
    return list(best.values())


def _plan_footprints(project: Project, session: Session, drawings: list[Drawing]) -> list[dict]:
    """Kat planlarının (statik kalıp ya da mimari) bina oturumu: aynı kat için statik varsa mimari sayılmaz.
    Bodrum / temel paftaları cephe için atlanır (yer altı).

    Aynı kat eşleşmesi **blok içinde** yapılır: C1'in +6.00 kalıp planı, C2'nin +6.00 mimari planını elemez.
    Ortak (blok = "") çizimler yalnız ortak planları eler — bodrum ve zemin gibi birleşik katlar."""
    out = []
    labels_struct = set()
    for d in drawings:
        if d.discipline == DEFAULT_DISCIPLINE:
            els = _included_elements(d, session)
            if not any(e.etype in ("column", "shear_wall") for e in els):
                continue
            fp = building_footprint(els)
            if fp and fp[0] >= 10:
                labels_struct.add((d.block or "", kot_from_label(d.label)))
                out.append({"drawing": d.label or d.filename, "drawing_id": d.id, "block": d.block or "",
                            "area": round(fp[0], 2), "perimeter": round(fp[1], 2), "sides": footprint_sides(els),
                            "storey_height": storey_height_of(project, d), "storey_count": d.storey_count,
                            "basement": "BODRUM" in (d.label or "").upper(), "source": "structural"})
    for d in drawings:
        if d.discipline == "architectural":
            els = _included_elements(d, session)
            if not any(e.etype == "wall" for e in els):
                continue
            if kot_from_label(d.label) and (d.block or "", kot_from_label(d.label)) in labels_struct:
                continue
            fp = building_footprint(els, d.spaces)
            if fp and fp[0] >= 10:
                out.append({"drawing": d.label or d.filename, "drawing_id": d.id, "block": d.block or "",
                            "area": round(fp[0], 2), "perimeter": round(fp[1], 2),
                            "sides": footprint_sides(els, d.spaces),
                            "storey_height": storey_height_of(project, d), "storey_count": d.storey_count,
                            "basement": "BODRUM" in (d.label or "").upper(),
                            "source": "spaces" if d.spaces else "architectural"})
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
    out = {"gross": 0.0, "net": 0.0, "source": "none", "detail": "", "glass": round(glass, 2), "per_drawing": [],
           "sides": {k: 0.0 for k in FACADE_SIDES}}
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
            for yon, m in (fp.get("sides") or {}).items():
                if yon in FACADE_SIDES:
                    out["sides"][yon] += m * fp["storey_height"] * max(1, fp["storey_count"])
        if total > 0:
            out.update(gross=total, source="estimated",
                       detail="kat planı dış hattı (kolon / perde / duvar) çevresi × kat yüksekliği × kat sayısı (tahmin; elle düzeltilebilir)")
    out["gross"] = round(out["gross"], 2)
    out["net"] = round(max(out["gross"] - glass, 0.0), 2)
    # Yön yön net: cam hangi cephede olduğu bilinmediği için brüt payıyla dağıtılır — bu bir kabuldür,
    # kalemin notunda yazar. (Doğrama pozları proje toplamıdır, konumları cepheye bağlanamaz.)
    toplam_yon = sum(out["sides"].values())
    if toplam_yon > 0:
        olcek = out["gross"] / toplam_yon          # kenar toplamı eğik cephede çevreyi aşar; brüte oranla
        out["sides"] = {k: round(v * olcek, 2) for k, v in out["sides"].items()}
        out["sides_net"] = {k: round(max(v - glass * v / out["gross"], 0.0), 2) if out["gross"] else 0.0
                            for k, v in out["sides"].items()}
    else:
        out["sides_net"] = {k: 0.0 for k in FACADE_SIDES}
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
        kind = sys_item.code.lower()
        # Cephe yön yön ayrılır: her cephenin kendi işi, kendi iskelesi, kendi teslim sırası vardır.
        # Yön ayrımı çıkmazsa (dış hat okunamadı) tek satır kalır.
        yonler = [(k, v) for k, v in (fa.get("sides_net") or {}).items() if v > 0]
        if len(yonler) >= 2:
            cam_notu = (f"; cam ({fa['glass']:,.0f} m²) cephelere brüt payıyla dağıtıldı — hangi doğramanın "
                        f"hangi cephede olduğu poz listesinden bilinmiyor" if fa["glass"] > 0 else "")
            for yon, net in sorted(yonler, key=lambda kv: -kv[1]):
                brut = fa["sides"][yon]
                out.append(BoqItem(key=f"{kind}:{slug(yon)}", kind=kind, group=slug(yon),
                                   label=f"{sys_item.name} — {SIDE_LABEL[yon]}", unit=sys_item.unit, quantity=net,
                                   discipline=f"ksf:{sys_item.discipline}", kind_label=sys_item.name,
                                   discipline_label=catalog.discipline_name(sys_item.discipline),
                                   notes=[f"Net {net:,.0f} m² = brüt {brut:,.0f} m² − cam payı; kaynak: {fa['detail']}{cam_notu}"],
                                   detail={"facade_source": fa["source"], "facade_side": yon,
                                           "gross_m2": round(brut, 2),
                                           "evidence": {TAHMIN if fa["source"] == "estimated" else TURETILDI: round(net, 3)}}))
        else:
            note = f"Miktar = net cephe alanı ({fa['gross']:,.0f} m² brüt − {fa['glass']:,.0f} m² cam); kaynak: {fa['detail']}"
            out.append(BoqItem(key=f"{kind}:*", kind=kind, group="*", label=sys_item.name,
                               unit=sys_item.unit, quantity=fa["net"], discipline=f"ksf:{sys_item.discipline}", kind_label=sys_item.name,
                               discipline_label=catalog.discipline_name(sys_item.discipline), notes=[note],
                               detail={"facade_source": fa["source"],
                                       "evidence": {TAHMIN if fa["source"] == "estimated" else TURETILDI: round(fa["net"], 3)}}))
    return out


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
    # Aynı sistem birden çok satıra bölünmüş olabilir (cephe yön yön: ön / arka / sağ / sol). Sistem paneli
    # tek sistem görmeli: miktarlar toplanır, satırlar "parcalar" olarak taşınır.
    birlesik: dict[str, BoqItem] = {}
    parcalar: dict[str, list[dict]] = {}
    for it in items:
        sys_item = catalog.get(it.kind)
        if not sys_item or not sys_item.is_system:
            continue
        parcalar.setdefault(sys_item.code, []).append(
            {"key": it.key, "label": it.label, "quantity": round(it.quantity, 3),
             "side": it.detail.get("facade_side", "")})
        var = birlesik.get(sys_item.code)
        if var is None:
            birlesik[sys_item.code] = it.model_copy(deep=True) if hasattr(it, "model_copy") else copy.deepcopy(it)
        else:
            var.quantity += it.quantity
    for it in birlesik.values():
        sys_item = catalog.get(it.kind)
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
                    "components": comps, "missing": missing, "parcalar": parcalar.get(sys_item.code, []),
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


def price_book(session: Session, scope: str) -> dict[str, list[PriceBookItem]]:
    """Fiyat bankası satırları anahtara göre (proje bağımsız; bkz. cost/pricebook.py)."""
    out: dict[str, list[PriceBookItem]] = {}
    for r in session.exec(select(PriceBookItem).where(PriceBookItem.scope == scope)).all():
        out.setdefault(r.key, []).append(r)
    return out


def ensure_price_items(project: Project, items: list[BoqItem], session: Session) -> list[PriceItem]:
    """Keşifteki her kalem için işçilik satırı; girilmemiş değerler fiyat bankasından doldurulur."""
    existing = {p.key: p for p in session.exec(select(PriceItem).where(PriceItem.project_id == project.id))}
    book = price_book(session, "labor")
    # ÇŞB / firma birim fiyat listesi: kalemin poz numarasından eşleşir, malzeme + işçiliğin yerine geçer.
    poz_book = {r.poz: r for r in session.exec(select(PriceBookItem).where(PriceBookItem.scope == "poz")) if r.poz}
    poz_of = {it.key: it.poz for it in items if it.poz}
    poz_birim_uyusmaz: list[tuple[str, str, str, str]] = []
    changed = False
    for d in default_price_items(items):
        item = existing.get(d.key)
        if item is None:
            item = PriceItem(project_id=project.id, key=d.key, name=d.name, unit=d.unit)
            existing[d.key] = item
            changed = True
        # poz bedeli: kaleme özeldir (her kalemin kendi pozu vardır), genel satıra yazılmaz
        poz = poz_of.get(d.key, "")
        pr = poz_book.get(poz) if poz else None
        # scope="poz" satırında bedel unit_price alanındadır (her şey dahil birim fiyat).
        # Birim uyuşmazlığı sessizce geçilemez: demir keşifte kg, ÇŞB pozunda ton'dur (1000 kat fark).
        if pr and (pr.unit_price or 0) > 0 and not (item.poz_price or 0) > 0 \
                and "poz_price" not in (item.set_fields or []):
            from .cost.pozbook import unit_factor
            f = unit_factor(d.unit, pr.unit)
            if f is None:
                poz_birim_uyusmaz.append((poz, d.name, d.unit, pr.unit))
            else:
                item.poz_price = float(pr.unit_price) * f
                changed = True
        # banka değerleri türün genel satırına yazılır; kaleme özel satırlar boş kalıp genel satırdan devralır
        row = book_lookup(book, d.key) if d.key.endswith(":*") else None
        if row is None:
            session.add(item)
            continue
        for f in ("labor_price", "hours_per_unit", "crew_size"):
            # kullanıcının açıkça girdiği (0 dahil) değere dokunulmaz; boş kalanlar bankadan gelir
            if not (getattr(item, f) or 0) > 0 and f not in (item.set_fields or []) and (getattr(row, f) or 0) > 0:
                setattr(item, f, float(getattr(row, f)))
                changed = True
        session.add(item)
    if changed:
        session.commit()
    if poz_birim_uyusmaz:
        ensure_price_items.son_uyari = [
            f"{poz}: liste birimi '{pb}', keşif birimi '{kb}' ({ad}) — çevrilemediği için poz bedeli uygulanmadı"
            for poz, ad, kb, pb in poz_birim_uyusmaz]
    else:
        ensure_price_items.son_uyari = []
    order = {k: i for i, k in enumerate(KIND_ORDER)}
    return sorted(existing.values(), key=lambda p: (order.get(p.key.split(":")[0], 99), "*" not in p.key, p.name))


def ensure_material_prices(project: Project, items: list[BoqItem], session: Session) -> list[MaterialPrice]:
    """Keşifteki her ürün için (C30/37 beton, Ø12 demir, Ytong 20 cm…) fiyat satırı; kullanıcı doldurur.

    Ürün adı parametreye bağlıdır (beton sınıfı değişince ad da değişir): var olan satırın adı güncellenir.
    Ürün fiyatı boşsa, ürünü kullanan kalemlerin **ürün öncesi** malzeme fiyatı (PriceItem.unit_price) devralınır;
    böylece eski projelerde girilmiş fiyatlar kaybolmaz."""
    params = project_params(project)
    existing = {m.key: m for m in session.exec(select(MaterialPrice).where(MaterialPrice.project_id == project.id))}
    old = {p.key: p for p in session.exec(select(PriceItem).where(PriceItem.project_id == project.id))}
    book = price_book(session, "material")
    lines = material_lines(items, params)
    changed = False

    def inherited(ln) -> tuple[float, str]:
        """Ürünü kullanan kalemlerin eski malzeme fiyatı (kaleme özel > türün genel satırı)."""
        for it in ln.items:
            o = old.get(it["key"])
            if o and (o.unit_price or 0) > 0:
                return float(o.unit_price), (o.brand or "")
        for it in ln.items:
            o = old.get(f"{it['key'].split(':')[0]}:*")
            if o and (o.unit_price or 0) > 0:
                return float(o.unit_price), (o.brand or "")
        return 0.0, ""

    for ln in lines:
        m = existing.get(ln.key)
        if m is None:
            m = MaterialPrice(project_id=project.id, key=ln.key, name=ln.name, unit=ln.unit)
            existing[ln.key] = m
            changed = True
        elif m.name != ln.name or m.unit != ln.unit:
            m.name, m.unit = ln.name, ln.unit
            changed = True
        if not (m.unit_price or 0) > 0:
            price, brand = inherited(ln)
            if price <= 0:
                row = book_lookup(book, ln.key)      # fiyat bankası (proje bağımsız ürün fiyatları)
                if row is not None and (row.unit_price or 0) > 0:
                    price, brand = float(row.unit_price), (row.brand or "")
            if price > 0:
                m.unit_price = price
                m.brand = m.brand or brand
                changed = True
        session.add(m)
    if changed:
        session.commit()
    order = {ln.key: i for i, ln in enumerate(lines)}
    return sorted(existing.values(), key=lambda m: (order.get(m.key, 9999), m.name))


def to_material_data(m: MaterialPrice) -> MaterialData:
    return MaterialData(m.key, m.name, m.unit, m.unit_price or 0.0, m.brand or "")


def to_price_data(p: PriceItem) -> PriceData:
    return PriceData(p.key, p.name, p.unit, p.unit_price or 0.0, p.labor_price or 0.0, p.brand or "",
                     p.hours_per_unit or 0.0, p.crew_size or 0.0, tuple(p.set_fields or []),
                     poz_price=p.poz_price or 0.0)


def project_cost(project: Project, session: Session) -> tuple[list[QuantityLine], dict, dict, list[BoqItem], dict]:
    lines, summary, info = project_quantities(project, session)
    items = project_boq(project, session, summary)
    prices = ensure_price_items(project, items, session)
    materials = ensure_material_prices(project, items, session)
    params = project_params(project)
    cost = compute_cost(items, [to_price_data(p) for p in prices], project.vat_rate,
                        hours_per_day=float(params.get("work_hours_per_day") or 8.0),
                        materials=[to_material_data(m) for m in materials], params=params)
    return lines, summary, info, items, cost


def boq_payload(items: list[BoqItem]) -> dict:
    return boq_summary(items)


def project_quality(project, session, items, summary, cost=None):
    """Same evidence for API and exported reports, without mutating project data."""
    from .quality import build_quality
    from .planset import plan_check, PLAN_TYPE_BY_CODE
    drawings = list(session.exec(select(Drawing).where(Drawing.project_id == project.id)))
    elements = list(session.exec(select(Element).join(Drawing).where(Drawing.project_id == project.id)))
    blocks = project_blocks(project, drawings)
    check = plan_check(drawings, project.plan_set, blocks["blocks"], blocks["missing"])
    quality = build_quality(drawings, elements, items, summary, project.params or {}, check, cost)
    # Güven dağılımı: her kalemin rozeti `BoqItem.confidence` ile zaten API ve Excel'e gidiyor;
    # burada keşfin tamamı için tek cümle üretilir ("Metrajın %78'i çizimden ölçüldü …").
    from .confidence import distribution
    quality["confidence"] = distribution(items)
    heights = storey_heights(project, drawings)
    for d in drawings:
        pt = PLAN_TYPE_BY_CODE.get(d.plan_type)
        if pt and not pt.analyze:
            continue
        h = heights["per_drawing"].get(d.id)
        if not h:
            continue
        # Kaynak değerin kendisinden okunur: proje H'si girilmiş olsa da uygulanmamış olabilir (değişken katlı bina).
        src_txt = h.get("source", "")
        source = ("default" if src_txt == "varsayılan"
                  else "user" if src_txt in ("çizime girildi", "projeye girildi", "parametre")
                  else "drawing")
        quality["assumptions"].append({"key": f"storey_height:{d.id}", "label": f"{d.label or d.filename} — kat yüksekliği (m)",
                                      "value": h["height"], "source": source})
        if source != "user":
            quality["issues"].append({"code": "storey_height", "severity": "review", "drawing_id": d.id,
                                      "drawing": d.label or d.filename,
                                      "message": f"Kat yüksekliği {h['height']:g} m ({h['source']}); ilgili kesit ve katla eşleşmesini kontrol edin."})
    quality["issues"].extend(_storey_height_override(project, drawings, elements))
    # Kat sayısı: sorulmadan çizimden türetildi. Her paftanın sayısı ve KAYNAK CÜMLESİ rapora girer;
    # çıkarılamayan pafta "varsayım" olarak işaretlenir. Bu, bugüne kadar rapordan tamamen kaçan ve
    # metrajı mertebe olarak kaydıran varsayımın görünür olduğu tek yerdir.
    from .derive import storey_counts
    sc = storey_counts(project, drawings)
    for d in drawings:
        v = sc["per_drawing"].get(d.id)
        if not v or PLAN_TYPE_BY_CODE.get(d.plan_type) and not PLAN_TYPE_BY_CODE[d.plan_type].analyze:
            continue
        quality["assumptions"].append({"key": f"storey_count:{d.id}",
                                       "label": f"{d.label or d.filename} — temsil ettiği kat sayısı",
                                       "value": v["value"], "source": v["kind"], "detail": v["source"]})
    for w in sc["warnings"]:
        quality["issues"].append({"code": w["code"], "severity": w["severity"], "drawing_id": None,
                                  "drawing": None, "message": w["message"]})
    quality["storey_count"] = {"total": sc["total"], "levels": sc["levels"], "unowned": sc["unowned"]}
    if any(w["severity"] == "blocking" for w in sc["warnings"]):
        quality["status"] = "incomplete"
        quality["label"] = "Eksik / kontrol gerekli"
    # Döşeme kalınlığı: kolon / perde / kiriş net yükseklikleri ve duvar yüksekliği buna bağlı. Planda
    # ölçüm varsa proje parametresi değil o kullanılır; ölçüm yoksa varsayım olduğu söylenir.
    from .derive import slab_thicknesses
    _els: dict[int, list] = {}
    for e in elements:
        _els.setdefault(e.drawing_id, []).append(e)
    st = slab_thicknesses(project, drawings, lambda d: _els.get(d.id, []))
    quality["assumptions"].append({"key": "slab_thickness", "label": "Döşeme kalınlığı (m)",
                                   "value": round(st["effective"], 3), "source": st["kind"],
                                   "detail": st["source"]})
    for w in st["warnings"]:
        quality["issues"].append({"code": "slab_thickness_default", "severity": "review",
                                  "drawing_id": None, "drawing": None, "message": w})
    # Kapsam sahipliği: hangi miktar hangi paftadan sayıldı, ikinci paftada ne düştü, ne eklendi
    els_by_id: dict[int, list] = {}
    for e in elements:
        if e.included:
            els_by_id.setdefault(e.drawing_id, []).append(e)
    scope = scope_resolution(project, drawings, els_by_id)
    quality["scope"] = scope.to_dict()
    for n in scope.notes:
        quality["issues"].append({"code": f"scope_{n.kind}", "severity": n.severity, "drawing_id": n.drawing_id or None,
                                  "drawing": n.drawing or None, "message": n.message})
    # Sonucu ikinci bir yoldan sına: bağımsız kanıtlarla çelişen bir sayı "eksik" değil, **yanlış** olabilir.
    from .selfcheck import build as selfcheck_build
    rapor = selfcheck_build(summary, elements, project_rebar_mix(project, session, drawings))
    quality["selfcheck"] = rapor.to_dict()
    for c in rapor.celisen:
        quality["issues"].append({"code": "selfcheck_conflict", "severity": "blocking", "drawing_id": None,
                                  "drawing": None,
                                  "message": f"{c.ad} — {c.kapsam}: {c.aciklama} (bağımsızlık: {c.bagimsizlik})"})
    if rapor.celisen:
        quality["status"] = "incomplete"
        quality["label"] = "Eksik / kontrol gerekli"
    return quality


def _tr(v: float) -> str:
    """İşaretli, binlik ayracı nokta olan Türkçe sayı: 1497.0 -> "+1.497"."""
    return f"{v:+,.0f}".replace(",", ".")


def _storey_height_override(project, drawings, elements=None) -> list[dict]:
    """Projeye girilen H ile çizimin kotları çelişiyorsa ne olduğunu bildirir.

    İki ayrı durum vardır ve karıştırılmamalıdır:

    **(a) H uygulanmadı.** Kotlar kat kat değişiyorsa tek bir H hiçbir katta doğru olamaz; `storey_heights`
    çizimin kotlarını esas alır. Burada düzeltilecek bir şey yoktur, yalnız kullanıcının girdiği sayının
    neden kullanılmadığı ve bunun miktara etkisi yazılır (bilgi notu).

    **(b) H uygulandı ama bazı paftalarda kotla uyuşmuyor.** Yükseklikler sabit görünüyor (yayılım küçük),
    o yüzden kullanıcının kararı korunur; fark m³ / m² olarak ölçülüp bildirilir ve tek tıkla düzeltme sunulur.
    """
    from types import SimpleNamespace
    h = float(project.storey_height or 0)
    if h <= 0:
        return []
    auto = storey_heights(SimpleNamespace(storey_height=0.0), drawings)["per_drawing"]
    uygulandi = storey_heights(project, drawings)["source"] == "parametre"
    by_drawing: dict[int, list] = {}
    for e in (elements or []):
        by_drawing.setdefault(e.drawing_id, []).append(e)
    farkli, d_beton, d_kalip = [], 0.0, 0.0
    for d in drawings:
        if d.storey_height and d.storey_height > 0:
            continue                      # paftaya elle girilmiş: proje H'si zaten geçerli değil
        a = auto.get(d.id) or {}
        if a.get("kot") is None or abs(float(a.get("height", h)) - h) <= 0.05:
            continue
        auto_h = float(a["height"])
        farkli.append((d, auto_h))
        # (a)'da çizim değeri zaten kullanıldı: fark "H kullanılsaydı ne olurdu"nun tersidir
        delta = ((auto_h - h) if not uygulandi else (auto_h - h)) * max(1, getattr(d, "storey_count", 1) or 1)
        for e in by_drawing.get(d.id, []):
            if not e.included or e.etype not in ("column", "shear_wall"):
                continue
            d_beton += (e.area or 0.0) * delta
            # kolon: çevre × H, perde: 2 × uzunluk × H (metraj formülleri tablosu)
            yuz = 2 * (e.length or 0.0) if e.etype == "shear_wall" and e.length else (e.perimeter or 0.0)
            d_kalip += yuz * delta
    if not farkli:
        return []
    yukseklikler = [v for _, v in farkli]
    ornek = ", ".join(f"{(d.label or d.filename)[:24]} {v:g} m" for d, v in farkli[:4])
    fark_var = abs(d_beton) >= 0.5 or abs(d_kalip) >= 1.0
    if not uygulandi:
        mesaj = (f"Projeye girilen kat yüksekliği {h:g} m **kullanılmadı**: çizimden okunan kotlar kat kat "
                 f"değişiyor ({min(yukseklikler):g}–{max(yukseklikler):g} m), tek bir H hiçbir katta doğru "
                 f"olamaz. Her pafta kendi kotundan hesaplandı ({ornek}).")
        if fark_var:
            mesaj += (f" {h:g} m uygulansaydı kolon + perde betonu {_tr(-d_beton)} m³, "
                      f"kalıbı {_tr(-d_kalip)} m² olurdu.")
        mesaj += " Bir paftanın yüksekliğini kendiniz belirlemek isterseniz o paftaya doğrudan girin."
        return [{"code": "storey_height_auto_applied", "severity": "review", "drawing_id": None,
                 "drawing": None, "message": mesaj}]
    mesaj = (f"Projeye girilen kat yüksekliği {h:g} m, {len(farkli)} paftada çizimden okunan kot farkının "
             f"yerine kullanıldı ({ornek}).")
    if fark_var:
        mesaj += (f" Kotlardan hesaplansaydı kolon + perde betonu {_tr(d_beton)} m³, "
                  f"kalıbı {_tr(d_kalip)} m² değişirdi.")
    return [{"code": "storey_height_override", "severity": "review", "drawing_id": None, "drawing": None,
             "fix": {"action": "storey_height_auto", "label": "Kat yüksekliklerini kotlardan hesapla"},
             "message": mesaj + " Proje H'sini 0 yapın (kotlardan otomatik) ya da her paftaya kendi yüksekliğini girin."}]


