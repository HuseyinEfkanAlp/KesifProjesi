---
name: kesif-projesi-ortam
description: "KesifProjesi (DXF keşif/metraj) reposunun bu Mac'teki geliştirme ortamı ve çalışma şekli"
metadata: 
  node_type: memory
  type: project
  originSessionId: 74ec39ed-8433-4941-a6e7-8311c1858993
  modified: 2026-09-05T06:52:21.296Z
---

Repo: github.com/HuseyinEfkanAlp/KesifProjesi, dizin `~/Desktop/kesifProjesicld` içine klonlandı (5 Eyl 2026).
Proje Windows'ta (PowerShell, `start.ps1`) geliştirilmişti; Mac'te sistem Python'u 3.9 olduğu için
`backend/.venv` conda ile Python 3.12 olarak kuruldu (`conda create -p backend/.venv python=3.12`). Mac başlatma: `./start.sh`.

Kullanıcı Türkçe yazıyor; geliştirmeyi doğrudan `main` dalına commit + push ile yürütüyor (tek dal, PR yok).
DWG -> DXF: ODA File Converter `~/Applications/ODAFileConverter.app` kurulu (5 Eyl 2026); libredwg `dwg2dxf` bu dosyalarda
katman adlarını kaybediyor, kullanma. Kullanıcı gerçek çizimleri proje köküne atıyor (`*.dwg` gitignore'da); dönüşümler `work/` altında.
Gerçek A4-A5 statik DWG'leri: `~/Desktop/kesifProjesicld/*.dwg`, A1-A5 mimari DWG/DXF: `~/Desktop/daasdas/A BLOK/`.

Tarayıcı doğrulaması (7 Eyl 2026): `chromium-cli` yok; Playwright'ı scratchpad'e `npm i playwright@1.62.0` ile kurunca
`~/Library/Caches/ms-playwright/chromium-1234` önbelleğiyle başsız Chromium indirmesiz çalışıyor (1.63 -> 1243 ister, indirir).
Vite dev 5173, `/api` proxy'si 8000'e; test için backend'i `KESIF_DATA_DIR=<geçici>` ile başlatıp gerçek veriyi koruyun.

**Why:** `python3` çağrısı 3.9'a gider ve proje `X | None` sözdizimi kullanır; testler ve sunucu daima `backend/.venv/bin/python` ile çalıştırılmalı.
**How to apply:** Test: `cd backend && ./.venv/bin/python -m pytest tests -q`. Frontend: `cd frontend && npm run build`. Push için `gh` oturumu açık (HuseyinEfkanAlp).
İlgili: [[kesif-projesi-hedef]]
