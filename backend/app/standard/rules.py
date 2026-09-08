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
    ("demir", r"^o(8|10|12)$", "15.160.1003", "Ø8–Ø12 nervürlü çelik"),
    ("demir", r"^o(14|16|18|20|22|24|26|28)$", "15.160.1004", "Ø14–Ø28 nervürlü çelik"),
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
    ("boru_pprc_temiz", r".*", "25.305.21", "PN 20 polipropilen temiz su borusu (çapa göre alt poz)"),
    ("boru_pe", r"^32$", "25.305.7101", "PE100 SDR17 PN10 polietilen boru Ø32"),
    ("hava_kanal", r"^[1-5]\d\dx\d+$|^600x\d+$", "25.470.1101", "Galvanizli sacdan dikdörtgen hava kanalı, en geniş kenar ≤ 600 mm (0,60 mm)"),
    ("hava_kanal", r"^(6[0-9]\d|[7-9]\d\d|1[01]\d\d|12[0-4]\d)x\d+$", "25.470.1102", "Galvanizli sacdan dikdörtgen hava kanalı, en geniş kenar ≤ 1249 mm (0,80 mm)"),
    ("hava_kanal", r"^(1[3-9]\d\d|2[0-4]\d\d)x\d+$", "25.470.1103", "Galvanizli sacdan dikdörtgen hava kanalı, en geniş kenar ≤ 2490 mm (1,00 mm)"),
    ("hava_kanal", r".*", "25.470.11", "Galvanizli sacdan dikdörtgen hava kanalı (kenara göre alt poz)"),
    ("hava_kanal_yuvarlak", r".*", "25.470.1204", "Kenetli spiral galvanizli sacdan silindirik hava kanalı Ø ≤ 1000 mm"),
    ("sprinkler", r".*", "25.705.1102", "Dik DN20 standart uygulama otomatik yangın sprinkleri"),
    ("seramik_zemin", r".*", "15.375.1053", "40x40 cm I. kalite renkli seramik yer karosu ile döşeme kaplaması (karo yapıştırıcısı ile)"),
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
    "kalip": [_r("KALIP_ISCILIK", 1.2), _r("KALIP_ISKELESI", 1.0, "", "H")],   # kurma + söküm saat/m²; iskele m³ = m² × H
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
