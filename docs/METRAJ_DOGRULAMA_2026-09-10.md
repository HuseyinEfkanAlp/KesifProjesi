# Metraj güvenilirliği: düzeltme ve doğrulama

## Yapılan düzeltmeler

1. Plan sınıflandırması: REBAR_DET / donatı detay katmanları ana donatı planı kanıtından ayrıldı. Gerçek üst/alt donatı planı katmanları ve açık donatı başlıkları korunuyor. Genel “kat planı” başlığında geometrik katman kanıtı kullanılıyor; açık “mimari” başlığı ve kullanıcı seçimi korunuyor.
2. Kat yüksekliği: paftaya girilen yükseklik > projeye girilen yükseklik > otomatik kot çıkarımı > varsayılan. Proje yüksekliği 0 olduğunda otomatik mod çalışıyor. Böylece kiriş altı veya ara kot, kullanıcının açık yüksekliğini değiştiremiyor.
3. Kontrol özeti: metraj ve maliyet API'leri `quality` alanıyla eksik paftaları, sıfır elemanlı çizimleri, eşleşmeyen etiketleri, dışlanan/düşük güvenli elemanları, oran donatısını ve reçete/türetme kabullerini taşıyor. Kontrol özeti, metraj/maliyet ekranında ve Excel'in ilk `Kontrol` sayfasında gösteriliyor.
4. Maliyet sonucu “hesaplanan tutar (taslak)”, süre “süre senaryosu (tahmini)” olarak sunuluyor. Yalnız işçilik fiyatı eksikken de eksik fiyat uyarısı görünür.

## Gerçek pafta doğrulaması

Dört B Blok kırpılmış paftası, yeni projelerle geçici veritabanında API üzerinden işlendi. Kullanıcının mevcut proje verileri değiştirilmedi.

| Pafta | Önce otomatik eleman | Sonra otomatik eleman |
|---|---:|---:|
| Bodrum ilk yarı | 940 | 940 |
| Bodrum ikinci yarı | 0 | 1142 |
| Zemin | 0 | 830 |
| Birinci kat | 852 | 852 |
| Sentetik statik kat planı | 0 | 8 |

Zemin kolon + perde betonunda, plan tipi elle düzeltildikten sonra bile eski yükseklik önceliğiyle 680,478 m³ çıkıyordu. H=3,80 m kullanıcı değeri doğru uygulanınca 728,400 m³ çıktı. Kayıtlı 731,31 m³ referansa fark −%6,95'ten −%0,40'a indi. Kalıp 2.932,568 m²; 2.996,27 m² referansa fark −%2,13.

Bodrum kolon + perde beton farkı +%3,90; birinci kat +%4,71 olarak kaldı. Bu farkları referansa yaklaşsın diye katsayıyla kapatmadık. Eleman, kot bölgesi ve ölçü kuralı bazında bağımsız inceleme gerekiyor.

Referanslar `samples/b_blok/README.md` içindeki TABLE4 aktarımıdır. Orijinal referans tablosunun bağımsız yeniden ölçümü yapılmadı. Bu karşılaştırma tek başına kesin metraj onayı değildir.

## Kullanım ve kalan sınırlar

- Eski kayıtlardaki yanlış disiplin seçimi kendiliğinden değişmez; ilgili paftanın plan tipi/disiplini düzeltilip yeniden analiz edilmelidir. Kullanıcının manuel tip/eleman kararları otomatik yeniden yazılmadı.
- Proje H değeri pozitifse bütün paftalar için genel yükseklik olarak kullanılır; farklı katlar için pafta yüksekliği girilmeli, kotlardan otomatik hesap için genel H=0 olmalıdır.
- Varsayılan malzeme sınıfı veya kullanıcı girişi, çizimden doğrulanmış malzeme sayılmaz.
- Eşleşmeyen döşeme/kiriş etiketleri hâlâ kontrol gerektirir; bu düzeltme onların hepsini ölçmüş değildir.
- `quality.certified` her zaman false'dur. Kontrollerin temiz çıkması bağımsız mühendislik onayı üretmez. İnceleme/onarım uyarıları miktarları zorla sıfırlamaz; mevcut hesap taslağını görünür bırakır.
- Reçete ve oran değerleri proje şartnamesine göre doğrulanmalıdır. Kesin kabul için aynı kapsamda bağımsız eleman/mahal bazlı referans metraj gerekir.

## Tekrarlanabilir kontroller

`backend/tests/test_planset.py`: detay katmanı, genel kat başlığı, açık mimari ve donatı başlıkları, otomatik örnek yükleme regresyonları.

`backend/tests/test_levels.py`: açık proje/pafta yüksekliği önceliği ve otomatik moda dönüş.

`backend/tests/test_quality.py`: boş pafta, eşleşmeyen geometri, varsayılan/kullanıcı kaynağı, oran demiri, eksik işçilik, API ve Excel kontrol özeti.

Yerel deneme çıktıları: `work/validation-2026-09-10/after-fix/results.json`, `height-fix/results.json`, `final-classification.json`.

Son doğrulama: tüm backend testleri 289 başarılı, 1 atlanan (DWG testi ODA erişimiyle dahil); frontend TypeScript + üretim derlemesi başarılı. Mevcut bağımlılıkların deprecation uyarıları sürüyor.
