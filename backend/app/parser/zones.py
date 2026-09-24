"""Alan çizgisiyle ayrılmış bölgeler: ortak alan mı, dükkân mı, teknik hacim mi?

AVM / iş merkezinde dükkânlar **kaba teslim** edilir: içi sıvanmaz, boyanmaz, tavanı ve döşemesi kiracının
işidir; müteahhidin keşfinde yalnız ortak alanlar (lobi, koridor, merdiven) ve dükkânın dış cephesi vardır.
Bunu hesaplamak için hangi bölgenin ortak alan olduğunu bilmek gerekir. Mimar mahal adı yazmasa da çoğu
zaman bölgeleri **alan çizgisiyle** ayırır (A blokları: `brn_area`); içindeki yazılar ve biçimi ne
olduklarını söyler:

  ortak   : LOBİ / HOL / KORİDOR / GİRİŞ / ASANSÖR yazısı; merdiven yazısı ("ZEMİN KAT 24X(30 / 16.45)");
            ya da uzun ve dar şerit (en boy ≥ 4, eni ≤ 9 m) — pasaj / koridor
  dukkan  : DÜKKAN / MAĞAZA yazısı; ya da büyük (≥ 60 m²) ve ortak işareti taşımayan bölge — bağımsız bölüm
  teknik  : ŞAFT / TEKNİK / ÇÖP / ELEKTRİK / TESİSAT odası
  belirsiz: hiçbiri — keşif onu ortak saymaz, rapor ayrıca gösterir

Kural tabanlıdır ve her karar gerekçesini taşır ("içinde 'LOBİ' yazıyor", "43 × 7,8 m şerit"). Emin
olunamayan bölge uydurulmaz: belirsiz kalır.
"""
from __future__ import annotations

import re

from shapely.geometry import Point as SPoint
from shapely.geometry import Polygon

from ..planset import normalize_title
from .loader import Drawing

AREA_LAYER = re.compile(r"(^|[_\-\s])(AREA|ALAN|MAHAL|BOLUM|ZONE)([_\-\s]|$)", re.IGNORECASE)
_COMMON = re.compile(r"LOBI|\bHOL\b|KORIDOR|PASAJ|GIRIS|ASANSOR|FUAYE|MERDIVEN|SAHANLIK|RAMPA")
_STAIR_NOTE = re.compile(r"\d+\s*X\s*\(\s*\d+")          # "24X(30 / 16.45)" basamak sayısı × (genişlik / yükseklik)
_SHOP = re.compile(r"DUKKAN|MAGAZA|MARKET|KIRACI|RESTORAN|CAFE|KAFE")
_TECH = re.compile(r"SAFT|TEKNIK|COP\b|COP\s*TOPLAMA|ELEKTRIK\s*ODASI|TESISAT|PANO|JENERATOR|TRAFO|DEPO")
CORRIDOR_ASPECT = 4.0
CORRIDOR_MAX_WIDTH = 9.0
SHOP_MIN_AREA = 60.0
MIN_ZONE_AREA = 2.0

KIND_LABEL = {"ortak": "Ortak alan", "dukkan": "Dükkân (kiracı alanı)", "teknik": "Teknik hacim", "belirsiz": "Belirsiz"}


def _dims(p: Polygon) -> tuple[float, float]:
    """Döndürülmüş en küçük dikdörtgenin (uzun, kısa) kenarı."""
    r = p.minimum_rotated_rectangle
    c = list(r.exterior.coords)
    a = ((c[1][0] - c[0][0]) ** 2 + (c[1][1] - c[0][1]) ** 2) ** 0.5
    b = ((c[2][0] - c[1][0]) ** 2 + (c[2][1] - c[1][1]) ** 2) ** 0.5
    return max(a, b), min(a, b)


def classify(poly: Polygon, texts: list[str]) -> tuple[str, str]:
    """(tür, gerekçe). texts: bölgenin içindeki yazılar."""
    norm = [normalize_title(t) for t in texts if t]
    for t, raw in zip(norm, texts):
        if _COMMON.search(t):
            return "ortak", f"içinde “{' '.join(raw.split())[:24]}” yazıyor"
    for t, raw in zip(norm, texts):
        if _SHOP.search(t):
            return "dukkan", f"içinde “{' '.join(raw.split())[:24]}” yazıyor"
    for t, raw in zip(norm, texts):
        if _TECH.search(t):
            return "teknik", f"içinde “{' '.join(raw.split())[:24]}” yazıyor"
    for raw in texts:
        if raw and _STAIR_NOTE.search(raw.upper()):
            return "ortak", f"merdiven: “{' '.join(raw.split())[:28]}”"
    uzun, kisa = _dims(poly)
    if kisa > 0 and uzun / kisa >= CORRIDOR_ASPECT and kisa <= CORRIDOR_MAX_WIDTH:
        return "ortak", f"{uzun:.0f} × {kisa:.1f} m uzun dar şerit — koridor / pasaj"
    if poly.area >= SHOP_MIN_AREA:
        return "dukkan", f"{poly.area:.0f} m² adsız büyük bölge — bağımsız bölüm"
    return "belirsiz", "işaret yok"


def scan_zones(drawing: Drawing) -> list[dict]:
    """Alan katmanlarındaki kapalı çokgenler, türleriyle: [{"kind", "area", "points", "why", "layer"}]."""
    polys = []
    for e in drawing.entities:
        if e.kind != "polygon" or len(e.points) < 3 or not AREA_LAYER.search(e.layer or ""):
            continue
        try:
            p = Polygon(e.points).buffer(0)
        except Exception:
            continue
        if not p.is_empty and p.area >= MIN_ZONE_AREA and p.geom_type == "Polygon":
            polys.append((p, e.layer))
    if not polys:
        return []
    texts = [(SPoint(e.points[0]), e.text) for e in drawing.entities if e.kind == "text" and e.text and e.points]
    out = []
    for p, layer in polys:
        inside = [t for pt, t in texts if p.contains(pt)]
        kind, why = classify(p, inside)
        out.append({"kind": kind, "area": round(p.area, 2), "why": why, "layer": layer,
                    "points": [[round(x, 3), round(y, 3)] for x, y in p.exterior.coords]})
    return out
