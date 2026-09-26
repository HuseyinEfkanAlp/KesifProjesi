"""Çelik konstrüksiyon elemanları (çelik kolon / kiriş / aşık / çapraz planları).

Çelik planında eleman üç biçimde çizilir:
  - dikdörtgen: profil genişliğinde kapalı ince dikdörtgen (HEA100 → 10 cm, Ø101.6 boru → 10,2 cm); kolon kesit
    olarak (HEB260 → 26 × 26 cm kare)
  - çift çizgi: aynı dikdörtgenin iki uzun kenarı ayrı çizgiler (kapalı değil)
  - tek çizgi: elemanın ekseni tek çizgi (aşık, kuşak, çapraz, makas elemanı); genişliği yoktur, profili yazıdan
Profil adı ayrı bir "marka" yazısıdır (HEA260, Kolon-HEB260, Ø101.6x6, 120x80x4); kılavuz çizgisiyle elemana bağlanır
ya da elemanın yanında, tek çizgide elemana paralel yazılır.

  eleman boyu  = dikdörtgenin uzun kenarı / çizginin boyu; EĞİMLİ elemanda gerçek boy = √(plan² + Δh²):
                 Δh iki ucundaki kot yazısından ("+16.85" … "+18.65") ya da elemana paralel eğim yazısından
                 ("%25", "EĞİM %15", "20°"); eğim bilgisi yoksa plandaki izdüşüm (kullanıcıya sorulur)
  profil       = (1) kılavuz çizgisinin eleman ucundaki yazı, (2) en yakın, genişliği (tek çizgide doğrultusu) tutan
                 yazı, (3) aynı katmandaki elemanların hepsi tek profilse o profil (tahmin)
  kolon boyu   = planda okunmaz (kesit); keşifte kotlardan türetilir (services)
Ağırlık = boy × kg/m (standard/steel.py). Dikdörtgen elemanın kenar / eksen çizgileri ikinci kez sayılmaz; gizli
(kesikli) katmanlar alınmaz.
"""
from __future__ import annotations

import math
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
NEAR_TEK = 0.8            # m — tek çizgi elemanın paralel markasının azami uzaklığı
PARALEL_TOL = 20.0        # derece — tek çizgi marka / eğim yazısı doğrultu toleransı
WIDTH_TOL = 0.45          # genişlik tutması (oran)
EK_MIN_KILAVUZ = 3        # tanınmayan katman: en az bu kadar elemanına kılavuzla profil bağlanmışsa çelik katmanıdır
KAPLI = 0.5               # çizginin bu kadarı bir dikdörtgen elemanın üstündeyse o elemanın kenarı / eksenidir
KOT_UCU = 0.8             # m — eleman ucuna bu kadar yakın kot yazısı o ucun kotudur
EGIM_R = 15.0             # m — eğim yazısının etkilediği en uzak eleman
# tanınmayan katmanlardan aday alınmayacaklar: bağlantı / plaka / aks / yazı / gizli çizgi / betonarme
EK_HARIC = re.compile(r"PLAKA|PLATE|B[İI]RLE[SŞ][İI]M|AKS|GRID|KES[İI]KL[İI]|HIDDEN|DASH|BULON|BOLT|ANKRAJ|TARAMA|HATCH|"
                      r"YAZI|TEXT|MARKA|[ÖO]L[CÇ][ÜU]|DIM|BETON|ANTET|PAFTA|DETAY|KAYNAK|WELD|DEFPOINTS", re.IGNORECASE)
GIZLI = re.compile(r"KES[İI]KL[İI]|HIDDEN|DASH|G[İI]ZL[İI]", re.IGNORECASE)
KOT_RE = re.compile(r"^\s*([+\-±]?\d{1,3}[.,]\d{2,3})\s*$")
EGIM_RE = re.compile(r"(?:%\s*(?P<p1>\d{1,3}(?:[.,]\d+)?))|(?:(?P<p2>\d{1,3}(?:[.,]\d+)?)\s*%)"
                     r"|(?:(?P<d>\d{1,2}(?:[.,]\d+)?)\s*(?:°|%%[dD]|DERECE))", re.IGNORECASE)


_GENEL = {"C", "G", "S", "A", "MARKA", "YAZI", "TEXT", "CIZGI", "KESIKLI", "0"}


def _tokens(layer: str) -> set[str]:
    """Katman adının ayırt edici sözcükleri: "C-Marka-Capraz" → {CAPRAZ}, "C-Kiris-Stabilite" → {KIRIS, STABILITE}."""
    t = (layer or "").upper().replace("İ", "I").replace("Ş", "S").replace("Ç", "C").replace("Ğ", "G").replace("Ü", "U").replace("Ö", "O")
    return {w for w in re.split(r"[^A-Z0-9]+", t) if w and w not in _GENEL}


def _genislik_tutar(prof: dict, w: float) -> bool:
    adaylar = [prof["width"]] + ([prof["width2"]] if prof.get("width2") else [])
    return any(abs(w - c) <= WIDTH_TOL * c for c in adaylar)


def _aci(a, b) -> float:
    """İki nokta doğrultusu, derece [0, 180)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0


def _aci_farki(x: float, y: float) -> float:
    d = abs(x - y) % 180.0
    return min(d, 180.0 - d)


def _eksen(p: Polygon) -> LineString:
    """İnce dikdörtgenin boyuna ekseni (kısa kenarların ortalarını birleştirir)."""
    r = p.minimum_rotated_rectangle
    c = list(r.exterior.coords)[:4] if r.geom_type == "Polygon" else list(p.exterior.coords)[:4]
    if len(c) < 4:
        return LineString(list(p.exterior.coords)[:2])
    kenar = [(c[i], c[(i + 1) % 4]) for i in range(4)]
    kisa = sorted(kenar, key=lambda k: math.dist(*k))[:2]
    m = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in kisa]
    return LineString(m)


def _cizgi_eslestir(cizgiler: list[dict]) -> tuple[list[tuple[dict, dict, float]], list[dict]]:
    """Paralel, üst üste binen ve profil genişliği kadar aralıklı iki çizgi = çift çizgiyle çizilmiş tek eleman.
    Döner: (çiftler [(a, b, aralık)], kalan tek çizgiler)."""
    if not cizgiler:
        return [], []
    iki = [c for c in cizgiler if len(c["ls"].coords) == 2]
    tree = STRtree([c["ls"].buffer(MAX_WIDTH) for c in iki]) if iki else None
    adaylar = []
    for i, a in enumerate(iki):
        for j in (tree.query(a["ls"]) if tree is not None else []):
            j = int(j)
            if j <= i:
                continue
            b = iki[j]
            if _aci_farki(a["aci"], b["aci"]) > 2.0:
                continue
            d = b["ls"].distance(Point(a["ls"].interpolate(0.5, normalized=True)))
            if not (0.03 <= d <= MAX_WIDTH):
                continue
            # a'nın doğrultusunda örtüşme
            (x0, y0), (x1, y1) = a["ls"].coords
            L = math.hypot(x1 - x0, y1 - y0)
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            ta = sorted([0.0, L])
            tb = sorted(((bx - x0) * ux + (by - y0) * uy) for bx, by in b["ls"].coords)
            ort = min(ta[1], tb[1]) - max(ta[0], tb[0])
            if ort < 0.7 * min(L, b["ls"].length):
                continue
            adaylar.append((d, i, j))
    kullanilan: set[int] = set()
    ciftler = []
    for d, i, j in sorted(adaylar):
        if i in kullanilan or j in kullanilan:
            continue
        kullanilan |= {i, j}
        ciftler.append((iki[i], iki[j], d))
    eslesen = {id(iki[i]) for i in kullanilan}
    return ciftler, [c for c in cizgiler if id(c) not in eslesen]


def detect_steel(drawing: Drawing, layers: list[str], params: DetectParams,
                 extra_layers: list[str] | None = None) -> list[DetectedElement]:
    """layers: çelik eleman katmanları (adından tanınan). extra_layers: adı tanınmayan öteki katmanlar — elemanları
    ancak katmanın en az EK_MIN_KILAVUZ elemanına kılavuz çizgisiyle profil yazısı bağlanıyorsa alınır ("C-Pr" katmanında
    "Dikme-120x80x4" markalı parapet dikmeleri: Yat Kulübü çatıları)."""
    ek = {l for l in (extra_layers or []) if l not in layers and not EK_HARIC.search(l or "")}
    if not layers and not ek:
        return []
    katman = set(layers) | ek
    uyeler: list[dict] = []
    gorulen: list[Polygon] = []

    def _ekle(p: Polygon, layer: str, L: float, S: float, kolon: bool, eksen: LineString, bicim: str) -> None:
        uyeler.append({"i": len(uyeler), "poly": p, "layer": layer, "L": L, "S": S, "kolon": bool(kolon), "prof": None,
                       "kaynak": "",
                       "tok": _tokens(layer), "ek": layer in ek, "kilavuz": False, "eksen": eksen, "bicim": bicim,
                       "aci": _aci(*list(eksen.coords)[:2]) if len(eksen.coords) >= 2 else 0.0})

    for e in drawing.entities:
        if e.layer not in katman or not e.is_closed_polygon:
            continue
        try:
            p = Polygon(e.points).buffer(0)
        except Exception:
            continue
        if p.is_empty or p.area < 1e-4 or p.geom_type != "Polygon":
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
        _ekle(p, e.layer, L, S, kolon, _eksen(p), "dikdortgen")

    # --- çizgiyle çizilmiş elemanlar: dikdörtgenin kenarı / ekseni olmayan, gizli katmanda olmayan çizgiler
    dik = [u["poly"].buffer(0.02) for u in uyeler]
    dtree = STRtree(dik) if dik else None
    cizgiler = []
    for e in drawing.entities:
        if e.layer not in katman or e.kind not in ("line", "polyline") or len(e.points) < 2 or GIZLI.search(e.layer or ""):
            continue
        ls = LineString(e.points)
        if ls.length < MIN_LEN:
            continue
        if dtree is not None:
            kapli = sum(ls.intersection(dik[int(i)]).length for i in dtree.query(ls))
            if kapli >= KAPLI * ls.length:
                continue
        cizgiler.append({"ls": ls, "layer": e.layer, "aci": _aci(e.points[0], e.points[-1])})
    ciftler, tekler = _cizgi_eslestir(cizgiler)
    for a, b, d in ciftler:
        p = Polygon(list(a["ls"].coords) + list(b["ls"].coords)[::-1]).convex_hull
        L, S, _ = min_area_rect(list(p.exterior.coords)[:-1])
        if L < MIN_LEN or L / max(S, 1e-6) < 2.5:
            continue
        _ekle(p, a["layer"], L, S, False, _eksen(p), "cift_cizgi")
    for c in tekler:
        _ekle(c["ls"].buffer(0.005), c["layer"], c["ls"].length, 0.0, False, c["ls"], "tek_cizgi")

    if not uyeler:
        return []
    tree = STRtree([u["poly"] for u in uyeler])
    yazilar = []
    kotlar: list[tuple[Point, float]] = []
    egimler: list[tuple[Point, float, float, str]] = []     # (nokta, doğrultu, eğim oranı, yazı)
    for e in drawing.texts():
        pr = parse_profile(e.text)
        rot = float(getattr(e, "rotation", 0.0) or 0.0) % 180.0
        pt = Point(e.points[0])
        if pr:
            # tek çizgi markası elemana paraleldir; yazının ortası eklenme noktasından doğrultusunda yarım boy ötede
            yarim = 0.45 * len(e.text or "") * float(e.height or 0.0)
            orta = Point(pt.x + yarim * math.cos(math.radians(rot)), pt.y + yarim * math.sin(math.radians(rot)))
            yazilar.append({"pt": pt, "orta": orta, "rot": rot, "prof": pr, "kolon": bool(KOLON_WORD.search(e.text)),
                            "raw": e.text, "tok": _tokens(e.layer)})
            continue
        m = KOT_RE.match(e.text or "")
        if m:
            kotlar.append((pt, float(m.group(1).replace(",", ".").replace("±", ""))))
            continue
        if len(e.text or "") <= 25:
            m = EGIM_RE.search(e.text or "")
            if m:
                if m.group("d"):
                    s = math.tan(math.radians(float(m.group("d").replace(",", "."))))
                else:
                    s = float((m.group("p1") or m.group("p2")).replace(",", ".")) / 100.0
                if 0.005 < s <= 1.0:
                    egimler.append((pt, rot, s, e.text.strip()))
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
                # eşit uzaklıkta çizim sırası belirler (bellek adresi değil): aynı dosya her yüklemede aynı sonucu verir
                aday.append((-len(tok & u["tok"]) if tok else 0, d, u["i"]))
        return uyeler[min(aday)[2]] if aday else None

    def _yakin_tutar(y: dict, u: dict) -> bool:
        if u["prof"] is not None or u["kolon"] != y["kolon"]:
            return False
        if u["bicim"] == "tek_cizgi":
            # genişlik yok: yazı elemana paralel ve yakın olmalı
            return (_aci_farki(y["rot"], u["aci"]) <= PARALEL_TOL
                    and min(u["eksen"].distance(y["pt"]), u["eksen"].distance(y["orta"])) <= NEAR_TEK)
        return _genislik_tutar(y["prof"], u["S"])

    # 1. tur: kılavuzlu yazılar (her biçim) ve genişliği tutan dikdörtgen / çift çizgi elemanlar. Tek çizgiler yalnız
    # 2. turda, artakalan yazılardan alır: aksi halde dikdörtgen elemanın yanındaki kenar / yardımcı çizgi onun markasını
    # çalıyordu (Yat Kulübü +17.90 planı: 6 HEA100 markası 1,31 m'lik çizgilere gidip çelik %16 artıyordu).
    artakalan = []
    for y in yazilar:
        hedef = None
        # (1) kılavuz: ucu yazıya değen çizginin öbür ucu elemana
        for k in kilavuz:
            a, b = Point(k.coords[0]), Point(k.coords[-1])
            for bas, son in ((a, b), (b, a)):
                if son.distance(y["pt"]) <= LEADER_TOUCH:
                    # kılavuz ucunda dikdörtgen / çift çizgi eleman varsa o; yoksa tek çizgi
                    u = en_yakin(bas, LEADER_TOUCH, lambda u: u["prof"] is None and u["kolon"] == y["kolon"]
                                 and u["bicim"] != "tek_cizgi", y["tok"])                         or en_yakin(bas, LEADER_TOUCH, lambda u: u["prof"] is None and u["kolon"] == y["kolon"], y["tok"])
                    if u:
                        hedef = u
                        u["kilavuz"] = True
                        break
            if hedef:
                break
        if hedef is None:
            hedef = en_yakin(y["pt"], NEAR_LABEL, lambda u: u["bicim"] != "tek_cizgi" and _yakin_tutar(y, u), y["tok"])
            if hedef is not None:
                # yazıya paralel bir tek çizgi elemandan daha yakın mı? değilse yazı o çizginindir (2. tur)
                tek = en_yakin(y["orta"], NEAR_TEK, lambda u: u["bicim"] == "tek_cizgi" and _yakin_tutar(y, u))
                if tek is not None and tek["eksen"].distance(y["orta"]) < hedef["poly"].distance(y["pt"]):
                    hedef = None
        if hedef is not None:
            hedef["prof"], hedef["kaynak"] = y["prof"], y["raw"]
        else:
            artakalan.append(y)
    for y in artakalan:
        hedef = None
        for nokta in (y["orta"], y["pt"]):
            hedef = en_yakin(nokta, NEAR_TEK, lambda u: u["bicim"] == "tek_cizgi" and _yakin_tutar(y, u), y["tok"])
            if hedef is not None:
                break
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

    def _kot(pt: Point) -> float | None:
        yakin = [(pt.distance(p), v) for p, v in kotlar if pt.distance(p) <= KOT_UCU]
        return min(yakin)[1] if yakin else None

    def _egim(u: dict) -> tuple[float, str]:
        """(Δh, kaynak) — iki ucun kot yazısından ya da elemana paralel eğim yazısından; bulunamazsa (0, "")."""
        c = list(u["eksen"].coords)
        if len(c) < 2:
            return 0.0, ""
        k1, k2 = _kot(Point(c[0])), _kot(Point(c[-1]))
        if k1 is not None and k2 is not None and abs(k1 - k2) > 0.05 and abs(k1 - k2) <= 1.7 * u["L"]:
            return abs(k1 - k2), f"uç kotları {min(k1, k2):+.2f} / {max(k1, k2):+.2f}"
        # eğim yazısı eğim doğrultusundadır: elemanın o doğrultudaki izdüşümü kadar yükselir (makas tam, çatı
        # düzlemindeki köşegen çapraz kısmen, aşık / saçak kirişi hiç)
        orta = u["eksen"].interpolate(0.5, normalized=True)
        uygun = [(orta.distance(p), rot, s, t) for p, rot, s, t in egimler if orta.distance(p) <= EGIM_R]
        if uygun:
            _, rot, s, t = min(uygun)
            dh = u["L"] * abs(math.cos(math.radians(_aci_farki(rot, u["aci"])))) * s
            if dh > 0.01:
                return dh, f"eğim yazısı “{t}”"
        return 0.0, ""

    out: list[DetectedElement] = []
    for u in uyeler:
        uyari = []
        tahmin = False
        if u["prof"] is None:
            c = by_layer.get((u["layer"], u["kolon"]))
            if c and len(c) == 1:
                ad = next(iter(c))
                if (u["bicim"] == "tek_cizgi" and u["L"] >= 0.5) or _genislik_tutar(prof_of[ad], u["S"]):
                    u["prof"], tahmin = prof_of[ad], True
                    uyari.append(f"Profil yazısı yok; katmandaki öteki elemanlar gibi {ad} kabul edildi")
        if u["prof"] is None:
            if u["kolon"] or u["bicim"] == "tek_cizgi":
                continue       # etiketsiz kare (kolon izi / plaka) ya da etiketsiz çizgi (yardımcı çizgi olabilir): sayılmaz
            uyari.append("Profil yazısı bulunamadı; ağırlık hesaplanamadı")
        pr = u["prof"] or {}
        if u["bicim"] == "tek_cizgi":
            pts = [(round(x, 4), round(y, 4)) for x, y in u["eksen"].coords]
        else:
            pts = [(round(x, 4), round(y, 4)) for x, y in list(u["poly"].exterior.coords)[:-1]]
        L = u["L"]
        dh, egim_kaynak = (0.0, "") if u["kolon"] else _egim(u)
        if dh > 0:
            L = math.hypot(u["L"], dh)
            uyari.append(f"Eğimli eleman: gerçek boy {L:.2f} m (plan {u['L']:.2f} m, Δh {dh:.2f} m — {egim_kaynak})")
        el = DetectedElement(etype="steel_member", layer=u["layer"], points=pts, source="STEEL",
                             name=pr.get("name") or "Çelik eleman", subtype=pr.get("name") or "",
                             b=round(u["S"], 4) if u["S"] else pr.get("width"),
                             length=None if u["kolon"] else round(L, 4),
                             confidence=0.5 if not pr else (0.7 if tahmin else 0.85), label_raw=u["kaynak"])
        el.meta = {"profile": pr.get("name"), "kg_m": pr.get("kg_m"), "family": pr.get("family"),
                   "column": u["kolon"], "profile_guess": tahmin, "drawn_as": u["bicim"]}
        if dh > 0:
            el.meta.update(plan_length=round(u["L"], 4), rise=round(dh, 4), slope_source=egim_kaynak)
        if u["kolon"]:
            el.warnings.append("Çelik kolon planda kesit olarak çizili: boyu kotlardan türetilir")
        el.warnings.extend(uyari)
        out.append(el)
    return out


# ---------------------------------------------------------------- kesit paftasından eğim

KESIT_KOT_R = (25.0, 12.0)    # m — eğik çizginin kotlarını veren kot yazıları bu kadar yatay / düşey yakında


def section_slopes(drawing: Drawing, layers: list[str]) -> list[dict]:
    """Çelik kesit / görünüş paftasındaki eğik elemanlar: [{"layer", "zlo", "zhi", "egim", "boy"}].

    Kesitte makas / kiriş eğik çizilir; çizimin düşey ekseni kottur. Kotu, çizginin yakınındaki kot yazılarından
    (+13.20, +15.00…) doğrusal eşlemeyle bulunur (z = a·y + b; kesit başka ölçekte çizilse de eğim açısı değişmez).
    Böylece her eğik çizginin hangi kot aralığında durduğu, yani hangi eğimli çatı paftasına ait olduğu bilinir
    (services.steel_section_slopes). Gizli (kesikli) katmanlar ve 3°'den az / 60°'den çok eğik çizgiler alınmaz."""
    kat = {l for l in layers if not GIZLI.search(l or "")}
    if not kat:
        return []
    kotlar = [(e.points[0][0], e.points[0][1], float(m.group(1).replace(",", ".").replace("±", "")))
              for e in drawing.texts() for m in [KOT_RE.match(e.text or "")] if m]
    if len(kotlar) < 2:
        return []

    def _esle(x: float, y: float):
        """Çizginin kotu için z = a·y + b. Yakındaki kot yazılarından birbiriyle tutarlı en büyük grup alınır: aynı paftada
        alt alta duran başka bir kesitin kotları (Yat Kulübü A-A'nın hemen üstünde B-B) eşlemeyi bozmasın."""
        yakin = sorted(((math.hypot(kx - x, ky - y), ky, kz) for kx, ky, kz in kotlar
                        if abs(kx - x) <= KESIT_KOT_R[0] and abs(ky - y) <= KESIT_KOT_R[1]))[:12]
        if len({kz for _, _, kz in yakin}) < 2:
            return None
        # önce 1:1 (model uzayında kesit gerçek ölçüde çizilir): z − y farkı aynı olan en büyük grup
        farklar = [kz - ky for _, ky, kz in yakin]
        en_iyi = max(({i for i, f in enumerate(farklar) if abs(f - g) <= 0.35} for g in farklar), key=len)
        grup = [yakin[i] for i in sorted(en_iyi)]
        if len(grup) >= 2 and len({kz for _, _, kz in grup}) >= 2:
            return 1.0, sorted(farklar[i] for i in en_iyi)[len(en_iyi) // 2]
        # başka ölçekte çizilmiş kesit: en yakın dört yazıyla doğrusal eşleme
        grup = yakin[:4]
        n = len(grup)
        my, mz = sum(p[1] for p in grup) / n, sum(p[2] for p in grup) / n
        sxx = sum((p[1] - my) ** 2 for p in grup)
        if sxx < 1e-9:
            return None
        a = sum((p[1] - my) * (p[2] - mz) for p in grup) / sxx
        b = mz - a * my
        # yazılar kot çizgisinin hemen üstündedir: artık hatası yazı boyu kadardır; çok dağınıksa bu bir kesit değildir
        if not (0.2 <= a <= 5.0) or max(abs(a * p[1] + b - p[2]) for p in grup) > 0.5:
            return None
        return a, b

    out: dict[tuple, dict] = {}
    for e in drawing.entities:
        if e.layer not in kat or e.kind not in ("line", "polyline", "polygon") or len(e.points) < 2:
            continue
        pts = list(e.points) + ([e.points[0]] if e.kind == "polygon" else [])
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            L = math.hypot(x2 - x1, y2 - y1)
            if L < 0.5:
                continue
            t = _aci_farki(_aci((x1, y1), (x2, y2)), 0.0)
            if not (3.0 <= t <= 60.0):
                continue
            ab = _esle((x1 + x2) / 2, (y1 + y2) / 2)
            if ab is None:
                continue
            a, b = ab
            z1, z2 = sorted((a * y1 + b, a * y2 + b))
            egim = round(math.tan(math.radians(t)), 3)
            k = (e.layer, round(z1, 1), round(z2, 1), egim)
            r = out.setdefault(k, {"layer": e.layer, "zlo": round(z1, 2), "zhi": round(z2, 2), "egim": egim, "boy": 0.0})
            r["boy"] = round(r["boy"] + L, 2)
    return sorted(out.values(), key=lambda r: (r["layer"], r["zlo"]))


def member_axis_angle(points: list, tek_cizgi: bool) -> float | None:
    """Eleman ekseninin plan doğrultusu (derece, [0, 180))."""
    try:
        if tek_cizgi:
            return _aci(points[0], points[-1])
        c = list(_eksen(Polygon(points)).coords)
        return _aci(c[0], c[-1])
    except Exception:
        return None
