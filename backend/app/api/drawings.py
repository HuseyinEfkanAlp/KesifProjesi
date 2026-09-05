from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import UPLOAD_DIR, get_session
from ..export.svg import render_svg
from ..models import Drawing, Element, Project
from ..parser.layer_profile import ALL_ELEMENT_TYPES, DEFAULT_DISCIPLINE, DISCIPLINES, types_for
from ..parser.loader import UNIT_SCALE, load_dxf
from ..parser.sheets import BIG_FILE_BYTES, SheetScan, crop_sheets, scan_sheets
from ..services import analyze_and_store, recompute_derived
from .projects import get_project

router = APIRouter(prefix="/api", tags=["drawings"])


def get_drawing(drawing_id: int, session: Session) -> Drawing:
    d = session.get(Drawing, drawing_id)
    if not d:
        raise HTTPException(404, "Çizim bulunamadı")
    return d


def drawing_out(d: Drawing, session: Session) -> dict:
    n = len(session.exec(select(Element.id).where(Element.drawing_id == d.id)).all())
    return {**d.model_dump(exclude={"stored_path"}), "element_count": n}


def _safe_name(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", filename)


def _check_discipline(d: str | None) -> str:
    d = (d or DEFAULT_DISCIPLINE).strip().lower()
    if d not in DISCIPLINES:
        raise HTTPException(400, f"Geçersiz disiplin: {d} (structural / architectural / electrical)")
    return d


def _create_drawing(project: Project, dest: Path, filename: str, label: str, storey_count: int,
                    unit_override: str | None, session: Session, storey_height: float | None = None,
                    discipline: str = DEFAULT_DISCIPLINE) -> Drawing:
    """Kaydedilmiş DXF için Drawing kaydı açar ve analiz eder; hata olursa dosya ve kayıt geri alınır."""
    try:
        load_dxf(dest, unit_override=unit_override)
    except Exception as ex:  # bozuk / DXF olmayan dosya
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"DXF okunamadı: {ex}")
    d = Drawing(project_id=project.id, filename=filename, stored_path=str(dest),
                label=label, storey_count=max(1, storey_count), unit_override=unit_override or None,
                storey_height=storey_height if storey_height and storey_height > 0 else None,
                discipline=discipline)
    session.add(d)
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
            "can_use_whole": size <= BIG_FILE_BYTES}


@router.post("/projects/{project_id}/drawings", status_code=201)
async def upload_drawing(project_id: int, file: UploadFile = File(...), label: str = Form(""),
                         storey_count: int = Form(1), unit_override: str | None = Form(None),
                         discipline: str = Form(DEFAULT_DISCIPLINE),
                         session: Session = Depends(get_session)):
    """DXF yükler. Dosya tek paftaysa hemen analiz edilir (201 + çizim).

    Çok paftalı (ruhsat projesi gibi bütün paftalar yan yana) ya da çok büyük dosyalarda ise dosya kaynak
    olarak saklanır ve pafta listesi döner (200 + needs_sheet_selection); kullanıcı paftaları seçince
    /drawings/from-source ile her pafta ayrı çizim olarak kırpılıp analiz edilir.
    """
    project = get_project(project_id, session)
    discipline = _check_discipline(discipline)
    if not file.filename or not file.filename.lower().endswith(".dxf"):
        raise HTTPException(400, "Yalnızca .dxf dosyaları kabul edilir. DWG dosyasını AutoCAD'de 'Farklı Kaydet' ile DXF'e çevirin.")
    if unit_override and unit_override not in UNIT_SCALE:
        raise HTTPException(400, "Birim mm, cm veya m olmalı")
    safe = _safe_name(file.filename)
    token = uuid.uuid4().hex[:10]
    src = UPLOAD_DIR / f"src_{token}_{safe}"
    with src.open("wb") as out:
        while chunk := await file.read(8 * 1024 * 1024):
            out.write(chunk)
    try:
        scan = scan_sheets(src)
    except Exception as ex:
        src.unlink(missing_ok=True)
        raise HTTPException(400, f"DXF okunamadı: {ex}")
    if scan.multi_sheet or src.stat().st_size > BIG_FILE_BYTES:
        scan.save()
        return JSONResponse(status_code=200, content={
            "needs_sheet_selection": True, "source": _source_out(src, scan),
            "sheets": [sh.to_dict() for sh in scan.sheets],
        })
    dest = UPLOAD_DIR / f"{project_id}_{token[:8]}_{safe}"
    src.rename(dest)
    d = _create_drawing(project, dest, file.filename, label or Path(file.filename).stem, storey_count,
                        unit_override or None, session, discipline=discipline)
    return drawing_out(d, session)


class SheetPick(BaseModel):
    index: int
    label: str = ""
    storey_count: int = 1
    storey_height: float | None = None   # bu katın yüksekliği (m); boş -> proje değeri
    discipline: str | None = None        # boş -> isteğin disiplini


class FromSourceIn(BaseModel):
    token: str
    sheets: list[SheetPick] = []
    whole: bool = False               # (küçük dosyalarda) tüm çizimi tek plan olarak ekle
    unit_override: str | None = None
    discipline: str = DEFAULT_DISCIPLINE


@router.get("/sources/{token}/sheets")
def source_sheets(token: str):
    src = _source_path(token)
    scan = SheetScan.load(src) or scan_sheets(src)
    return {"source": _source_out(src, scan), "sheets": [sh.to_dict() for sh in scan.sheets]}


@router.post("/projects/{project_id}/drawings/from-source", status_code=201)
def drawings_from_source(project_id: int, body: FromSourceIn, session: Session = Depends(get_session)):
    """Kaynak dosyadan seçilen paftaları kırpar, her birini ayrı çizim olarak ekleyip analiz eder."""
    project = get_project(project_id, session)
    if body.unit_override and body.unit_override not in UNIT_SCALE:
        raise HTTPException(400, "Birim mm, cm veya m olmalı")
    discipline = _check_discipline(body.discipline)
    src = _source_path(body.token)
    scan = SheetScan.load(src) or scan_sheets(src)
    orig = src.name[len(f"src_{body.token}_"):]
    created: list[Drawing] = []
    if body.whole:
        if src.stat().st_size > BIG_FILE_BYTES:
            raise HTTPException(400, "Dosya tüm çizim olarak analiz edilemeyecek kadar büyük; pafta seçin")
        dest = UPLOAD_DIR / f"{project_id}_{uuid.uuid4().hex[:8]}_{orig}"
        shutil.copyfile(src, dest)
        created.append(_create_drawing(project, dest, orig, Path(orig).stem, 1, body.unit_override, session,
                                       discipline=discipline))
    jobs = []
    seen: set[int] = set()
    for pick in body.sheets:
        if pick.index in seen:
            continue
        seen.add(pick.index)
        if not (0 <= pick.index < len(scan.sheets)):
            raise HTTPException(400, f"Geçersiz pafta indeksi: {pick.index}")
        sheet = scan.sheets[pick.index]
        dest = UPLOAD_DIR / f"{project_id}_{uuid.uuid4().hex[:8]}_pafta{pick.index + 1}_{orig}"
        jobs.append((sheet, pick, dest))
    if jobs:
        counts = crop_sheets(src, [(sh.bbox, dest) for sh, _, dest in jobs])
        for (sheet, pick, dest), n in zip(jobs, counts):
            if n == 0:
                dest.unlink(missing_ok=True)
                continue
            created.append(_create_drawing(project, dest, f"{orig} › {sheet.title}", pick.label or sheet.title,
                                           pick.storey_count, body.unit_override, session,
                                           storey_height=pick.storey_height,
                                           discipline=_check_discipline(pick.discipline or discipline)))
    if not created:
        raise HTTPException(400, "Eklenecek pafta seçilmedi")
    return [drawing_out(d, session) for d in created]


@router.get("/projects/{project_id}/drawings")
def list_drawings(project_id: int, session: Session = Depends(get_session)):
    get_project(project_id, session)
    return [drawing_out(d, session) for d in session.exec(select(Drawing).where(Drawing.project_id == project_id))]


@router.get("/drawings/{drawing_id}")
def read_drawing(drawing_id: int, session: Session = Depends(get_session)):
    return drawing_out(get_drawing(drawing_id, session), session)


class DrawingPatch(BaseModel):
    label: str | None = None
    storey_count: int | None = None
    storey_height: float | None = None   # 0 / None -> proje değeri kullanılır
    unit_override: str | None = None   # "" -> otomatik
    discipline: str | None = None      # değişirse yeniden analiz


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
    for k, v in data.items():
        setattr(d, k, v)
    session.add(d)
    session.commit()
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


@router.get("/drawings/{drawing_id}/elements")
def list_elements(drawing_id: int, session: Session = Depends(get_session)):
    get_drawing(drawing_id, session)
    els = session.exec(select(Element).where(Element.drawing_id == drawing_id).order_by(Element.etype, Element.name)).all()
    return [e.model_dump() for e in els]


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


class ElementIn(ElementPatch):
    etype: str
    count: int = 1


@router.post("/drawings/{drawing_id}/elements", status_code=201)
def add_element(drawing_id: int, body: ElementIn, session: Session = Depends(get_session)):
    """Parser'ın kaçırdığı elemanı elle ekle (ör. 6 adet S5 40/40 kolon)."""
    get_drawing(drawing_id, session)
    if body.etype not in ALL_ELEMENT_TYPES:
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
    if "etype" in data and data["etype"] not in ALL_ELEMENT_TYPES:
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
