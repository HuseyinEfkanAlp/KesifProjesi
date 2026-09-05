from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import Session

from ..db import get_session
from ..export.excel import build_workbook
from ..services import boq_payload, project_cost, project_params
from .projects import get_project

router = APIRouter(prefix="/api/projects", tags=["reports"])


@router.get("/{project_id}/cost")
def read_cost(project_id: int, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    _, summary, _, items, cost = project_cost(p, session)
    return {"summary": summary, "boq": boq_payload(items), "cost": cost}


@router.get("/{project_id}/cost.xlsx")
def download_excel(project_id: int, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    lines, summary, info, items, cost = project_cost(p, session)
    data = build_workbook({"name": p.name, "storey_height": p.storey_height, "slab_thickness": p.slab_thickness,
                           **project_params(p)},
                          lines, summary, cost, element_info=info, boq=[i.to_dict() for i in items])
    fname = re.sub(r"[^A-Za-z0-9_-]+", "_", p.name) or "proje"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fname}_kesif_maliyet.xlsx"'})
