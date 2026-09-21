---
name: kesif-gercek-dosya-dogrulama
description: Sezgisel (heuristic) kod değişikliği kullanıcının gerçek DXF'lerinde ölçülmeden bitmiş sayılmaz; .sheets.json önbelleği baseline olarak güvenilmez
metadata:
  type: feedback
---

10 Eyl 2026: Kullanıcı pafta bölmeyi ve eleman parçalanmasını "amatör, bizi yanıltır" diye eleştirdi.
Testler (272 birim testi) yeşilken bile gerçek dosyalarda sonuç kullanılamaz haldeydi.

**Why:** Bu projedeki kodun büyük kısmı sezgisel — eşikler, kümeleme, katman tanıma. Birim testleri
yapay küçük DXF'lerle çalışır ve gerçek ruhsat dosyalarındaki kaçak nesne, iç içe layout dikdörtgeni,
alt başlık gürültüsü gibi durumları hiç görmez. Bir dosyada işe yarayan kural başka dosyada paftaları
paramparça edebiliyor.

**How to apply:** Sezgisel bir kuralı değiştirirken önce `backend/data/uploads/src_*.dxf` ve
`work/a4a5/oda/*.dxf` üzerinde ölç, tablo halinde önce/sonra çıkar, her dosyada gerileme olmadığını
göster. Karşılaştırma tabanı olarak yanındaki `.sheets.json` önbelleğini KULLANMA — eski kod
sürümünden kalmış olabilir (kiriş dosyasında önbellek 100 pafta diyordu, aynı kod 29 üretiyordu);
gerçek taban için `git show HEAD:<dosya>` ile o anki kodu çalıştır. Tek bir yönteme bağlanmak yerine
birkaç aday üretip puanlamak (bkz. `scan_sheets` içindeki dört bölümleme) dosyalar arası
dayanıklılığı belirgin artırıyor. İlgili: [[kesif-guven-paketi]], [[kesif-projesi-hedef]]
