"""Çelik konstrüksiyon elemanları (çelik kolon / kiriş / aşık / çapraz planları).

Çelik planında her eleman üstten görünüşüyle, profil genişliğinde ince bir dikdörtgen olarak çizilir (HEA100 → 10 cm,
Ø101.6 boru → 10,2 cm); kolon kesit olarak (HEB260 → 26 × 26 cm kare). Profil adı ayrı bir "marka" yazısıdır
(HEA260, Kolon-HEB260, Ø101.6x6, 120x80x4) ve çoğu zaman kılavuz çizgisiyle elemana bağlanır.

  eleman boyu  = dikdörtgenin uzun kenarı (plandaki izdüşüm; eğimli çaprazda gerçek boy daha uzundur — uyarı)
  profil       = (1) kılavuz çizgisinin eleman ucundaki yazı, (2) en yakın, genişliği tutan yazı,
                 (3) aynı katmandaki elemanların hepsi tek profilse o profil (tahmin)
  kolon boyu   = planda okunmaz (kesit); keşifte kotlardan türetilir (services)
Ağırlık = boy × kg/m (standard/steel.py). Kesikli (gizli) kopyalar katman profilinde yok sayılır.
"""
from __future__ import annotations

import re
from collections import Counter

from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon

from ...standard.steel import parse_profile
from ..geometry import min_area_rect
from ..loader import Drawing
from .base import DetectParams, DetectedElement

LEADER_LAYER = re.compile(r"MARKA|LEADER|KILAVUZ|C[İI]ZG[İI]", re.IGNORECASE)
# kolon ve dikme (üst konstrüksiyon dikmesi) planda kesittir: boyu kotlardan
KOLON_WORD = re.compile(r"KOLON|COLUMN|\bCOL\b|D[İI]KME|\bPOST", re.IGNORECASE)
MAX_WIDTH = 0.65          # m — daha geniş dikdörtgen çelik eleman değildir
MIN_LEN = 0.25
LEADER_TOUCH = 0.35       # m — kılavuz ucu yazıya / elemana bu kadar yakın
NEAR_LABEL = 1.5          # m — kılavuzsuz yazının elemana azami uzaklığı
WIDTH_TOL = 0.45          # genişlik tutması (oran)
EK_MIN_KILAVUZ = 3        # tanınmayan katman: en az bu kadar elemanına kılavuzla profil bağlanmışsa çelik katmanıdır
# tanınmayan katmanlardan aday alınmayacaklar: bağlantı / plaka / aks / yazı / gizli çizgi / betonarme
EK_HARIC = re.compile(r"PLAKA|PLATE|B[İI]RLE[SŞ][İI]M|AKS|GRID|KES[İI]KL[İI]|HIDDEN|DASH|BULON|BOLT|ANKRAJ|TARAMA|HATCH|"
                      r"YAZI|TEXT|MARKA|[ÖO]L[CÇ][ÜU]|DIM|BETON|ANTET|PAFTA|DETAY|KAYNAK|WELD|DEFPOINTS", re.IGNORECASE)


_GENEL = {"C", "G", "S", "A", "MARKA", "YAZI", "TEXT", "CIZGI", "KESIKLI", "0"}


def _tokens(layer: str) -> set[str]:
    """Katman adının ayırt edici sözcükleri: "C-Marka-Capraz" → {CAPRAZ}, "C-Kiris-Stabilite" → {KIRIS, STABILITE}."""
    t = (layer or "").upper().replace("İ", "I").replace("Ş", "S").replace("Ç", "C").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O")
    return {w for w in re.split(r"[^A-Z0-9]+", t) if w and w not in _GENEL}


def _genislik_tutar(prof: dict, w: float) -> bool:
    adaylar = [prof["width"]] + ([prof["width2"]] if prof.get("width2") else [])
    return any(abs(w - c) <= WIDTH_TOL * c for c in adaylar)


def detect_steel(drawing: Drawing, layers: list[str], params: DetectParams,
                 extra_layers: list[str] | None = None) -> list[DetectedElement]:
    """layers: çelik eleman katmanları (adından tanınan). extra_layers: adı tanınmayan öteki katmanlar — elemanları
    ancak katmanın en az EK_MIN_KILAVUZ elemanına kılavuz çizgisiyle profil yazısı bağlanıyorsa alınır ("C-Pr" katmanında
    "Dikme-120x80x4" markalı parapet dikmeleri: Yat Kulübü çatıları)."""
    ek = {l for l in (extra_layers or []) if l not in layers and not EK_HARIC.search(l or "")}
    if not layers and not ek:
        return []
    uyeler: list[dict] = []
    gorulen: list[Polygon] = []
    for e in drawing.entities:
        if (e.layer not in layers and e.layer not in ek) or not e.is_closed_polygon:
            continue
        try:
            p = Polygon(e.points).buffer(0)
        except Exception:
            continue
        if p.is_empty or p.area < 1e-4:
            continue
        L, S, _ = min_area_rect(list(p.exterior.coords)[:-1])
        if S > MAX_WIDTH or L < 0.05:
            continue
        # aynı eleman çokgen + tarama olarak iki kez çizilir
        if any(p.intersection(q).area > 0.9 * min(p.area, q.area) for q in gorulen if q.bounds[0] <= p.bounds[2]
               and q.bounds[2] >= p.bounds[0] and q.bounds[1] <= p.bounds[3] and q.bounds[3] >= p.bounds[1]):
            continue
        gorulen.append(p)
        # kesit: kare (HEB) ya da dikdörtgen kutu (120x60 → oran 2); kiriş / aşık hiçbir zaman bu kadar kısa değildir
        kolon = L <= MAX_WIDTH and L / max(S, 1e-6) < 2.5 and (KOLON_WORD.search(e.layer or "") or S >= 0.05)
        if not kolon and (L < MIN_LEN or L / max(S, 1e-6) < 2.5):
            continue
        uyeler.append({"poly": p, "layer": e.layer, "L": L, "S": S, "kolon": bool(kolon), "prof": None, "kaynak": "",
                       "tok": _tokens(e.layer), "ek": e.layer in ek, "kilavuz": False})
    if not uyeler:
        return []
    tree = STRtree([u["poly"] for u in uyeler])
    yazilar = []
    for e in drawing.texts():
        pr = parse_profile(e.text)
        if pr:
            yazilar.append({"pt": Point(e.points[0]), "prof": pr, "kolon": bool(KOLON_WORD.search(e.text)), "raw": e.text,
                            "tok": _tokens(e.layer)})
    kilavuz = [LineString(e.points) for e in drawing.entities
               if LEADER_LAYER.search(e.layer or "") and e.kind in ("line", "polyline") and len(e.points) >= 2]

    def en_yakin(pt: Point, r: float, filtre=None, tok: set | None = None):
        """En yakın eleman; yazının katmanıyla ortak sözcüğü olan elemanlar önce (Marka-Capraz → Capraz)."""
        aday = []
        for i in tree.query(pt.buffer(r)):
            u = uyeler[int(i)]
            if filtre and not filtre(u):
                continue
            d = u["poly"].distance(pt)
            if d <= r:
                aday.append((-len(tok & u["tok"]) if tok else 0, d, id(u), u))
        return min(aday)[3] if aday else None

    for y in yazilar:
        hedef = None
        # (1) kılavuz: ucu yazıya değen çizginin öbür ucu elemana
        for k in kilavuz:
            a, b = Point(k.coords[0]), Point(k.coords[-1])
            for bas, son in ((a, b), (b, a)):
                if son.distance(y["pt"]) <= LEADER_TOUCH:
                    u = en_yakin(bas, LEADER_TOUCH, lambda u: u["prof"] is None and u["kolon"] == y["kolon"], y["tok"])
                    if u:
                        hedef = u
                        u["kilavuz"] = True
                        break
            if hedef:
                break
        if hedef is None:
            hedef = en_yakin(y["pt"], NEAR_LABEL, lambda u: u["prof"] is None and u["kolon"] == y["kolon"]
                             and _genislik_tutar(y["prof"], u["S"]), y["tok"])
        if hedef is not None:
            hedef["prof"], hedef["kaynak"] = y["prof"], y["raw"]
    # tanınmayan katman: yeterince kılavuzlu eleman yoksa o katman çelik değildir (hepsi düşer)
    kil = Counter(u["layer"] for u in uyeler if u["ek"] and u["kilavuz"])
    uyeler = [u for u in uyeler if not u["ek"] or kil[u["layer"]] >= EK_MIN_KILAVUZ]
    # (3) etiketsiz eleman: katmanındaki etiketli elemanların hepsi tek profilse ve genişlik tutuyorsa o
    by_layer: dict[tuple, Counter] = {}
    for u in uyeler:
        if u["prof"]:
            by_layer.setdefault((u["layer"], u["kolon"]), Counter())[u["prof"]["name"]] += 1
    prof_of = {p["prof"]["name"]: p["prof"] for p in uyeler if p["prof"]}
    out: list[DetectedElement] = []
    for u in uyeler:
        uyari = []
        tahmin = False
        if u["prof"] is None:
            c = by_layer.get((u["layer"], u["kolon"]))
            if c and len(c) == 1:
                ad = next(iter(c))
                if _genislik_tutar(prof_of[ad], u["S"]):
                    u["prof"], tahmin = prof_of[ad], True
                    uyari.append(f"Profil yazısı yok; katmandaki öteki elemanlar gibi {ad} kabul edildi")
        if u["prof"] is None:
            if u["kolon"]:
                continue                      # etiketsiz kare: kolon izi / plaka olabilir, sayılmaz
            uyari.append("Profil yazısı bulunamadı; ağırlık hesaplanamadı")
        pr = u["prof"] or {}
        pts = [(round(x, 4), round(y, 4)) for x, y in list(u["poly"].exterior.coords)[:-1]]
        el = DetectedElement(etype="steel_member", layer=u["layer"], points=pts, source="STEEL",
                             name=pr.get("name") or "Çelik eleman", subtype=pr.get("name") or "",
                             b=round(u["S"], 4), length=None if u["kolon"] else round(u["L"], 4),
                             confidence=0.5 if not pr else (0.7 if tahmin else 0.85), label_raw=u["kaynak"])
        el.meta = {"profile": pr.get("name"), "kg_m": pr.get("kg_m"), "family": pr.get("family"),
                   "column": u["kolon"], "profile_guess": tahmin}
        if u["kolon"]:
            el.warnings.append("Çelik kolon planda kesit olarak çizili: boyu kotlardan türetilir")
        el.warnings.extend(uyari)
        out.append(el)
    return out
