"""Katman adı -> eleman tipi eşleme profili (disiplin bazlı).

Profil JSON biçimi: {"column": ["KOLON", "COL"], "wall": [...], ..., "hole": [...], "ignore": [...]}
Desenler büyük/küçük harf duyarsız regex'tir ve katman adında herhangi bir yerde aranır.

Disiplinler: statik (structural), mimari (architectural), elektrik (electrical). Her çizim tek bir disipline
aittir; katman sınıflandırması yalnızca o disiplinin eleman tiplerini üretir (mimari paftadaki "PERDE" katmanı
perde duvar/kolon değil, yok sayılır; kullanıcı tam ad eşlemesi yapmışsa o kazanır).
"hole" tipi: döşeme boşlukları (şaft, merdiven boşluğu); döşeme alanından düşülür.
"""
from __future__ import annotations

import re

DISCIPLINES: dict[str, str] = {
    "structural": "Statik (kalıp planı)",
    "architectural": "Mimari (sezgisel)",
    "electrical": "Elektrik (sezgisel)",
    "mechanical": "Mekanik (sezgisel)",
    "standard": "KSF standart çizim (tüm disiplinler)",
    "rebar": "Donatı planı (demir metraj tablosu)",
    "mapped": "Katman eşlemeli (cephe / çatı / peyzaj / diğer)",
}
STANDARD_DISCIPLINE = "standard"
REBAR_DISCIPLINE = "rebar"
MAPPED_DISCIPLINE = "mapped"
DEFAULT_DISCIPLINE = "structural"

# Eleman tipleri (metraja giren)
STRUCTURAL_TYPES: dict[str, str] = {
    "column": "Kolon",
    "shear_wall": "Perde",
    "beam": "Kiriş",
    "slab": "Döşeme",
    "foundation": "Temel",
}
ARCHITECTURAL_TYPES: dict[str, str] = {
    "wall": "Duvar",
    "door": "Kapı",
    "window": "Pencere",
}
ELECTRICAL_TYPES: dict[str, str] = {
    "tray": "Kablo tavası",
    "cable": "Kablo",
    "conduit": "Boru",
    "fixture": "Armatür / priz / anahtar",
}
MECHANICAL_TYPES: dict[str, str] = {
    "pipe": "Boru (mekanik / sıhhi / yangın)",
    "duct": "Hava kanalı",
    "mech_fixture": "Mekanik cihaz / vitrifiye",
}
TYPES_BY_DISCIPLINE: dict[str, dict[str, str]] = {
    "structural": STRUCTURAL_TYPES,
    "architectural": ARCHITECTURAL_TYPES,
    "electrical": ELECTRICAL_TYPES,
    "mechanical": MECHANICAL_TYPES,
}
# Geriye uyumluluk: ELEMENT_TYPES statik tipler (metraj motoru, özet); ALL_ELEMENT_TYPES tüm disiplinler
ELEMENT_TYPES = STRUCTURAL_TYPES
ALL_ELEMENT_TYPES: dict[str, str] = {**STRUCTURAL_TYPES, **ARCHITECTURAL_TYPES, **ELECTRICAL_TYPES, **MECHANICAL_TYPES}
TYPE_DISCIPLINE: dict[str, str] = {t: d for d, types in TYPES_BY_DISCIPLINE.items() for t in types}

AUX_TYPES: dict[str, str] = {"hole": "Döşeme boşluğu"}
ALL_TYPES = {**ALL_ELEMENT_TYPES, **AUX_TYPES}


def types_for(discipline: str) -> dict[str, str]:
    """Katman eşlemede seçilebilen tipler: disiplinin elemanları (+ statikte döşeme boşluğu). Standart çizimde eşleme yok."""
    if discipline in (STANDARD_DISCIPLINE, REBAR_DISCIPLINE, MAPPED_DISCIPLINE):
        return {}
    base = dict(TYPES_BY_DISCIPLINE.get(discipline, STRUCTURAL_TYPES))
    if discipline == "structural":
        base.update(AUX_TYPES)
    return base


# Öncelik sırası: daha spesifik tipler önce (ör. "DÖŞEME ŞAFT" -> hole, "TEMEL_KIRIS" -> temel, "KABLO TAVASI" -> tava)
MATCH_ORDER = ("hole", "foundation", "shear_wall", "column", "beam", "slab",
               "window", "door", "wall",
               "tray", "conduit", "fixture", "cable",
               "pipe", "duct", "mech_fixture")

DEFAULT_PROFILE: dict[str, list[str]] = {
    # statik
    "column": [r"KOLON", r"\bCOL\b", r"S[-_]?COL", r"COLUMN", r"STR[-_]COL"],
    "shear_wall": [r"PERDE", r"S[-_]?WALL", r"SHEAR", r"STR[-_]WALL"],
    "beam": [r"KIRI[SŞ]", r"KİRİ[SŞ]", r"\bBEAM\b", r"S[-_]?BEAM", r"STR[-_]BEAM"],
    "slab": [r"DO[SŞ]EME", r"DÖ[SŞ]EME", r"\bSLAB", r"S[-_]?SLAB", r"STR[-_]SLAB"],
    "foundation": [r"TEMEL", r"RADYE", r"FOUND", r"FOOTING", r"RAFT", r"S[-_]?FND"],
    "hole": [r"[SŞ]AFT", r"SHAFT", r"BO[SŞ]LUK", r"OPENING", r"VOID"],
    # mimari
    "wall": [r"DUVAR", r"\bWALL", r"A[-_]?WALL", r"YTONG", r"GAZBETON", r"TU[GĞ]LA", r"B[Iİ]MS", r"AL[CÇ][Iİ]PAN",
             r"DRYWALL", r"PARTITION", r"BÖLME", r"BOLME"],
    "door": [r"KAPI", r"(?<![A-Z])DOOR", r"A[-_]?DOOR", r"KAPILAR"],
    "window": [r"PENCERE", r"(?<![A-Z])WINDOW", r"A[-_]?WIND", r"A[-_]?GLAZ", r"DO[GĞ]RAMA", r"CAM\b"],
    # elektrik
    "tray": [r"TAVA", r"\bTRAY", r"KABLO\s*KANAL", r"CABLE\s*TRAY", r"\bKT\b", r"BUSBAR", r"MERDIVEN\s*TAVA"],
    "cable": [r"KABLO", r"\bCABLE", r"\bWIRE", r"E[-_]?WIRE", r"BESLEME", r"L[Iİ]NYE", r"SORT[Iİ]", r"KOLON\s*HAT",
              r"E[-_]?POWR", r"CIRCUIT", r"\bHAT\b", r"DATA", r"\bCAT\s?[56]", r"ZAYIF\s*AK"],
    "conduit": [r"\bBORU", r"CONDUIT", r"\bPVC\b", r"SP[Iİ]RAL", r"KANAL\b"],
    "fixture": [r"ARMAT[UÜ]R", r"AYDINLATMA", r"\bLIGHT", r"E[-_]?LITE", r"FIXTURE", r"LUMIN", r"PR[Iİ]Z", r"SOCKET",
                r"ANAHTAR", r"SWITCH", r"\bBUAT", r"S[Iİ]GORTA", r"PANO", r"\bDEV[Iİ]CE", r"DETEKT[OÖ]R", r"SENS[OÖ]R",
                r"S[Iİ]REN", r"YANGIN", r"ACIL", r"EXIT", r"\bTV\b", r"DATA\s*PR"],
    # mekanik: boru hatları (sistem adıyla), hava kanalları, cihaz / vitrifiye blokları
    "pipe": [r"\bBORU", r"\bPIPE", r"PPRC", r"\bPVC\b", r"TEM[Iİ]Z\s*SU", r"P[Iİ]S\s*SU", r"P[Iİ]SSU", r"SO[GĞ]UK\s*SU", r"SICAK\s*SU",
             r"KULLANMA\s*SU", r"AT[Iİ]K\s*SU", r"DRENAJ", r"YA[GĞ]MUR\s*(SU|HAT|BORU)", r"ISITMA", r"SO[GĞ]UTMA", r"\bCHW\b", r"\bHHW\b",
             r"\bDN\s*\d", r"BAKIR", r"COPPER", r"YANGIN\s*(BORU|HAT)", r"SPR[Iİ]NK.*(BORU|HAT|P[Iİ]PE)", r"\bGAZ\s*(BORU|HAT)",
             r"M[-_]?PIPE", r"P[-_]?(CW|HW|SAN|WASTE|VENT)\b", r"HAVALIK|VENT\b"],
    "duct": [r"KANAL(?!\s*[Iİ]ZASYON)", r"\bDUCT", r"HAVA\b", r"EGZO[SZ]T?", r"EXHAUST", r"TAZE", r"SUPPLY", r"RETURN", r"\bFLEX", r"SP[Iİ]RAL"],
    "mech_fixture": [r"MENFEZ", r"D[Iİ]F[UÜ]Z", r"GRILLE", r"ANEMOSTAT", r"VANA", r"VALVE", r"SPR[Iİ]NK", r"RADYAT", r"FANCOIL", r"\bFCU\b",
                     r"\bVRF\b", r"\bVRV\b", r"KL[Iİ]MA", r"\bAHU\b", r"SANTRAL", r"\bFAN\b", r"ASP[Iİ]RAT", r"DAMPER", r"V[Iİ]TR[Iİ]F[Iİ]YE",
                     r"LAVABO", r"KLOZET", r"\bWC\b", r"P[Iİ]SUAR", r"P[Iİ]SUVAR", r"BATARYA", r"EV[Iİ]YE", r"S[UÜ]ZGE[CÇ]", r"POMPA", r"\bPUMP",
                     r"KAZAN", r"BOILER", r"CHILLER", r"H[Iİ]DROFOR", r"DEPO", r"\bTANK", r"YANGIN\s*DOLAB", r"H[Iİ]DRANT", r"T[UÜ]P\b",
                     r"KOLLEKT", r"KOLEKT", r"SAYA[CÇ]", r"M[-_]?EQUIP", r"P[-_]?FIXT", r"SANITARY", r"TES[Iİ]SAT\s*C[Iİ]HAZ"],
}

# Bu katmanlar hiçbir zaman eleman sayılmaz (yazı, ölçü, aks, detay, donatı, tarama vb.)
IGNORE_PATTERNS = [
    r"YAZI", r"TEXT", r"OLCU", r"ÖLÇÜ", r"\bDIM", r"\bAKS", r"AXIS", r"GRID",
    r"DEFPOINTS", r"ANTET", r"CERCEVE", r"ÇERÇEVE", r"TITLE", r"TARAMA", r"HATCH",
    r"DETAIL", r"DETAY", r"REBAR", r"DONATI", r"DONATİ", r"\bKOT\b", r"APLIKASYON", r"APLİKASYON",
    r"KESIT", r"KESİT", r"SECTION", r"MERDIVEN", r"MERDİVEN", r"STAIR", r"\bIZI\b", r"İZİ",
    r"MARKA",  # sadece yazı içerir; yazılar katmandan bağımsız toplanır
    r"\bLGP",  # LGP-SLAB: döşeme etiketi çerçeve kutuları (döşeme çokgeni değil)
    r"KES[Iİ]K",  # kesik/gizli çizgi kopyaları (KM Temel Kesik: radye sınırının ofsetli kopyası)
    r"G[Iİ]ZL[Iİ]", r"\bHIDE", r"HIDDEN",  # gizli / görünmez yardımcı katmanlar (HB-GIZLI-DATA gibi yazı katmanları)
]
# Mimari paftada duvarlar çoğu zaman tarama (hatch) ile çizilir; bu desenler mimaride yok sayılmaz
ARCH_KEEP = {r"TARAMA", r"HATCH"}
# Elektrik paftasında "MERDIVEN TAVA" (merdiven tipi kablo tavası) elemandır; tava deseni yok-saymadan önce gelir
ELEC_KEEP = {r"MERDIVEN", r"MERDİVEN"}


def _compile(patterns: list[str]) -> list[re.Pattern]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p, re.IGNORECASE))
        except re.error:
            out.append(re.compile(re.escape(p), re.IGNORECASE))
    return out


def _upper(s: str) -> str:
    # Türkçe i/ı: Python upper() 'i'->'I' yapar; 'ş','ğ','ç','ö','ü' doğru dönüşür
    return s.replace("i", "İ").upper()


def _is_exact(pat: re.Pattern) -> bool:
    return pat.pattern.startswith("^") and pat.pattern.endswith("$")


class LayerProfile:
    def __init__(self, overrides: dict[str, list[str]] | None = None, ignore: list[str] | None = None):
        """overrides: varsayılan profile EK desenler (projeye kaydedilen kullanıcı eşlemeleri)."""
        self.overrides: dict[str, list[str]] = {k: list(v) for k, v in (overrides or {}).items() if v}
        base = {k: list(v) for k, v in DEFAULT_PROFILE.items()}
        for k, v in self.overrides.items():
            base[k] = base.get(k, []) + [p for p in v if p not in base.get(k, [])]
        self.raw = base
        self._compiled = {k: _compile(v) for k, v in self.raw.items()}
        ignore_list = ignore if ignore is not None else IGNORE_PATTERNS
        self._ignore = _compile(ignore_list)
        self._ignore_arch = _compile([p for p in ignore_list if p not in ARCH_KEEP])
        self._ignore_elec = _compile([p for p in ignore_list if p not in ELEC_KEEP])

    def classify(self, layer: str, discipline: str = DEFAULT_DISCIPLINE) -> str | None:
        """Katmanı disiplinin eleman tiplerinden birine atar; eşleşmezse None (yok sayılır).
        Bağlanmış xref katmanları ("PROJE$0$brn_doors") son parçasıyla değerlendirilir."""
        name = _upper(layer)
        if "$" in name:
            name = name.rsplit("$", 1)[-1] or name
        allowed = set(types_for(discipline))
        order = [t for t in MATCH_ORDER if t in allowed]
        # Kullanıcının tam ad eşlemesi (^...$) yok-sayma listesinden ve disiplin kısıtından önce gelir
        for etype in MATCH_ORDER:
            for pat in self._compiled.get(etype, []):
                if _is_exact(pat) and pat.search(name):
                    return etype if etype in allowed else None
        if any(_is_exact(pat) and pat.search(name) for pat in self._compiled.get("ignore", [])):
            return None
        ignore = {"architectural": self._ignore_arch, "electrical": self._ignore_elec}.get(discipline, self._ignore)
        for pat in ignore:
            if pat.search(name):
                return None
        for etype in order:
            for pat in self._compiled.get(etype, []):
                if pat.search(name):
                    return etype
        return None

    def is_ignored(self, layer: str) -> bool:
        """Kullanıcı bu katmanı açıkça 'ölçülmez' yaptı mı (tam ad yok-sayma)?"""
        name = _upper(layer)
        return any(_is_exact(pat) and pat.search(name) for pat in self._compiled.get("ignore", []))

    def layers_for(self, etype: str, layers: list[str], discipline: str | None = None) -> list[str]:
        disc = discipline or TYPE_DISCIPLINE.get(etype, DEFAULT_DISCIPLINE)
        return [l for l in layers if self.classify(l, disc) == etype]

    def to_dict(self) -> dict[str, list[str]]:
        """Yalnızca kullanıcı eklemeleri (projeye kaydedilir); varsayılanlar kodda kalır."""
        return {k: list(v) for k, v in self.overrides.items()}

    def effective(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self.raw.items()}

    def with_layer(self, etype: str | None, layer: str) -> "LayerProfile":
        """Belirli bir katmanı tam ad ile bir eleman tipine atar; etype None ise 'yok sayılır' yapar."""
        exact = f"^{re.escape(_upper(layer))}$"
        raw = {k: [p for p in v if p != exact] for k, v in self.to_dict().items()}
        raw.setdefault("ignore", [])
        raw["ignore"] = [p for p in raw["ignore"] if p != exact]
        if etype:
            raw.setdefault(etype, []).append(exact)
        else:
            raw["ignore"].append(exact)
        return LayerProfile(raw)


def mapped_item(profile: "LayerProfile", layer: str) -> tuple[str, str | None, str | None] | None:
    """Katman eşlemeli çizim: kullanıcı katmanı bir katalog kalemine atamışsa (anahtar 'item:<KOD>',
    'item:<KOD>:<ölçüm>' ya da 'item:<KOD>:<ölçüm>:<etiket deseni>') (kod, ölçüm, desen) döndürür.
    Desen: etiket sayımında yalnız bu düzenli ifadeye uyan yazılar sayılır (ör. '^(GP|EP)')."""
    name = _upper(layer)
    for key, pats in profile.raw.items():
        if not key.startswith("item:"):
            continue
        for pat in profile._compiled.get(key, []):
            if pat.search(name):
                parts = key.split(":", 3)
                measure = parts[2] if len(parts) > 2 and parts[2] else None
                pattern = parts[3] if len(parts) > 3 and parts[3] else None
                return parts[1], measure, pattern
    return None
