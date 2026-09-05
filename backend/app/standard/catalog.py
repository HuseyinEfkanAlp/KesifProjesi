"""Keşif Çizim Standardı (KÇS) kataloğu: disiplinler ve keşif kalemleri.

Standart katman adı:  KSF-<DİSİPLİN>-<KALEM>[-<ÖZELLİK>]
  KSF-HAV-HAVA_KANAL-600x400   havalandırma kanalı 600x400 mm  (çizgi -> m)
  KSF-SIH-BORU_PPRC-32         PPRC boru Ø32                   (çizgi -> m)
  KSF-YAN-SPRINKLER            sprinkler                       (blok -> adet)
  KSF-CEP-KOMPOZIT_PANEL       kompozit cephe paneli           (kapalı alan -> m²)
  KSF-MIM-DUVAR_YTONG-20       Ytong duvar 20 cm               (çizgi -> m² = uzunluk × duvar yüksekliği)
  KSF-IZO-XPS-5                XPS ısı yalıtımı 5 cm           (alan -> m²)
  KSF-STA-DOLGU-30             dolgu 30 cm                     (alan -> m³ = alan × kalınlık)
Alan ayracı '-' (tire); kelime içi ayraç '_' (alt çizgi). ÖZELLİK serbest metindir (boyut, kesit, malzeme, marka).

Ölçüm kuralı (measure): count | length | area | wall_area | volume
  count      blok / sembol sayısı (adet)
  length     çizgi / polyline uzunluğu (m)
  area       kapalı çokgen / tarama alanı (m²)
  wall_area  uzunluk × yükseklik (m²); yükseklik ÖZELLİK'in 2. parçası (ör. 20x300 -> 300 cm) yoksa proje duvar yüksekliği
  volume     alan × kalınlık (m³); kalınlık ÖZELLİK'ten cm olarak (ör. 30 -> 0.30 m)
Katalogda olmayan kalem geometriden ölçülür (blok->adet, çizgi->m, alan->m²) ve uyarı verir.

Katalog varsayılanı kodda; kullanıcı eklemeleri / değişiklikleri DATA_DIR/catalog.json dosyasında saklanır.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

MEASURES: dict[str, tuple[str, str]] = {
    "count": ("Adet (blok sayımı)", "adet"),
    "length": ("Uzunluk (çizgi)", "m"),
    "area": ("Alan (kapalı çokgen / tarama)", "m²"),
    "wall_area": ("Duvar alanı (uzunluk × yükseklik)", "m²"),
    "volume": ("Hacim (alan × kalınlık)", "m³"),
}

DEFAULT_DISCIPLINES: dict[str, str] = {
    "STA": "Statik / kaba yapı",
    "MIM": "Mimari",
    "INC": "İnce işler",
    "CEP": "Dış cephe",
    "CAT": "Çatı",
    "IZO": "İzolasyon",
    "ELK": "Elektrik",
    "ZAY": "Zayıf akım / otomasyon",
    "MEK": "Mekanik (ısıtma / soğutma)",
    "HAV": "Havalandırma",
    "YAN": "Yangın tesisatı",
    "SIH": "Sıhhi tesisat",
    "ALT": "Altyapı",
    "PEY": "Peyzaj",
    "ASN": "Asansör / yürüyen merdiven",
}


@dataclass
class CatalogItem:
    code: str                 # KALEM kodu (büyük harf, alt çizgi)
    discipline: str           # disiplin kodu
    name: str                 # görünen ad
    measure: str              # count | length | area | wall_area | volume
    unit: str = ""            # boş -> ölçüm kuralının birimi
    spec_label: str = ""      # ÖZELLİK alanının anlamı ("en x yükseklik (mm)")
    example: str = ""         # örnek katman adı
    custom: bool = False      # kullanıcı ekledi

    def __post_init__(self):
        self.code = normalize_code(self.code)
        self.discipline = self.discipline.upper()
        if self.measure not in MEASURES:
            raise ValueError(f"Geçersiz ölçüm kuralı: {self.measure}")
        if not self.unit:
            self.unit = MEASURES[self.measure][1]
        if not self.example:
            self.example = f"KSF-{self.discipline}-{self.code}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["measure_label"] = MEASURES[self.measure][0]
        return d


def normalize_code(code: str) -> str:
    c = code.strip().replace("ı", "i").replace("İ", "I").replace("ş", "s").replace("Ş", "S").replace("ğ", "g").replace("Ğ", "G")
    c = c.replace("ç", "c").replace("Ç", "C").replace("ö", "o").replace("Ö", "O").replace("ü", "u").replace("Ü", "U")
    c = re.sub(r"[^A-Za-z0-9]+", "_", c).strip("_").upper()
    return c


def _i(code, disc, name, measure, spec_label="", example=""):
    return CatalogItem(code, disc, name, measure, spec_label=spec_label, example=example)


DEFAULT_ITEMS: list[CatalogItem] = [
    # STA
    _i("BETON", "STA", "Beton (alan × kalınlık)", "volume", "kalınlık (cm)", "KSF-STA-BETON-20"),
    _i("GROBETON", "STA", "Grobeton", "volume", "kalınlık (cm)", "KSF-STA-GROBETON-10"),
    _i("DOLGU", "STA", "Dolgu / blokaj", "volume", "kalınlık (cm)", "KSF-STA-DOLGU-30"),
    _i("KAZI", "STA", "Kazı", "volume", "derinlik (cm)", "KSF-STA-KAZI-350"),
    _i("KALIP", "STA", "Kalıp", "area", "", "KSF-STA-KALIP"),
    _i("CELIK_PROFIL", "STA", "Çelik profil", "length", "profil (HEA200)", "KSF-STA-CELIK_PROFIL-HEA200"),
    _i("HASIR_CELIK", "STA", "Hasır çelik", "area", "tip (Q221)", "KSF-STA-HASIR_CELIK-Q221"),
    # MIM
    _i("DUVAR_YTONG", "MIM", "Ytong / gazbeton duvar", "wall_area", "kalınlık (cm) [x yükseklik (cm)]", "KSF-MIM-DUVAR_YTONG-20"),
    _i("DUVAR_TUGLA", "MIM", "Tuğla duvar", "wall_area", "kalınlık (cm)", "KSF-MIM-DUVAR_TUGLA-13.5"),
    _i("DUVAR_BIMS", "MIM", "Bims duvar", "wall_area", "kalınlık (cm)", "KSF-MIM-DUVAR_BIMS-19"),
    _i("DUVAR_ALCIPAN", "MIM", "Alçıpan bölme duvar", "wall_area", "sistem (2x12.5)", "KSF-MIM-DUVAR_ALCIPAN-2x12.5"),
    _i("KAPI", "MIM", "Kapı", "count", "tip / ölçü (90x210)", "KSF-MIM-KAPI-K1_90x210"),
    _i("PENCERE", "MIM", "Pencere", "count", "tip / ölçü (120x140)", "KSF-MIM-PENCERE-P1_120x140"),
    _i("CAM", "MIM", "Cam", "area", "tip (4+16+4)", "KSF-MIM-CAM-4+16+4"),
    _i("KOREKUYU", "MIM", "Korkuluk", "length", "tip", "KSF-MIM-KOREKUYU-CAM"),
    # INC
    _i("SIVA", "INC", "Sıva", "wall_area", "tip (ALCI / CIMENTO)", "KSF-INC-SIVA-ALCI"),
    _i("BOYA", "INC", "Boya", "wall_area", "tip", "KSF-INC-BOYA-PLASTIK"),
    _i("SERAMIK_ZEMIN", "INC", "Zemin seramiği", "area", "ebat (60x60)", "KSF-INC-SERAMIK_ZEMIN-60x60"),
    _i("SERAMIK_DUVAR", "INC", "Duvar seramiği", "wall_area", "ebat", "KSF-INC-SERAMIK_DUVAR-30x60"),
    _i("LAMINAT", "INC", "Laminat parke", "area", "tip", "KSF-INC-LAMINAT-8MM"),
    _i("ASMA_TAVAN", "INC", "Asma tavan", "area", "tip (ALCIPAN / METAL / TASYUNU)", "KSF-INC-ASMA_TAVAN-TASYUNU"),
    _i("SUPURGELIK", "INC", "Süpürgelik", "length", "tip", "KSF-INC-SUPURGELIK-MDF"),
    _i("SAP", "INC", "Şap", "volume", "kalınlık (cm)", "KSF-INC-SAP-5"),
    # CEP
    _i("KOMPOZIT_PANEL", "CEP", "Kompozit cephe paneli", "area", "kalınlık / renk", "KSF-CEP-KOMPOZIT_PANEL-4MM"),
    _i("GIYDIRME_CEPHE", "CEP", "Giydirme cephe", "area", "sistem", "KSF-CEP-GIYDIRME_CEPHE"),
    _i("MANTOLAMA", "CEP", "Mantolama", "area", "malzeme + kalınlık (EPS_5)", "KSF-CEP-MANTOLAMA-EPS_5"),
    _i("CEPHE_TASI", "CEP", "Cephe taşı / kaplama", "area", "tip", "KSF-CEP-CEPHE_TASI"),
    _i("CEPHE_BOYA", "CEP", "Dış cephe boyası", "area", "tip", "KSF-CEP-CEPHE_BOYA"),
    # CAT
    _i("CATI_MEMBRAN", "CAT", "Çatı membranı", "area", "tip", "KSF-CAT-CATI_MEMBRAN-3MM"),
    _i("CATI_SANDVIC_PANEL", "CAT", "Sandviç panel", "area", "kalınlık (mm)", "KSF-CAT-CATI_SANDVIC_PANEL-50"),
    _i("CATI_KIREMIT", "CAT", "Kiremit / shingle", "area", "tip", "KSF-CAT-CATI_KIREMIT"),
    _i("CATI_OLUK", "CAT", "Oluk", "length", "tip", "KSF-CAT-CATI_OLUK-PVC"),
    _i("CATI_DERE", "CAT", "Dere / yağmur iniş borusu", "length", "çap (mm)", "KSF-CAT-CATI_DERE-100"),
    _i("CATI_ISIK_BANDI", "CAT", "Çatı ışıklık", "area", "tip", "KSF-CAT-CATI_ISIK_BANDI"),
    # IZO
    _i("XPS", "IZO", "XPS ısı yalıtımı", "area", "kalınlık (cm)", "KSF-IZO-XPS-5"),
    _i("EPS", "IZO", "EPS ısı yalıtımı", "area", "kalınlık (cm)", "KSF-IZO-EPS-5"),
    _i("TASYUNU", "IZO", "Taşyünü", "area", "kalınlık (cm)", "KSF-IZO-TASYUNU-5"),
    _i("SU_YALITIM_MEMBRAN", "IZO", "Su yalıtım membranı", "area", "tip (BITUMLU_3MM)", "KSF-IZO-SU_YALITIM_MEMBRAN-BITUMLU_3MM"),
    _i("SURME_IZOLASYON", "IZO", "Sürme izolasyon", "area", "tip", "KSF-IZO-SURME_IZOLASYON"),
    # ELK
    _i("KABLO", "ELK", "Kablo", "length", "tip + kesit (NYY_4x16)", "KSF-ELK-KABLO-NYY_4x16"),
    _i("TAVA", "ELK", "Kablo tavası", "length", "en x yükseklik (mm)", "KSF-ELK-TAVA-200x60"),
    _i("BUSBAR", "ELK", "Busbar", "length", "akım (A)", "KSF-ELK-BUSBAR-800A"),
    _i("BORU", "ELK", "Elektrik borusu", "length", "çap + tip (20_PVC)", "KSF-ELK-BORU-20_PVC"),
    _i("ARMATUR", "ELK", "Aydınlatma armatürü", "count", "tip", "KSF-ELK-ARMATUR-LED_PANEL_60x60"),
    _i("ACIL_AYDINLATMA", "ELK", "Acil aydınlatma / exit", "count", "tip", "KSF-ELK-ACIL_AYDINLATMA"),
    _i("PRIZ", "ELK", "Priz", "count", "tip", "KSF-ELK-PRIZ-TOPRAKLI"),
    _i("ANAHTAR", "ELK", "Anahtar", "count", "tip", "KSF-ELK-ANAHTAR-KOMUTATOR"),
    _i("PANO", "ELK", "Pano", "count", "tip", "KSF-ELK-PANO-KAT_PANOSU"),
    _i("TOPRAKLAMA", "ELK", "Topraklama şeridi / iletkeni", "length", "kesit", "KSF-ELK-TOPRAKLAMA-30x3.5"),
    # ZAY
    _i("DATA_KABLO", "ZAY", "Data kablosu", "length", "tip (CAT6A)", "KSF-ZAY-DATA_KABLO-CAT6A"),
    _i("DATA_PRIZ", "ZAY", "Data prizi", "count", "tip", "KSF-ZAY-DATA_PRIZ-2xRJ45"),
    _i("KAMERA", "ZAY", "Kamera", "count", "tip", "KSF-ZAY-KAMERA-DOME"),
    _i("YANGIN_DEDEKTOR", "ZAY", "Yangın dedektörü", "count", "tip (DUMAN / ISI)", "KSF-ZAY-YANGIN_DEDEKTOR-DUMAN"),
    _i("YANGIN_BUTON", "ZAY", "Yangın ihbar butonu / siren", "count", "tip", "KSF-ZAY-YANGIN_BUTON"),
    _i("HOPARLOR", "ZAY", "Anons hoparlörü", "count", "tip", "KSF-ZAY-HOPARLOR"),
    _i("KARTLI_GECIS", "ZAY", "Kartlı geçiş / turnike", "count", "tip", "KSF-ZAY-KARTLI_GECIS"),
    # MEK
    _i("BORU_CELIK", "MEK", "Çelik boru", "length", "çap (DN65)", "KSF-MEK-BORU_CELIK-DN65"),
    _i("BORU_BAKIR", "MEK", "Bakır boru", "length", "çap (mm)", "KSF-MEK-BORU_BAKIR-22"),
    _i("BORU_PPRC", "MEK", "PPRC boru", "length", "çap (mm)", "KSF-MEK-BORU_PPRC-32"),
    _i("BORU_IZOLASYON", "MEK", "Boru izolasyonu", "length", "kalınlık (mm)", "KSF-MEK-BORU_IZOLASYON-19"),
    _i("FANCOIL", "MEK", "Fancoil", "count", "kapasite", "KSF-MEK-FANCOIL-4KW"),
    _i("VRF_IC_UNITE", "MEK", "VRF iç ünite", "count", "kapasite", "KSF-MEK-VRF_IC_UNITE-5.6KW"),
    _i("VRF_DIS_UNITE", "MEK", "VRF dış ünite", "count", "kapasite", "KSF-MEK-VRF_DIS_UNITE-28KW"),
    _i("RADYATOR", "MEK", "Radyatör", "count", "ölçü", "KSF-MEK-RADYATOR-600x1000"),
    _i("VANA", "MEK", "Vana", "count", "çap / tip", "KSF-MEK-VANA-DN50_KURESEL"),
    _i("POMPA", "MEK", "Pompa", "count", "tip", "KSF-MEK-POMPA"),
    _i("KAZAN", "MEK", "Kazan / chiller / ısı pompası", "count", "kapasite", "KSF-MEK-KAZAN-500KW"),
    # HAV
    _i("HAVA_KANAL", "HAV", "Havalandırma kanalı (dikdörtgen)", "length", "en x yükseklik (mm)", "KSF-HAV-HAVA_KANAL-600x400"),
    _i("HAVA_KANAL_YUVARLAK", "HAV", "Havalandırma kanalı (yuvarlak)", "length", "çap (mm)", "KSF-HAV-HAVA_KANAL_YUVARLAK-315"),
    _i("FLEX_KANAL", "HAV", "Flex kanal", "length", "çap (mm)", "KSF-HAV-FLEX_KANAL-200"),
    _i("KANAL_IZOLASYON", "HAV", "Kanal izolasyonu", "length", "kalınlık (mm)", "KSF-HAV-KANAL_IZOLASYON-25"),
    _i("MENFEZ", "HAV", "Menfez / difüzör", "count", "ölçü", "KSF-HAV-MENFEZ-600x600"),
    _i("DAMPER", "HAV", "Damper", "count", "tip / ölçü", "KSF-HAV-DAMPER-YANGIN_400x400"),
    _i("FAN", "HAV", "Fan / aspiratör", "count", "debi (m3/h)", "KSF-HAV-FAN-5000"),
    _i("KLIMA_SANTRALI", "HAV", "Klima santrali", "count", "debi (m3/h)", "KSF-HAV-KLIMA_SANTRALI-20000"),
    # YAN
    _i("SPRINKLER", "YAN", "Sprinkler", "count", "tip (K80_UST)", "KSF-YAN-SPRINKLER-K80_UST"),
    _i("YANGIN_BORU", "YAN", "Yangın borusu (çelik)", "length", "çap (DN)", "KSF-YAN-YANGIN_BORU-DN100"),
    _i("YANGIN_DOLABI", "YAN", "Yangın dolabı", "count", "tip", "KSF-YAN-YANGIN_DOLABI"),
    _i("YANGIN_VANA", "YAN", "Yangın vanası / zon vanası", "count", "çap", "KSF-YAN-YANGIN_VANA-DN100"),
    _i("YANGIN_POMPA", "YAN", "Yangın pompası", "count", "tip", "KSF-YAN-YANGIN_POMPA"),
    _i("SONDURME_TUPU", "YAN", "Söndürme tüpü", "count", "kg / tip", "KSF-YAN-SONDURME_TUPU-6KG"),
    # SIH
    _i("BORU_PVC", "SIH", "PVC pis su borusu", "length", "çap (mm)", "KSF-SIH-BORU_PVC-100"),
    _i("BORU_PPRC_TEMIZ", "SIH", "PPRC temiz su borusu", "length", "çap (mm)", "KSF-SIH-BORU_PPRC_TEMIZ-25"),
    _i("BORU_PE", "SIH", "PE boru", "length", "çap (mm)", "KSF-SIH-BORU_PE-63"),
    _i("LAVABO", "SIH", "Lavabo", "count", "tip", "KSF-SIH-LAVABO"),
    _i("KLOZET", "SIH", "Klozet", "count", "tip", "KSF-SIH-KLOZET-ASMA"),
    _i("PISUAR", "SIH", "Pisuvar", "count", "tip", "KSF-SIH-PISUAR"),
    _i("BATARYA", "SIH", "Batarya", "count", "tip", "KSF-SIH-BATARYA-LAVABO"),
    _i("YER_SUZGECI", "SIH", "Yer süzgeci", "count", "tip", "KSF-SIH-YER_SUZGECI"),
    _i("HIDROFOR", "SIH", "Hidrofor", "count", "tip", "KSF-SIH-HIDROFOR"),
    _i("SU_DEPOSU", "SIH", "Su deposu", "count", "hacim (m3)", "KSF-SIH-SU_DEPOSU-50"),
    # ALT
    _i("BORU_KORUGE", "ALT", "Koruge boru", "length", "çap (mm)", "KSF-ALT-BORU_KORUGE-300"),
    _i("BORU_BETON", "ALT", "Beton boru", "length", "çap (mm)", "KSF-ALT-BORU_BETON-600"),
    _i("BACA", "ALT", "Muayene bacası / rögar", "count", "tip", "KSF-ALT-BACA-1000"),
    _i("YAGMUR_IZGARA", "ALT", "Yağmur ızgarası", "length", "tip", "KSF-ALT-YAGMUR_IZGARA"),
    _i("BORDUR", "ALT", "Bordür", "length", "tip", "KSF-ALT-BORDUR-BETON"),
    _i("PARKE_TAS", "ALT", "Parke taşı / kilit taşı", "area", "tip", "KSF-ALT-PARKE_TAS-8CM"),
    _i("ASFALT", "ALT", "Asfalt", "area", "kalınlık (cm)", "KSF-ALT-ASFALT-5"),
    _i("SAHA_BETONU", "ALT", "Saha betonu", "volume", "kalınlık (cm)", "KSF-ALT-SAHA_BETONU-15"),
    _i("ISTINAT", "ALT", "İstinat duvarı", "length", "tip", "KSF-ALT-ISTINAT"),
    _i("AYDINLATMA_DIREGI", "ALT", "Aydınlatma direği", "count", "boy (m)", "KSF-ALT-AYDINLATMA_DIREGI-8"),
    # PEY
    _i("CIM", "PEY", "Çim", "area", "tip (RULO / TOHUM)", "KSF-PEY-CIM-RULO"),
    _i("AGAC", "PEY", "Ağaç", "count", "tür / çap", "KSF-PEY-AGAC-CINAR"),
    _i("CALI", "PEY", "Çalı / bitki", "count", "tür", "KSF-PEY-CALI"),
    _i("BITKI_TOPRAGI", "PEY", "Bitki toprağı", "volume", "kalınlık (cm)", "KSF-PEY-BITKI_TOPRAGI-30"),
    _i("SULAMA_BORU", "PEY", "Sulama borusu", "length", "çap (mm)", "KSF-PEY-SULAMA_BORU-32"),
    _i("SULAMA_BASLIK", "PEY", "Sulama başlığı", "count", "tip", "KSF-PEY-SULAMA_BASLIK"),
    _i("BANK", "PEY", "Bank / kent mobilyası", "count", "tip", "KSF-PEY-BANK"),
    _i("PEYZAJ_DOSEME", "PEY", "Peyzaj döşemesi", "area", "tip", "KSF-PEY-PEYZAJ_DOSEME-GRANIT"),
    # ASN
    _i("ASANSOR", "ASN", "Asansör", "count", "kapasite / durak", "KSF-ASN-ASANSOR-1000KG_5D"),
    _i("YURUYEN_MERDIVEN", "ASN", "Yürüyen merdiven", "count", "yükseklik (m)", "KSF-ASN-YURUYEN_MERDIVEN-4.5"),
]


class Catalog:
    def __init__(self, disciplines: dict[str, str] | None = None, items: list[CatalogItem] | None = None):
        self.disciplines: dict[str, str] = dict(disciplines if disciplines is not None else DEFAULT_DISCIPLINES)
        self.items: dict[str, CatalogItem] = {}
        for it in (items if items is not None else DEFAULT_ITEMS):
            self.items[it.code] = it

    # ---------- erişim
    def get(self, code: str) -> CatalogItem | None:
        return self.items.get(normalize_code(code))

    def discipline_name(self, code: str) -> str:
        return self.disciplines.get(code.upper(), code.upper())

    def by_discipline(self) -> list[dict]:
        out = []
        for code, name in self.disciplines.items():
            out.append({"code": code, "name": name,
                        "items": [it.to_dict() for it in self.items.values() if it.discipline == code]})
        return out

    def to_dict(self) -> dict:
        return {"disciplines": self.disciplines, "items": [it.to_dict() for it in self.items.values()],
                "measures": {k: {"label": v[0], "unit": v[1]} for k, v in MEASURES.items()},
                "by_discipline": self.by_discipline()}

    # ---------- değişiklik
    def upsert_item(self, data: dict) -> CatalogItem:
        it = CatalogItem(code=data["code"], discipline=data["discipline"], name=data["name"], measure=data["measure"],
                         unit=data.get("unit") or "", spec_label=data.get("spec_label") or "", example=data.get("example") or "",
                         custom=True)
        if it.discipline not in self.disciplines:
            raise ValueError(f"Bilinmeyen disiplin kodu: {it.discipline}")
        self.items[it.code] = it
        return it

    def remove_item(self, code: str) -> bool:
        return self.items.pop(normalize_code(code), None) is not None

    def upsert_discipline(self, code: str, name: str) -> None:
        code = normalize_code(code)[:3]
        if len(code) != 3:
            raise ValueError("Disiplin kodu 3 harf olmalı (ör. HAV)")
        self.disciplines[code] = name.strip()

    # ---------- kalıcılık: yalnızca varsayılandan farklar
    def overrides(self) -> dict:
        defaults = {it.code: it for it in DEFAULT_ITEMS}
        items = [asdict(it) for it in self.items.values() if it.code not in defaults or asdict(it) != asdict(defaults[it.code])]
        removed = [c for c in defaults if c not in self.items]
        discs = {k: v for k, v in self.disciplines.items() if DEFAULT_DISCIPLINES.get(k) != v}
        return {"items": items, "removed": removed, "disciplines": discs}

    @classmethod
    def from_overrides(cls, data: dict | None) -> "Catalog":
        cat = cls()
        data = data or {}
        for k, v in (data.get("disciplines") or {}).items():
            cat.disciplines[k] = v
        for c in data.get("removed") or []:
            cat.items.pop(c, None)
        for d in data.get("items") or []:
            d = {k: v for k, v in d.items() if k in {"code", "discipline", "name", "measure", "unit", "spec_label", "example", "custom"}}
            it = CatalogItem(**d)
            cat.items[it.code] = it
        return cat

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.overrides(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        if path.exists():
            try:
                return cls.from_overrides(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return cls()


# ---------------------------------------------------------------- katman adı

LAYER_RE = re.compile(r"^\s*KSF[-_](?P<disc>[A-Za-z]{3})-(?P<code>[A-Za-z0-9_]+?)(?:-(?P<spec>.+))?\s*$", re.IGNORECASE)


@dataclass
class ParsedLayer:
    discipline: str
    code: str
    spec: str | None
    item: CatalogItem | None
    layer: str

    @property
    def known(self) -> bool:
        return self.item is not None


def parse_layer(layer: str, catalog: Catalog) -> ParsedLayer | None:
    """'KSF-HAV-HAVA_KANAL-600x400' -> ParsedLayer; standart dışı katman -> None."""
    m = LAYER_RE.match(layer)
    if not m:
        return None
    disc = m.group("disc").upper()
    code = normalize_code(m.group("code"))
    spec = (m.group("spec") or "").strip() or None
    item = catalog.get(code)
    if item is not None and item.discipline != disc:
        # kod başka disiplinde kayıtlı; katmandaki disiplin kodu esas alınır ama kalem tanımı kullanılır
        pass
    return ParsedLayer(disc, code, spec, item, layer)


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def spec_numbers(spec: str | None) -> list[float]:
    """'20x300' -> [20, 300]; 'DN65' -> [65]; 'NYY_4x16' -> [4, 16]."""
    if not spec:
        return []
    return [float(x.replace(",", ".")) for x in _NUM.findall(spec)]
