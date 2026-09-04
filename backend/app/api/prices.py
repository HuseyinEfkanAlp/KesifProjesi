from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..cost.pricing import QUANTITY_KINDS
from ..db import get_session
from ..models import PriceItem
from ..services import ensure_price_items, project_quantities
from .projects import get_project

router = APIRouter(prefix="/api/projects", tags=["prices"])


class PriceIn(BaseModel):
    key: str
    unit_price: float
    name: str | None = None


@router.get("/{project_id}/prices")
def list_prices(project_id: int, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    _, summary, _ = project_quantities(p, session)
    items = ensure_price_items(p, summary, session)
    return [i.model_dump() for i in items]


@router.put("/{project_id}/prices")
def upsert_prices(project_id: int, body: list[PriceIn], session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    existing = {i.key: i for i in session.exec(select(PriceItem).where(PriceItem.project_id == p.id))}
    for pi in body:
        kind = pi.key.split(":")[0]
        if kind not in QUANTITY_KINDS:
            raise HTTPException(400, f"Geçersiz fiyat anahtarı: {pi.key}")
        item = existing.get(pi.key)
        if item is None:
            item = PriceItem(project_id=p.id, key=pi.key, name=pi.name or pi.key, unit=QUANTITY_KINDS[kind][1])
            existing[pi.key] = item
        item.unit_price = max(0.0, pi.unit_price)
        if pi.name:
            item.name = pi.name
        session.add(item)
    session.commit()
    return [i.model_dump() for i in existing.values()]
