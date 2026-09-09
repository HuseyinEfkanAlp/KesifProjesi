from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..cost.materials import (CONCRETE_CLASSES, CONCRETE_TYPES, FORMWORK_MATERIALS, REBAR_GRADES,
                              material_lines, material_of)
from ..db import get_session
from ..models import MaterialPrice, PriceItem
from ..parser.layer_profile import DISCIPLINES
from ..quantity.boq import KIND_META, WORK_GROUPS
from ..standard.rules import work_group_of
from ..services import ensure_material_prices, ensure_price_items, load_catalog, project_boq, project_params
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
    clear: list[str] | None = None        # bu alanlar "girilmedi"ye döner (genel satır uygulanır)


def price_out(p: PriceItem, catalog=None, boq: dict | None = None, params: dict | None = None) -> dict:
    """boq: keşif kalemi anahtarı -> BoqItem (miktar, poz, reçete ve kullandığı ürün fiyat satırına eklenir)."""
    d = p.model_dump()
    kind = p.key.split(":")[0]
    d["kind"] = kind
    d["is_general"] = p.key.endswith(":*")
    it_b = (boq or {}).get(p.key)
    d["quantity"] = round(it_b.quantity, 3) if it_b else None
    d["poz"] = it_b.poz if it_b else ""
    d["recipe"] = bool(it_b and it_b.detail.get("recipe"))
    m = material_of(it_b, params or {}) if it_b else None
    d["material_key"], d["material_name"] = m if m else ("", "")
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
    d["work_group"] = work_group_of(d["discipline"])
    d["work_group_label"] = WORK_GROUPS.get(d["work_group"], d["work_group"])
    return d


@router.get("/{project_id}/prices")
def list_prices(project_id: int, session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    items = project_boq(p, session)
    cat = load_catalog()
    boq = {i.key: i for i in items}
    params = project_params(p)
    return [price_out(i, cat, boq, params) for i in ensure_price_items(p, items, session)]


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
        set_fields = set(item.set_fields or [])
        for f in ("unit_price", "labor_price", "hours_per_unit", "crew_size"):
            v = getattr(pi, f)
            if v is not None:
                setattr(item, f, max(0.0, float(v)))
                set_fields.add(f)          # 0 da açık bir değerdir (yalnız malzeme, işçilik yok gibi)
        for f in pi.clear or []:
            if f in ("unit_price", "labor_price", "hours_per_unit", "crew_size"):
                setattr(item, f, 0.0)
                set_fields.discard(f)
        item.set_fields = sorted(set_fields)
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


# --------------------------------------------------------------- malzeme (ürün) fiyatları

class MaterialIn(BaseModel):
    key: str
    unit_price: float | None = None
    brand: str | None = None
    note: str | None = None


@router.get("/{project_id}/materials")
def list_materials(project_id: int, session: Session = Depends(get_session)):
    """Keşifteki ürünler (C30/37 beton, Ø12 demir, Ytong 20 cm…): malzeme fiyatı bunlara girilir."""
    p = get_project(project_id, session)
    items = project_boq(p, session)
    params = project_params(p)
    lines = {ln.key: ln for ln in material_lines(items, params)}
    out = []
    for m in ensure_material_prices(p, items, session):
        ln = lines.get(m.key)
        out.append({**m.model_dump(), "kind": m.key.split(":")[0],
                    "kind_label": ln.kind_label if ln else m.key.split(":")[0],
                    "work_group": ln.work_group if ln else "", "work_group_label": ln.work_group_label if ln else "",
                    "quantity": round(ln.quantity, 3) if ln else 0.0,
                    "items": ln.items if ln else [],
                    "in_boq": ln is not None})
    return out


@router.put("/{project_id}/materials")
def upsert_materials(project_id: int, body: list[MaterialIn], session: Session = Depends(get_session)):
    p = get_project(project_id, session)
    items = project_boq(p, session)
    params = project_params(p)
    lines = {ln.key: ln for ln in material_lines(items, params)}
    existing = {m.key: m for m in session.exec(select(MaterialPrice).where(MaterialPrice.project_id == p.id))}
    for mi in body:
        m = existing.get(mi.key)
        if m is None:
            ln = lines.get(mi.key)
            if ln is None:
                raise HTTPException(400, f"Geçersiz ürün anahtarı: {mi.key}")
            m = MaterialPrice(project_id=p.id, key=ln.key, name=ln.name, unit=ln.unit)
            existing[mi.key] = m
        if mi.unit_price is not None:
            m.unit_price = max(0.0, float(mi.unit_price))
        if mi.brand is not None:
            m.brand = mi.brand.strip()
        if mi.note is not None:
            m.note = mi.note.strip()
        session.add(m)
    session.commit()
    return list_materials(project_id, session)


@router.get("/{project_id}/material-options")
def material_options(project_id: int, session: Session = Depends(get_session)):
    """Malzeme seçim listeleri: beton sınıfları, donatı sınıfı, kalıp malzemesi ve sınıf atanabilen eleman tipleri."""
    get_project(project_id, session)
    return {"concrete_classes": CONCRETE_CLASSES, "concrete_types": CONCRETE_TYPES,
            "rebar_grades": REBAR_GRADES, "formwork_materials": FORMWORK_MATERIALS}
