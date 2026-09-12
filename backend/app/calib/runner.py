"""Korpusu ölçer ve referansla karşılaştırır.

Ölçüm yolu uygulamanınkiyle aynıdır (`analyze_file` → `compute_all`); kalibrasyonun kendi formülü yoktur,
yoksa neyi doğruladığımız belirsizleşir. Tek fark: veritabanı yok, kat yüksekliği korpustan gelir.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from ..parser.analyzer import analyze_file
from ..quantity.engine import ElementData, QuantityParams, compute_all
from ..services import dominant_beam_depth, dominant_slab_thickness
from .corpus import MEASURES, BIRIM, Corpus, Floor


@dataclass
class SheetResult:
    dosya: str
    birim: str
    birim_dogrulandi: bool
    elemanlar: dict[str, int]
    uyarilar: list[str]
    hata: str = ""


@dataclass
class Delta:
    olcu: str
    bizim: float
    referans: float

    @property
    def fark(self) -> float:
        return self.bizim - self.referans

    @property
    def yuzde(self) -> float:
        return 100.0 * self.fark / self.referans if self.referans else float("inf")

    def to_dict(self) -> dict:
        return {"olcu": self.olcu, "birim": BIRIM.get(self.olcu, ""), "bizim": round(self.bizim, 2),
                "referans": round(self.referans, 2), "fark": round(self.fark, 2), "yuzde": round(self.yuzde, 2)}


@dataclass
class FloorResult:
    kat: str
    kat_yuksekligi: float
    doseme_kalinligi: float
    kiris_yuksekligi: float | None
    net_doseme: bool
    elemanlar: dict[str, int]
    olculen: dict[str, float]
    farklar: list[Delta]
    paftalar: list[SheetResult]
    teshis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"kat": self.kat, "kat_yuksekligi": self.kat_yuksekligi, "doseme_kalinligi": self.doseme_kalinligi,
                "kiris_yuksekligi": self.kiris_yuksekligi, "net_doseme": self.net_doseme,
                "elemanlar": self.elemanlar, "olculen": {k: round(v, 2) for k, v in self.olculen.items()},
                "farklar": [d.to_dict() for d in self.farklar], "teshis": self.teshis,
                "paftalar": [{"dosya": s.dosya, "birim": s.birim, "birim_dogrulandi": s.birim_dogrulandi,
                              "elemanlar": s.elemanlar, "hata": s.hata} for s in self.paftalar]}


@dataclass
class RunResult:
    korpus: str
    proje: str
    guven: str
    katlar: list[FloorResult]
    saniye: float = 0.0

    @property
    def tum_farklar(self) -> list[Delta]:
        return [d for k in self.katlar for d in k.farklar]

    def skor(self) -> dict:
        """Tek bakışta durum: ölçü bazında ortalama mutlak sapma (%) ve en kötü sapma."""
        by: dict[str, list[float]] = {}
        for d in self.tum_farklar:
            by.setdefault(d.olcu, []).append(abs(d.yuzde))
        out = {m: {"ortalama_mutlak_yuzde": round(sum(v) / len(v), 2), "en_kotu_yuzde": round(max(v), 2),
                   "kat_sayisi": len(v)} for m, v in sorted(by.items())}
        hepsi = [abs(d.yuzde) for d in self.tum_farklar]
        out["_genel"] = {"ortalama_mutlak_yuzde": round(sum(hepsi) / len(hepsi), 2) if hepsi else 0.0,
                         "en_kotu_yuzde": round(max(hepsi), 2) if hepsi else 0.0, "kat_sayisi": len(hepsi)}
        return out

    def to_dict(self) -> dict:
        return {"korpus": self.korpus, "proje": self.proje, "guven": self.guven,
                "saniye": round(self.saniye, 1), "skor": self.skor(),
                "katlar": [k.to_dict() for k in self.katlar]}


def _measure_floor(floor: Floor, varsayilan_d: float = 0.15) -> tuple[list, list[SheetResult]]:
    """Katın bütün paftalarını okur; tek bir eleman listesi döndürür (kat bazında tek metraj)."""
    elements, sheets = [], []
    for path in floor.paftalar:
        try:
            r = analyze_file(path, label=floor.ad)
        except Exception as ex:                     # bozuk / okunamayan pafta kalibrasyonu durdurmasın
            sheets.append(SheetResult(path, "", False, {}, [], hata=f"{type(ex).__name__}: {ex}"))
            continue
        sheets.append(SheetResult(path, r.unit, r.unit_detected,
                                  dict(Counter(e.etype for e in r.elements)), list(r.warnings)))
        elements.extend(r.elements)
    return elements, sheets


def run_one(corpus: Corpus, varsayilan_d: float = 0.15) -> RunResult:
    t0 = time.time()
    kat_sonuc = []
    for floor in corpus.katlar:
        elements, sheets = _measure_floor(floor, varsayilan_d)
        d = floor.doseme_kalinligi or dominant_slab_thickness(elements) or varsayilan_d
        net = any(e.etype == "slab" and e.subtype == "net" for e in elements)
        beam_depth = dominant_beam_depth(elements)
        params = QuantityParams(storey_height=floor.kat_yuksekligi or 3.0, slab_thickness=d,
                                storey_count=floor.kat_sayisi, beam_full_height=net, beam_depth=beam_depth)
        lines = compute_all([ElementData.from_obj(e, id=i) for i, e in enumerate(elements)], params)

        toplam: dict[str, dict[str, float]] = {}
        for ln in lines:
            t = toplam.setdefault(ln.etype, {"concrete": 0.0, "formwork": 0.0})
            t["concrete"] += ln.total_concrete
            t["formwork"] += ln.total_formwork
        olculen = {}
        for olcu, (etypes, buyukluk) in MEASURES.items():
            olculen[olcu] = sum(toplam.get(e, {}).get(buyukluk, 0.0) for e in etypes)
        farklar = [Delta(olcu=m, bizim=olculen[m], referans=v) for m, v in sorted(floor.referans.items())]

        kat_sonuc.append(FloorResult(
            kat=floor.ad, kat_yuksekligi=params.storey_height, doseme_kalinligi=d, kiris_yuksekligi=beam_depth,
            net_doseme=net, elemanlar=dict(Counter(e.etype for e in elements)), olculen=olculen,
            farklar=farklar, paftalar=sheets))
    return RunResult(korpus=corpus.ad, proje=corpus.proje, guven=corpus.guven,
                     katlar=kat_sonuc, saniye=time.time() - t0)


def run_corpus(corpora: list[Corpus]) -> list[RunResult]:
    from .diagnose import diagnose
    out = []
    for c in corpora:
        r = run_one(c)
        for kat in r.katlar:
            kat.teshis = diagnose(kat)
        out.append(r)
    return out
