"""Statik pafta etiketlerini çözümler.

Örnekler: "S1 30/60", "S101 40x40", "K1001 (100/45)", "(100/100)", "P1 20/250", "D101 h=15",
"d=12", "D:20cm", "TK1 60/80", "Ø8/15", "8Φ16", "%%c12". Boyutlar varsayılan olarak cm kabul edilir.
Ad ve kesit ayrı yazılarda olabilir ("S1001" ve "(100/100)"); birleştirme LabelIndex'te yapılır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DIA_CHARS = r"[ØøΦφ∅]"

# Eleman tipi ön ekleri (Türkçe statik yaygın kullanım)
PREFIX_TYPES: dict[str, str] = {
    "S": "column", "SP": "column", "C": "column",
    "K": "beam", "B": "beam", "BK": "beam", "KB": "beam",
    "P": "shear_wall", "W": "shear_wall",
    "D": "slab", "DD": "slab",          # DD: düşük döşeme
    "T": "foundation", "TK": "foundation", "ST": "foundation", "R": "foundation", "RT": "foundation",
    "RD": "foundation",                 # RD1 / RD2: radye bölgesi
}
# Ad ön ekine eklenen kat kodu: SB (bodrum), SZ (zemin); rakamlı katlar ("S1094") sayı kısmında kalır
FLOOR_CODES = ("B", "Z")


def prefix_type(prefix: str) -> str | None:
    """'S' -> column, 'SB'/'SZ' -> column (kat kodlu), 'DDB' -> slab; bilinmiyorsa None."""
    p = prefix.upper()
    if p in PREFIX_TYPES:
        return PREFIX_TYPES[p]
    if len(p) >= 2 and p[-1] in FLOOR_CODES and p[:-1] in PREFIX_TYPES:
        return PREFIX_TYPES[p[:-1]]
    return None

_NUM = r"\d+(?:[.,]\d+)?"
_NAME_DIMS = re.compile(
    rf"^\s*(?P<prefix>[A-ZÇĞİÖŞÜ]{{1,3}})\s*-?\s*(?P<num>\d+[A-Za-z']?)\s*[:\-]?\s*\(?\s*"
    rf"(?P<b>{_NUM})\s*[/xX×*]\s*(?P<h>{_NUM})\s*\)?",
)
_NAME_ONLY = re.compile(r"^\s*(?P<prefix>[A-ZÇĞİÖŞÜ]{1,3})\s*-?\s*(?P<num>\d+[A-Za-z']?)\b")
_DIMS_ONLY = re.compile(
    rf"(?<![\dØøΦφ∅/.,])\(?\s*(?P<b>{_NUM})\s*[/xX×*]\s*(?P<h>{_NUM})\s*\)?(?!\s*[/xX×])"
)
_THICK = re.compile(rf"(?:^|[\s(,;])[hHdD]\s*[=:]\s*(?P<t>{_NUM})\s*(?:cm)?")
_REBAR_COUNT = re.compile(rf"(?P<n>\d+)\s*{DIA_CHARS}\s*(?P<d>\d+)")
_REBAR_SPACING = re.compile(rf"{DIA_CHARS}\s*(?P<d>\d+)\s*/\s*(?P<s>\d+)")
_ELEVATION = re.compile(rf"^\s*[+\-±]\s*{_NUM}\s*$")   # "+4.00" kot yazısı
_BARE_CM = re.compile(rf"^\s*(?P<t>{_NUM})\s*cm\s*$", re.IGNORECASE)   # "15cm": döşeme/radye kalınlığı


@dataclass
class Label:
    raw: str
    name: str | None = None
    type_hint: str | None = None
    b: float | None = None          # metre
    h: float | None = None          # metre
    thickness: float | None = None  # metre
    rebar: list[dict] = field(default_factory=list)

    @property
    def has_dims(self) -> bool:
        return self.b is not None and self.h is not None

    @property
    def is_meaningful(self) -> bool:
        return bool(self.name or self.has_dims or self.thickness or self.rebar)

    def merged_with(self, other: "Label | None") -> "Label":
        """Ad taşıyan etiketi kesit/kalınlık taşıyan başka bir etiketle birleştirir."""
        if other is None:
            return self
        m = Label(raw=self.raw if self.raw == other.raw else f"{self.raw} {other.raw}",
                  name=self.name or other.name, type_hint=self.type_hint or other.type_hint,
                  b=self.b if self.has_dims else other.b, h=self.h if self.has_dims else other.h,
                  thickness=self.thickness if self.thickness is not None else other.thickness,
                  rebar=self.rebar or other.rebar)
        return m


def normalize(text: str) -> str:
    t = text.replace("%%c", "Ø").replace("%%C", "Ø").replace("%%d", "°").replace("%%u", "")
    t = re.sub(r"\\[A-Za-z][^;]*;", "", t)   # kalan MTEXT format kodları
    t = t.replace("\\P", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", t).strip()


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_label(text: str, label_unit_scale: float = 0.01) -> Label:
    """Etiketi çözümler. label_unit_scale: etiketteki sayıların metreye çarpanı (cm -> 0.01)."""
    t = normalize(text)
    lab = Label(raw=t)
    if _ELEVATION.match(t):
        return lab

    # Donatı ifadeleri ("8Ø16", "Ø8/15") boyut olarak yanlış okunmasın diye önce ayıklanır
    stripped = _REBAR_SPACING.sub(" ", _REBAR_COUNT.sub(" ", t))

    m = _NAME_DIMS.match(stripped)
    if m:
        prefix = m.group("prefix").upper()
        lab.name = f"{prefix}{m.group('num')}"
        lab.type_hint = prefix_type(prefix)
        lab.b = _num(m.group("b")) * label_unit_scale
        lab.h = _num(m.group("h")) * label_unit_scale
    else:
        m = _NAME_ONLY.match(stripped)
        if m:
            prefix = m.group("prefix").upper()
            if prefix_type(prefix):
                lab.name = f"{prefix}{m.group('num')}"
                lab.type_hint = prefix_type(prefix)
        d = _DIMS_ONLY.search(stripped)
        if d:
            lab.b = _num(d.group("b")) * label_unit_scale
            lab.h = _num(d.group("h")) * label_unit_scale

    th = _THICK.search(stripped) or _BARE_CM.match(stripped)
    if th:
        lab.thickness = _num(th.group("t")) * label_unit_scale

    for r in _REBAR_COUNT.finditer(t):
        lab.rebar.append({"count": int(r.group("n")), "dia_mm": int(r.group("d"))})
    for r in _REBAR_SPACING.finditer(t):
        lab.rebar.append({"dia_mm": int(r.group("d")), "spacing_cm": int(r.group("s"))})
    return lab
