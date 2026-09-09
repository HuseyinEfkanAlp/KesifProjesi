from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..models import Drawing
from ..parser.rebar_mix import normalize as normalize_mix
from ..services import boq_payload, project_boq, project_params, project_quantities, project_rebar_mix
from .projects import get_project

router = APIRouter(prefix="/api/projects", tags=["quantities"])


@router.get("/{project_id}/quantities")
def read_quantities(project_id: int, session: Session = Depends(get_session)):
    """Statik metraj (beton/kalıp/demir satırları) + tüm disiplinlerin keşif listesi."""
    p = get_project(project_id, session)
    lines, summary, info = project_quantities(p, session)
    items = project_boq(p, session, summary)
    return {
        "summary": summary,
        "lines": [{**ln.to_dict(), **{k: v for k, v in info.get(ln.element_id, {}).items() if k != "warnings"},
                   "warnings": info.get(ln.element_id, {}).get("warnings", [])} for ln in lines],
        "boq": boq_payload(items),
        "params": {"storey_height": p.storey_height, "slab_thickness": p.slab_thickness, **project_params(p)},
        "rebar_mix": rebar_mix_out(p, session),
    }


def rebar_mix_out(p, session: Session) -> dict:
    """Çizimdeki donatı yazılarından okunan çap dağılımı (eleman tipi -> [{dia_mm, share}]).

    Oran demiri (donatı tablosu olmayan elemanlar) bu dağılıma göre çaplara bölünür; kullanıcı hangi nervürlü
    demirin nereden geldiğini burada görür."""
    from sqlmodel import select

    drawings = session.exec(select(Drawing).where(Drawing.project_id == p.id)).all()
    mix = project_rebar_mix(p, session, drawings)
    out: dict[str, list[dict]] = {}
    for etype, raw in mix.items():
        n = normalize_mix(raw)
        if n:
            out[etype] = [{"dia_mm": d, "share": round(v, 4)} for d, v in n.items()]
    return out
