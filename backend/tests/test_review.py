"""Metraj kontrolü: keşif satırını onaylama, reddetme, elle düzeltme (app/api/review.py).

Ürünün sözü "metrajı ben çıkarırım" değil, "çıkarırım, nereden geldiğini gösteririm, sen
onaylarsın". Testler asıl kuralı sabitler: **hesaplanan değer hiçbir zaman silinmez.**
"""
import pytest
from fastapi.testclient import TestClient

from app.quantity.boq import BoqItem
from app.services import apply_reviews


def _item(key="duvar:ytong_20", qty=100.0):
    kind, group = key.split(":", 1)
    return BoqItem(key=key, kind=kind, group=group, label=key, unit="m²", quantity=qty,
                   discipline="architectural")


def _kurulum(client: TestClient, **karar):
    """Proje açar, verilen kararı API'den yazar ve (proje, oturum) döner."""
    from app import db as dbmod
    from sqlmodel import Session

    from app.models import Project

    pid = client.post("/api/projects", json={"name": "kontrol"}).json()["id"]
    if karar:
        r = client.put(f"/api/projects/{pid}/review", json={"item_key": "duvar:ytong_20", **karar})
        assert r.status_code == 200, r.text
    s = Session(dbmod.engine)
    return s.get(Project, pid), s


def test_elle_miktar_uygulanir_hesaplanan_saklanir(client: TestClient):
    """"AI tarafından hesaplanan: 100 m² · Manuel: 120 m²" — ikisi de raporda durmalı."""
    p, session = _kurulum(client, status="onaylandi", quantity=120.0,
                          reason="şantiye ölçümü", author="Efkan")
    it = apply_reviews(p, session, [_item(qty=100.0)])[0]
    assert it.quantity == 120.0
    assert it.review["computed"] == 100.0           # programdan çıkan sayı silinmedi
    assert it.review["status"] == "onaylandi"
    assert it.review["reason"] == "şantiye ölçümü"


def test_reddedilen_kalem_listeden_silinmez_sifirlanir(client: TestClient):
    """Sessizce kaybolan bir kalem, hiç hesaplanmamış bir kalemden ayırt edilemez."""
    p, session = _kurulum(client, status="reddedildi")
    items = apply_reviews(p, session, [_item(qty=100.0)])
    assert len(items) == 1
    assert items[0].quantity == 0.0
    assert items[0].review["computed"] == 100.0
    assert items[0].review["status"] == "reddedildi"


def test_onay_miktari_degistirmez(client: TestClient):
    p, session = _kurulum(client, status="onaylandi")
    it = apply_reviews(p, session, [_item(qty=100.0)])[0]
    assert it.quantity == 100.0 and it.review["status"] == "onaylandi"


def test_karari_olmayan_kalem_kontrol_bekler(client: TestClient):
    p, session = _kurulum(client)
    it = apply_reviews(p, session, [_item()])[0]
    assert it.review == {}
    assert it.to_dict()["review_status"] == "kontrol"


def test_karar_kalem_anahtarina_bagli_yeniden_analizde_korunur(client: TestClient):
    """Karar elemana değil kalem anahtarına bağlı: pafta yeniden analiz edilince de durur."""
    p, session = _kurulum(client, status="onaylandi", quantity=120.0)
    # yeniden analiz: aynı anahtar, farklı hesaplanan miktar
    it = apply_reviews(p, session, [_item(qty=155.0)])[0]
    assert it.quantity == 120.0 and it.review["computed"] == 155.0


# ------------------------------------------------------------------ API

def test_api_karar_yazar_gunceller_ve_siler(client: TestClient):
    pid = client.post("/api/projects", json={"name": "kontrol"}).json()["id"]
    r = client.put(f"/api/projects/{pid}/review",
                   json={"item_key": "duvar:ytong_20", "status": "onaylandi", "quantity": 120.0,
                         "computed": 100.0, "reason": "şantiye", "author": "Efkan"})
    assert r.status_code == 200 and r.json()["quantity"] == 120.0

    r = client.put(f"/api/projects/{pid}/review",
                   json={"item_key": "duvar:ytong_20", "status": "reddedildi"})
    assert r.json()["status"] == "reddedildi" and r.json()["quantity"] is None

    liste = client.get(f"/api/projects/{pid}/review").json()
    assert liste["counts"]["reddedildi"] == 1 and len(liste["rows"]) == 1

    assert client.delete(f"/api/projects/{pid}/review/duvar:ytong_20").status_code == 204
    assert client.get(f"/api/projects/{pid}/review").json()["rows"] == []


@pytest.mark.parametrize("body,beklenen", [
    ({"item_key": "", "status": "onaylandi"}, "anahtar"),
    ({"item_key": "a:b", "status": "belirsiz"}, "Durum"),
    ({"item_key": "a:b", "quantity": -5.0}, "negatif"),
])
def test_api_gecersiz_karari_reddeder(client: TestClient, body, beklenen):
    pid = client.post("/api/projects", json={"name": "kontrol"}).json()["id"]
    r = client.put(f"/api/projects/{pid}/review", json=body)
    assert r.status_code == 400 and beklenen in r.json()["detail"]
