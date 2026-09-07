"""Çizimdeki poz listeleri (doğrama / mahal tabloları) — yazıdan adet okuma.

Doğrama paftalarında her poz bir yazı bloğudur:
    "Poz: EMP1\\nAdet: 82"        "Poz: EMP3\\n9 Adet AÇILIR KAPI"        "Poz: EMP2\\nAdet: 2\\n(FOTOSELLİ KAPI)"
Ayrıştırıcı poz kodu, adet ve açıklamayı verir; keşifte her poz ayrı kalem olur (DOGRAMA:EMP1 = 82 adet).
Aynı poz birden çok yerde yazılıyorsa (plan + pafta) en büyük adet alınır, tekrar sayılmaz.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_POZ = re.compile(r"POZ\s*[:.]?\s*(?P<poz>[A-Z]{1,4}\s?-?\d+[A-Z]?(?:['’])?)", re.IGNORECASE)
_ADET = re.compile(r"ADET\s*[:.]?\s*(?P<n>\d+)|(?P<n2>\d+)\s*(?:AD\.?|ADET)\b", re.IGNORECASE)
_PAREN = re.compile(r"\(([^)]*)\)")


@dataclass
class ScheduleRow:
    poz: str
    count: int
    note: str = ""
    raw: str = ""
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"poz": self.poz, "count": self.count, "note": self.note, "raw": self.raw}


def _norm_poz(p: str) -> str:
    return re.sub(r"\s+", "", p.upper()).replace("’", "'")


def parse_schedule_text(text: str) -> ScheduleRow | None:
    """Tek bir yazı bloğundan poz + adet. Adet yazmıyorsa None (yalnız etiket)."""
    t = (text or "").replace("\\P", "\n")
    m = _POZ.search(t)
    if not m:
        return None
    rest = t[m.end():]
    poz = _norm_poz(m.group("poz"))
    a = _ADET.search(rest)
    if not a:
        # "Poz: EMP914" gibi bitişik yazımda kod + adet ayrılır: EMP9 14 (ilk rakam kod, kalanı adet; düşük güven)
        tail = re.match(r"^\s*(\d{1,3})\b", rest)
        if tail:
            n = int(tail.group(1))
        else:
            dm = re.match(r"^([A-Z]+-?)(\d)(\d{1,2})([A-Z]?'?)$", poz)
            if not dm or dm.group(4):
                return None
            poz, n = dm.group(1) + dm.group(2), int(dm.group(3))
    else:
        n = int(a.group("n") or a.group("n2"))
    note = " ".join(x.strip() for x in _PAREN.findall(rest)) or re.sub(r"ADET\s*[:.]?\s*\d+|\d+\s*(ADET|AD\.?)(?=\s|$)", "", rest, flags=re.IGNORECASE).strip()
    note = re.sub(r"\s+", " ", note).strip(" -:")
    return ScheduleRow(poz, n, note[:60], re.sub(r"\s+", " ", t).strip()[:80])


def parse_schedule(texts: list[str], source: str = "") -> list[ScheduleRow]:
    """Yazı listesinden poz tablosu; aynı poz tekrarlanırsa en büyük adet."""
    rows: dict[str, ScheduleRow] = {}
    for txt in texts:
        r = parse_schedule_text(txt)
        if not r:
            continue
        cur = rows.get(r.poz)
        if cur is None or r.count > cur.count:
            if cur is not None:
                r.sources = cur.sources
            rows[r.poz] = r
        rows[r.poz].sources.append(source)
    return sorted(rows.values(), key=lambda r: (re.sub(r"\d+", "", r.poz), int(re.search(r"\d+", r.poz).group()) if re.search(r"\d+", r.poz) else 0, r.poz))


def merge_schedules(per_drawing: list[list[ScheduleRow]]) -> list[ScheduleRow]:
    out: dict[str, ScheduleRow] = {}
    for rows in per_drawing:
        for r in rows:
            cur = out.get(r.poz)
            if cur is None or r.count > cur.count:
                out[r.poz] = r
    return list(out.values())
