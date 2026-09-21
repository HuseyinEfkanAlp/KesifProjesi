---
name: kesif-arayuz-sade
description: "Kullanıcı arayüzü karışık buldu; özet kompakt tek satırlık liste olmalı, tanıdık çizim tablosu görünür kalsın, ayrıntı katlanır"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8e3dfcaa-4364-46e2-ad27-5d521fbc4060
  modified: 2026-09-08T07:38:51.088Z
---

8 Eyl 2026: Kullanıcı "biraz fazla karışık geldi" dedi; ilk sadeleştirme denemem (özet tablosunda her satırda
select + Elemanlar/Sil butonu + sarkan not metni, çizim tablosunun katlanır bölüme saklanması) "berbat" bulundu.
Kabul gören hal: en üstte durum noktası + ad + tip + bulunanlar + tek satıra kırpılmış not (giriş alanı ve buton yok),
altında eski "Çizimler" tablosu görünür ve 1400 px'e sığar; plan seti ve sistemler katlanır `<details>`.

**Why:** Kullanıcı "program çizimimden ne anladı?" sorusunu bir bakışta görmek istiyor ama alıştığı düzenleme
tablosunu kaybetmek istemiyor; kalabalık satırlar ve sarkan metin "berbat" algısı yaratıyor.
**How to apply:** Özet bölümlerine etkileşim (select, buton) koyma, metni `text-overflow: ellipsis` ile tek satırda tut,
var olan tabloları gizleme; yeni bilgi için özet satırına sütun ekle, ayrıntıyı Elemanlar sayfasına bırak. Değişiklikten
sonra Playwright ekran görüntüsüyle 1400 px'te taşma kontrolü yap. İlgili: [[kesif-projesi-hedef]], [[kesif-projesi-ortam]]
