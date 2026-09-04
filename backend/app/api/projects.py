from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Drawing, Element, PriceItem, Project
from ..parser.layer_profile import DEFAULT_PROFILE, ALL_TYPES, LayerProfile
from ..quantity.engine import DEFAULT_REBAR_RATIOS
from ..services import analyze_and_store

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    storey_height: float = 3.0
    slab_thickness: float = 0.15
    vat_rate: float = 0.0
    rebar_ratios: dict[str, float] | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    storey_height: float | None = None
    slab_thickness: float | None = None
    vat_rate: float | None = None
    rebar_ratios: dict[str, float] | None = None


class LayerMap(BaseModel):
    layer: str
    etype: str | None  # None -> eşlemeyi kaldır


def get_project(project_id: int, session: Session) -> Project:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadı")
    return p


def project_out(p: Project, session: Session) -> dict:
    n = len(session.exec(select(Drawing.id).where(Drawing.project_id == p.id)).all())
    return {**p.model_dump(), "drawing_count": n,
            "rebar_ratios": {**DEFAULT_REBAR_RATIOS, **(p.rebar_ratios or {})}}


@router.get("")
def list_projects(session: Session = Depends(get_session)):
    return [project_out(p, session) for p in session.exec(select(Project).order_by(Project.created_at.desc()))]


@router.post("", status_code=201)
def create_project(body: ProjectIn, session: Session = Depends(get_session)):
    p = Project(**body.model_dump(exclude={"rebar_ratios"}), rebar_ratios=body.rebar_ratios or {},
                layer_profile={})   # yalnızca kullanıcı eşlemeleri saklanır; varsayılanlar kodda
    session.add(p)
    session.commit()
    session.refresh(p)
    return project_out(p, session)


@router.get("/{project_id}")
def read_project(project_id: int, session: Session = Depends(get_session)):
    return project_out(get_project(project_id, session), session)


@router.patch("/{project_id}")
def update_project(project_id: int, body: ProjectPatch, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    data = body.model_dump(exclude_unset=True)
    reanalyze = "slab_thickness" in data and data["slab_thickness"] != p.slab_thickness
    for k, v in data.items():
        setattr(p, k, v)
    session.add(p)
    session.commit()
    if reanalyze:  # varsayılan döşeme kalınlığı dedektör parametresi
        for d in session.exec(select(Drawing).where(Drawing.project_id == p.id)):
            analyze_and_store(d, p, session)
    session.refresh(p)
    return project_out(p, session)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    for d in session.exec(select(Drawing).where(Drawing.project_id == p.id)):
        for e in session.exec(select(Element).where(Element.drawing_id == d.id)):
            session.delete(e)
        session.delete(d)
    for pi in session.exec(select(PriceItem).where(PriceItem.project_id == p.id)):
        session.delete(pi)
    session.delete(p)
    session.commit()


@router.get("/{project_id}/layer-profile")
def read_profile(project_id: int, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    prof = LayerProfile(p.layer_profile or None)
    return {"profile": prof.effective(), "overrides": prof.to_dict(), "defaults": DEFAULT_PROFILE,
            "element_types": ALL_TYPES}


@router.put("/{project_id}/layer-profile")
def replace_profile(project_id: int, profile: dict[str, list[str]], session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    p.layer_profile = LayerProfile(profile).to_dict()
    session.add(p)
    session.commit()
    _reanalyze_all(p, session)
    return {"profile": p.layer_profile}


@router.post("/{project_id}/layer-profile/map")
def map_layer(project_id: int, body: LayerMap, session: Session = Depends(get_session)):
    """Tek bir katmanı bir eleman tipine atar (ya da atamayı kaldırır) ve tüm çizimleri yeniden analiz eder."""
    p = get_project(project_id, session)
    if body.etype is not None and body.etype not in ALL_TYPES:
        raise HTTPException(400, f"Geçersiz eleman tipi: {body.etype}")
    p.layer_profile = LayerProfile(p.layer_profile or None).with_layer(body.etype, body.layer).to_dict()
    session.add(p)
    session.commit()
    _reanalyze_all(p, session)
    return {"profile": p.layer_profile}


def _reanalyze_all(p: Project, session: Session) -> None:
    for d in session.exec(select(Drawing).where(Drawing.project_id == p.id)):
        analyze_and_store(d, p, session)
