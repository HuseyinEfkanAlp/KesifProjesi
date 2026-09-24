"""Çok kiracılık: her proje bir şirkete aittir ve kimse başkasının projesini göremez.

**Neden şimdi:** kiracı ayrımı sonradan eklenemez. Bir kere kiracısız veri birikince her sorguyu
tek tek gözden geçirmek, kaçırılan bir tanesinde başka müşterinin metrajını göstermek demektir.
Bugün tek şirket var (`DEFAULT_COMPANY_SLUG`), ama sütun ve süzgeç baştan yerinde duruyor.

**Tek kapı kuralı.** Kiracı süzgeci uçlarda elle yazılmaz: isteğin şirketi bir bağlam değişkeninde
(`_slug`) taşınır ve `api.projects.get_project` onu kendiliğinden uygular. Projeye ulaşan 35 uç
zaten o fonksiyondan geçiyor; süzgeci oraya koymak "unutulabilir" olmaktan çıkarır. Elle yazılan
süzgeç er geç bir yerde unutulur ve unutulduğu yer tam olarak veri sızıntısının olduğu yerdir.

⚠ Bağlam değişkeni **iş parçacığına özeldir**: arka planda iş çalıştıran her yer (`jobs.py`)
şirketi kendi iş parçacığında yeniden kurmak zorundadır — `use_company()` bunun içindir.

Şirketi **giriş yapan kullanıcı** belirler (app/auth.py): `main.kimlik_kapisi` oturumdan kullanıcıyı
bulur ve onun şirketini buraya koyar. İstemcinin söylediği hiçbir şey (başlık, parametre) şirketi
değiştiremez.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException
from sqlmodel import Session, select

from .models import Company, Project

DEFAULT_COMPANY_SLUG = "varsayilan"
DEFAULT_COMPANY_NAME = "Varsayılan şirket"

# Roller. Neye izin verildiği uçlarda değil `auth.izin`de tek yerden okunur.
ROLES = ("sahibi", "uzman", "goruntuleyen")

# İsteğin şirketi (slug). Boş = varsayılan şirket.
_slug: ContextVar[str] = ContextVar("kesif_company_slug", default="")


def set_slug(slug: str) -> None:
    _slug.set((slug or "").strip())


def get_slug() -> str:
    return _slug.get()


@contextmanager
def use_company(slug: str):
    """Bağlam değişkenini geçici olarak kurar. Arka plan iş parçacıkları bunu kullanmak zorundadır:
    ContextVar iş parçacığına özeldir, isteğin bağlamı oraya kendiliğinden taşınmaz."""
    token = _slug.set((slug or "").strip())
    try:
        yield
    finally:
        _slug.reset(token)


def default_company(session: Session) -> Company:
    """Varsayılan şirket; yoksa oluşturulur. Tek kiracılı kurulumda her proje buna bağlanır."""
    c = session.exec(select(Company).where(Company.slug == DEFAULT_COMPANY_SLUG)).first()
    if c is None:
        c = Company(slug=DEFAULT_COMPANY_SLUG, name=DEFAULT_COMPANY_NAME)
        session.add(c)
        session.commit()
        session.refresh(c)
    return c


def current_company(session: Session) -> Company:
    """İsteğin ait olduğu şirket (giriş yapan kullanıcınınki).

    Bağlam bilinmeyen bir şirketi gösteriyorsa istek reddedilir: sessizce varsayılana düşmek,
    yanlış kiracının verisini göstermenin en kolay yoludur."""
    slug = get_slug()
    if not slug or slug == DEFAULT_COMPANY_SLUG:
        return default_company(session)
    c = session.exec(select(Company).where(Company.slug == slug)).first()
    if c is None:
        raise HTTPException(404, f"Şirket bulunamadı: {slug}")
    return c


def owned(company_id: int):
    """Projeleri kiracıya göre süzen ortak koşul.

    Eski kayıtlar (kiracılık öncesi) `company_id = None` taşır; **yalnız varsayılan şirket**
    onları görür. Her şirketin görmesi sızıntı, hiç kimsenin görmemesi ise yükseltmeden sonra
    bütün projelerin kaybolması olurdu."""
    return Project.company_id == company_id


def owned_or_legacy(company_id: int, is_default: bool):
    return (Project.company_id == company_id) | (Project.company_id == None) if is_default \
        else owned(company_id)  # noqa: E711
