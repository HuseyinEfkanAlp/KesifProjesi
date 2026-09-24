"""Giriş, çıkış, ilk kurulum ve şirket içi kullanıcı yönetimi.

Kimlik denetimi burada değil `main.kimlik_kapisi`nde yapılır; buradaki uçlar yalnız oturumu açar,
kapatır ve kullanıcıları yönetir. `/api/users` uçları ara katmanda sahibine kısıtlanır
(`auth.izin`), yine de her uç şirketi ayrıca süzer: başka şirketin kullanıcısı 404'tür.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import auth
from ..db import get_session
from ..models import Company, User
from ..tenancy import ROLES, default_company

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class SetupIn(BaseModel):
    email: str
    password: str
    name: str = ""
    company_name: str = ""


class PasswordIn(BaseModel):
    current: str
    new: str


class UserIn(BaseModel):
    email: str
    password: str
    name: str = ""
    role: str = "uzman"


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None


class ResetIn(BaseModel):
    password: str


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(auth.COOKIE_NAME, token, max_age=auth.SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=auth.COOKIE_SECURE, path="/")


def _me(k: auth.Kimlik) -> dict:
    return {"user": {"id": k.user_id, "email": k.email, "name": k.name, "role": k.role,
                     "role_label": auth.ROLE_LABELS.get(k.role, k.role)},
            "company": {"slug": k.company_slug, "name": k.company_name}}


def _require() -> auth.Kimlik:
    k = auth.current()
    if k is None:                       # ara katman bunu zaten engeller; savunma amaçlı
        raise HTTPException(401, "Giriş yapmanız gerekiyor.")
    return k


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise HTTPException(400, f"Rol şunlardan biri olmalı: {', '.join(ROLES)}")


# ------------------------------------------------------------------ oturum

@router.get("/auth/status")
def status(session: Session = Depends(get_session)):
    """Açılışta istemcinin ilk sorusu: kurulum mu, giriş mi, yoksa içeride mi?"""
    k = auth.current()
    return {"needs_setup": auth.needs_setup(session), "me": _me(k) if k else None,
            "roles": auth.ROLE_LABELS}


@router.post("/auth/setup")
def setup(body: SetupIn, response: Response, session: Session = Depends(get_session)):
    """İlk hesap. Yalnız hiç kullanıcı yokken çalışır; hesap varsayılan şirketin sahibi olur ve
    kiracılık öncesi projelerin hepsini görür (bkz. tenancy.owned_or_legacy)."""
    if not auth.needs_setup(session):
        raise HTTPException(409, "Kurulum zaten yapılmış. Giriş yapın.")
    email = auth.normalize_email(body.email)
    if "@" not in email:
        raise HTTPException(400, "Geçerli bir e-posta adresi girin.")
    if msg := auth.check_password_rule(body.password):
        raise HTTPException(400, msg)
    company = default_company(session)
    if body.company_name.strip():
        company.name = body.company_name.strip()
        session.add(company)
        session.commit()
        session.refresh(company)
    user = auth.create_user(session, company, email, body.password, body.name, role="sahibi")
    _set_cookie(response, auth.open_session(session, user))
    return _me(auth.kimlik_of(user, company))


@router.post("/auth/login")
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    email = auth.normalize_email(body.email)
    if kalan := auth.login_locked(email):
        raise HTTPException(429, f"Çok fazla hatalı deneme. {max(1, kalan // 60)} dakika sonra tekrar deneyin.")
    user = session.exec(select(User).where(User.email == email)).first()
    # Kullanıcı yoksa da aynı cevap: hangi e-postaların kayıtlı olduğu sızdırılmaz.
    if user is None or not auth.verify_password(body.password, user.password_hash):
        auth.login_failed(email)
        raise HTTPException(401, "E-posta veya şifre hatalı.")
    if not user.active:
        raise HTTPException(403, "Bu hesap kapatılmış. Şirket sahibinizle görüşün.")
    auth.login_succeeded(email)
    company = session.get(Company, user.company_id)
    _set_cookie(response, auth.open_session(session, user))
    return _me(auth.kimlik_of(user, company))


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    token = request.cookies.get(auth.COOKIE_NAME)
    if token:
        auth.close_session(session, token)
    response.delete_cookie(auth.COOKIE_NAME, path="/")


@router.get("/auth/me")
def me():
    return _me(_require())


@router.post("/auth/password", status_code=204)
def change_password(body: PasswordIn, request: Request, session: Session = Depends(get_session)):
    """Kendi şifresini değiştirir; bu tarayıcı dışındaki bütün oturumlar kapanır."""
    k = _require()
    user = session.get(User, k.user_id)
    if user is None or not auth.verify_password(body.current, user.password_hash):
        raise HTTPException(400, "Mevcut şifre hatalı.")
    if msg := auth.check_password_rule(body.new):
        raise HTTPException(400, msg)
    user.password_hash = auth.hash_password(body.new)
    session.add(user)
    session.commit()
    auth.close_all_sessions(session, user.id, keep_token=request.cookies.get(auth.COOKIE_NAME))


# ------------------------------------------------------------------ kullanıcı yönetimi (sahibi)

def _company_user(session: Session, user_id: int) -> User:
    k = _require()
    u = session.get(User, user_id)
    if u is None or u.company_id != k.company_id:
        raise HTTPException(404, "Kullanıcı bulunamadı")
    return u


def _active_owners(session: Session, company_id: int) -> int:
    return len(session.exec(select(User.id).where(User.company_id == company_id, User.role == "sahibi",
                                                  User.active == True)).all())  # noqa: E712


@router.get("/users")
def list_users(session: Session = Depends(get_session)):
    k = _require()
    rows = session.exec(select(User).where(User.company_id == k.company_id).order_by(User.created_at)).all()
    return [auth.user_out(u) for u in rows]


@router.post("/users", status_code=201)
def add_user(body: UserIn, session: Session = Depends(get_session)):
    """Şirkete kullanıcı ekler. Şifreyi sahibi belirler ve kişiye iletir; kişi girince değiştirebilir."""
    k = _require()
    _check_role(body.role)
    email = auth.normalize_email(body.email)
    if "@" not in email:
        raise HTTPException(400, "Geçerli bir e-posta adresi girin.")
    if msg := auth.check_password_rule(body.password):
        raise HTTPException(400, msg)
    if session.exec(select(User).where(User.email == email)).first() is not None:
        raise HTTPException(409, "Bu e-posta ile kayıtlı bir kullanıcı zaten var.")
    company = session.get(Company, k.company_id)
    return auth.user_out(auth.create_user(session, company, email, body.password, body.name, body.role))


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, session: Session = Depends(get_session)):
    u = _company_user(session, user_id)
    data = body.model_dump(exclude_unset=True)
    if "role" in data:
        _check_role(data["role"])
    # Şirket sahipsiz kalmasın: son etkin sahibi rolünü bırakamaz, kapatılamaz.
    sahiplikten_cikiyor = u.role == "sahibi" and u.active and (
        data.get("role", "sahibi") != "sahibi" or data.get("active") is False)
    if sahiplikten_cikiyor and _active_owners(session, u.company_id) <= 1:
        raise HTTPException(400, "Şirketin en az bir etkin sahibi olmalı. Önce başka birini sahibi yapın.")
    if "name" in data and data["name"] is not None:
        u.name = data["name"].strip()
    if data.get("role"):
        u.role = data["role"]
    if data.get("active") is not None:
        u.active = bool(data["active"])
    session.add(u)
    session.commit()
    session.refresh(u)
    if not u.active:
        auth.close_all_sessions(session, u.id)
    return auth.user_out(u)


@router.post("/users/{user_id}/password", status_code=204)
def reset_password(user_id: int, body: ResetIn, session: Session = Depends(get_session)):
    """Sahibi, şifresini unutan çalışanına yeni şifre verir; kişinin açık oturumları kapanır."""
    u = _company_user(session, user_id)
    if msg := auth.check_password_rule(body.password):
        raise HTTPException(400, msg)
    u.password_hash = auth.hash_password(body.password)
    session.add(u)
    session.commit()
    auth.close_all_sessions(session, u.id)
