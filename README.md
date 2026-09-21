# Keşif — DXF Planından Metraj, Keşif, Maliyet ve Süre

AutoCAD planlarını (DXF) okuyup üç disiplinde keşif çıkarır:

| Disiplin | Çizim | Tespit edilen | Keşif kalemleri |
|---|---|---|---|
| **Statik** | kalıp planı | kolon, perde, kiriş, döşeme, temel | beton m³, kalıp m², demir kg |
| **Mimari** | kat planı | duvar (malzeme + kalınlık), kapı, pencere | duvar m² (Ytong / tuğla / bims / alçıpan…), sıva m², boya m², kapı adet, pencere adet, cam m² |
| **Elektrik** | tava / aydınlatma / kuvvet planı | kablo tavası, kablo, boru, armatür / priz / anahtar | tava m (boyut bazında), kablo m (kesit bazında), boru m, armatür adet (kategori) |

**Malzeme** birim fiyatı ürüne (C30/37 hazır beton, Ø12 nervürlü demir, Ytong 20 cm), **işçilik** birim fiyatı ile
adam-saat / birim kaleme girilir; program maliyet tablosu (malzeme + işçilik, KDV) ve **süre tahmini** (gün) üretir,
Excel raporu indirir.

### Keşif Çizim Standardı (KÇS) — bütün disiplinler

Yukarıdaki üç disiplin, standart dışı eski çizimler için **sezgisel** tanımadır. Asıl yol, müelliflerin çizimi
[**KÇS**](docs/KESIF_CIZIM_STANDARDI.md) ile teslim etmesidir: katman adı kalemi tanımlar, geometri miktarı verir.

```
KSF-<DİSİPLİN>-<KALEM>-<ÖZELLİK>      KSF-HAV-HAVA_KANAL-600x400   KSF-YAN-SPRINKLER-K80_UST   KSF-STA-DOLGU-30
```

Program katman adını okur, **katalog**dan ölçüm kuralını alır (blok → adet, çizgi → m, kapalı alan → m², duvar → uzunluk × yükseklik,
hacim → alan × kalınlık) ve doğrudan keşif kalemi üretir; katman eşleme gerekmez. Katalog 15 disiplin (statik, mimari, ince işler,
cephe, çatı, izolasyon, elektrik, zayıf akım, mekanik, havalandırma, yangın, sıhhi tesisat, altyapı, peyzaj, asansör) ve ~120 kalemle
gelir; **Standart** sayfasından disiplin ve kalem eklenir (`data/catalog.json`). Tasarımcı için hazır katmanlı **şablon DXF** indirilir
(`/api/catalog/template.dxf`). Yeni bir disiplin eklemek kod değil, katalog satırıdır.

## Kurulum

Gereksinimler: Python 3.12, Node 20+.

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# Frontend
cd ..\frontend
npm install
```

macOS / Linux'ta Python 3.12 yoksa conda ile: `conda create -y -p backend/.venv python=3.12` sonra
`backend/.venv/bin/python -m pip install -r backend/requirements.txt`.

## Çalıştırma (geliştirme)

Windows: iki ayrı terminalde, ya da tek komutla `.\start.ps1`. macOS / Linux: `./start.sh`.

```powershell
cd backend;  .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
cd frontend; npm run dev
```

Tarayıcı: http://127.0.0.1:5173  (API dokümantasyonu: http://127.0.0.1:8000/docs)

Üretim: `cd frontend; npm run build` sonrası backend `frontend/dist` klasörünü kendisi servis eder (http://127.0.0.1:8000).

## Kullanım akışı

1. **Yeni proje** (sihirbaz, `/projects/new`): ad, kat yüksekliği (H) ve varsayılan döşeme kalınlığı (d) gir; ikinci adımda
   **planlarını bırak**. Proje sayfasında mimari / elektrik / süre parametreleri: duvar yüksekliği (boşsa H − d), sıva ve boya
   yüzü sayısı, kablo iniş payı (m/hat), kablo ve tava fire %, günlük çalışma saati.
2. **Planları yükle**: DXF ya da DWG (ODA File Converter kuruluysa), birden çok dosya birlikte bırakılabilir. Her dosyanın
   **plan tipi** (temel kalıp, kat kalıp, donatı, kolon / kiriş detay, mimari kat / tavan / döşeme kaplama / çatı / cephe,
   elektrik tava / aydınlatma / kuvvet / zayıf akım, mekanik ısıtma / havalandırma / sıhhi / yangın, altyapı, peyzaj…)
   dosya adı ve paftadaki başlıktan tanınır; analiz **disiplini** plan tipinden gelir (`planset.py`). Başlık zayıfsa
   ("ZEMİN KAT PLANI") katman adları karar verir: KOLON / KİRİŞ katmanları → statik kalıp planı, DUVAR / KAPI → mimari,
   TAVA / KABLO → elektrik, `KSF-` → KÇS standart. Disiplin ve plan tipi sonradan çizim listesinden değiştirilebilir
   (disiplin değişince yeniden analiz edilir).
   - **Ruhsat projesi** (bütün paftalar yan yana tek dosya): paftalar otomatik bulunur (çerçeve dikdörtgenleri; yoksa nesne
     kümeleri), her paftanın plan tipi başlığından tanınıp önceden işaretlenir (kesit / detay paftaları işaretlenmez);
     onaylanan paftalar ayrı plan olarak kırpılıp kendi disipliniyle analiz edilir. 40 MB üstü dosyalar hiçbir zaman bütün olarak açılmaz.
   - "Kaç kat temsil ediyor" alanı tip kat çarpanıdır; temel elemanları hiçbir zaman çarpılmaz.
   - Her planın kendi **kat yüksekliği** girilebilir (boşsa projenin H değeri).
   - Başlıksız **küçük kümeler** (merdiven detayı, pano tablosu, lejant: 200 nesneden az ya da katmanlarından disiplin
     çıkmayan) plan sayılmaz, seçili gelmez (`fragment`). Katman sayımı yalnız geometriyi sayar; yazı katmanları
     (HB-GIZLI-DATA gibi) disiplin seçmez.
   - **Birim oylaması**: aynı dosyadan kırpılan paftalar tek birimdedir. Yazı yüksekliği kanıtı olan paftaların çoğunluğu
     (≥ 2 pafta, ≥ %60) bir birimi destekliyorsa başlıktaki (yanlış) birimle kalan paftalar o birimle yeniden analiz edilir
     (`unit_verdict`, `drawings._harmonize_units`).
   - Proje sayfasının başındaki **"Çizimlerden ne anlaşıldı"** tablosu her pafta için durum (okundu / boş / sorun / tip seçilmedi),
     bulunanlar ("99 duvar · 35 pencere · 11 kapı · 5 mahal alanı") ve tek cümlelik not verir (`drawings.drawing_summary`);
     plan seti kontrolü, katmanlı sistemler ve çizim ayarları katlanır bölümlerdedir.
   - **Yapı blokları** (`parser/blocks.py`, `Drawing.block`, `Project.blocks`): yaygın tipolojide bodrum ve zemin
     katlar birleşiktir (ortada koridor, tek yapı), üst katlar C1 / C2 / C3 / C4 diye ayrılır; statik tek ruhsat
     dosyası, mimari blok blok ayrı dosyalar gelir. Blok adı dosya adından tanınır (`… A4-A5 BLOK KALIP PLANLARI.dwg`,
     `C1 BLOK MİMARİ.dwg`, `BLOK: C4 kuvvet.dwg`; "BLOKAJ" blok sayılmaz) ve çizim listesindeki **Blok** sütunundan
     değiştirilir. Boş = **ortak / tüm bina** (bodrum, zemin, vaziyet, altyapı).

     **Projenin kaç bloğu olduğu sorulmaz, çizimden çıkar** (`services.project_blocks`). İki ayrı kanıt:
     - **pafta başlığı** — paftadaki en iri "… BLOK" yazısı o paftanın bloğudur (`Başlık_Yazı` katmanında
       `A4-A5 BLOK`). Keşfin kapsamı = planı yüklenmiş blokların birleşimi.
     - **vaziyet planı** — sitenin bütün bloklarını yazar (gerçek dosyada `A1 BLOK` … `C4 BLOK`, `N BLOK`, 22 ad).
       Vaziyet genelde keşiften geniştir, bu yüzden eksik saymaz: planı yüklenmemişler tek satırlık hatırlatma
       olur ("Vaziyet planında 12 blok daha var, hiç planı yüklenmedi"). Birleşik ad kendi parçalarını kapsar:
       `A4-A5` varken vaziyetteki `A4` ve `A5` eksik sayılmaz.

     Tek bloklu yapıda hiçbir yerde "BLOK" geçmez; liste boş kalır ve program tek yapı gibi çalışır.
     `Project.blocks` yalnız kullanıcı düzeltmesidir (`PUT /api/projects/{id}/blocks`); boşsa çizimden okunan
     liste geçerlidir. Blok bilinci üç yeri düzeltir:
     - plan seti kontrolü blok başına yapılır: bir tipin çizimlerinden en az biri bir bloğa aitse o tip her blokta
       aranır ("Mimari: Mimari kat planları şu bloklarda yok: C3"). Yalnız ortak çizilen tipler (temel, vaziyet)
       blok başına aranmaz.
     - aynı kat eşleştirmesi blok içinde kalır: C1'in +6.00 kalıp planı, C2'nin +6.00 mimari planını elemez
       (`services._plan_footprints`) — yoksa cephe alanı eksik çıkardı.
     - çatı alanı blok başına hesaplanır. Podyum varsa (ortak kat + üstünde kuleler) toplam çatı = birleşik kat
       oturumu; blok çatıları ve aradaki **podyum terası** bunun içindedir, üst üste sayılmaz.
   - **Plan seti kontrolü**: proje sayfası ve sihirbaz, hangi plan tiplerinin yüklendiğini gösterir; yüklenmemiş zorunlu planlar
     için uyarı verir ("Altyapı: Altyapı planı yüklenmedi", "Elektrik: Elektrik kablo tava planı yüklenmedi",
     "Mimari: Mimari tavan planı yüklenmedi" …). Projede gerçekten olmayan bir plan satırında **Bu projede yok** seçilir;
     gereklilik projeye kaydedilir (`plan_set`). Plan tipi tanınamayan çizimler ayrıca uyarılır. API:
     `GET /api/projects/{id}/plan-check`, `PUT /api/projects/{id}/plan-set`, `GET /api/projects/meta/plan-types`.
3. **Elemanlar** sayfası: plan önizlemede tespit edilen elemanlar renkli görünür.
   - **Katman eşleme**: hangi katmanın kolon / duvar / tava / … çizdiğini seç; yalnızca çizimin disiplinine ait tipler seçilebilir.
     Eşlenmemiş katmanlar metraja girmez.
   - Tabloda b/h/kalınlık/uzunluk/adet ve alt tip (duvar malzemesi, kablo kesiti, tava boyutu, armatür kategorisi) düzenlenebilir,
     eleman silinebilir, parser'ın kaçırdığı eleman elle eklenebilir.
4. **Metraj**: disiplin bazlı **keşif listesi** (kalem, birim, miktar) + statik grup özeti ve eleman bazlı liste.
5. **Birim Fiyatlar** — iki ayrı sekme:
   - **Malzeme (ürün)**: fiyat eleman türüne değil **ürüne** girilir. Kolon, perde, kiriş ve döşeme betonu aynı
     "Hazır beton C30/37" satırından fiyatlanır; Ø12 demir hangi elemanda geçerse geçsin tek satırdır. Sayfadaki
     **ürün seçimi** hangi elemanın hangi ürünü kullandığını belirler: genel beton sınıfı, temel / kolon / perde /
     kiriş / döşeme için ayrı sınıf, grobeton sınıfı, donatı sınıfı (B420C), kalıp malzemesi. Duvar, kablo, tava,
     kapı gibi kalemler zaten ürün bazında gruplanır (Ytong 20 cm, NYY 4x16, 200x60 tava).
   - **İşçilik**: kalem (poz) bazında işçilik ₺/birim, adam-saat/birim, ekip. Türün "genel" satırı özel değer
     girilmeyen kalemlere uygulanır. Birimi *saat* olan kalemler (kalıp / demir işçiliği, montaj) salt işçiliktir.
6. **Maliyet**: ürün bazında malzeme tablosu + kalem tablosu (hangi kalem hangi üründen fiyatlandı), disiplin ve iş
   grubu toplamları, KDV, **süre** (disiplinler paralel / işler ardışık), Excel indir.

### Fiyatlar ve tedarikçiler (bütün projeler için)

Sol menüdeki **Fiyatlar ve tedarikçiler** sayfası proje bağımsız fiyat bankasıdır: bütün ürünlerin fiyatı bir kez
buraya girilir, açılan her yeni projede ürün ve işçilik fiyatları kendiliğinden dolar.

- **Malzeme (ürün)**: beton sınıfları, donatı çapları, kalıp malzemeleri, tür genel satırları ve katalogdaki
  ~120 kalem hazır listelenir (iş grubuna göre katlanır, arama var). Bir ürüne **birden çok tedarikçi fiyatı**
  girilebilir; geçerli fiyat seçtiğiniz ("bunu kullan") satır, seçim yoksa en düşük olandır.
- **İşçilik**: kalem türü bazında ₺/birim, adam-saat/birim, ekip. Projede türün genel satırına uygulanır.
- **Tedarikçiler**: firma, yetkili, telefon, e-posta, not. Tedarikçi silinince fiyat satırları kalır, bağlantısı boşalır.

Devralma sırası: projede elle girilmiş değer > fiyat bankası. Banka güncellenince boş kalan proje satırları
kendiliğinden yenilenir; girilmiş fiyatların üzerine yazmak için proje Birim Fiyatlar sayfasındaki **Bankadaki
fiyatlarla güncelle** düğmesi kullanılır (`POST /api/projects/{id}/apply-pricebook?overwrite=true`).
API: `GET/PUT /api/pricebook`, `DELETE /api/pricebook/{row}`, `GET/POST/PATCH/DELETE /api/suppliers`.

`samples/` klasöründe sentetik örnek çizimler var: `ornek_kat_plani.dxf`, `ornek_temel_plani.dxf` (statik),
`ornek_mimari_plani.dxf` (Ytong 20 + tuğla 10 duvarlar, 2 kapı, 3 pencere), `ornek_elektrik_plani.dxf` (2 tava, 3 kablo hattı, boru, 9 armatür/priz/anahtar),
`ornek_ksf_plani.dxf` (KÇS standardı: havalandırma kanalı, PPRC boru, sprinkler, kompozit cephe, XPS, Ytong duvar, dolgu, ağaç).

## Parser nasıl çalışır

2D çizimde "bu bir kolon" bilgisi yoktur. Sistem:

- **Katman profili** (`backend/app/parser/layer_profile.py`): `KOLON`, `S-COL`, `KIRIS`, `BEAM`, `DOSEME`, `SLAB`, `PERDE`, `TEMEL`… regex'leri.
  Projede katman eşleme yapıldıkça profil projeye kaydedilir.
- **Geometri**: kapalı polyline / hatch / solid / blok içi çokgenler → alan, çevre, çevreleyen dikdörtgen.
  Kirişler ve sürekli temeller için **paralel çizgi çiftleri** (aralık = genişlik, örtüşme = uzunluk) da tanınır.
  Çizgilerle kapatılmış (polyline olmayan) dikdörtgenler de yakalanır.
- **Etiketler** (`text_parser.py`): `S1 30/60`, `K101 25x50`, `P1 20/250`, `D101 h=15`, `TK1 60/80`, `Ø8/15`, `8Φ16`, `%%c`.
  Kat kodlu adlar da tanınır: `SB033` / `SZ094` / `S1094` (bodrum / zemin / 1. kat kolonu), `KB0021`, `PB0922`, `DB041`,
  `DDB024` (düşük döşeme), `RD1` (radye bölgesi); çıplak `15cm` yazısı kalınlıktır.
  Etiketteki sayılar cm kabul edilir. Etiket kesiti çizimle uyuşmazsa uyarı verilir.
- **Birim**: `$INSUNITS` başlığından (mm/cm/m); yoksa çizim boyutundan tahmin edilir ve uyarı verilir. Çizim bazında elle seçilebilir.
- **Çok paftalı dosya** (`sheets.py`): dosya ezdxf'siz satır satır taranır (500 MB ≈ 20 s). Pafta çerçeveleri = büyük
  dikdörtgenler (kapalı polyline, 4 çizgi ya da büyük antet bloğu); iç içe olanlardan dıştaki alınır. Her paftanın başlığı
  içindeki en büyük "… PLANI / KESİTİ / DETAYI" yazısıdır. Tarama her pafta için en kalabalık 40 katmanı da sayar
  (plan tipi / disiplin ipucu). Başlık bir blok tanımının içindeyse (antet bloğu ATTRIB değil, blok içi TEXT) bulunamaz;
  pafta "başlıksız" görünür ve plan tipi elle seçilir. Seçilen paftalar tek geçişte küçük DXF'lere kırpılır
  (çizgi, polyline, yazı, daire, yay, solid; blok ve tarama alınmaz).
- **Radye**: temel katmanındaki çokgenler kalınlık bölgeleridir (`RD1` + `70cm`); pafta kesiminde açık kalan sınır kapatılır.
  Çokgen dışında kalan radye etiketleri varsa (`RD2 40cm`, sınırı çizilmemiş ince bölge) bina oturumu kolon/perde dış
  hattından 1 m dışarı alınarak tahmin edilir, çokgenler düşülür (düşük güven; alan elle düzeltilebilir).

### KÇS standart çizim (`standard/catalog.py`, `detectors/standard.py`, `quantity/boq.py: standard_items`)

- Katman adı `KSF-<DİSİPLİN>-<KALEM>-<ÖZELLİK>` ayrıştırılır (`parse_layer`); kalem katalogda aranır.
- Ölçüm kuralı: `count` (bloklar), `length` (çizgi / polyline; kapalı ise çevre), `area` (kapalı çokgen / tarama, kopyalar elenir),
  `wall_area` (uzunluk × yükseklik; yükseklik özellikteki 2. sayı ya da proje duvar yüksekliği), `volume` (alan × özellikteki kalınlık cm).
- Katalogda olmayan kalem geometriye göre ölçülür ve "kataloğa ekleyin" uyarısı verir; `KSF` ile başlamayan katmanlar metraja girmez.
- Keşif anahtarı `<kalem_kodu>:<özellik>` (`hava_kanal:600x400`, `sprinkler:k80_ust`); fiyat / işçilik / süre mekanizması aynıdır.
- Katalog: varsayılan kodda (`DEFAULT_ITEMS`), kullanıcı değişiklikleri `DATA_DIR/catalog.json`; API `/api/catalog`, şablon `/api/catalog/template.dxf`.

### Katman eşlemeli çizim (`mapped` disiplini): cephe, çatı, peyzaj, standart dışı her pafta

KSF adlandırması olmayan bir çizimde (ör. ofisin kendi katmanlarıyla çizilmiş cephe görünüşü) kullanıcı **her katmanı bir
katalog kalemine ve ölçüm kuralına** eşler: `brn_hatch_gazbeton → Ytong duvar, alan (m²)`, `Söve → korkuluk/söve, uzunluk (m)`,
`Kartonpiyer → adet`. Program katman adından öneri üretir (`detectors/standard.py: SUGGEST_RULES`), kullanıcı tek tıkla onaylar.
Eşleme projeye kaydedilir (`layer_profile` içinde `item:<KOD>[:<ölçüm>]`), aynı ofisin sonraki çizimlerinde otomatik uygulanır.
Pafta kırpma bu amaçla **tarama (HATCH) sınırlarını** kapalı çokgen olarak ve **blok içeriğini** de yazar (500 MB'a kadar).
Cephe görünüşünde malzeme taramalarının alanı = cephe m² (sıva, boya, mantolama, kaplama, cam); söve / silme / küpeşte m; kartonpiyer adet.

### Mimari parser (sezgisel)

- **Duvar** (`detectors/walls.py`): duvar katmanındaki paralel çizgi çiftleri (aralık = kalınlık; kapı boşluklarında kesilen parçalar
  birleştirilir) ve kapalı çokgenler / taramalar (dikdörtgense kısa kenar = kalınlık, değilse uzunluk = alan / kalınlık).
  Malzeme katman adından (`A-DUVAR-YTONG`, `DUVAR TUGLA`) ya da yakın etiketten (`YTONG 20`, `20 cm GAZBETON`) okunur.
- **Kapı / pencere** (`detectors/openings.py`): kapı ve pencere katmanlarındaki bloklar (INSERT) sayılır. Ölçü: yakın etiket
  (`K1 90/210`, `P1 120/140`), yoksa blok adı (`PENCERE_120x140`, `KAPI_90`), yoksa blok kutusu; yükseklik varsayılanı kapı 210, pencere 140 cm.
  Bloksuz çizimlerde `P3 120/140` gibi etiketler tek başına sayılır (düşük güven).
- Keşif: duvar m² = uzunluk × duvar yüksekliği × kat sayısı − kapı/pencere boşlukları (gruplara alanlarıyla orantılı düşülür);
  sıva ve boya = net duvar × yüz sayısı; cam = pencere genişlik × yükseklik.

### Elektrik parser

- **Tava / kablo / boru** (`detectors/electrical.py`): ilgili katmandaki çizgi ve polyline'lar; uç uca değen parçalar tek hat sayılır.
  Boyut / kesit / çap önce **katman adından** (`E-TAVA-200x60`, `E-KABLO-5x6`), yoksa en yakın **etiketten** (`TAVA 200x60`, `NYY 4x16`,
  `3x2,5 NYM`, `Ø20 PVC`) okunur; her etiket bir hatta atanır. Çift çizgi çizilen tavalarda aralık = genişlik.
- **Armatür / priz / anahtar**: armatür katmanlarındaki bloklar sayılır; kategori blok ya da katman adından
  (`LED_PANEL` → armatür, `PRIZ_TOPRAKLI` → priz, `ANAHTAR`, `DEDEKTOR` → yangın, `DATA`, `PANO` …).
- Keşif: kablo m = (hat + iniş payı) × kat sayısı × (1 + fire), tava m × (1 + fire), armatür adet (kategori + blok adı bazında).

### Maliyet ve süre

Fiyat kalemi anahtarı `<tür>:<grup>` (`beton:column`, `duvar:ytong:20`, `kablo:nyy_4x16`, `tava:200x60`, `armatur:priz_priz_toprakli`);
`<tür>:*` genel fiyat. Her kalem: malzeme ₺/birim, işçilik ₺/birim, marka, adam-saat/birim, ekip. Kalem tutarı = miktar × (malzeme + işçilik);
kalem süresi = miktar × adam-saat / (ekip × günlük saat). Toplam süre iki biçimde: işler ardışık (kalemlerin toplamı) ve
disiplinler paralel (en uzun disiplin). Adam-saat girilmeyen kalemler süreye katılmaz ve uyarı verilir.

**Adam-saat nereden gelir:** reçetedeki işçilik bileşeninden. Kalıp 1.000 m² → "Kalıp kurma + söküm işçiliği"
1.200 saat (norm 1,2 saat/m², katalogdan düzenlenir). Birimi *saat* olan bu kalemlerde **miktarın kendisi adam-saattir**;
adam-saat/birim girilmezse 1,0 kabul edilir, yani süre hiçbir şey girilmeden çıkar. Kullanıcı üst kaleme (kalıp m²)
kendi normunu girerse o geçerlidir ve o üst kalemden gelen reçete işçiliği süreye ikinci kez katılmaz
(satırda `hours_source = "üst kalemde sayıldı"`).

**Ekip:** girilmemişse gün, tek kişilik **adam-gün**dür (`duration.man_days`); takvim günü için işçilik satırına
ekip sayısı girilir (1.200 saat ÷ 10 kişi ÷ 8 saat = 15 gün). Ekip girilmemiş kalemler `duration.missing_crew`
ile uyarılır.

### Demir işçiliği: çapa, kata ve hazır demire bağlı

Demirde "1 m² kaç adam-saat" anlamsızdır; belirleyici **ton başına** işçiliktir ve o da **çapa** bağlıdır:
bir ton Ø8 ≈ 2.500 m, bir ton Ø26 ≈ 240 m — aynı tonaj on kat farklı sayıda çubuk, bağ noktası ve kesim demektir.
(ÇŞB'nin demiri 15.160.1003 Ø8–12 ve 15.160.1004 Ø14–28 diye ikiye ayırmasının sebebi de budur.)

Program her demir kalemini çapına göre üç ayrı işe açar (`standard/rules.py: REBAR_LABOR_HOURS_PER_TON`,
`quantity/recipes.py: _rebar_recipe`):

| | hazırlık (kesme-bükme) | taşıma-dağıtım | montaj (yerleştirme-bağlama) | toplam |
|---|---|---|---|---|
| Ø8–10 | 12 | 6 | 24 | **42 sa/t** |
| Ø12 | 9 | 5 | 17 | **31** |
| Ø14–16 | 8 | 4 | 13 | **25** |
| Ø18–22 | 7 | 4 | 10 | **21** |
| Ø24–40 | 6 | 4 | 8 | **18** |

- **Çift kat / tek kat çizimden okunur.** Alt ve üst donatı yazıları ve katman adları sayılır
  (`parser/rebar_mix.py: scan_layer_tags` / `layer_verdict`): `(ALT)` / `(ÜST)`, `ƒ20/18 Temel Üst Donatısı (X Yönü)`,
  katman `VM Üst Donatı` / `VOLKAN-DONATI ALT`. Kot yazıları ("+0.82 (TEMEL ÜST KOT)") kanıt sayılmaz.
  Çift katta montaj ×1,15 (üst hasır sehpa üstünde, havada bağlanır) ve **sehpa / poz demiri** 25 kg/ton eklenir
  — sehpanın kendi kesme-bükme ve yerine koyma işçiliği de zincirde açılır.
  Proje parametresi `rebar_layers` ile elle `cift` / `tek` seçilebilir.
- **Hazır demir:** `rebar_prefab_pct` = atölyede kesilip bükülerek gelen demir yüzdesi; o oranda hazırlık sahada
  yapılmaz (taşıma ve montaj değişmez).

A4-A5 (2.156 t, çizimden okunan çap karışımı, çift kat): **55.032 adam-saat ≈ 25,5 sa/ton**, 5,4 t sehpa demiri.
Tablodaki değerler yaygın uygulama varsayılanıdır, ÇŞB analizinden doğrulanmadı — katalogdan düzenlenir.

### Kalıp işçiliği: eleman biçimine, malzemeye ve tekrar kullanıma bağlı

Kalıpta da m² başına sabit saat yanlıştır: aynı 1 m² kalıp kolonda dört köşe + şakül + eksen tutturma, perdede
düz pano, kirişte taban + iki yanak + tavan işi, temelde yalnız yerde düz kenar demektir. İşçilik üçe ayrılır
(`standard/rules.py: FORMWORK_LABOR_HOURS_PER_M2`, `quantity/recipes.py: _formwork_recipe`):

| | imalat (kesme-çakma) | kurma | söküm-temizlik | toplam |
|---|---|---|---|---|
| Temel (kenar kalıbı) | 0,20 | 0,40 | 0,20 | **0,80 sa/m²** |
| Perde | 0,25 | 0,55 | 0,25 | **1,05** |
| Döşeme | 0,25 | 0,55 | 0,30 | **1,10** |
| Kolon | 0,35 | 0,75 | 0,35 | **1,45** |
| Kiriş | 0,40 | 0,85 | 0,40 | **1,65** |
| Merdiven | 0,60 | 1,20 | 0,50 | **2,30** |
| *(tipi okunamayan kalem)* | 0,30 | 0,60 | 0,30 | **1,20** |

- **İmalat levhanın kullanım sayısına bölünür** (`formwork_reuse`): pano bir kez yapılır, N kez kullanılır;
  her kullanımdaki yerinde düzeltme payı *kurma* içindedir.
- **Kalıp sistemi** (`formwork_material`) çarpan uygular: kereste ×1,25/1,15/1,10 · plywood ×1 ·
  hazır çelik pano imalatı sıfırlar, kurma ×0,70 söküm ×0,60 · tünel kalıp kurma ×0,45 söküm ×0,40.
- Döşeme altındaki **kalıp iskelesi** ayrı kalemdir (ÇŞB 15.185), bu norma dahil değildir.

A4-A5 (43.348 m², tipik dağılım, 5 kullanım): plywood **45.594 saat (1,05 sa/m²)** · çelik pano 28.636 (0,66) ·
tünel 18.609 (0,43). Eski düz 1,2 sa/m² her sistemde 52.018 saat diyordu.
Değerler yaygın uygulama varsayılanıdır, ÇŞB analizinden doğrulanmadı.

## Metraj formülleri (statik)

| Eleman | Beton | Kalıp |
|---|---|---|
| Kolon | alan × Hk | çevre × Hf |
| Perde | alan × Hk | 2 × uzunluk × Hf |
| Kiriş | b × hk × net L | (b + 2 × hk) × net L |
| Döşeme | alan × kalınlık | alan |
| Radye | alan × kalınlık | çevre × kalınlık |
| Sürekli temel | b × h × L | 2 × L × h |

- Döşeme **brüt** çokgenle ölçülüyorsa (çokgen kolonu da kapsar): Hk = H − d, hk = h − d.
- Döşeme kiriş ağından **net** alan olarak türetilmişse: kolon/perde döşeme kalınlığı boyunca da tek sayılır, Hk = H ve hk = h.
- Kolon/perde kalıbı kiriş altına kadar: Hf = H − (kattaki baskın kiriş yüksekliği; kiriş yoksa d).
  Bu kural, çizimi üreten programın kolon kalıbıyla (B Blok: %2-6 fark) uyuşur.

Kiriş net uzunluğu kolon/perde içine giren kısım düşülerek bulunur. Demir = beton × kg/m³ oranı (proje parametrelerinde düzenlenir).

## Testler

```powershell
cd backend; .\.venv\Scripts\python -m pytest tests -q
```

Testler, sonucu bilinen sentetik DXF'ler üretir (`tests/fixtures/make_dxf.py`) ve tespit + metraj + API akışını doğrular.

## Gerçek çizimde öğrenilenler (AVM A1-A3 bloğu, +4.15 kotu kalıp planı)

Bu çizimle kalibre edilen davranışlar:

- **Birim doğrulama**: dosya `$INSUNITS = mm` diyordu ama cm ile çizilmişti. Kolon etiketindeki kesit
  ("(100/100)") ile çizilen kolonun boyutu karşılaştırılır; 10× fark varsa birim otomatik düzeltilir ve uyarı verilir.
- **Ayrık etiketler**: ad ("S1001") ve kesit ("(100/100)") ayrı yazılardır; en yakın ad + en yakın kesit birleştirilir.
  Kiriş etiketi "K1001 (100/45)", döşeme "D1000" + "d=12" / "D:20cm", kot yazıları ("+4.00") yok sayılır.
- **Döşeme çokgeni yok**: döşemeler kiriş çizgileri + kolon/perde sınırlarından üretilen kapalı yüzeylerdir
  (içinde döşeme etiketi olan yüzey). Bu alan kirişler arası **net** alandır; bu durumda kiriş betonu tam yükseklikle
  (b × h × L) alınır, böylece toplam beton doğru kalır. "Şaft" katmanındaki çokgenler döşemeden düşülür.
- **Kiriş parçaları**: kirişler kolon geçişlerinde kesilmiş çift çizgilerdir; aynı hizadaki parçalar birleştirilir,
  sonra üzerindeki etiket sayısına göre kirişlere bölünür.
- **Yok sayılan katmanlar**: detay/donatı/kesit/merdiven/aplikasyon/kot/marka/tarama katmanları (`IGNORE_PATTERNS`).
  "VM Kolon" katmanına çizilmiş büyük bölgeler (4 m² üstü) kolon sayılmaz, listede düşük güvenle ve metraj dışı görünür.
- **Performans**: 25 bin nesne ~18 saniyede analiz edilir (paralel çizgi araması STRtree ile).

## Gerçek çizimde öğrenilenler (B Blok ruhsat projesi, 494 MB, 67 pafta)

Ayrıntılı not ve kırpılmış test paftaları: `samples/b_blok/README.md`.

- Bütün paftalar tek model uzayında yan yana; pafta çerçeveleri `TABLO` katmanında kapalı dikdörtgen. Pafta seçme akışı
  bu dosya için yazıldı (66 pafta 17 saniyede bulunur, seçilen paftalar tek geçişte kırpılır).
- Adlar kat kodlu (`SB033`, `SZ094`, `S1094`, `KB0021`, `PB0922`, `DB041`, `DDB024`); döşeme kalınlığı çıplak `15cm`.
  `LGP-SLAB2` katmanı döşeme etiketi kutusudur, döşeme değildir (yok sayılır). `KM Temel Kesik` radye sınırının ofsetli
  kopyasıdır (`KESİK` yok sayılır).
- Radye iki kalınlık bölgesi: `KM Temel` çokgenleri RD1 (70 cm); geri kalan oturum RD2 (40 cm) — sınırı çizilmemiş,
  tahmin edilir.
- Doğrulama (programın kendi metraj tablosu `TABLE4` katmanında): kolon+perde betonu bodrum %4, zemin %0,4, 1. kat %5 içinde.
  Bu projede demir yoğunluğu yüksek: kolon/perde 160-190 kg/m³, kiriş ~160 kg/m³ (proje parametrelerinden girilir).

## DWG yükleme

Program DXF okur. **ODA File Converter** (ücretsiz, https://www.opendesign.com/guestfiles/oda_file_converter) kuruluysa DWG doğrudan
yüklenir: sunucu dosyayı ACAD2018 DXF'e çevirir ve devam eder (`/api/health` → `dwg_support`). Dönüştürücü aranan yerler: `KESIF_ODA_CONVERTER`
ortam değişkeni, macOS `~/Applications/ODAFileConverter.app`, Windows `C:\Program Files\ODA\ODAFileConverter*`.
`libredwg` (`dwg2dxf`) AutoCAD 2013+ dosyalarında katman tablosunu çözemiyor (katman adları boş kalıyor); kullanmayın.

## Gerçek çizimde öğrenilenler (KIYI İstanbul A4-A5 blok, 5 DWG, 5 Eyl 2026)

Aynı statik ofisin ("VM …" katmanları) 5 dosyası: temel kalıp+donatı, kolon aplikasyon, kalıp planları (4 kot), kalıp donatı, kiriş detayları.
Birim mm yazılı, cm çizilmiş (otomatik düzeltme çalıştı). Kalıp planı paftaları: +4.15, +7.95, +10.65/+11.65, +15.65; temel üst kotu +0.52/+0.82.
Kat yükseklikleri kot farklarından girildi: 3.55 / 3.80 / 3.70 / 4.00.

Bu çizimle yapılan düzeltmeler:

- **Kiriş çizgileri kolon yüzüne değmiyor** (birkaç cm boşluk): döşeme hücreleri kapanmıyor, birleşip devasa yüzey oluyor ve
  400 m² sınırından eleniyordu. Kolon/perde çokgenleri 5 cm tamponlanıyor (`support_snap`); döşeme alanı +4.15'te 1.610 → 7.966 m².
  Hâlâ kapanmayan büyük yüzey birden çok döşeme etiketi içeriyorsa **birleşik panel** olarak alınır (uyarı + düşük güven).
- **Radye bölge sınırları** çizgi + açık polyline karışımı, uçlar arasında 0.7–2 m boşluk: ağ önce birlikte kapatılır, sarkan uçlar
  2.5 m içindeki çizgiye kendi doğrultusunda uzatılarak köprülenir (`raft_line_snap`); yan yana paralel çizgiler (sürekli temel)
  köprülenmez. Dört RD1 (70 cm) bölgesi yakalandı; aralardaki koridorlar kalan alan olarak RD2 (40 cm) etiketinden alınır.
- **Etiketsiz kirişler** (%7–14): kattaki baskın kiriş yüksekliğiyle hesaplanır, not düşülür (eskiden 0 alınıyordu).
- Temel paftasındaki kolon/perde izleri metraj dışı (doğru); "Parapet (20/82)" etiketleri `parapet` ipucu alır, kolona yapışmaz;
  `VM Parapet Tarama` henüz metraja girmiyor (bkz. güven paketi notu).

**Güven paketi (9 Eyl 2026)** — dört bağımsız inceleme (demir, statik, mimari/elektrik/mekanik, altyapı) sonrası bu çizimle yeniden kalibre edildi:

- **Döşeme hücreleri kayan-nokta gürültüsüyle kapanmıyordu**: kiriş çizgi uçları 1e-13 m farkla "çakışmadığı" için `polygonize`
  hücreyi kapatamıyor, açık bölgeler dış halkayla birleşip sahte "birleşik panel" oluyordu. Çizgiler 1 mm hassasiyet ızgarasına
  oturtulur (`shapely.set_precision`, `faces_from_network` / `polygons_on_layers`). +15.65'te 66 kayıp döşemenin hepsi bulundu
  (104 → 163 döşeme, 902 → 2.502 m²); +7.95 ve +10.65'teki 1.300 m²'lik sahte halkalar gitti. Tek etiketli 400 m² üstü panel
  atılmaz, düşük güvenle (metraj dışı) listelenir.
- **Kırpma payı komşu paftaya taşıyordu**: bitişik çerçevelerde kenardaki kiriş / poz yazısı iki paftaya da yazılıyordu. Pay komşu
  çerçevenin çekirdeğine kadar kırpılır; kiriş detaylarında poz satırı 8.264 → 7.987 (kaynak dosyadaki sayıyla birebir).
- **Donatı paftası kalıp planı sanılıyordu**: başlığı "+7.95 KOTU KALIP PLANI" olan döşeme donatı paftaları (alt başlık "X YÖNÜ
  DONATI PLANI") statik analiz ediliyor, tablo okunmuyor ve kalıp betonu ikinci kez sayılıyordu. Bütün başlık adayları değerlendirilir,
  donatı adayı kazanır; katmanlarda DONATI / POZ / METRAJ nesneleri kalabalıksa katman kanıtı da donatı der.
- **Kiriş detaylarının demiri döşemeye yazılıyordu** (pafta başlığı "K1075"): hedef eleman artık plan tipi > başlıktaki açık sözcük
  > dosya adı sırasıyla bulunur.
- **Kesit etiketi alanla tutarlı olan seçilir**: "Parapet (20/82)" ya da komşu kirişin "(100/45)" yazısı 100×100 kolona yapışmaz
  (kesit uyuşmazlığı 48 → 3 kolon). Yüzey içindeki "(100/100)" yazısı döşeme kalınlığı olmaz (1,00 m sahte kalınlık gitti).
- **Kiriş yan kalıbı döşeme altına kadar** (h − d; ÇŞB 15.180.1003 "kalıp gören yüz"): kiriş kalıbı 18.612 → 15.067 m². Kesişen
  kirişlerde ortak hacim dar kirişten düşülür (~150 m³). Etiketsiz kiriş için etiket 0,6 m'ye kadar aranır; atanmamış kiriş /
  döşeme etiketleri uyarıda listelenir (eksik kiriş → elle ekleme).
- **Temel**: etiketsiz açık polyline kutuları ("MİLANO 1/2", 405 m² → 202 m³ sahte beton) metraj dışı; RD2 tahmini yalnız etiketli
  bölgelere dayanır (3.368 → 2.907 m²).
- **Blok öznitelikleri (ATTRIB)**: blok yerleşimine bağlı öznitelikler `virtual_entities()` çıktısına girmez; ayrıca okunur.
  A4-A5 temel paftasında yazı sayısı 3.145 → 11.298, tanınan donatı yazısı 87 → 786 (kolon adları, poz ve boy yazıları da burada).
- **Oran demirinin çapı**: donatı tablosu olmayan elemanların demiri beton × kg/m³ ile bulunur ve çapı bilinmezdi.
  Artık çizimdeki donatı yazıları (`20ƒ14/20`, `4X7ƒ12/10`, `ƒ14/18`, `8Ø16`, `P01 182ƒ8/10 etr. l=196`) taranıp
  **çap karışımı** çıkarılır (`parser/rebar_mix.py`: pay = adet × çap², boy yazılıysa × boy) ve oran demiri bu dağılıma
  göre çap kalemlerine bölünür: `demir:column:o12` → ürün olarak "Nervürlü inşaat demiri Ø12". Karışım paftanın hedef
  eleman tipine yazılır (kolon aplikasyon → kolon, temel → temel, kiriş detay → kiriş); tipe özel dağılım yoksa proje
  geneli kullanılır. Metraj sayfasında "Çizimden okunan donatı çapları" olarak görünür, `rebar_dia_split: off` ile kapatılır.
  A4-A5 projesinde okunan dağılım: temel Ø20 %69 / Ø26 %18 / Ø14 %13, kolon Ø26 %36 / Ø14 %32 / Ø12 %21,
  döşeme Ø10 %70 / Ø12 %24, kiriş Ø8 %26 / Ø26 %25 / Ø20 %15.
- **Demir toplama**: tip kat çarpanı tablo demirine de uygulanır; kot bazında eşleme (donatı paftası olan katın oranı düşer, olmayan
  kat oranla kalır ve uyarı verir); kaynak (tablo / poz / elle / oran) çap bazında ve keşifte görünür; "AĞIRLIK (ton)" satırı,
  sütunlar arasına ortalanmış genel toplam sağlaması, `160+30` kanca payı, metre boy, `4Q14`, "(2 ADET)" çarpanı, adetsiz poz uyarısı.
  Fire kalemi yalnız kesim artığıdır (%3): bindirme ve kanca poz boylarında zaten vardır. Varsayılan oranlar kolon 180 / perde 140 /
  kiriş 140 / döşeme 85 / temel 95 kg/m³ (oran her zaman düşük güven).

Demir: 11 donatı paftasının metraj tabloları (temel X/Y/ilave, döşeme alt/üst × 4 kot) birebir okundu (907,9 t); kolon paftalarının
tabloları blok içindeydi (5 tablo, 633 t); kiriş detaylarında tablo yok, 7.987 adetli poz yazısından 604,6 t hesaplandı. Yalnız perde
(7 t) oranla kaldı. Gerçek oranlar bu projede: radye 97, kolon **374**, kiriş 178, döşeme 82 kg/m³.

Güven paketi sonrası (9 Eyl 2026; `find_parallel_pairs` çoklu eşleme ile aynı çizgiyi paylaşan ardışık kirişler de yakalanır),
10 Eyl 2026'da proje sıfırdan yeniden kurularak doğrulandı (parantez içi: 9 Eyl değerleri):

| Grup | Adet | Beton m³ | Kalıp m² | Demir t | Demir kaynağı |
|---|---|---|---|---|---|
| Radye (RD1 7.166 m² × 0,70 + RD2 2.907 m² × 0,40) | 5 | 6.186 | 779 | 635,5 | tablo |
| Kolon | 457 | 1.726 (1.693) | 6.103 (5.963) | 633,0 | tablo (blok içi) |
| Perde | 23 | 83 (74) | 489 (433) | 11,6 (10,4) | oran (140 kg/m³) |
| Kiriş | 1.760 | 3.734 | 15.608 (15.067) | 604,6 | poz yazıları (7.987 satır) |
| Döşeme | 368 çokgen (1.349 parça) | 3.128 | 21.106 | 272,3 | tablo |
| **Toplam** | | **14.918** (14.815) | **44.611** (43.348) | **2.163** (2.156) | |

**Bu tablonun tekrarlanma koşulu: proje kat yüksekliği H = 0** (kotlardan otomatik). A4-A5'te kat yükseklikleri
2,50 / 3,95 / 2,70 / 5,00 m olarak değişir; yeni proje formunun varsayılanı olan H = 3,0 m bütün paftalara
uygulanınca beton 14.900 → 14.542 m³, kalıp 44.541 → 43.045 m² olur (demir etkilenmez, tablodan / pozdan gelir).
Bu durum artık kontrol özetinde `storey_height_override` uyarısı olarak bildirilir.

11 Eyl 2026'da proje beş DXF'ten API üzerinden yeniden kuruldu: 51 kutu tarandı, 50'si plan olarak tanınıp elle
düzeltme olmadan analiz edildi, 1 tanesi ("VAZİYET PLANI", 11 nesnelik şablon çerçevesi) boş çerçeve olarak elendi.
Sonuç bu tabloyla %0,2 içinde örtüştü (14.900 / 44.541 / 2.163,1).

Demir çap bazında sapma −0,4% ile +0,2% arasında; tablo ve poz kaynaklı 2.145,5 t birebir aynı, oranla tahmin
edilen yalnız 17,6 t (perde + parapet, ikisi de uyarıyla). Beton +0,7%, kalıp +2,9%: kalıp farkı kiriş yan kalıbının
yüksekliğini belirleyen döşeme kalınlığından gelir (beton d'den bağımsız olduğu için birebir aynı kaldı).
Döşeme "adet"i düştü çünkü kirişlerle bölünmüş aynı döşemenin bitişik parçaları artık tek elemanda birleşiyor
(`parser/merge.py`); alan ve beton değişmez.

Çap bazında: Ø8 154 t, Ø10 200 t, Ø12 367 t, Ø14 268 t, Ø16 82 t, Ø20 596 t, Ø26 481 t.

## Sessizce kaybolan miktar ve yanlış alarm (12 Eyl 2026)

Kontrol listesinin işe yaraması, "eksik" dediğinin gerçekten eksik olmasına bağlı. İki yönde de ölçüldü.

**Yanlış alarm kalktı: tekrarlanan marka eksik sayılmıyor.** Aynı döşeme / kiriş markası plan boyunca defalarca
yazılır — A4-A5'in temel kalıp paftasında tek `D1000` markası **528 kez** geçiyor ve 26 döşemeye atanmış. Kalan
kopyalar "kapalı bir hücreye düşmedi" diye engelleyici eksik sayılıyor, dört kalıp paftasını da kilitliyordu.
Artık önce **adın ölçülen bir elemanda geçip geçmediğine** bakılır (`analyzer._unclaimed_labels`); geçiyorsa
eksik yoktur. Geçmiyorsa ikinci soru: etiketin 1,5 m yakınında **etiketin kendi kesitiyle** (b/h sırası önemsiz)
ölçülmüş bir eleman var mı? Varsa miktar sayılmış, yalnız ad eşleşmemiştir (uzun kiriş hattı komşu markayı almış
olur) — inceleme notu; yoksa eleman gerçekten kaçmıştır — eksik.

A4-A5'in dört kalıp paftasında ölçülen sonuç (**miktarlar birebir aynı kaldı**: 1.760 kiriş, 3.589,9 m³,
17.742,2 m² kiriş kalıbı, 368 döşeme, 21.106,1 m²):

| | önce | sonra |
|---|---:|---|
| Döşeme "eksik" uyarısı | 4 pafta (engelleyici) | **0** — hepsi yanlış alarmdı |
| Kiriş etiketi uyarısı | 45 ad (engelleyici) | **12 gerçek boşluk** + 33 "ad eşleşmedi" (inceleme) |

Yani daha önce "≈95 m³ eksik beton" diye okunan 45 kiriş etiketinin 33'ünde beton zaten ölçülmüştü; kaybolan
miktar değil, addı.

**Sessizce kaybolan miktar görünür oldu.** B2 BLOK'un "BİRİNCİ KAT PLANI" paftasında `FB_Prekast` katmanı
**177.592 nesne** tutuyor (paftanın %94'ü) ve hiçbir keşif kalemi üretmiyordu; uyarı listesinde 3 nesnelik
katmanlarla yan yana, sayısız duruyordu. İki kural eklendi:

- **Eşlenmemiş katmanlar nesne sayısıyla ve çoktan aza sıralı** yazılır; bir katman tek başına paftanın
  nesnelerinin %30'undan çoğunu tutuyorsa ayrı bir **engelleyici** uyarı çıkar (`analyzer._dominant_unmapped`):
  "paftanın asıl içeriği burada olabilir, bu katmanı bir katalog kalemine ve ölçüm kuralına eşleyin".
- **`label_count` kuralı yazı ister**; katmanda panel kodu yazısı yok ama geometri varsa o geometri sessizce
  düşüyordu. Artık kaç nesnenin ölçülmeden kaldığı yazılır (`standard.measure_layer`) ve bu da engelleyicidir —
  prekast paftasında 5.692, görünüş paftasında 286.734 nesne.

**Kat yüksekliği farkı artık m³ / m² olarak yazılır.** `storey_height_override` uyarısı "kotların yerine
kullanıldı" demekle kalmıyor; elemanların kesit alanı ve çevresinden **farkın bedelini** hesaplıyor. A4-A5'te
üretilen cümle: *"Okunan yükseklikler kat kat değişiyor (2,5–5 m), tek bir H hiçbir katta doğru olamaz.
Kotlardan hesaplansaydı kolon + perde betonu +358 m³, kalıbı +1.497 m² değişirdi."* — bağımsız ölçülen gerçek
bedelle (358 m³ / 1.496 m²) birebir. Yükseklikler kat kat ayrışıyorsa uyarı **engelleyici** olur ve kontrol
listesinde **tek tıkla düzeltme** düğmesi çıkar (proje H'sini 0 yapar; `QualitySummary`, `issue.fix`).

Testler: `backend/tests/test_unmeasured.py` (tekrarlanan marka, ad eşleşmesi, gerçek boşluk, baskın katman,
yazısız `label_count`, engelleyici sınıflandırma), `backend/tests/test_levels.py` (farkın m³ / m² bedeli).

## Demir: donatı paftası tabloları, kat bazında metraj, sarf kalemleri

- **Donatı planı** disiplini: paftadaki poz tablosu (POZ / ÇAP / ADET / BOY / toplam boy / ağırlık; `parser/rebar_tables.py`)
  okunur, her çap bir `rebar` elemanı olur (meta: kg, m, hedef eleman, kot). Hedef eleman plan adından: TEMEL → temel,
  KOLON, KİRİŞ, PERDE; yazmıyorsa döşeme. Kot (`+7.95`) plan adından. Tablosu olan eleman tipinin demiri **tablodan**
  (kaynak "tablo"), diğerleri beton × kg/m³ oranıyla ("oran") alınır; keşifte demir çap bazında (`demir:o12`) listelenir.
- Tablo yoksa **adetli poz yazıları** toplanır (kiriş / kolon açılımı: `P45 4Ø14 ila. l=160` = 4 adet Ø14 × 1.60 m;
  etriye bölgeleri `P05 72Ø8/10 etr. l=160`). Adetsiz kesit tekrarları (`4Ø12`, `P05 Ø8 l=160`) sayılmaz. Kanca / bindirme
  payı yazıda yoksa eksik kalabilir (uyarı verilir).
- Pafta kırpma, pafta içine düşen **blok (INSERT) içeriğini** de yazar: bazı ofisler kolon detay paftasını ya da metraj tablosunu
  blok olarak koyar (A4-A5 kolon paftaları böyleydi; 250 MB üstü dosyada bu geçiş atlanır).
- **Kat / pafta bazında** özet (`summary.by_drawing`, Excel "Kat Bazında"): her planın kolon / perde / kiriş / döşeme /
  temel betonu, kalıbı, oranla demiri; donatı paftalarının çap bazında kg'ı ve kotu.
- **Sarf ve fire** (proje parametreleri, `quantity/boq.py: structural_items`): beton fire %, demir fire/bindirme %,
  bağ teli kg/ton, plywood levha adedi (kalıp m² / levha m² / kullanım sayısı), kalıp yağı L/m², çivi kg/m².
  Hepsi keşif listesinde ayrı kalem; fiyatlanır ve süreye girer.

## Gerçek çizimlerle kalibrasyon

Firmanın çizimleri geldiğinde:
1. Çizimi yükle, **Katman eşleme** panelinde katmanları ata.
2. Yakalanmayan eleman tipleri için `layer_profile.py` içindeki `DEFAULT_PROFILE`'a firma standardı regex'lerini ekle.
3. Farklı etiket formatları için `text_parser.py` regex'lerini genişlet; `tests/test_text_parser.py`'ye örnek ekle.
4. Kiriş çizim tekniği (çift çizgi / polyline / blok) farklıysa `detectors/beams.py` heuristiklerini ayarla.

## Gerçek mimari / elektrik çizimlerle kalibrasyon

Mimari ve elektrik dedektörleri şimdilik sentetik çizimlerle (`tests/fixtures/make_dxf.py`) doğrulandı. Firmanın gerçek paftaları geldiğinde:
1. Çizimi ilgili disiplinle yükle; **Katman eşleme** panelinde duvar / kapı / pencere / tava / kablo / armatür katmanlarını ata.
2. Firma katman standardını `layer_profile.py` içindeki `DEFAULT_PROFILE`'a ekle (`wall`, `door`, `window`, `tray`, `cable`, `conduit`, `fixture`).
3. Etiket biçimleri farklıysa `labels_ext.py` regex'lerini genişlet, `tests/test_disciplines.py`'ye örnek ekle.
4. Blok adlarından kategori/ölçü çıkarımı için `labels_ext.py` içindeki `FIXTURE_CATEGORIES`, `opening_type_from_name`, `size_from_name`.

## Katmanlı sistemler: kenet / kiremit / teras çatı, mantolama (`catalog.py: components`, `parser/materials.py`, `services.project_systems`)

Çatı ve cephede katmanlar çizilmez, yazılır. Bu yüzden bir katalog kalemi **sistem** olabilir: `components` listesi
(`{"code": "OSB", "factor": 1.0, "spec": "11"}` …) o kalem ölçüldüğünde ayrı iş kalemi olarak yazılacak bileşenleri ve
çarpanlarını verir (miktar = sistem miktarı × çarpan; mertek m/m², dübel adet/m²). Varsayılan sistemler: `KENET_CATI`,
`KIREMIT_CATI`, `TERAS_CATI` (CAT), `MANTOLAMA_SISTEM` (CEP); Standart sayfasından `OSB×1:11; MERTEK×1.7:5x10` biçiminde
yeni sistem eklenir.

- **Projeden çıkarma**: her çizimin bütün yazıları (blok içi dahil) taranır (`scan_materials`): "OSB 11 mm", "10 cm TAŞYÜNÜ",
  "BUHAR KESİCİ", "KENET ÇATI" → bileşen kodu + kanıt + kalınlık (`drawing.materials`). Çatı katmanı için öneri bu kanıta
  göre seçilir: yazılarda KENET varsa `KENET_CATI`, TERAS/GEZİLEN varsa `TERAS_CATI`, KİREMİT varsa `KIREMIT_CATI`, yoksa düz
  `CATI_KIREMIT`; mantolama katmanı her zaman `MANTOLAMA_SISTEM` önerilir.
- **Bileşen kararı** (`project_systems`): kullanıcı kararı > çizim kanıtı ("projede yazıyor", kalınlık kanıttan) > yok
  ("projede yok"). Yazmayan bileşenler keşfe girmez ve **kullanıcıya sorulur** ("Kenet çatı sistemi (200 m²): projede yazmıyor →
  Buhar kesici, Aşık"); kullanıcı *Ekle (projede var)* der ya da yok bırakır, özelliği (kalınlık) düzenler. Kararlar
  `project.systems` içinde saklanır. Panel proje sayfasında ve Metraj sayfasında.
- **Keşif**: sistem satırı listede kalır ama fiyatlanmaz (`detail.system`); dahil bileşenler `<bileşen>:<özellik>` anahtarıyla
  ayrı kalem olur (`expand_systems`) ve Birim Fiyatlar'da fiyatlanır. API: `GET/PUT /api/projects/{id}/systems`.
- Cephe için ayrıca söve, silme, denizlik kalemleri ve katman önerileri eklendi (söve çizgi → m, blok → adet).

## Türetilmiş kalemler ve tamlık kontrolü (`services.derived_items`, `roof_area`)

Detaylı maliyette gözden kaçmasın diye çizimden **türetilen** kalemler keşfe eklenir (fiyatlanır, "Türetildi" notu,
`detail.derived`; proje parametresi `derived_off` ile kural kapatılır — panelde *kapat / aç*):

| Tetik | Türetilen | Miktar |
|---|---|---|
| Boya | Boya astarı | boya m² |
| Kat planı oturumu (statik ya da mimari) | Tavan sıva + astar + boya | oturum × kat sayısı |
| Mahal alanı yazıları ("LOBİ 45,20 m²", "CALZEDONIA 106.60m2") | Şap; döşeme kaplaması (tip seçilecek) — **yalnız seçili mahal türlerinde** (`finish_rooms`: LOBİ, VİTRİN, GİRİŞ, HOL, KORİDOR, FUAYE; ya da `finish_area_m2` elle) | seçili mahaller × kat sayısı (şap × kalınlık) |
| Temel (radye / sürekli) | Temel su yalıtımı; grobeton; koruma şapı | temel alanı (grobeton × kalınlık) |
| Çatı sistemi biliniyor (parametre ya da kesit notu) | Çatı alanı bilgi satırı + sistem kalemi → bileşenler | çatı alanı |

**Çatı alanı**: çizimde ölçülen çatı kalemi > parametre > en büyük (bodrum olmayan) kat planı oturumu. **Çatı sistemi**: parametre >
kesit / detay notlarındaki tek kanıt (KENET / KİREMİT / TERAS). Bina oturumu artık mimari plandaki duvar çokgenlerinden de
çıkar (`building_footprint`: en büyük parça), cephe brüt alanı için bodrum paftaları atlanır.

Mahal yazıları `drawing.rooms` alanında saklanır (`parser/schedules.py: parse_rooms`); mağaza gibi kapsam dışı mahaller kontrol listesinde
"kaplama dışı" olarak sayılır, mahal yazısı hiç yoksa "alan yok" uyarısı verilir (bloğun tamamı şaplanmaz; B2'de yalnız vitrin ve lobiler).

**Tamlık kontrol listesi** (miktarı türetilemeyen ama olması gereken işler; sistem panelinde uyarı): çatı sistemi seçilmedi
(betonarme teras ise eğim betonu + buhar kesici + ısı yalıtımı + su yalıtımı + koruma betonu), cephe sistemi seçilmedi (cephe boyası /
astar / mantolama), pencere var ama söve / denizlik / silme yok, cam m² yok, çok katlıda korkuluk / küpeşte yok, ıslak hacim seramiği
ve yalıtımı yok, temel drenajı, döşeme kaplaması tipi. API: `GET /api/projects/{id}/systems` → `roof`, `derived`, `checklist`.

**Çerçevesiz paftalar**: çerçeve yoksa ve kümeleme başlık sayısından az pafta bulursa, aynı hizadaki pafta başlıklarının x
konumlarından bantlar üretilir (`sheets.py: boxes_from_titles`, kaynak "title"): başlık satırındaki aynı boy yazılar da pafta
başlığıdır ("DOĞRAMALAR", "PREKAST KALIP"), pafta adı satırdaki başlıktır (daha büyük alt görünüş başlığı aday listesine gider), aykırı
noktalar yüzdelik yayılımla elenir. B2 BLOK 11 paftaya ayrıldı ve her pafta doğru tipe (kat planı / kesit / görünüş / doğrama / prekast) atandı.
Plan tipleri: `mim_dograma` (poz listesi) ve `mim_prekast` eklendi; "… KAT PLANI" başlığı statik xref katmanları olsa da mimari sayılır.

## Gerçek çizimde öğrenilenler (B2 BLOK mimari uygulama seti, 520 MB DXF, 7 Eyl 2026)

- 11 pafta çerçevesiz yan yana (vaziyet, bodrum / zemin / 1. kat / çatı katı / +15.65 planları, kesitler, görünüşler, doğramalar,
  prekast kalıp); küme tespiti prekast dokusu (590 bin nesne, `FB_Prekast`) yüzünden 3 kümede kaldı → paftalar başlık x
  konumlarından elle tanımlandı. Planlar bağlanmış xref bloklarında; akış tabanlı blok açma ile kırpıldı (5 dk).
- `$INSUNITS` mm yazılı, çizim cm; yazı yüksekliği sağlaması birimi otomatik düzeltti (1. kat paftasında 20'den az yazı var, düzeltilmedi).
- Duvarlar `brn_duvar_gazbeton` kapalı çokgenleri (kalınlık 10 / 15 / 20 / 25 cm); kapı-pencere blok değil çizgi, sayılmadı;
  doğrama **poz listesi** (`Poz: EMP1 / Adet: 82`, 14 poz, 170 adet) keşfe girdi ve plan blok sayımıyla tutuyor (EMP1 kör kasa 81, EMP7 34).
- Kesit notlarından kenet çatı sistemi (galvaniz kenetli sac, OSB, taşyünü + Z profil, buhar dengeleyici) tanındı; ayırıcı keçe ve
  mertek sorulur. "Bitümlü çift kat izolasyon" temel notudur, çatı membranı sanılabilir (kontrol edin). Teras katmanları (meyil betonu,
  su yalıtımı, XPS, koruma betonu) yazıyor ama teras alanı ölçülmedi.
- Çatı alanı ve cephe brüt alanı için çizimde kapalı çokgen yok: zemin kat duvar / kolon çokgenlerinin dış hattı (1.434 m², çevre 171 m)
  elle girildi. Cephe prekast; panel kodları bu dosyada yok (prekast kalıp paftası yalnız MN-x monoblok pencere tipleri).

## Gerçek çizimde öğrenilenler (B2 BLOK + "B Bloklar uygulama" DXF'leri, 8 Eyl 2026)

- **Kapı / pencere blok değil poz yazısı**: bu ofis planda her doğramayı yalnız "EMP1", "EMP3 - KANATLI" yazısıyla
  işaretliyor; adet ve açıklama doğrama paftasındaki poz listesinde ("Poz: EMP3 / 9 Adet AÇILIR KAPI"), ölçü ise plan
  paftalarının altındaki görünüşlerde (brn_windows dikdörtgenleri: genişlik yatay, yükseklik düşey) ya da yazının yanındaki
  "130 x 250" ölçü yazılarında (üç ayrı TEXT; döndürülmüş yazıda alt alta). `detectors/openings.py`:
  - `poz_catalog`: çizimden poz → ölçü (görünüş dikdörtgeni > ölçü yazısı; kapıda yükseklik büyük olan) ve poz → kapı /
    pencere (poz listesi notu; ölçüsü ≥ 195 cm yüksekse kapı; EMP3A, EMP3'ün türü). Çizime `drawing.poz` olarak yazılır.
  - `detect_poz_openings`: bilinen önekli (proje poz listesi / K, P…) poz yazısı bir **duvara 2 m içinde** ise plandaki
    boşluktur; görünüşteki poz yazılarının yanında duvar olmadığından sayılmaz. Zemin kat: 46 (EMP1 35, EMP3 8…), çatı katı 44.
  - Proje bilgisi `services.detect_params(project, session)` ile her analize girer (öteki paftaların `poz` sözlüğü ve
    doğrama elemanları). Poz listesi sonradan yüklenirse `drawings._refresh_openings` kapı / pencere bulamamış mimari
    planları yeniden analiz eder.
  - Keşif: plandan sayılan pozlu boşluk **duvardan düşülür**, adet ve **cam m²** poz listesinden gelir (proje toplamı;
    `architectural_items(schedule_poz=…)`, `standard_items` DOGRAMA satırına ölçü notu + `cam` kalemi). B2: 131 pencere pozu,
    298 m² cam; duvarlar 130 m² boşluk düşülmüş.
- **Birim**: B2 dosyası başlıkta mm, gerçekte cm. Paftaların çoğu yazı yüksekliğinden cm'yi buluyor ama 1. kat / görünüş /
  doğrama paftaları (az ya da büyük yazı) mm'de kalıyordu → pafta oylaması. Kaynak dosya taramasındaki üst düzey yazı
  medyanı (`SheetScan.suggested_unit`) bu dosyada yanıltıcı (285 birimlik kot yazıları): bilgi olarak saklanır, karar vermez.
- **Plan geometrisi olmayan pafta**: "B_Bloklar_Uygulama_04.dxf" 3.048 nesnelik bir açıklama katmanı (mahal yazıları,
  merdiven, aydınlatma sembolleri); duvarlar dış referansta kalmış. Mimari paftada duvar yok ve 60'tan az çizgi / çokgen
  varsa `analyze._architectural` ilk uyarı olarak "plan geometrisi yok, xref'leri bağlayıp (Bind) yeniden yükleyin" der;
  özet tabloda **Sorun**. Aynı dosyanın 9 başlıksız kümesi (30–500 nesne, gizli DATA yazı katmanları yüzünden "elektrik"
  sayılmıştı) artık parça olarak elenir.
- Kat yüksekliği 0 girilmiş projede duvar yüksekliği sessizce 3 m alınıyordu: keşif satırına not, proje sayfasına uyarı.

## Keşif standardı: iş grupları, ÇŞB pozları ve ölçü kuralları (`standard/rules.py`)

Keşif listesi Türkiye'deki yaygın düzende dört iş grubuna ayrılır: **kaba yapı (inşaat)**, **ince işler (mimari)**,
**mekanik tesisat**, **elektrik tesisatı** (+ altyapı / peyzaj). Her kalem mümkünse bir Çevre, Şehircilik ve İklim
Değişikliği Bakanlığı (ÇŞB) **poz numarası** taşır ve miktarı o pozun **ölçü kuralına** göre hesaplanır:

| Kalem | Poz | Ölçü kuralı |
|---|---|---|
| Beton | 15.150.1006 (C30/37) | projedeki hacim, m³ |
| Kalıp | 15.180.1003 (plywood) | kalıp gören yüzler; inşaat boşluğu çevre kalıbı sayılmaz |
| Demir | 15.160.1003 (Ø8–12) / 15.160.1004 (Ø14–28) | donatı boyu × birim ağırlık, ton |
| Gazbeton duvar | 15.225.1004 / 1007 / 1010 (10 / 15 / 20 cm) | projesi üzerinden; **0,10 m² altı boşluk düşülmez** |
| Sıva | 15.280.1008 | sıvanan yüzeyler, **tüm boşluklar düşülür** |
| Boya | 15.540.1509 | boyanan yüzeyler, tüm boşluklar düşülür |
| Kablo / boru | 35.140.xxxx / 25.305.xxxx | hat boyu, m |

Katalogdaki kalemin `poz` alanı doluysa (Standart sayfası) o kullanılır; sezgisel kalemlerde `rules.default_poz` eşlemesi
denenir. Keşif yanıtı `by_group` (iş grubu bazında), `rules` (uygulanan kurallar) ve her kalemde `poz` / `work_group`
taşır; Excel'de "İş grubu" ve "Poz" sütunları vardır. Kaynaklar: yfk.csb.gov.tr birim fiyat tarifleri, birimfiyat.net poz sayfaları.

## Mekanik / sıhhi / havalandırma / yangın sezgisel tanıma (`detectors/mechanical.py`, disiplin `mechanical`)

Standart dışı tesisat paftaları da KÇS katmanı ya da elle eşleme olmadan okunur:
- **Boru**: boru katmanlarındaki hatlar uç uca zincirlenir; çap etiketten (`Ø110 PVC`, `DN65`, `PPRC 32`, `1 1/4"`) ya da
  katman adından; **sistem** katman adı + etiketten katalog koduna gider: PVC / pis su / atık / drenaj → `BORU_PVC`,
  PPRC / temiz - soğuk - sıcak su → `BORU_PPRC_TEMIZ`, PE → `BORU_PE`, bakır / gaz → `BORU_BAKIR`, yangın / sprinkler →
  `YANGIN_BORU`, çelik / DN / ısıtma - soğutma → `BORU_CELIK` (anlaşılmazsa çelik + uyarı).
- **Kanal**: `600x400` dikdörtgen (`HAVA_KANAL`), `Ø315` yuvarlak / spiral (`HAVA_KANAL_YUVARLAK`), flex (`FLEX_KANAL`); çift
  çizgi kanalda aralık = genişlik (aynı katman, boyları örtüşen çiftler). Blok içi çizgiler hat sayılmaz.
- **Cihaz / vitrifiye**: cihaz katmanlarındaki bloklar (menfez, vana, sprinkler, radyatör, fancoil, VRF, klima santrali, fan,
  damper, lavabo, klozet, pisuar, batarya, süzgeç, pompa, kazan, hidrofor, depo, yangın dolabı, tüp…) blok / katman
  adından koda gider; boru / kanal katmanındaki bloklar yalnız adı tanınırsa sayılır; tanınmayan blok `MEKANIK_CIHAZ`.
- Elemanlar `meta.ksf_code` taşır: keşifte katalog kalemi olarak (poz, reçete, iş grubu MEK) yazılır. Plan tipleri
  `mek_yangin / mek_hav / mek_isitma / mek_sihhi` bu disipline gider; mimari paftadaki tesisat katmanları "+ Mekanik" ek
  disipliniyle açılır (B2 Blok'ta `-ST-Soğuksu`, `-0-Kolon Pissu`, `-HT-Kanal Egzost`, `brn_vitrifiye` böyle tanınır).

## KÇS statik paftaları ve başlıksız dosyalar (8 Eyl 2026, "Örnek Proje" STA-00…07 / STA-TEM)

- `KSF-STA-KOLON-40x40x300`, `KIRIS-30x60`, `PERDE-25x300`, `DOSEME-20`, `TEMEL / RADYE` katmanları **statik motora** gider
  (beton, kalıp, demir; `layer_profile.KSF_STRUCTURAL`): kesit / kalınlık katman adından, güven 0,95; `_ON` (ön boyut),
  `_KESIN` ekleri atılır. Kiriş / perde tek eksen çizgisiyle çizilmişse çizgiler kesiti katman adından alan elemanlardır
  (`analyzer._centerline_elements`). Üçüncü sayı (300) kat yüksekliğidir: çizime H olarak yazılır.
- `REF_…`, `SEMA_…`, `…METRAJ_DISI` katmanları (referans görünüş, şema) hiçbir disiplinde ölçülmez.
- **Başlıksız dosya paftaya bölünmez**: pafta seçimi yalnız en az iki başlıklı pafta varsa (ya da dosya 40 MB üstüyse) sorulur;
  plan + görünüş + notlar yan yana duran tek blok planı tek çizimdir (`SheetScan.multi_sheet`).
- Plan tipi dosya adındaki kısa kodlardan da tanınır: `STA-TEM` temel kalıp, `STA-03` kat kalıp, `MIM-01`, `ELK-02`, `MEK-00`,
  `HAV`, `SIH`, `YAN`, `ALT`, `PEY`, `CAT`, `CEP`; kat sırası dosya adındaki sayıdan (`STA-03` → 3. kat). Başlık ve dosya adı
  tanınmazsa KSF katmanlarının baskın disiplini plan tipini verir (`planset.ksf_plan_type`); KSF katmanlı paftada disiplin
  "standart"tır.

## Kat yüksekliği kotlardan (`parser/levels.py`, `services.storey_heights`)

Planlarda ve kesitlerde kot yazıları iki sistemde olabilir: parantez dışı yapı sıfırı, parantez içi mutlak ("-4.15 (+0.00)",
"+0.00 (+4.15 sıfır kotu)", "+11.50(+15.65)"); parantezli yazılardan ofset bulunur, her şey mutlak sisteme çevrilir; hangi
sistemde olduğu belirsiz çıplak değerler sayılmaz. Birbirine 2 m'den yakın seviyeler (kaplama, peyzaj, asma kat, platform)
elenir; kalan seviyelerin ardışık farkı kat yüksekliğidir. Her paftanın kotu etiketten ("+7.95 KOTU KALIP PLANI", "15.65 KOTU
PLANI") ya da "… KOTU" yazısından; kotu olmayan planlar kat sırasıyla (temel, bodrum, zemin, asma, birinci…, çatı) seviye
dizisine oturtulur. Öncelik: çizime girilen H > paftanın kotu ile üst seviye farkı > kat sırası > projeye girilen H > medyan
kat farkı > 3,0 m. Proje yanıtında `levels`; keşif notunda kaynak yazar. B2 Blok: 0,00 / 4,15 / 7,95 / 10,65 / 15,65 → 4,15 /
3,80 / 2,70 / 5,00 m.

## Otomatik katman eşleme (eşlemeli paftalar) ve kaba yapı türetmeleri

- Tavan, döşeme kaplaması, cephe, çatı, peyzaj, altyapı gibi **eşlemeli** paftalarda katman adından tanınan kalemler
  (`SUGGEST_RULES`) artık onay beklemeden ölçülür: güven 0,55, `meta.auto_mapped`, katman bilgisinde `auto`; Elemanlar
  sayfasında "otomatik" rozeti, **Onayla** düğmesi ya da "— ölçülmez —" seçimi (tam ad yok-sayma, `LayerProfile.is_ignored`).
- **Temel kazısı**: temel alanı × `excavation_depth_m` (varsayılan 1,5 m) × `excavation_margin` (1,15 şev / çalışma payı) →
  `KAZI` (reçete: ekskavatör + kamyon saati); **geri dolgu** = kazı − temel betonu − grobeton. Kapatma: `derived_off` içine
  `kazi`, `geri_dolgu`.
- **Lento** reçetesi (yerinde döküm varsayımı): adet başına 0,03 m³ beton, 3 kg demir (`DEMIR`, 15.160.1003), 0,3 m² kalıp;
  bunların işçilik ve iskele reçeteleri zincirleme açılır. Prefabrik lento kullanılıyorsa katalogdan sıfırlanır.
- Doğrulanmış pozlar genişledi: PVC pis su Ø75 / 100-110 / 125 (25.305.6102-6104), PPRC 20 / 40 mm (25.305.2101 / 2104),
  PE Ø32 (25.305.7101), dikdörtgen kanal kenara göre (25.470.1101-1103), spiral kanal (25.470.1204), sprinkler DN20
  (25.705.1102), 40x40 seramik (15.375.1053).

## Reçeteler: her kalemden alt işler (`quantity/recipes.py`, `CatalogItem.recipe`, `rules.RECIPES_BY_KIND`)

Zaman ya da maliyet doğuran her alt iş keşfe girer: ana kalem keşfe yazılınca reçetesi sorulmadan açılır ("reçete" rozeti,
`detail.recipe / parent / depth`), bileşenin kendi reçetesi de zincirleme açılır (derinlik ≤ 4, aynı kod zincirde tekrar etmez):

```
Çelik çatı 1.000 m²   → çelik konstrüksiyon 25 t → ankraj bulonu 250 → tij 250, somun 500, pul 500
                                                 → kaynak 1.000 m, antipas 500 m², boya 500 m², montaj 750 saat, vinç 100 saat
                      → aşık 1.600 m, sandviç panel 1.050 m² → panel vidası, mahya kapama, panel montajı
Döşeme 800 m²         → kalıp iskelesi 800 × (H − d) m³ (ÇŞB 15.185.1001; reçete değil, türetilir)   Beton → pompaj m³
Cephe (mantolama / kompozit / giydirme / taş / boya) → iş iskelesi cephe brüt m² (tek kez, türetilir) (+ taşıyıcı profil, ankraj, vinç)
Prekast panel (adet)  → ankraj 4, kaynak 1,2 m, montaj 2 saat, vinç 0,5 saat, derz 6 m
Pencere / kapı / doğrama (adet) → lento, montaj saati, montaj köpüğü      Duvar m² → gazbeton tutkalı 4 kg
```

Katalogdaki 137 kalemin varsayılan reçetesi vardır (`catalog.DEFAULT_RECIPES`, `rules.RECIPES_BY_KIND`); her iş grubunda
**işçilik saatleri** ayrı kalemdir (birimi `saat`: beton yerleştirme 1,0 / m³, demir 20 / t, kalıp kurma + söküm 1,2 / m²,
duvar örgü 0,8 / m², sıva 0,7, boya 0,3, seramik 1,0, kablo çekme 0,05 / m, PPRC 0,25 / m, çelik boru 0,5 / m, kanal 0,6 / m,
sprinkler 1,2 / adet, vitrifiye 2 / adet, asansör 240 / adet…) ve sarf / yardımcı imalat da yazılır (vibratör, kür, tutkal,
harç, alçıpan profil + vida + derz bandı, seramik yapıştırıcı + derz dolgusu, askı teli, buat, tava askısı + ek, boru askısı +
fittings + kaynak, kanal askısı + flanş, yivli kaplin, hendek kazısı + yatak kumu + geri dolgu, kum yatak, vinç…).

Reçete biçimi (Standart sayfası): `KOD×çarpan:özellik; …`, çarpan sonundaki `H` kat yüksekliğiyle çarpar
(`KALIP_ISKELESI×1H`). Çarpanlar yaygın uygulama varsayılanıdır; satır notunda "reçete varsayılanı" yazar. Çizimde zaten
ölçülmüş bir kalem (ör. iskele) reçeteyle çift yazılmaz, not düşülür. Tümünü kapatmak: `derived_off` içine `recete`.
İşçilik saatleri (montaj, kaynak) ayrı kalemdir ve Birim Fiyatlar'da adam-saat / fiyatla maliyete girer.

## Aynı paftada birden çok disiplin (`analyzer.analyze_drawing(extra_disciplines=…)`)

Bir paftada mimari + elektrik ya da elektrik + mekanik birlikte çizilmiş olabilir. Her çizimin bir **ana disiplini** ve
istenirse **ek disiplinleri** vardır (`Drawing.disciplines`; proje sayfasında disiplin hücresindeki "+ Elektrik" düğmesi):
- Katmanlar sırayla ana, sonra ek disiplinlerin profiliyle sınıflanır; ilk tanıyan disiplin kazanır. Her disiplinin
  dedektörü kendi katmanlarıyla çalışır; elemanlar tipine göre keşifte doğru iş grubuna düşer.
- **KSF-… katmanları her disiplinde** standart kuralla ölçülür (standarda uygun çizilmiş bir kalem hangi paftada olursa
  olsun sayılır).
- Analiz, açılmamış disiplinlerin katman kanıtını sayar (`discipline_hints`: geometrik nesne ≥ 8) ve uyarı verir;
  mimari paftadaki KOLON / KİRİŞ katmanları için statik açılmaz (statik planda sayılır, çift sayım olmasın).
- Statik metraj eleman tipine göre alınır; disiplini ne olursa olsun kolon / kiriş elemanı olan her pafta girer (donatı paftası hariç).

## Büyük dosyada blok içeriği (akış) ve doğrama poz listesi

- **Blok içinde plan** (bağlanmış xref, doğrama blokları, kolon detay blokları): 100 MB üstü DXF'te pafta kırpma, blok içeriğini
  ezdxf'siz akışla açar (`sheets.py: _expand_blocks_stream`). Yalnız paftaya düşen INSERT'lerin blokları okunur (iç içe 4 seviye),
  nesneler yerleştirme / ölçek / dönme ile dönüştürülür, katmanı "0" olan alt nesneler INSERT'in katmanını alır. INSERT'in kendisi
  boş blok tanımıyla korunur (kapı / pencere / armatür adet sayımı çalışır). 60 bin nesneden büyük bloklar doku / 3B model
  sayılır, açılmaz (uyarı). B2 BLOK (520 MB, 667 bin nesne, 1.143 blok): 11 pafta 5 dakikada kırpıldı.
- **Doğrama poz listesi** (`parser/schedules.py`): "Poz: EMP1 / Adet: 82", "9 Adet AÇILIR KAPI", "Poz: EMP914" (bitişik: EMP9 14,
  düşük güven) yazıları okunur; her poz `DOGRAMA:<poz>` kalemi olur (adet), açıklama nota yazılır. Aynı poz birden çok yerde
  yazılıysa en büyük adet alınır. Mimari ve katman eşlemeli çizimlerde otomatik çalışır.

## Cephe: etiket sayımı (prekast panel) ve cephe brüt alanı

- **Etiket sayımı** ölçüm kuralı (`label_count`): katmandaki her yazı bir kalem, her kod ayrı satır (`prekast_panel:gp-4` 20 adet).
  Kot ("+4.15"), sayı, tek karakter ve pafta işaretleri (KESİT-3, 1-1 KESİTİ, DETAY) sayılmaz. Eşlemeye **etiket deseni** eklenebilir:
  `item:PREKAST_PANEL:label_count:^(GP|EP)` (Elemanlar sayfasında desen kutusu) → yalnız uyan yazılar sayılır; aynı deseni birden
  çok katmana verebilirsiniz (A5 BLOK'ta GP kodları "inova prekast - YAZI", EP kodları "0" katmanındaydı: 80 panel, 17 tip).
  Katalog kalemi `PREKAST_PANEL`; katman adında PREKAST/PRECAST geçince önerilir.
- **Cephe brüt alanı** (`services.facade_area`), öncelik sırasıyla: (1) görünüşte `CEPHE_BRUT` kalemine eşlenen dış hat çokgeni,
  (2) proje parametresi *Brüt cephe alanı* (elle), (3) tahmin: her kalıp planında döşeme / kiriş / kolon / perde çokgenlerinin
  birleşimi (boşluklar 0,6 m'ye kadar kapatılır, delikler doldurulur, 15 cm cephe payı) → dış çevre × kat yüksekliği × kat sayısı
  (`building_footprint`). Net = brüt − cam (CAM kalemi varsa). A4-A5 blokta kat başına 478–496 m çevre, ~1.800 m² cephe; çatı
  katı paftasında döşemeler bulunamadığı için çevre şişer (elle düzeltin).
- **Cephe sistemi** proje parametresi (`facade_system`: MANTOLAMA_SISTEM, KOMPOZIT_PANEL, CEPHE_TASI…): seçilince keşfe
  "Cephe brüt alanı" bilgi satırı (fiyatlanmaz) ve miktarı net cephe alanı olan sistem kalemi eklenir; katmanlı sistemse
  bileşenleri sorulur. Görünüşte aynı kalem zaten ölçülmüşse ikinci kez eklenmez. Sistem panelinde alan ve kaynağı görünür.

## Plan seti (`planset.py`)

`PLAN_TYPES`: 7 grupta (statik, mimari, elektrik, mekanik, altyapı, peyzaj, asansör) ~30 plan tipi; her biri için başlık
düzenli ifadesi (Türkçe harfler ASCII'ye indirgenir, sıra önemli: özel olanlar önce), analiz disiplini, varsayılan
gereklilik (`required` / `optional`), `analyze` (kesit / detay: yüklenir ama metraja girmez) ve `satisfies`
(genel elektrik tesisat planı aydınlatma + kuvveti karşılar). `classify_title()` başlıklardan ilk tanınan tipi verir
(plan başlığı kesit / detay başlığına tercih edilir); `discipline_from_layers()` katman sayımından baskın disiplini bulur;
`resolve_plan()` ikisini birleştirir. `plan_check()` projenin çizimlerine göre durum listesi ve uyarıları üretir.
Yeni bir plan tipi eklemek `PLAN_TYPES` listesine bir satırdır.

## Cephe: ön / arka / sağ / sol ayrı ayrı (`services.footprint_sides`)

Cephe tek bir "brüt alan" değildir; her yönün kendi işi vardır (kaplama, boya, söve, denizlik, korkuluk,
prekast). Bina dış hattının **her kenarı, dışa bakan normaline göre** dört yönden birine yazılır:

```
+X sağdaki cephe   −X soldaki cephe   +Y üstteki cephe   −Y alttaki cephe
```

Yönler **çizim eksenidir**, pusula değil: çizimin kuzeyi bilinmez, hangi cephenin "ön" olduğunu kullanıcı
söyler. Görünüş paftasındaki `ÖN / ARKA / SAĞ / SOL GÖRÜNÜŞ` başlıkları bu eşlemeyi kurmak için okunur.

**Kendi sağlaması var:** dik kenarlı bir binada dört yönün toplamı dış çevreye **eşittir**. Eğik kenarda
izdüşümlerin toplamı kenar boyunu aşar (45°'de 1,41 katı) — çünkü eğik yüzey iki görünüşte birden yer alır;
bu fazlalık `egik_fazla` ile ayrıca bildirilir.

Alan / çevre ve kenarlar **aynı çokgenden** türer (`footprint_polygon`). Ayrı hesaplanırken kenar toplamı
40 m, çevre 163 m çıkıyordu — concave hull ve pay yalnız birinde uygulanıyordu.

B2 BLOK'ta ölçülen (kat planı dış hattı × kat yüksekliği × kat sayısı):

| | m² |
|---|---:|
| Sağdaki cephe (+X) | 287 |
| Soldaki cephe (−X) | 287 |
| Üstteki cephe (+Y) | 579 |
| Alttaki cephe (−Y) | 579 |
| **Toplam** | **1.732** |

### Görünüş paftasında ne var, ne yok

B2 BLOK'un `GÖRÜNÜŞLER` paftası ölçüldü: dört başlık (ÖN / SAĞ / ARKA / SOL) 2×2 düzende duruyor ve
paftanın 273.000 nesnesinin neredeyse tamamı `FB_Prekast` katmanında. Ama bu geometri **bina silueti değil**:
yoğunluk haritası 55 m × 2,5 m'lik iki yatay bant gösteriyor — prekast panel bandı. Bina dış hattını
çizebilecek diğer katmanlarda toplam 1.183 m çizgi var, dört cepheyi kapatmaya yetmiyor.

Bu yüzden cephe alanı **görünüşten değil kat planı dış hattından** ölçülüyor. Görünüşten ölçüm, ancak siluet
çizili bir sette (ya da katman eşlemesi yapılmış bir görünüşte) mümkün olur.

### Cephe sistemi yön yön kalem üretir

Cephe sistemi seçilince (mantolama / kompozit / cephe taşı / prekast) keşifte **her cephe ayrı satır** olur:

```
Mantolama sistemi (katmanlı) — Üstteki cephe (+Y)     449,6 m²
Mantolama sistemi (katmanlı) — Alttaki cephe (−Y)     449,6 m²
Mantolama sistemi (katmanlı) — Sağdaki cephe (+X)     222,6 m²
Mantolama sistemi (katmanlı) — Soldaki cephe (−X)     222,6 m²
```

Her cephenin kendi işi, kendi iskelesi, kendi teslim sırası vardır; tek satır bunu gizliyordu. Toplamları
net cephe alanına eşittir (1.344 m²) ve katmanlı sistem bileşenleri (EPS, file, sıva, boya, dübel) proje
toplamı üzerinden açılır — malzeme siparişi toplamdan verilir.

**Cam dağıtımı bir kabuldür ve öyle yazılır:** doğrama pozları proje toplamıdır, hangi doğramanın hangi
cephede olduğu bilinmez; cam her cepheye brüt payıyla dağıtılır ve kalemin notunda bu açıkça geçer.
Dış hat okunamazsa yön ayrımı yapılmaz, tek satır kalır — uydurma yön üretilmez.

Sistem paneli tek sistem görür: bölünmüş satırların miktarı toplanır, parçalar `parcalar` alanında taşınır.

Testler: `backend/tests/test_cephe.py` (12 test; dikdörtgen / çıkıntılı / eğik bina, yön ayrımı, cam kabulü,
yön çıkmazsa tek satır).

## Doğrama zinciri: cam → doğrama → körkasa (12 Eyl 2026)

İlke: **varlık ile ölçü ayrı şeylerdir.** Bir yerde cam varsa orada doğrama da, körkasa da vardır; ölçüsü
okunamadı diye kalem silinmez — adet keşifte kalır, eksik olan **ölçü** açıkça bildirilir.

Zincir katalog reçetesinden gelir (`catalog.DEFAULT_RECIPES: DOGRAMA`) ve poz **türüne göre** ayrışır:

| poz türü | alt işler |
|---|---|
| pencere | körkasa ($SIZE), körkasa profili (çevre), körkasa montajı, cam fitili, silikon, mastik, denizlik (genişlik), dübel |
| kapı | kapı kasası ($SIZE), pervaz (çevre), menteşe ×3, kilit, kol, stoper, eşik (genişlik), dübel, silikon |

B2 BLOK'ta 170 doğramanın 147'si pencere (körkasa), 23'ü kapı (kapı kasası) — toplam tutuyor.

### Camlı kapı artık cam üretiyor

"KAPI" geçen poz camsız sayılıyordu; oysa **fotoselli / vitrin / giyotin kapı neredeyse tamamen camdır**
(`services.GLAZED_WORDS`). AVM girişindeki bütün cam keşiften düşüyordu. Düzeltmeden sonra cam
306,9 → **328,0 m²**.

### Cam dökümü: hangi ölçüden ne kadar, hangi pozdan

Cam **ölçüye göre** birleşir (sipariş ölçü bazında verilir) ama hangi pozlardan geldiği artık etikette:

```
Cam 140×190 cm (EMP1 82)              218,5 m²    82 adet
Cam 120×150 cm (EMP7 34)               61,2 m²    34 adet
Cam 120×100 cm (EMP9 14, EMP9B 1)      18,0 m²    15 adet
Cam 150×205 cm (EMP4A 2, EMP5 3)       15,4 m²     5 adet
Cam 150×250 cm (EMP4 4)                15,0 m²     4 adet
```

Daha önce etiket tek poz yazdığı için "EMP5 camı 5 adet ama doğrama 3" gibi görünüyordu — miktar doğruydu,
etiket yanıltıyordu (EMP4A da 150×205).

### Ölçüsü bulunamayan doğrama artık kaybolmuyor

```
17 adet doğramanın ölçüsü çizimde bulunamadı (EMP8 13 adet, EMP2 2 adet, EMP1A 1 adet, EMP6 1 adet).
Adetleri keşifte var ama camı ve ölçüye bağlı alt işleri hesaplanamadı; ölçüleri doğrama paftasından girin.
```

Ölçüler plan paftalarındaki poz yazılarının yanından toplanıyor; doğrama paftasında ölçü tablosu yoksa bu
pozlar ölçüsüz kalır. Adet ve körkasa yine sayılır, yalnız cam ve denizlik hesaplanamaz.

### Kavisli / kemerli doğrama

Kemer kuşağında taşıyıcı profil, **boardex** ve taşyünü olur. Kemer yüksekliği çizimde yazmadığı için çevre
hesaplanamaz — **miktar uydurulmaz**, kalem eksik olarak bildirilir (`kavisli_dograma`, required).
`BOARDEX` katalog kalemi eklendi (m², reçetesi dübel + yalıtım işçiliği) ki elle girilebilsin.
B2 BLOK'ta kavis yazısı yok, bu yüzden bu uyarı çıkmıyor.

Testler: `backend/tests/test_dograma.py` (9 test).

## Plandan donatı metrajı: tabloya bakmadan kilogram (`parser/rebar_plan.py`)

Demirin %99'u donatı tablolarından geliyordu; tablosu olmayan projede geriye `beton × kg/m³` oranı kalıyordu
(A4-A5'te tablosuz sonuç −%24). Bu modül demiri **çizimin kendisinden** ölçer.

### 1) Adetli çağrı × çizilen kol boyu — döşeme, temel, ilave donatı

Donatı planında her donatı grubu bir çağrı yazısıyla anlatılır **ve çubuğun kendisi çizilir**:

```
çağrı   "21ƒ10/18"                  21 adet Ø10, 18 cm aralıkla
çizgi   donatı katmanında 4,95 m    çubuğun boyu (kırık çubukta her kol ayrı çizgi)
ağırlık = 21 × 4,95 m × 0,617 kg/m = 64,2 kg
```

Boy **ölçülür**, tahmin edilmez. Her çubuk parçası en yakın çağrıya bağlanır; 3 m'den uzak parça hiçbir
çağrıya bağlanmaz (yoksa aks ve çerçeve çizgileri demire dönüşür). Marka / poz / grup katmanlarındaki
çizgiler çubuk sayılmaz.

**A4-A5'in 11 donatı paftasında, müellifin poz tablolarına karşı:**

| | plandan (bizim) | tablodan (müellif) | fark |
|---|---:|---:|---:|
| Temel X / Y / ilave | 635.737 kg | 635.545 kg | +%0,0 |
| Döşeme (8 pafta) | 270.767 kg | 272.346 kg | −%0,6 |
| **Toplam** | **906.504 kg** | **907.891 kg** | **−%0,2** |

Pafta bazında en kötü sapma %2,8. Yani tablo olmadan da aynı sayıya varıyoruz; tablo artık kaynak değil,
**doğrulama**. Tablo varsa iki sonuç karşılaştırılıp uyarı olarak yazılır; tablo yoksa plan hesabı demirin
kaynağı olur (`kaynak: plan`).

### 2) Etriye — kesit ve boy biliniyorsa

```
adet   = boy / aralık + 1
çevre  = 2 × (b + h) − 8 × paspayı + 2 × kanca
80/30 kolon, H = 3,95 m, Ø12/10  ->  40 adet × 2,20 m × 0,888 = 78,1 kg
```

Aralık yazısı önce elemanın yakınında, yoksa paftanın baskın etriye tarifinde aranır. Yalnız **ETR** geçen
yazılar etriye sayılır — `ƒ12/15` tek başına döşeme donatısı da olabilir. Yazı bulunamazsa hesap yapılmaz:
uydurulmuş bir aralıkla tonaj üretmek, hesap yapmamaktan kötüdür.

### Birim sağlaması: çizim kendi birimini ele veriyor

Donatı planı çubuk boylarını **cm** olarak yazar (`VM Poz Kollar`: `495`). Ölçülen boy bu sayıyı vermiyorsa
`$INSUNITS` yanılıyor demektir — ve bu, yazı yüksekliği tahmininden **daha güçlü** bir kanıttır: tahmin değil,
çizimin kendi beyanı.

Bu sağlama gerçek bir hata buldu: A4-A5'in **8 donatı paftası "mm" yazıyor ama cm çizilmiş** (oran tam 10,0,
1.731 örnek). Tablo değerleri kg olduğu için metraj bozulmamıştı, ama plandan ölçüm imkânsız hale geliyordu.
Artık `suggested_unit` ile düzeltiliyor. Kanıt temiz bir kat sayısı vermiyorsa hesap **yapılmaz** —
yanlış birimle üretilen tonaj, hesap yapmamaktan çok daha zararlıdır.

Testler: `backend/tests/test_rebar_plan.py` (16 test; sayılar elle sağlanabilir seçildi).

## Kanıt sıralaması: çelişkide hangi sayının esas alınacağı (`services.storey_heights`)

Bir çelişki iki sayının birlikte duramayacağını söyler; hangisinin yanlış olduğunu söylemez — **girdilerinin
kanıt gücü farklı olmadıkça**. Kanıt sırası:

| | örnek | güç |
|---|---|---|
| Çizimden doğrudan okunan | donatı tablosu, kesit etiketi, kolon çokgeni, kot yazısı | en güçlü |
| Çizimden türetilen | kot farkından kat yüksekliği | güçlü |
| Kullanıcının paftaya girdiği | o paftanın yüksekliği | açık karar, korunur |
| Projeye girilen tek değer / form varsayılanı | H = 3,0 m | en zayıf |

**Uygulanan kural:** projeye girilen tek bir H, çizimden okunan kotlar kat kat değişiyorsa (yayılım > 0,30 m)
uygulanmaz — çünkü tek bir sayı değişken katlı bir binanın hiçbir katında doğru olamaz. Her pafta kendi
kotundan hesaplanır. Bu bir tahmin değil, zayıf kanıtın yerine güçlü kanıtın konmasıdır.

Sınırlar, kullanıcının kararını korumak için:

- **Paftaya elle girilen yükseklik her zaman kazanır** — kullanıcının pafta bazındaki kararına dokunulmaz.
- **Kotlar sabitse proje H'si korunur.** Düzeltme yalnız gerçek çelişki varken devreye girer; "H 2,80 ama
  kotlar 3,00 diyor" durumunda karar kullanıcınındır, fark bildirilir ve tek tıkla düzeltme sunulur.
- **Girilen değer silinmez**, yalnız uygulanmaz; ne yapıldığı ve H uygulansaydı miktarın ne olacağı yazılır
  (`storey_height_auto_applied`, inceleme notu).

### A4-A5'te etkisi

H = 3,0 m girili, çizimdeki kotlar 2,50 / 3,95 / 2,70 / 5,00 m. Düzeltme öncesi ve sonrası:

| | önce (H = 3,0 uygulanıyordu) | sonra (kotlar esas) | bağımsız doğrulanmış |
|---|---:|---:|---:|
| Beton | 14.542 m³ | **14.900,2** | 14.900 |
| Kalıp | 43.045 m² | **44.541,4** | 44.541 |
| Demir | 2.160,3 t | **2.163,1** | 2.163,1 |
| Kolon donatı oranı | 462 kg/m³ ✗ | **370 kg/m³ ✓** | ölçülen 374 |
| Kendini kontrol | 15 destekliyor · **1 çelişiyor** | **16 destekliyor · 0 çelişiyor** | |

Yani fizikten gelen çelişki (`selfcheck`), kotlardan gelen kanıtla (`storey_heights`) kapandı ve sonuç
bağımsız olarak doğrulanmış değerlere birebir oturdu.

Testler: `backend/tests/test_levels.py` — değişken katta H uygulanmaz, sabit katta kullanıcının değeri
korunur, paftaya elle girilen her zaman kazanır, düzeltme sessiz yapılmaz.

## Kapsam sahipliği: bir kez okunan miktar ikinci paftadan tekrar okunmaz (`quantity/scope.py`)

Bir kalem birden çok paftada çizilidir. Zayıf akım paftasının altlığında kablo tavası, kuvvet planının
altlığında mimari duvar, mimari kat planının altlığında kolonlar vardır. İkisini de saymak miktarı ikiye
katlar; ikinci paftayı toptan atmak ise o paftadaki **gerçek eklemeyi** (yalnız zayıf akımda çizilen ek tava
kolu) kaybettirir. İkisi de metrajı bozar, ikincisi sessizce bozar.

**Kural: aynı nesne bir kez sayılır, ayrı nesne her zaman sayılır.** Aynılığın kanıtı konumdur — kırpılan
paftalar dünya koordinatını koruduğu için aynı blokta, aynı katta, aynı yere düşen aynı tipteki eleman aynı
elemandır (`same_object`: tip + alt tip + merkez mesafesi + büyüklük oranı). Eşleştirme uyan ilk nesneyi
değil **en yakınını** alır (eşitlikte miktarı en yakın olanı).

### Katın kimliği de çizimden okunur (`services._floor_identity`)

Kural "aynı kat" tanımına dayanır, o yüzden kat kimliği kullanıcıdan istenmez — iki bağımsız kanıt vardır ve
her biri tek başına yeterlidir:

- **Kot**: başlıktan (`+7.95 KOTU KALIP PLANI`) ya da çizimin içinden okunan kot (`parser/levels.py`).
- **Plan adındaki kat sırası** (`levels.floor_rank`): `BODRUM`, `ZEMİN KAT`, `2. KAT`, `ÇATI`, `STA-03`.
  Elektrik ve mekanik paftalarında kot çoğu zaman yazmaz, **kat adı yazar** — kural orada da çalışır.

İkisini birden taşıyan tek bir pafta (`2. KAT (+7.95) KALIP PLANI`) iki kimliği birbirine bağlar: kotla
adlandırılmış statik pafta ile kat adıyla adlandırılmış elektrik paftası aynı kata düşer. Hiçbir kanıt yoksa
kat bilinmiyordur ve o paftada **hiçbir miktar düşürülmez**.

### Sahip kim: kalemi ölçmek için çizilen pafta

Her plan tipi, yetkili olduğu eleman tiplerini bildirir (`planset.PlanType.owns`):

| Kalem | Sahibi | Altlıkta çizilse de saymayan |
|---|---|---|
| Kablo tavası | Elektrik kablo tava planı | zayıf akım, aydınlatma, kuvvet |
| Armatür / priz / kablo / boru | Aydınlatma · kuvvet · zayıf akım (üçü eşit yetkili) | mimari, statik |
| Duvar / kapı / pencere | Mimari kat planı | tavan, kaplama, elektrik altlığı |
| Kolon / perde / kiriş / döşeme | Kat kalıp planı | mimari kat planı, donatı altlığı |
| Temel | Temel kalıp planı | |
| Boru / cihaz · kanal | Isıtma · sıhhi · yangın (eşit) · havalandırma | |

Yetki sırası: **0** kalemin sahibi, **1** kalemin disiplinini taşıyan pafta, **2** disiplini tutan çizim,
**3** ilgisiz pafta. Yalnız daha düşük yetkili pafta eler; **eşit yetkili iki pafta birbirini asla elemez**
(bir katın iki yarıya kırpılmış paftası, iki ayrı kat, iki blok — hepsi gerçek ölçümdür).

Metraja girmeyen pafta sahiplik de kuramaz: donatı paftası ve kesit / detay paftaları kapsam dışıdır, yoksa
donatı paftasının altlığındaki kalıp planı, kalıp planının kendisini düşürürdü.

### Karar sırası

1. **Nesneler üst üste düşüyor** → eşleşen kopya sayılmaz, eşleşmeyen **ek olarak sayılır**. Bir nesne yalnız
   bir kopyayı karşılar: sahipte bir tava varken ikinci paftada iki tane varsa, ikincisi kopya değil ektir.
2. **Düşmüyor ama kat biliniyor** → aynı katın ayrı orijinde çizilmiş ikinci paftası olabilir: ötelemeler
   denenir (`_align`) ve **doğrulanır** — en az 3 nesne ve nesnelerin %70'i tutmalı. Öteleme bir çıkarımdır,
   konum kanıtı kadar güçlü değildir: zayıf bir hizalama ayrı bir yapı bloğunun gerçek ölçümünü sildirebilir.
   Bu yolla düşen miktar her zaman "kontrol edilmeli" işaretlenir. Eşit yetkili paftalar hiç hizalanmaz.
3. **Düşmüyor ve kat bilinmiyor** → *hiçbir şey düşürülmez.* Örtüşmeyen iki pafta aynı dosyada yan yana duran
   ayrı bölgeler de olabilir (bir DXF'te temel ve zemin paftası). **Sessizce kaybolan miktar, çift sayımdan
   zararlıdır**: ikisi de sayılır, kullanıcıya iki miktar ve ne yapacağı yazılır.
4. **Sahibi hiç yüklenmemişse** kalem sayılır ama "yetkili paftası yüklenmedi, sayı altlıktan geliyor, düşük
   güven" notu düşer — tava planı yokken zayıf akımdaki tava kaybolmaz.

Elle eklenen / düzeltilen eleman (`manual`) hiçbir zaman elenmez; hiçbir şey veritabanından silinmez,
sahiplik her hesapta yeniden kurulur ve düşen her miktar **Kapsam** panelinde nesne sayısı ve miktarıyla
görünür. Proje parametresi `scope_off=1` kuralı tümden kapatır.

### Gerçek paftada ölçüldü (21 Eyl 2026)

**Altlık senaryosu** — B Blok zemin kalıp planı (830 eleman) aynı projeye iki kez yüklendi: biri kat kalıp
planı (sahibi), öbürü mimari kat planı (altlık).

| | beton m³ | kalıp m² | demir kg |
|---|---:|---:|---:|
| Tek pafta (doğru cevap) | 2.170,9 | 9.457,6 | 302.984 |
| İki pafta, kapsam **kapalı** | 4.341,7 | 18.915,3 | 605.969 |
| İki pafta, kapsam **açık** | **2.170,9** | **9.457,6** | **302.984** |

830 nesnenin 830'u eşleşti, sahte ek üretilmedi: fark **0,00**.

**Yanlış alarm kontrolü** — A4-A5 mimari seti (2 DXF, 16 pafta, 115 keşif kalemi) kapsam açık ve kapalı
birebir aynı sonucu verdi, tek bir kapsam notu çıkmadı. Paftalar farklı görünüşler olduğu için elenecek
nesne yok; kural sessizce hiçbir şeyi düşürmedi.

**Eşleştirme en yakını alır, uyan ilkini değil.** İlk ölçümde 830 nesnenin 10'u "ek" sayılıp metrajı %1,2
şişirdi: birebir ikizi olan eleman, ikizini toleransa giren komşusuna kaptırıyor, ikiz sonra boşta kalıp ek
sanılıyordu. Eşleşme artık merkez mesafesine (eşitlikte miktar farkına) göre en yakın nesneyi seçer.
Senaryodaki iki paftanın katı, adlarındaki "Zemin"den tanındı; kullanıcı hiçbir şey girmedi.

Kapsam kuralını ölçmek için kapatmak: proje parametresi `scope_off = 1` (her pafta kendi ölçtüğünü yazar).

Bu senaryo repoda bir **gerileme kapısıdır**: `cd backend && python calib/senaryo_altlik.py` (çıkış kodu 1 =
kaldı). `python -m app.calib` doğruluk kapısıdır, bu ise çift sayım kapısı; kapsam kuralına dokunan her
değişiklikten sonra ikisi de koşturulur.

Testler: `backend/tests/test_scope.py` — zayıf akım tavayı ikinci kez saymaz, ek kol eklenir, bir katın iki
yarısı toplanır, ayrı kot / ayrı blok / farklı kesit elenmez, kot yoksa hiçbir şey düşmez, aynı DXF'te yan
yana duran paftalar birbirini elemez, ikiz komşuya kaptırılmaz, zayıf hizalama kabul edilmez,
kat kimliği kot ve plan adından okunur, uçtan uca API akışı.

## Kendini yanlışlayan kontroller (`app/selfcheck.py`)

Kontrol listesi (`quality.py`) "ne eksik" diye sorar: pafta okundu mu, katman eşleşti mi. Bu modül başka bir
şey sorar: **ürettiğimiz sayı kendi içinde tutarlı mı?** Aynı büyüklüğe iki bağımsız yoldan bakar ve ikisini
çarpıştırır. Amaç sonucu savunmak değil, **çürütmeye çalışmak**.

### Tek kural: dairesel kontrol hiçbir şey kanıtlamaz

Demiri `beton × 140` ile bulup sonra "demir/beton 140 çıktı, demek doğru" demek bir doğrulama değil, aynı
sayıyı iki kez yazmaktır. Böyle bir kontrol asla `destekliyor` demez — `kararsiz` der ve sebebini yazar
(`bagimsizlik: "YOK — demir zaten beton × oran ile bulundu"`). Bir kontrolün değeri girdilerinin
bağımsızlığından gelir:

    demir  ←  donatı tablosu / poz yazısı    (çizimdeki yazılar)
    beton  ←  eleman geometrisi × yükseklik   (çizimdeki çizgiler)

İkisi birbirini hiç görmez. Oranları ise fizikle ve yönetmelikle sınırlıdır — bu yüzden bant dışına çıkmak
**gerçek bir çelişkidir**. Sonuç üç değerlidir, "doğru" yoktur: `destekliyor` / `celisiyor` / `kararsiz`.

### Kontroller

| Kod | Ne çarpıştırır | Bant nereden |
|---|---|---|
| `demir_orani` | demir (yazılardan) ÷ beton (geometriden) | TS500 / TBDY donatı oranı: kolonda ρ ≤ %4 → 314 kg/m³ + etriye ≈ **400 tavan** |
| `doseme_kalinlik` | beton ÷ kalıp = kalınlık | fiziksel döşeme kalınlığı 7–45 cm |
| `kalip_beton` | yüzey ÷ hacim | elemanın kendi geometrisi (döşemede tam olarak 1/t) |
| `cap_tutarliligi` | keşifteki çaplar ↔ planda yazan çaplar | çizimde hiç yazmayan çap sipariş edilemez |
| `kat_tutarliligi` | her katın betonu ↔ katların medyanı | her kat ayrı paftadan, ayrı geometriden |
| `toplam_saglama` | grup toplamı ↔ proje toplamı | aritmetik; tutmazsa hata **bizdedir** |

### Gerçek projede ne buldu

A4-A5'te 18 kontrol çalıştı: **15 destekliyor, 1 çelişiyor, 2 kararsız**. Çelişen:

> **Donatı oranı — Kolon:** 462 kg/m³ bandın üstünde (100–400). İki sayıdan biri yanlış: ya kolon betonu az
> ölçüldü (kat yüksekliği / eleman sayısı), ya da demir fazla toplandı (çift sayım / eksik kat).
> *Bağımsızlık: demir tablo kaynağından (çizim yazıları), beton eleman geometrisinden — birbirini görmüyor.*

Bu, `storey_height_override` uyarısının bulduğu H = 3,0 m sorununun **tamamen farklı bir yoldan** bulunmuş
hâlidir: biri kotları karşılaştırarak, diğeri fizikle. Doğru kat yükseklikleriyle (H = 0) kolon betonu
1.370 → 1.708 m³ olur, oran **370 kg/m³**'e iner ve çelişki kapanır — 370, bu projede bağımsız olarak ölçülen
374 kg/m³ ile uyuşuyor.

Kararsız kalan ikisi perde ve parapet: demirleri oranla bulunduğu için kontrol dairesel olurdu. Sistem bunu
"eşleşti" diye raporlamak yerine açıkça "bu kontrol bir şey kanıtlamaz" diyor.

Çelişen bir kontrol keşifte **engelleyici** (`selfcheck_conflict`) olarak görünür ve durum `incomplete` olur.
Hepsinin desteklemesi ise doğruluk kanıtı değildir; raporun kendi cümlesi: *"yalnız bilinen çelişkilerin
bulunmadığını gösterir."*

Testler: `backend/tests/test_selfcheck.py` (15 test). En önemlisi `test_dairesel_kontrol_asla_desteklemez` —
sistemin kendini kandırmadığının testi.

## Poz bedeliyle fiyatlandırma: birim fiyat listesini bir kez yapıştır (`cost/pozbook.py`)

Canlı kullanımda asıl tıkanma metraj değil **fiyat girişidir**: keşifte 100+ kalem çıkar, hepsine elle fiyat
girmek kimsenin yapmayacağı bir iştir; program 0 ₺ gösterir. Ama kalemlerin çoğunda **ÇŞB poz numarası**
zaten var (A4-A5'te 78 kalemin 47'si) ve her müteahhitte o yılın birim fiyat listesi bulunur.

`POST /api/pricebook/poz-import` bir metin alır, poz numarasına göre fiyat bankasına yazar; yeni projeler de
bu bankadan dolar. Gerçek listeler tek biçimde olmadığı için ayraca güvenilmez — satırdaki **poz numarası ve
son sayı** aranır, aradaki metin addır. Dört ayraç da çalışır (sekme, `;`, `|`, hizalama boşluğu), sayı
Türkçedir (binlik nokta, ondalık virgül), birim normalleştirilir (`m2` → `m²`, `TON` → `ton`).

### Poz bedeli her şey dahildir

ÇŞB birim fiyatı malzeme + işçilik + makine + yüklenici kârını kapsar. Bu yüzden `PriceItem.poz_price`
doluysa malzeme ve işçiliğin **yerine geçer**, üstüne eklenmez — toplanırsa bedel iki kez sayılır.

### Birim uyumu: sessiz geçilemeyecek tek şey

Demir keşifte **kg**, ÇŞB pozunda **ton**'dur. Çevrilmezse tutar **1000 kat** çıkar; gerçek projede ölçüldü:

```
çevirmeden:  Demir Ø20  595.492,7 kg × 27.400 ₺  =  16.316.499.980 ₺     (16 milyar)
çevirerek:   Demir Ø20  595.492,7 kg × 27,400 ₺  =      16.316.500 ₺     (16 milyon)
```

`unit_factor` bilinen dönüşümleri uygular (kg↔ton, m↔km, L↔m³); **çeviremediğinde fiyatı hiç uygulamaz** ve
sebebini bildirir. m² fiyatını m³ kalemine tahminle uydurmaktansa o kalemi fiyatsız bırakmak doğrudur.

### A4-A5'te uçtan uca

Örnek bir liste (beton 3.250 ₺/m³, kalıp 485,50 ₺/m², demir 27.400–27.850 ₺/ton) yapıştırıldığında:

| kalem | miktar | birim fiyat | tutar |
|---|---:|---:|---:|
| Beton — Radye | 6.185,7 m³ | 3.250,00 | 20.103.671 ₺ |
| Demir Ø20 | 595.492,7 kg | 27,400 | 16.316.500 ₺ |
| Demir Ø26 | 478.886,9 kg | 27,400 | 13.121.501 ₺ |
| Kalıp — Döşeme | 21.106,1 m² | 485,50 | 10.246.995 ₺ |
| **Genel toplam (KDV hariç)** | | | **132.889.198 ₺** |

43 kalem poz bedeliyle fiyatlandı; kalan 35 işçilik ve 30 malzeme satırı hâlâ kullanıcıdan bekleniyor
(reçete alt işleri ve pozu olmayan kalemler). Program artık 0 ₺ değil, eksiği sayılabilir bir tutar veriyor.

Testler: `backend/tests/test_pozbook.py` (27 test; sayı biçimi, dört ayraç, birim normalleştirme, birim
dönüşümü, uçtan uca liste → banka → keşif).

## Süre: ekip normu ayrı, ekip sayısı kullanıcının kararı (`standard/rules.py: CREW_SIZE`)

Süre "169.173 adam-saat → 21.146 adam-gün" diye çıkıyordu; bu kullanıcıya hiçbir şey söylemez. Sebep ekip
sayısının 1 varsayılmasıydı. Ayrım şudur:

- **Bir ekipteki kişi sayısı bir normdur** — kalıpta 2 marangoz + 1 amele, sıvada usta + yardımcı, beton
  dökümünde pompa başında kalabalık ekip. `CREW_SIZE` bunu verir (tanınmayan işte usta + yardımcı = 2).
- **Kaç ekibin aynı anda çalışacağı saha kararıdır** — proje parametresi `crew_count` (varsayılan 1).

Ekip = kişi/ekip × eşzamanlı ekip sayısı. A4-A5'te (169.173 saat):

| eşzamanlı ekip | takvim (paralel) | gereken ortalama kişi |
|---:|---:|---:|
| 1 | 5.107 gün | 4 |
| 5 | 1.022 gün | 21 |
| 10 | **511 gün** | **42** |

Süreyle birlikte **`implied_headcount`** yazılır: *bu takvim süresi için sahada ortalama kaç kişi gerekir.*
14.900 m³ betonluk bir AVM'yi 17 ayda bitirmek için 42 kişi — kullanıcı gerçekçiliği bu sayıdan görür ve
ekip sayısını ona göre değiştirir. Norm bir program varsayılanıdır, kullanıcı girişi değildir: normdan gelen
kalemler `norm_crew` ile ayrıca listelenir.

## Eksik fiyatlar etki sırasına göre (`cost/pricing.py: _missing_ranked`)

"Fiyatı girilmemiş 65 kalem var" cümlesi kullanılabilir değildir. Sıralama uydurma fiyata dayanmaz, bildiğimiz
büyüklükleri kullanır: işçilik satırında miktarın kendisi adam-saattir, diğerlerinde hesaplanan adam-saat,
o da yoksa kendi türü içinde miktar. Ürünler ürün bazında toplanır (aynı demir birçok kalemde geçer).

A4-A5'te ilk 8 işçilik satırı toplam saatin **%90'ını** tutuyor:

```
Demir yerleştirme - bağlama        35.986 saat
Kalıp kurma                        30.349 saat
Demir kesme - bükme                18.781 saat
Sıva işçiliği                      17.809 saat
…
```

Maliyet ekranında "Önce hangilerini doldurmalı?" başlığı altında görünür; kullanıcı 65 satır yerine üstteki
birkaçını doldurup tutarın çoğunu çıkarır.

## Kalibrasyon döngüsü: ölç → doğru metrajla karşılaştır → farkı sebebe bağla (`app/calib`)

Metrajın doğruluğu tek dosyada denenerek artmaz: bir kuralı bir çizimde düzeltmek başka çizimde bozabilir
(bkz. pafta bölme, 10 Eyl). Bu yüzden düzeltme değil **ölçüm** kalıcıdır. `app/calib` bir korpusu (paftalar +
bilinen doğru metraj) çalıştırır, farkı kalem kalem çıkarır, **farkı sebebe bağlar** ve önceki tabanla kıyaslar.

```
python -m app.calib               bütün korpusu ölç, farkı ve teşhisi yaz, tabanla kıyasla (gerileme varsa çıkış 1)
python -m app.calib --kaydet      bu koşuyu taban yap
python -m app.calib --korpus X    yalnız bir proje
```

### Doğru metraj nereden geliyor

Web'de (çizim + doğrulanmış metraj) eşleşmiş açık veri seti yok. Ama **gerek de yok**: Türk statik ofisleri
kendi icmallerini paftaya çiziyor. B Blok'ta `TABLE4` katmanı müellifin kat bazında KALIP (m²) / BETON (m³)
tablosu; A4-A5'te `VM-METRAJ` katmanı donatı metraj tablosu (zaten okuyoruz — demirin %99,3'ü buradan geliyor).
Yani **her proje dosyası kendi cevap anahtarını taşıyor**. Referansın güveni her zaman kayıtlı (`guven`):

| | anlamı |
|---|---|
| `cizimden` | çizimin kendi metraj tablosundan okundu |
| `aktarim` | tablodan elle aktarıldı, bağımsız ölçülmedi |
| `bagimsiz` | bağımsız ölçüm / hakediş icmali |

**"Eşleşti" ≠ "doğru".** Müellifin tablosuyla aynı sonucu vermek, ikimizin de aynı kabulü kullandığını gösterir.

### Teşhis: hangi değişken suçlu

Fark yüzdesi tek başına işe yaramaz; `diagnose.py` farkı formülün kendisinden geri hesaplar. Kolon/perde betonu
ve kalıbı **farklı** yükseklik kullandığı için hangisinin saptığı doğrudan suçluyu gösterir:

    beton = alan × Hk        Hk = H (net döşeme) ya da H − d
    kalıp = çevre × Hf       Hf = H − kattaki baskın kiriş yüksekliği

Geometri doğruysa oran doğrudan yüksekliğe düşer: `h_doğru = h_kullanılan × referans / bizim`. Geri hesaplanan
yükseklik formüldeki adaylardan (H, H − d, H − kiriş) birine denk düşüyorsa suçlu bir **kabuldür**; hiçbirine
denk düşmüyorsa suçlu yükseklik değil **eleman tespitidir**.

### İlk koşu (B Blok, TABLE4 referansı)

| Kat | Beton m³ (bizim / ref) | % | Kalıp m² (bizim / ref) | % |
|---|---|---:|---|---:|
| Bodrum | 1.500,0 / 1.443,7 | +3,90 | 6.380,7 / 6.367,8 | +0,20 |
| Zemin | 728,4 / 731,3 | −0,40 | 2.932,6 / 2.996,3 | −2,13 |
| Birinci kat | 709,2 / 677,3 | +4,71 | 2.843,7 / 2.802,0 | +1,49 |

Genel ortalama mutlak sapma **%2,14**, en kötü %4,71. (Kalıp eskiden %15–25 fazlaydı; kiriş altı düzeltmesinin
işe yaradığını bu koşu bağımsız olarak doğruluyor.)

Teşhisin bulduğu: bodrum ve birinci katta kalıp eşleşirken beton sapıyor, ve geri hesaplanan beton yüksekliği
**tam olarak H − d**'ye denk düşüyor (3,21 ≈ 3,18 ve 3,53 ≈ 3,55) — yani müellif kolon betonunu brüt döşeme
kabulüyle hesaplamış, biz net kabulüyle. **Ama zemin katı bu hipotezi yalanlıyor** (H ile eşleşiyor) ve A4-A5
net kabulüyle %0,7'de tutuyor. Tek dosyaya bakıp kural değiştirmenin tuzağı tam burada: hipotez birden çok
katta ve projede tekrarlanmadan kural değişmez. Korpus büyüdükçe bu soru kendiliğinden cevaplanacak.

### Gerileme kapısı

Taban kaydedildikten sonra her koşu kıyaslanır. Kasten sokulan bir hata (kolon kalıbı `Hf` yerine `H`) ile
denendi:

```
b_blok: %2.14 → %7.46  ↑ GERİLEME
    bodrum/kolon_perde_kalip_m2: %+0.20 → %+11.46
    zemin/kolon_perde_kalip_m2:  %-2.13 → %+9.93
    birinci kat/kolon_perde_kalip_m2: %+1.49 → %+14.38
```

Çıkış kodu 1 döner; CI'da doğrudan kullanılabilir. Testler: `backend/tests/test_calib.py` (13 test — korpus
okuma, fark hesabı, altı teşhis dalı, bozuk / boş pafta, tanınmayan ölçü).

### Korpusa proje eklemek

`backend/calib/corpus/<ad>.json` — bir dosya, bir proje; katlara bölünür çünkü referans metraj hemen her zaman
kat bazındadır. Kat yüksekliği korpusta **açıkça** yazılır (tahmin edilmez): kalibrasyonun en sık yanıltıcı
değişkeni budur.

```json
{ "proje": "…", "kaynak": "TABLE4", "guven": "aktarim",
  "katlar": [{ "ad": "zemin", "kat_yuksekligi": 3.80,
               "paftalar": ["samples/b_blok/crop_zemin.dxf"],
               "referans": {"kolon_perde_beton_m3": 731.31, "kolon_perde_kalip_m2": 2996.27} }] }
```

Karşılaştırılabilen ölçüler `calib/corpus.py: MEASURES`; tanınmayan bir anahtar sessizce 0 sayılmaz, hata verir.

## Yol haritası

- Detay paftalarından gerçek demir metrajı (`8Φ16`, `Φ8/15` + boy)
- Mimari: döşeme kaplaması / tavan (oda çokgenlerinden m²), süpürgelik, kapı-pencere doğrama m²
- Elektrik: aydınlatma planı ile kuvvet planını birleştirip devre bazlı kablo boyu (armatür → pano yolu), kanal / spiral boru
- Mekanik: boru çapı bazında hat uzunlukları, kanal m²
- İş programı: kalem bağımlılıkları ile Gantt (şu an disiplin bazlı paralel / ardışık iki uç değer)
- DWG doğrudan yükleme (ODA File Converter)
