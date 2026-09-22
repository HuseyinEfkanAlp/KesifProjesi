"""İş kuyruğu: uzun süren analiz web isteğinin içinde beklemez.

**Neden gerekli:** 177 MB'lık bir ruhsat dosyasında kırpma + analiz 6 dakika sürüyor. Bugün bu
yükleme isteğinin içinde çalışıyor; tarayıcı, vekil sunucu ve yük dengeleyici o kadar beklemez.
İnternetten kullanan biri için bu, "yükledim ve site dondu" demektir.

**Sözleşme:** yükleme bir **iş kaydı** açar ve hemen döner. İstemci `GET /api/jobs/{id}` ile
ilerlemeyi okur; iş bitince sonucu (oluşan çizimler, alım raporu) aynı kayıttan alır.

**Altyapı seçimi — kasıtlı olarak basit:** veritabanı tablosu + arka plan iş parçacığı. Celery/RQ
bir Redis kurulumu ve ayrı bir süreç ister; bu aşamada kazandıracağı tek şey çok sunuculu
dağıtımdır ve henüz tek sunucu var. Arayüz (`enqueue` / `run_pending`) aynı kaldığı sürece
altına sonradan gerçek bir kuyruk konabilir.

⚠ İş parçacığı **kendi veritabanı oturumunu** açar ve kiracı bağlamını `tenancy.use_company` ile
yeniden kurar: `ContextVar` iş parçacığına özeldir, isteğin bağlamı oraya taşınmaz.
"""
from __future__ import annotations

import threading
import traceback
from datetime import datetime
from typing import Any, Callable

from sqlmodel import Session, select

from . import db
from .models import Job

# ⚠ Motor `db.engine` üzerinden GEÇ okunur, içe aktarmada yakalanmaz: test ortamı (ve ileride
# ayrı bir işçi süreci) motoru değiştiriyor; bağlamak, işlerin yanlış veritabanına yazılması demek.
# İşçi iş parçacığını kendiliğinden başlatmayı kapatmak için: AUTO_START = False (testler böyle
# yapar; işler `run_pending` ile denetimli çalışır).
AUTO_START = True


def _engine():
    return db.engine

# Durumlar. "kuyrukta" ile "calisiyor" ayrı tutulur: kullanıcıya "sıra bekliyor" ile "işleniyor"
# farklı şeyler söyler ve bekleme süresi tahmini buna dayanır.
QUEUED, RUNNING, DONE, FAILED = "kuyrukta", "calisiyor", "bitti", "hata"
ACTIVE = (QUEUED, RUNNING)

# İş türü -> çalıştırıcı. Kayıt `register` ile yapılır; jobs.py hiçbir iş türünü kendisi bilmez,
# böylece api katmanına bağımlı olmaz.
_RUNNERS: dict[str, Callable[[Session, Job], dict]] = {}
# Aynı anda çalışan iş sayısı: analiz CPU ve bellek yoğun (177 MB dosyada ~3 GB), paralel
# çalıştırmak makineyi kilitler. Tek şerit, sıra beklemekten iyidir.
_lock = threading.Lock()
_working = threading.Event()


def register(kind: str, fn: Callable[[Session, Job], dict]) -> None:
    _RUNNERS[kind] = fn


def enqueue(session: Session, project_id: int | None, kind: str, payload: dict[str, Any],
            label: str = "", company_slug: str = "") -> Job:
    """İş kaydı açar ve arka planı dürter. Hemen döner — çağıran beklemez."""
    job = Job(project_id=project_id, kind=kind, payload=payload, label=label,
              company_slug=company_slug, status=QUEUED)
    session.add(job)
    session.commit()
    session.refresh(job)
    poke()
    return job


def progress(session: Session, job_id: int, pct: float | None = None, message: str = "") -> None:
    """İşin ilerlemesini yazar. Ayrı oturumda çalışır ki uzun işlem sırasında da görünsün."""
    with Session(_engine()) as s:
        j = s.get(Job, job_id)
        if j is None or j.status not in ACTIVE:
            return
        if pct is not None:
            j.progress = max(0.0, min(100.0, float(pct)))
        if message:
            j.message = message[:400]
        s.add(j)
        s.commit()


def _run_one(job_id: int) -> None:
    from .tenancy import use_company
    with Session(_engine()) as s:
        job = s.get(Job, job_id)
        if job is None or job.status != QUEUED:
            return
        job.status = RUNNING
        job.started_at = datetime.utcnow()
        s.add(job)
        s.commit()
        s.refresh(job)
        fn = _RUNNERS.get(job.kind)
        try:
            if fn is None:
                raise ValueError(f"Bilinmeyen iş türü: {job.kind}")
            # Kiracı bağlamı bu iş parçacığında yeniden kurulur (ContextVar taşınmaz).
            with use_company(job.company_slug or ""):
                sonuc = fn(s, job)
            job = s.get(Job, job_id)
            # Sonuç JSON sütununa yazılır: çalıştırıcılar datetime / Path gibi nesneler döndürebilir
            # (çizim kaydında `analyzed_at` var) ve bunlar doğrudan yazılamaz.
            from fastapi.encoders import jsonable_encoder
            job.result = jsonable_encoder(sonuc or {})
            job.status = DONE
            job.progress = 100.0
        except Exception as ex:                       # noqa: BLE001 — hata kullanıcıya gösterilecek
            job = s.get(Job, job_id)
            job.status = FAILED
            # Kullanıcıya tek cümle, ayrıntı kayda: "dosya açılamadı" yeterli, yığın izi değil.
            job.error = str(ex)[:500] or ex.__class__.__name__
            job.detail = traceback.format_exc()[-4000:]
        job.finished_at = datetime.utcnow()
        s.add(job)
        s.commit()


def _worker() -> None:
    """Kuyruktaki işleri sırayla çalıştırır. Kuyruk boşalınca durur; `poke` yeniden başlatır."""
    while True:
        with Session(_engine()) as s:
            job = s.exec(select(Job).where(Job.status == QUEUED).order_by(Job.created_at)).first()
            job_id = job.id if job else None
        if job_id is None:
            break
        _run_one(job_id)


def poke() -> None:
    """Kuyrukta iş varsa bir işçi başlatır. Zaten çalışıyorsa ya da AUTO_START kapalıysa bir şey yapmaz."""
    if not AUTO_START or _working.is_set():
        return
    with _lock:
        if _working.is_set():
            return
        _working.set()

    def calis():
        try:
            _worker()
        finally:
            _working.clear()
            # Son kontrolden sonra iş eklenmiş olabilir: kuyruk boş değilse kendini yeniden kur.
            with Session(_engine()) as s:
                if s.exec(select(Job).where(Job.status == QUEUED)).first():
                    poke()

    threading.Thread(target=calis, name="kesif-isci", daemon=True).start()


def run_pending(limit: int = 50) -> int:
    """Kuyruktaki işleri **bu iş parçacığında** çalıştırır (test ve tek seferlik kullanım için).
    Döner: çalıştırılan iş sayısı."""
    n = 0
    while n < limit:
        with Session(_engine()) as s:
            job = s.exec(select(Job).where(Job.status == QUEUED).order_by(Job.created_at)).first()
            job_id = job.id if job else None
        if job_id is None:
            break
        _run_one(job_id)
        n += 1
    return n


def job_out(j: Job) -> dict:
    sure = None
    if j.started_at:
        bitis = j.finished_at or datetime.utcnow()
        sure = round((bitis - j.started_at).total_seconds(), 1)
    return {"id": j.id, "project_id": j.project_id, "kind": j.kind, "label": j.label,
            "status": j.status, "progress": round(j.progress, 1), "message": j.message,
            "error": j.error, "result": j.result or {},
            "created_at": j.created_at.isoformat() if j.created_at else "",
            "started_at": j.started_at.isoformat() if j.started_at else "",
            "finished_at": j.finished_at.isoformat() if j.finished_at else "",
            "seconds": sure}
