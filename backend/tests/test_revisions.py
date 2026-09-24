"""Revizyon takibi: aynı paftanın yenisi yüklenince eskisi hesaptan çıkar, silinmez."""
import re
from pathlib import Path

import pytest

from app.models import Drawing
from app.revisions import identity, revision_date


def test_revision_date_from_filename():
    assert revision_date("A2 BLOK - 21.11.2025.dxf") == "2025-11-21"
    assert revision_date("A3_05.09.2025") == "2025-09-05"
    assert revision_date("mimari 04.01.24 rev") == "2024-01-04"
    assert revision_date("A Bloklar  _  09.dxf") == ""
    assert revision_date("kat 32.13.2025") == ""            # geçersiz tarih okunmaz


def test_identity_ignores_file_and_scale_noise():
    a = Drawing(project_id=1, filename="x.dxf", stored_path="", label="A2 BLOK ZEMİN KAT PLANI 1/100",
                block="A2", plan_type="mim_kat_plani")
    b = Drawing(project_id=1, filename="y.dxf", stored_path="", label="A2 Blok Zemin Kat Planı",
                block="A2", plan_type="mim_kat_plani")
    c = Drawing(project_id=1, filename="y.dxf", stored_path="", label="A2 Blok 1. Kat Planı",
                block="A2", plan_type="mim_kat_plani")
    d = Drawing(project_id=1, filename="y.dxf", stored_path="", label="A3 Blok Zemin Kat Planı",
                block="A3", plan_type="mim_kat_plani")
    assert identity(a) == identity(b)
    assert identity(a) != identity(c)
    assert identity(a) != identity(d)


def _upload(client, pid, path, name, label="Normal Kat"):
    with open(path, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": (name, f, "application/dxf")},
                        data={"label": label, "storey_count": "3"})
    assert r.status_code == 201, r.text
    return r.json()


def _column_m3(client, pid):
    q = client.get(f"/api/projects/{pid}/quantities").json()
    return {g["key"]: g for g in q["summary"]["groups"]}["column"]["concrete_m3"]


def _pid(client):
    return client.post("/api/projects", json={"name": "Rev", "storey_height": 3.0, "slab_thickness": 0.15}).json()["id"]


def test_new_revision_replaces_old_in_quantities(client, storey_dxf):
    pid = _pid(client)
    eski = _upload(client, pid, storey_dxf, "kat - 04.01.2024.dxf")
    tek = _column_m3(client, pid)
    yeni = _upload(client, pid, storey_dxf, "kat - 21.11.2025.dxf")
    assert yeni["revision"] == "2025-11-21" and yeni["superseded_by"] is None
    assert any("Revizyon" in w for w in yeni["warnings"])
    liste = {d["id"]: d for d in client.get(f"/api/projects/{pid}/drawings").json()}
    assert liste[eski["id"]]["superseded_by"] == yeni["id"]          # eski silinmedi, listede duruyor
    assert _column_m3(client, pid) == pytest.approx(tek)             # iki kez sayılmadı


def test_older_revision_uploaded_later_is_not_counted(client, storey_dxf):
    pid = _pid(client)
    yeni = _upload(client, pid, storey_dxf, "kat - 21.11.2025.dxf")
    eski = _upload(client, pid, storey_dxf, "kat - 04.01.2024.dxf")
    assert eski["superseded_by"] == yeni["id"]
    assert any("ESKİ" in w for w in eski["warnings"])
    liste = {d["id"]: d for d in client.get(f"/api/projects/{pid}/drawings").json()}
    assert liste[yeni["id"]]["superseded_by"] is None


def test_undated_reupload_wins_and_different_floor_is_kept(client, storey_dxf):
    pid = _pid(client)
    a = _upload(client, pid, storey_dxf, "kat.dxf")
    b = _upload(client, pid, storey_dxf, "kat.dxf")
    c = _upload(client, pid, storey_dxf, "kat.dxf", label="Zemin Kat")    # başka kat: revizyon değil
    liste = {d["id"]: d for d in client.get(f"/api/projects/{pid}/drawings").json()}
    assert liste[a["id"]]["superseded_by"] == b["id"]
    assert liste[b["id"]]["superseded_by"] is None and liste[c["id"]]["superseded_by"] is None


def test_make_current_and_delete_restore_old(client, storey_dxf):
    pid = _pid(client)
    eski = _upload(client, pid, storey_dxf, "kat - 04.01.2024.dxf")
    yeni = _upload(client, pid, storey_dxf, "kat - 21.11.2025.dxf")
    r = client.post(f"/api/drawings/{eski['id']}/make-current")
    assert r.status_code == 200 and r.json()["superseded_by"] is None
    liste = {d["id"]: d for d in client.get(f"/api/projects/{pid}/drawings").json()}
    assert liste[yeni["id"]]["superseded_by"] == eski["id"]
    # geçerli olanı sil → öteki geri hesaba girer
    assert client.delete(f"/api/drawings/{eski['id']}").status_code == 204
    liste = {d["id"]: d for d in client.get(f"/api/projects/{pid}/drawings").json()}
    assert liste[yeni["id"]]["superseded_by"] is None


def test_every_project_drawing_query_filters_superseded():
    """Tek kapı: projedeki çizim sorguları eski revizyonu dışlar. Yalnız liste (geçmişi gösterir) ve proje
    silme (hepsini siler) bilerek süzmez; yeni bir sorgu süzgeçsiz eklenirse bu test yakalar."""
    kok = Path(__file__).resolve().parents[1] / "app"
    izinli = {("drawings.py", "return [drawing_out"), ("projects.py", "for d in session.exec")}
    kacak = []
    for p in kok.rglob("*.py"):
        for no, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"select\(Drawing\)\.where\(Drawing\.project_id ==", satir) and "superseded_by" not in satir:
                if not any(p.name == f and frag in satir for f, frag in izinli):
                    kacak.append(f"{p.name}:{no}")
    assert not kacak, kacak
