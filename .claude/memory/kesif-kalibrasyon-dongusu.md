---
name: kesif-kalibrasyon-dongusu
description: "Metraj doğruluğunu ölçerek artırma yolu — çizimin kendi metraj tablosu referanstır, app/calib korpusu + gerileme kapısı"
metadata: 
  node_type: memory
  type: project
  originSessionId: a7d26364-c44b-4e85-8e3f-2fd3b5d3c70b
  modified: 2026-09-12T08:26:46.650Z
---

12 Eyl 2026: Kullanıcı "web'deki projelerle kendini eğit, metraj çıkar, doğru metrajla karşılaştır, hatanı gör
ve düzelt — bir metraj canavarına dönüş" dedi. Araştırıldı: **web'de (çizim + doğrulanmış metraj) eşleşmiş
açık veri seti yok** (arama yalnız ticari yazılım ve patent veriyor; Türk siteleri DWG proje paylaşıyor ama
metraj eşleşmesi ve lisans yok).

**Asıl kaynak dosyanın içinde:** Türk statik ofisleri kendi icmallerini paftaya çiziyor.
- `TABLE4` (B Blok) = müellifin kat bazında KALIP m² / BETON m³ tablosu → beton/kalıp referansı
- `VM-METRAJ` (A4-A5), `mtr_tb` / `mtr_k` / `POZ` = donatı metraj tablosu → zaten okunuyor (demirin %99,3'ü)
Yani her proje dosyası kendi cevap anahtarını taşıyor; "eğitim verisi" toplamak gerekmiyor.

Kurulan: `backend/app/calib/` — korpus (`corpus.py`), ölçüm (`runner.py`), teşhis (`diagnose.py`), CLI
(`python -m app.calib [--kaydet] [--korpus X]`), korpus dosyaları `backend/calib/corpus/*.json`,
taban `backend/calib/taban.json`. 13 test (`tests/test_calib.py`).

**Teşhis mantığı** (asıl değerli kısım): kolon/perde betonu ve kalıbı farklı yükseklik kullanır
(Hk = H ya da H−d; Hf = H − kiriş). Geometri doğruysa oran doğrudan yüksekliğe düşer, yani
`h_doğru = h_kullanılan × referans / bizim` ile geri hesaplanır. Sonuç formüldeki adaylardan birine denk
düşüyorsa suçlu bir **kabul**, hiçbirine düşmüyorsa suçlu **eleman tespiti**.

İlk koşu (B Blok, 3 kat): genel ortalama mutlak sapma %2,14, en kötü %4,71. Kalıp eskiden %15–25 fazlaydı;
kiriş altı düzeltmesi bağımsız doğrulandı. Gerileme kapısı kasten sokulan hatayla denendi (%2,14 → %7,46,
çıkış kodu 1).

**Açık soru:** bodrum ve 1. katta geri hesap "beton yüksekliği H−d olmalı" diyor (müellif brüt kabul
kullanmış), ama zemin katı ve A4-A5 net kabulü destekliyor. Tek dosyaya bakıp kural değiştirilmedi.

**Why:** Kullanıcı gerçek ihale güveni istiyor; sezgisel kuralın "iyileşti" iddiası ölçülmeden kabul edilemez
(bkz. [[kesif-gercek-dosya-dogrulama]]). Kalıcı olan düzeltme değil, ölçüm düzeneğidir.
**How to apply:** Metrajı etkileyen her değişiklikten sonra `python -m app.calib` çalıştır; gerileme varsa
çıkış kodu 1 olur. Yeni gerçek proje geldiğinde önce içinde metraj tablosu ara (TABLE4 / VM-METRAJ / mtr_*),
varsa korpusa ekle. Referansın `guven` alanı her zaman dolsun; "eşleşti" ≠ "doğru", yalnız müellifle aynı
kabulü kullandığımız anlamına gelir. İlgili: [[kesif-guven-paketi]], [[kesif-projesi-hedef]]
