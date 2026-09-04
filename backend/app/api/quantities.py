from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..services import project_quantities
from .projects import get_project

router = APIRouter(prefix="/api/projects", tags=["quantities"])


@router.get("/{project_id}/quantities")
def read_quantities(project_id: int, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    lines, summary, info = project_quantities(p, session)
    return {
        "summary": summary,
        "lines": [{**ln.to_dict(), **{k: v for k, v in info.get(ln.element_id, {}).items() if k != "warnings"},
                   "warnings": info.get(ln.element_id, {}).get("warnings", [])} for ln in lines],
        "params": {"storey_height": p.storey_height, "slab_thickness": p.slab_thickness},
    }
