"""Fiyat bankası ve tedarikçiler: proje bağımsız ürün / işçilik fiyatları.

Kullanıcı bütün ürünlerin fiyatını burada bir kez girer; yeni projede ürün ve işçilik satırları buradan
doldurulur (services.ensure_material_prices / ensure_price_items). Aynı ürüne birden çok tedarikçi fiyatı
girilebilir, geçerli fiyat seçili (preferred) satır ya da en düşük olandır.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..cost.pricebook import known_products
from ..db import get_session
from ..models import MaterialPrice, PriceBookItem, Supplier
from ..services import load_catalog

router = APIRouter(prefix="/api", tags=["pricebook"])


# ------------------------------------------------------------------ tedarikçiler

class SupplierIn(BaseModel):
    name: str
    contact: str | None = None
    phone: str | None = None
    email: str | None = None
    note: str | None = None


@router.get("/suppliers")
def list_suppliers(session: Session = Depends(get_session)):
    rows = session.exec(select(PriceBookItem)).all()
    counts: dict[int, int] = {}
    for r in rows:
        if r.supplier_id:
            counts[r.supplier_id] = counts.get(r.supplier_id, 0) + 1
    return [{**s.model_dump(), "price_count": counts.get(s.id or 0, 0)}
            for s in session.exec(select(Supplier)).all()]


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, session: Session = Depends(get_session)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Tedarikçi adı boş olamaz")
    s = Supplier(name=name, contact=(body.contact or "").strip(), phone=(body.phone or "").strip(),
                 email=(body.email or "").strip(), note=(body.note or "").strip())
    session.add(s)
    session.commit()
    session.refresh(s)
    return {**s.model_dump(), "price_count": 0}


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierIn, session: Session = Depends(get_session)):
    s = session.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Tedarikçi bulunamadı")
    if body.name is not None and body.name.strip():
        s.name = body.name.strip()
    for f in ("contact", "phone", "email", "note"):
        v = getattr(body, f)
        if v is not None:
            setattr(s, f, v.strip())
    session.add(s)
    session.commit()
    session.refresh(s)
    return s.model_dump()


@router.delete("/suppliers/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, session: Session = Depends(get_session)):
    s = session.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Tedarikçi bulunamadı")
    for r in session.exec(select(PriceBookItem).where(PriceBookItem.supplier_id == supplier_id)):
        r.supplier_id = None      # fiyat satırları kalır, tedarikçisi boşalır
        session.add(r)
    session.delete(s)
    session.commit()


# ------------------------------------------------------------------ fiyat bankası

class BookIn(BaseModel):
    key: str
    scope: str = "material"
    name: str | None = None
    unit: str | None = None
    supplier_id: int | None = None
    unit_price: float | None = None
    labor_price: float | None = None
    hours_per_unit: float | None = None
    crew_size: float | None = None
    brand: str | None = None
    note: str | None = None
    preferred: bool | None = None
    id: int | None = None            # var olan satırı güncelle; yoksa (anahtar, tedarikçi) çiftiyle bulunur


def _row_out(r: PriceBookItem, sup: dict[int, str]) -> dict:
    return {**r.model_dump(), "supplier_name": sup.get(r.supplier_id or 0, "")}


def _best(rows: list[PriceBookItem], scope: str) -> PriceBookItem | None:
    if not rows:
        return None
    pref = [r for r in rows if r.preferred]
    if pref:
        return pref[0]
    field = "unit_price" if scope == "material" else "labor_price"
    priced = [r for r in rows if (getattr(r, field) or 0) > 0]
    return min(priced, key=lambda r: getattr(r, field)) if priced else rows[0]


@router.get("/pricebook")
def get_pricebook(scope: str = "material", session: Session = Depends(get_session)):
    """Fiyat girilebilecek ürünler (ya da işçilik kalem türleri) ve her birinin tedarikçi fiyatları."""
    if scope not in ("material", "labor"):
        raise HTTPException(400, "scope: material | labor")
    cat = load_catalog()
    products = {p["key"]: dict(p) for p in known_products(cat)}
    if scope == "labor":
        # işçilik: her tür için tek satır ("<tür>:*")
        labor: dict[str, dict] = {}
        for p in products.values():
            kind = p["key"].split(":")[0]
            key = f"{kind}:*"
            if key not in labor:
                name = p["name"].split(" (tür geneli)")[0]
                labor[key] = {**p, "key": key, "name": name}
        products = labor
    else:
        # projelerde gerçekten geçen ürünler (ör. duvar_ytong:20x300) listeye eklenir
        for m in session.exec(select(MaterialPrice)).all():
            if m.key not in products:
                base = products.get(f"{m.key.split(':')[0]}:*", {})
                products[m.key] = {"key": m.key, "name": m.name, "unit": m.unit,
                                   "discipline": base.get("discipline", ""), "discipline_label": base.get("discipline_label", ""),
                                   "work_group": base.get("work_group", "ALT"), "work_group_label": base.get("work_group_label", "Altyapı / peyzaj / diğer")}
    used = {m.key for m in session.exec(select(MaterialPrice)).all()} if scope == "material" else set()
    sup = {s.id: s.name for s in session.exec(select(Supplier)).all() if s.id}
    rows_by_key: dict[str, list[PriceBookItem]] = {}
    for r in session.exec(select(PriceBookItem).where(PriceBookItem.scope == scope)).all():
        rows_by_key.setdefault(r.key, []).append(r)
        if r.key not in products:
            products[r.key] = {"key": r.key, "name": r.name or r.key, "unit": r.unit, "discipline": "",
                               "discipline_label": "", "work_group": "ALT", "work_group_label": "Altyapı / peyzaj / diğer"}
    out = []
    for key, p in products.items():
        rows = rows_by_key.get(key, [])
        best = _best(rows, scope)
        out.append({**p, "rows": [_row_out(r, sup) for r in rows],
                    "price": (best.unit_price if scope == "material" else best.labor_price) if best else 0.0,
                    "brand": best.brand if best else "", "supplier_name": sup.get((best.supplier_id or 0) if best else 0, ""),
                    "hours_per_unit": best.hours_per_unit if best else 0.0,
                    "crew_size": best.crew_size if best else 0.0,
                    "in_projects": key in used})
    return {"scope": scope, "products": out, "suppliers": list_suppliers(session)}


@router.put("/pricebook")
def upsert_pricebook(body: list[BookIn], session: Session = Depends(get_session)):
    cat = load_catalog()
    known = {p["key"]: p for p in known_products(cat)}
    project_keys = {m.key: m for m in session.exec(select(MaterialPrice)).all()}
    for b in body:
        if b.scope not in ("material", "labor"):
            raise HTTPException(400, "scope: material | labor")
        row = session.get(PriceBookItem, b.id) if b.id else None
        if row is None:
            q = select(PriceBookItem).where(PriceBookItem.key == b.key, PriceBookItem.scope == b.scope)
            q = q.where(PriceBookItem.supplier_id == b.supplier_id) if b.supplier_id else q.where(PriceBookItem.supplier_id.is_(None))
            row = session.exec(q).first()
        if row is None:
            meta = known.get(b.key)
            mp = project_keys.get(b.key)
            if meta is None and mp is None and b.scope == "material" and not b.name:
                raise HTTPException(400, f"Bilinmeyen ürün: {b.key}")
            row = PriceBookItem(key=b.key, scope=b.scope, supplier_id=b.supplier_id,
                                name=b.name or (meta or {}).get("name") or (mp.name if mp else b.key),
                                unit=b.unit or (meta or {}).get("unit") or (mp.unit if mp else ""))
        for f in ("unit_price", "labor_price", "hours_per_unit", "crew_size"):
            v = getattr(b, f)
            if v is not None:
                setattr(row, f, max(0.0, float(v)))
        for f in ("brand", "note", "name", "unit"):
            v = getattr(b, f, None)
            if v is not None:
                setattr(row, f, v.strip())
        if b.supplier_id is not None:
            row.supplier_id = b.supplier_id
        if b.preferred is not None:
            row.preferred = bool(b.preferred)
            if row.preferred:      # aynı anahtarda tek seçili satır
                for other in session.exec(select(PriceBookItem).where(PriceBookItem.key == row.key,
                                                                      PriceBookItem.scope == row.scope)).all():
                    if other.id != row.id:
                        other.preferred = False
                        session.add(other)
        row.updated_at = datetime.utcnow()
        session.add(row)
    session.commit()
    return get_pricebook(body[0].scope if body else "material", session)


@router.delete("/pricebook/{row_id}", status_code=204)
def delete_pricebook_row(row_id: int, session: Session = Depends(get_session)):
    row = session.get(PriceBookItem, row_id)
    if not row:
        raise HTTPException(404, "Fiyat satırı bulunamadı")
    session.delete(row)
    session.commit()
