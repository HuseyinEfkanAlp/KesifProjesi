"""Revizyon takibi: aynı paftanın yenisi gelince eskisi hesaptan çıkar.

Mimar planı revize eder, kullanıcı yeni dosyayı yükler ("A2 BLOK - 04.01.24" → "A2 BLOK - 21.11.2025").
Eskisi hesapta kalırsa aynı katın duvarları iki kez sayılır. Kullanıcıdan "eskisini sil" istenmez —
teknik değil ve unutur; sistem kendisi eşleştirir:

  kimlik  = (blok, plan tipi, kat)   — kat: paftanın kotu, yoksa adındaki kat sırası, o da yoksa başlığı
  yenisi  = dosya adındaki tarihi büyük olan; tarih okunamazsa son yüklenen

Eski pafta **silinmez**: `superseded_by` ile yenisine bağlanır, çizim listesinde "eski revizyon" olarak
görünür, hiçbir hesaba girmez (tek kapı: projedeki çizim sorgularının hepsi `superseded_by IS NULL` süzer).
Kullanıcının metraj kontrol kararları kaybolmaz — kalem anahtarına bağlıdırlar, paftaya değil.

Eski bir revizyon sonradan yüklenirse (önce 2025, sonra 2023) yüklenen dosya eski sayılır ve söylenir.
"""
from __future__ import annotations

import re
from datetime import date

from sqlmodel import Session

from .models import Drawing
from .parser.blocks import normalize
from .parser.levels import floor_rank
from .planset import normalize_title

_DATE = re.compile(r"(?<!\d)(\d{1,2})([./-])(\d{1,2})\2(\d{4}|\d{2})(?!\d)")   # iki ayırıcı aynı: "05.09.2025"
# başlıkta pafta kimliğine katılmayan sözcükler (ölçek, blok adı, kot yazısı)
_NOISE = re.compile(r"OLCEK\s*\d*|1\s*/?\s*\d{2,4}|\bBLOK\b|\b[A-Z]\d{1,2}\b|[+\-]?\d+[.,]\d+|KOTU?")


def source_file(d: Drawing) -> str:
    """Paftanın geldiği dosya: kırpılmış paftada "dosya.dxf › başlık"."""
    return (d.filename or "").split(" › ")[0].strip()


def revision_date(name: str) -> str:
    """Dosya adındaki tarih: "A2 BLOK - 21.11.2025" → "2025-11-21"; "04.01.24" → "2024-01-04"; yoksa ""."""
    for m in _DATE.finditer(name or ""):
        g, a, y = int(m.group(1)), int(m.group(3)), int(m.group(4))
        if y < 100:
            y += 2000
        try:
            return date(y, a, g).isoformat()
        except ValueError:
            continue
    return ""


def identity(d: Drawing) -> tuple | None:
    """Paftanın kimliği: (blok, plan tipi, kat). Kat: kot > adındaki kat sırası > sadeleştirilmiş başlık.
    Hiçbiri yoksa None: adsız paftalar birbirinin revizyonu sayılmaz (yanlış eşleşme veri kaybettirir)."""
    if d.kot is not None:
        kat = ("kot", round(float(d.kot), 2))
    else:
        r = floor_rank(d.label or "")
        baslik = " ".join(_NOISE.sub(" ", normalize_title(d.label or "")).split())
        if r is None and not baslik:
            return None
        kat = ("sira", r) if r is not None else ("baslik", baslik)
    return (normalize(d.block or ""), d.plan_type or d.discipline or "", kat)


def apply_revisions(new: list[Drawing], session: Session) -> list[str]:
    """Yeni yüklenen paftaları projedeki etkin paftalarla eşleştirir; eskisi olanı hesaptan çıkarır.
    Döner: kullanıcıya gösterilecek cümleler."""
    from sqlmodel import select
    if not new:
        return []
    yeni_idler = {d.id for d in new}
    project_id = new[0].project_id
    etkin = [d for d in session.exec(select(Drawing).where(Drawing.project_id == project_id, Drawing.superseded_by.is_(None))).all()
             if d.id not in yeni_idler]
    olaylar: list[str] = []
    for d in new:
        d.revision = d.revision or revision_date(source_file(d))
        kim = identity(d)
        if kim is None:
            session.add(d)
            continue
        for o in etkin:
            if o.superseded_by is not None or identity(o) != kim:
                continue
            o.revision = o.revision or revision_date(source_file(o))
            if d.revision and o.revision and d.revision < o.revision:
                d.superseded_by = o.id
                olaylar.append(f"“{d.label}” ({source_file(d)}) projedeki paftadan ESKİ ({d.revision} < {o.revision}): "
                               f"hesaba katılmadı, “{source_file(o)}” geçerli.")
                break
            o.superseded_by = d.id
            session.add(o)
            olaylar.append(f"“{o.label}” yeni revizyonla değişti: {source_file(o)}"
                           f"{' (' + o.revision + ')' if o.revision else ''} → {source_file(d)}"
                           f"{' (' + d.revision + ')' if d.revision else ''}. Eski pafta hesaptan çıktı, listede duruyor.")
        session.add(d)
    session.commit()
    return olaylar


def make_current(d: Drawing, session: Session) -> Drawing | None:
    """Kullanıcı eski revizyonu geri geçerli yapar (yanlış eşleşme ya da yeni revizyon beğenilmedi): aynı
    kimlikteki etkin pafta bu paftaya bağlanıp hesaptan çıkar. Döner: yerine geçilen pafta."""
    from sqlmodel import select
    if d.superseded_by is None:
        return None
    kim = identity(d)
    yerine = None
    if kim is None:
        kim = ("__eslesmez__", d.id)
    for o in session.exec(select(Drawing).where(Drawing.project_id == d.project_id, Drawing.superseded_by.is_(None))).all():
        if identity(o) == kim:
            o.superseded_by = d.id
            session.add(o)
            yerine = yerine or o
    if yerine is None and d.superseded_by is not None:
        # kimlik sonradan değişmiş (plan tipi düzeltildi): doğrudan yerine geçtiği paftayla yer değiştir
        o = session.get(Drawing, d.superseded_by)
        if o is not None and o.superseded_by is None:
            o.superseded_by = d.id
            session.add(o)
            yerine = o
    d.superseded_by = None
    session.add(d)
    session.commit()
    return yerine


def release(d: Drawing, session: Session) -> None:
    """Pafta silinirken: onun yüzünden hesaptan çıkmış paftalar, silinenin yerine geçtiği paftaya
    (o da yoksa etkin hâle) bağlanır — yeni revizyonu silmek eskisini geri getirir."""
    from sqlmodel import select
    for o in session.exec(select(Drawing).where(Drawing.superseded_by == d.id)).all():
        o.superseded_by = d.superseded_by
        session.add(o)
