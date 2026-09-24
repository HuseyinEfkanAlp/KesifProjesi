"""Giriş ve yetki (app/auth.py, app/api/auth.py).

`client` fikstürü varsayılan şirketin sahibi olarak giriş yapmış başlar (ilk kurulum hesabı:
sahip@test.local / sifre1234). Kimliksiz davranış çerezler silinerek sınanır.
"""
import pytest
from fastapi.testclient import TestClient

from app import auth

SAHIP = "sahip@test.local"
SIFRE = "sifre1234"


@pytest.fixture(autouse=True)
def _kilit_temiz():
    auth._fails.clear()          # giriş denemesi sayacı bellekte; testler birbirini kilitlemesin
    yield
    auth._fails.clear()


def _giris(client, email, sifre=SIFRE):
    return client.post("/api/auth/login", json={"email": email, "password": sifre})


def _ekle(client, email, rol, sifre=SIFRE, ad=""):
    r = client.post("/api/users", json={"email": email, "password": sifre, "role": rol, "name": ad})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ kapı

def test_kimliksiz_istek_reddedilir(client: TestClient):
    client.cookies.clear()
    r = client.get("/api/projects")
    assert r.status_code == 401 and r.json()["detail"] == "Giriş yapmanız gerekiyor."
    assert client.post("/api/projects", json={"name": "x"}).status_code == 401


def test_acik_uclar_kimlik_istemez(client: TestClient):
    client.cookies.clear()
    assert client.get("/api/health").status_code == 200
    st = client.get("/api/auth/status").json()
    assert st["needs_setup"] is False and st["me"] is None


def test_sahte_cerez_kimlik_saglamaz(client: TestClient):
    client.cookies.clear()
    client.cookies.set(auth.COOKIE_NAME, "uydurma-anahtar")
    assert client.get("/api/projects").status_code == 401


def test_cerez_httponly(client: TestClient):
    client.cookies.clear()
    r = _giris(client, SAHIP)
    cerez = r.headers["set-cookie"].lower()
    assert "httponly" in cerez and "samesite=lax" in cerez


# ------------------------------------------------------------------ kurulum ve giriş

def test_kurulum_bir_kez_yapilir(client: TestClient):
    r = client.post("/api/auth/setup", json={"email": "ikinci@test.local", "password": SIFRE})
    assert r.status_code == 409


def test_ilk_kurulum_hesabi_sahibi_olur(client: TestClient):
    me = client.get("/api/auth/me").json()
    assert me["user"]["role"] == "sahibi" and me["company"]["slug"] == "varsayilan"


def test_needs_setup_kullanici_yokken():
    from sqlmodel import Session, SQLModel, create_engine
    from sqlmodel.pool import StaticPool
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        assert auth.needs_setup(s) is True


def test_yanlis_sifre_ve_olmayan_kullanici_ayni_cevabi_alir(client: TestClient):
    a = _giris(client, SAHIP, "yanlis-sifre")
    b = _giris(client, "yok@test.local", "yanlis-sifre")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()                   # hangi e-postanın kayıtlı olduğu sızmaz


def test_eposta_buyuk_kucuk_harf_duyarsiz(client: TestClient):
    assert _giris(client, "  SAHIP@Test.Local ").status_code == 200


def test_art_arda_hatali_giris_kilitlenir(client: TestClient):
    for _ in range(auth.MAX_FAILS):
        assert _giris(client, SAHIP, "yanlis-sifre").status_code == 401
    r = _giris(client, SAHIP)                     # doğru şifre bile kilit süresince reddedilir
    assert r.status_code == 429 and "dakika" in r.json()["detail"]


def test_cikis_oturumu_kapatir(client: TestClient):
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/projects").status_code == 401


def test_sifre_ve_anahtar_duz_metin_saklanmaz(client: TestClient):
    from sqlmodel import Session, select

    from app import db
    from app.models import User, UserSession
    token = client.cookies.get(auth.COOKIE_NAME)
    with Session(db.engine) as s:
        u = s.exec(select(User).where(User.email == SAHIP)).first()
        assert SIFRE not in u.password_hash and u.password_hash.startswith("scrypt$")
        assert all(row.token_hash != token for row in s.exec(select(UserSession)).all())


def test_kisa_sifre_reddedilir(client: TestClient):
    r = client.post("/api/users", json={"email": "k@test.local", "password": "kisa", "role": "uzman"})
    assert r.status_code == 400 and "8" in r.json()["detail"]


# ------------------------------------------------------------------ roller

def test_goruntuleyen_bakar_degistiremez(client: TestClient):
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    _ekle(client, "bakan@test.local", "goruntuleyen")
    _giris(client, "bakan@test.local")
    assert client.get(f"/api/projects/{pid}").status_code == 200
    r = client.patch(f"/api/projects/{pid}", json={"name": "değişti"})
    assert r.status_code == 403 and "görüntüleme" in r.json()["detail"]
    assert client.post("/api/projects", json={"name": "yeni"}).status_code == 403
    assert client.delete(f"/api/projects/{pid}").status_code == 403


def test_goruntuleyen_kendi_sifresini_degistirebilir(client: TestClient):
    _ekle(client, "bakan@test.local", "goruntuleyen")
    _giris(client, "bakan@test.local")
    r = client.post("/api/auth/password", json={"current": SIFRE, "new": "yenisifre99"})
    assert r.status_code == 204
    client.cookies.clear()
    assert _giris(client, "bakan@test.local", "yenisifre99").status_code == 200


def test_uzman_proje_acar_kullanici_yonetemez(client: TestClient):
    _ekle(client, "uzman@test.local", "uzman")
    _giris(client, "uzman@test.local")
    assert client.post("/api/projects", json={"name": "P"}).status_code == 201
    r = client.get("/api/users")
    assert r.status_code == 403 and "sahibi" in r.json()["detail"]


def test_metraj_karari_oturumdaki_kisinin_adiyla_yazilir(client: TestClient):
    _ekle(client, "ayse@test.local", "uzman", ad="Ayşe Yılmaz")
    _giris(client, "ayse@test.local")
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    r = client.put(f"/api/projects/{pid}/review", json={"item_key": "duvar:x", "status": "onaylandi"})
    assert r.json()["author"] == "Ayşe Yılmaz"


# ------------------------------------------------------------------ kullanıcı yönetimi

def test_ayni_eposta_iki_kez_eklenemez(client: TestClient):
    _ekle(client, "u@test.local", "uzman")
    r = client.post("/api/users", json={"email": "U@test.local", "password": SIFRE, "role": "uzman"})
    assert r.status_code == 409


def test_gecersiz_rol_reddedilir(client: TestClient):
    r = client.post("/api/users", json={"email": "u@test.local", "password": SIFRE, "role": "patron"})
    assert r.status_code == 400


def test_son_sahip_kendini_dusuremez(client: TestClient):
    ben = client.get("/api/auth/me").json()["user"]["id"]
    r = client.patch(f"/api/users/{ben}", json={"role": "uzman"})
    assert r.status_code == 400 and "sahibi" in r.json()["detail"]
    assert client.patch(f"/api/users/{ben}", json={"active": False}).status_code == 400
    # ikinci sahip varken olur
    _ekle(client, "ortak@test.local", "sahibi")
    assert client.patch(f"/api/users/{ben}", json={"role": "uzman"}).status_code == 200


def test_kapatilan_hesabin_oturumu_duser(client: TestClient):
    u = _ekle(client, "giden@test.local", "uzman")
    from fastapi.testclient import TestClient as TC

    from app import main
    diger = TC(main.app)
    assert _giris(diger, "giden@test.local").status_code == 200
    assert diger.get("/api/projects").status_code == 200
    assert client.patch(f"/api/users/{u['id']}", json={"active": False}).status_code == 200
    assert diger.get("/api/projects").status_code == 401
    r = _giris(diger, "giden@test.local")
    assert r.status_code == 403 and "kapatılmış" in r.json()["detail"]


def test_sahibi_sifre_sifirlar_eski_oturum_duser(client: TestClient):
    u = _ekle(client, "unutan@test.local", "uzman")
    from fastapi.testclient import TestClient as TC

    from app import main
    diger = TC(main.app)
    _giris(diger, "unutan@test.local")
    r = client.post(f"/api/users/{u['id']}/password", json={"password": "yepyeni123"})
    assert r.status_code == 204
    assert diger.get("/api/projects").status_code == 401
    assert _giris(diger, "unutan@test.local", "yepyeni123").status_code == 200


def test_baska_sirketin_kullanicisi_yonetilemez(client: TestClient):
    from sqlmodel import Session

    from app import db
    from app.models import Company
    with Session(db.engine) as s:
        c = Company(slug="baska", name="Başka")
        s.add(c)
        s.commit()
        s.refresh(c)
        yabanci = auth.create_user(s, c, "yabanci@baska.test", SIFRE, role="uzman")
    assert client.patch(f"/api/users/{yabanci.id}", json={"active": False}).status_code == 404
    assert all(u["email"] != "yabanci@baska.test" for u in client.get("/api/users").json())


def test_izin_kurali():
    assert auth.izin("goruntuleyen", "GET", "/api/projects") is None
    assert auth.izin("goruntuleyen", "POST", "/api/auth/logout") is None
    assert auth.izin("goruntuleyen", "PUT", "/api/pricebook") is not None
    assert auth.izin("uzman", "DELETE", "/api/projects/1") is None
    assert auth.izin("uzman", "GET", "/api/users") is not None
    assert auth.izin("sahibi", "POST", "/api/users") is None
