---
name: kesif-iscilik-normu
description: "İşçilik normu ilkesi: birim başına sabit saat yanlış; belirleyici olan ton/kg başına ve çapa, kata, hazır gelme durumuna bağlı norm (10 Eyl 2026)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8bd81ab0-8cc3-4a8d-a87e-b4a0842db2b0
  modified: 2026-09-10T06:40:17.544Z
---

10 Eyl 2026, kullanıcı (inşaatçı) demir işçiliği üzerinden ilkeyi koydu: "Temel donatısında '1 m² kaç adam-saat'
tek başına sabit bir değer değil; asıl belirleyici 1 m²'ye kaç kg donatı düştüğü, donatının çapı, çift kat/tek kat
olması, bindirme-sıklaştırma ve demirin sahada ne kadar hazır geldiği. O demiri hazırlamak, kesmek, ulaştırmak da
ayrı bir işçilik."

Yapılan: demir reçetesi sabit 0,02 saat/kg olmaktan çıktı; `standard/rules.py: REBAR_LABOR_HOURS_PER_TON`
çap bandına göre norm (Ø8–10: 42 sa/t → Ø24–40: 18 sa/t), üç ayrı iş (hazırlık / taşıma / montaj),
`rebar_prefab_pct` hazır demir, çift kat çarpanı ×1,15 + sehpa demiri 25 kg/t. Çift/tek kat çizimden okunuyor
(`parser/rebar_mix.py: scan_layer_tags`, `layer_verdict`) — gerçek A4-A5 paftalarında doğrulandı.

**Why:** Kullanıcı normu "m² başına sabit saat" diye modellemenin fiziksel olarak yanlış olduğunu söyledi;
metrajın kendisi doğru olsa bile yanlış norm süreyi anlamsız yapar.
**How to apply:** Yeni bir kalemin işçilik normunu yazarken önce "bu işin saatini gerçekte ne belirliyor" diye
sor (ölçü birimi değil sürücü değişken), sonra normu o değişkene bağla ve kalan kısmı parametre yap. İşçiliği
tek kalemde toplama: hazırlık / taşıma / montaj gibi sahada ayrı ayrı olabilen (ya da hiç olmayan) işlere ayır.
Norm değerleri ÇŞB analizinden doğrulanmadıysa kod yorumunda ve README'de açıkça "yaygın uygulama varsayılanı"
diye işaretle. İlgili: [[kesif-standart-poz]], [[kesif-guven-paketi]], [[kesif-donati-capi]]
