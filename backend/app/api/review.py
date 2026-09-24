"""Metraj kontrol ekranı: keşif satırlarını onaylama, reddetme ve elle düzeltme.

Ürünün sözü "metrajı ben çıkarırım" değil, "metrajı çıkarırım ve **nereden geldiğini gösteririm,
sen onaylarsın**". Bu yüzden karar bir alan değil bir kayıttır: kim, ne zaman, hangi gerekçeyle.

Hesaplanan değer hiçbir zaman silinmez — `services.apply_reviews` elle girilen miktarı uygularken
programdan çıkan sayıyı `review["computed"]` içinde saklar.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import QuantityOverride
from ..services import REVIEW_STATUSES
from .projects import get_project

router = APIRouter(prefix="/api/projects", tags=["review"])


class ReviewIn(BaseModel):
    item_key: str
    status: str | None = None          # onaylandi | kontrol | reddedildi
    quantity: float | None = None      # elle miktar; null = hesaplanan kullanılsın
    computed: float | None = None      # değiştirildiği andaki hesaplanan değer (karşılaştırma için)
    reason: str = ""
    author: str = ""


def _out(r: QuantityOverride) -> dict:
    return {"item_key": r.item_key, "status": r.status, "quantity": r.quantity, "computed": r.computed,
            "reason": r.reason, "author": r.author,
            "updated_at": r.updated_at.isoformat() if r.updated_at else ""}


@router.get("/{project_id}/review")
def read_reviews(project_id: int, session: Session = Depends(get_session)):
    get_project(project_id, session)
    rows = session.exec(select(QuantityOverride).where(QuantityOverride.project_id == project_id)).all()
    return {"rows": [_out(r) for r in rows],
            "counts": {s: sum(1 for r in rows if r.status == s) for s in REVIEW_STATUSES}}


@router.put("/{project_id}/review")
def upsert_review(project_id: int, body: ReviewIn, session: Session = Depends(get_session)):
    """Bir keşif satırının kararını yazar. Aynı satıra tekrar yazmak kaydı günceller."""
    get_project(project_id, session)
    key = (body.item_key or "").strip()
    if not key:
        raise HTTPException(400, "Kalem anahtarı boş olamaz")
    if body.status and body.status not in REVIEW_STATUSES:
        raise HTTPException(400, f"Durum şunlardan biri olmalı: {', '.join(REVIEW_STATUSES)}")
    if body.quantity is not None and body.quantity < 0:
        raise HTTPException(400, "Miktar negatif olamaz")
    row = session.exec(select(QuantityOverride)
                       .where(QuantityOverride.project_id == project_id,
                              QuantityOverride.item_key == key)).first()
    if row is None:
        row = QuantityOverride(project_id=project_id, item_key=key)
    if body.status:
        row.status = body.status
    row.quantity = body.quantity
    if body.computed is not None:
        row.computed = body.computed
    row.reason = body.reason or ""
    # Kararı kimin verdiği oturumdan gelir; istemci ayrıca ad yazdıysa o korunur.
    from ..auth import current
    k = current()
    row.author = body.author or (k.name or k.email if k else "")
    row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(row)


@router.delete("/{project_id}/review/{item_key:path}", status_code=204)
def delete_review(project_id: int, item_key: str, session: Session = Depends(get_session)):
    """Kararı kaldırır: satır yeniden hesaplanan değere ve "kontrol" durumuna döner."""
    get_project(project_id, session)
    row = session.exec(select(QuantityOverride)
                       .where(QuantityOverride.project_id == project_id,
                              QuantityOverride.item_key == item_key)).first()
    if row is not None:
        session.delete(row)
        session.commit()
