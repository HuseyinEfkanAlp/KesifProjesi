"""Arka plan işlerinin durumu: yükleme bitti mi, nerede kaldı, hata varsa ne?

Uzun analiz artık istek içinde beklemiyor (app/jobs.py); istemci bu uçlardan ilerlemeyi okur.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..jobs import ACTIVE, job_out
from ..models import Job
from .projects import get_project

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}")
def read_job(job_id: int, session: Session = Depends(get_session)):
    j = session.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "İş bulunamadı")
    if j.project_id is not None:
        get_project(j.project_id, session)      # kiracı süzgeci: başkasının işi görünmez
    return job_out(j)


@router.get("/projects/{project_id}/jobs")
def list_jobs(project_id: int, active: bool = False, session: Session = Depends(get_session)):
    """Projenin işleri, yenisi başta. active=true: yalnız kuyrukta / çalışan işler."""
    get_project(project_id, session)
    q = select(Job).where(Job.project_id == project_id)
    if active:
        q = q.where(Job.status.in_(ACTIVE))      # type: ignore[attr-defined]
    return [job_out(j) for j in session.exec(q.order_by(Job.created_at.desc()))]
