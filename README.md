# Keşif — DXF Planından Metraj ve Maliyet

AutoCAD statik kalıp planlarını (DXF) okuyup kolon / perde / kiriş / döşeme / temel elemanlarını tespit eder,
beton (m³), kalıp (m²) ve demir (kg) metrajını çıkarır, girdiğiniz birim fiyatlarla maliyet tablosu ve Excel raporu üretir.

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

## Çalıştırma (geliştirme)

İki ayrı terminalde, ya da tek komutla `.\start.ps1`:

```powershell
cd backend;  .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
cd frontend; npm run dev
```

Tarayıcı: http://127.0.0.1:5173  (API dokümantasyonu: http://127.0.0.1:8000/docs)

Üretim: `cd frontend; npm run build` sonrası backend `frontend/dist` klasörünü kendisi servis eder (http://127.0.0.1:8000).

## Kullanım akışı

1. **Proje oluştur**: kat yüksekliği (H) ve varsayılan döşeme kalınlığı (d) gir.
2. **DXF yükle**: AutoCAD'de DWG'yi *Farklı Kaydet → AutoCAD DXF* ile dönüştür.
   - Her plan ayrı dosya olabilir, ya da **bütün paftaların yan yana durduğu tek ruhsat projesi dosyası** yüklenir:
     paftalar otomatik bulunur (çerçeve dikdörtgenleri; yoksa nesne kümeleri), listeden **kalıp planları** seçilir,
     her pafta ayrı plan olarak kırpılıp analiz edilir. 40 MB üstü dosyalar hiç bir zaman bütün olarak açılmaz.
   - "Kaç kat temsil ediyor" alanı tip kat çarpanıdır; temel elemanları hiçbir zaman çarpılmaz.
   - Her planın kendi **kat yüksekliği** girilebilir (boşsa projenin H değeri).
3. **Elemanlar** sayfası: plan önizlemede tespit edilen elemanlar renkli görünür.
   - **Katman eşleme**: hangi katmanın kolon/kiriş/… çizdiğini seç; eşlenmemiş katmanlar metraja girmez.
   - Tabloda b/h/kalınlık/uzunluk/adet düzenlenebilir, eleman silinebilir, parser'ın kaçırdığı eleman elle eklenebilir.
4. **Metraj**: grup özeti ve eleman bazlı liste.
5. **Birim Fiyatlar**: beton ₺/m³, kalıp ₺/m², demir ₺/kg (genel + gruba özel).
6. **Maliyet**: kalem tablosu, KDV, Excel indir.

`samples/` klasöründe sentetik örnek çizimler var (`ornek_kat_plani.dxf`, `ornek_temel_plani.dxf`).

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

## Metraj formülleri

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

## Gerçek çizimlerle kalibrasyon

Firmanın çizimleri geldiğinde:
1. Çizimi yükle, **Katman eşleme** panelinde katmanları ata.
2. Yakalanmayan eleman tipleri için `layer_profile.py` içindeki `DEFAULT_PROFILE`'a firma standardı regex'lerini ekle.
3. Farklı etiket formatları için `text_parser.py` regex'lerini genişlet; `tests/test_text_parser.py`'ye örnek ekle.
4. Kiriş çizim tekniği (çift çizgi / polyline / blok) farklıysa `detectors/beams.py` heuristiklerini ayarla.

## Yol haritası

- Detay paftalarından gerçek demir metrajı (`8Φ16`, `Φ8/15` + boy)
- Mimari: duvar uzunluğu × kat yüksekliği − kapı/pencere → duvar / sıva / boya m²
- Elektrik / mekanik: katman bazlı hat uzunlukları → kablo / boru m
- DWG doğrudan yükleme (ODA File Converter)
