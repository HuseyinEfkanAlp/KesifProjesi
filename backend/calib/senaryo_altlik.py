"""Kapsam gerileme senaryosu: aynı pafta iki kez yüklenince metraj ikiye katlanmamalı.

`python -m calib.senaryo_altlik` (backend dizininde) ya da `python calib/senaryo_altlik.py`.

Gerçek bir pafta (B Blok zemin kalıp planı, 830 eleman) tek projeye iki kez yüklenir: biri kat kalıp planı
(kalemin sahibi), öbürü mimari kat planı (altlık). Beklenen: kapsam açıkken toplamlar **tek paftayla
birebir** aynı, kapalıyken tam iki katı. Kapsam kuralına (quantity/scope.py) dokunan her değişiklikten sonra
koşturulur; `python -m app.calib` doğruluk kapısıdır, bu ise çift sayım kapısı.

Çıkış kodu 0 = geçti, 1 = kaldı.
"""
import json, os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["KESIF_DATA_DIR"] = tempfile.mkdtemp(prefix="kesif-altlik-")
from fastapi.testclient import TestClient
from app.main import app

SRC = ROOT / "samples/b_blok/crop_zemin.dxf"
out = {}
with TestClient(app) as c:
    def kur(ad, paftalar, scope_off=None):
        pid = c.post("/api/projects", json={"name": ad, "storey_height": 3.8}).json()["id"]
        if scope_off:
            c.patch(f"/api/projects/{pid}", json={"params": {"scope_off": "1"}})
        for label, ptype, disc in paftalar:
            with open(SRC, "rb") as f:
                r = c.post(f"/api/projects/{pid}/drawings", files={"file": (f"{ptype}.dxf", f, "application/dxf")},
                           data={"label": label, "plan_type": ptype, "discipline": disc})
            assert r.status_code == 201, r.text
        q = c.get(f"/api/projects/{pid}/quantities").json()
        t = {k: round(float(v or 0), 1) for k, v in q["summary"]["totals"].items()}
        return t, q["quality"].get("scope") or {}, {i["key"]: i["quantity"] for i in q["boq"]["items"]}

    tek, _, tek_boq = kur("tek pafta", [("Zemin kalıp", "sta_kat_kalip", "structural")])
    cift, sc, cift_boq = kur("kalıp + mimari altlık",
                             [("Zemin kalıp", "sta_kat_kalip", "structural"),
                              ("Zemin mimari", "mim_kat_plani", "structural")])
    kapali, _, kapali_boq = kur("kapsam kapalı",
                                [("Zemin kalıp", "sta_kat_kalip", "structural"),
                                 ("Zemin mimari", "mim_kat_plani", "structural")], scope_off=True)
    out = {"tek": tek, "kapsam_acik": cift, "kapsam_kapali": kapali,
           "scope": {"dusen": sc.get("duplicate_count"), "eklenen": sc.get("addition_count"),
                     "notlar": [n["message"] for n in (sc.get("notes") or [])]}}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    tamam = (cift == tek and sc.get("addition_count") == 0
             and all(kapali[k] > 1.9 * tek[k] for k in tek if tek[k] > 0))
    print("GEÇTİ: iki pafta = tek pafta, sahte ek yok" if tamam else
          "KALDI: kapsam kuralı beklendiği gibi çalışmadı", flush=True)
    raise SystemExit(0 if tamam else 1)
