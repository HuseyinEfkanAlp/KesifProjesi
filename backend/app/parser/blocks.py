"""Yapı bloğu: bir çizimin hangi bloğa ait olduğu ("C1", "A4-A5") ya da bütün binaya ortak olduğu.

Yaygın tipoloji: bodrum ve zemin katlar **birleşik** (ortada koridor, tek yapı), üst katlar ayrı bloklara
(C1, C2, C3, C4) bölünür. Statik genelde tek ruhsat dosyasıdır; mimari blok blok ayrı dosyalarda gelir.
Program blok bilmezse iki şey sessizce bozulur: eksik bir bloğun mimarisi fark edilmez, ve aynı kottaki
farklı blok planları birbirini eler (bkz. services._plan_footprints).

Blok adı **dosya adında** durur ("KIYI İSTANBUL A4-A5 BLOK KALIP PLANLARI.dwg"); pafta başlıkları kot ve
plan tipi yazar ("+7.95 KOTU KALIP PLANI"), blok yazmaz. Bu yüzden önce dosya adı, sonra pafta başlığı okunur.

Boş dize ("") = ortak / tüm bina: bodrum, zemin, vaziyet, altyapı gibi bloklara bölünmeyen planlar.
"""
from __future__ import annotations

import re

ORTAK = ""
ORTAK_LABEL = "Ortak / tüm bina"

# "A4-A5 BLOK", "C1 BLOK", "B BLOK", "BLOK C2", "C-1 BLOĞU"; BLOKAJ'a takılmaz (\b BLOK'tan sonra harf istemez)
_NAME = r"[A-ZÇĞİÖŞÜ]{1,3}[- ]?\d{0,3}(?:\s*[-/]\s*[A-ZÇĞİÖŞÜ]?\d{1,3})?"
_BEFORE = re.compile(rf"(?<![A-ZÇĞİÖŞÜ0-9])({_NAME})\s*BLO[KĞ]", re.IGNORECASE)
# BLOK ile ad arasında ayırıcı şart: "BLOKAJ" blok adı üretmesin
_AFTER = re.compile(rf"BLO[KĞ]U?\s*(?:[:\-]\s*|\s+)({_NAME})(?![A-ZÇĞİÖŞÜ])", re.IGNORECASE)
# blok adı sanılmaması gereken kelimeler (dosya adında "… KALIP BLOK PLANI" gibi)
_NOT_A_NAME = re.compile(r"^(KAT|PLAN|TEMEL|KALIP|DONATI|MIM|STA|ELK|MEK|VE|VAZIYET|ZEMIN|BODRUM|NORMAL|TIP)$",
                         re.IGNORECASE)


def normalize(name: str) -> str:
    """Blok adını tek biçime indirir: "c-1" -> "C1", " a4 - a5 " -> "A4-A5".

    Harf ile sayı arasındaki tire atılır ("C-3" = "C3"); iki blok adını birleştiren tire korunur
    ("A4-A5" tek bir çizimde iki blok demektir, ayrı bir addır)."""
    n = re.sub(r"\s*[-/]\s*", "-", str(name or "").strip().upper())
    n = re.sub(r"[\s_]+", "", n).strip("-")
    parts = n.split("-")
    out = [parts[0]] if parts else []
    for prev, cur in zip(parts, parts[1:]):
        # önceki parça salt harfse (C + 3) tire yapıştırılır; ikisi de rakam içeriyorsa (A4 - A5) korunur
        out.append(cur if prev.isalpha() and cur.isdigit() else "-" + cur)
    return "".join(out)


def _clean(m: re.Match) -> str:
    n = normalize(m.group(1))
    return "" if not n or _NOT_A_NAME.match(n) else n


def detect_block(*texts: str) -> str:
    """Dosya adı / pafta başlığı gibi yazılardan blok adı; bulunamazsa "" (ortak).

    Sırayla bakılır: ilk eşleşen kazanır — dosya adını önce verin."""
    for t in texts:
        if not t:
            continue
        for pat in (_BEFORE, _AFTER):
            m = pat.search(str(t))
            if m and (n := _clean(m)):
                return n
    return ""


def detect_with_known(text: str, known: list[str]) -> str:
    """Blok adı "BLOK" kelimesi olmadan da geçebilir ("C2 MİMARİ KAT PLANI.dwg"): projede zaten bilinen
    blok adlarından biri yazıda tek başına duruyorsa o kabul edilir."""
    t = re.sub(r"[^A-Z0-9ÇĞİÖŞÜ]+", " ", str(text or "").upper())
    for name in sorted({normalize(k) for k in known if k}, key=len, reverse=True):
        # "C-3" da "C3" da aynı bloğu gösterir: tire isteğe bağlı aranır
        pat = r"[-\s]?".join(re.escape(c) for c in name if c != "-")
        if name and re.search(rf"(?<![A-Z0-9]){pat}(?![A-Z0-9])", t):
            return name
    return ""


def parts_of(name: str) -> set[str]:
    """Birleşik blok adının kapsadığı adlar: "A4-A5" -> {"A4-A5", "A4", "A5"}.

    Tek çizimde iki blok birlikte veriliyorsa ("A4-A5 BLOK KALIP PLANI") vaziyet planındaki ayrı "A4 BLOK"
    ve "A5 BLOK" yazıları eksik blok sayılmamalıdır."""
    n = normalize(name)
    return {n} | {p for p in n.split("-") if p} if n else set()


def covered_by(names) -> set[str]:
    """Bir blok listesinin kapsadığı bütün adlar (birleşik adlar parçalarıyla birlikte)."""
    out: set[str] = set()
    for n in names or []:
        out |= parts_of(n)
    return out


def block_label(name: str) -> str:
    return f"{name} bloğu" if name else ORTAK_LABEL


# ---------------------------------------------------------------- çizimden blok listesi
#
# Bir projenin kaç bloğu olduğu kullanıcıdan sorulmaz, çizimden okunur. İki ayrı kanıt vardır:
#
#   pafta başlığı   "A4-A5 BLOK"                 -> bu paftanın ait olduğu blok (keşfin kapsamı)
#   vaziyet planı   "A1 BLOK", "C2 BLOK", "N BLOK", ...  -> sitedeki bütün bloklar (aday liste)
#
# Vaziyet planı genelde bütün siteyi gösterir; keşif yalnız birkaç bloğu kapsayabilir. Bu yüzden **keşif
# kapsamı** = planı yüklenmiş bloklar; vaziyette görünüp planı olmayanlar yalnız hatırlatma olarak bildirilir
# ("vaziyet planında C3 BLOK da var, planı yüklenmedi").
#
# Tek bloklu yapıda hiçbir yerde "BLOK" geçmeyebilir: liste boş kalır, program tek yapı gibi çalışır.
_COUNT_MAX_LEN = 60


def scan_texts(texts) -> dict[str, int]:
    """Yazılardan blok adı sayımı: {"A1": 1, "C2": 1, "N": 3}. Yazı listesi ya da (yazı, yükseklik) çiftleri."""
    out: dict[str, int] = {}
    for row in texts or []:
        t = row[0] if isinstance(row, (tuple, list)) else row
        if not t or len(str(t)) > _COUNT_MAX_LEN:
            continue
        if n := detect_block(str(t)):
            out[n] = out.get(n, 0) + 1
    return out


def own_block(texts) -> str:
    """Paftanın kendi bloğu: blok adı geçen yazıların **en büyüğü** (pafta başlığı en iri yazıdır).

    texts: (yazı, yükseklik) çiftleri. Yükseklik yoksa ilk eşleşen alınır."""
    best, best_h = "", -1.0
    for row in texts or []:
        t, h = (row[0], float(row[1] or 0.0)) if isinstance(row, (tuple, list)) else (row, 0.0)
        if not t or len(str(t)) > _COUNT_MAX_LEN:
            continue
        if (n := detect_block(str(t))) and h > best_h:
            best, best_h = n, h
    return best


def scan_drawing(drawing) -> dict[str, int]:
    return scan_texts([(e.text, e.height) for e in drawing.entities if e.kind == "text" and e.text])


def own_block_of_drawing(drawing) -> str:
    return own_block([(e.text, e.height) for e in drawing.entities if e.kind == "text" and e.text])
