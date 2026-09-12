"""Aynı kalemi tüketen elemanları tek satırda toplayan grup anahtarı.

Bir kat kalıp planında 185 kolonun tek tek listelenmesi keşifçiye bilgi vermez; "42 adet 100/100 kolon"
verir: aynı kesitteki kolonlar metre başına aynı betonu, aynı kalıbı, aynı demiri tüketir, aynı birim
fiyatla çarpılır. Bu yüzden hem plan önizlemesinde hem özet tablosunda eleman değil **grup** gösterilir.

Anahtar tek yerde hesaplanır (bu modül): önizlemedeki çokgenin `data-group`'u ile tablodaki satırın anahtarı
aynı olmak zorunda, yoksa tabloya tıklayınca çizimde başka şey seçilir. Frontend bu anahtarı kendi
hesaplamaz; eleman listesiyle birlikte sunucudan alır.

Gruplama ölçüsü elemanın **sürücü boyutudur**: sayılan elemanda kesit (kolon 100/100, kiriş 50/45), alanla
ölçülende kalınlık (döşeme 12 cm, radye 70 cm), uzunlukla ölçülende kalınlık + malzeme (perde 30 cm,
duvar 20 cm ytong). Boyu / uzunluğu gruba girmez: 3 m ve 4 m'lik iki 100/100 kolon aynı kalemdir, adetleri
toplanır, uzunlukları toplam olarak yazılır.
"""
from __future__ import annotations

from typing import Any

# Grup etiketinde kesit (b×h) kullanan tipler: sayılan, kesiti belli elemanlar
SECTION_TYPES = {"column", "beam", "door", "window"}
# Kalınlık + malzeme ile gruplanan, uzunlukla ölçülen tipler
WIDTH_TYPES = {"shear_wall", "wall", "parapet", "tray", "duct"}
# Kalınlıkla gruplanan alan elemanları
THICKNESS_TYPES = {"slab", "foundation"}

FOUNDATION_SUBTYPE = {"raft": "radye", "strip": "sürekli", "pad": "tekil"}
NO_SIZE = "ölçüsüz"


def _cm(v: float | None) -> int | None:
    """metre -> tam cm; 0 / None -> None. Çizimden gelen 0.29999999 ile 0.3 aynı gruba düşsün diye yuvarlanır."""
    if not v:
        return None
    return int(round(v * 100))


def section_label(el: dict[str, Any]) -> str:
    """Elemanın grup etiketi: "100/100", "30 cm ytong", "12 cm", "radye 70 cm"...

    Boş dönmez; ölçüsü okunamayan eleman "ölçüsüz" grubuna düşer (yoksa ölçüsüzler ölçülülerle karışır)."""
    etype = el.get("etype") or ""
    subtype = (el.get("subtype") or "").strip()
    b, h, t = _cm(el.get("b")), _cm(el.get("h")), _cm(el.get("thickness"))
    if etype in SECTION_TYPES:
        if b and h:
            return f"{b}/{h}"
        return subtype or NO_SIZE
    if etype in WIDTH_TYPES:
        parts = [f"{b} cm" if b else "", subtype]
        label = " ".join(p for p in parts if p)
        return label or NO_SIZE
    if etype in THICKNESS_TYPES:
        kind = FOUNDATION_SUBTYPE.get(subtype, subtype) if etype == "foundation" else ""
        parts = [kind, f"{t} cm" if t else ""]
        label = " ".join(p for p in parts if p)
        return label or NO_SIZE
    # katalog kalemi (KSF), donatı satırı, armatür kategorisi: alt tip zaten kalemi tanımlar
    return subtype or (el.get("name") or "") or NO_SIZE


def group_key(el: dict[str, Any]) -> str:
    """Önizleme çokgeni ile özet satırını eşleyen anahtar. Tip + grup etiketi."""
    return f"{el.get('etype') or ''}|{section_label(el)}"


def annotate(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Eleman sözlüklerine `group` ve `section` alanlarını ekler (yerinde değiştirmez)."""
    return [{**el, "group": group_key(el), "section": section_label(el)} for el in elements]
