"""Kalibrasyon korpusu: (paftalar + bilinen doğru metraj) çiftleri.

Bir korpus dosyası tek bir projedir; katlara bölünür çünkü referans metraj neredeyse her zaman kat bazındadır
(müellifin icmal tablosu da öyle). Her katın kendi kat yüksekliği vardır — kalibrasyonun en sık yanıltıcı
değişkeni budur, o yüzden korpusta açıkça yazılır, tahmin edilmez.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Referansın ne kadar sağlam olduğu. "eşleşti" demek "doğru" demek değildir; hangi kanıtla eşleştiğimiz önemli.
GUVEN = {
    "cizimden": "Çizimin kendi metraj tablosundan okundu (müellifin sayısı)",
    "aktarim": "Çizimdeki tablodan elle aktarıldı; bağımsız yeniden ölçülmedi",
    "bagimsiz": "Bağımsız ölçüm / hakediş icmali",
}

# Karşılaştırılabilen ölçüler: referans anahtarı -> (eleman tipleri, hangi büyüklük)
MEASURES: dict[str, tuple[tuple[str, ...], str]] = {
    "kolon_perde_beton_m3": (("column", "shear_wall"), "concrete"),
    "kolon_perde_kalip_m2": (("column", "shear_wall"), "formwork"),
    "kiris_beton_m3": (("beam",), "concrete"),
    "kiris_kalip_m2": (("beam",), "formwork"),
    "doseme_beton_m3": (("slab",), "concrete"),
    "doseme_kalip_m2": (("slab",), "formwork"),
    "temel_beton_m3": (("foundation",), "concrete"),
    "beton_m3": (("column", "shear_wall", "beam", "slab", "foundation", "parapet"), "concrete"),
    "kalip_m2": (("column", "shear_wall", "beam", "slab", "foundation", "parapet"), "formwork"),
}

BIRIM = {m: ("m³" if m.endswith("_m3") else "m²") for m in MEASURES}


@dataclass
class Floor:
    """Bir kat: paftaları, kat yüksekliği ve bilinen doğru metrajı."""
    ad: str
    paftalar: list[str]
    kat_yuksekligi: float | None = None
    doseme_kalinligi: float | None = None
    kat_sayisi: int = 1
    referans: dict[str, float] = field(default_factory=dict)
    not_: str = ""

    def bilinmeyen_olculer(self) -> list[str]:
        return [k for k in self.referans if k not in MEASURES]


@dataclass
class Corpus:
    ad: str
    proje: str
    kaynak: str
    guven: str
    katlar: list[Floor]
    not_: str = ""
    yol: Path | None = None

    @property
    def guven_aciklama(self) -> str:
        return GUVEN.get(self.guven, self.guven)


def corpus_dir() -> Path:
    """backend/calib/corpus — korpus tanımlarının yeri."""
    return Path(__file__).resolve().parents[2] / "calib" / "corpus"


def _resolve(p: str, base: Path) -> str:
    """Korpustaki yollar depo köküne göredir; mutlak yol da kabul edilir."""
    q = Path(p)
    return str(q if q.is_absolute() else (base / q))


def load_corpus(path: str | Path, repo_root: Path | None = None) -> Corpus:
    path = Path(path)
    root = repo_root or Path(__file__).resolve().parents[3]
    raw = json.loads(path.read_text(encoding="utf-8"))
    katlar = []
    for k in raw.get("katlar", []):
        katlar.append(Floor(ad=k["ad"], paftalar=[_resolve(p, root) for p in k.get("paftalar", [])],
                            kat_yuksekligi=k.get("kat_yuksekligi"),
                            doseme_kalinligi=k.get("doseme_kalinligi", raw.get("varsayilan", {}).get("doseme_kalinligi")),
                            kat_sayisi=int(k.get("kat_sayisi", 1)),
                            referans={kk: float(vv) for kk, vv in (k.get("referans") or {}).items()},
                            not_=k.get("not", "")))
    c = Corpus(ad=path.stem, proje=raw.get("proje", path.stem), kaynak=raw.get("kaynak", ""),
               guven=raw.get("guven", "aktarim"), katlar=katlar, not_=raw.get("not", ""), yol=path)
    bilinmeyen = sorted({m for k in katlar for m in k.bilinmeyen_olculer()})
    if bilinmeyen:
        raise ValueError(f"{path.name}: tanınmayan referans ölçüsü {bilinmeyen}; MEASURES'a ekleyin")
    return c


def load_all(directory: Path | None = None) -> list[Corpus]:
    d = directory or corpus_dir()
    return [load_corpus(p) for p in sorted(d.glob("*.json"))] if d.exists() else []
