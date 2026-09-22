from __future__ import annotations

import re
import shutil
import time
import uuid
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import UPLOAD_DIR, get_session
from ..export.svg import render_svg
from ..models import Drawing, Element, Project
from ..parser.layer_profile import ALL_ELEMENT_TYPES, DEFAULT_DISCIPLINE, DISCIPLINES, types_for  # noqa: F401
from ..parser.analyzer import HEURISTIC_DISCIPLINES
from ..parser.blocks import detect_block, detect_with_known, normalize as normalize_block
from ..parser.dwg import convert_dwg_to_dxf, dwg_supported
from ..parser.loader import UNIT_SCALE, load_dxf
from ..intake import auto_pick_sheets, sheet_verdict
from ..parser.sheets import BIG_FILE_BYTES, Sheet, SheetScan, crop_sheets, scan_sheets
from ..parser.titleblock import TitleBlock
from ..planset import PLAN_TYPE_BY_CODE, resolve_plan
from ..quantity.grouping import annotate
from ..services import (analyze_and_store, apply_storey_counts, boq_payload, detect_params, drawing_boq,
                        load_catalog, recompute_derived, refresh_wall_areas)
from ..jobs import enqueue, job_out, progress, register
from ..tenancy import get_slug
from .projects import get_project

router = APIRouter(prefix="/api", tags=["drawings"])


def get_drawing(drawing_id: int, session: Session) -> Drawing:
    d = session.get(Drawing, drawing_id)
    if not d:
        raise HTTPException(404, "Çizim bulunamadı")
    return d


FOUND_LABELS = {**{k: v.lower() for k, v in ALL_ELEMENT_TYPES.items()}, "dograma": "doğrama pozu", "rebar": "donatı çapı"}
# Özet notu: paftayı en iyi anlatan uyarı (öncelik sırasıyla başlangıç deseni, kısa karşılığı)
NOTE_PRIORITY: list[tuple[str, str | None]] = [
    ("Bu paftada plan geometrisi yok", None),
    ("Birim '", None),
    ("Poz yazılarından", None),
    ("Doğrama poz listesi okundu", None),
    ("Kapı / pencere bulunamadı", None),
    ("Duvar katmanı var ama", None),
    ("Pencere katmanı var ama", None),
    ("Kablo katmanı var ama", None),
    ("Armatür / priz / anahtar katmanı var ama", None),
    ("Donatı metraj tablosu bulunamadı", None),
    ("Mahal alanı yazıları okundu", None),
    ("Doğrama ölçüleri okundu", None),
    ("Henüz katman eşlenmedi", "Katman eşlenmedi: Elemanlar sayfasında katmanları katalog kalemine atayın (öneriler hazır)."),
    ("Çizim birimi", None),
]


def _qty(v: float) -> str:
    """4099.2 -> '4.099', 12.4 -> '12,4' (Türkçe sayı yazımı)."""
    return f"{v:,.0f}".replace(",", ".") if v >= 100 else f"{v:.1f}".replace(".", ",")


def found_parts(elements: list[Element], catalog=None) -> list[str]:
    """'Bulunanlar' parçaları: kalem katalogda alan / uzunluk ile ölçülüyorsa miktar (4.099 m² tuğla duvar, 2.790 m kiriş),
    yoksa adet (256 kapı). Klasik duvarda (wall) uzunluk parantezde yazılır."""
    acc: dict[str, dict] = {}
    for e in elements:
        if not e.included:
            continue
        a = acc.setdefault(e.etype, {"n": 0, "length": 0.0, "area": 0.0})
        a["n"] += e.count or 1
        a["length"] += (e.length or 0.0) * (e.count or 1)
        a["area"] += (e.area or 0.0) * (e.count or 1)
    parts = []
    for et, a in sorted(acc.items(), key=lambda kv: -kv[1]["n"]):
        item = catalog.get(et.upper()) if catalog is not None and et not in ALL_ELEMENT_TYPES else None
        label = item.name.lower() if item else FOUND_LABELS.get(et, et.replace("_", " "))
        measure = item.measure if item else ""
        if measure in ("area", "wall_area", "volume") and a["area"] > 0:
            parts.append(f"{_qty(a['area'])} m² {label}")
        elif measure == "length" and a["length"] > 0:
            parts.append(f"{_qty(a['length'])} m {label}")
        elif et == "wall" and a["length"] > 0:
            parts.append(f"{a['n']} {label} ({_qty(a['length'])} m)")
        else:
            parts.append(f"{a['n']} {label}")
    return parts


def drawing_summary(d: Drawing, elements: list[Element], catalog=None) -> dict:
    """Proje sayfası özeti: durum (ok / empty / problem / untyped), bulunanlar ('4.099 m² tuğla duvar · 37 pencere'),
    tek cümlelik not. catalog: KSF kalemlerinin adı ve ölçü birimi için (yoksa tip kodu ve adet)."""
    parts = found_parts(elements, catalog)
    if d.rooms:
        parts.append(f"{len(d.rooms)} mahal alanı")
    warnings = list(d.warnings or [])
    problem = any(w.startswith("Bu paftada plan geometrisi yok") for w in warnings)
    if not d.plan_type:
        status = "untyped"
    elif problem:
        status = "problem"
    else:
        status = "ok" if parts else "empty"
    note = ""
    for prefix, short in NOTE_PRIORITY:
        hit = next((w for w in warnings if w.startswith(prefix)), None)
        if hit:
            note = short or hit
            break
    if not note and warnings:
        note = warnings[0]
    return {"status": status, "found": " · ".join(parts), "note": note[:200]}


def drawing_out(d: Drawing, session: Session, catalog=None) -> dict:
    elements = session.exec(select(Element).where(Element.drawing_id == d.id)).all()
    return {**d.model_dump(exclude={"stored_path"}), "element_count": len(elements),
            **drawing_summary(d, elements, catalog if catalog is not None else load_catalog())}


def _safe_name(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", filename)


AUTO_DISCIPLINE = "auto"


def _check_discipline(d: str | None, allow_auto: bool = False) -> str:
    d = (d or DEFAULT_DISCIPLINE).strip().lower()
    if allow_auto and d == AUTO_DISCIPLINE:
        return AUTO_DISCIPLINE
    if d not in DISCIPLINES:
        raise HTTPException(400, f"Geçersiz disiplin: {d} ({' / '.join(DISCIPLINES)})")
    return d


def _check_plan_type(code: str | None) -> str:
    code = (code or "").strip()
    if code and code not in PLAN_TYPE_BY_CODE:
        raise HTTPException(400, f"Geçersiz plan tipi: {code}")
    return code


def _resolve(discipline: str, plan_type: str | None, titles: list[str], layers: dict[str, int] | None = None) -> tuple[str, str]:
    """Disiplin ve plan tipini tamamlar: plan tipi verilmemişse başlıklardan (zayıfsa katmanlardan) tanınır;
    disiplin 'auto' ise plan tipinden gelir."""
    code, disc = resolve_plan(titles, layers, _check_plan_type(plan_type))
    if discipline == AUTO_DISCIPLINE:
        discipline = disc or DEFAULT_DISCIPLINE
    return discipline, code


# Sınıflandırma kararı `app/intake.py` içindedir (saf ve test edilebilir olsun diye);
# buradaki adlar geriye dönük uyum için korunur.
_sheet_out = sheet_verdict


def apply_titleblock(project: Project, tb: TitleBlock, session: Session) -> list[str]:
    """Ruhsat antedinden okunan proje verisini **boş** parametrelere yazar.

    Antet "MALZEME: C35-S420" der; kullanıcı bunu bugün Parametreler sayfasında elle giriyor. Okunabiliyorsa
    hazır gelsin — ama kullanıcının kendi girdiği değer asla ezilmez, yalnız boş alan doldurulur."""
    params = dict(project.params or {})
    notes: list[str] = []
    for key, val, label in (("concrete_class", tb.concrete_class, "Beton sınıfı"),
                            ("rebar_grade", tb.rebar_grade, "Donatı çeliği sınıfı")):
        if val and not str(params.get(key) or "").strip():
            params[key] = val
            notes.append(f"{label} {val}")
    # Antetin kendisi de saklanır: kat adedi ve inşaat alanı parametre değil, çapraz doğrulama kanıtıdır
    # (çizimdeki kotlardan çıkan kat sayısı antetle çelişirse `derive.storey_counts` uyarı yazar).
    if notes or (not tb.empty and not project.titleblock):
        project.params = params
        project.titleblock = tb.to_dict()
        session.add(project)
        session.commit()
    return notes


def majority_unit(verdicts: list[str | None]) -> tuple[str, int] | None:
    """Paftaların yazı yüksekliği kanıtından dosyanın birimi: en az 2 pafta ve oyların %60'ı aynı birimi demeli."""
    votes = Counter(v for v in verdicts if v)
    if not votes:
        return None
    unit, n = votes.most_common(1)[0]
    if n < 2 or n < 0.6 * sum(votes.values()):
        return None
    return unit, n


def _harmonize_units(project: Project, created: list[Drawing], session: Session) -> None:
    """Aynı dosyadan kırpılan paftalar tek birimdedir. Yazı yüksekliği kanıtı olan paftaların çoğunluğu bir birimi
    destekliyorsa, başlıktaki (yanlış) birimle kalan paftalar o birimle yeniden analiz edilir."""
    vote = majority_unit([d.unit_verdict for d in created])
    if not vote:
        return
    unit, n = vote
    for d in created:
        if d.unit == unit or d.unit_override:
            continue
        old = d.unit
        d.unit_override = unit
        analyze_and_store(d, project, session)
        d.warnings = [f"Birim '{unit}' aynı dosyadaki öteki paftalardan alındı ({n} pafta; bu paftada yazı az, başlıkta '{old}' yazıyordu)."] \
            + [w for w in d.warnings if "yazı yükseklikleri" not in w]
        session.add(d)
        session.commit()


def _refresh_openings(project: Project, session: Session) -> None:
    """Doğrama poz bilgisi (poz listesi, görünüş ölçüleri) sonradan geldiyse, kapı / pencere bulunamayan ya da ölçüsüz
    poz sayan mimari planlar bu bilgiyle yeniden analiz edilir."""
    params = detect_params(project, session)
    if not (params.poz_prefixes or params.poz_sizes):
        return
    for d in session.exec(select(Drawing).where(Drawing.project_id == project.id, Drawing.discipline == "architectural")):
        els = session.exec(select(Element).where(Element.drawing_id == d.id)).all()
        has_wall = any(e.etype == "wall" for e in els)
        openings = [e for e in els if e.etype in ("door", "window")]
        unsized = any("ölçüsü bulunamadı" in w for e in openings for w in (e.warnings or []))
        known = {p for p in {e.subtype for e in openings if e.source == "POZ_LABEL"} if p in params.poz_sizes}
        if has_wall and (not openings or (unsized and known)):
            analyze_and_store(d, project, session)


def _project_blocks(project: Project, session: Session) -> list[str]:
    """Projede şimdiye kadar tanınmış blok adları (yeni çizimin adını eşlemek için)."""
    return sorted({(d.block or "") for d in session.exec(select(Drawing).where(Drawing.project_id == project.id))} - {""})


def _detect_block(project: Project, session: Session, *texts: str) -> str:
    """Dosya adı / pafta başlığından blok; "BLOK" kelimesi yoksa projedeki bilinen adlarla eşleştirilir."""
    if b := detect_block(*texts):
        return b
    known = _project_blocks(project, session)
    for t in texts:
        if b := detect_with_known(t or "", known):
            return b
    return ""


def _create_drawing(project: Project, dest: Path, filename: str, label: str, storey_count: int,
                    unit_override: str | None, session: Session, storey_height: float | None = None,
                    discipline: str = DEFAULT_DISCIPLINE, plan_type: str = "", block: str | None = None) -> Drawing:
    """Kaydedilmiş DXF için Drawing kaydı açar ve analiz eder; hata olursa dosya ve kayıt geri alınır."""
    try:
        load_dxf(dest, unit_override=unit_override)
    except Exception as ex:  # bozuk / DXF olmayan dosya
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"DXF okunamadı: {ex}")
    # Kat sayısı çizimden türetilir (`services.apply_storey_counts`); formın varsayılanı 1 bir beyan
    # değildir. Yalnız açıkça 1'den büyük bir sayı verildiyse kullanıcının kararı sayılır ve ezilmez.
    d = Drawing(project_id=project.id, filename=filename, stored_path=str(dest),
                label=label, storey_count=max(1, storey_count), unit_override=unit_override or None,
                storey_manual=storey_count if storey_count > 1 else None,
                storey_height=storey_height if storey_height and storey_height > 0 else None,
                discipline=discipline, plan_type=plan_type,
                block=normalize_block(block) if block is not None else _detect_block(project, session, filename, label))
    session.add(d)
    if d.block and d.block not in (project.blocks or []):
        project.blocks = list(project.blocks or []) + [d.block]   # tanınan blok projeye eklenir
        session.add(project)
    session.commit()
    session.refresh(d)
    try:
        analyze_and_store(d, project, session)
    except Exception as ex:  # analiz hatası: yarım kayıt bırakma
        session.rollback()
        for e in session.exec(select(Element).where(Element.drawing_id == d.id)):
            session.delete(e)
        session.delete(d)
        session.commit()
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"Analiz sırasında hata: {type(ex).__name__}: {ex}")
    return d


# Pafta seçimi için tutulan kaynak kopyasının ömrü. Çok paftalı her yükleme dosyanın tam bir kopyasını
# `src_<token>_<ad>.dxf` olarak bırakır; kullanıcı paftaları seçtikten sonra bu kopyanın işi biter ama aynı
# dosyadan sonradan pafta eklenebilsin diye hemen silinmez. Süresi dolanlar bir sonraki yüklemede süpürülür —
# yoksa klasör sınırsız büyür (bir ölçümde 34 artık kopya, 1,9 GB).
SOURCE_TTL_HOURS = 24


def sweep_sources(ttl_hours: float = SOURCE_TTL_HOURS) -> tuple[int, int]:
    """Süresi dolmuş kaynak kopyalarını ve pafta önbelleklerini siler. (dosya sayısı, bayt) döner."""
    cutoff = time.time() - ttl_hours * 3600
    n = size = 0
    for f in list(UPLOAD_DIR.glob("src_*")):
        try:
            st = f.stat()
            if st.st_mtime >= cutoff:
                continue
            f.unlink()
        except OSError:
            continue
        n += 1
        size += st.st_size
    return n, size


def _source_path(token: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{10}", token):
        raise HTTPException(400, "Geçersiz kaynak dosya kimliği")
    found = sorted(UPLOAD_DIR.glob(f"src_{token}_*.dxf"))
    if not found:
        raise HTTPException(404, "Kaynak dosya bulunamadı; çizimi yeniden yükleyin")
    return found[0]


def _source_out(src: Path, scan: SheetScan) -> dict:
    token = src.name.split("_")[1]
    orig = src.name[len(f"src_{token}_"):]
    size = src.stat().st_size
    return {"token": token, "filename": orig, "size_mb": round(size / 1e6, 1), "entity_count": scan.entity_count,
            "can_use_whole": size <= BIG_FILE_BYTES, "unit": scan.unit or "", "suggested_unit": scan.suggested_unit or "",
            "dropped": scan.dropped, "strays": scan.strays,
            # antet (proje bilgi tablosu) pafta değildir; okunanlar proje parametresi önerisi olarak gösterilir
            "titleblock": scan.titleblock.to_dict(), "titleblock_summary": scan.titleblock.summary()}


@router.post("/projects/{project_id}/drawings", status_code=201)
def upload_drawing(project_id: int, file: UploadFile = File(...), label: str = Form(""),
                         storey_count: int = Form(1), unit_override: str | None = Form(None),
                         discipline: str = Form(AUTO_DISCIPLINE), plan_type: str = Form(""),
                         auto: bool = Form(True), background: bool | None = Form(None),
                         session: Session = Depends(get_session)):
    """DXF / DWG yükler ve analiz eder. Kullanıcıya pafta seçimi SORULMAZ.

    Tek paftalı dosya doğrudan analiz edilir (201 + çizim). Çok paftalı (ruhsat projesi gibi bütün
    paftalar yan yana) ya da büyük dosyada sistem **paftaları kendisi seçer** (`intake.auto_pick_sheets`):
    plan tipi tanınan paftalar alınır, antet / boş çerçeve / detay parçası atlanır, tipi tanınmayan büyük
    paftalar **rapora yazılır** (metraja sessizce girmeyen hiçbir şey olmamalı). Dönüş:
    201 + {"drawings": [...], "intake": {...}}.

    auto=false: eski davranış — pafta listesi döner (200 + needs_sheet_selection) ve kullanıcı
    /drawings/from-source ile seçer. Uzman görünümü bunu kullanır.

    discipline "auto" (varsayılan): plan tipi dosya adı ve çizimdeki başlıktan tanınır, disiplin ondan gelir.
    """
    project = get_project(project_id, session)
    discipline = _check_discipline(discipline, allow_auto=True)
    plan_type = _check_plan_type(plan_type)
    fname = file.filename or ""
    is_dwg = fname.lower().endswith(".dwg")
    if not (fname.lower().endswith(".dxf") or is_dwg):
        raise HTTPException(400, "Yalnızca .dxf ya da .dwg dosyaları kabul edilir.")
    if is_dwg and not dwg_supported():
        raise HTTPException(400, "DWG dönüştürücü (ODA File Converter) bu sunucuda kurulu değil. DWG dosyasını AutoCAD'de "
                                 "'Farklı Kaydet → DXF' ile çevirin ya da ODA File Converter kurun (bkz. README).")
    if unit_override and unit_override not in UNIT_SCALE:
        raise HTTPException(400, "Birim mm, cm veya m olmalı")
    safe = _safe_name(fname)
    sweep_sources()
    token = uuid.uuid4().hex[:10]
    if is_dwg:
        dwg_path = UPLOAD_DIR / f"src_{token}_{safe}"
        with dwg_path.open("wb") as out:
            shutil.copyfileobj(file.file, out, 8 * 1024 * 1024)
        safe = safe[:-4] + ".dxf"
        src = UPLOAD_DIR / f"src_{token}_{safe}"
        try:
            convert_dwg_to_dxf(dwg_path, src)
        except RuntimeError as ex:
            raise HTTPException(400, str(ex))
        finally:
            dwg_path.unlink(missing_ok=True)
        file_label = fname[:-4] + ".dxf"
    else:
        src = UPLOAD_DIR / f"src_{token}_{safe}"
        with src.open("wb") as out:
            shutil.copyfileobj(file.file, out, 8 * 1024 * 1024)
        file_label = fname
    try:
        scan = scan_sheets(src)
    except Exception as ex:
        src.unlink(missing_ok=True)
        raise HTTPException(400, f"DXF okunamadı: {ex}")
    if scan.multi_sheet or src.stat().st_size > BIG_FILE_BYTES:
        scan.save()
        if not auto:
            return JSONResponse(status_code=200, content={
                "needs_sheet_selection": True, "source": _source_out(src, scan),
                "sheets": [_sheet_out(sh) for sh in scan.sheets],
            })
        picks, rapor = auto_pick_sheets(scan)
        if not picks:
            raise HTTPException(400, "Dosyada ölçülebilir plan bulunamadı: " + rapor.note)
        # Kırpma + analiz dakikalar sürüyor (177 MB'lık dosyada 6 dakika); istek içinde beklenmez.
        # İş kaydı açılır ve hemen dönülür; istemci /api/jobs/{id} ile ilerlemeyi okur.
        if not (BACKGROUND_UPLOAD if background is None else background):
            secimler = [SheetPick(index=x["index"], discipline=x["discipline"] or discipline,
                                  plan_type=x["plan_type"] or None, storey_count=storey_count)
                        for x in picks]
            created = ingest_sheets(project, src, scan, secimler, session, file_label,
                                    unit_override or None, discipline, plan_type or None)
            return {"drawings": [drawing_out(d, session) for d in created], "intake": rapor.to_dict()}
        job = enqueue(session, project.id, "upload",
                      payload={"src": str(src), "file_label": file_label, "picks": picks,
                               "unit_override": unit_override or None, "discipline": discipline,
                               "plan_type": plan_type or None, "storey_count": storey_count,
                               "intake": rapor.to_dict()},
                      label=file_label, company_slug=get_slug())
        return JSONResponse(status_code=202, content={"job": job_out(job), "intake": rapor.to_dict()})
    dest = UPLOAD_DIR / f"{project_id}_{token[:8]}_{safe}"
    src.rename(dest)
    discipline, plan_type = _resolve(discipline, plan_type, [label, Path(fname).stem, *scan.titles], scan.layers)
    if BACKGROUND_UPLOAD if background is None else background:
        # Tek pafta da uzun sürebilir: gerçek aydınlatma planı (7 MB, 29 bin nesne) 24 saniye.
        job = enqueue(session, project.id, "analyze",
                      payload={"dest": str(dest), "file_label": file_label,
                               "label": label or Path(fname).stem, "storey_count": storey_count,
                               "unit_override": unit_override or None,
                               "discipline": discipline, "plan_type": plan_type,
                               "titleblock": scan.titleblock.to_dict()},
                      label=file_label, company_slug=get_slug())
        return JSONResponse(status_code=202, content={"job": job_out(job)})
    d = _create_drawing(project, dest, file_label, label or Path(fname).stem, storey_count,
                        unit_override or None, session, discipline=discipline, plan_type=plan_type)
    applied = apply_titleblock(project, scan.titleblock, session)
    if applied:
        d.warnings = [f"Dosyanın antedinden okundu ve boş proje parametrelerine yazıldı: {', '.join(applied)}."] + list(d.warnings)
        session.add(d)
        session.commit()
    _refresh_openings(project, session)
    apply_storey_counts(project, session)   # kat sayisi sorulmaz: cizimden turetilip kaydedilir
    session.refresh(d)
    return drawing_out(d, session)


class SheetPick(BaseModel):
    index: int
    label: str = ""
    storey_count: int = 1
    storey_height: float | None = None   # bu katın yüksekliği (m); boş -> proje değeri
    discipline: str | None = None        # boş -> isteğin disiplini ("auto": plan tipinden)
    plan_type: str | None = None         # boş -> pafta başlığından tanınır


class FromSourceIn(BaseModel):
    token: str
    sheets: list[SheetPick] = []
    whole: bool = False               # (küçük dosyalarda) tüm çizimi tek plan olarak ekle
    unit_override: str | None = None
    discipline: str = AUTO_DISCIPLINE  # "auto": her paftanın disiplini başlığından tanınan plan tipinden gelir
    plan_type: str | None = None       # whole için


@router.get("/sources/{token}/sheets")
def source_sheets(token: str):
    src = _source_path(token)
    scan = SheetScan.load(src) or scan_sheets(src)
    return {"source": _source_out(src, scan), "sheets": [_sheet_out(sh) for sh in scan.sheets]}


def ingest_sheets(project: Project, src: Path, scan: SheetScan, picks: list, session: Session,
                 orig: str, unit_override: str | None = None, discipline: str = AUTO_DISCIPLINE,
                 plan_type: str | None = None, whole: bool = False) -> list[Drawing]:
    """Seçilen paftaları kırpar, her birini ayrı çizim olarak ekleyip analiz eder.

    Hem otomatik yükleme (`upload_drawing`) hem uzman seçimi (`drawings_from_source`) buraya gelir;
    kararlar farklı, yürütme aynıdır."""
    project_id = project.id
    created: list[Drawing] = []
    if whole:
        if src.stat().st_size > BIG_FILE_BYTES:
            raise HTTPException(400, "Dosya tüm çizim olarak analiz edilemeyecek kadar büyük; pafta seçin")
        dest = UPLOAD_DIR / f"{project_id}_{uuid.uuid4().hex[:8]}_{orig}"
        shutil.copyfile(src, dest)
        disc, ptype = _resolve(discipline, plan_type, [Path(orig).stem, *scan.titles], scan.layers)
        created.append(_create_drawing(project, dest, orig, Path(orig).stem, 1, unit_override, session,
                                       discipline=disc, plan_type=ptype))
    jobs = []
    seen: set[int] = set()
    for pick in picks:
        if pick.index in seen:
            continue
        seen.add(pick.index)
        if not (0 <= pick.index < len(scan.sheets)):
            raise HTTPException(400, f"Geçersiz pafta indeksi: {pick.index}")
        sheet = scan.sheets[pick.index]
        dest = UPLOAD_DIR / f"{project_id}_{uuid.uuid4().hex[:8]}_pafta{pick.index + 1}_{orig}"
        jobs.append((sheet, pick, dest))
    if jobs:
        counts = crop_sheets(src, [(sh.bbox, dest) for sh, _, dest in jobs], neighbors=[sh.bbox for sh in scan.sheets])
        for (sheet, pick, dest), n in zip(jobs, counts):
            if n == 0:
                dest.unlink(missing_ok=True)
                continue
            disc, ptype = _resolve(_check_discipline(pick.discipline or discipline, allow_auto=True), pick.plan_type,
                                   [sheet.title if sheet.titled else "", *sheet.titles, Path(orig).stem], sheet.layers)
            created.append(_create_drawing(project, dest, f"{orig} › {sheet.title}", pick.label or sheet.title,
                                           pick.storey_count, unit_override, session,
                                           storey_height=pick.storey_height, discipline=disc, plan_type=ptype))
    if not created:
        raise HTTPException(400, "Eklenecek pafta seçilmedi")
    if not unit_override:
        _harmonize_units(project, created, session)
    applied = apply_titleblock(project, scan.titleblock, session)
    if applied:
        created[0].warnings = [f"Dosyanın antedinden okundu ve boş proje parametrelerine yazıldı: "
                               f"{', '.join(applied)}."] + list(created[0].warnings)
        session.add(created[0])
        session.commit()
    _refresh_openings(project, session)
    apply_storey_counts(project, session)   # kat sayısı sorulmaz: çizimden türetilip kaydedilir
    for d in created:
        session.refresh(d)
    return created


# Yükleme varsayılan olarak ARKA PLANDA analiz eder: 7 MB'lık bir aydınlatma planı bile istek
# içinde 24 saniye sürüyor ve bu bir web kullanıcısı için "site dondu" demektir. Boyut ayırt edici
# değil — süreyi belirleyen nesne sayısı ve hizalama araması. Senkron çalışma isteğe bağlı kalır
# (betik / toplu işlem ve testler): `background=false` ya da bu bayrak.
BACKGROUND_UPLOAD = True


def _run_upload(session: Session, job) -> dict:
    """İş kuyruğundaki çok paftalı yükleme: pafta kırpılır, analiz edilir, çizimler eklenir.

    Kendi oturumunda çalışır (jobs.py açar). Hata olursa iş "hata" durumuna düşer ve sebebi
    kullanıcıya tek cümleyle gösterilir — dosya sessizce kaybolmaz."""
    from ..api.projects import get_project as _get
    d = job.payload or {}
    src = Path(d["src"])
    if not src.exists():
        raise RuntimeError("Yüklenen dosya bulunamadı (geçici kaynak silinmiş olabilir); yeniden yükleyin.")
    project = _get(job.project_id, session)
    scan = SheetScan.load(src) or scan_sheets(src)
    secimler = [SheetPick(index=x["index"], discipline=x["discipline"] or d["discipline"],
                          plan_type=x["plan_type"] or None, storey_count=d.get("storey_count") or 1)
                for x in d["picks"]]
    progress(session, job.id, 5.0, f"{len(secimler)} pafta kırpılıp analiz edilecek")
    created = ingest_sheets(project, src, scan, secimler, session, d["file_label"],
                            d.get("unit_override"), d["discipline"], d.get("plan_type"))
    return {"drawings": [drawing_out(x, session) for x in created], "intake": d.get("intake") or {}}


def _run_analyze(session: Session, job) -> dict:
    """Tek paftalı yüklemenin analizi (kuyrukta)."""
    from ..api.projects import get_project as _get
    from ..parser.titleblock import TitleBlock
    d = job.payload or {}
    dest = Path(d["dest"])
    if not dest.exists():
        raise RuntimeError("Yüklenen dosya bulunamadı; yeniden yükleyin.")
    project = _get(job.project_id, session)
    progress(session, job.id, 10.0, "çizim analiz ediliyor")
    dr = _create_drawing(project, dest, d["file_label"], d["label"], d.get("storey_count") or 1,
                         d.get("unit_override"), session, discipline=d["discipline"], plan_type=d["plan_type"])
    applied = apply_titleblock(project, TitleBlock.from_dict(d.get("titleblock")), session)
    if applied:
        dr.warnings = [f"Dosyanın antedinden okundu ve boş proje parametrelerine yazıldı: "
                       f"{', '.join(applied)}."] + list(dr.warnings)
        session.add(dr)
        session.commit()
    _refresh_openings(project, session)
    apply_storey_counts(project, session)
    session.refresh(dr)
    return {"drawings": [drawing_out(dr, session)]}


register("upload", _run_upload)
register("analyze", _run_analyze)


@router.post("/projects/{project_id}/drawings/from-source", status_code=201)
def drawings_from_source(project_id: int, body: FromSourceIn, session: Session = Depends(get_session)):
    """Uzman seçimi: kaynak dosyadan SEÇİLEN paftaları ekler. Otomatik yükleme bunu kullanmaz."""
    project = get_project(project_id, session)
    if body.unit_override and body.unit_override not in UNIT_SCALE:
        raise HTTPException(400, "Birim mm, cm veya m olmalı")
    discipline = _check_discipline(body.discipline, allow_auto=True)
    src = _source_path(body.token)
    scan = SheetScan.load(src) or scan_sheets(src)
    orig = src.name[len(f"src_{body.token}_"):]
    created = ingest_sheets(project, src, scan, body.sheets, session, orig, body.unit_override,
                            discipline, body.plan_type, body.whole)
    return [drawing_out(d, session) for d in created]


@router.get("/projects/{project_id}/drawings")
def list_drawings(project_id: int, session: Session = Depends(get_session)):
    get_project(project_id, session)
    cat = load_catalog()
    return [drawing_out(d, session, cat) for d in session.exec(select(Drawing).where(Drawing.project_id == project_id))]


@router.get("/drawings/{drawing_id}")
def read_drawing(drawing_id: int, session: Session = Depends(get_session)):
    return drawing_out(get_drawing(drawing_id, session), session)


class DrawingPatch(BaseModel):
    label: str | None = None
    storey_count: int | None = None
    storey_height: float | None = None   # 0 / None -> proje değeri kullanılır
    unit_override: str | None = None   # "" -> otomatik
    discipline: str | None = None      # değişirse yeniden analiz
    disciplines: list[str] | None = None   # ek sezgisel disiplinler (aynı paftada mimari + elektrik); değişirse yeniden analiz
    plan_type: str | None = None       # plan seti tipi ("" -> tanımsız)
    block: str | None = None           # yapı bloğu ("C1"); "" -> ortak / tüm bina


@router.patch("/drawings/{drawing_id}")
def update_drawing(drawing_id: int, body: DrawingPatch, session: Session = Depends(get_session)):
    d = get_drawing(drawing_id, session)
    data = body.model_dump(exclude_unset=True)
    if "storey_height" in data:
        h = data.pop("storey_height")
        d.storey_height = float(h) if h and float(h) > 0 else None
    reanalyze = False
    if "unit_override" in data:
        uo = data.pop("unit_override") or None
        if uo and uo not in UNIT_SCALE:
            raise HTTPException(400, "Birim mm, cm veya m olmalı")
        reanalyze = uo != d.unit_override
        d.unit_override = uo
    if "discipline" in data:
        disc = _check_discipline(data.pop("discipline"))
        if disc != d.discipline:
            reanalyze = True
            d.discipline = disc
    if "disciplines" in data:
        extra = []
        for x in data.pop("disciplines") or []:
            x = _check_discipline(x)
            if x not in HEURISTIC_DISCIPLINES:
                raise HTTPException(400, f"Ek disiplin yalnız sezgisel disiplinlerden olabilir: {', '.join(HEURISTIC_DISCIPLINES)}")
            if x != d.discipline and x not in extra:
                extra.append(x)
        if extra != list(d.disciplines or []):
            reanalyze = True
            d.disciplines = extra
    if "plan_type" in data:
        d.plan_type = _check_plan_type(data.pop("plan_type"))
    if "block" in data:
        d.block = normalize_block(data.pop("block") or "")
    if "storey_count" in data:
        # Uzman gorunumunden elle girilen kat sayisi kullanicinin kararidir: turetme bunu bir daha ezmez.
        n = data.pop("storey_count")
        d.storey_manual = max(1, int(n)) if n else None
        d.storey_count = d.storey_manual or d.storey_count
    height_changed = "storey_height" in data and data["storey_height"] != d.storey_height
    for k, v in data.items():
        setattr(d, k, v)
    session.add(d)
    session.commit()
    if height_changed and not reanalyze:
        refresh_wall_areas(session.get(Project, d.project_id), session, [d])
    if reanalyze:
        analyze_and_store(d, session.get(Project, d.project_id), session)
    session.refresh(d)
    return drawing_out(d, session)


@router.delete("/drawings/{drawing_id}", status_code=204)
def delete_drawing(drawing_id: int, session: Session = Depends(get_session)):
    d = get_drawing(drawing_id, session)
    for e in session.exec(select(Element).where(Element.drawing_id == d.id)):
        session.delete(e)
    Path(d.stored_path).unlink(missing_ok=True)
    session.delete(d)
    session.commit()


@router.post("/drawings/{drawing_id}/reanalyze")
def reanalyze(drawing_id: int, session: Session = Depends(get_session)):
    d = get_drawing(drawing_id, session)
    analyze_and_store(d, session.get(Project, d.project_id), session)
    return drawing_out(d, session)


@router.get("/drawings/{drawing_id}/layers")
def drawing_layers(drawing_id: int, session: Session = Depends(get_session)):
    d = get_drawing(drawing_id, session)
    return {"layers": d.layers, "element_types": types_for(d.discipline or DEFAULT_DISCIPLINE), "discipline": d.discipline,
            "unit": d.unit, "unit_detected": d.unit_detected, "warnings": d.warnings}


@router.get("/drawings/{drawing_id}/boq")
def drawing_boq_out(drawing_id: int, session: Session = Depends(get_session)):
    """Paftanın metrajı: ölçülen kalemler (duvar malzeme bazında m², kapı adet, KSF kalemleri…) ve tür toplamları."""
    d = get_drawing(drawing_id, session)
    project = get_project(d.project_id, session)
    return boq_payload(drawing_boq(project, d, session))


@router.get("/drawings/{drawing_id}/elements")
def list_elements(drawing_id: int, session: Session = Depends(get_session)):
    get_drawing(drawing_id, session)
    els = session.exec(select(Element).where(Element.drawing_id == drawing_id).order_by(Element.etype, Element.name)).all()
    # grup anahtarı sunucuda hesaplanır: önizlemedeki çokgenin data-group'u ile aynı olmak zorunda
    return annotate([e.model_dump() for e in els])


@router.get("/drawings/{drawing_id}/preview.svg")
def preview_svg(drawing_id: int, width: int = 1200, session: Session = Depends(get_session)):
    d = get_drawing(drawing_id, session)
    dxf = load_dxf(d.stored_path, unit_override=d.unit_override)
    els = [e.model_dump() for e in session.exec(select(Element).where(Element.drawing_id == d.id, Element.included == True))]  # noqa: E712
    return Response(render_svg(dxf, els, width=width), media_type="image/svg+xml")


# ---------- Elemanlar ----------

class ElementPatch(BaseModel):
    etype: str | None = None
    subtype: str | None = None
    name: str | None = None
    b: float | None = None
    h: float | None = None
    thickness: float | None = None
    area: float | None = None
    length: float | None = None
    perimeter: float | None = None
    count: int | None = None
    included: bool | None = None
    meta: dict | None = None      # rebar: {"dia_mm", "weight_kg", "target", "kot"} — elle demir girişi


class ElementIn(ElementPatch):
    etype: str
    count: int = 1


@router.post("/drawings/{drawing_id}/elements", status_code=201)
def add_element(drawing_id: int, body: ElementIn, session: Session = Depends(get_session)):
    """Parser'ın kaçırdığı elemanı elle ekle (ör. 6 adet S5 40/40 kolon)."""
    get_drawing(drawing_id, session)
    if body.etype not in ALL_ELEMENT_TYPES and body.etype != "rebar":
        raise HTTPException(400, "Geçersiz eleman tipi")
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    e = Element(drawing_id=drawing_id, source="MANUAL", manual=True, confidence=1.0, layer="(elle)", **data)
    recompute_derived(e)
    session.add(e)
    session.commit()
    session.refresh(e)
    return e.model_dump()


@router.patch("/elements/{element_id}")
def update_element(element_id: int, body: ElementPatch, session: Session = Depends(get_session)):
    e = session.get(Element, element_id)
    if not e:
        raise HTTPException(404, "Eleman bulunamadı")
    data = body.model_dump(exclude_unset=True)
    if "etype" in data and data["etype"] not in ALL_ELEMENT_TYPES and data["etype"] != "rebar":
        raise HTTPException(400, "Geçersiz eleman tipi")
    geometric = {"b", "h", "length", "thickness", "etype", "subtype"} & set(data)
    for k, v in data.items():
        setattr(e, k, v)
    if geometric and not ({"area", "perimeter"} & set(data)):
        recompute_derived(e)
    if set(data) - {"included"}:
        e.manual = True
    session.add(e)
    session.commit()
    session.refresh(e)
    return e.model_dump()


@router.delete("/elements/{element_id}", status_code=204)
def delete_element(element_id: int, session: Session = Depends(get_session)):
    e = session.get(Element, element_id)
    if not e:
        raise HTTPException(404, "Eleman bulunamadı")
    session.delete(e)
    session.commit()
