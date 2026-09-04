"""Katman adı -> eleman tipi eşleme profili.

Profil JSON biçimi: {"column": ["KOLON", "COL"], "beam": [...], ..., "hole": [...]}
Desenler büyük/küçük harf duyarsız regex'tir ve katman adında herhangi bir yerde aranır.
"hole" tipi: döşeme boşlukları (şaft, merdiven boşluğu); döşeme alanından düşülür.
"""
from __future__ import annotations

import re

ELEMENT_TYPES: dict[str, str] = {
    "column": "Kolon",
    "shear_wall": "Perde",
    "beam": "Kiriş",
    "slab": "Döşeme",
    "foundation": "Temel",
}
AUX_TYPES: dict[str, str] = {"hole": "Döşeme boşluğu"}
ALL_TYPES = {**ELEMENT_TYPES, **AUX_TYPES}

# Öncelik sırası: daha spesifik tipler önce (ör. "DÖŞEME ŞAFT" -> hole, "TEMEL_KIRIS" -> temel)
MATCH_ORDER = ("hole", "foundation", "shear_wall", "column", "beam", "slab")

DEFAULT_PROFILE: dict[str, list[str]] = {
    "column": [r"KOLON", r"\bCOL\b", r"S[-_]?COL", r"COLUMN", r"STR[-_]COL"],
    "shear_wall": [r"PERDE", r"S[-_]?WALL", r"SHEAR", r"STR[-_]WALL"],
    "beam": [r"KIRI[SŞ]", r"KİRİ[SŞ]", r"\bBEAM\b", r"S[-_]?BEAM", r"STR[-_]BEAM"],
    "slab": [r"DO[SŞ]EME", r"DÖ[SŞ]EME", r"\bSLAB", r"S[-_]?SLAB", r"STR[-_]SLAB"],
    "foundation": [r"TEMEL", r"RADYE", r"FOUND", r"FOOTING", r"RAFT", r"S[-_]?FND"],
    "hole": [r"[SŞ]AFT", r"SHAFT", r"BO[SŞ]LUK", r"OPENING", r"VOID"],
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
]


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


class LayerProfile:
    def __init__(self, overrides: dict[str, list[str]] | None = None, ignore: list[str] | None = None):
        """overrides: varsayılan profile EK desenler (projeye kaydedilen kullanıcı eşlemeleri)."""
        self.overrides: dict[str, list[str]] = {k: list(v) for k, v in (overrides or {}).items() if v}
        base = {k: list(v) for k, v in DEFAULT_PROFILE.items()}
        for k, v in self.overrides.items():
            base[k] = base.get(k, []) + [p for p in v if p not in base.get(k, [])]
        self.raw = base
        self._compiled = {k: _compile(v) for k, v in self.raw.items()}
        self._ignore = _compile(ignore if ignore is not None else IGNORE_PATTERNS)

    def classify(self, layer: str) -> str | None:
        name = _upper(layer)
        # Kullanıcının tam ad eşlemesi (^...$) yok-sayma listesinden önce gelir
        for etype in MATCH_ORDER:
            for pat in self._compiled.get(etype, []):
                if pat.pattern.startswith("^") and pat.pattern.endswith("$") and pat.search(name):
                    return etype
        if any(pat.pattern.startswith("^") and pat.pattern.endswith("$") and pat.search(name)
               for pat in self._compiled.get("ignore", [])):
            return None
        for pat in self._ignore:
            if pat.search(name):
                return None
        for etype in MATCH_ORDER:
            for pat in self._compiled.get(etype, []):
                if pat.search(name):
                    return etype
        return None

    def layers_for(self, etype: str, layers: list[str]) -> list[str]:
        return [l for l in layers if self.classify(l) == etype]

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
