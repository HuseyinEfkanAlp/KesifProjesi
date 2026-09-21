---
name: kesif-guven-paketi
description: "9 Eyl 2026 güven paketi: dört bağımsız inceleme sonrası kapatılan zayıf noktalar, doğrulanmış gerçek-veri değerleri ve hâlâ açık kalanlar"
metadata: 
  node_type: memory
  type: project
  originSessionId: 208d646b-dfcc-4fb6-96cc-37d7a314029c
  modified: 2026-09-09T11:04:54.218Z
---

9 Eyl 2026: Kullanıcı "zayıf nokta kalmasın, güven yüksek olsun, demir tonajları önemli, her şey incelensin" dedi.
Dört paralel inceleme (demir, statik, mimari/elektrik/mekanik, altyapı) yapıldı; ~60 bulgu iki commit'te kapatıldı
(26c293b, sonrası). Testler 226 → 241.

Gerçek veri doğrulaması (A4-A5, work/a4a5/oda): demir tabloları temel 635,5 t / kolon 633,0 t / döşeme 272,3 t birebir;
kiriş poz satırı 7.987 (kaynakla aynı; eskiden 8.264 çift sayım) → 604,6 t. Statik: +15.65'te döşeme 104 → 163
(kayan-nokta gürültüsü, `shapely.set_precision(…, 0.001)`), kolon kesit uyuşmazlığı 48 → 3, sahte radye kutuları dışarıda.
README'deki A4-A5 tablosu yeni değerlerle güncellendi (beton 14.815 m³, kalıp 43.348 m², demir 2.156 t).

Hâlâ açık / düşük güven: perde demiri oranla (7–10 t); +7.95'te 34 kiriş etiketi hiçbir kirişe atanmadı (uyarıda listelenir,
elle eklenir); elektrik ve mekanik sezgisel dedektörler hâlâ yalnız sentetik çizimle test edildi (gerçek pafta yok);
kablo tavası ÇŞB pozu (35.190.1100) birimi doğrulanamadı; geri dolgu pozu bulunamadı; duvar köşe payı sezgisel.

**Why:** Kullanıcı gerçek ihale düzeninde güvenilir tonaj istiyor; hangi sayının doğrulanmış olduğu bilinmeli.
**How to apply:** Yeni kalibrasyonda önce `scratchpad`'siz olarak `backend/tests` + README "Güven paketi" bölümüne bak;
demir için kaynak alanı (tablo / poz / elle / oran) her zaman korunmalı; oran her zaman düşük güven.
İlgili: [[kesif-projesi-hedef]], [[kesif-standart-poz]], [[kesif-projesi-ortam]]

10 Eyl 2026 — proje sıfırdan kurulup yeniden doğrulandı (5 DXF, 51 pafta, API üzerinden). Dört hata daha çıktı ve
kapatıldı: (1) döşeme donatı tablosunun yanına düşen kiriş adı 226 t döşeme demirini kirişe yazıyordu — tablo
yanındaki ad artık yalnız kolon↔perde arasında hedef değiştirebiliyor; (2) "İLAVE DONATI PLANI" adında TEMEL
geçmediği için döşeme sayılıyordu (66,5 t) — plan tipi "döşeme donatısı" ise dosya adı soruluyor; (3) kalıp planı
döşeme kotuyla, kolon donatı paftası kolon üst kotuyla adlandırıldığı için kolon demiri hem tablodan hem oranla
sayılıyordu (+120 t) — kot 1,5 m'ye kadar yakınsa eşleştiriliyor, ayrıca adında kot yazmayan paftada çizimden
okunan kot kullanılıyor; (4) vaziyet planı (1/1000) metraja girip 1.073 m² sahte ytong duvarı üretiyordu —
mim_vaziyet artık analyze=False.

Son durum (referans 9 Eyl): beton 14.918/14.815, kalıp 44.611/43.348, demir 2.163/2.156. Çap bazında sapma
−0,4%..+0,2%. Tablo ve poz kaynaklı 2.145,5 t birebir; oranla tahmin yalnız 17,6 t (perde + parapet, uyarılı).
Kalıp farkının tamamı kiriş yan kalıbı yüksekliğini belirleyen döşeme kalınlığından (beton d'den bağımsız,
o yüzden birebir). Duvar m² formülü iki paftada elle doğrulandı: uzunluk × yükseklik − boşluklar, fark 0,00 m².

11 Eyl 2026 — üçüncü sıfırdan doğrulama (5 DXF, API üzerinden, izole veritabanı). Sınıflandırma: 51 kutu → 50 plan
elle düzeltmesiz tanındı, 1 boş çerçeve elendi; statik plan seti 6/6 tam. Metraj **H=0 (kottan otomatik)** ile
14.900 m³ / 44.541 m² / 2.163,1 t — 10 Eyl referansına %0,12–0,16, demirde %0,00. Demirin %99,3'ü tablo+poz
(sert kanıt), %0,7'si oran. Aynı kurulum var olan projeyle birebir (%0,00) çıktı: boru hattı tekrarlanabilir.

**Kritik tuzak:** yeni proje formunun varsayılanı H=3,0 m; `services.storey_heights` sırası "projeye girilen H >
kot" olduğu için bu varsayılan çizimdeki kotları eziyor. A4-A5'te bedeli 358 m³ beton + 1.496 m² kalıp (%2,4).
Artık `storey_height_override` uyarısıyla bildiriliyor ama **çözüm kullanıcıda**: değişken katlı binada H=0 olmalı.

Açık kalan (ölçüldü): 45 kiriş etiketi hiçbir kirişe atanmadı (~95 m³, betonun %0,66'sı; demiri pozdan geldiği
için demir etkilenmiyor), 4 döşeme etiketi (D1000..D4000) kapalı hücreye düşmedi, 5 paftada birim $INSUNITS ile
çelişiyor (kanıtla cm'e çevriliyor ama "blocking" işaretleniyor — ağırlık fazla).
