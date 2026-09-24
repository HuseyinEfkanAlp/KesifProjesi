"""Kullanım türü: katın ne olduğu (dükkân / konut / otel / ofis / sosyal tesis) çizimin yazılarından.

Metrajı değiştirir: AVM'de dükkân içi kiracının işidir (kaba teslim — sıva, boya, tavan yok), konutta her
oda tam teslim edilir. Karma yapıda (zeminde dükkân, üstte daire) kural **kat kat** uygulanır; proje
geneline tek bir "AVM" düğmesi konutu da kaba teslim sayardı.

Kullanıcıya sorulmaz, plandan okunur: mahal yazıları ("DÜKKAN 3", "DAİRE 5", "YATAK ODASI", "2+1", "OTEL
ODASI", "OFİS"), kiracı yazısı, antetteki "KONUT + TİCARET". Alan çizgisinden dükkân sayılan bölgeler
(parser/zones.py) de ticari kanıttır. Kanıt yoksa kat "belirsiz" kalır ve eski davranış sürer.
"""
from __future__ import annotations

import re

from ..planset import normalize_title

# Tür → yazı kalıbı (normalize_title çıktısı üzerinde: Türkçe harfsiz, büyük harf)
PATTERNS: dict[str, re.Pattern] = {
    "ticari": re.compile(r"\b(DUKKAN\w*|MAGAZA\w*|MARKET|VITRIN\w*|SHOWROOM|KIRACI\w*|AVM|ALISVERIS MERKEZI\w*"
                         r"|TICARI|TICARET\w*)\b"),
    # "VERGİ DAİRESİ" / "DAİRE BAŞKANLIĞI" her ruhsat antedinde var: daire yalnız yalın hâliyle ("DAİRE 5");
    # "YATAR DAİRE(2)" geometri adıdır (daire kesitli depo / boru), konut değil — C1 genel bodrum planı
    "konut": re.compile(r"\b((?<!YATAR )(?<!DIK )DAIRE(?! BASKANLIG)\b|KONUT\w*|YATAK ODASI|EBEVEYN\w*|COCUK ODASI)\b"
                        r"|(?<![\d+])[1-6] ?\+ ?[01](?![\d+])"),
    "otel": re.compile(r"\b(OTEL\w*|RESEPSIYON|KONAKLAMA)\b"),
    "ofis": re.compile(r"\b(OFIS\w*|BURO\w*|TOPLANTI (ODASI|SALONU)|YONETICI ODASI)\b"),
    "sosyal": re.compile(r"\b(RESTORAN\w*|KAFE\w*|CAFE|SPOR SALONU|FITNESS|BALO SALONU|SOSYAL TESIS\w*|KULUP\w*)\b"),
}
KIND_LABEL = {"ticari": "Ticari (dükkân / mağaza)", "konut": "Konut", "otel": "Otel", "ofis": "Ofis",
              "sosyal": "Sosyal tesis / yeme-içme", "": "Belirsiz"}
# Kaba teslim kuralı yalnız bu türün katlarına uygulanır; belirsiz kat eski davranışla (dükkân katı) sayılır.
SHELL_KINDS = ("ticari", "")


def scan_texts(texts: list[str]) -> dict[str, dict]:
    """Yazılardan tür başına kanıt: {"ticari": {"n": 12, "ornek": ["DÜKKAN 3", …]}}. Aynı yazı bir kez sayılır."""
    out: dict[str, dict] = {}
    for raw in dict.fromkeys(t.strip() for t in texts if t and t.strip()):
        if len(raw) > 120:            # uzun not paragrafları ("… konut alanlarında …") kanıt sayılmaz
            continue
        if re.search(r"\d\s*[*xX×]\s*\d", raw):   # ölçü yazısı ("400*4000cm"): mahal adı değil
            continue
        t = normalize_title(raw)
        for kind, pat in PATTERNS.items():
            if pat.search(t):
                e = out.setdefault(kind, {"n": 0, "ornek": []})
                e["n"] += 1
                if len(e["ornek"]) < 3:
                    e["ornek"].append(" ".join(raw.split())[:30])
    return out


def scan_usage(drawing) -> dict[str, dict]:
    """Paftanın bütün yazılarından (blok içi dahil) kullanım kanıtı."""
    return scan_texts([e.text for e in drawing.entities if e.kind == "text" and e.text])


def floor_usage(usage: dict | None, zones: list[dict] | None = None) -> tuple[str, str]:
    """(tür, gerekçe). Ticari kanıt en az ötekiler kadarsa ticari (zeminde dükkân + konut lobisi = dükkân katı);
    değilse en çok kanıtlı tür. Kanıt yoksa ("", "")."""
    say = {k: int((usage or {}).get(k, {}).get("n") or 0) for k in PATTERNS}
    ornek = {k: list((usage or {}).get(k, {}).get("ornek") or []) for k in PATTERNS}
    dz = sum(1 for z in (zones or []) if z.get("kind") == "dukkan")
    if dz:
        say["ticari"] += dz
        ornek["ticari"].append(f"{dz} dükkân bölgesi (alan çizgisi)")
    if not any(say.values()):
        return "", ""
    tur = "ticari" if say["ticari"] and say["ticari"] >= max(say.values()) else max(say, key=lambda k: say[k])
    return tur, f"{say[tur]} kanıt: " + ", ".join(f"“{x}”" if "bölgesi" not in x else x for x in ornek[tur][:3])
