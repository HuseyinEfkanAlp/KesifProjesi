from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Drawing, Element, PriceItem, Project
from ..parser.layer_profile import ALL_TYPES, DEFAULT_PROFILE, DISCIPLINES, TYPES_BY_DISCIPLINE, LayerProfile
from ..planset import LEVELS, PLAN_GROUPS, PLAN_TYPE_BY_CODE, PLAN_TYPES, effective_levels, plan_check
from ..quantity.boq import DEFAULT_PARAMS, KIND_META
from ..quantity.engine import DEFAULT_REBAR_RATIOS
from ..services import analyze_and_store, project_params, project_systems

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    storey_height: float = 3.0
    slab_thickness: float = 0.15
    vat_rate: float = 0.0
    rebar_ratios: dict[str, float] | None = None
    params: dict | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    storey_height: float | None = None
    slab_thickness: float | None = None
    vat_rate: float | None = None
    rebar_ratios: dict[str, float] | None = None
    params: dict | None = None      # disiplin parametreleri (duvar yüksekliği, sıva yüzü, kablo iniş payı, günlük saat)


class LayerMap(BaseModel):
    layer: str
    etype: str | None  # None -> eşlemeyi kaldır


def _clean_params(raw: dict | None) -> dict:
    """Yalnızca bilinen parametreleri saklar; sayısal alanlar float'a çevrilir, boş -> None."""
    out: dict = {}
    for k, v in (raw or {}).items():
        if k not in DEFAULT_PARAMS:
            continue
        if v in ("", None):
            out[k] = None
        else:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = v
    return out


def get_project(project_id: int, session: Session) -> Project:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadı")
    return p


def project_out(p: Project, session: Session) -> dict:
    n = len(session.exec(select(Drawing.id).where(Drawing.project_id == p.id)).all())
    ds = session.exec(select(Drawing).where(Drawing.project_id == p.id)).all()
    check = plan_check(ds, p.plan_set)
    return {**p.model_dump(), "drawing_count": n,
            "rebar_ratios": {**DEFAULT_REBAR_RATIOS, **(p.rebar_ratios or {})},
            "params": project_params(p),
            "plan_check": {"missing_required": check["missing_required"], "present": check["present"],
                           "total_required": check["total_required"], "complete": check["complete"],
                           "warnings": check["warnings"]}}


@router.get("")
def list_projects(session: Session = Depends(get_session)):
    return [project_out(p, session) for p in session.exec(select(Project).order_by(Project.created_at.desc()))]


@router.post("", status_code=201)
def create_project(body: ProjectIn, session: Session = Depends(get_session)):
    p = Project(**body.model_dump(exclude={"rebar_ratios", "params"}), rebar_ratios=body.rebar_ratios or {},
                params=_clean_params(body.params), layer_profile={})   # yalnızca kullanıcı eşlemeleri saklanır
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
    if "params" in data:
        p.params = _clean_params({**(p.params or {}), **(data.pop("params") or {})})
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
            "element_types": ALL_TYPES, "disciplines": DISCIPLINES, "types_by_discipline": TYPES_BY_DISCIPLINE}


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
        if body.etype.startswith("item:"):
            from ..services import load_catalog
            from ..standard.catalog import MEASURES, normalize_code
            parts = body.etype.split(":")
            code = normalize_code(parts[1]) if len(parts) > 1 else ""
            measure = parts[2] if len(parts) > 2 and parts[2] else ""
            if not load_catalog().get(code):
                raise HTTPException(400, f"Katalogda olmayan kalem: {code}")
            if measure and measure not in MEASURES:
                raise HTTPException(400, f"Geçersiz ölçüm kuralı: {measure}")
            body.etype = f"item:{code}" + (f":{measure}" if measure else "")
        else:
            raise HTTPException(400, f"Geçersiz eleman tipi: {body.etype}")
    p.layer_profile = LayerProfile(p.layer_profile or None).with_layer(body.etype, body.layer).to_dict()
    session.add(p)
    session.commit()
    _reanalyze_all(p, session)
    return {"profile": p.layer_profile}


def _reanalyze_all(p: Project, session: Session) -> None:
    for d in session.exec(select(Drawing).where(Drawing.project_id == p.id)):
        analyze_and_store(d, p, session)


@router.get("/{project_id}/plan-check")
def read_plan_check(project_id: int, session: Session = Depends(get_session)):
    """Plan seti kontrolü: hangi plan tipleri yüklü, hangileri eksik (uyarı), hangileri bu projede yok sayıldı."""
    p = get_project(project_id, session)
    ds = session.exec(select(Drawing).where(Drawing.project_id == p.id)).all()
    return {**plan_check(ds, p.plan_set), "plan_set": effective_levels(p.plan_set), "levels": list(LEVELS)}


@router.put("/{project_id}/plan-set")
def update_plan_set(project_id: int, body: dict[str, str], session: Session = Depends(get_session)):
    """Plan tipi gerekliliklerini değiştirir: {code: required | optional | skip}. Verilmeyenler olduğu gibi kalır."""
    p = get_project(project_id, session)
    cur = dict(p.plan_set or {})
    for code, level in body.items():
        if code not in PLAN_TYPE_BY_CODE:
            raise HTTPException(400, f"Geçersiz plan tipi: {code}")
        if level not in LEVELS:
            raise HTTPException(400, f"Geçersiz gereklilik: {level} ({' / '.join(LEVELS)})")
        if PLAN_TYPE_BY_CODE[code].level == level:
            cur.pop(code, None)      # varsayılana döndü
        else:
            cur[code] = level
    p.plan_set = cur
    session.add(p)
    session.commit()
    return read_plan_check(project_id, session)


@router.get("/{project_id}/systems")
def read_systems(project_id: int, session: Session = Depends(get_session)):
    """Projedeki katmanlı sistemler ve bileşen kararları (projede yazıyor / yok / elle eklendi)."""
    p = get_project(project_id, session)
    return project_systems(p, session)


class ComponentDecision(BaseModel):
    include: bool | None = None   # None: karar silinir (kanıta döner)
    spec: str | None = None


@router.put("/{project_id}/systems")
def update_systems(project_id: int, body: dict[str, dict[str, ComponentDecision]], session: Session = Depends(get_session)):
    """Bileşen kararlarını günceller: {sistem_kodu: {bileşen_kodu: {include, spec}}}. Verilmeyenler olduğu gibi kalır."""
    from ..services import load_catalog
    p = get_project(project_id, session)
    cat = load_catalog()
    cur = {k: dict(v) for k, v in (p.systems or {}).items()}
    for sys_code, comps in body.items():
        sys_item = cat.get(sys_code)
        if not sys_item or not sys_item.is_system:
            raise HTTPException(400, f"Katmanlı sistem değil: {sys_code}")
        valid = {c["code"] for c in sys_item.components}
        bucket = cur.setdefault(sys_item.code, {})
        for comp_code, dec in comps.items():
            from ..standard.catalog import normalize_code
            code = normalize_code(comp_code)
            if code not in valid:
                raise HTTPException(400, f"{sys_item.code} sisteminde bileşen yok: {code}")
            entry = dict(bucket.get(code) or {})
            if dec.include is None and dec.spec is None:
                bucket.pop(code, None)
                continue
            if dec.include is not None:
                entry["include"] = dec.include
            if dec.spec is not None:
                entry["spec"] = dec.spec.strip()
            bucket[code] = entry
        if not bucket:
            cur.pop(sys_item.code, None)
    p.systems = cur
    session.add(p)
    session.commit()
    return project_systems(p, session)


@router.get("/meta/plan-types")
def plan_types_meta():
    """Plan seti kataloğu: gruplar ve plan tipleri (başlık tanıma, disiplin önerisi, varsayılan gereklilik)."""
    return {"groups": PLAN_GROUPS, "types": [t.to_dict() for t in PLAN_TYPES], "levels": list(LEVELS)}


@router.get("/meta/disciplines")
def disciplines_meta():
    """Arayüz için: disiplinler, eleman tipleri, keşif türleri ve varsayılan parametreler."""
    return {"disciplines": DISCIPLINES, "types_by_discipline": TYPES_BY_DISCIPLINE,
            "kinds": {k: {"label": v[0], "unit": v[1], "discipline": v[2]} for k, v in KIND_META.items()},
            "default_params": DEFAULT_PARAMS}
