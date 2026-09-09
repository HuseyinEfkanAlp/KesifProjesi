"""Çizim yazılarından donatı çapı karışımı: "projede hangi nervürlü demir kullanılıyor".

Donatı ve kalıp planlarında donatı yazıları şu biçimlerde geçer:

    20ƒ14/20            20 adet Ø14, 20 cm aralıkla        (temel / döşeme donatısı)
    4X7ƒ12/10           4 × 7 adet Ø12, 10 cm aralıkla     (kolon etriyesi)
    20ƒ26               20 adet Ø26                        (kolon boyuna donatısı)
    ƒ14/18 Temel Üst Donatısı (Y Yönü)                      (adetsiz, aralıklı)
    P01 182ƒ8/10 etr. l=196                                 (poz yazısı, boyu ile)

Buradan **ağırlık** çıkarmak için çubuk boyu gerekir (poz yazılarında var, plan yazılarında yok); bu modül
ağırlık değil **çap karışımı** üretir: her çapın toplam çelik alanına (Σ adet × çap², boy varsa × boy) oranı.
Karışım, donatı tablosu olmayan elemanların oranla (beton × kg/m³) bulunan demirini çaplara bölmek için
kullanılır — böylece "çap karışık" tek kalem yerine Ø12 / Ø14 / Ø26 kalemleri ve ürün fiyatları çıkar.

Çap simgesi: projelerde Ø yerine ISOCPEUR fontunun `ƒ` (U+0192) ya da `Q` glyph'i, AutoCAD `%%c` kodu geçer.
"""
from __future__ import annotations

import re
from collections import defaultdict

DIA_SYM = r"(?:[ØøΦφ∅ƒ]|%%[cC]|Q)"
MIN_DIA, MAX_DIA = 6, 40

# "4X7ƒ12/10" (çarpımlı adet), "20ƒ14/20", "ƒ14/18", "ƒ12"
_MIX = re.compile(
    rf"(?:(?P<mult>\d{{1,2}})\s*[xX×]\s*)?(?P<n>\d{{1,4}})?\s*{DIA_SYM}\s*(?P<d>\d{{1,2}})"
    rf"(?:\s*/\s*(?P<s>\d{{1,3}}))?"
)
_LEN = re.compile(r"\bl\s*=\s*(\d{2,4})", re.IGNORECASE)
# yazıyı donatı yazısı saymayan bağlamlar (aks / kot / ölçek yazıları)
_SKIP = re.compile(r"ÖLÇEK|OLCEK|SCALE|KOTU|PAFTA", re.IGNORECASE)


def unit_area(dia_mm: int) -> float:
    """Çelik alanı ölçüsü (mm²'ye orantılı): ağırlık ∝ çap²."""
    return float(dia_mm) ** 2


def scan_texts(texts: list[str]) -> dict[int, float]:
    """Yazılardan çap -> çelik alanı payı (ham; normalize edilmemiş)."""
    out: dict[int, float] = defaultdict(float)
    for raw in texts:
        t = (raw or "").strip()
        if not t or len(t) > 160 or _SKIP.search(t):
            continue
        length_m = 0.0
        ml = _LEN.search(t)
        if ml:
            v = int(ml.group(1))
            length_m = v / 100.0 if v >= 20 else float(v)      # cm (yaygın); küçükse metre
        for m in _MIX.finditer(t):
            d = int(m.group("d"))
            if not (MIN_DIA <= d <= MAX_DIA):
                continue
            n = int(m.group("n")) * int(m.group("mult") or 1) if m.group("n") else 0.0
            if not n:
                s = m.group("s")
                # adetsiz aralıklı ("ƒ14/18"): metre başına 100/aralık çubuk; yalın "ƒ12": tek çubuk
                n = 100.0 / int(s) if s and int(s) > 0 else 1.0
            out[d] += n * unit_area(d) * (length_m or 1.0)
    return dict(out)


def normalize(raw: dict[int, float], min_share: float = 0.02) -> dict[int, float]:
    """Ham payları toplamı 1 olan karışıma çevirir; çok küçük paylar (yazım hatası, tek yazı) atılır."""
    total = sum(v for v in raw.values() if v > 0)
    if total <= 0:
        return {}
    mix = {d: v / total for d, v in raw.items() if v > 0 and v / total >= min_share}
    t2 = sum(mix.values())
    return {d: v / t2 for d, v in sorted(mix.items())} if t2 > 0 else {}


def scan_drawing(drawing) -> dict[int, float]:
    """Bir çizimin bütün yazılarından (blok içi dahil) ham çap payları."""
    return scan_texts([e.text for e in drawing.entities if e.kind == "text" and e.text])


def merge(mixes: list[dict[int, float]]) -> dict[int, float]:
    """Birden çok paftanın ham paylarını toplar."""
    out: dict[int, float] = defaultdict(float)
    for m in mixes:
        for d, v in (m or {}).items():
            out[int(d)] += float(v)
    return dict(out)


def split_by_dia(quantity: float, mix: dict[int, float]) -> list[tuple[int, float]]:
    """Bir miktarı çap karışımına göre böler: [(çap, miktar), …]. Karışım boşsa boş liste."""
    norm = normalize(mix) if mix and abs(sum(mix.values()) - 1.0) > 1e-6 else dict(mix or {})
    if not norm:
        return []
    return [(d, quantity * share) for d, share in sorted(norm.items()) if quantity * share > 0]
