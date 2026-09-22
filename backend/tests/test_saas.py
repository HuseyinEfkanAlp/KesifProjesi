"""SaaS zemini: çok kiracılık ve iş kuyruğu (app/tenancy.py, app/jobs.py).

İki şey de sonradan eklenemez. Kiracı ayrımı bir kez kiracısız veri birikince her sorguyu
gözden geçirmek demektir; kaçırılan bir tanesi başka müşterinin metrajını göstermektir.
Uzun analizin istek içinde beklemesi ise internetten kullanan biri için "site dondu"dur.
"""
from fastapi.testclient import TestClient

from app import jobs as jobsmod
from app.jobs import DONE, FAILED, QUEUED, enqueue, job_out, register, run_pending
from app.models import Company


def _sirket(session, slug, ad=""):
    c = Company(slug=slug, name=ad or slug)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _oturum():
    from sqlmodel import Session

    from app import db as dbmod
    return Session(dbmod.engine)


# ------------------------------------------------------------------ çok kiracılık

def test_kiraci_baskasinin_projesini_goremez(client: TestClient):
    with _oturum() as s:
        _sirket(s, "aofis", "A Ofis")
        _sirket(s, "bofis", "B Ofis")
    a = client.post("/api/projects", json={"name": "A projesi"}, headers={"X-Company": "aofis"}).json()

    # B ofisi A'nın projesini listede görmez
    liste = client.get("/api/projects", headers={"X-Company": "bofis"}).json()
    assert [p["id"] for p in liste] == []

    # doğrudan erişimde de 404 — 403 değil: projenin varlığı bile sızdırılmaz
    r = client.get(f"/api/projects/{a['id']}", headers={"X-Company": "bofis"})
    assert r.status_code == 404


def test_kiraci_kendi_projesini_gorur(client: TestClient):
    with _oturum() as s:
        _sirket(s, "aofis")
    a = client.post("/api/projects", json={"name": "A projesi"}, headers={"X-Company": "aofis"}).json()
    r = client.get(f"/api/projects/{a['id']}", headers={"X-Company": "aofis"})
    assert r.status_code == 200 and r.json()["name"] == "A projesi"
    assert [p["id"] for p in client.get("/api/projects", headers={"X-Company": "aofis"}).json()] == [a["id"]]


def test_bilinmeyen_sirket_sessizce_varsayilana_dusmez(client: TestClient):
    """Sessizce varsayılana düşmek, yanlış kiracının verisini göstermenin en kolay yoludur."""
    r = client.get("/api/projects", headers={"X-Company": "olmayan-ofis"})
    assert r.status_code == 404


def test_kiracilik_oncesi_projeleri_yalniz_varsayilan_sirket_gorur(client: TestClient):
    """Yükseltmeden sonra eski projeler kaybolmamalı; ama her şirkete de açılmamalı."""
    eski = client.post("/api/projects", json={"name": "Eski"}).json()     # başlıksız = varsayılan şirket
    with _oturum() as s:
        from app.models import Project
        p = s.get(Project, eski["id"])
        p.company_id = None                                              # kiracılık öncesi kayıt
        s.add(p)
        s.commit()
        _sirket(s, "aofis")
    assert client.get(f"/api/projects/{eski['id']}").status_code == 200
    assert client.get(f"/api/projects/{eski['id']}", headers={"X-Company": "aofis"}).status_code == 404


# ------------------------------------------------------------------ iş kuyruğu

def test_is_sirayla_calisir_ve_sonuc_saklanir(client: TestClient):
    register("deneme", lambda s, j: {"toplam": j.payload["a"] + j.payload["b"]})
    with _oturum() as s:
        job = enqueue(s, None, "deneme", {"a": 2, "b": 3})
        assert job.status == QUEUED
    assert run_pending() == 1
    j = client.get(f"/api/jobs/{job.id}").json()
    assert j["status"] == DONE and j["result"]["toplam"] == 5
    assert j["progress"] == 100.0 and j["seconds"] is not None


def test_hata_kullaniciya_tek_cumle_ayrinti_kayda(client: TestClient):
    """Dosya sessizce kaybolmaz: iş 'hata' durumuna düşer ve sebebi görünür."""
    def patla(s, j):
        raise RuntimeError("DXF okunamadı: bozuk dosya")

    register("patlar", patla)
    with _oturum() as s:
        job = enqueue(s, None, "patlar", {})
    run_pending()
    j = client.get(f"/api/jobs/{job.id}").json()
    assert j["status"] == FAILED
    assert j["error"] == "DXF okunamadı: bozuk dosya"
    assert "detail" not in j                      # yığın izi kullanıcıya gösterilmez


def test_bilinmeyen_is_turu_hata_verir(client: TestClient):
    with _oturum() as s:
        job = enqueue(s, None, "boyle-bir-is-yok", {})
    run_pending()
    with _oturum() as s:
        from app.models import Job
        assert s.get(Job, job.id).status == FAILED


def test_ilerleme_is_calisirken_gorunur(client: TestClient):
    from app.jobs import progress

    def yavas(s, j):
        progress(s, j.id, 40.0, "3/6 pafta")
        with _oturum() as s2:
            from app.models import Job
            ara = s2.get(Job, j.id)
            assert ara.progress == 40.0 and ara.message == "3/6 pafta"
        return {}

    register("yavas", yavas)
    with _oturum() as s:
        job = enqueue(s, None, "yavas", {})
    run_pending()
    with _oturum() as s:
        from app.models import Job
        assert s.get(Job, job.id).status == DONE


def test_is_kiraci_baglamini_kendi_parcaciginda_kurar(client: TestClient):
    """ContextVar iş parçacığına özeldir: işçi şirketi kayıttan okuyup yeniden kurmak zorundadır."""
    from app.tenancy import get_slug

    gorulen = {}
    register("slug", lambda s, j: gorulen.update(slug=get_slug()) or {})
    with _oturum() as s:
        enqueue(s, None, "slug", {}, company_slug="aofis")
    run_pending()
    assert gorulen["slug"] == "aofis"


def test_testlerde_arka_plan_parcacigi_calismaz():
    """Yarış durumu olmasın diye testte işler yalnız run_pending ile çalışır."""
    assert jobsmod.AUTO_START is False


def test_proje_isleri_listelenir(client: TestClient):
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    register("deneme2", lambda s, j: {})
    with _oturum() as s:
        enqueue(s, pid, "deneme2", {}, label="proje.dxf")
    aktif = client.get(f"/api/projects/{pid}/jobs?active=true").json()
    assert len(aktif) == 1 and aktif[0]["label"] == "proje.dxf"
    run_pending()
    assert client.get(f"/api/projects/{pid}/jobs?active=true").json() == []
    assert len(client.get(f"/api/projects/{pid}/jobs").json()) == 1


def test_job_out_yigin_izini_sizdirmaz():
    from app.models import Job
    j = Job(id=1, kind="x", status=FAILED, error="tek cümle", detail="Traceback...")
    assert "detail" not in job_out(j) and job_out(j)["error"] == "tek cümle"
