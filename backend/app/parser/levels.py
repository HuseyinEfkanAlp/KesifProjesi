"""Kot yazılarından kat seviyeleri ve kat yükseklikleri.

Planlarda ve kesitlerde kotlar "+4.15", "±0,00", "-3.33(+0.82)", "+0.00 (+4.15 sıfır kotu)", "+10.65 DÖŞEME KOTU",
"15.65 KOTU PLANI" biçiminde yazılır. İki sistem birlikte kullanılabilir: parantez dışı (yapı sıfırına göre) ve parantez içi
(mutlak / vaziyet). Parantezli yazılardan iki sistem arasındaki ofset bulunur; tüm değerler parantez içi (mutlak) sisteme çevrilir.
Kat seviyeleri: birbirinden en az MIN_STOREY (2 m) uzak seviyeler (kaplama / peyzaj / asma kat kotları elenir);
kat yüksekliği = ardışık seviyelerin farkı.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import median

_NUM = r"[+\-±]?\s?\d{1,3}[.,]\d{2}"
_PAIR = re.compile(rf"^\s*(?P<x>{_NUM})\s*\(\s*(?P<y>{_NUM})", re.IGNORECASE)
_SIGNED = re.compile(r"(?<![\d.,])(?P<v>[+\-±]\s?\d{1,3}[.,]\d{2})(?![\d])")
_UNSIGNED = re.compile(r"(?<![\d.,+\-±])(?P<v>\d{1,3}[.,]\d{2})(?![\d])")
_KOT_WORD = re.compile(r"\bKOT(U|LARI)?\b|S[Iİ]FIR\s*KOT|D[OÖ][SŞ]EME\s*KOT|LEVEL", re.IGNORECASE)
_EXCLUDE = re.compile(r"PEYZAJ|ZEM[Iİ]N\s*KOT|TABAN\s*KOT|SU\s*KOT|KAZI", re.IGNORECASE)
# yapı sıfır kotu referansı bütün paftalarda yazılır; paftanın kat kotu için oy sayılmaz
_DATUM = re.compile(r"S[Iİ]FIR\s*KOT", re.IGNORECASE)
MIN_STOREY = 2.0
LEVEL_RANGE = (-30.0, 200.0)


def _val(s: str) -> float:
    s = s.replace("±", "").replace(" ", "").replace(",", ".")
    return float(s)


@dataclass
class LevelScan:
    levels: list[float] = field(default_factory=list)     # mutlak sistemde tüm seviyeler (sıralı, tekil)
    floors: list[float] = field(default_factory=list)     # kat seviyeleri (≥ MIN_STOREY aralıklı)
    offset: float | None = None                            # parantez içi − parantez dışı (iki kot sistemi arasındaki fark)
    kot: float | None = None                               # bu paftanın kat kotu ("… KOTU" yazısı) — mutlak sistem
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def storey_heights(self) -> list[float]:
        return [round(b - a, 2) for a, b in zip(self.floors, self.floors[1:])]


def floor_levels(levels: list[float], min_gap: float = MIN_STOREY) -> list[float]:
    out: list[float] = []
    for v in sorted(set(round(x, 2) for x in levels)):
        if not out or v - out[-1] >= min_gap:
            out.append(v)
    return out


def parse_levels(texts: list[str], label: str = "") -> LevelScan:
    pairs: list[tuple[float, float]] = []
    bare: list[tuple[float, bool, bool]] = []   # (değer, KOT sözcüğü var mı, işaretli mi)
    kot_votes: Counter = Counter()
    for raw in texts:
        t = (raw or "").replace("\\P", " ").strip()
        if not t:
            continue
        m = _PAIR.match(t)
        has_kot = bool(_KOT_WORD.search(t)) and not _EXCLUDE.search(t)
        votes = has_kot and not _DATUM.search(t)
        if m:
            try:
                x, y = _val(m.group("x")), _val(m.group("y"))
            except ValueError:
                continue
            if LEVEL_RANGE[0] <= x <= LEVEL_RANGE[1] and LEVEL_RANGE[0] <= y <= LEVEL_RANGE[1]:
                pairs.append((x, y))
                if votes:
                    kot_votes[round(y, 2)] += 1
            continue
        vals = [_val(v.group("v")) for v in _SIGNED.finditer(t)]
        signed = bool(vals)
        if not vals and has_kot:
            vals = [_val(v.group("v")) for v in _UNSIGNED.finditer(t)]
        for v in vals:
            if LEVEL_RANGE[0] <= v <= LEVEL_RANGE[1]:
                bare.append((v, has_kot, votes))
    scan = LevelScan()
    abs_vals: Counter = Counter()
    if pairs:
        scan.offset = round(median(y - x for x, y in pairs), 2)
        abs_set = {round(y, 2) for _, y in pairs}
        rel_set = {round(x, 2) for x, _ in pairs}
        for _, y in pairs:
            abs_vals[round(y, 2)] += 1
        for v, has_kot, votes in bare:
            r = round(v, 2)
            if r in abs_set:
                abs_vals[r] += 1
                if votes:
                    kot_votes[r] += 1
            elif r in rel_set:
                abs_vals[round(r + scan.offset, 2)] += 1
                if votes:
                    kot_votes[round(r + scan.offset, 2)] += 1
            elif has_kot:
                abs_vals[r] += 1
                if votes:
                    kot_votes[r] += 1
            # iki sisteme de uymayan işaretli değer: hangi sistemde olduğu belirsiz, sayılmaz
    else:
        for v, has_kot, votes in bare:
            abs_vals[round(v, 2)] += 1
            if votes:
                kot_votes[round(v, 2)] += 1
    label_kot = kot_from_label(label)
    if label_kot is not None:
        kot_votes[round(label_kot, 2)] += 5
        abs_vals[round(label_kot, 2)] += 1
    scan.levels = sorted(abs_vals)
    scan.floors = floor_levels(scan.levels)
    scan.counts = {f"{k:+.2f}": n for k, n in sorted(abs_vals.items())}
    # paftanın kat kotu: kat seviyesi olan (kaplama / peyzaj kotu olmayan) en çok oy alan değer
    floor_set = set(scan.floors)
    for v, _ in kot_votes.most_common():
        if v in floor_set:
            scan.kot = v
            break
    return scan


_LABEL_KOT = re.compile(r"(?P<v>[+\-±]?\s?\d{1,3}[.,]\d{2})\s*KOT", re.IGNORECASE)


def kot_from_label(label: str) -> float | None:
    """'+7.95 KOTU KALIP PLANI', '15.65 KOTU PLANI' -> 7.95 / 15.65 (mutlak sistem varsayılır)."""
    m = _LABEL_KOT.search(label or "")
    if not m:
        return None
    try:
        return _val(m.group("v"))
    except ValueError:
        return None


# ---------------------------------------------------------------- kat sırası (kot yoksa plan adından)

_ORDINALS = {"BIRINCI": 1, "IKINCI": 2, "UCUNCU": 3, "DORDUNCU": 4, "BESINCI": 5, "ALTINCI": 6, "YEDINCI": 7, "SEKIZINCI": 8,
             "DOKUZUNCU": 9, "ONUNCU": 10}


def floor_rank(label: str) -> float | None:
    """Plan adından kat sırası: temel −100, N. bodrum −N, zemin 0, asma 0.5, birinci 1 … çatı 99. Bilinmiyorsa None."""
    from ..planset import normalize_title
    n = normalize_title(label or "")
    if not n:
        return None
    if "TEMEL" in n or re.search(r"\bTEM\b", n):
        return -100
    m = re.search(r"\b[A-Z]{2,4}[-_ ](\d{1,2})\b", n)     # STA-03, MIM-00: dosya adındaki kat numarası
    if m and not re.search(r"\d\s*\.\s*(KAT|NORMAL)", n):
        return int(m.group(1))
    m = re.search(r"(\d+)\s*\.?\s*BODRUM", n)
    if m:
        return -int(m.group(1))
    if "BODRUM" in n:
        return -1
    if "CATI" in n or "TERAS" in n:
        return 99
    if "ASMA" in n:
        return 0.5
    if "ZEMIN" in n or "GIRIS" in n:
        return 0
    for word, k in _ORDINALS.items():
        if re.search(rf"\b{word}\b", n):
            return k
    m = re.search(r"(\d+)\s*\.?\s*(KAT|NORMAL)", n)
    if m:
        return int(m.group(1))
    if "NORMAL" in n or "TIP" in n:
        return 1
    return None
