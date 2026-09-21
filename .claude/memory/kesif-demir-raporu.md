---
name: kesif-demir-raporu
description: "Kullanıcının en çok istediği çıktı: toplam ton demir + çap bazında döküm; Metraj sayfasının ilk paneli ve Excel'de ayrı sayfa"
metadata:
  type: feedback
---

11 Eyl 2026: Kullanıcı yan konulardan sıkılıp asıl isteğini netleştirdi: "attığım plana göre doğru metraj ve
işçilik çıkarsın — ne kadar demir harcıyorum, toplamda şu kadar ton demir; üstüne bastım şu demirden şu kadar
şu demirden bu kadar gibi çıktı gibi."

Veri zaten doğru üretiliyordu ama **ekranda gömülüydü**: toplam, 28 satırlık "Tür toplamları" listesinin içinde
bir satırdı; çap dökümü sayfanın altında katlanmış bir `<details>` içindeydi; üstteki rozetler yalnız **yüzde**
gösteriyordu (Ø8 %22), kilo değil. Yapılan: `quantity/rebar_report.py` çap bazında tek rapor üretiyor
(metraj / oranla / fire sütunları ayrı — sipariş üçünün toplamı), Metraj sayfasının **ilk paneli** oldu
(büyük "2.225,1 ton" + "64.723 saat işçilik" + çap tablosu), Excel'e ayrı "Demir" sayfası eklendi.

**Why:** Üç kaynak (donatı tablosu / oran tahmini / fire) ayrı sütunda kalmalı — hangisinin kanıtı olduğu
görülsün, sipariş sayısı ile metraj kontrolü karışmasın. Çapa bölünemeyen demir gizlenmez, ayrı satır olur.
**How to apply:** Yeni bir toplam üretirken "kullanıcı bunu kaç tıklamada görüyor?" diye sor; doğru sayıyı
üretmek yetmiyor, ilk ekranda olmalı. İlgili: [[kesif-arayuz-sade]], [[kesif-grup-bazli-gosterim]], [[kesif-guven-paketi]]
