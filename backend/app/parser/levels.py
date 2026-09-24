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
# Temel kotları ("-3.10 Temel Alt Kot", "-1.70 Temel Üst Kot") kat seviyesi değildir. C1 ruhsatında bodrum
# planındaki temel alt kotu bodrumun kat kotu sanıldı (-3.10; gerçeği -3.33) ve üstelik parantezli
# yazılardan bulunan mutlak sisteme çevrilmeden kaldı. Kazı derinliği için ayrıca okunur (materials).
_FOUNDATION = re.compile(r"TEMEL|GROBETON|RADYE", re.IGNORECASE)
_BOTTOM_KOT = re.compile(r"ALT\s*KOT|\bT\.?\s*A\.?\s*K\b", re.IGNORECASE)
# Arazi / yol kotu taşıyan paftalar: binanın katlarını anlatmaz (bkz. building_levels)
SITE_PLAN_TYPES = {"mim_vaziyet", "pey_peyzaj", "alt_altyapi"}
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


# Temel paftası onlarca temel üst / alt kotu taşır (A blokları: -1.28, -0.68, +0.12, +0.52… "T.A.K", "T.Ü.K"
# kısaltmalarıyla). Bunlar kat seviyesi değildir: temel paftasından yalnız paftanın kendi kotu alınır.
FOUNDATION_PLAN_TYPES = {"sta_temel_kalip", "sta_temel_donati"}
# Detay paftası (temel / merdiven detayı) yerel kotlar taşır; yalnız kendi kotu sayılır.
KOT_ONLY_TYPES = FOUNDATION_PLAN_TYPES | {"mim_detay"}
# Kat planları: kendi kotu biliniyorsa yalnız o sayılır. Kalıp planında kiriş üstü / merdiven sahanlığı gibi ara
# kotlar (A blokları +11.65 planında +10.25, +10.65) kat dizisinde sahte kat doğuruyordu.
PER_FLOOR_TYPES = {"sta_kat_kalip", "sta_doseme_donati", "mim_kat_plani", "mim_tavan", "mim_doseme_kaplama"}


def building_levels(drawings, datum: float | None = None) -> list[float]:
    """Projedeki paftaların kot seviyeleri (kat kotları dahil) — vaziyet / peyzaj / altyapı paftaları hariç.

    Vaziyet planı yol, arazi ve bina ±0,00'ının araziye oturduğu kotu taşır; binanın kat dizisine
    karışırsa sahte katlar doğar (C1: vaziyetten gelen +0,82 ve genel bodrum planının +2,50'si kat
    yüksekliklerini 2,50 / 5,45 m yaptı; gerçeği 3,33 / 3,80 / 3,70 / 2,90)."""
    per: list[tuple[object, list[float]]] = []
    for d in drawings:
        tip = getattr(d, "plan_type", "") or ""
        if tip in SITE_PLAN_TYPES:
            continue
        vals: list[float] = []
        if d.kot is not None:
            vals.append(float(d.kot))
        if tip not in KOT_ONLY_TYPES and not (tip in PER_FLOOR_TYPES and d.kot is not None):
            vals.extend(float(v) for v in (d.levels or []))
        per.append((d, vals))
    # Bağıl → mutlak: kendi paftasında parantezli çift olmayan yazı yapı sıfırına göre olabilir (A1 mimarisi
    # "+3.80" = mutlak +7.95). Değer projenin başka hiçbir paftasında yokken "değer + ±0,00'ın mutlak kotu"
    # varsa bağıldır, çevrilir. Hiçbir kanıt yoksa dokunulmaz (tek sistemli projede eski davranış).
    out: list[float] = []
    for i, (d, vals) in enumerate(per):
        if datum and getattr(d, "level_offset", None) is None:
            others = {round(v, 2) for j, (_, vs) in enumerate(per) if j != i for v in vs}
            vals = [round(v + datum, 2) if round(v, 2) not in others and round(v + datum, 2) in others else v for v in vals]
        out.extend(vals)
    return out


def building_datum(drawings) -> float:
    """Yapı ±0,00'ının mutlak sistemdeki kotu: paftaların parantezli kot yazılarından (medyan); yoksa 0.

    Kotlar mutlak sisteme çevrildiği için "zemin kat = 0,00'a en yakın seviye" artık doğru değildir:
    C1 ruhsatında ±0,00 = +4,15 idi ve 0,00'a en yakın seviye bodrumun +0,82'siydi — zemin kat bodrumun
    kotunu, birinci kat zeminin kotunu aldı."""
    vals = sorted(float(d.level_offset) for d in drawings
                  if getattr(d, "level_offset", None) is not None and (getattr(d, "plan_type", "") or "") not in SITE_PLAN_TYPES)
    return vals[len(vals) // 2] if vals else 0.0


def building_floors(drawings, datum: float | None = None) -> list[float]:
    """Binanın kat seviyeleri.

    Omurga, kat planlarının (kalıp / mimari) **kendi kotlarıdır**: her biri "bu plan şu kottadır" diye açık bir
    beyandır. Öteki kotlar (kesit, kotu bilinmeyen planlar) yalnız omurganın boşluklarını doldurur — en çok
    tekrarlanan önce, omurgaya ve birbirine MIN_STOREY'den yakın olmamak şartıyla. Alttan açgözlü seçim
    (floor_levels) tek bir zayıf ara kotun (+10.25, ±0.00) hemen üstündeki asıl katı elemesine yol açıyordu.
    Omurga iki seviyeden azsa eski yönteme düşülür."""
    anchors = sorted({round(float(d.kot), 2) for d in drawings
                      if d.kot is not None and (getattr(d, "plan_type", "") or "") in PER_FLOOR_TYPES})
    if len(anchors) < 2:
        return floor_levels(building_levels(drawings, datum))
    from collections import Counter as _C
    destek = _C(round(v, 2) for v in building_levels(drawings, datum))
    floors = list(anchors)
    for v, _ in sorted(destek.items(), key=lambda kv: (-kv[1], kv[0])):
        if all(abs(v - f) >= MIN_STOREY for f in floors):
            floors.append(v)
    return sorted(floors)


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
    temel_disi = not _FOUNDATION.search(label or "")   # temel paftasının kendi kotu temel kotudur
    for raw in texts:
        t = (raw or "").replace("\\P", " ").strip()
        if not t or (temel_disi and _FOUNDATION.search(t)):
            continue
        m = _PAIR.match(t)
        has_kot = bool(_KOT_WORD.search(t)) and not _EXCLUDE.search(t)
        # temel paftasının kotu ÜST kotudur (kazı derinliği ondan hesaplanır); alt kot yazıları oy vermez
        votes = has_kot and not _DATUM.search(t) and (temel_disi or not _BOTTOM_KOT.search(t))
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
    # Paftada en sık geçen kot da kabul edilir: kat seviyeleri alttan açgözlü seçildiği için "+10.25" gibi bir
    # ara kot, 1,4 m üstündeki asıl kat kotunu (+11.65 — paftada 303 kez yazılı, "+11.65 KOTU" başlıklı) eliyordu.
    baskin = abs_vals.most_common(1)[0][0] if abs_vals else None
    for v, _ in kot_votes.most_common():
        if v in floor_set or v == baskin:
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
    if re.search(r"CATI\s*(KATI|ARASI)|TERAS\s*KATI", n):
        return 98            # çatı katı: çatının ALTINDAKİ kat (en üst seviye çatının kendisidir)
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

# ---------- Kazı kotları: kesitte "TABİİ ZEMİN KOTU -0.45", "KAZI TABANI -3.20", "TEMEL ALT KOTU -3.05"
# yazılıdır. Kazı derinliği varsayılana düşmesin diye önce bunlar okunur (services.excavation_depth).
_GROUND_WORDS = re.compile(r"TAB[İI]{1,2}\s*ZEM[İI]N|DO[ĞG]AL\s*ZEM[İI]N|MEVCUT\s*ZEM[İI]N|ZEM[İI]N\s*KOT", re.IGNORECASE)
_BOTTOM_WORDS = re.compile(r"KAZI\s*(TABAN|KOT|SEV[İI]YE)|TEMEL\s*ALT\s*KOT|GROBETON\s*(ALT|KOT)", re.IGNORECASE)
_DEPTH_WORDS = re.compile(r"KAZI\s*DER[İI]NL[İI][ĞG]", re.IGNORECASE)
MAX_EXC_TEXT = 80


def excavation_levels(texts: list[str]) -> dict:
    """Kazı için yazıdan okunan değerler: tabii zemin kotu, kazı tabanı kotu, doğrudan kazı derinliği.

    Döner: {"ground", "bottom", "depth"} (bulunamayan None) + her biri için kanıt yazısı."""
    out: dict = {"ground": None, "bottom": None, "depth": None,
                 "ground_note": "", "bottom_note": "", "depth_note": ""}
    for raw in texts:
        t = (raw or "").replace(chr(92) + "P", " ").strip()
        if not t or len(t) > MAX_EXC_TEXT:
            continue
        vals = [_val(v.group("v")) for v in _SIGNED.finditer(t)]
        if not vals:
            vals = [_val(v.group("v")) for v in _UNSIGNED.finditer(t)]
        vals = [v for v in vals if LEVEL_RANGE[0] <= v <= LEVEL_RANGE[1]]
        if not vals:
            continue
        if out["depth"] is None and _DEPTH_WORDS.search(t):
            d = abs(vals[0])
            if 0.2 <= d <= 30:
                out["depth"], out["depth_note"] = d, t[:60]
            continue
        if out["ground"] is None and _GROUND_WORDS.search(t):
            out["ground"], out["ground_note"] = vals[0], t[:60]
        if out["bottom"] is None and _BOTTOM_WORDS.search(t):
            out["bottom"], out["bottom_note"] = min(vals), t[:60]
    return out


# ---------- Pafta başlığındaki kat aralığı: "1.-5. NORMAL KAT PLANI", "2-7. KAT PLANI", "TİP KAT (5 KAT)"
# Bir tip kat planı birden çok katı temsil eder; kaç katı temsil ettiği çoğu projede başlığında yazar.
# Kat sayısı kullanıcıya SORULMAZ (ürün prensibi), önce burada aranır.
#
# `planset.normalize_title` burada KULLANILAMAZ: noktalama işaretlerini siliyor ve "1.-5." → "1 5"
# oluyor, yani aralığı aralık yapan ayraç kayboluyor. Bu yüzden yalnız Türkçe büyük harfe çevirilir.
_SPAN = re.compile(r"(?<!\d)(\d{1,2})\s*\.?\s*[-–—/]\s*(\d{1,2})\s*\.?\s*(?:NORMAL\s*|T[İI]P\s*)?KAT(?![A-ZİĞÜŞÖÇ])")
_COUNT = re.compile(r"\(\s*(\d{1,2})\s*(?:ADET\s*)?KAT\s*\)|(?<!\d)(\d{1,2})\s*KATLI")
TYPICAL_FLOOR = re.compile(r"NORMAL\s*KAT|T[İI]P\s*KAT|TEKRAR\s*KAT")


def _title_upper(label: str) -> str:
    """Türkçe büyük harf; noktalama korunur (aralık ayracı gerekli)."""
    return (label or "").replace("i", "İ").replace("ı", "I").upper()


def storey_span(label: str) -> tuple[int, int] | None:
    """Pafta başlığındaki kat aralığı: "1.-5. NORMAL KAT PLANI" → (1, 5). Yoksa None.

    Yalnız aralık döner; tek kat ("3. KAT PLANI") bu fonksiyonun işi değildir — onu floor_rank verir."""
    m = _SPAN.search(_title_upper(label))
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    return (lo, hi) if 0 <= lo < hi <= 60 else None


def storey_count_in_label(label: str) -> int | None:
    """Başlıkta açıkça yazan kat adedi: "TİP KAT (5 KAT)" → 5, "5 KATLI" → 5. Yoksa None."""
    m = _COUNT.search(_title_upper(label))
    if not m:
        return None
    v = int(m.group(1) or m.group(2))
    return v if 1 <= v <= 60 else None


def is_typical_floor(label: str) -> bool:
    """Bu pafta bir TİP / NORMAL kat planı mı (birden çok katı temsil eder)?"""
    return bool(TYPICAL_FLOOR.search(_title_upper(label)))


def level_for_rank(floors: list[float], rank: float, datum: float = 0.0) -> float | None:
    """Kat sirasini (floor_rank) kot dizisindeki seviyeye oturtur. Bilinmiyorsa None.

    Sira mutlak okunur: zemin (0) = dizide 0,00'a en yakin kot, 1. kat onun bir ustu, 1. bodrum bir alti.
    (Siralanmis listedeki konum kullanilamaz: yuklenmemis katlar dizide bosluk birakmaz, "zemin" ve
    "1. kat" planlari birbirinin kotunu alir.)"""
    if not floors:
        return None
    zero = min(range(len(floors)), key=lambda i: abs(floors[i] - datum))   # zemin: ±0,00'a (mutlak: datum) en yakın
    if rank == -100:                       # temel: en alt seviye
        return floors[0]
    if rank == 99:                         # cati: en ust kat seviyesi
        return floors[-1]
    if rank == 98:                         # cati kati: cati seviyesinin bir alti (A bloklari: +11.65, cati +15.65)
        return floors[-2] if len(floors) >= 3 else floors[-1]
    if rank != int(rank):                  # asma kat: sira disi
        return None
    i = zero + int(rank)
    return floors[i] if 0 <= i < len(floors) else None
