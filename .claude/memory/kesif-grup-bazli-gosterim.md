---
name: kesif-grup-bazli-gosterim
description: "Ön izlemede ve listelerde tek tek eleman değil, aynı kesitteki elemanların adedi gösterilir; tıklama grubu seçer"
metadata:
  type: feedback
---

11 Eyl 2026: Kullanıcı "tek tek kolonlar veya zemin olmasın, aynı oranlarda demir beton kullanılıyorsa adet
olarak olsun — şu kadar şu genişlikte kolon" ve "ön izlemede tıklanabilir çok alan görüyorum, temelde neden
birden fazla yer tıklayabiliyorum" dedi. Çözüm: `backend/app/quantity/grouping.py` tek grup anahtarı üretir
("column|100/100", "foundation|radye 70 cm"); SVG çokgenine `data-group`, eleman API'sine `group`/`section`
olarak gider. Önizlemede tıklama elemanı değil grubu seçer, grubun bütün parçaları yanar, ötekiler solar.

**Why:** Aynı kesitteki elemanlar metre başına aynı betonu/kalıbı/demiri tüketir, aynı birim fiyatla çarpılır;
185 kolonu tek tek görmek bilgi vermiyor. Bölünmüş temel (kirişlerle parçalanmış radye) çizimde çok parça ama
keşifte tek kalem — çok tıklama alanı kullanıcıya "sistem karıştırıyor" hissi veriyordu.
**How to apply:** Yeni bir liste/önizleme eklerken grup anahtarını **backend'de** hesapla, frontend'de tekrar
hesaplama — ikisi ayrılırsa tabloya tıklayınca çizimde başka şey seçilir (test: `tests/test_grouping.py`).
Uzunluk/boy gruba girmez, sürücü boyut girer. İlgili: [[kesif-arayuz-sade]], [[kesif-iscilik-normu]]
