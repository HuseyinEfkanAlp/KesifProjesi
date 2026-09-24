"""Kullanım türü: katın dükkân mı daire mi olduğu yazılardan; kaba teslim yalnız dükkân katlarına."""
from __future__ import annotations

import pytest

from app.parser.usage import floor_usage, scan_texts


@pytest.mark.parametrize("yazilar, tur", [
    (["DÜKKAN 3", "DÜKKAN 4", "LOBİ"], "ticari"),
    (["MAĞAZA", "VİTRİN 1"], "ticari"),
    (["DAİRE 5", "YATAK ODASI", "SALON"], "konut"),
    (["3+1", "BALKON"], "konut"),
    (["OTEL ODASI", "RESEPSİYON"], "otel"),
    (["OFİS 2", "TOPLANTI ODASI"], "ofis"),
    (["RESTORAN", "MUTFAK"], "sosyal"),
    (["VERGİ DAİRESİ", "DAİRE BAŞKANLIĞI", "KOLON", "S101"], ""),       # antet: konut kanıtı değil
    (["1/100", "+4.00", "-0.15 (+4.00)"], ""),
    (["YATAR DAIRE(2)", "YATAR DAİRE(1) 400*4000cm"], ""),               # C1 genel bodrum: geometri adı
])
def test_kat_turu_yazilardan(yazilar, tur):
    assert floor_usage(scan_texts(yazilar))[0] == tur


def test_uzun_not_kanit_sayilmaz():
    uzun = "Konut alanlarında kullanılacak tüm malzemeler TSE belgeli olacak ve şantiye şefinin onayı alınacaktır. " * 2
    assert scan_texts([uzun]) == {}


def test_dukkan_ve_konut_lobisi_ayni_katta_dukkan_kati():
    tur, neden = floor_usage(scan_texts(["DÜKKAN 1", "DÜKKAN 2", "KONUT GİRİŞİ"]))
    assert tur == "ticari" and "DÜKKAN" in neden


def test_alan_cizgisi_dukkan_bolgesi_ticari_kanit():
    tur, neden = floor_usage({}, [{"kind": "dukkan"}, {"kind": "ortak"}])
    assert tur == "ticari" and "dükkân bölgesi" in neden


def _proje(s, pid, katlar):
    from app.models import Drawing
    out = []
    for label, usage in katlar:
        d = Drawing(project_id=pid, filename="c1.dxf", stored_path="x", label=label, block="C1",
                    discipline="architectural", plan_type="mim_kat_plani", zones=[], usage=scan_texts(usage))
        s.add(d)
        out.append(d)
    s.commit()
    return out


def test_karma_yapida_konut_kati_tam_teslim(client, monkeypatch):
    """Zemin dükkân, 1. kat daire, proje "dükkânlar kaba teslim": tavan = dükkân katının ortak alanı +
    konut katının bütün oturumu; dükkân katının oturumu girmez. Duvar yüzü kuralı yalnız dükkân katında."""
    from sqlmodel import Session, select

    from app import db, services
    from app.models import Drawing, Project
    pid = client.post("/api/projects", json={"name": "Karma", "params": {"tenant_shell": 1}}).json()["id"]
    with Session(db.engine) as s:
        zemin, birinci = _proje(s, pid, [("C1 BLOK / ZEMİN KAT PLANI", ["DÜKKAN 1", "DÜKKAN 2"]),
                                         ("C1 BLOK / BİRİNCİ KAT PLANI", ["DAİRE 3", "DAİRE 4", "YATAK ODASI"])])
        p = s.get(Project, pid)
        p.common_areas = [{"blok": "C1", "kat": 0, "tur": "lobi", "alan": 40.0}]
        s.add(p)
        s.commit()
        assert services.shell_floor(zemin) and not services.shell_floor(birinci)
        fps = [{"drawing": zemin.label, "drawing_id": zemin.id, "block": "C1", "area": 500.0, "perimeter": 90.0, "sides": [], "storey_height": 4.0, "source": "architectural", "storey_count": 1, "basement": False},
               {"drawing": birinci.label, "drawing_id": birinci.id, "block": "C1", "area": 450.0, "perimeter": 86.0, "sides": [], "storey_height": 3.0, "source": "architectural", "storey_count": 3, "basement": False}]
        monkeypatch.setattr(services, "_plan_footprints", lambda *a, **k: fps)
        ds = s.exec(select(Drawing).where(Drawing.project_id == pid)).all()
        tavan = [i for i in services.project_boq(s.get(Project, pid), s) if i.kind == "tavan_siva_boya"]
        assert len(tavan) == 1 and tavan[0].quantity == pytest.approx(40.0 + 450.0 * 3)
        assert "tam teslim" in tavan[0].notes[0]
        u = services.project_usage(ds)
        assert u["mixed"] and u["kinds"] == ["konut", "ticari"]
    r = client.get(f"/api/projects/{pid}").json()
    assert {k["usage"] for k in r["usage"]["floors"]} == {"ticari", "konut"}


def test_dukkan_yazisi_varsa_kaba_teslim_sorulur_konutta_sorulmaz(client):
    from sqlmodel import Session, select

    from app import db, services
    from app.models import Drawing, Project
    from app.services import load_catalog
    for katlar, sorulur in (([("ZEMİN KAT PLANI", ["MAĞAZA 1"]), ("1. KAT PLANI", ["DAİRE 2"])], True),
                            ([("ZEMİN KAT PLANI", ["DAİRE 1"]), ("1. KAT PLANI", ["DAİRE 2"])], False)):
        pid = client.post("/api/projects", json={"name": "S"}).json()["id"]
        with Session(db.engine) as s:
            _proje(s, pid, katlar)
            ds = s.exec(select(Drawing).where(Drawing.project_id == pid)).all()
            p = s.get(Project, pid)
            _, check = services.derived_items(p, s, load_catalog(), [], ds, services.project_params(p))
        assert any(c["code"] == "kiraci_kaba_teslim" for c in check) is sorulur
