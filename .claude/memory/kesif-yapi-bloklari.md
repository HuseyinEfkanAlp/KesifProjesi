---
name: kesif-yapi-bloklari
description: Kullanıcının projesinin tipolojisi (birleşik bodrum+zemin podyum + C1..C4 kuleler) ve programa eklenen blok kavramı — 10 Eyl 2026
metadata: 
  node_type: memory
  type: project
  originSessionId: 8bd81ab0-8cc3-4a8d-a87e-b4a0842db2b0
  modified: 2026-09-10T07:33:50.422Z
---

10 Eyl 2026: Kullanıcı yeni bir ruhsat projesi açacak. Tipoloji: **bodrum ve zemin katlar birleşik**
(ortada koridor, tek yapı), üstünde **C1 / C2 / C3 / C4** blokları. Statik tek DWG (bütün paftalar),
mimari **blok blok ayrı dosyalar**.

Eklenen: `parser/blocks.py`, `Drawing.block` ("" = ortak / tüm bina), `Drawing.blocks_seen`,
`services.project_blocks`, blok başına plan seti kontrolü ("partial"), `_plan_footprints`'te (blok, kot)
eşleştirmesi, blok başına çatı + podyum terası.

**Blok listesi kullanıcıdan sorulmaz, çizimden okunur** (kullanıcı düzeltmesi: 10 Eyl 2026, "bir projenin kaç
bloğunun olduğunu program kendi çıkarmalı"). İki kanıt: pafta başlığındaki en iri "… BLOK" yazısı paftanın
bloğu (gerçek dosyada `Başlık_Yazı` katmanında "A4-A5 BLOK"), vaziyet planı sitenin tamamı (aynı dosyada
VAZİYET bloğunun içinde 22 ad: A1..C4, N, T, U). Vaziyet keşiften geniş olabilir → eksik saymaz, hatırlatır.
`Project.blocks` yalnız düzeltmedir.

**Why:** Program blok bilmediği için üç şey sessizce bozuluyordu — eksik bir bloğun mimarisi uyarı vermiyordu,
farklı blokların aynı kotu birbirini eliyordu (cephe eksik), çatı tek bloğunki sayılıyordu.
**How to apply:** Çok bloklu projede "tek bina" varsayan her yeri gözden geçir: kot / kat eşleştirmesi, oturum,
çatı, cephe, kat yüksekliği havuzu. Ortak (birleşik) katlar blok başına aranmamalı. **Hâlâ açık:** metraj,
maliyet ve süre blok bazında ayrışmıyor (tek toplam çıkıyor); ruhsat/ihale düzeninde blok kırılımı isteniyorsa
sıradaki iş bu. İlgili: [[kesif-projesi-hedef]], [[kesif-guven-paketi]]
