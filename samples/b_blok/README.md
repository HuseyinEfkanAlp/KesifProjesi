# B Blok ruhsat projesi (REV01) — inceleme notu (4 Eyl 2026)

Kaynak: `B BLOK RUHSAT PROJESI-REV01.dxf` (494 MB, AutoCAD 2018 / UTF-8, 1.009.057 nesne, 155 katman, 67 pafta).
Buradaki `crop_*.dxf` dosyaları o çizimden kırpılmış tek paftalardır (sadece çizgi/polyline/yazı); parser
kalibrasyonu ve test için kullanılır. Kırpma bölgeleri (çizim birimi, x aralığı; y −76000..−66000):

| Dosya | Pafta | x aralığı |
|---|---|---|
| crop_temel02.dxf | TEMEL KALIP PLANI - 02 | −829000 .. −810000 |
| crop_bodrum01a.dxf | BODRUM KAT KALIP PLANI (1. yarı) | −648000 .. −630000 |
| crop_bodrum01b.dxf | BODRUM KAT KALIP PLANI (2. yarı) | −626000 .. −608000 |
| crop_zemin.dxf | ZEMİN KAT KALIP PLANI | −522000 .. −507000 |
| crop_kat1.dxf | BİRİNCİ NORMAL KAT KALIP PLANI | −470000 .. −455000 |

## Çizimin yapısı
- Tüm paftalar tek model uzayında yan yana (x: −863 km .. +2.2 km çizim birimi), her pafta ~20.000 birim aralıkla.
- `$INSUNITS = mm` yazıyor ama çizim **cm** ile yapılmış (kolon (100/100) → 100×100 birim). Parser'ın otomatik birim düzeltmesi çalışıyor.
- Pafta başlıkları `ANTET1` katmanında (y ≈ −73.400). Antet değerleri xref_antet-100 katmanlarında: beton C?? okunmadı, çelik B 420C, tarih 14.08.2025.
- `-659..-651` aralığındaki bodrum paftası 1/2 ölçekli genel görünüş (kolonlar 50×50 çizilmiş); metrajda kullanılmamalı.
- Blok 4 alt bloktan oluşuyor (anahtar plan: B1, B2, B3, B4 BLOK).
- Kalıp planı içeriği olan katlar: Temel (2 pafta), Bodrum (2 pafta, ±0.00 döşemesi), Zemin (+3.80), 1. Kat (+7.50; bazı bölgeler +6.05/+6.50).
  "ÇATI KATI KALIP PLANI" paftasında antet dışında çizim yok. 2. kat kalıp planı yok (kolon aplikasyonu var).
- Kotlar: temel üst −3.33 (çukurlarda −4.83), temel alt −3.73/−4.03, döşemeler ±0.00 / +3.80 / +7.50 / +11.50, en üst +12.88.
  Kat yükseklikleri: bodrum 3.33, zemin 3.80, 1. kat 3.70, 2. kat 4.00 m.
- Radye temel: RD1 h=70 cm, RD2 h=40 cm (`KM Temel Marka`); altında grobeton 10 cm, blokaj 10 cm, koruma şapı 5 cm.

## Katmanlar (kalıp planı)
| Katman | İçerik |
|---|---|
| KM Kolon | kapalı LWPOLYLINE (kolon kesiti, gerçek boyut) |
| KM Perde | kapalı LWPOLYLINE (perde) |
| KM Kiriş | LINE çift çizgi (kolonlarda kesik) |
| KM Kolon/Kiriş/Perde/Döşeme Markası | yalnız TEXT etiketler |
| LGP-SLAB2 | döşeme etiketinin çerçeve kutusu (70×90 cm dikdörtgen çizgileri) — döşeme poligonu DEĞİL |
| KM Döşeme Şaft | boşluk poligonları |
| KM Temel / KM Temel Kesik | radye sınırı (dış sınır AÇIK polyline, 8 nokta) |
| VM Kolon İzi | üst kat kolon izi |
| REBAR_DET2/3, DETAIL2/3/4, TABLE2/3/4, COLUMN_DET*, BEAM2/3/4, SECTION4 | donatı/detay/tablo (metraj dışı) |
| mtr_tb, mtr_k, mtr_m, mtr_boy, mtr_not, POZ | temel demir metraj tablosu (poz, çap, adet, boy, L(m), toplam) |
| TABLE4 | programın kendi metraj özeti: KALIP (m2), BETON (m3), Ø6-12 (kg), Ø14-50 (kg) |

## Etiket biçimi
- Eleman adı = tip harfi + kat kodu + sıra no: `SB033` (S=kolon, B=bodrum), `SZ094` (zemin), `S1094` (1. kat), `S2094` (2. kat);
  kiriş `KB0021`, `KZ0063`, `K10155`; perde `PB0922`, `PZ0859`, `P10859`; döşeme `DB041`, `DZ002`, `D1001`, düşük döşeme `DDB024`.
- Kesit ayrı yazıda: `(100/100)`; kirişte genelde birleşik: `KB0021 (60/50)`; perdede bazen `PB0922 (30/535)`.
- Döşeme kalınlığı `15cm` (çıplak) veya `d=15cm`; kot yazıları `-0.15`, `+3.80` (yok sayılmalı).

## Programın kolon+perde metrajı (TABLE4) — doğrulama referansı
| Kat | Beton m³ | Kalıp m² | Ø6-12 kg | Ø14-50 kg |
|---|---|---|---|---|
| Bodrum | 1443.68 | 6367.84 | 122403.89 | 108431.69 |
| Zemin | 731.31 | 2996.27 | 67095.6 | 63719.8 |
| Birinci kat (+6.50) | 465.70 | 2034.06 | 43956.59 | 44347.2 |
| İkinci kat (+7.50) | 211.61 | 767.94 | 18002.4 | 36193.89 |
| Çatı | 454.71 | 2087.39 | 37501.8 | 30202.79 |

Mevcut parser (kırpılmış paftalar, kolon+perde alanı × kat yüksekliği): bodrum 1500 m³ (+4 %), zemin 728 m³ (−0.4 %),
1. kat 709 m³ (program 465.7+211.6 = 677 m³; paftada +6.50 ve +7.50 kotları birlikte). Kalıp bizde %15-25 fazla:
program kolon kalıbını net yükseklikle (H − kiriş yüksekliği) alıyor gibi.

## Parser'da yapılacaklar
1. `text_parser.py`: kat kodlu önekleri tanı (S/K/P/D/DD + [B|Z|0-9] + no) → tip ipucu ilk harften. Şu an `SZ…` adı düşüyor,
   kolonlara `KZ…` kiriş adı yapışıyor, `DB…` döşeme etiketi tip ipucu taşımadığı için döşeme hiç üretilmiyor.
2. Çıplak `15cm` → döşeme kalınlığı olarak oku.
3. `LGP-SLAB2` katmanını döşeme sayma (yok-sayma listesine `LGP` ekle); döşemeler kiriş ağından türetilsin.
4. Radye: `KM Temel` açık dış sınır polyline'ını kapat; RD1/RD2 etiketlerinden kalınlık al (`RD1` + `70cm`).
5. 1. kat paftasında 54 üst üste kolon (alt kat izi) var; dedupe bunu zaten teke indiriyor.
6. Büyük dosya: 494 MB tek DXF; pafta seçme/kırpma (x aralığı) özelliği ya da kullanıcıdan pafta bazlı DXF istemek gerekir.

## Güncelleme (5 Eyl 2026): yapılanlar ve sonuç

Parser'da yapılanlar: kat kodlu etiketler, çıplak `15cm`, `LGP`/`KESİK` yok sayma, radye (açık sınır + RD bölgeleri),
kolon/perde beton–kalıp kuralı, pafta bazlı kat yüksekliği, çok paftalı dosya için pafta tarama/kırpma (`app/parser/sheets.py`),
temel paftasındaki kolon/perde izlerinin metraj dışı bırakılması.

Uçtan uca (tam dosya yüklendi, 6 pafta seçildi: Temel-01/02, Bodrum-01/02 H=3.33, Zemin H=3.80, 1. Kat H=3.70):

| Grup | Beton m³ | Kalıp m² |
|---|---|---|
| Radye | 9016 | 1079 |
| Kolon | 2251 | 8641 |
| Perde | 687 | 3353 |
| Kiriş | 4740 | 19201 |
| Döşeme | 1580 | 10527 |
| **Toplam** | **18274** | **42801** |

Kolon+perde betonu programla: bodrum +3,9 %, zemin −0,4 %, 1. kat +4,7 %; kalıp −2,4 / −2,1 / +1,5 %.
2. kat ve çatı kalıp planı dosyada olmadığı için metrajda yok. Demir oranı önerisi (programın tablolarından):
kolon/perde 170, kiriş 160 kg/m³ (proje parametrelerinden girilir).
