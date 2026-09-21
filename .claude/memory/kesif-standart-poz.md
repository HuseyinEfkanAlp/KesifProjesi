---
name: kesif-standart-poz
description: "Keşif \"gerçekçi ve doğru\" olacak — ÇŞB poz ve ölçü kuralları, iş grupları, aynı paftada çok disiplin; 8 Eyl 2026 yönü"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8e3dfcaa-4364-46e2-ad27-5d521fbc4060
  modified: 2026-09-08T08:08:51.650Z
---

8 Eyl 2026: Kullanıcı keşfin "daha gerçekçi ve doğru", "doğru bir mimari düzende" olmasını istedi; internetten araştırma
serbest; aynı paftada mimari + elektrik ya da elektrik + mekanik olabileceği unutulmasın; standardımız (KÇS) varsa ona göre.
Yapılan: `backend/app/standard/rules.py` (iş grupları KABA / INCE / MEK / ELK / ALT, ÇŞB poz eşlemesi, ölçü kuralları),
`Drawing.disciplines` ek disiplinler, KSF katmanları her disiplinde ölçülür.

Doğrulanmış ÇŞB kuralları (birimfiyat.net / yfk.csb.gov.tr): gazbeton duvar 15.225.1004/1007/1010 → 0,10 m² altı boşluk
düşülmez; sıva 15.280.1008 ve boya 15.540.1509 → tüm boşluklar düşülür; kalıp 15.180.1003 → kalıp gören yüzler; demir
15.160.1003 (Ø8–12) / 15.160.1004 (Ø14–28) ton; beton 15.150.1006 C30/37 pompalı; NYY 3x2,5 kolon hattı 35.140.3161;
PPRC 25.305.xxxx. Poz numaralarını uydurma: yalnız doğrulananları `DEFAULT_POZ`'a ekle, gerisi katalogda kullanıcı girer.

Reçeteler (8 Eyl 2026, kullanıcı isteği "ayrıntıya kadar işçilikleri çıkart, tüm işleri girelim"): `CatalogItem.recipe`,
`catalog.DEFAULT_RECIPES` (137 kalem), `rules.RECIPES_BY_KIND`, `quantity/recipes.py` zincirleme açılım; işçilik "saat"
birimli ayrı kalem. Çarpanlar yaygın uygulama varsayılanı (kullanıcı katalogdan düzenler); yeni kalem eklerken reçetesini de ver.

**Why:** Kullanıcı gerçek ihale / hakediş düzeninde (iş grubu + poz + ölçü kuralı) keşif bekliyor; sezgisel kalem listesi yetmez.
**How to apply:** Yeni kalem eklerken iş grubunu ve varsa pozunu ver; miktar formülünü ilgili poz tarifinin "ölçü"
cümlesine dayandır ve `RULES` notuna yaz. Sonraki adaylar: mekanik / sıhhi tesisat sezgisel dedektörü (şu an yalnız KSF ya
da katman eşleme), tavan / şap / kaplama için mahal bazlı ince iş metrajı, kalıp iskelesi ve iskele kalemleri.
İlgili: [[kesif-projesi-hedef]], [[kesif-arayuz-sade]]
