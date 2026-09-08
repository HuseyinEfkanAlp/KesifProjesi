# Keşif Çizim Standardı (KÇS) — sürüm 1

Bu doküman, çizimleri **Keşif** programının doğrudan okuyabilmesi için proje müelliflerinin (mimari, statik, elektrik,
mekanik, altyapı, peyzaj…) uyması gereken çizim kurallarını tanımlar. Standarda uygun çizilen her plan, hiçbir katman eşleme
ya da elle düzeltme gerekmeden keşfe (metraj listesine) dönüşür.

## 1. Temel ilke

**Katman adı kalemi tanımlar, geometri miktarı verir.**

```
KSF-<DİSİPLİN>-<KALEM>-<ÖZELLİK>
```

| Alan | Kural | Örnek |
|---|---|---|
| `KSF` | Sabit ön ek. Bu ön eki taşımayan katmanlar metraja **girmez** (yazı, ölçü, aks, antet, mobilya…). | |
| `DİSİPLİN` | 3 harflik disiplin kodu (bölüm 3). | `HAV` |
| `KALEM` | Katalogdaki kalem kodu; büyük harf, kelime arası `_`. | `HAVA_KANAL` |
| `ÖZELLİK` | Serbest: boyut, kesit, çap, malzeme, tip, marka. Bir katmanda **tek** özellik; farklı özellik = farklı katman. Yoksa boş bırakılır. | `600x400` |

Alan ayracı **tire** (`-`), kelime içi ayraç **alt çizgi** (`_`). Türkçe karakter kullanılmaz (Ş→S, Ğ→G, İ→I, Ç→C, Ö→O, Ü→U).

Örnekler:

```
KSF-HAV-HAVA_KANAL-600x400        havalandırma kanalı 600x400 mm       -> m
KSF-HAV-MENFEZ-600x600            menfez 600x600                       -> adet
KSF-SIH-BORU_PVC-100              PVC pis su borusu Ø100               -> m
KSF-SIH-BORU_PPRC_TEMIZ-25        PPRC temiz su borusu Ø25             -> m
KSF-YAN-SPRINKLER-K80_UST         sprinkler K80 üst                    -> adet
KSF-YAN-YANGIN_BORU-DN100         yangın borusu DN100                  -> m
KSF-MEK-BORU_CELIK-DN65           çelik boru DN65                      -> m
KSF-MEK-FANCOIL-4KW               fancoil 4 kW                         -> adet
KSF-ELK-KABLO-NYY_4x16            NYY 4x16 kablo                       -> m
KSF-ELK-TAVA-200x60               kablo tavası 200x60                  -> m
KSF-ELK-ARMATUR-LED_PANEL_60x60   LED panel armatür                    -> adet
KSF-MIM-DUVAR_YTONG-20            Ytong duvar 20 cm                    -> m²  (uzunluk × duvar yüksekliği)
KSF-MIM-DUVAR_YTONG-20x300        Ytong duvar 20 cm, yükseklik 300 cm  -> m²
KSF-MIM-PENCERE-P1_120x140        P1 pencere                           -> adet
KSF-CEP-KOMPOZIT_PANEL-4MM        kompozit cephe paneli                -> m²
KSF-CAT-CATI_MEMBRAN-3MM          çatı membranı                        -> m²
KSF-IZO-XPS-5                     XPS 5 cm                             -> m²
KSF-STA-DOLGU-30                  dolgu 30 cm                          -> m³  (alan × kalınlık)
KSF-ALT-BORU_KORUGE-300           koruge boru Ø300                     -> m
KSF-PEY-CIM-RULO                  rulo çim                             -> m²
KSF-PEY-AGAC-CINAR                çınar                                -> adet
```

## 2. Geometri kuralları (ölçüm tipi)

Her kalemin kataloğunda bir **ölçüm kuralı** vardır; çizim buna uygun yapılır.

| Ölçüm | Birim | Nasıl çizilir | Program ne yapar |
|---|---|---|---|
| **Adet** (`count`) | adet | Her eleman bir **BLOK** (INSERT) olarak yerleştirilir. Blok adı serbesttir. | Blok sayar. Blok yoksa 1.5 m'den küçük kapalı sembolleri sayar ve uyarır. |
| **Uzunluk** (`length`) | m | Çizgi (LINE) ya da polyline; hat kırıklı olabilir. Çift çizgi çizmeyin, **tek eksen çizgisi** çizin. | Tüm çizgi uzunluklarını toplar. |
| **Alan** (`area`) | m² | **Kapalı** polyline ya da tarama (HATCH). Açık polyline alan vermez. | Kapalı alanları toplar; üst üste kopyaları eler. |
| **Duvar alanı** (`wall_area`) | m² | Duvar **eksen çizgisi**; kalınlık özellikte. Yükseklik özellikte 2. sayı olabilir (`20x300`), yoksa projenin duvar yüksekliği. | uzunluk × yükseklik |
| **Hacim** (`volume`) | m³ | Kapalı alan; **kalınlık özellikte cm** olarak zorunlu (`DOLGU-30`). | alan × kalınlık |

Diğer kurallar:

- **Birim mm** (`$INSUNITS = 4`). cm ya da m çizilmişse program yine okur ama dosya başlığında birim doğru olmalı.
- **Her kat / her plan ayrı pafta.** Aynı katmanda iki katın hatları üst üste olmaz. Tip katlar tek çizilir; kaç kat olduğu programda girilir.
- Yazı, ölçü, aks, antet, çerçeve, mobilya, kot, tarama-dekor katmanları `KSF` ile başlamaz.
- Kesit, detay, şema paftaları metraja girmez; planlarla aynı dosyada olabilir.
- Blokların içindeki nesneler katman `0`'da ise INSERT'in katmanını alır (AutoCAD davranışı); bloğu doğru katmana koymak yeter.
- Xref kullanılmaz; DXF'e kaydederken bind edilir.
- Teslim biçimi: **DXF** (AutoCAD 2018, ASCII). DWG kabul edilmez.

## 3. Disiplin kodları

| Kod | Disiplin | Kod | Disiplin |
|---|---|---|---|
| STA | Statik / kaba yapı | MEK | Mekanik (ısıtma / soğutma) |
| MIM | Mimari | HAV | Havalandırma |
| INC | İnce işler | YAN | Yangın tesisatı |
| CEP | Dış cephe | SIH | Sıhhi tesisat |
| CAT | Çatı | ALT | Altyapı |
| IZO | İzolasyon | PEY | Peyzaj |
| ELK | Elektrik | ASN | Asansör / yürüyen merdiven |
| ZAY | Zayıf akım / otomasyon | | |

Yeni disiplin ve kalemler programın **Standart** sayfasından eklenir; katalog `data/catalog.json` içinde saklanır.

### Aynı paftada birden çok disiplin

KÇS katmanı disiplinini kendi adında taşır (`KSF-ELK-…`, `KSF-HAV-…`); bu yüzden bir paftada mimari, elektrik ve mekanik
kalemler birlikte çizilebilir, program her katmanı kendi disiplinine ve iş grubuna yazar. Standart dışı (sezgisel) paftalarda
ise ana disipline ek disiplin açılır (proje sayfası, "+ Elektrik").

### Poz numarası ve ölçü kuralı

Katalogdaki her kaleme ÇŞB birim fiyat **poz numarası** girilebilir (Standart sayfası); keşifte kalem o pozla listelenir ve
Excel'e yazılır. Miktarlar pozların ölçü kurallarına göre hesaplanır (duvarda 0,10 m² altı boşluk düşülmez; sıva ve boyada
tüm boşluklar düşülür; kalıpta kalıp gören yüzler; demir ton). Kurallar keşif sayfasındaki "Ölçü kuralları" bölümünde listelenir.

## 4. Kalem kataloğu

Tam liste programın **Standart** sayfasında ve şablon DXF içinde (`KSF-NOT` katmanı) yer alır. Katalogda olmayan bir kalem çizilirse
program onu yine ölçer (blok → adet, çizgi → m, kapalı alan → m²) ama "katalogda yok" uyarısı verir; kalemi kataloğa ekleyince
adı, birimi ve ölçüm kuralı düzelir.

## 5. Şablon

Programdan **KSF_sablon.dxf** indirilir (`Standart → Şablon DXF indir` ya da `/api/catalog/template.dxf`). Şablon, katalogdaki
her kalem için hazır katman (disipline göre renk, açıklama satırı) ve `KSF-NOT` katmanında bu kuralların özetini içerir.
Tasarımcı ya şablon üzerine çizer ya da katmanları kendi çizimine aktarır (DesignCenter / `LAYTRANS`).

## 6. Kontrol listesi (teslim öncesi)

1. Metraja girecek her nesne `KSF-…` katmanında mı? (`Standart` sayfasındaki *katman adı dene* kutusuyla ad doğrulanır.)
2. Adet kalemleri blok mu? Alan kalemleri kapalı mı? Uzunluk kalemleri tek eksen çizgisi mi?
3. Hacim ve duvar kalemlerinde kalınlık / yükseklik özellikte var mı?
4. Her plan ayrı pafta mı, birim mm mi, xref yok mu?
5. Dosya DXF olarak kaydedildi mi?

Programa yüklenince: disiplin olarak **KSF standart çizim** seçilir; uyarı listesi boşsa çizim standarda tam uygundur.
