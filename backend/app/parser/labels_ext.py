"""Mimari ve elektrik pafta etiketleri / blok adları için çözümleyiciler.

Mimari:
  Duvar: "YTONG 20", "20 cm GAZBETON", "DUVAR 13.5", "TUĞLA 19" -> malzeme + kalınlık (cm)
  Kapı/pencere: "K1 90/210", "P3 120x140", "PC1 (150/220)" -> tip, ad, genişlik/yükseklik (cm)
Elektrik:
  Tava: "TAVA 200x60", "KT 300/60", "100x50 KABLO TAVASI" -> genişlik x yükseklik (mm)
  Kablo: "NYY 4x16", "3x2,5 NYM", "N2XH 5x10", "CAT6" -> tip + kesit
  Boru: "Ø20 PVC", "25mm HFT boru" -> çap (mm)
Sayılar bulundukları alanın yaygın birimiyle okunur (mimari cm, elektrik mm).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .text_parser import normalize

_NUM = r"\d+(?:[.,]\d+)?"


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _up(s: str) -> str:
    return s.replace("i", "İ").upper()


# ---------------------------------------------------------------- mimari

WALL_MATERIALS: dict[str, tuple[str, list[str]]] = {
    # anahtar: (görünen ad, katman/etiket desenleri)
    "ytong": ("Ytong / gazbeton", [r"YTONG", r"GAZ\s*BETON", r"\bAAC\b", r"GAZBETON"]),
    "tugla": ("Tuğla", [r"TU[GĞ]LA", r"BRICK", r"HARMAN"]),
    "bims": ("Bims blok", [r"B[Iİ]MS", r"PONZA"]),
    "alcipan": ("Alçıpan bölme", [r"AL[CÇ][Iİ]PAN", r"GYPSUM", r"DRYWALL", r"BÖLME\s*DUVAR", r"BOLME"]),
    "beton": ("Betonarme duvar", [r"BETON", r"CONCRETE", r"B\.?A\.?\s*DUVAR"]),
    "tas": ("Taş duvar", [r"TA[SŞ]\s*DUVAR", r"STONE"]),
}
_MATERIAL_RE = {k: [re.compile(p, re.IGNORECASE) for p in pats] for k, (_, pats) in WALL_MATERIALS.items()}
_WALL_THICK = re.compile(rf"(?<![\d.,/xX])(?P<t>{_NUM})\s*(?:cm|CM)?(?![\d.,/xX])")

OPENING_PREFIXES: dict[str, str] = {
    "P": "window", "PC": "window", "PN": "window", "W": "window", "PE": "window",
    "K": "door", "KP": "door", "KD": "door", "D": "door", "DR": "door",
}
_OPENING = re.compile(
    rf"^\s*(?P<prefix>[A-ZÇĞİÖŞÜ]{{1,2}})\s*-?\s*(?P<num>\d+[A-Za-z']?)\s*[:\-]?\s*\(?\s*"
    rf"(?:(?P<b>{_NUM})\s*[/xX×*]\s*(?P<h>{_NUM}))?\s*\)?"
)
_DIMS = re.compile(rf"(?<![\d.,])(?P<b>{_NUM})\s*[/xX×*]\s*(?P<h>{_NUM})(?![\d.,])")


def wall_material(*texts: str) -> str | None:
    """Katman adı ya da etiketten duvar malzemesi anahtarı ('ytong' vb.)."""
    for t in texts:
        if not t:
            continue
        for key, pats in _MATERIAL_RE.items():
            if any(p.search(t) for p in pats):
                return key
    return None


@dataclass
class WallLabel:
    raw: str
    material: str | None = None
    thickness: float | None = None     # metre

    @property
    def is_meaningful(self) -> bool:
        return self.material is not None or self.thickness is not None


def parse_wall_label(text: str, unit_scale: float = 0.01) -> WallLabel:
    t = normalize(text)
    lab = WallLabel(raw=t)
    lab.material = wall_material(t)
    if lab.material or re.search(r"DUVAR|WALL", t, re.IGNORECASE):
        m = _WALL_THICK.search(t)
        if m:
            v = _num(m.group("t"))
            if 3 <= v <= 60:           # cm aralığı; "2026" gibi sayılar değil
                lab.thickness = v * unit_scale
    return lab


@dataclass
class OpeningLabel:
    raw: str
    etype: str | None = None          # window | door
    name: str | None = None
    width: float | None = None        # metre
    height: float | None = None       # metre

    @property
    def has_dims(self) -> bool:
        return self.width is not None and self.height is not None

    @property
    def is_meaningful(self) -> bool:
        return self.etype is not None or self.has_dims


def parse_opening_label(text: str, unit_scale: float = 0.01) -> OpeningLabel:
    t = normalize(text)
    lab = OpeningLabel(raw=t)
    m = _OPENING.match(t)
    if m and _up(m.group("prefix")) in OPENING_PREFIXES:
        prefix = _up(m.group("prefix"))
        lab.etype = OPENING_PREFIXES[prefix]
        lab.name = f"{prefix}{m.group('num')}"
        if m.group("b") and m.group("h"):
            lab.width, lab.height = _num(m.group("b")) * unit_scale, _num(m.group("h")) * unit_scale
    if not lab.has_dims:
        d = _DIMS.search(t)
        if d:
            b, h = _num(d.group("b")), _num(d.group("h"))
            if 30 <= b <= 600 and 30 <= h <= 400:       # cm cinsinden makul kapı/pencere ölçüsü
                lab.width, lab.height = b * unit_scale, h * unit_scale
    if lab.etype is None:
        if re.search(r"PENCERE|WINDOW", t, re.IGNORECASE):
            lab.etype = "window"
        elif re.search(r"KAPI|DOOR", t, re.IGNORECASE):
            lab.etype = "door"
    return lab


def opening_type_from_name(block_or_layer: str) -> str | None:
    """Blok / katman adından kapı ya da pencere olduğu anlaşılırsa döndürür."""
    n = _up(block_or_layer)
    if re.search(r"PENCERE|WINDOW|WIN\b|GLAZ|DOGRAMA|DOĞRAMA", n):
        return "window"
    if re.search(r"KAPI|DOOR|\bDR\b", n):
        return "door"
    return None


def size_from_name(name: str, unit_scale: float = 0.01) -> tuple[float | None, float | None]:
    """'PENCERE_120x140', 'KAPI-90' gibi blok adlarından ölçü (m)."""
    d = _DIMS.search(name)
    if d:
        b, h = _num(d.group("b")), _num(d.group("h"))
        if 30 <= b <= 600 and 30 <= h <= 400:
            return b * unit_scale, h * unit_scale
    m = re.search(r"(?<!\d)(\d{2,3})(?!\d)", name)
    if m and 40 <= int(m.group(1)) <= 400:
        return int(m.group(1)) * unit_scale, None
    return None, None


# ---------------------------------------------------------------- elektrik

CABLE_TYPES = (r"NYY", r"NYM", r"NHXMH", r"N2XH", r"N2XCH", r"NYCY", r"NYA(?:F)?", r"NYRY", r"YVV", r"H07(?:Z|V|RN)[-\w]*",
               r"H05[-\w]*", r"TTR", r"LI(?:Y|H)C[YH]", r"J-?Y\(ST\)Y", r"FTP", r"UTP", r"S/?FTP", r"CAT\s?[56]A?E?",
               r"FIBER", r"F/?O", r"HFFR", r"LSZH", r"XLPE", r"NHXH", r"JE-H\(ST\)H", r"RG-?\d+")
_CABLE_TYPE = re.compile(r"(?<![A-Z0-9])(?P<t>" + "|".join(CABLE_TYPES) + r")(?![A-Z0-9])", re.IGNORECASE)
_SECTION = re.compile(
    rf"(?<![\d.,])(?P<n>\d{{1,2}})\s*[xX×]\s*(?P<a>{_NUM})(?:\s*\+\s*(?P<pe>{_NUM}))?(?:\s*(?:mm2|mm²|mm))?(?![\d.,])"
)
_TRAY_SIZE = re.compile(rf"(?<![\d.,])(?P<w>\d{{2,4}})\s*[xX×/]\s*(?P<h>\d{{2,3}})(?:\s*mm)?(?![\d.,])")
_TRAY_WORD = re.compile(r"TAVA|TRAY|\bKT\b|KANAL|BUSBAR", re.IGNORECASE)
_TRAY_WIDTH_ONLY = re.compile(r"(?:TAVA|TRAY|KT)\s*[:\-]?\s*(?P<w>\d{2,4})(?!\d)", re.IGNORECASE)
_CONDUIT = re.compile(r"(?:[ØøΦφ∅]|\bQ|DN|\bd\s*=?)\s*(?P<d>\d{2,3})(?!\d)|(?P<d2>\d{2,3})\s*(?:mm)\b", re.IGNORECASE)
_CONDUIT_WORD = re.compile(r"BORU|CONDUIT|PVC|HFT|SP[Iİ]RAL|GALVAN|ÇEL[Iİ]K", re.IGNORECASE)


def fmt_num(v: float) -> str:
    return f"{v:g}"


@dataclass
class ElecLabel:
    raw: str
    kind: str | None = None           # tray | cable | conduit
    spec: str | None = None           # "200x60" | "NYY 4x16" | "Ø20 PVC"
    width: float | None = None        # tava genişliği (m)
    height: float | None = None       # tava yüksekliği (m)
    cable_type: str | None = None
    section: str | None = None        # "4x16"

    @property
    def is_meaningful(self) -> bool:
        return self.kind is not None


def parse_elec_label(text: str, unit_scale: float = 0.001) -> ElecLabel:
    """Elektrik etiketini çözer. unit_scale: mm -> m."""
    t = normalize(text)
    lab = ElecLabel(raw=t)
    ct = _CABLE_TYPE.search(t)
    sec = _SECTION.search(t)
    tray_word = bool(_TRAY_WORD.search(t))

    if sec and not tray_word:
        n, a = int(sec.group("n")), _num(sec.group("a"))
        if 1 <= n <= 61 and a <= 400:
            s = f"{n}x{fmt_num(a)}" + (f"+{fmt_num(_num(sec.group('pe')))}" if sec.group("pe") else "")
            lab.kind, lab.section = "cable", s
            lab.cable_type = ct.group("t").upper().replace(" ", "") if ct else None
            lab.spec = f"{lab.cable_type} {s}".strip() if lab.cable_type else s
            return lab
    if ct and not tray_word:
        lab.kind = "cable"
        lab.cable_type = ct.group("t").upper().replace(" ", "")
        lab.spec = lab.cable_type
        return lab
    ts = _TRAY_SIZE.search(t)
    if ts and (tray_word or int(ts.group("w")) >= 50):
        w, h = int(ts.group("w")), int(ts.group("h"))
        lab.kind, lab.spec = "tray", f"{w}x{h}"
        lab.width, lab.height = w * unit_scale, h * unit_scale
        return lab
    tw = _TRAY_WIDTH_ONLY.search(t)
    if tw:
        w = int(tw.group("w"))
        lab.kind, lab.spec, lab.width = "tray", f"{w}", w * unit_scale
        return lab
    if tray_word:
        lab.kind, lab.spec = "tray", None
        return lab
    cd = _CONDUIT.search(t)
    if cd and (_CONDUIT_WORD.search(t) or cd.group("d")):
        d = int(cd.group("d") or cd.group("d2"))
        if 10 <= d <= 200:
            mat = re.search(r"PVC|HFT|SP[Iİ]RAL|GALVAN|ÇEL[Iİ]K|HFFR", t, re.IGNORECASE)
            lab.kind = "conduit"
            lab.width = d * unit_scale
            lab.spec = f"Ø{d}" + (f" {mat.group(0).upper()}" if mat else "")
            return lab
    return lab


FIXTURE_CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "armatur": ("Aydınlatma armatürü", [r"ARMAT", r"AYDINLATMA", r"LIGHT", r"LITE", r"LUMIN", r"LAMBA", r"LAMP", r"SPOT",
                                        r"DOWNLIGHT", r"FLORESAN", r"LED", r"PANEL\s*ARMAT", r"APLIK", r"APLİK", r"SARKIT"]),
    "acil": ("Acil aydınlatma / exit", [r"ACIL", r"ACİL", r"EXIT", r"EMERGENCY", r"YÖNLENDİRME", r"YONLENDIRME"]),
    "priz": ("Priz", [r"PR[Iİ]Z", r"SOCKET", r"RECEPT", r"OUTLET", r"\bUPS\s*PR"]),
    "anahtar": ("Anahtar", [r"ANAHTAR", r"SWITCH", r"KOMÜTATÖR", r"KOMUTATOR", r"VAVIEN", r"VAVİEN", r"DIMMER"]),
    "buat": ("Buat / kutu", [r"BUAT", r"KUTU", r"\bBOX", r"JUNCTION"]),
    "pano": ("Pano", [r"PANO", r"PANEL\b", r"TABLO", r"\bDB\b", r"SAYAÇ", r"SAYAC"]),
    "data": ("Data / telefon prizi", [r"DATA", r"RJ45", r"TELEFON", r"PHONE", r"\bTV\b", r"UYDU", r"NETWORK"]),
    "yangin": ("Yangın algılama", [r"DEDEKT", r"DETEKT", r"DETECTOR", r"S[Iİ]REN", r"SIREN", r"BUTON", r"YANGIN",
                                  r"DUMAN", r"SMOKE", r"FLA[SŞ]ÖR", r"FLASOR"]),
}
_FIXTURE_RE = {k: [re.compile(p, re.IGNORECASE) for p in pats] for k, (_, pats) in FIXTURE_CATEGORIES.items()}


def fixture_category(*names: str) -> str | None:
    for n in names:
        if not n:
            continue
        for key, pats in _FIXTURE_RE.items():
            if any(p.search(n) for p in pats):
                return key
    return None
