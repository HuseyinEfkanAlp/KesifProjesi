---
name: kesif-kanit-siralamasi
description: Kendini yanlışlayan kontroller (selfcheck.py) ve çelişkide hangi sayının esas alınacağını belirleyen kanıt sıralaması
metadata: 
  node_type: memory
  type: project
  originSessionId: a7d26364-c44b-4e85-8e3f-2fd3b5d3c70b
  modified: 2026-09-12T11:44:48.613Z
---

12 Eyl 2026: Kullanıcı "kendini kontrol eden, destekleyen, doğrulayan ve yanlışlayan bir sistem kur" dedi,
ardından "hangi sayı yanlışsa onu göstermesin, doğru olan esas alınsın".

**`app/selfcheck.py`** — sonucu ikinci bir yoldan sınar (`quality.py` "ne eksik" sorar, bu "sayı tutarlı mı").
Temel kural: **dairesel kontrol hiçbir şey kanıtlamaz.** Demiri `beton × oran` ile bulup "oran tuttu" demek
doğrulama değildir; böyle kontrol asla `destekliyor` demez, `kararsiz` der ve `bagimsizlik: "YOK — ..."` yazar.
Sonuç üç değerli: destekliyor / celisiyor / kararsiz. Kontroller: `demir_orani` (demir yazılardan ÷ beton
geometriden; bant TS500 ρ≤%4 → kolonda 400 kg/m³ tavan), `doseme_kalinlik` (beton÷kalıp = 1/t),
`kalip_beton`, `cap_tutarliligi` (keşif çapları ↔ planda yazan çaplar), `kat_tutarliligi`, `toplam_saglama`.
Çelişen kontrol keşifte engelleyici (`selfcheck_conflict`). 15 test; en kritiği
`test_dairesel_kontrol_asla_desteklemez`.

**Kanıt sıralaması** (`services.storey_heights`): çelişkide suçluyu belirleyen şey girdilerin kanıt gücüdür.
çizimden okunan > çizimden türetilen > kullanıcının paftaya girdiği > projeye girilen tek değer / varsayılan.
Uygulanan kural: **projeye girilen tek H, çizimden okunan kotlar kat kat değişiyorsa (yayılım > 0,30 m)
uygulanmaz** — tek sayı değişken katlı binanın hiçbir katında doğru olamaz. Sınırlar: paftaya elle girilen
yükseklik her zaman kazanır; kotlar sabitse kullanıcının H'si korunur (fark bildirilir + tek tıkla düzeltme);
girilen değer silinmez, yalnız uygulanmaz (`storey_height_auto_applied`, inceleme notu).

**A4-A5 etkisi:** beton 14.542 → 14.900,2 · kalıp 43.045 → 44.541,4 · demir 2.160,3 → 2.163,1 t —
bağımsız doğrulanmış değerlere birebir. Kolon donatı oranı 462 (çelişiyor) → 370 kg/m³ (destekliyor;
ölçülen gerçek 374). Kendini kontrol 15/1/2 → 16/0/2.

**Why:** İki bağımsız yol (fizik ve kotlar) aynı hataya işaret etti; kullanıcı sistemin bunu kendi
düzeltmesini istedi. Ama düzeltme ancak kanıt asimetrisi varsa meşrudur — yoksa hangi sayının yanlış
olduğu bilinemez ve sessiz değiştirme hatayı gizler.
**How to apply:** Yeni bir otomatik düzeltme eklerken önce "hangi girdi daha zayıf kanıta dayanıyor" sorusunu
cevapla; asimetri yoksa düzeltme değil **çelişki bildirimi** yap. Kullanıcının açık kararı (paftaya girilen
değer) hiçbir düzeltmeyle ezilmez. İlgili: [[kesif-kalibrasyon-dongusu]], [[kesif-guven-paketi]]
