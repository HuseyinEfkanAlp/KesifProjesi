"""Birim fiyat listesini (ÇŞB / firma) metinden okur ve poz numarasına göre fiyat bankasına yazar.

Canlı kullanımda asıl tıkanma fiyat girişidir: keşifte 100+ kalem çıkar, hepsine elle fiyat girmek
kimsenin yapmayacağı bir iştir. Ama kalemlerin çoğunda **ÇŞB poz numarası** zaten var (A4-A5'te 78
kalemden 47'si) ve her müteahhitte o yılın birim fiyat listesi bulunur. Liste bir kez yapıştırılır,
eşleşme poz numarasından yapılır.

Gerçek listeler tek biçimde değildir; ayraç sekme, noktalı virgül, virgül ya da sadece boşluk olabilir:

    15.150.1006;Beton santralinde üretilen C 30/37;m³;3.250,00
    15.180.1003  Ahşap kalıp yapılması     m2     485,50
    15.160.1004 | Nervürlü çelik hasır Ø14-28 | ton | 28.400,00

Bu yüzden ayraca güvenilmez: **satırdaki poz numarası ve son sayı** aranır, aradaki metin addır.
Sayı biçimi Türkçedir (binlik nokta, ondalık virgül) ama "3250.00" da kabul edilir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ÇŞB poz numarası: 15.150.1006 / 35.140.3161 (iki ya da üç grup). Y.16.052 gibi eski biçim de kabul edilir.
POZ = re.compile(r"\b(?:[A-ZÇĞİÖŞÜ]\.)?\d{2}\.\d{2,3}(?:\.\d{3,4})?\b")
# Sayı: 3.250,00 | 3250,00 | 3250.00 | 3250
NUM = re.compile(r"-?\d{1,3}(?:\.\d{3})*(?:,\d+)?$|-?\d+(?:[.,]\d+)?$")
BIRIM = re.compile(r"^(m3|m³|m2|m²|m|mt|kg|ton|adet|ad|lt|l|saat|sa|takım|tk|paket|pk|çift|gün)$", re.IGNORECASE)
BIRIM_DUZELT = {"m3": "m³", "m2": "m²", "mt": "m", "ad": "adet", "l": "L", "lt": "L", "sa": "saat", "tk": "takım", "pk": "paket"}


@dataclass
class PozPrice:
    poz: str
    name: str
    unit: str
    price: float
    raw: str

    def to_dict(self) -> dict:
        return {"poz": self.poz, "name": self.name, "unit": self.unit, "price": self.price}


def parse_number(s: str) -> float | None:
    """Türkçe sayı: binlik nokta, ondalık virgül. "3.250,00" -> 3250.0, "485,50" -> 485.5, "3250.00" -> 3250.0."""
    s = s.strip().replace(" ", "").replace("₺", "").replace("TL", "")
    if not s or not NUM.match(s):
        return None
    if "," in s:                      # virgül varsa ondalık ayracıdır, nokta binliktir
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:            # 1.234.567 -> binlik
        s = s.replace(".", "")
    elif "." in s:
        tam, _, kesir = s.partition(".")
        if len(kesir) == 3 and len(tam) <= 3:    # 3.250 -> binlik mi ondalık mı? üç hane = binlik
            s = tam + kesir
    try:
        return float(s)
    except ValueError:
        return None


def _tokens(line: str) -> list[str]:
    """Satırı alana böler: önce belirgin ayraçlar, yoksa iki ve daha fazla boşluk, o da yoksa tek boşluk."""
    for sep in ("\t", ";", "|"):
        if sep in line:
            return [t.strip() for t in line.split(sep) if t.strip()]
    parts = [t.strip() for t in re.split(r"\s{2,}", line) if t.strip()]
    return parts if len(parts) >= 3 else [t for t in line.split(" ") if t.strip()]


def parse_line(line: str) -> PozPrice | None:
    """Bir satırdan (poz, ad, birim, fiyat) çıkarır; poz ya da fiyat yoksa None."""
    line = line.strip()
    if not line or len(line) < 8:
        return None
    m = POZ.search(line)
    if not m:
        return None
    poz = m.group(0)
    parts = _tokens(line)
    # fiyat: sondan başlayarak ilk okunabilen sayı (poz'un kendisi sayı sayılmaz)
    price = None
    price_i = -1
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == poz or POZ.fullmatch(parts[i]):
            continue
        v = parse_number(parts[i])
        if v is not None and v > 0:
            price, price_i = v, i
            break
    if price is None:
        return None
    unit = ""
    orta = [p for k, p in enumerate(parts) if k != price_i and p != poz and not POZ.fullmatch(p)]
    for p in orta:
        if BIRIM.match(p):
            unit = BIRIM_DUZELT.get(p.lower(), p.lower())
            break
    ad = " ".join(p for p in orta if not BIRIM.match(p)).strip(" -–—:")
    # Poz satırın içindeyse addan ayıkla
    ad = ad.replace(poz, "").strip(" -–—:")
    return PozPrice(poz=poz, name=ad[:200], unit=unit, price=price, raw=line[:300])


@dataclass
class ImportResult:
    rows: list[PozPrice]
    skipped: int
    duplicates: int

    def to_dict(self) -> dict:
        return {"okunan": len(self.rows), "atlanan": self.skipped, "tekrar": self.duplicates,
                "ornek": [r.to_dict() for r in self.rows[:5]]}


def parse_list(text: str) -> ImportResult:
    """Bir birim fiyat listesini satır satır okur. Aynı poz tekrar ederse **sonuncusu** geçerlidir."""
    rows: dict[str, PozPrice] = {}
    skipped = dup = 0
    for line in (text or "").splitlines():
        r = parse_line(line)
        if r is None:
            if line.strip():
                skipped += 1
            continue
        if r.poz in rows:
            dup += 1
        rows[r.poz] = r
    return ImportResult(rows=list(rows.values()), skipped=skipped, duplicates=dup)


# ---------------------------------------------------------------- birim uyumu

# Poz bedeli listenin birimine göredir; keşif kaleminin birimi başka olabilir. Demir keşifte **kg**,
# ÇŞB pozunda **ton**'dur: dönüştürülmezse tutar 1000 kat çıkar (ölçüldü: 16 milyon yerine 16 milyar ₺).
# Değer: kalem birimi başına fiyat = poz fiyatı × çarpan.
UNIT_ALIAS = {"m3": "m³", "m2": "m²", "mt": "m", "ad": "adet", "lt": "L", "l": "L", "sa": "saat",
              "tk": "takım", "pk": "paket", "kilogram": "kg"}
UNIT_FACTOR: dict[tuple[str, str], float] = {
    ("kg", "ton"): 0.001,      # fiyat ton başına, miktar kg -> birim fiyat 1000'de bir
    ("ton", "kg"): 1000.0,
    ("m", "km"): 0.001,
    ("km", "m"): 1000.0,
    ("L", "m³"): 0.001,
    ("m³", "L"): 1000.0,
}


def normalize_unit(u: str) -> str:
    u = (u or "").strip()
    return UNIT_ALIAS.get(u.lower(), u)


def unit_factor(item_unit: str, poz_unit: str) -> float | None:
    """Poz fiyatını kalem birimine çeviren çarpan; çevrilemiyorsa None (fiyat uygulanmaz).

    Aynı birim -> 1.0. Bilinen dönüşüm -> katsayı. Poz biriminin yazmadığı liste -> 1.0 kabul edilir
    ama bu bir varsayımdır; çağıran taraf uyarır."""
    a, b = normalize_unit(item_unit), normalize_unit(poz_unit)
    if not b:
        return 1.0                      # listede birim yok: kalemin birimi varsayılır
    if not a or a == b:
        return 1.0
    return UNIT_FACTOR.get((a, b))
