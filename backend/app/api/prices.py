from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import PriceItem
from ..parser.layer_profile import DISCIPLINES
from ..quantity.boq import KIND_META
from ..services import ensure_price_items, load_catalog, project_boq
from .projects import get_project

router = APIRouter(prefix="/api/projects", tags=["prices"])


class PriceIn(BaseModel):
    key: str
    unit_price: float | None = None       # malzeme ₺/birim
    labor_price: float | None = None      # işçilik ₺/birim
    brand: str | None = None
    hours_per_unit: float | None = None   # adam-saat / birim
    crew_size: float | None = None
    name: str | None = None


def price_out(p: PriceItem, catalog=None) -> dict:
    d = p.model_dump()
    kind = p.key.split(":")[0]
    d["kind"] = kind
    d["is_general"] = p.key.endswith(":*")
    if kind in KIND_META:
        d["discipline"] = KIND_META[kind][2]
        d["discipline_label"] = DISCIPLINES.get(d["discipline"], d["discipline"])
        d["kind_label"] = KIND_META[kind][0]
    else:
        catalog = catalog or load_catalog()
        it = catalog.get(kind)
        d["discipline"] = f"ksf:{it.discipline}" if it else "ksf:???"
        d["discipline_label"] = catalog.discipline_name(it.discipline) if it else "Katalog dışı"
        d["kind_label"] = it.name if it else kind
    return d


@router.get("/{project_id}/prices")
def list_prices(project_id: int, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    items = project_boq(p, session)
    cat = load_catalog()
    return [price_out(i, cat) for i in ensure_price_items(p, items, session)]


@router.put("/{project_id}/prices")
def upsert_prices(project_id: int, body: list[PriceIn], session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    existing = {i.key: i for i in session.exec(select(PriceItem).where(PriceItem.project_id == p.id))}
    cat = load_catalog()
    for pi in body:
        kind = pi.key.split(":")[0]
        cat_item = cat.get(kind) if kind not in KIND_META else None
        if kind not in KIND_META and cat_item is None:
            raise HTTPException(400, f"Geçersiz fiyat anahtarı: {pi.key}")
        item = existing.get(pi.key)
        if item is None:
            unit = KIND_META[kind][1] if kind in KIND_META else cat_item.unit
            item = PriceItem(project_id=p.id, key=pi.key, name=pi.name or pi.key, unit=unit)
            existing[pi.key] = item
        if pi.unit_price is not None:
            item.unit_price = max(0.0, pi.unit_price)
        if pi.labor_price is not None:
            item.labor_price = max(0.0, pi.labor_price)
        if pi.hours_per_unit is not None:
            item.hours_per_unit = max(0.0, pi.hours_per_unit)
        if pi.crew_size is not None:
            item.crew_size = max(0.0, pi.crew_size)
        if pi.brand is not None:
            item.brand = pi.brand.strip()
        if pi.name:
            item.name = pi.name
        session.add(item)
    session.commit()
    out = []
    for i in existing.values():
        session.refresh(i)
        out.append(price_out(i, cat))
    return out
