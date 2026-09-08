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
            m = re.match(r"^([^×x*:]+?)\s*(?:[×x*]\s*([0-9.,]+)(H)?)?\s*(?::\s*(.+))?$", part)
            if not m:
                continue
            parsed.append({"code": m.group(1), "factor": m.group(2) or 1, "spec": (m.group(4) or "").strip(),
                           "times": "H" if m.group(3) else ""})
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
        if str(c.get("times") or "").upper() == "H":
            row["times"] = "H"
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


def _c(code, factor=1.0, spec="", times=""):
    return {"code": code, "factor": factor, "spec": spec, "times": times}


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
