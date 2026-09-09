"""Plan seti: başlıktan plan tipi tanıma, eksik plan kontrolü ve API akışı."""
from __future__ import annotations

import pytest

from app.planset import PLAN_TYPES, classify_title, discipline_for, plan_check
from tests.test_sheets import multi_dxf  # noqa: F401


@pytest.mark.parametrize("title, code", [
    ("ZEMİN KAT KALIP PLANI", "sta_kat_kalip"),
    ("+4.15 KOTU KALIP PLANI", "sta_kat_kalip"),
    ("TEMEL KALIP PLANI", "sta_temel_kalip"),
    ("RADYE TEMEL PLANI", "sta_temel_kalip"),
    ("TEMEL DONATI PLANI", "sta_temel_donati"),
    ("1-KIYI İSTANBUL A4-A5 BLOK TEMEL KALIP ve DONATI PLANLARI 10.05.2023", "sta_temel_donati"),
    ("KOLON APLİKASYON PLANI VE DETAYLARI", "sta_kolon"),
    ("KİRİŞ DETAYLARI", "sta_kiris"),
    ("DÖŞEME DONATI PLANI", "sta_doseme_donati"),
    ("KALIP DONATI PLANLARI", "sta_doseme_donati"),
    ("PERDE DETAYLARI", "sta_perde"),
    ("ZEMİN KAT KABLO TAVA PLANI", "elk_tava"),
    ("1. KAT AYDINLATMA PLANI", "elk_aydinlatma"),
    ("ZEMİN KAT KUVVET (PRİZ) PLANI", "elk_kuvvet"),
    ("ZAYIF AKIM PLANI", "elk_zayif"),
    ("YANGIN ALGILAMA PLANI", "elk_zayif"),
    ("ELEKTRİK KOLON ŞEMASI", "elk_kolon_sema"),
    ("ELEKTRİK TESİSAT PLANI", "elk_genel"),
    ("YANGIN TESİSATI PLANI", "mek_yangin"),
    ("SPRİNKLER PLANI", "mek_yangin"),
    ("HAVALANDIRMA PLANI", "mek_hav"),
    ("ISITMA SOĞUTMA PLANI", "mek_isitma"),
    ("SIHHİ TESİSAT PLANI", "mek_sihhi"),
    ("ALTYAPI PLANI", "alt_altyapi"),
    ("YAĞMUR SUYU VE KANALİZASYON PLANI", "alt_altyapi"),
    ("PEYZAJ PLANI", "pey_peyzaj"),
    ("ASANSÖR PLANI", "asn_asansor"),
    ("VAZİYET PLANI", "mim_vaziyet"),
    ("ZEMİN KAT TAVAN PLANI", "mim_tavan"),
    ("ASMA TAVAN PLANI", "mim_tavan"),
    ("DÖŞEME KAPLAMA PLANI", "mim_doseme_kaplama"),
    ("ZEMİN KAT DÖŞEME PLANI", "mim_doseme_kaplama"),
    ("ÇATI PLANI", "mim_cati"),
    ("ÇATI KATI PLANI", "mim_kat_plani"),
    ("KUZEY CEPHE GÖRÜNÜŞÜ", "mim_cephe"),
    ("A-A KESİTİ", "mim_kesit"),
    ("KAPI PENCERE DETAYLARI", "mim_detay"),
    ("ZEMİN KAT PLANI", "mim_kat_plani"),
    ("NORMAL KAT PLANI", "mim_kat_plani"),
    ("A4_BLOK_21.11.25", None),
    ("GENEL NOTLAR", None),
])
def test_classify_title(title, code):
    found = classify_title(title)
    assert (found.code if found else None) == code


def test_classify_uses_fallback_titles():
    """Ana başlık tanınmazsa diğer adaylara bakılır; dosya adı da aday olabilir."""
    assert classify_title("Pafta 3 (başlıksız)", "ZEMİN KAT KALIP PLANI").code == "sta_kat_kalip"
    assert classify_title("", "") is None


def test_discipline_for():
    assert discipline_for("sta_kat_kalip") == "structural"
    assert discipline_for("sta_temel_donati") == "rebar"
    assert discipline_for("elk_tava") == "electrical"
    assert discipline_for("mim_kat_plani") == "architectural"
    assert discipline_for("mim_tavan") == "mapped"
    assert discipline_for("", "structural") == "structural"


def test_plan_check_missing_and_skip():
    ds = [{"id": 1, "label": "Zemin kalıp", "plan_type": "sta_kat_kalip", "discipline": "structural"},
          {"id": 2, "label": "Elektrik", "plan_type": "elk_genel", "discipline": "electrical"},
          {"id": 3, "label": "Notlar", "plan_type": "", "discipline": "structural"}]
    r = plan_check(ds, {"alt_altyapi": "skip"})
    by = {t["code"]: t for g in r["groups"] for t in g["types"]}
    assert by["sta_kat_kalip"]["status"] == "present" and by["sta_kat_kalip"]["drawings"][0]["id"] == 1
    assert by["elk_tava"]["status"] == "missing"
    assert by["mim_tavan"]["status"] == "missing"
    assert by["alt_altyapi"]["status"] == "skipped"
    assert by["sta_perde"]["status"] == "optional_missing"
    # genel elektrik planı aydınlatma ve kuvveti karşılar
    assert by["elk_aydinlatma"]["status"] == "present" and by["elk_aydinlatma"]["via"]
    assert by["elk_kuvvet"]["status"] == "present"
    assert any("Elektrik: Elektrik kablo tava planı yüklenmedi" == w for w in r["warnings"])
    assert any("Mimari: Mimari tavan planı yüklenmedi" == w for w in r["warnings"])
    assert not any("Altyapı planı" in w for w in r["warnings"])
    assert any("tanınamadı" in w for w in r["warnings"])
    assert r["unknown"][0]["id"] == 3 and not r["complete"]
    assert r["missing_required"] == sum(1 for p in PLAN_TYPES if p.level == "required") - 4  # kalıp, aydınlatma, kuvvet, (altyapı skip)


def test_api_plan_flow(client, multi_dxf, storey_dxf, elec_dxf):
    pid = client.post("/api/projects", json={"name": "Plan seti"}).json()["id"]
    r = client.get(f"/api/projects/{pid}/plan-check")
    assert r.status_code == 200
    assert r.json()["present"] == 0 and r.json()["missing_required"] > 0
    assert "Altyapı: Altyapı planı yüklenmedi" in r.json()["warnings"]

    # tek paftalı dosya, disiplin auto: plan tipi dosya adından
    with open(storey_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("ZEMIN KAT KALIP PLANI.dxf", f, "application/dxf")})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["plan_type"] == "sta_kat_kalip" and d["discipline"] == "structural" and d["element_count"] > 0

    with open(elec_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("kablo tava plani.dxf", f, "application/dxf")})
    assert r.status_code == 201, r.text
    assert r.json()["plan_type"] == "elk_tava" and r.json()["discipline"] == "electrical"

    # çok paftalı: paftalarda plan tipi ve disiplin önerisi
    with open(multi_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("ruhsat.dxf", f, "application/dxf")})
    assert r.status_code == 200 and r.json()["needs_sheet_selection"]
    sheets = {s["title"]: s for s in r.json()["sheets"]}
    assert sheets["TEMEL KALIP PLANI"]["plan_type"] == "sta_temel_kalip" and sheets["TEMEL KALIP PLANI"]["discipline"] == "structural"
    assert sheets["ZEMİN KAT KALIP PLANI"]["plan_type"] == "sta_kat_kalip"
    assert sheets["KOLON DETAYLARI"]["plan_type"] == "sta_kolon" and sheets["KOLON DETAYLARI"]["discipline"] == "rebar"
    token = r.json()["source"]["token"]
    r = client.post(f"/api/projects/{pid}/drawings/from-source", json={
        "token": token, "sheets": [{"index": sheets["TEMEL KALIP PLANI"]["index"]},
                                   {"index": sheets["KOLON DETAYLARI"]["index"], "plan_type": "sta_kiris", "discipline": "auto"}]})
    assert r.status_code == 201, r.text
    ds = {d["label"]: d for d in r.json()}
    assert ds["TEMEL KALIP PLANI"]["plan_type"] == "sta_temel_kalip" and ds["TEMEL KALIP PLANI"]["discipline"] == "structural"
    assert ds["KOLON DETAYLARI"]["plan_type"] == "sta_kiris" and ds["KOLON DETAYLARI"]["discipline"] == "rebar"

    chk = client.get(f"/api/projects/{pid}/plan-check").json()
    by = {t["code"]: t for g in chk["groups"] for t in g["types"]}
    assert by["sta_kat_kalip"]["status"] == "present" and by["elk_tava"]["status"] == "present"
    assert by["sta_temel_kalip"]["status"] == "present" and by["sta_kiris"]["status"] == "present"
    assert by["mim_tavan"]["status"] == "missing"

    # bu projede altyapı yok
    r = client.put(f"/api/projects/{pid}/plan-set", json={"alt_altyapi": "skip"})
    assert r.status_code == 200
    by = {t["code"]: t for g in r.json()["groups"] for t in g["types"]}
    assert by["alt_altyapi"]["status"] == "skipped"
    assert client.get(f"/api/projects/{pid}").json()["plan_check"]["missing_required"] == r.json()["missing_required"]
    assert client.put(f"/api/projects/{pid}/plan-set", json={"yok": "skip"}).status_code == 400

    # çizimin plan tipi elle değiştirilebilir
    r = client.patch(f"/api/drawings/{d['id']}", json={"plan_type": "mim_tavan"})
    assert r.status_code == 200 and r.json()["plan_type"] == "mim_tavan"
    assert client.patch(f"/api/drawings/{d['id']}", json={"plan_type": "olmayan"}).status_code == 400

    meta = client.get("/api/projects/meta/plan-types").json()
    assert {t["code"] for t in meta["types"]} >= {"sta_kat_kalip", "elk_tava", "alt_altyapi"}


def test_layers_override_weak_title():
    """'ZEMİN KAT PLANI' adlı ama KOLON / KİRİŞ katmanlı çizim statik kalıp planıdır; DUVAR / KAPI katmanlıysa mimari."""
    from app.planset import discipline_from_layers, resolve_plan
    sta = {"KOLON": 40, "KIRIS": 30, "DOSEME": 10, "AKS": 50, "YAZI": 80}
    arch = {"A-DUVAR-YTONG": 60, "KAPI": 10, "PENCERE": 12, "YAZI": 30}
    elec = {"E-TAVA-200x60": 20, "E-KABLO-5x6": 30, "ARMATUR": 15}
    assert discipline_from_layers(sta) == "structural"
    assert discipline_from_layers(arch) == "architectural"
    assert discipline_from_layers(elec) == "electrical"
    assert discipline_from_layers({"KSF-STA-KOLON": 30, "KSF-MIM-DUVAR-20": 20}) == "standard"
    assert discipline_from_layers({"YAZI": 100, "AKS": 50}) is None
    assert discipline_from_layers({"KOLON": 3}) is None   # çok az nesne

    assert resolve_plan(["ZEMİN PLANI"], sta) == ("sta_kat_kalip", "structural")          # genel "PLAN": katmanlar karar verir
    assert resolve_plan(["ZEMİN KAT PLANI"], sta) == ("mim_kat_plani", "architectural")   # "KAT PLANI" açıkça mimari (statik xref olsa da)
    assert resolve_plan(["ZEMİN KAT PLANI"], arch) == ("mim_kat_plani", "architectural")
    assert resolve_plan(["ZEMİN KAT PLANI"], None) == ("mim_kat_plani", "architectural")
    assert resolve_plan(["Pafta 3 (başlıksız)"], sta) == ("sta_kat_kalip", "structural")
    assert resolve_plan(["Pafta 3 (başlıksız)"], elec) == ("elk_genel", "electrical")
    assert resolve_plan(["Pafta 3 (başlıksız)"], None) == ("", "")
    # güçlü başlık katmanlara bakmaz; açık tip her şeyi ezer
    assert resolve_plan(["KABLO TAVA PLANI"], sta) == ("elk_tava", "electrical")
    assert resolve_plan(["ZEMİN KAT PLANI"], sta, explicit="mim_tavan") == ("mim_tavan", "mapped")
    # kesit başlığı, paftadaki plan başlığına yenilir
    from app.planset import classify_title
    assert classify_title("A-A KESİTİ Ölçek:1/100", "ZEMIN KAT KALIP PLANI (1/100)").code == "sta_kat_kalip"
    assert classify_title("A-A KESİTİ").code == "mim_kesit"


def test_api_weak_title_uses_layers(client, storey_dxf):
    pid = client.post("/api/projects", json={"name": "Katman ipucu"}).json()["id"]
    with open(storey_dxf, "rb") as f:
        r = client.post(f"/api/projects/{pid}/drawings", files={"file": ("ZEMIN PLANI.dxf", f, "application/dxf")})
    assert r.status_code == 201, r.text
    assert r.json()["plan_type"] == "sta_kat_kalip" and r.json()["discipline"] == "structural" and r.json()["element_count"] > 0
