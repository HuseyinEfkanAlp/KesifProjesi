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

# Reçete çarpanının ayrıca çarpıldığı büyüklük: H kat yüksekliği; PER / WID / AREA boşluğun (kapı, pencere, doğrama)
# toplam çevresi (m) / genişliği (m) / alanı (m²) — adet yerine bunlar esas alınır (fitil, pervaz, denizlik, cam).
TIMES: dict[str, str] = {"H": "× kat yüksekliği", "PER": "× boşluk çevresi (adet yerine)", "WID": "× boşluk genişliği (adet yerine)",
                         "AREA": "× boşluk alanı (adet yerine)"}

MEASURES: dict[str, tuple[str, str]] = {
    "count": ("Adet (blok sayımı)", "adet"),
    "length": ("Uzunluk (çizgi)", "m"),
    "area": ("Alan (kapalı çokgen / tarama)", "m²"),
    "wall_area": ("Duvar alanı (uzunluk × yükseklik)", "m²"),
    "volume": ("Hacim (alan × kalınlık)", "m³"),
    "label_count": ("Etiket sayımı (katmandaki yazılar, her kod ayrı kalem)", "adet"),
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
    poz: str = ""             # ÇŞB birim fiyat poz numarası (ör. 15.225.1010); boşsa rules.default_poz denenir
    # Katmanlı sistem: bu kalem ölçüldüğünde (ör. çatı alanı) ayrı iş kalemi olarak yazılacak bileşenler.
    # [{"code": "OSB", "factor": 1.0, "spec": "11"}]: miktar = sistem miktarı × factor; spec varsayılan özellik.
    # Sistem bileşenleri kullanıcıya sorulur (projede yazıyor / yok).
    components: list[dict] = field(default_factory=list)
    # Reçete: bu kalem keşfe girdiğinde kendiliğinden yazılan alt işler (sarf, yardımcı imalat, işçilik): iskele, ankraj,
    # kaynak, tij / somun / pul, montaj saati… Aynı biçim; "times": "H" ise çarpan ayrıca kat yüksekliğiyle çarpılır
    # (kalıp iskelesi m³ = kalıp m² × H). Sorulmaz, "reçete varsayılanı" notuyla yazılır; katalogdan düzenlenir.
    recipe: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.code = normalize_code(self.code)
        self.discipline = self.discipline.upper()
        if self.measure not in MEASURES:
            raise ValueError(f"Geçersiz ölçüm kuralı: {self.measure}")
        if not self.unit:
            self.unit = MEASURES[self.measure][1]
        if not self.example:
            self.example = f"KSF-{self.discipline}-{self.code}"
        self.components = normalize_components(self.components)
        self.recipe = normalize_components(self.recipe)

    @property
    def is_system(self) -> bool:
        return bool(self.components)

    @property
    def has_recipe(self) -> bool:
        return bool(self.recipe)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["measure_label"] = MEASURES[self.measure][0]
        d["is_system"] = self.is_system
        d["has_recipe"] = self.has_recipe
        return d


def normalize_components(comps) -> list[dict]:
    """Bileşen listesini temizler: kod normalize, factor float (>0), spec metin. Metin biçimi de kabul edilir:
    'OSB×1; TASYUNU×1:5; MERTEK×1.6' (kod × çarpan [: özellik])."""
    if not comps:
        return []
    if isinstance(comps, str):
        parsed = []
        for part in re.split(r"[;\n]+", comps):
            part = part.strip()
            if not part:
                continue
            m = re.match(r"^([^×x*:]+?)\s*(?:[×x*]\s*([0-9.,]+)([HPWA])?)?\s*(?::\s*(.+))?$", part)
            if not m:
                continue
            parsed.append({"code": m.group(1), "factor": m.group(2) or 1, "spec": (m.group(4) or "").strip(),
                           "times": {"H": "H", "P": "PER", "W": "WID", "A": "AREA"}.get(m.group(3) or "", "")})
        comps = parsed
    out: list[dict] = []
    seen: set[str] = set()
    for c in comps:
        if not isinstance(c, dict) or not c.get("code"):
            continue
        code = normalize_code(str(c["code"]))
        if not code or code in seen:
            continue
        try:
            factor = float(str(c.get("factor", 1)).replace(",", "."))
        except ValueError:
            factor = 1.0
        if factor <= 0:
            continue
        seen.add(code)
        row = {"code": code, "factor": factor, "spec": str(c.get("spec") or "").strip()}
        times = str(c.get("times") or "").upper()
        if times in TIMES:
            row["times"] = times
        when = str(c.get("when") or "").lower()
        if when in ("window", "door"):
            row["when"] = when
        out.append(row)
    return out


def normalize_code(code: str) -> str:
    c = code.strip().replace("ı", "i").replace("İ", "I").replace("ş", "s").replace("Ş", "S").replace("ğ", "g").replace("Ğ", "G")
    c = c.replace("ç", "c").replace("Ç", "C").replace("ö", "o").replace("Ö", "O").replace("ü", "u").replace("Ü", "U")
    c = re.sub(r"[^A-Za-z0-9]+", "_", c).strip("_").upper()
    return c


def _i(code, disc, name, measure, spec_label="", example="", components=None, unit="", recipe=None, poz=""):
    return CatalogItem(code, disc, name, measure, unit=unit, spec_label=spec_label, example=example,
                       components=components or [], recipe=recipe or [], poz=poz)


def _c(code, factor=1.0, spec="", times="", when=""):
    return {"code": code, "factor": factor, "spec": spec, "times": times, "when": when}


DEFAULT_ITEMS: list[CatalogItem] = [
    # STA
    _i("BETON", "STA", "Beton (alan × kalınlık)", "volume", "kalınlık (cm)", "KSF-STA-BETON-20"),
    _i("GROBETON", "STA", "Grobeton", "volume", "kalınlık (cm)", "KSF-STA-GROBETON-10"),
    _i("DOLGU", "STA", "Dolgu / blokaj", "volume", "kalınlık (cm)", "KSF-STA-DOLGU-30"),
    _i("KAZI", "STA", "Kazı", "volume", "derinlik (cm)", "KSF-STA-KAZI-350"),
    _i("KALIP", "STA", "Kalıp", "area", "", "KSF-STA-KALIP", recipe=[_c("KALIP_ISKELESI", 1.0, "", "H")]),
    _i("KALIP_ISKELESI", "STA", "Kalıp iskelesi (çelik boru)", "volume", "", "KSF-STA-KALIP_ISKELESI", unit="m³", poz="15.185.1006"),
    _i("BETON_POMPAJ", "STA", "Beton pompajı / yerleştirme", "volume", "", "KSF-STA-BETON_POMPAJ", unit="m³"),
    _i("CELIK_PROFIL", "STA", "Çelik profil", "length", "profil (HEA200)", "KSF-STA-CELIK_PROFIL-HEA200"),
    _i("HASIR_CELIK", "STA", "Hasır çelik", "area", "tip (Q221)", "KSF-STA-HASIR_CELIK-Q221"),
    # STA — çelik konstrüksiyon reçetesi (kg başına): ankraj, tij / somun / pul, kaynak, antipas + boya, montaj, vinç
    _i("CELIK_KONSTRUKSIYON", "STA", "Çelik konstrüksiyon (imalat + montaj)", "count", "profil sınıfı (S235 / S275)", "KSF-STA-CELIK_KONSTRUKSIYON-S275",
       unit="kg", recipe=[_c("ANKRAJ_BULONU", 0.01, "M20"), _c("KAYNAK", 0.04), _c("ANTIPAS", 0.02), _c("CELIK_BOYA", 0.02),
                          _c("CELIK_MONTAJ", 0.03), _c("VINC", 0.004)]),
    _i("ANKRAJ_BULONU", "STA", "Ankraj bulonu / kimyasal ankraj", "count", "çap (M20)", "KSF-STA-ANKRAJ_BULONU-M20",
       recipe=[_c("TIJ", 1.0, "M20"), _c("SOMUN", 2.0, "M20"), _c("PUL", 2.0, "M20")]),
    _i("TIJ", "STA", "Tij (dişli çubuk)", "count", "çap (M20)", "KSF-STA-TIJ-M20"),
    _i("SOMUN", "STA", "Somun", "count", "çap (M20)", "KSF-STA-SOMUN-M20"),
    _i("PUL", "STA", "Pul / rondela", "count", "çap (M20)", "KSF-STA-PUL-M20"),
    _i("KAYNAK", "STA", "Kaynak (köşe / küt)", "length", "tip", "KSF-STA-KAYNAK"),
    _i("ANTIPAS", "STA", "Antipas astar (çelik yüzey)", "area", "tip", "KSF-STA-ANTIPAS"),
    _i("CELIK_BOYA", "STA", "Çelik son kat boya", "area", "tip", "KSF-STA-CELIK_BOYA"),
    _i("CELIK_MONTAJ", "STA", "Çelik montaj işçiliği", "count", "", "KSF-STA-CELIK_MONTAJ", unit="saat"),
    _i("VINC", "STA", "Vinç (mobil / kule)", "count", "kapasite (ton)", "KSF-STA-VINC", unit="saat"),
    _i("IS_ISKELESI", "STA", "İş iskelesi (cephe / dış)", "area", "tip (CELIK_BORU)", "KSF-STA-IS_ISKELESI", unit="m²"),
    # MIM
    _i("DUVAR_YTONG", "MIM", "Ytong / gazbeton duvar", "wall_area", "kalınlık (cm) [x yükseklik (cm)]", "KSF-MIM-DUVAR_YTONG-20"),
    _i("DUVAR_TUGLA", "MIM", "Tuğla duvar", "wall_area", "kalınlık (cm)", "KSF-MIM-DUVAR_TUGLA-13.5"),
    _i("DUVAR_BIMS", "MIM", "Bims duvar", "wall_area", "kalınlık (cm)", "KSF-MIM-DUVAR_BIMS-19"),
    _i("DUVAR_ALCIPAN", "MIM", "Alçıpan bölme duvar", "wall_area", "sistem (2x12.5)", "KSF-MIM-DUVAR_ALCIPAN-2x12.5"),
    _i("KAPI", "MIM", "Kapı", "count", "tip / ölçü (90x210)", "KSF-MIM-KAPI-K1_90x210",
       recipe=[_c("LENTO", 1.0), _c("DOGRAMA_MONTAJ", 1.5), _c("MONTAJ_KOPUGU", 1.0)]),
    _i("PENCERE", "MIM", "Pencere", "count", "tip / ölçü (120x140)", "KSF-MIM-PENCERE-P1_120x140",
       recipe=[_c("LENTO", 1.0), _c("DOGRAMA_MONTAJ", 1.0), _c("MONTAJ_KOPUGU", 1.0)]),
    _i("LENTO", "MIM", "Lento (kapı / pencere üstü)", "count", "tip (PREFABRIK / YERINDE)", "KSF-MIM-LENTO"),
    # doğrama alt işleri: körkasa, cam takma / izolasyon, kapı aksesuarları
    _i("KORKASA", "MIM", "Körkasa (galvaniz / ahşap)", "count", "tip", "KSF-MIM-KORKASA"),
    _i("KORKASA_MONTAJ", "MIM", "Körkasa montaj işçiliği", "count", "", "KSF-MIM-KORKASA_MONTAJ", unit="saat"),
    _i("DUBEL_VIDA", "MIM", "Dübel + vida (doğrama sabitleme)", "count", "", "KSF-MIM-DUBEL_VIDA"),
    _i("CAM_FITIL", "MIM", "Cam fitili / EPDM conta", "length", "", "KSF-MIM-CAM_FITIL"),
    _i("SILIKON", "MIM", "Silikon (cam / kasa derzi)", "length", "", "KSF-MIM-SILIKON"),
    _i("MASTIK", "MIM", "Dış mastik (kasa - duvar derzi)", "length", "", "KSF-MIM-MASTIK"),
    _i("KAPI_KASASI", "MIM", "Kapı kasası", "count", "tip", "KSF-MIM-KAPI_KASASI"),
    _i("PERVAZ", "MIM", "Pervaz", "length", "tip", "KSF-MIM-PERVAZ"),
    _i("MENTESE", "MIM", "Menteşe", "count", "", "KSF-MIM-MENTESE"),
    _i("KILIT", "MIM", "Kilit + silindir", "count", "tip", "KSF-MIM-KILIT"),
    _i("KAPI_KOLU", "MIM", "Kapı kolu", "count", "tip", "KSF-MIM-KAPI_KOLU"),
    _i("STOPER", "MIM", "Kapı stoperi", "count", "", "KSF-MIM-STOPER"),
    _i("ESIK", "MIM", "Eşik", "length", "tip", "KSF-MIM-ESIK"),
    _i("DOGRAMA_MONTAJ", "MIM", "Doğrama montaj işçiliği", "count", "", "KSF-MIM-DOGRAMA_MONTAJ", unit="saat"),
    _i("MONTAJ_KOPUGU", "MIM", "Montaj köpüğü", "count", "", "KSF-MIM-MONTAJ_KOPUGU", unit="tüp"),
    _i("DUVAR_TUTKAL", "MIM", "Gazbeton tutkalı", "count", "", "KSF-MIM-DUVAR_TUTKAL", unit="kg"),
    _i("CAM", "MIM", "Cam", "area", "tip (4+16+4)", "KSF-MIM-CAM-4+16+4"),
    _i("KOREKUYU", "MIM", "Korkuluk", "length", "tip", "KSF-MIM-KOREKUYU-CAM"),
    _i("DOGRAMA", "MIM", "Doğrama (poz listesinden)", "count", "poz (EMP1)", "KSF-MIM-DOGRAMA-EMP1",
       recipe=[_c("LENTO", 1.0), _c("DOGRAMA_MONTAJ", 1.5), _c("MONTAJ_KOPUGU", 1.0)]),
    # INC
    _i("SIVA", "INC", "Sıva", "wall_area", "tip (ALCI / CIMENTO)", "KSF-INC-SIVA-ALCI"),
    _i("BOYA", "INC", "Boya", "wall_area", "tip", "KSF-INC-BOYA-PLASTIK"),
    _i("SERAMIK_ZEMIN", "INC", "Zemin seramiği", "area", "ebat (60x60)", "KSF-INC-SERAMIK_ZEMIN-60x60"),
    _i("SERAMIK_DUVAR", "INC", "Duvar seramiği", "wall_area", "ebat", "KSF-INC-SERAMIK_DUVAR-30x60"),
    _i("LAMINAT", "INC", "Laminat parke", "area", "tip", "KSF-INC-LAMINAT-8MM"),
    _i("ASMA_TAVAN", "INC", "Asma tavan", "area", "tip (ALCIPAN / METAL / TASYUNU)", "KSF-INC-ASMA_TAVAN-TASYUNU"),
    _i("SUPURGELIK", "INC", "Süpürgelik", "length", "tip", "KSF-INC-SUPURGELIK-MDF"),
    _i("SAP", "INC", "Şap", "volume", "kalınlık (cm)", "KSF-INC-SAP-5"),
    _i("ASTAR", "INC", "Boya astarı", "wall_area", "tip", "KSF-INC-ASTAR"),
    _i("DOSEME_KAPLAMA", "INC", "Döşeme kaplaması (tip seçilecek)", "area", "tip (SERAMIK / PARKE / EPOKSI)", "KSF-INC-DOSEME_KAPLAMA-SERAMIK"),
    _i("TAVAN_SIVA_BOYA", "INC", "Tavan sıva + astar + boya", "area", "tip", "KSF-INC-TAVAN_SIVA_BOYA"),
    _i("TEMEL_SU_YALITIMI", "IZO", "Temel su yalıtımı (bitümlü membran / sürme)", "area", "tip", "KSF-IZO-TEMEL_SU_YALITIMI"),
    _i("KORUMA_SAPI", "IZO", "Koruma şapı (temel yalıtımı üstü)", "area", "kalınlık (cm)", "KSF-IZO-KORUMA_SAPI-5"),
    _i("DRENAJ", "IZO", "Drenaj levhası / drenaj borusu", "area", "tip", "KSF-IZO-DRENAJ"),
    # CEP
    _i("KOMPOZIT_PANEL", "CEP", "Kompozit cephe paneli", "area", "kalınlık / renk", "KSF-CEP-KOMPOZIT_PANEL-4MM",
       recipe=[_c("IS_ISKELESI", 1.0), _c("CEPHE_TASIYICI_PROFIL", 2.5, "ALU"), _c("ANKRAJ_BULONU", 1.5, "M10")]),
    _i("GIYDIRME_CEPHE", "CEP", "Giydirme cephe", "area", "sistem", "KSF-CEP-GIYDIRME_CEPHE",
       recipe=[_c("IS_ISKELESI", 1.0), _c("ANKRAJ_BULONU", 1.2, "M12"), _c("VINC", 0.05)]),
    _i("MANTOLAMA", "CEP", "Mantolama", "area", "malzeme + kalınlık (EPS_5)", "KSF-CEP-MANTOLAMA-EPS_5", recipe=[_c("IS_ISKELESI", 1.0)]),
    _i("CEPHE_TASI", "CEP", "Cephe taşı / kaplama", "area", "tip", "KSF-CEP-CEPHE_TASI", recipe=[_c("IS_ISKELESI", 1.0)]),
    _i("CEPHE_BOYA", "CEP", "Dış cephe boyası", "area", "tip", "KSF-CEP-CEPHE_BOYA", recipe=[_c("IS_ISKELESI", 1.0)]),
    _i("CEPHE_TASIYICI_PROFIL", "CEP", "Cephe taşıyıcı profil (alt konstrüksiyon)", "length", "malzeme (ALU / GALVANIZ)", "KSF-CEP-CEPHE_TASIYICI_PROFIL-ALU"),
    # CEP — mantolama sistemi bileşenleri
    _i("MANTOLAMA_YAPISTIRICI", "CEP", "Mantolama yapıştırıcısı", "area", "", "KSF-CEP-MANTOLAMA_YAPISTIRICI"),
    _i("MANTOLAMA_DUBEL", "CEP", "Mantolama dübeli", "count", "boy (mm)", "KSF-CEP-MANTOLAMA_DUBEL-120"),
    _i("MANTOLAMA_FILE", "CEP", "Sıva filesi (donatı filesi)", "area", "gramaj", "KSF-CEP-MANTOLAMA_FILE-160"),
    _i("MANTOLAMA_SIVA", "CEP", "Mantolama sıvası (file sıvası + dekoratif sıva)", "area", "tip", "KSF-CEP-MANTOLAMA_SIVA"),
    _i("KOSE_PROFILI", "CEP", "Köşe / subasman profili", "length", "tip", "KSF-CEP-KOSE_PROFILI"),
    _i("SOVE", "CEP", "Söve", "length", "tip / en (cm)", "KSF-CEP-SOVE-15"),
    _i("SILME", "CEP", "Silme / kat silmesi", "length", "tip", "KSF-CEP-SILME"),
    _i("DENIZLIK", "CEP", "Denizlik", "length", "tip (MERMER / ALU)", "KSF-CEP-DENIZLIK-MERMER"),
    _i("PREKAST_PANEL", "CEP", "Prekast cephe paneli (etiket kodu bazında)", "label_count", "panel kodu (GP-4 / EP17)", "KSF-CEP-PREKAST_PANEL",
       recipe=[_c("ANKRAJ_BULONU", 4.0, "M20"), _c("KAYNAK", 1.2), _c("PREKAST_MONTAJ", 2.0), _c("VINC", 0.5), _c("PANEL_DERZ", 6.0)]),
    _i("PREKAST_MONTAJ", "CEP", "Prekast panel montaj işçiliği", "count", "", "KSF-CEP-PREKAST_MONTAJ", unit="saat"),
    _i("PANEL_DERZ", "CEP", "Panel derz dolgusu (mastik + fitil)", "length", "tip", "KSF-CEP-PANEL_DERZ"),
    _i("CEPHE_BRUT", "CEP", "Cephe brüt alanı (görünüş dış hattı)", "area", "cephe adı (ON / ARKA)", "KSF-CEP-CEPHE_BRUT-ON"),
    _i("MANTOLAMA_SISTEM", "CEP", "Mantolama sistemi (katmanlı)", "area", "yalıtım + kalınlık (EPS_5)",
       "KSF-CEP-MANTOLAMA_SISTEM-EPS_5",
       [_c("EPS", 1.0, "5"), _c("MANTOLAMA_YAPISTIRICI"), _c("MANTOLAMA_DUBEL", 6.0, "120"), _c("MANTOLAMA_FILE"),
        _c("MANTOLAMA_SIVA"), _c("CEPHE_BOYA"), _c("KOSE_PROFILI", 0.3)], recipe=[_c("IS_ISKELESI", 1.0)]),
    # CAT
    _i("CATI_MEMBRAN", "CAT", "Çatı membranı", "area", "tip", "KSF-CAT-CATI_MEMBRAN-3MM"),
    _i("CATI_SANDVIC_PANEL", "CAT", "Sandviç panel", "area", "kalınlık (mm)", "KSF-CAT-CATI_SANDVIC_PANEL-50",
       recipe=[_c("PANEL_VIDASI", 6.0), _c("MAHYA_KAPAMA", 0.15), _c("PANEL_MONTAJ", 0.25)]),
    _i("PANEL_VIDASI", "CAT", "Panel vidası (matkap uçlu, contalı)", "count", "", "KSF-CAT-PANEL_VIDASI"),
    _i("MAHYA_KAPAMA", "CAT", "Mahya / kenar kapama sacı", "length", "tip", "KSF-CAT-MAHYA_KAPAMA"),
    _i("PANEL_MONTAJ", "CAT", "Panel montaj işçiliği", "count", "", "KSF-CAT-PANEL_MONTAJ", unit="saat"),
    # CAT — çelik çatı sistemi (m² çatı alanı): çelik konstrüksiyon kg/m² reçetesi zincirleme açılır
    _i("CELIK_CATI", "CAT", "Çelik çatı sistemi (katmanlı)", "area", "kaplama (SANDVIC_PANEL / TRAPEZ)", "KSF-CAT-CELIK_CATI-SANDVIC_PANEL",
       [_c("CELIK_KONSTRUKSIYON", 25.0, "S275"), _c("ASIK", 1.6, "C120"), _c("CATI_SANDVIC_PANEL", 1.05, "50"),
        _c("CATI_OLUK", 0.12), _c("CATI_DERE", 0.05, "100")]),
    _i("CATI_KIREMIT", "CAT", "Kiremit / shingle", "area", "tip", "KSF-CAT-CATI_KIREMIT"),
    _i("CATI_OLUK", "CAT", "Oluk", "length", "tip", "KSF-CAT-CATI_OLUK-PVC"),
    _i("CATI_DERE", "CAT", "Dere / yağmur iniş borusu", "length", "çap (mm)", "KSF-CAT-CATI_DERE-100"),
    _i("CATI_ISIK_BANDI", "CAT", "Çatı ışıklık", "area", "tip", "KSF-CAT-CATI_ISIK_BANDI"),
    # CAT — katmanlı çatı sistemleri ve bileşenleri
    _i("KENET_KAPLAMA", "CAT", "Kenet çatı kaplaması (metal)", "area", "malzeme (TITANYUM_CINKO / ALU / GALVANIZ)", "KSF-CAT-KENET_KAPLAMA-ALU"),
    _i("AYIRICI_KECE", "CAT", "Ayırıcı keçe / yapısal mat", "area", "tip", "KSF-CAT-AYIRICI_KECE"),
    _i("OSB", "CAT", "OSB levha", "area", "kalınlık (mm)", "KSF-CAT-OSB-11"),
    _i("CATI_TAHTASI", "CAT", "Çatı tahtası / ahşap kaplama", "area", "kalınlık (mm)", "KSF-CAT-CATI_TAHTASI-22"),
    _i("MERTEK", "CAT", "Mertek (ahşap)", "length", "kesit (5x10)", "KSF-CAT-MERTEK-5x10"),
    _i("ASIK", "CAT", "Aşık (ahşap / çelik)", "length", "kesit", "KSF-CAT-ASIK-10x10"),
    _i("CATI_LATA", "CAT", "Lata / kontrlata", "length", "kesit", "KSF-CAT-CATI_LATA-3x5"),
    _i("EGIM_BETONU", "CAT", "Eğim betonu / eğim şapı", "area", "ort. kalınlık (cm)", "KSF-CAT-EGIM_BETONU-8"),
    _i("CATI_CAKIL", "CAT", "Çakıl / balast", "area", "kalınlık (cm)", "KSF-CAT-CATI_CAKIL-5"),
    _i("KORUMA_BETONU", "CAT", "Koruma betonu / koruma şapı", "area", "kalınlık (cm)", "KSF-CAT-KORUMA_BETONU-5"),
    _i("KENET_CATI", "CAT", "Kenet çatı sistemi (katmanlı)", "area", "kaplama malzemesi", "KSF-CAT-KENET_CATI-ALU",
       [_c("KENET_KAPLAMA"), _c("AYIRICI_KECE"), _c("OSB", 1.0, "11"), _c("SU_YALITIM_MEMBRAN", 1.0, "NEFES_ALAN"),
        _c("TASYUNU", 1.0, "10"), _c("BUHAR_KESICI"), _c("MERTEK", 1.7, "5x10"), _c("ASIK", 0.8)]),
    _i("KIREMIT_CATI", "CAT", "Kiremit çatı sistemi (katmanlı)", "area", "kiremit tipi", "KSF-CAT-KIREMIT_CATI-MARSILYA",
       [_c("CATI_KIREMIT"), _c("CATI_LATA", 3.0, "3x5"), _c("SU_YALITIM_MEMBRAN", 1.0, "NEFES_ALAN"), _c("OSB", 1.0, "11"),
        _c("TASYUNU", 1.0, "10"), _c("BUHAR_KESICI"), _c("MERTEK", 1.7, "5x10"), _c("ASIK", 0.8)]),
    _i("TERAS_CATI", "CAT", "Teras çatı sistemi (katmanlı)", "area", "tip (GEZILEN / GEZILMEYEN)", "KSF-CAT-TERAS_CATI-GEZILMEYEN",
       [_c("EGIM_BETONU", 1.0, "8"), _c("BUHAR_KESICI"), _c("XPS", 1.0, "8"), _c("SU_YALITIM_MEMBRAN", 1.0, "BITUMLU_3MM"),
        _c("GEOTEKSTIL"), _c("CATI_CAKIL", 1.0, "5"), _c("KORUMA_BETONU", 1.0, "5")]),
    # IZO
    _i("XPS", "IZO", "XPS ısı yalıtımı", "area", "kalınlık (cm)", "KSF-IZO-XPS-5"),
    _i("EPS", "IZO", "EPS ısı yalıtımı", "area", "kalınlık (cm)", "KSF-IZO-EPS-5"),
    _i("TASYUNU", "IZO", "Taşyünü", "area", "kalınlık (cm)", "KSF-IZO-TASYUNU-5"),
    _i("SU_YALITIM_MEMBRAN", "IZO", "Su yalıtım membranı", "area", "tip (BITUMLU_3MM)", "KSF-IZO-SU_YALITIM_MEMBRAN-BITUMLU_3MM"),
    _i("SURME_IZOLASYON", "IZO", "Sürme izolasyon", "area", "tip", "KSF-IZO-SURME_IZOLASYON"),
    _i("BUHAR_KESICI", "IZO", "Buhar kesici", "area", "tip", "KSF-IZO-BUHAR_KESICI"),
    _i("GEOTEKSTIL", "IZO", "Geotekstil keçe", "area", "gramaj", "KSF-IZO-GEOTEKSTIL-300"),
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


# ---------------------------------------------------------------- yardımcı imalat, sarf ve işçilik kalemleri (reçete bileşenleri)
#
# Birimi "saat" olan kalemler işçiliktir (adam-saat); Birim Fiyatlar'da saat ücretiyle maliyete, ekip büyüklüğüyle süreye girer.
_L = "saat"
AUX_ITEMS: list[CatalogItem] = [
    # STA
    _i("BETON_ISCILIK", "STA", "Beton yerleştirme işçiliği", "count", "", "KSF-STA-BETON_ISCILIK", unit=_L),
    _i("VIBRATOR", "STA", "Vibratör (beton sıkıştırma)", "count", "", "KSF-STA-VIBRATOR", unit=_L),
    _i("BETON_KUR", "STA", "Beton kürü (kür kimyasalı / sulama)", "area", "", "KSF-STA-BETON_KUR"),
    _i("DEMIR_ISCILIK", "STA", "Demir kesme - bükme - yerleştirme işçiliği", "count", "", "KSF-STA-DEMIR_ISCILIK", unit=_L),
    _i("KALIP_ISCILIK", "STA", "Kalıp kurma + söküm işçiliği", "count", "", "KSF-STA-KALIP_ISCILIK", unit=_L),
    _i("KAZI_MAKINE", "STA", "Ekskavatör (kazı)", "count", "", "KSF-STA-KAZI_MAKINE", unit=_L),
    _i("KAMYON", "STA", "Kamyon (nakliye)", "count", "", "KSF-STA-KAMYON", unit=_L),
    _i("SIKISTIRMA", "STA", "Dolgu serme + sıkıştırma işçiliği", "count", "", "KSF-STA-SIKISTIRMA", unit=_L),
    # MIM / INC
    _i("DUVAR_ISCILIK", "MIM", "Duvar örgü işçiliği", "count", "", "KSF-MIM-DUVAR_ISCILIK", unit=_L),
    _i("HARC", "MIM", "Örgü harcı (hazır)", "count", "", "KSF-MIM-HARC", unit="kg"),
    _i("ALCIPAN_PROFIL", "MIM", "Alçıpan profili (C / U)", "length", "tip", "KSF-MIM-ALCIPAN_PROFIL"),
    _i("ALCIPAN_VIDA", "MIM", "Alçıpan vidası", "count", "", "KSF-MIM-ALCIPAN_VIDA"),
    _i("DERZ_BANDI", "MIM", "Derz bandı + derz dolgu alçısı", "length", "", "KSF-MIM-DERZ_BANDI"),
    _i("CAM_MONTAJ", "MIM", "Cam montaj işçiliği", "count", "", "KSF-MIM-CAM_MONTAJ", unit=_L),
    _i("KOREKUYU_MONTAJ", "MIM", "Korkuluk montaj işçiliği", "count", "", "KSF-MIM-KOREKUYU_MONTAJ", unit=_L),
    _i("SIVA_ISCILIK", "INC", "Sıva işçiliği", "count", "", "KSF-INC-SIVA_ISCILIK", unit=_L),
    _i("BOYA_ISCILIK", "INC", "Boya işçiliği", "count", "", "KSF-INC-BOYA_ISCILIK", unit=_L),
    _i("KAPLAMA_ISCILIK", "INC", "Kaplama döşeme işçiliği", "count", "", "KSF-INC-KAPLAMA_ISCILIK", unit=_L),
    _i("SERAMIK_YAPISTIRICI", "INC", "Seramik yapıştırıcısı", "count", "", "KSF-INC-SERAMIK_YAPISTIRICI", unit="kg"),
    _i("DERZ_DOLGU", "INC", "Derz dolgusu", "count", "", "KSF-INC-DERZ_DOLGU", unit="kg"),
    _i("SILTE", "INC", "Parke şiltesi", "area", "", "KSF-INC-SILTE"),
    _i("ASKI_TELI", "INC", "Asma tavan askı teli / çubuğu", "count", "", "KSF-INC-ASKI_TELI"),
    _i("TAVAN_PROFILI", "INC", "Asma tavan taşıyıcı profili", "length", "tip", "KSF-INC-TAVAN_PROFILI"),
    _i("SAP_ISCILIK", "INC", "Şap işçiliği", "count", "", "KSF-INC-SAP_ISCILIK", unit=_L),
    _i("YALITIM_ISCILIK", "IZO", "Yalıtım uygulama işçiliği", "count", "", "KSF-IZO-YALITIM_ISCILIK", unit=_L),
    _i("BITUM_ASTAR", "IZO", "Bitüm astarı", "count", "", "KSF-IZO-BITUM_ASTAR", unit="kg"),
    # CEP / CAT
    _i("MANTOLAMA_ISCILIK", "CEP", "Mantolama uygulama işçiliği", "count", "", "KSF-CEP-MANTOLAMA_ISCILIK", unit=_L),
    _i("CEPHE_MONTAJ", "CEP", "Cephe kaplama montaj işçiliği", "count", "", "KSF-CEP-CEPHE_MONTAJ", unit=_L),
    _i("CATI_ISCILIK", "CAT", "Çatı uygulama işçiliği", "count", "", "KSF-CAT-CATI_ISCILIK", unit=_L),
    _i("KENET_KLIPS", "CAT", "Kenet klipsi", "count", "", "KSF-CAT-KENET_KLIPS"),
    # ELK / ZAY
    _i("KABLO_CEKME", "ELK", "Kablo çekme işçiliği", "count", "", "KSF-ELK-KABLO_CEKME", unit=_L),
    _i("TAVA_MONTAJ", "ELK", "Kablo tavası montaj işçiliği", "count", "", "KSF-ELK-TAVA_MONTAJ", unit=_L),
    _i("TAVA_ASKI", "ELK", "Tava askısı / konsol", "count", "", "KSF-ELK-TAVA_ASKI"),
    _i("TAVA_EK", "ELK", "Tava ek parçası", "count", "", "KSF-ELK-TAVA_EK"),
    _i("BORU_MONTAJ_ELK", "ELK", "Elektrik borusu döşeme işçiliği", "count", "", "KSF-ELK-BORU_MONTAJ_ELK", unit=_L),
    _i("ARMATUR_MONTAJ", "ELK", "Armatür / cihaz montaj işçiliği", "count", "", "KSF-ELK-ARMATUR_MONTAJ", unit=_L),
    _i("BUAT", "ELK", "Buat / kasa", "count", "tip", "KSF-ELK-BUAT"),
    _i("PRIZ_MONTAJ", "ELK", "Priz / anahtar montaj işçiliği", "count", "", "KSF-ELK-PRIZ_MONTAJ", unit=_L),
    _i("PANO_MONTAJ", "ELK", "Pano montaj + bağlantı işçiliği", "count", "", "KSF-ELK-PANO_MONTAJ", unit=_L),
    _i("TOPRAKLAMA_ISCILIK", "ELK", "Topraklama işçiliği", "count", "", "KSF-ELK-TOPRAKLAMA_ISCILIK", unit=_L),
    _i("ZAYIF_AKIM_MONTAJ", "ZAY", "Zayıf akım cihaz montaj + devreye alma", "count", "", "KSF-ZAY-ZAYIF_AKIM_MONTAJ", unit=_L),
    # MEK / HAV / YAN / SIH
    _i("BORU_MONTAJ", "MEK", "Boru montaj işçiliği", "count", "", "KSF-MEK-BORU_MONTAJ", unit=_L),
    _i("BORU_ASKI", "MEK", "Boru askısı / kelepçe", "count", "çap", "KSF-MEK-BORU_ASKI"),
    _i("FITTINGS", "MEK", "Bağlantı parçası (dirsek / te / manşon)", "count", "çap", "KSF-MEK-FITTINGS"),
    _i("CIHAZ_MONTAJ", "MEK", "Cihaz montaj + devreye alma işçiliği", "count", "", "KSF-MEK-CIHAZ_MONTAJ", unit=_L),
    _i("KANAL_MONTAJ", "HAV", "Kanal montaj işçiliği", "count", "", "KSF-HAV-KANAL_MONTAJ", unit=_L),
    _i("KANAL_ASKI", "HAV", "Kanal askısı (tij + profil)", "count", "", "KSF-HAV-KANAL_ASKI"),
    _i("FLANS", "HAV", "Kanal flanşı + conta", "count", "", "KSF-HAV-FLANS"),
    _i("SPRINKLER_MONTAJ", "YAN", "Sprinkler / yangın cihazı montaj işçiliği", "count", "", "KSF-YAN-SPRINKLER_MONTAJ", unit=_L),
    _i("YIVLI_KAPLIN", "YAN", "Yivli kaplin / bağlantı", "count", "çap", "KSF-YAN-YIVLI_KAPLIN"),
    _i("VITRIFIYE_MONTAJ", "SIH", "Vitrifiye / armatür montaj işçiliği", "count", "", "KSF-SIH-VITRIFIYE_MONTAJ", unit=_L),
    # ALT / PEY / ASN
    _i("YATAK_KUMU", "ALT", "Boru yatak kumu", "volume", "", "KSF-ALT-YATAK_KUMU", unit="m³"),
    _i("GERI_DOLGU", "ALT", "Hendek geri dolgusu", "volume", "", "KSF-ALT-GERI_DOLGU", unit="m³"),
    _i("ALTYAPI_MONTAJ", "ALT", "Altyapı boru / baca montaj işçiliği", "count", "", "KSF-ALT-ALTYAPI_MONTAJ", unit=_L),
    _i("KUM_YATAK", "ALT", "Kum yatak (parke / döşeme altı)", "volume", "", "KSF-ALT-KUM_YATAK", unit="m³"),
    _i("PEYZAJ_ISCILIK", "PEY", "Peyzaj uygulama işçiliği", "count", "", "KSF-PEY-PEYZAJ_ISCILIK", unit=_L),
    _i("ASANSOR_MONTAJ", "ASN", "Asansör / yürüyen merdiven montaj işçiliği", "count", "", "KSF-ASN-ASANSOR_MONTAJ", unit=_L),
]
DEFAULT_ITEMS.extend(AUX_ITEMS)

# Kalem -> reçete (bileşen kodu, çarpan, özellik). Çarpanlar yaygın uygulama / ÇŞB analiz varsayılanıdır; kullanıcı düzenler.
# Birim başına adam-saat: beton 1,0 / m³, demir 20 / t, kalıp 1,2 / m² (kurma + söküm), duvar 0,8 / m², sıva 0,7, boya 0,3,
# seramik 1,0, kablo 0,05 / m, PPRC 0,25 / m, çelik boru 0,5 / m, kanal 0,6 / m, sprinkler 1,2 / adet, vitrifiye 2 / adet.
DEFAULT_RECIPES: dict[str, list[tuple]] = {
    # STA
    "BETON": [("BETON_ISCILIK", 1.0), ("VIBRATOR", 0.3), ("BETON_KUR", 1.0), ("BETON_POMPAJ", 1.0)],
    "GROBETON": [("BETON_ISCILIK", 0.8), ("BETON_POMPAJ", 1.0)],
    "DOLGU": [("SIKISTIRMA", 0.3), ("KAMYON", 0.08)],
    "KAZI": [("KAZI_MAKINE", 0.05), ("KAMYON", 0.1)],
    "KALIP": [("KALIP_ISCILIK", 1.2), ("KALIP_ISKELESI", 1.0, "", "H")],
    "CELIK_PROFIL": [("KAYNAK", 0.5), ("ANTIPAS", 0.3), ("CELIK_BOYA", 0.3), ("CELIK_MONTAJ", 0.4), ("ANKRAJ_BULONU", 0.2, "M20")],
    "HASIR_CELIK": [("DEMIR_ISCILIK", 0.05)],
    "SAHA_BETONU": [("BETON_ISCILIK", 0.8), ("BETON_KUR", 1.0), ("BETON_POMPAJ", 1.0)],
    # MIM
    "DUVAR_YTONG": [("DUVAR_ISCILIK", 0.8), ("DUVAR_TUTKAL", 4.0)],
    "DUVAR_TUGLA": [("DUVAR_ISCILIK", 1.0), ("HARC", 25.0)],
    "DUVAR_BIMS": [("DUVAR_ISCILIK", 0.9), ("HARC", 20.0)],
    "DUVAR_ALCIPAN": [("DUVAR_ISCILIK", 0.9), ("ALCIPAN_PROFIL", 3.0), ("ALCIPAN_VIDA", 30.0), ("DERZ_BANDI", 2.0), ("TASYUNU", 1.0, "5")],
    "CAM": [("CAM_MONTAJ", 0.5)],   # fitil / silikon pencere ve doğrama reçetesinde (boşluk çevresinden); cam m² ile çift yazılmaz
    # pencere: körkasa + sabitleme + cam izolasyonu (çevre) + denizlik (genişlik)
    "PENCERE": [("KORKASA", 1.0), ("KORKASA_MONTAJ", 0.5), ("DUBEL_VIDA", 8.0), ("CAM_FITIL", 1.0, "", "PER"),
                ("SILIKON", 1.0, "", "PER"), ("MASTIK", 1.0, "", "PER"), ("DENIZLIK", 1.0, "", "WID")],
    # kapı: kasa, pervaz (iki yüz ≈ çevre), menteşe, kilit, kol, stoper, eşik (genişlik), sabitleme, derz silikonu
    "KAPI": [("KAPI_KASASI", 1.0), ("PERVAZ", 1.0, "", "PER"), ("MENTESE", 3.0), ("KILIT", 1.0), ("KAPI_KOLU", 1.0), ("STOPER", 1.0),
             ("ESIK", 1.0, "", "WID"), ("DUBEL_VIDA", 6.0), ("SILIKON", 1.0, "", "PER")],
    # doğrama (poz listesi): pencere pozlarına pencere alt işleri, kapı pozlarına kapı alt işleri (opening_kind)
    "DOGRAMA": [("KORKASA", 1.0, "", "", "window"), ("KORKASA_MONTAJ", 0.5, "", "", "window"), ("DUBEL_VIDA", 8.0),
                ("CAM_FITIL", 1.0, "", "PER", "window"), ("SILIKON", 1.0, "", "PER"), ("MASTIK", 1.0, "", "PER", "window"),
                ("DENIZLIK", 1.0, "", "WID", "window"),
                ("KAPI_KASASI", 1.0, "", "", "door"), ("PERVAZ", 1.0, "", "PER", "door"), ("MENTESE", 3.0, "", "", "door"),
                ("KILIT", 1.0, "", "", "door"), ("KAPI_KOLU", 1.0, "", "", "door"), ("STOPER", 1.0, "", "", "door"), ("ESIK", 1.0, "", "WID", "door")],
    "KOREKUYU": [("KOREKUYU_MONTAJ", 0.8), ("ANKRAJ_BULONU", 2.0, "M10")],
    # INC
    "SIVA": [("SIVA_ISCILIK", 0.7), ("KOSE_PROFILI", 0.2)],
    "BOYA": [("BOYA_ISCILIK", 0.3)],
    "ASTAR": [("BOYA_ISCILIK", 0.1)],
    "SERAMIK_ZEMIN": [("KAPLAMA_ISCILIK", 1.0), ("SERAMIK_YAPISTIRICI", 5.0), ("DERZ_DOLGU", 0.5)],
    "SERAMIK_DUVAR": [("KAPLAMA_ISCILIK", 1.2), ("SERAMIK_YAPISTIRICI", 5.0), ("DERZ_DOLGU", 0.5)],
    "LAMINAT": [("KAPLAMA_ISCILIK", 0.4), ("SILTE", 1.05)],
    "ASMA_TAVAN": [("KAPLAMA_ISCILIK", 0.6), ("ASKI_TELI", 2.0), ("TAVAN_PROFILI", 3.0)],
    "SUPURGELIK": [("KAPLAMA_ISCILIK", 0.15)],
    "SAP": [("SAP_ISCILIK", 8.0)],
    "DOSEME_KAPLAMA": [("KAPLAMA_ISCILIK", 1.0), ("SERAMIK_YAPISTIRICI", 5.0)],
    "TAVAN_SIVA_BOYA": [("SIVA_ISCILIK", 0.7), ("BOYA_ISCILIK", 0.4)],
    # IZO
    "XPS": [("YALITIM_ISCILIK", 0.2)], "EPS": [("YALITIM_ISCILIK", 0.2)], "TASYUNU": [("YALITIM_ISCILIK", 0.2)],
    "SU_YALITIM_MEMBRAN": [("YALITIM_ISCILIK", 0.3), ("BITUM_ASTAR", 0.4)],
    "SURME_IZOLASYON": [("YALITIM_ISCILIK", 0.3)], "BUHAR_KESICI": [("YALITIM_ISCILIK", 0.1)], "GEOTEKSTIL": [("YALITIM_ISCILIK", 0.05)],
    "TEMEL_SU_YALITIMI": [("YALITIM_ISCILIK", 0.35), ("BITUM_ASTAR", 0.4)],
    "KORUMA_SAPI": [("SAP_ISCILIK", 0.4)], "DRENAJ": [("YALITIM_ISCILIK", 0.3)],
    # CEP
    "MANTOLAMA": [("IS_ISKELESI", 1.0), ("MANTOLAMA_ISCILIK", 1.2)],
    "MANTOLAMA_SISTEM": [("IS_ISKELESI", 1.0), ("MANTOLAMA_ISCILIK", 1.2)],
    "KOMPOZIT_PANEL": [("IS_ISKELESI", 1.0), ("CEPHE_TASIYICI_PROFIL", 2.5, "ALU"), ("ANKRAJ_BULONU", 1.5, "M10"), ("CEPHE_MONTAJ", 1.0)],
    "GIYDIRME_CEPHE": [("IS_ISKELESI", 1.0), ("ANKRAJ_BULONU", 1.2, "M12"), ("VINC", 0.05), ("CEPHE_MONTAJ", 1.5)],
    "CEPHE_TASI": [("IS_ISKELESI", 1.0), ("CEPHE_MONTAJ", 1.5), ("SERAMIK_YAPISTIRICI", 8.0)],
    "CEPHE_BOYA": [("IS_ISKELESI", 1.0), ("BOYA_ISCILIK", 0.3)],
    "SOVE": [("CEPHE_MONTAJ", 0.5)], "SILME": [("CEPHE_MONTAJ", 0.4)], "DENIZLIK": [("CEPHE_MONTAJ", 0.4)],
    "PREKAST_PANEL": [("ANKRAJ_BULONU", 4.0, "M20"), ("KAYNAK", 1.2), ("PREKAST_MONTAJ", 2.0), ("VINC", 0.5), ("PANEL_DERZ", 6.0)],
    # CAT
    "CATI_MEMBRAN": [("CATI_ISCILIK", 0.3), ("BITUM_ASTAR", 0.4)],
    "CATI_SANDVIC_PANEL": [("PANEL_VIDASI", 6.0), ("MAHYA_KAPAMA", 0.15), ("PANEL_MONTAJ", 0.25)],
    "CATI_KIREMIT": [("CATI_ISCILIK", 0.6)], "CATI_OLUK": [("CATI_ISCILIK", 0.4)], "CATI_DERE": [("CATI_ISCILIK", 0.4)],
    "CATI_ISIK_BANDI": [("CATI_ISCILIK", 1.0)],
    "KENET_KAPLAMA": [("CATI_ISCILIK", 0.8), ("KENET_KLIPS", 6.0)],
    "AYIRICI_KECE": [("CATI_ISCILIK", 0.05)], "OSB": [("CATI_ISCILIK", 0.3)], "CATI_TAHTASI": [("CATI_ISCILIK", 0.4)],
    "MERTEK": [("CATI_ISCILIK", 0.2)], "ASIK": [("CATI_ISCILIK", 0.15)], "CATI_LATA": [("CATI_ISCILIK", 0.1)],
    "EGIM_BETONU": [("BETON_ISCILIK", 0.5)], "CATI_CAKIL": [("CATI_ISCILIK", 0.1)], "KORUMA_BETONU": [("BETON_ISCILIK", 0.5)],
    # ELK
    "KABLO": [("KABLO_CEKME", 0.05)],
    "TAVA": [("TAVA_MONTAJ", 0.4), ("TAVA_ASKI", 0.6), ("TAVA_EK", 0.35)],
    "BUSBAR": [("TAVA_MONTAJ", 0.6), ("TAVA_ASKI", 0.5)],
    "BORU": [("BORU_MONTAJ_ELK", 0.1)],
    "ARMATUR": [("ARMATUR_MONTAJ", 0.5), ("BUAT", 1.0)], "ACIL_AYDINLATMA": [("ARMATUR_MONTAJ", 0.5), ("BUAT", 1.0)],
    "PRIZ": [("PRIZ_MONTAJ", 0.4), ("BUAT", 1.0, "KASA")], "ANAHTAR": [("PRIZ_MONTAJ", 0.4), ("BUAT", 1.0, "KASA")],
    "PANO": [("PANO_MONTAJ", 8.0)], "TOPRAKLAMA": [("TOPRAKLAMA_ISCILIK", 0.2)],
    # ZAY
    "DATA_KABLO": [("KABLO_CEKME", 0.05)], "DATA_PRIZ": [("ZAYIF_AKIM_MONTAJ", 0.5), ("BUAT", 1.0, "KASA")],
    "KAMERA": [("ZAYIF_AKIM_MONTAJ", 2.0)], "YANGIN_DEDEKTOR": [("ZAYIF_AKIM_MONTAJ", 0.8)], "YANGIN_BUTON": [("ZAYIF_AKIM_MONTAJ", 0.8)],
    "HOPARLOR": [("ZAYIF_AKIM_MONTAJ", 0.8)], "KARTLI_GECIS": [("ZAYIF_AKIM_MONTAJ", 4.0)],
    # MEK
    "BORU_CELIK": [("BORU_MONTAJ", 0.5), ("BORU_ASKI", 0.7), ("KAYNAK", 0.3), ("FITTINGS", 0.3)],
    "BORU_BAKIR": [("BORU_MONTAJ", 0.3), ("BORU_ASKI", 0.8), ("FITTINGS", 0.5)],
    "BORU_PPRC": [("BORU_MONTAJ", 0.25), ("BORU_ASKI", 0.7), ("FITTINGS", 0.5)],
    "BORU_IZOLASYON": [("YALITIM_ISCILIK", 0.15)],
    "FANCOIL": [("CIHAZ_MONTAJ", 4.0)], "VRF_IC_UNITE": [("CIHAZ_MONTAJ", 4.0)], "VRF_DIS_UNITE": [("CIHAZ_MONTAJ", 12.0), ("VINC", 2.0)],
    "RADYATOR": [("CIHAZ_MONTAJ", 2.0)], "VANA": [("CIHAZ_MONTAJ", 0.5)], "POMPA": [("CIHAZ_MONTAJ", 6.0)],
    "KAZAN": [("CIHAZ_MONTAJ", 40.0), ("VINC", 4.0)],
    # HAV
    "HAVA_KANAL": [("KANAL_MONTAJ", 0.6), ("KANAL_ASKI", 0.8), ("FLANS", 0.7)],
    "HAVA_KANAL_YUVARLAK": [("KANAL_MONTAJ", 0.4), ("KANAL_ASKI", 0.7)],
    "FLEX_KANAL": [("KANAL_MONTAJ", 0.2)], "KANAL_IZOLASYON": [("YALITIM_ISCILIK", 0.3)],
    "MENFEZ": [("CIHAZ_MONTAJ", 0.7)], "DAMPER": [("CIHAZ_MONTAJ", 1.5)], "FAN": [("CIHAZ_MONTAJ", 6.0)],
    "KLIMA_SANTRALI": [("CIHAZ_MONTAJ", 40.0), ("VINC", 4.0)],
    # YAN
    "SPRINKLER": [("SPRINKLER_MONTAJ", 1.2)],
    "YANGIN_BORU": [("BORU_MONTAJ", 0.6), ("BORU_ASKI", 0.7), ("YIVLI_KAPLIN", 0.3)],
    "YANGIN_DOLABI": [("SPRINKLER_MONTAJ", 3.0)], "YANGIN_VANA": [("SPRINKLER_MONTAJ", 1.0)],
    "YANGIN_POMPA": [("CIHAZ_MONTAJ", 16.0)], "SONDURME_TUPU": [("SPRINKLER_MONTAJ", 0.2)],
    # SIH
    "BORU_PVC": [("BORU_MONTAJ", 0.3), ("BORU_ASKI", 0.5), ("FITTINGS", 0.4)],
    "BORU_PPRC_TEMIZ": [("BORU_MONTAJ", 0.25), ("BORU_ASKI", 0.7), ("FITTINGS", 0.5)],
    "BORU_PE": [("BORU_MONTAJ", 0.3), ("FITTINGS", 0.2)],
    "LAVABO": [("VITRIFIYE_MONTAJ", 2.0)], "KLOZET": [("VITRIFIYE_MONTAJ", 2.5)], "PISUAR": [("VITRIFIYE_MONTAJ", 2.0)],
    "BATARYA": [("VITRIFIYE_MONTAJ", 0.8)], "YER_SUZGECI": [("VITRIFIYE_MONTAJ", 0.8)],
    "HIDROFOR": [("CIHAZ_MONTAJ", 8.0)], "SU_DEPOSU": [("CIHAZ_MONTAJ", 6.0)],
    # ALT
    "BORU_KORUGE": [("KAZI", 1.2, "100"), ("YATAK_KUMU", 0.3), ("GERI_DOLGU", 0.9), ("ALTYAPI_MONTAJ", 0.3)],
    "BORU_BETON": [("KAZI", 2.0, "150"), ("YATAK_KUMU", 0.4), ("GERI_DOLGU", 1.5), ("ALTYAPI_MONTAJ", 0.6), ("VINC", 0.1)],
    "BACA": [("KAZI", 2.5, "200"), ("GERI_DOLGU", 1.5), ("ALTYAPI_MONTAJ", 6.0), ("VINC", 0.5)],
    "YAGMUR_IZGARA": [("ALTYAPI_MONTAJ", 0.5)], "BORDUR": [("ALTYAPI_MONTAJ", 0.3), ("BETON", 0.05, "15")],
    "PARKE_TAS": [("KUM_YATAK", 0.05), ("KAPLAMA_ISCILIK", 0.6)],
    "ASFALT": [("SIKISTIRMA", 0.05)], "ISTINAT": [("KAZI", 1.0, "100"), ("GERI_DOLGU", 0.5)],
    "AYDINLATMA_DIREGI": [("ARMATUR_MONTAJ", 6.0), ("BETON", 0.5, "25"), ("ANKRAJ_BULONU", 4.0, "M24"), ("VINC", 0.5)],
    # PEY
    "CIM": [("PEYZAJ_ISCILIK", 0.1)], "AGAC": [("PEYZAJ_ISCILIK", 1.5), ("KAZI", 0.5, "80")], "CALI": [("PEYZAJ_ISCILIK", 0.3)],
    "BITKI_TOPRAGI": [("PEYZAJ_ISCILIK", 0.3)], "SULAMA_BORU": [("BORU_MONTAJ", 0.1), ("KAZI", 0.1, "40")],
    "SULAMA_BASLIK": [("PEYZAJ_ISCILIK", 0.3)], "BANK": [("PEYZAJ_ISCILIK", 2.0), ("ANKRAJ_BULONU", 4.0, "M12")],
    "PEYZAJ_DOSEME": [("KUM_YATAK", 0.05), ("KAPLAMA_ISCILIK", 0.6)],
    # ASN
    "ASANSOR": [("ASANSOR_MONTAJ", 240.0), ("VINC", 8.0)], "YURUYEN_MERDIVEN": [("ASANSOR_MONTAJ", 160.0), ("VINC", 8.0)],
}


def _apply_default_recipes() -> None:
    by_code = {it.code: it for it in DEFAULT_ITEMS}
    for code, rows in DEFAULT_RECIPES.items():
        it = by_code.get(code)
        if not it:
            raise RuntimeError(f"Reçete tanımlı ama kalem yok: {code}")
        recipe = list(it.recipe)   # kod içinde tanımlı reçete korunur, yeni bileşenler eklenir
        have = {c["code"] for c in recipe}
        for row in rows:
            comp = _c(row[0], row[1] if len(row) > 1 else 1.0, row[2] if len(row) > 2 else "", row[3] if len(row) > 3 else "",
                      row[4] if len(row) > 4 else "")
            if comp["code"] not in have:
                recipe.append(comp)
        it.recipe = normalize_components(recipe)
        for c in it.recipe:
            if c["code"] not in by_code:
                raise RuntimeError(f"{code} reçetesindeki bileşen katalogda yok: {c['code']}")


_apply_default_recipes()


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
                         custom=True, components=data.get("components") or [], poz=(data.get("poz") or "").strip(),
                         recipe=data.get("recipe") or [])
        if it.discipline not in self.disciplines:
            raise ValueError(f"Bilinmeyen disiplin kodu: {it.discipline}")
        for c in it.components + it.recipe:
            if c["code"] == it.code:
                raise ValueError("Kalem kendi bileşeni olamaz")
            if c["code"] not in self.items:
                raise ValueError(f"Bileşen katalogda yok: {c['code']} (önce kalem olarak ekleyin)")
        self.items[it.code] = it
        return it

    def systems(self) -> list[CatalogItem]:
        return [it for it in self.items.values() if it.is_system]

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
            d = {k: v for k, v in d.items() if k in {"code", "discipline", "name", "measure", "unit", "spec_label", "example", "custom", "components", "poz", "recipe"}}
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
