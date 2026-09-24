"""Kimlik doğrulama ve yetki: kim giriş yaptı, hangi şirkettendir, ne yapabilir?

**Tek kapı.** Kimlik uçlarda tek tek denetlenmez: `main.kimlik_kapisi` ara katmanı her `/api/`
isteğinde çerezi okur, kullanıcıyı bulur, şirketini `tenancy` bağlamına koyar ve rol kuralını
(`izin`) uygular. Yeni eklenen bir uç kendiliğinden korunur; korumayı unutmak mümkün değildir.
Kiracılıkta olduğu gibi: elle yazılan denetim bir yerde unutulur ve unutulduğu yer açıktır.

**Şirketi kullanıcı belirler.** Önceki `X-Company` başlığı kaldırıldı — başlığı herkes yazabilir,
başka şirketin projesini görmek için tek satır yeterdi.

Şifre `hashlib.scrypt` ile saklanır (standart kütüphane, ek bağımlılık yok). Oturum anahtarı
çerezde durur, veritabanında yalnız SHA-256 özeti.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlmodel import Session, select

from .models import Company, User, UserSession

COOKIE_NAME = "kesif_oturum"
SESSION_DAYS = 30
MIN_PASSWORD = 8

# Üretimde (HTTPS) çerez yalnız şifreli bağlantıda gönderilsin. Yerelde http olduğu için kapalı.
COOKIE_SECURE = os.environ.get("KESIF_COOKIE_SECURE", "") in ("1", "true", "evet")

# Kimliksiz erişilebilen uçlar: ilk kurulum, giriş ve durum.
PUBLIC_PATHS = {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/setup"}

# Görüntüleyen de olsa herkesin kendi hesabı için yapabildiği yazma işlemleri.
SELF_SERVICE = {"/api/auth/logout", "/api/auth/password"}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# scrypt maliyeti (~130 ms). Testler düşürür; saklanan özet kendi parametresini taşıdığı için eski
# özetler değer değişse de doğrulanır.
SCRYPT_N = 2 ** 14

ROLE_LABELS = {
    "sahibi": "Sahibi — her şey + kullanıcı yönetimi",
    "uzman": "Uzman — proje açar, çizim yükler, metrajı onaylar",
    "goruntuleyen": "Görüntüleyen — yalnız bakar ve rapor indirir",
}


@dataclass(frozen=True)
class Kimlik:
    user_id: int
    email: str
    name: str
    role: str
    company_id: int
    company_slug: str
    company_name: str


_kimlik: ContextVar[Kimlik | None] = ContextVar("kesif_kimlik", default=None)


def current() -> Kimlik | None:
    return _kimlik.get()


def set_current(k: Kimlik | None) -> None:
    _kimlik.set(k)


# ------------------------------------------------------------------ yetki kuralı

def izin(role: str, method: str, path: str) -> str | None:
    """İstek bu role açık mı? Açıksa None, değilse kullanıcıya gösterilecek gerekçe.

    Kural bilerek kaba ve tek yerde: uçları tek tek etiketlemek, etiketsiz kalan ucun herkese
    açık olması demektir. Kural yol ve yöntemden okunur, yeni uç kendiliğinden kapsanır."""
    if path.startswith("/api/users"):
        return None if role == "sahibi" else "Kullanıcıları yalnız şirket sahibi yönetebilir."
    if method in SAFE_METHODS or path in SELF_SERVICE:
        return None
    if role == "goruntuleyen":
        return "Hesabınız yalnız görüntüleme yetkisine sahip; değişiklik yapamazsınız."
    return None


# ------------------------------------------------------------------ şifre

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    n, r, p = SCRYPT_N, 8, 1
    h = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                              n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(h)))
        return hmac.compare_digest(calc.hex(), h)
    except (ValueError, TypeError):
        return False


def check_password_rule(password: str) -> str | None:
    if len(password or "") < MIN_PASSWORD:
        return f"Şifre en az {MIN_PASSWORD} karakter olmalı."
    return None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


# ------------------------------------------------------------------ giriş denemesi sınırı

# Aynı e-postaya art arda yanlış şifre: tahmin saldırısını yavaşlatır. Bellekte tutulur —
# sunucu yeniden başlayınca sıfırlanır, bu kabul edilebilir (amaç yavaşlatmak).
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
_fails: dict[str, list[float]] = {}


def login_locked(email: str) -> int:
    """Kilitliyse kalan saniye, değilse 0."""
    now = time.monotonic()
    recent = [t for t in _fails.get(email, []) if now - t < LOCK_SECONDS]
    _fails[email] = recent
    if len(recent) >= MAX_FAILS:
        return int(LOCK_SECONDS - (now - recent[0])) + 1
    return 0


def login_failed(email: str) -> None:
    _fails.setdefault(email, []).append(time.monotonic())


def login_succeeded(email: str) -> None:
    _fails.pop(email, None)


# ------------------------------------------------------------------ oturum

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def open_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(UserSession(token_hash=_digest(token), user_id=user.id,
                            expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS)))
    user.last_login = datetime.utcnow()
    session.add(user)
    session.commit()
    return token


def close_session(session: Session, token: str) -> None:
    row = session.exec(select(UserSession).where(UserSession.token_hash == _digest(token))).first()
    if row is not None:
        session.delete(row)
        session.commit()


def close_all_sessions(session: Session, user_id: int, keep_token: str | None = None) -> None:
    """Kullanıcının oturumlarını kapatır (şifre değişince, pasifleştirilince)."""
    keep = _digest(keep_token) if keep_token else None
    for row in session.exec(select(UserSession).where(UserSession.user_id == user_id)).all():
        if row.token_hash != keep:
            session.delete(row)
    session.commit()


def resolve(session: Session, token: str | None) -> Kimlik | None:
    """Çerezdeki anahtardan kimliği çıkarır. Süresi dolmuş, pasif kullanıcı → None."""
    if not token:
        return None
    row = session.exec(select(UserSession).where(UserSession.token_hash == _digest(token))).first()
    if row is None:
        return None
    if row.expires_at < datetime.utcnow():
        session.delete(row)
        session.commit()
        return None
    user = session.get(User, row.user_id)
    if user is None or not user.active:
        return None
    company = session.get(Company, user.company_id)
    if company is None:
        return None
    return kimlik_of(user, company)


def kimlik_of(user: User, company: Company) -> Kimlik:
    return Kimlik(user_id=user.id, email=user.email, name=user.name, role=user.role,
                  company_id=company.id, company_slug=company.slug, company_name=company.name)


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None}


def needs_setup(session: Session) -> bool:
    """Hiç kullanıcı yoksa ilk açılış: ilk hesabı açan varsayılan şirketin sahibi olur."""
    return session.exec(select(User.id)).first() is None


def create_user(session: Session, company: Company, email: str, password: str, name: str = "",
                role: str = "uzman") -> User:
    u = User(company_id=company.id, email=normalize_email(email), name=(name or "").strip(),
             password_hash=hash_password(password), role=role)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u
