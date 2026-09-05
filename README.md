# Keşif — DXF Planından Metraj, Keşif, Maliyet ve Süre

AutoCAD planlarını (DXF) okuyup üç disiplinde keşif çıkarır:

| Disiplin | Çizim | Tespit edilen | Keşif kalemleri |
|---|---|---|---|
| **Statik** | kalıp planı | kolon, perde, kiriş, döşeme, temel | beton m³, kalıp m², demir kg |
| **Mimari** | kat planı | duvar (malzeme + kalınlık), kapı, pencere | duvar m² (Ytong / tuğla / bims / alçıpan…), sıva m², boya m², kapı adet, pencere adet, cam m² |
| **Elektrik** | tava / aydınlatma / kuvvet planı | kablo tavası, kablo, boru, armatür / priz / anahtar | tava m (boyut bazında), kablo m (kesit bazında), boru m, armatür adet (kategori) |

Girdiğiniz **malzeme** ve **işçilik** birim fiyatları, tercih ettiğiniz **marka** ve **adam-saat / birim** değerleriyle
maliyet tablosu (malzeme + işçilik, KDV) ve **süre tahmini** (gün) üretir; Excel raporu indirir.

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

1. **Proje oluştur**: kat yüksekliği (H) ve varsayılan döşeme kalınlığı (d) gir. Proje sayfasında mimari / elektrik / süre
   parametreleri: duvar yüksekliği (boşsa H − d), sıva ve boya yüzü sayısı, kablo iniş payı (m/hat), kablo ve tava fire %, günlük çalışma saati.
2. **DXF yükle**: AutoCAD'de DWG'yi *Farklı Kaydet → AutoCAD DXF* ile dönüştür. Yüklerken **disiplin** seç (statik / mimari / elektrik);
   çizim o disiplinin dedektörleriyle analiz edilir. Disiplin sonradan çizim listesinden değiştirilebilir (yeniden analiz edilir).
   - Her plan ayrı dosya olabilir, ya da **bütün paftaların yan yana durduğu tek ruhsat projesi dosyası** yüklenir:
     paftalar otomatik bulunur (çerçeve dikdörtgenleri; yoksa nesne kümeleri), listeden **kalıp planları** seçilir,
     her pafta ayrı plan olarak kırpılıp analiz edilir. 40 MB üstü dosyalar hiç bir zaman bütün olarak açılmaz.
   - "Kaç kat temsil ediyor" alanı tip kat çarpanıdır; temel elemanları hiçbir zaman çarpılmaz.
   - Her planın kendi **kat yüksekliği** girilebilir (boşsa projenin H değeri).
3. **Elemanlar** sayfası: plan önizlemede tespit edilen elemanlar renkli görünür.
   - **Katman eşleme**: hangi katmanın kolon / duvar / tava / … çizdiğini seç; yalnızca çizimin disiplinine ait tipler seçilebilir.
     Eşlenmemiş katmanlar metraja girmez.
   - Tabloda b/h/kalınlık/uzunluk/adet ve alt tip (duvar malzemesi, kablo kesiti, tava boyutu, armatür kategorisi) düzenlenebilir,
     eleman silinebilir, parser'ın kaçırdığı eleman elle eklenebilir.
4. **Metraj**: disiplin bazlı **keşif listesi** (kalem, birim, miktar) + statik grup özeti ve eleman bazlı liste.
5. **Birim Fiyatlar**: her kalem için marka, malzeme ₺/birim, işçilik ₺/birim, adam-saat/birim, ekip. Türün "genel" satırı
   özel değer girilmeyen kalemlere uygulanır.
6. **Maliyet**: malzeme + işçilik kalem tablosu, disiplin bazlı toplamlar, KDV, **süre** (disiplinler paralel / işler ardışık), Excel indir.

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
  içindeki en büyük "… PLANI / KESİTİ / DETAYI" yazısıdır. Seçilen paftalar tek geçişte küçük DXF'lere kırpılır
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
- Temel paftasındaki kolon/perde izleri metraj dışı (doğru); "Parapet (20/82)" etiketleri ve `VM Parapet Tarama` henüz sayılmıyor.
- +15.65 çatı paftasında 66 döşeme etiketi kiriş ağı olmayan bölgede: bu döşemeler bulunamıyor (elle eklenmeli).

Demir: 11 donatı paftasının metraj tabloları (temel X/Y/ilave, döşeme alt/üst × 4 kot) birebir okundu (907,9 t); kolon paftalarının
tabloları blok içindeydi (5 tablo, 633 t); kiriş detaylarında tablo yok, 7.987 adetli poz yazısından 607 t hesaplandı. Yalnız perde
(7 t) oranla kaldı. Gerçek oranlar bu projede: radye 97, kolon **374**, kiriş 178, döşeme 82 kg/m³ — kolon için varsayılan 130 çok düşüktü.

| Grup | Adet | Beton m³ | Kalıp m² | Demir t | Demir kaynağı |
|---|---|---|---|---|---|
| Radye (RD1 7.166 m² × 0,70 + RD2 3.368 m² × 0,40) | 8 | 6.572 | 945 | 635,5 | tablo |
| Kolon | 457 | 1.693 | 5.963 | 633,0 | tablo (blok içi) |
| Perde | 23 | 74 | 433 | 7,4 | oran |
| Kiriş | 1.746 | 3.405 | 16.797 | 607,5 | poz yazıları |
| Döşeme | 1.254 | 3.319 | 22.225 | 272,3 | tablo |
| **Toplam** | | **15.064** | **46.363** | **2.156** | |

Çap bazında: Ø8 154 t, Ø10 200 t, Ø12 367 t, Ø14 268 t, Ø16 82 t, Ø20 596 t, Ø26 481 t.

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

## Yol haritası

- Detay paftalarından gerçek demir metrajı (`8Φ16`, `Φ8/15` + boy)
- Mimari: döşeme kaplaması / tavan (oda çokgenlerinden m²), süpürgelik, kapı-pencere doğrama m²
- Elektrik: aydınlatma planı ile kuvvet planını birleştirip devre bazlı kablo boyu (armatür → pano yolu), kanal / spiral boru
- Mekanik: boru çapı bazında hat uzunlukları, kanal m²
- İş programı: kalem bağımlılıkları ile Gantt (şu an disiplin bazlı paralel / ardışık iki uç değer)
- DWG doğrudan yükleme (ODA File Converter)
