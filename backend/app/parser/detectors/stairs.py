"""Betonarme merdiven tespiti (kalıp planı).

Kalıp planında merdiven, merdiven katmanında (MERDİVEN / STAIR) çizilir:
  - kol     : içinde basamak çizgileri olan dikdörtgen; basamak çizgisinin boyu kol genişliği, dik kenarı yatay boy
  - sahanlık: basamak çizgisi olmayan, kola bitişik dikdörtgen
  - not     : "M1 18x(28/16.67) h=15" — rıht adedi × (basamak / rıht, cm) ve plak kalınlığı. Türk projelerinde
              merdiven yanına yazılan alışılmış biçim (zones._STAIR_NOTE aynısını mimari planda okur).
Birbirine değen kollar ve sahanlıklar tek merdivendir. Ölçüler meta'ya yazılır; beton / kalıp motorda
(quantity/engine.stair_geometry), ince işler (kaplama, korkuluk, merdiven altı) keşifte aynı geometriden hesaplanır.
Not yoksa rıht yüksekliği kat yüksekliğinden türetilir (kat yüksekliği / toplam rıht) ve bu uyarı olarak yazılır;
plak kalınlığı yazmıyorsa 15 cm kabul edilir (uyarı).
"""
from __future__ import annotations

import re

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from ..geometry import min_area_rect
from ..loader import Drawing
from .base import DetectParams, DetectedElement

NOTE = re.compile(r"(\d{1,2})\s*[xX×*]\s*\(\s*(\d{2}(?:[.,]\d+)?)\s*/\s*(\d{1,2}(?:[.,]\d+)?)\s*\)")
THICK = re.compile(r"\b[hHdD]\s*=\s*(\d{1,2}(?:[.,]\d+)?)")
NOTE_REACH = 3.0          # m — not merdivenin bu kadar yakınında olmalı
DEFAULT_T = 0.15
MIN_TREADS = 2            # kol sayılması için en az basamak çizgisi


def _rects(drawing: Drawing, layers: list[str]) -> list[Polygon]:
    out = []
    for e in drawing.entities:
        if e.layer not in layers or not e.is_closed_polygon:
            continue
        try:
            p = Polygon(e.points).buffer(0)
        except Exception:
            continue
        if p.is_empty or p.area < 0.2:
            continue
        L, S, _ = min_area_rect(list(p.exterior.coords)[:-1])
        if L * S > 0 and p.area / (L * S) > 0.9:
            out.append(p)
    return out


def _tread_flights(cizgi: list) -> list[dict]:
    """Kol dikdörtgeni olmayan çizim: eşit boylu, paralel, eşit aralıklı (22–40 cm) basamak çizgisi dizisi bir koldur.
    Dizinin kapladığı dikdörtgen kolun planıdır (ilk ve son çizgi kolun başı ve sonu kabul edilir)."""
    import math
    from collections import defaultdict
    gruplar: dict = defaultdict(list)
    for c in cizgi:
        (x0, y0), (x1, y1) = c.coords[0], c.coords[-1]
        L = c.length
        if L < 0.7:
            continue
        ang = round(math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180.0)
        gruplar[(ang, round(L, 1))].append(c)
    out = []
    for (ang, L), cs in gruplar.items():
        if len(cs) < 4:
            continue
        ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        nx, ny = -uy, ux
        cs = sorted(cs, key=lambda c: c.centroid.x * nx + c.centroid.y * ny)
        # dizi: art arda eşit aralık, aynı hizada başlayan çizgiler
        dizi = [cs[0]]
        for c in cs[1:]:
            d = (c.centroid.x - dizi[-1].centroid.x) * nx + (c.centroid.y - dizi[-1].centroid.y) * ny
            yan = abs((c.centroid.x - dizi[-1].centroid.x) * ux + (c.centroid.y - dizi[-1].centroid.y) * uy)
            if 0.22 <= d <= 0.40 and yan < 0.05:
                dizi.append(c)
                continue
            if len(dizi) >= 4:
                out.append(dizi)
            dizi = [c]
        if len(dizi) >= 4:
            out.append(dizi)
    kollar = []
    for dizi in out:
        aralik = [(b.centroid.x - a.centroid.x, b.centroid.y - a.centroid.y) for a, b in zip(dizi, dizi[1:])]
        ort = sum(math.hypot(*v) for v in aralik) / len(aralik)
        if any(abs(math.hypot(*v) - ort) > 0.1 * ort for v in aralik):
            continue
        poly = unary_union([c.buffer(0.001) for c in dizi]).convex_hull
        kollar.append({"poly": poly, "w": dizi[0].length, "run": ort * (len(dizi) - 1), "treads": len(dizi) - 1})
    return kollar


def detect_stairs(drawing: Drawing, layers: list[str], params: DetectParams) -> list[DetectedElement]:
    if not layers:
        return []
    rects = _rects(drawing, layers)
    cizgi = []
    for e in drawing.entities:
        if e.layer in layers and e.kind in ("line", "polyline") and len(e.points) == 2:
            cizgi.append(LineString(e.points))
    kollar, sahanliklar = [], []
    for p in rects:
        ic = [c for c in cizgi if p.buffer(0.02).contains(c) and c.length > 0.3]
        L, S, _ = min_area_rect(list(p.exterior.coords)[:-1])
        if len(ic) >= MIN_TREADS:
            w = sorted(c.length for c in ic)[len(ic) // 2]
            run = L if abs(S - w) < abs(L - w) else S
            kollar.append({"poly": p, "w": w, "run": run, "treads": len(ic) + 1})
        else:
            sahanliklar.append({"poly": p, "area": p.area, "long": L})
    if not kollar:
        kollar = _tread_flights(cizgi)             # kol dikdörtgeni çizilmemiş: yalnız basamak çizgileri
        if not kollar:
            return []
    notlar = [(e.points[0], e.text) for e in drawing.texts() if NOTE.search(e.text or "")]
    # kolları ve sahanlıkları değme ile öbekle
    parcalar = [("kol", k) for k in kollar] + [("sah", s) for s in sahanliklar]
    grup = list(range(len(parcalar)))

    def kok(i):
        while grup[i] != i:
            grup[i] = grup[grup[i]]
            i = grup[i]
        return i
    for i in range(len(parcalar)):
        for j in range(i + 1, len(parcalar)):
            if parcalar[i][1]["poly"].distance(parcalar[j][1]["poly"]) < 0.05:
                grup[kok(i)] = kok(j)
    obek: dict[int, list] = {}
    for i, pc in enumerate(parcalar):
        obek.setdefault(kok(i), []).append(pc)
    out: list[DetectedElement] = []
    for parca in obek.values():
        ks = [p for t, p in parca if t == "kol"]
        if not ks:
            continue
        ss = [p for t, p in parca if t == "sah"]
        hull = unary_union([p["poly"] for _, p in parca])
        warn = []
        n = a = h = None
        t = None
        yakin = sorted(((hull.distance(Point(pt)), txt) for pt, txt in notlar), key=lambda x: x[0])
        if yakin and yakin[0][0] <= NOTE_REACH:
            txt = yakin[0][1]
            m = NOTE.search(txt)
            # not her zaman santimetredir ("28/16.67"), çizim birimi ne olursa olsun
            n, a, h = int(m.group(1)), float(m.group(2).replace(",", ".")) * 0.01, float(m.group(3).replace(",", ".")) * 0.01
            mt = THICK.search(txt[m.end():]) or THICK.search(txt)
            if mt:
                t = float(mt.group(1).replace(",", ".")) * 0.01
        if t is None:
            t = DEFAULT_T
            warn.append(f"Merdiven plak kalınlığı yazmıyor; {DEFAULT_T * 100:.0f} cm kabul edildi")
        kol_meta = []
        for kol in ks:
            treads = round(kol["run"] / a) if a else kol["treads"]
            kol_meta.append({"w": round(kol["w"], 3), "run": round(kol["run"], 3), "treads": int(treads),
                             "risers": int(treads) + 1})
        top_riht = sum(k["risers"] for k in kol_meta)
        if n and abs(n - top_riht) > 1:
            warn.append(f"Nottaki rıht adedi ({n}) kollardan sayılanla ({top_riht}) tutmuyor; kollar esas alındı")
        if h is None:
            warn.append("Merdiven notu (rıht × (basamak / rıht)) yok; rıht yüksekliği kat yüksekliğinden türetildi")
        genis = sum(k["w"] for k in kol_meta)
        goz = max((max(s["long"] for s in ss) - genis) if (ss and len(kol_meta) >= 2) else 0.0, 0.0)
        pts = list(hull.convex_hull.exterior.coords)[:-1] if hull.geom_type != "Polygon" else list(hull.exterior.coords)[:-1]
        el = DetectedElement(etype="stair", layer=layers[0], points=pts, area=hull.area,
                             source="STAIR", confidence=0.85 if h else 0.6, name="Merdiven")
        el.thickness = t
        el.meta = {"flights": kol_meta, "landing_area": round(sum(s["area"] for s in ss), 4),
                   "riser_h": round(h, 4) if h else None, "t": t, "goz": round(goz, 3), "note_risers": n}
        el.warnings.extend(warn)
        el.label_raw = yakin[0][1] if yakin and yakin[0][0] <= NOTE_REACH else ""
        out.append(el)
    return out
