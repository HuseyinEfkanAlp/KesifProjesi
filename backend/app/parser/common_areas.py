"""Ortak alan blokları: mimarın lobi / koridor / ışıklık döşeme planlarını adlı blok olarak koyduğu dosyalar.

A blokları mimari çalışma dosyasında ("A Bloklar _ 09.dxf") ortak alanlar pafta başlığı ya da alan çizgisi
olarak değil, **adlı bloklar** olarak durur: "a2 blok zemin kat lobi", "a3 1.kat lobi", "a bloklar 1. kat lobi
seramik", "orta alan döş planı", "a1a2 ışıklık". Blok adı ne olduğunu, hangi bloğa ve kata ait olduğunu söyler;
içindeki seramik ızgarası kapladığı alanı verir. Paftaların dışına bırakılmış olabilirler — bu okuma pafta
ayrımına bağlı değildir, doğrudan kaynak dosyadan yapılır.

Adım adım:
1. Model uzayındaki INSERT'lerden adı ortak alan diyenler (iç içe bloklar dahil) bulunur.
2. Her birinin çizgileri yerleşim dönüşümüyle model koordinatına alınır; birbirine OBEK_BOSLUK'tan yakın
   çizgiler bir öbektir (tek lobi); öbeğin dış kabuğu alanıdır.
3. Öbek hangi bloğun? Önce adından ("a2 …" → A2); tek blokta birden çok lobi taşıyan bloklarda planın büyük
   "A1…A5" blok yazılarından en yakını. Paftaların dışına konmuş blok, lobi biçimleri (en × boy) yerinde duran
   bir başka lobi bloğuyla eşleştirilerek plana kaydırılır — kat kat aynı lobi aynı biçimdedir.
4. Kat: adından ("zemin", "1.kat", "bodrum"). Tür: lobi / koridor (orta alan, döşeme planı) / ışıklık / tavan.

Aynı (blok, kat, tür) için birden çok kaynak varsa bloğa özel olan ("a2 blok zemin kat lobi") genel olana
("a bloklar …") tercih edilir — bloğa özel çizim daha günceldir.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from shapely.geometry import LineString
from shapely.ops import unary_union

from .sheets import _clean_text, _iter_entities, _open_dxf_text, _read_block_defs

NAME = re.compile(r"LOB[İI]|ORTA\s*ALAN|ORTAK\s*ALAN|KOR[İI]DOR|I[ŞS]IKLIK|D[ÖO][ŞS]EME\s*PLAN|TAVAN", re.IGNORECASE)
_BLOK_ADI = re.compile(r"\b([A-Z])\s*([1-9])\b")
_TEK_BLOK = re.compile(r"(?<![A-Z0-9])([A-Za-z])\s*-?\s*([1-9])\s*(?:BLOK)?\b", re.IGNORECASE)
_GENEL = re.compile(r"BLOKLAR|[A-Z]\d+\s*[A-Z]\d+|[A-Z]\d+\s*-\s*[A-Z]\d+", re.IGNORECASE)
OBEK_BOSLUK = 1.0          # m — bir lobinin döşeme çizgileri arasında bundan büyük boşluk yok
MIN_ALAN = 2.0             # m²
ETIKET_YAKIN = 45.0        # m — blok yazısına bu kadar yakın öbek "yerinde" sayılır
BICIM_TOL = 0.3            # m — iki lobi biçimi (en, boy) bu kadar yakınsa aynı lobidir
BLOK_ETIKET_MIN_H = 0.5    # m — "A1" blok yazısı en az bu yükseklikte (plan içi küçük yazılar değil)
MAX_DEPTH = 4


def kind_of(name: str) -> str:
    n = name.upper().replace("İ", "I").replace("Ş", "S").replace("Ö", "O")
    if "TAVAN" in n:
        return "tavan"
    if "ISIKLIK" in n:
        return "isiklik"
    if "LOBI" in n:
        return "lobi"
    return "koridor"          # orta alan / ortak alan / koridor / döşeme planı


def floor_of(name: str) -> float | None:
    from .levels import floor_rank
    return floor_rank(name)


def block_of(name: str) -> str:
    """Adda tek bir blok geçiyorsa o ("a2 blok zemin kat lobi" → A2); genel / çoklu adsa ""."""
    if _GENEL.search(name):
        return ""
    m = _TEK_BLOK.search(name)
    return f"{m.group(1).upper()}{m.group(2)}" if m else ""


def scan_common_areas(src: str, unit_scale: float = 0.01, sheets: list | None = None) -> list[dict]:
    """Kaynak dosyadan ortak alan satırları: [{"blok", "kat", "tur", "alan", "kaynak", "yer", "en", "boy"}].
    unit_scale: çizim birimi → m (cm = 0.01). sheets: [(bbox çizim biriminde, başlık)] — adında kat yazmayan
    blok, yerleştiği paftanın başlığından katını alır ("ZEMİN KAT YERLEŞİM PLANI")."""
    from .levels import floor_rank
    pafta = [(b, floor_rank(t or "")) for b, t in (sheets or [])]

    def pafta_kati(x: float, y: float) -> float | None:
        for (x0, y0, x1, y1), r in pafta:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return r
        return None
    k = unit_scale
    inserts, etiket = [], []
    with _open_dxf_text(src) as f:
        for e in _iter_entities(f):
            if e["t"] in ("TEXT", "MTEXT") and e.get("xs"):
                t = _clean_text("".join(e.get("3", [])) + e.get("1", "")).strip().upper()
                if _BLOK_ADI.fullmatch(t) and float(e.get("40", 0) or 0) * k >= BLOK_ETIKET_MIN_H:
                    etiket.append((t.replace(" ", ""), e["xs"][0] * k, e["ys"][0] * k))
            elif e["t"] == "INSERT" and e.get("2") and e.get("xs"):
                inserts.append(e)
    if not inserts:
        return []
    defs: dict[str, dict] = {}
    want = {i["2"] for i in inserts}
    for _ in range(MAX_DEPTH):
        missing = {n for n in want if n not in defs}
        if not missing:
            break
        got = _read_block_defs(src, missing)
        for n in missing:
            defs[n] = got.get(n) or {"base": [0.0, 0.0], "ents": [], "skipped": False}
            for e in defs[n]["ents"]:
                if e["t"] == "INSERT" and e.get("2"):
                    want.add(e["2"])

    def lines(name: str, tf, depth: int = 0) -> list:
        d = defs.get(name)
        if not d or d.get("skipped") or depth > MAX_DEPTH:
            return []
        bx, by = d["base"]
        out, poly = [], None
        for e in d["ents"]:
            t = e["t"]
            if t == "INSERT" and e.get("2") and e["xs"] and e["ys"]:
                sx, sy = float(e.get("41", 1) or 1), float(e.get("42", 1) or 1)
                a = math.radians(float(e.get("50", 0) or 0))
                ix, iy = e["xs"][0] - bx, e["ys"][0] - by
                out += lines(e["2"], lambda x, y, sx=sx, sy=sy, a=a, ix=ix, iy=iy:
                             tf(ix + x * sx * math.cos(a) - y * sy * math.sin(a), iy + x * sx * math.sin(a) + y * sy * math.cos(a)),
                             depth + 1)
            elif t == "POLYLINE":
                poly = []
            elif t == "VERTEX" and poly is not None and e["xs"] and e["ys"]:
                poly.append(tf(e["xs"][0] - bx, e["ys"][0] - by))
            elif t == "SEQEND":
                if poly and len(poly) >= 2:
                    out.append(LineString(poly))
                poly = None
            elif t in ("LINE", "LWPOLYLINE") and len(e["xs"]) >= 2 and len(e["ys"]) >= 2:
                out.append(LineString([tf(x - bx, y - by) for x, y in zip(e["xs"], e["ys"])]))
        return out

    def named(name: str, depth: int = 0) -> list[str]:
        """Bu bloğun kendisi ya da içindeki bloklardan adı ortak alan diyenler."""
        out = [name] if NAME.search(name) else []
        if depth < MAX_DEPTH and not out:
            for e in (defs.get(name) or {}).get("ents", []):
                if e["t"] == "INSERT" and e.get("2"):
                    out += named(e["2"], depth + 1)
        return out

    obekler = []      # (ad, alan, uzun, kısa, cx, cy, kat)
    for ins in inserts:
        ins_kat = pafta_kati(ins["xs"][0], ins["ys"][0])
        for ad in dict.fromkeys(named(ins["2"])):
            sx, sy = float(ins.get("41", 1) or 1), float(ins.get("42", 1) or 1)
            a = math.radians(float(ins.get("50", 0) or 0))
            X, Y = ins["xs"][0], ins["ys"][0]
            # iç içe blokta ad alt bloktadır; basitlik için dış yerleşim kullanılır (alt blok ofseti içeride dönüşür)
            kaynak = ins["2"] if ad == ins["2"] else ad
            g = lines(kaynak if ad == ins["2"] else ins["2"],
                      lambda x, y, sx=sx, sy=sy, a=a, X=X, Y=Y: ((X + x * sx * math.cos(a) - y * sy * math.sin(a)) * k,
                                                                  (Y + x * sx * math.sin(a) + y * sy * math.cos(a)) * k))
            if not g:
                continue
            u = unary_union([x.buffer(OBEK_BOSLUK) for x in g])
            for p in (list(u.geoms) if hasattr(u, "geoms") else [u]):
                h = unary_union([x for x in g if p.intersects(x)]).convex_hull
                if h.area < MIN_ALAN:
                    continue
                x0, y0, x1, y1 = h.bounds
                kat = floor_of(ad)
                obekler.append((ad, h.area, max(x1 - x0, y1 - y0), min(x1 - x0, y1 - y0), h.centroid.x, h.centroid.y,
                                kat if kat is not None else ins_kat))
    if not obekler:
        return []

    def en_yakin(x: float, y: float) -> tuple[str, float]:
        if not etiket:
            return "", float("inf")
        t = min(etiket, key=lambda t: (t[1] - x) ** 2 + (t[2] - y) ** 2)
        return t[0], math.hypot(t[1] - x, t[2] - y)

    yerinde = [o for o in obekler if en_yakin(o[4], o[5])[1] <= ETIKET_YAKIN]
    rows = []
    for ad in dict.fromkeys(o[0] for o in obekler):
        grup = [o for o in obekler if o[0] == ad]
        dx = dy = 0.0
        yer = "yerinde"
        if not all(en_yakin(o[4], o[5])[1] <= ETIKET_YAKIN for o in grup):
            oy = Counter()
            for o in grup:
                for r in yerinde:
                    if r[0] != ad and abs(o[2] - r[2]) < BICIM_TOL and abs(o[3] - r[3]) < BICIM_TOL:
                        oy[(round(r[4] - o[4]), round(r[5] - o[5]))] += 1
            if oy:
                (dx, dy), n = oy.most_common(1)[0]
                yer = f"biçim eşleşmesi ({n} lobi)"
            else:
                yer = "yerleştirilemedi"
        adblok = block_of(ad)
        for o in grup:
            # Blok: yakınında blok yazısı varsa o (tek blokta birden çok binanın lobisi olabilir — "a1 lobi döşeme
            # planı" A1..A5'in hepsini taşıyordu); yoksa addaki blok.
            yakin, mesafe = en_yakin(o[4] + dx, o[5] + dy) if yer != "yerleştirilemedi" else ("", float("inf"))
            blok = yakin if mesafe <= ETIKET_YAKIN else adblok
            rows.append({"blok": blok, "kat": o[6], "tur": kind_of(ad), "alan": round(o[1], 2),
                         "en": round(o[3], 2), "boy": round(o[2], 2), "kaynak": ad, "yer": yer,
                         # bloğa özel: adındaki blok öbeğin bloğuyla aynı ("a1 lobi döşeme planı" A2'nin
                         # lobisini de taşıyordu — orada genel kaynaktır)
                         "ozel": bool(adblok) and adblok == blok})
    # aynı (blok, kat, tür) için bloğa özel kaynak genel olanı ezer; aynı kaynağın tekrarları tekilleşir
    out, gorulen = [], set()
    for r in sorted(rows, key=lambda r: (not r["ozel"], r["kaynak"])):
        anahtar = (r["blok"], r["kat"], r["tur"])
        if r["ozel"]:
            if (anahtar, r["kaynak"], round(r["alan"])) in gorulen:
                continue
            gorulen.add((anahtar, r["kaynak"], round(r["alan"])))
            gorulen.add(anahtar)
        else:
            if anahtar in gorulen and r["tur"] == "lobi":
                continue
            if (anahtar, r["kaynak"], round(r["alan"])) in gorulen:
                continue
            gorulen.add((anahtar, r["kaynak"], round(r["alan"])))
        out.append(r)
    return out
