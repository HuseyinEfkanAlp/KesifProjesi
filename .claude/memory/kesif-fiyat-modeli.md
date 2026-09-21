---
name: kesif-fiyat-modeli
description: "Keşif projesinde birim fiyat modeli: işçilik kaleme, malzeme ürüne girilir (kullanıcı kararı, 9 Eyl 2026)"
metadata:
  type: feedback
---

Kullanıcı birim fiyatların iki ayrı eksende girilmesini istedi (9 Eyl 2026):
1. **İşçilik** fiyatı keşif kalemine (poza) — ₺/birim, adam-saat/birim, ekip.
2. **Malzeme** fiyatı kaleme değil **ürüne** — "perde betonu / kolon betonu" diye fiyat olmaz; "C30/37 hazır beton",
   "Ø12 nervürlü demir", "Ytong 20 cm" diye olur. Aynı ürünü kullanan bütün kalemler tek fiyattan hesaplanır.

Uygulama: `backend/app/cost/materials.py` kalem → ürün eşlemesi (beton sınıfı eleman tipine göre, demir çapı,
kalıp malzemesi; duvar / kablo / tava / kapı zaten ürün bazında gruplu). Hangi elemanda hangi ürünün kullanıldığı
Birim Fiyatlar sayfasındaki **ürün seçimi** panelinden (proje parametreleri: `concrete_class`,
`concrete_class_<eleman>`, `lean_concrete_class`, `rebar_grade`, `formwork_material`).

3. **Fiyatlar proje bazlı değil merkezi** olsun: sol menüdeki "Fiyatlar ve tedarikçiler" sayfası (rota `/pricebook`)
   bütün ürünlerin fiyatını tutar, yeni projeler oradan dolar. Bir ürüne birden çok tedarikçi fiyatı girilir,
   geçerli fiyat seçilen ya da en düşük olandır (`Supplier`, `PriceBookItem`, `backend/app/cost/pricebook.py`).

**Why:** Şantiyede fiyat sorulan şey imalatın adı değil satın alınan üründür; aynı beton dört elemanda geçer,
fiyat bir kez girilmelidir. Kullanıcı fiyatları her projede yeniden girmek istemiyor.
**How to apply:** Yeni bir tür eklerken malzeme fiyatını kaleme koyma; ürün anahtarı üret ya da kalemi zaten
ürün bazında grupla. Birimi "saat" olan kalemler salt işçiliktir, malzeme satırı istemez.
İlgili: [[kesif-projesi-hedef]], [[kesif-arayuz-sade]], [[kesif-standart-poz]]
