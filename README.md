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
Kalıp 800 m²          → kalıp iskelesi 800 × H m³ (ÇŞB 15.185.1006)     Beton → pompaj m³
Cephe (mantolama / kompozit / giydirme / taş / boya) → iş iskelesi m² (+ taşıyıcı profil, ankraj, vinç)
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

## Yol haritası

- Detay paftalarından gerçek demir metrajı (`8Φ16`, `Φ8/15` + boy)
- Mimari: döşeme kaplaması / tavan (oda çokgenlerinden m²), süpürgelik, kapı-pencere doğrama m²
- Elektrik: aydınlatma planı ile kuvvet planını birleştirip devre bazlı kablo boyu (armatür → pano yolu), kanal / spiral boru
- Mekanik: boru çapı bazında hat uzunlukları, kanal m²
- İş programı: kalem bağımlılıkları ile Gantt (şu an disiplin bazlı paralel / ardışık iki uç değer)
- DWG doğrudan yükleme (ODA File Converter)
