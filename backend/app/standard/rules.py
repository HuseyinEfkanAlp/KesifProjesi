"""Keşif ölçüm kuralları ve iş grupları (ÇŞB — Çevre, Şehircilik ve İklim Değişikliği Bakanlığı birim fiyat tarifleri).

Keşif, Türkiye'de yaygın uygulamadaki gibi dört iş grubunda toplanır: kaba yapı (inşaat), ince işler (mimari),
mekanik tesisat, elektrik tesisatı (+ altyapı / peyzaj). Her kalem mümkünse bir ÇŞB poz numarasıyla ilişkilendirilir ve
miktar o pozun **ölçü kuralına** göre hesaplanır. Kaynak poz tarifleri (birimfiyat.net / yfk.csb.gov.tr):

  15.150.1006  C 30/37 hazır beton (pompalı)                    m³   ölçü: projedeki beton hacmi
  15.160.1003  Ø8–Ø12 nervürlü beton çelik çubuğu               ton  ölçü: donatı detayına göre boy × birim ağırlık (cetvel)
  15.160.1004  Ø14–Ø28 nervürlü beton çelik çubuğu              ton
  15.180.1003  Plywood ile düz yüzeyli betonarme kalıbı         m²   ölçü: kalıp gören yüzler; inşaat boşluklarının çevre kalıbı sayılmaz
  15.185.1006  Çelik borudan kalıp iskelesi                     m³
  15.225.1004  10 cm gazbeton duvar (tutkallı)                  m²   ölçü: projesi üzerinden; 0,10 m²'den küçük boşluklar düşülmez
  15.225.1007  15 cm gazbeton duvar                             m²   (aynı kural)
  15.225.1010  20 cm gazbeton duvar                             m²   (aynı kural)
  15.280.1008  Makine sıvası ile duvarlara tek kat alçı sıva    m²   ölçü: sıvanan yüzeyler; tüm boşluklar ve öteki kaplama yüzeyleri düşülür
  15.540.1509  İç cephe astar + iki kat plastik boya            m²   ölçü: boyanan yüzeyler; tüm boşluklar düşülür
  25.305.xxxx  PPRC temiz su boruları                           m    ölçü: boru boyu
  35.140.3161  3x2,5 mm² NYY kolon / besleme hattı              m    ölçü: hat boyu
  25.305.6102/6103/6104  Sert PVC pis su borusu Ø75 / Ø100-110 / Ø125   m
  25.305.2101/2104  PN20 PPRC temiz su borusu 20 / 40 mm            m
  25.305.7101  PE100 SDR17 PN10 polietilen boru Ø32               m
  25.470.1101-1104  Galvanizli sacdan dikdörtgen hava kanalı (en geniş kenara göre)   m²/m
  25.470.1204  Kenetli spiral silindirik hava kanalı Ø ≤ 1000     m
  25.705.1102  Dik DN20 standart otomatik yangın sprinkleri       adet
  15.375.1053  40x40 renkli seramik yer karosu döşeme kaplaması   m²

Katalogdaki kalemin `poz` alanı doluysa o kullanılır; boşsa buradaki varsayılan eşleme (DEFAULT_POZ) denenir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- iş grupları

WORK_GROUPS: dict[str, str] = {
    "KABA": "Kaba yapı (inşaat)",
    "INCE": "İnce işler (mimari)",
    "MEK": "Mekanik tesisat",
    "ELK": "Elektrik tesisatı",
    "ALT": "Altyapı / peyzaj / diğer",
}
WORK_GROUP_ORDER = list(WORK_GROUPS)

# sezgisel disiplin anahtarı ya da "ksf:<DİSİPLİN>" -> iş grubu
_DISC_TO_GROUP: dict[str, str] = {
    "structural": "KABA", "rebar": "KABA",
    "architectural": "INCE",
    "electrical": "ELK",
    "mechanical": "MEK",
    "STA": "KABA",
    "MIM": "INCE", "INC": "INCE", "CEP": "INCE", "CAT": "INCE", "IZO": "INCE",
    "ELK": "ELK", "ZAY": "ELK",
    "MEK": "MEK", "HAV": "MEK", "YAN": "MEK", "SIH": "MEK",
    "ALT": "ALT", "PEY": "ALT", "ASN": "ALT",
}


def work_group_of(discipline_key: str) -> str:
    """'structural' -> KABA, 'ksf:HAV' -> MEK, bilinmeyen -> ALT."""
    key = (discipline_key or "").split(":", 1)[-1]
    return _DISC_TO_GROUP.get(key, _DISC_TO_GROUP.get(key.upper(), "ALT"))


# ---------------------------------------------------------------- ölçü kuralları

@dataclass(frozen=True)
class Rule:
    code: str
    text: str          # kullanıcıya gösterilen kural cümlesi
    source: str        # dayandığı poz / tarif


RULES: dict[str, Rule] = {
    "wall_opening": Rule("wall_opening", "Duvar: projesi üzerinden; 0,10 m²'den küçük boşluklar düşülmez",
                         "ÇŞB 15.225 gazbeton duvar pozları"),
    "plaster_openings": Rule("plaster_openings", "Sıva: sıvanan yüzeyler, tüm boşluklar düşülür", "ÇŞB 15.280.1008"),
    "paint_openings": Rule("paint_openings", "Boya: boyanan yüzeyler, tüm boşluklar düşülür", "ÇŞB 15.540.1509"),
    "formwork": Rule("formwork", "Kalıp: kalıp gören yüzler; inşaat boşluklarının çevre kalıbı sayılmaz", "ÇŞB 15.180.1003"),
    "rebar": Rule("rebar", "Demir: donatı boyu × birim ağırlık (cetvel), ton", "ÇŞB 15.160.1003 / 15.160.1004"),
    "concrete": Rule("concrete", "Beton: projedeki hacim (m³)", "ÇŞB 15.150.1006"),
    "pipe_length": Rule("pipe_length", "Boru / kablo: hat boyu (m)", "ÇŞB 25.305 / 35.140"),
}

WALL_OPENING_MIN_M2 = 0.10     # bu alanın altındaki boşluklar duvar metrajından düşülmez (ÇŞB 15.225)


def deductible_opening(area_m2: float) -> bool:
    return area_m2 >= WALL_OPENING_MIN_M2


# ---------------------------------------------------------------- varsayılan poz eşlemesi

# (tür, grup deseni) -> poz. Grup deseni düzenli ifadedir; ilk eşleşen kazanır.
DEFAULT_POZ: list[tuple[str, str, str, str]] = [
    ("beton", r".*", "15.150.1006", "C 30/37 hazır beton, pompalı"),
    ("kalip", r".*", "15.180.1003", "Plywood ile düz yüzeyli betonarme kalıbı"),
    # grup "o12" (tablodan) ya da "column:o12" (oran demiri çapa bölünmüş) olabilir: son parçaya bakılır
    ("demir", r"^(?:.*:)?o?(8|10|12)$", "15.160.1003", "Ø8–Ø12 nervürlü çelik"),
    ("demir", r"^(?:.*:)?o?(14|16|18|20|22|24|26|28)$", "15.160.1004", "Ø14–Ø28 nervürlü çelik"),
    ("demir", r".*", "15.160.1004", "Nervürlü çelik (çap bilinmiyor: Ø14–Ø28 pozu)"),
    ("duvar", r"^ytong:10$", "15.225.1004", "10 cm gazbeton duvar"),
    ("duvar", r"^ytong:15$", "15.225.1007", "15 cm gazbeton duvar"),
    ("duvar", r"^ytong:20$", "15.225.1010", "20 cm gazbeton duvar"),
    ("siva", r".*", "15.280.1008", "Makine sıvası ile tek kat alçı sıva"),
    ("boya", r".*", "15.540.1509", "İç cephe astar + iki kat plastik boya"),
    ("kablo", r"^nyy_3x2\.5$", "35.140.3161", "3x2,5 mm² NYY kolon / besleme hattı"),
    # mekanik / sıhhi / havalandırma / yangın (birimfiyat.net ile doğrulandı)
    ("boru_pvc", r"^(70|75)$", "25.305.6102", "Sert PVC pis su borusu Ø75, geçme muflu"),
    ("boru_pvc", r"^(100|110)$", "25.305.6103", "Sert PVC pis su borusu Ø100-110, geçme muflu"),
    ("boru_pvc", r"^125$", "25.305.6104", "Sert PVC pis su borusu Ø125"),
    ("boru_pprc_temiz", r"^20$", "25.305.2101", "PN 20 polipropilen temiz su borusu 1/2\" (20 mm)"),
    ("boru_pprc_temiz", r"^40$", "25.305.2104", "PN 20 polipropilen temiz su borusu 1 1/4\" (40 mm)"),
    ("boru_pprc_temiz", r".*", "", "PN 20 polipropilen temiz su borusu — çapa göre 25.305.21xx alt pozunu katalogdan seçin"),
    ("boru_pe", r"^32$", "25.305.7101", "PE100 SDR17 PN10 polietilen boru Ø32"),
    ("hava_kanal", r"^[1-5]\d\dx\d+$|^600x\d+$", "25.470.1101", "Galvanizli sacdan dikdörtgen hava kanalı, en geniş kenar ≤ 600 mm (0,60 mm)"),
    ("hava_kanal", r"^(6[0-9]\d|[7-9]\d\d|1[01]\d\d|12[0-4]\d)x\d+$", "25.470.1102", "Galvanizli sacdan dikdörtgen hava kanalı, en geniş kenar ≤ 1249 mm (0,80 mm)"),
    ("hava_kanal", r"^(1[3-9]\d\d|2[0-4]\d\d)x\d+$", "25.470.1103", "Galvanizli sacdan dikdörtgen hava kanalı, en geniş kenar ≤ 2490 mm (1,00 mm)"),
    ("hava_kanal", r".*", "", "Galvanizli sacdan dikdörtgen hava kanalı — kenara göre 25.470.11xx alt pozunu katalogdan seçin"),
    ("hava_kanal_yuvarlak", r".*", "25.470.1204", "Kenetli spiral galvanizli sacdan silindirik hava kanalı Ø ≤ 1000 mm"),
    ("sprinkler", r".*", "25.705.1102", "Dik DN20 standart uygulama otomatik yangın sprinkleri"),
    ("seramik_zemin", r".*", "15.375.1053", "40x40 cm I. kalite renkli seramik yer karosu ile döşeme kaplaması (karo yapıştırıcısı ile)"),
    # 9 Eyl 2026: birimfiyat.net / herpoz / kamupro / csb.gov.tr ile doğrulananlar
    ("seramik_duvar", r".*", "15.380.1056", "20x60 / 30x60 / 33x60 cm I. kalite renkli seramik duvar karosu ile duvar kaplaması (karo yapıştırıcısı ile)"),
    ("kazi", r".*", "15.120.1101", "Makine ile her derinlik ve genişlikte yumuşak ve sert toprak kazılması (derin kazı)"),
    ("grobeton", r".*", "15.150.1003", "C 16/20 hazır beton, pompalı (grobeton)"),
    ("kalip_iskelesi", r".*", "15.185.1001", "Çelik borudan kalıp iskelesi yapılması (0,00–4,00 m arası)"),
    ("is_iskelesi", r".*", "15.185.1013", "Ön yapımlı bileşenlerden tam güvenlikli dış cephe iş iskelesi (0,00–51,50 m)"),
    ("temel_su_yalitimi", r".*", "15.255.1009", "3 + 4 mm elastomer esaslı polimer bitümlü örtü ile iki kat su yalıtımı"),
    ("kablo", r"^nyy_4x16$", "35.140.3225", "4x16 mm² NYY kolon / besleme hattı"),
]
_DEFAULT_POZ_RE = [(k, re.compile(p, re.IGNORECASE), poz, name) for k, p, poz, name in DEFAULT_POZ]


def default_poz(kind: str, group: str) -> tuple[str, str] | None:
    """Sezgisel kalemler için varsayılan ÇŞB pozu: (poz no, poz adı) ya da None."""
    for k, rx, poz, name in _DEFAULT_POZ_RE:
        if k == kind and rx.match(group or ""):
            return poz, name
    return None


# ---------------------------------------------------------------- reçeteler (sezgisel kalemler)
#
# Katalog kalemlerinin reçetesi CatalogItem.recipe içindedir. Sezgisel (katalog dışı) türler için reçete burada:
# tür -> [{"code", "factor", "spec", "times"}]. Miktar = kalem miktarı × factor (× H, times == "H" ise).
# Değerler yaygın uygulama varsayılanıdır; kalem notunda "reçete varsayılanı" yazar, katalogdan düzenlenir.
def _r(code, factor=1.0, spec="", times=""):
    return {"code": code, "factor": factor, "spec": spec, "times": times}


RECIPES_BY_KIND: dict[str, list[dict]] = {
    # "kalip" reçetede yok: işçiliği eleman tipine / malzemeye göre hesaplanır (quantity/recipes.py: _formwork_recipe).
    # Kalıp iskelesi de reçetede değil: döşeme alanı × (H − d) (boq.structural_items)
    "beton": [_r("BETON_ISCILIK", 1.0), _r("VIBRATOR", 0.3), _r("BETON_KUR", 1.0), _r("BETON_POMPAJ", 1.0)],
    "demir": [_r("DEMIR_ISCILIK", 0.02)],                                         # 20 saat / ton = 0,02 saat / kg
    "duvar": [_r("DUVAR_ISCILIK", 0.8), _r("DUVAR_TUTKAL", 4.0)],                # saat / m²; kg / m² (gazbeton tutkalı)
    "siva": [_r("SIVA_ISCILIK", 0.7), _r("KOSE_PROFILI", 0.2)],
    "boya": [_r("BOYA_ISCILIK", 0.3)],
    "cam": [_r("CAM_MONTAJ", 0.5)],
    "tava": [_r("TAVA_MONTAJ", 0.4), _r("TAVA_ASKI", 0.6), _r("TAVA_EK", 0.35)],
    "kablo": [_r("KABLO_CEKME", 0.05)],
    "boru": [_r("BORU_MONTAJ_ELK", 0.1)],
    "armatur": [_r("ARMATUR_MONTAJ", 0.5), _r("BUAT", 1.0)],
    "pencere": [_r("LENTO"), _r("DOGRAMA_MONTAJ", 1.0), _r("MONTAJ_KOPUGU"), _r("KORKASA", 1.0, "$SIZE"), _r("KORKASA_PROFIL", 1.0, "", "PER"),
                _r("KORKASA_MONTAJ", 0.5), _r("DUBEL_VIDA", 8.0),
                _r("CAM_FITIL", 1.0, "", "PER"), _r("SILIKON", 1.0, "", "PER"), _r("MASTIK", 1.0, "", "PER"), _r("DENIZLIK", 1.0, "", "WID")],
    "kapi": [_r("LENTO"), _r("DOGRAMA_MONTAJ", 1.5), _r("MONTAJ_KOPUGU"), _r("KAPI_KASASI", 1.0, "$SIZE"), _r("PERVAZ", 1.0, "", "PER"), _r("MENTESE", 3.0),
             _r("KILIT"), _r("KAPI_KOLU"), _r("STOPER"), _r("ESIK", 1.0, "", "WID"), _r("DUBEL_VIDA", 6.0), _r("SILIKON", 1.0, "", "PER")],
}
RECIPE_MAX_DEPTH = 4


# ---------------------------------------------------------------- demir işçiliği (çap / kat / hazırlık bazında)
#
# "1 m² kaç adam-saat" demir için anlamsızdır: belirleyici olan **ton başına** işçiliktir ve o da çapa bağlıdır.
# Bir ton Ø8 demir ~2.500 m, bir ton Ø26 demir ~240 m'dir: aynı tonaj on kat farklı sayıda çubuk, bağ noktası ve
# kesim demektir. ÇŞB'nin demiri iki ayrı poza bölmesinin (15.160.1003 Ø8–12 / 15.160.1004 Ø14–28) sebebi de budur.
#
# İşçilik üç ayrı işe bölünür — biri sahada hiç yapılmayabilir (demir hazır kesilmiş / bükülmüş gelirse):
#   hazırlık : düzeltme, kesme, bükme, etriye / pilye imalatı
#   taşıma   : sahaya indirme, istifleme, kata / kalıp üstüne dağıtım
#   montaj   : yerine yerleştirme, aralık ayarı, bağlama, sehpa / pas payı
#
# Çift kat (alt + üst) donatıda montaj artar: üst hasır sehpa üstünde, havada bağlanır ve üstünde yürünür.
# Değerler yaygın uygulama varsayılanıdır (ÇŞB analizinden doğrulanmadı) — projeye göre katalogdan düzenlenir.
REBAR_LABOR_HOURS_PER_TON: list[tuple[int, int, dict[str, float]]] = [
    #  min  max   hazırlık  taşıma  montaj      (saat / ton)
    (6,  10, {"hazirlik": 12.0, "tasima": 6.0, "montaj": 24.0}),   # ince: çok çubuk, çok bağ noktası
    (11, 12, {"hazirlik":  9.0, "tasima": 5.0, "montaj": 17.0}),
    (13, 16, {"hazirlik":  8.0, "tasima": 4.0, "montaj": 13.0}),
    (17, 22, {"hazirlik":  7.0, "tasima": 4.0, "montaj": 10.0}),
    (23, 40, {"hazirlik":  6.0, "tasima": 4.0, "montaj":  8.0}),   # kalın: az çubuk ama ağır, vinç / iki kişi
]
REBAR_LABOR_DEFAULT_DIA = 14        # çapı okunamayan demir kaleminde varsayılan bant
MIN_REBAR_DIA, MAX_REBAR_DIA = 6, 40
REBAR_DOUBLE_LAYER_MONTAJ = 1.15    # çift kat: üst hasır havada bağlanır
REBAR_CHAIR_KG_PER_TON = 25.0       # çift katta üst hasırı taşıyan sehpa / poz demiri (kg / ton)


def rebar_dia_of_group(group: str) -> int:
    """Demir kalem grubundan çap: "o12" / "column:o12" / "fire:o12" -> 12; çap yoksa 0.

    Katalog kalemi olarak yazılan demirde (KSF / reçete: DEMIR spec'i "çap (mm)") grup çıplak sayıdır: "12"."""
    for part in str(group or "").split(":"):
        p = part.strip().lower()
        if p.startswith("o") and p[1:].isdigit():
            p = p[1:]
        if p.isdigit() and MIN_REBAR_DIA <= int(p) <= MAX_REBAR_DIA:
            return int(p)
    return 0


def rebar_labor_norms(dia_mm: int, layers: str = "", prefab_pct: float = 0.0) -> dict[str, float]:
    """Bir demir kalemi için saat / ton: {"hazirlik", "tasima", "montaj"}.

    dia_mm 0 ise REBAR_LABOR_DEFAULT_DIA bandı kullanılır. layers == "cift" montajı artırır.
    prefab_pct: hazır kesilmiş / bükülmüş gelen demir yüzdesi — o oranda hazırlık sahada yapılmaz."""
    d = int(dia_mm) or REBAR_LABOR_DEFAULT_DIA
    row = next((v for lo, hi, v in REBAR_LABOR_HOURS_PER_TON if lo <= d <= hi), REBAR_LABOR_HOURS_PER_TON[-1][2])
    out = dict(row)
    if layers == "cift":
        out["montaj"] = round(out["montaj"] * REBAR_DOUBLE_LAYER_MONTAJ, 2)
    ready = min(max(float(prefab_pct or 0.0), 0.0), 100.0) / 100.0
    out["hazirlik"] = round(out["hazirlik"] * (1.0 - ready), 2)
    return out


# ---------------------------------------------------------------- kalıp işçiliği (eleman tipi / malzeme / tekrar)
#
# Kalıpta da m² başına sabit saat yanlıştır: aynı 1 m² kalıp, elemanın **biçimine** göre çok farklı emek ister.
#
#   kolon    küçük yüzeyde dört köşe, şakül ve eksen tutturma  -> m² başına en çok kenar ve ölçü işi
#   perde    büyük düz panolar, m² başına az kenar             -> en ucuz düşey kalıp
#   kiriş    taban + iki yanak, baştan aşağı destek, tavan işi -> en pahalı yatay kalıp
#   döşeme   büyük düz yüzey (altındaki iskele ayrı kalemdir)
#   temel    yalnız çevre kenar kalıbı, yerde, düz             -> en ucuzu
#   merdiven rıht + basamak + eğim                             -> en pahalısı
#
# İşçilik üçe ayrılır (demirdeki gibi, biri hiç olmayabilir):
#   imalat : panonun kesilip çakılması / hazırlanması — bir kez yapılır, levha kaç kez kullanılırsa ona bölünür
#   kurma  : yerine kurma, ölçü - şakül - eksen, destek ve sıkma
#   söküm  : söküm, temizleme, yağlama, bir sonraki kata taşıma
#
# Hazır panolu sistemler (çelik pano, tünel kalıp) imalatı ortadan kaldırır, kurma ve sökümü hızlandırır.
# Değerler yaygın uygulama varsayılanıdır (ÇŞB analizinden doğrulanmadı) — katalogdan / parametreden düzenlenir.
FORMWORK_LABOR_HOURS_PER_M2: dict[str, dict[str, float]] = {
    #                    imalat  kurma  söküm      (saat / m², plywood, tek kullanım)
    "column":     {"imalat": 0.35, "kurma": 0.75, "sokum": 0.35},
    "shear_wall": {"imalat": 0.25, "kurma": 0.55, "sokum": 0.25},
    "beam":       {"imalat": 0.40, "kurma": 0.85, "sokum": 0.40},
    "slab":       {"imalat": 0.25, "kurma": 0.55, "sokum": 0.30},
    "foundation": {"imalat": 0.20, "kurma": 0.40, "sokum": 0.20},
    "parapet":    {"imalat": 0.30, "kurma": 0.70, "sokum": 0.30},
    "stair":      {"imalat": 0.60, "kurma": 1.20, "sokum": 0.50},
}
# eleman tipi okunamayan kalıp kalemi (KÇS kalemi, lento reçetesi…): eski düz 1,2 sa/m² değeri
FORMWORK_LABOR_DEFAULT: dict[str, float] = {"imalat": 0.30, "kurma": 0.60, "sokum": 0.30}

# kalıp malzemesi / sistemi çarpanı (params: formwork_material)
FORMWORK_MATERIAL_FACTOR: dict[str, dict[str, float]] = {
    "plywood": {"imalat": 1.0,  "kurma": 1.0,  "sokum": 1.0},
    "ahsap":   {"imalat": 1.25, "kurma": 1.15, "sokum": 1.10},   # kereste: her pano yerinde kesilip çakılır
    "celik":   {"imalat": 0.0,  "kurma": 0.70, "sokum": 0.60},   # hazır çelik pano: imalat yok, kilitli montaj
    "tunel":   {"imalat": 0.0,  "kurma": 0.45, "sokum": 0.40},   # tünel kalıp: vinçle tek parça
}


def formwork_etype_of_group(group: str) -> str:
    """Kalıp kalem grubundan eleman tipi: "column", "foundation:raft" -> "foundation"; tanınmazsa ""."""
    et = str(group or "").split(":")[0].strip().lower()
    return et if et in FORMWORK_LABOR_HOURS_PER_M2 else ""


def formwork_labor_norms(etype: str = "", material: str = "", reuse: float = 1.0) -> dict[str, float]:
    """Bir kalıp kalemi için saat / m²: {"imalat", "kurma", "sokum"}.

    imalat levhanın kullanım sayısına bölünür: pano bir kez yapılır, N kez kullanılır — her kullanımdaki
    yerinde düzeltme payı `kurma` içindedir."""
    base = FORMWORK_LABOR_HOURS_PER_M2.get(etype or "", FORMWORK_LABOR_DEFAULT)
    fac = FORMWORK_MATERIAL_FACTOR.get(str(material or "plywood").strip().lower(),
                                       FORMWORK_MATERIAL_FACTOR["plywood"])
    n = max(float(reuse or 1.0), 1.0)
    return {"imalat": round(base["imalat"] * fac["imalat"] / n, 4),
            "kurma": round(base["kurma"] * fac["kurma"], 4),
            "sokum": round(base["sokum"] * fac["sokum"], 4)}


# ---------------------------------------------------------------- ekip büyüklüğü

# **Bir ekipteki kişi sayısı** — bu bir norm, saha kararı değil. Kaç ekibin aynı anda çalışacağı projenin
# kendi kararıdır (`params.crew_count`), o yüzden ayrı tutulur: ekip = kişi/ekip × eşzamanlı ekip sayısı.
#
# Değerler Türkiye'de yaygın ekip kuruluşudur: kalıpta 2 marangoz + 1 amele, sıvada 1 usta + 1 amele,
# beton dökümünde pompa başında kalabalık ekip. ÇŞB analizlerinden doğrulanmadı; katalogdan düzenlenir.
CREW_SIZE: dict[str, float] = {
    # demir
    "demir_hazirlik": 3.0, "demir_montaj": 4.0, "demir_tasima": 3.0,
    # kalıp
    "kalip_imalat": 3.0, "kalip_kurma": 3.0, "kalip_sokum": 3.0,
    # beton
    "beton_iscilik": 6.0, "beton_pompaj": 4.0, "vibrator": 2.0, "beton_kur": 2.0,
    # duvar ve ince işler
    "duvar_iscilik": 2.0, "siva_iscilik": 2.0, "boya_iscilik": 2.0, "sap_iscilik": 3.0,
    "seramik_iscilik": 2.0, "yalitim_iscilik": 2.0, "cati_iscilik": 3.0,
    # doğrama / cephe / tesisat
    "dograma_montaj": 2.0, "korkasa_montaj": 2.0, "cam_montaj": 2.0, "cephe_montaj": 3.0,
    "prekast_montaj": 4.0, "kanal_montaj": 2.0, "boru_montaj": 2.0, "cihaz_montaj": 2.0,
    "vitrifiye_montaj": 2.0, "armatur_montaj": 2.0, "kablo_montaj": 2.0,
}
CREW_DEFAULT = 2.0        # tanınmayan işçilik kalemi: usta + yardımcı


def crew_size(kind: str) -> float:
    """Bir ekipteki kişi sayısı (norm). Eşzamanlı ekip sayısı ayrıdır."""
    return CREW_SIZE.get(kind, CREW_DEFAULT)
