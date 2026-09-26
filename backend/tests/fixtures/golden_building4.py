"""Altın bina 4: merdivenli ve teras çatılı 3 katlı konut (cm çizim, tek dosya), ölçüsü bilinen.

Sınadığı:
  - betonarme İKİ KOLLU merdiven (zemin ve 1. kat kalıp planında, S-STAIR katmanı): kollar basamak çizgili
    dikdörtgen, ara sahanlık basamaksız dikdörtgen, not "M1 18x(28/16.67) h=15" (rıht adedi × (basamak / rıht) cm)
  - döşemede merdiven boşluğu (S-BOSLUK), mimari planda merdiven çizgileri (A-STAIR) ve MERDİVEN HOLÜ
  - teras çatı: en üst kalıp planında parapet 20/100 (S-PARAPET), mimari ÇATI PLANI'nda "TERAS ÇATI (GEZİLMEYEN)"

Eksenler x 0/6000/12000, y 0/5000/10000 (mm); kolon 40/40; kiriş 25/50 (çevre kirişi dış yüzle aynı hizada);
döşeme 15 cm; kat yüksekliği 3,00 (±0,00 / +3,00 / +6,00 / çatı +9,00); radye 60 cm (üstü ±0,00), taşma 50 cm.
"""
import math
from pathlib import Path

import ezdxf
from shapely.geometry import LineString, box

XS = (0, 6000, 12000)
YS = (0, 5000, 10000)
D, H, PER = 150, 3000, 200
X0, X1, Y0, Y1 = -PER, 12000 + PER, -PER, 10000 + PER
T_EXT = 250
# merdiven (mm): iki kol + ara sahanlık; kollar y yönünde
ST_W, ST_GOZ, ST_A, ST_N, ST_T = 1200, 200, 280, 18, 150
ST_H = H / ST_N                              # rıht 166,67
ST_X, ST_Y = 6400, 5400                      # merdivenin sol-alt köşesi
ST_TREADS = ST_N // 2 - 1                    # kol başına basamak (9 rıht, 8 basamak)
ST_RUN = ST_TREADS * ST_A                    # 2240
KOL_A = (ST_X, ST_Y, ST_X + ST_W, ST_Y + ST_RUN)
KOL_B = (ST_X + ST_W + ST_GOZ, ST_Y, ST_X + 2 * ST_W + ST_GOZ, ST_Y + ST_RUN)
SAHANLIK = (ST_X, ST_Y + ST_RUN, ST_X + 2 * ST_W + ST_GOZ, ST_Y + ST_RUN + ST_W)
BOSLUK = (ST_X, ST_Y, ST_X + 2 * ST_W + ST_GOZ, ST_Y + ST_RUN + ST_W)
PAR_B, PAR_H = 200, 1000
SHEET_DX = 30000


def cols():
    return [(x, y, PER) for y in YS for x in XS]


def beams():
    out, n = [], 101
    for y in YS:
        yc = (Y0 + 125) if y == 0 else (Y1 - 125) if y == YS[-1] else y
        for xa, xb in zip(XS[:-1], XS[1:]):
            out.append((f"K{n}", 250, 500, (xa + PER, yc), (xb - PER, yc))); n += 1
    for x in XS:
        xc = (X0 + 125) if x == 0 else (X1 - 125) if x == XS[-1] else x
        for ya, yb in zip(YS[:-1], YS[1:]):
            out.append((f"K{n}", 250, 500, (xc, ya + PER), (xc, yb - PER))); n += 1
    return out


def cevre():
    out = []
    for y in (0, YS[-1]):
        y0 = Y0 if y == 0 else Y1 - 250
        for xa, xb in zip(XS[:-1], XS[1:]):
            out.append((xa + PER, y0, xb - PER, y0 + 250))
    for x in (0, XS[-1]):
        x0 = X0 if x == 0 else X1 - 250
        for ya, yb in zip(YS[:-1], YS[1:]):
            out.append((x0, ya + PER, x0 + 250, yb - PER))
    return out


def openings(kat):
    ys, yn, xw, xe = Y0 + 125, Y1 - 125, X0 + 125, X1 - 125
    o = [("P", "P1", 1500, 1500, (2500, ys), "x", T_EXT), ("P", "P1", 1500, 1500, (xw, 2500), "y", T_EXT),
         ("P", "P2", 1200, 1200, (9000, ys), "x", T_EXT), ("P", "P1", 1500, 1500, (2500, yn), "x", T_EXT),
         ("P", "P1", 1500, 1500, (xw, 7500), "y", T_EXT), ("P", "P3", 1200, 1500, (10600, yn), "x", T_EXT),
         ("K", "K1", 900, 2100, (6000, 2450), "y", 100), ("K", "K1", 900, 2100, (2450, 5000), "x", 100),
         ("K", "K1", 900, 2100, (10450, 5000), "x", 100), ("K", "K1", 900, 2100, (6000, 7450), "y", 100)]
    if kat == 0:
        o.append(("K", "DK", 1000, 2100, (xe, 7500), "y", T_EXT))          # bina girişi, merdiven holü doğu
    return o


def walls(kat):
    op = openings(kat)
    w = []
    for r in cevre():
        x0, y0, x1, y1 = r
        gaps = [(cy - wd / 2, cy + wd / 2) if yon == "y" else (cx - wd / 2, cx + wd / 2)
                for t, _n, wd, _h, (cx, cy), yon, _tt in op if t == "K" and x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1]
        w.append(("A-WALL-YTONG-25", r, gaps))
    for r, gaps in (((5950, PER, 6050, 5000 - PER), [(2000, 2900)]), ((5950, 5000 + PER, 6050, 10000 - PER), [(7000, 7900)]),
                    ((PER, 4950, 6000 - PER, 5050), [(2000, 2900)]), ((6000 + PER, 4950, 12000 - PER, 5050), [(10000, 10900)])):
        w.append(("A-WALL-TUGLA-10", r, gaps))
    return w


ROOMS = [("SALON", (X0 + T_EXT, Y0 + T_EXT, 5950, 4950)), ("MUTFAK", (6050, Y0 + T_EXT, X1 - T_EXT, 4950)),
         ("YATAK ODASI", (X0 + T_EXT, 5050, 5950, Y1 - T_EXT)), ("MERDİVEN HOLÜ", (6050, 5050, X1 - T_EXT, Y1 - T_EXT))]


def room_poly(r):
    p = box(*r)
    for x, y, hw in cols():
        p = p.difference(box(x - hw, y - hw, x + hw, y + hw))
    return p


class _P:
    def __init__(self, msp):
        self.msp = msp

    def p(self, x, y, ox):
        return ((x + ox) / 10.0, y / 10.0)          # mm → cm

    def rect(self, r, layer, ox):
        x0, y0, x1, y1 = r
        self.msp.add_lwpolyline([self.p(x0, y0, ox), self.p(x1, y0, ox), self.p(x1, y1, ox), self.p(x0, y1, ox)],
                                close=True, dxfattribs={"layer": layer})

    def line(self, a, b, layer, ox):
        self.msp.add_line(self.p(*a, ox), self.p(*b, ox), dxfattribs={"layer": layer})

    def txt(self, s, x, y, h, layer, ox):
        self.msp.add_text(s, dxfattribs={"layer": layer, "height": h / 10.0}).set_placement(self.p(x, y, ox))

    def sheet(self, i, title):
        ox = i * SHEET_DX
        self.rect((-3000, -4000, 18000, 14000), "ANTET", ox)
        self.txt(title, 0, -3000, 400, "ANTET", ox)
        return ox


def _merdiven(P, ox, layer, not_yaz):
    for r in (KOL_A, KOL_B, SAHANLIK):
        P.rect(r, layer, ox)
    for kol in (KOL_A, KOL_B):
        for i in range(1, ST_TREADS):
            y = kol[1] + i * ST_A
            P.line((kol[0], y), (kol[2], y), layer, ox)
    if not_yaz:
        P.txt(f"M1 {ST_N}x({ST_A // 10}/{ST_H / 10:.2f}) h={ST_T // 10}", ST_X + 100, ST_Y + ST_RUN + ST_W + 150, 120, "S-ANNO", ox)


def make_golden_building4(path) -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for n in ("ANTET", "S-ANNO", "S-COLS", "S-BEAM", "S-SLAB", "S-BOSLUK", "S-STAIR", "S-PARAPET", "S-FOOTING",
              "A-ANNO", "A-WALL-YTONG-25", "A-WALL-TUGLA-10", "A-DOOR", "A-GLAZ", "A-AREA-IDEN", "A-STAIR", "A-ROOF", "A-SECT"):
        doc.layers.add(n)
    msp = doc.modelspace()
    win = doc.blocks.new("WIN")
    win.add_lwpolyline([(-50, -12.5), (50, -12.5), (50, 12.5), (-50, 12.5)], close=True)
    win.add_line((-50, 0), (50, 0))
    door = doc.blocks.new("DOOR")
    door.add_line((-50, 0), (-50, 100))
    door.add_arc((-50, 0), 100, 0, 90)
    P = _P(msp)
    # temel
    ox = P.sheet(0, "TEMEL KALIP PLANI")
    P.rect((X0 - 500, Y0 - 500, X1 + 500, Y1 + 500), "S-FOOTING", ox)
    P.txt("R1 RADYE h=60", 5000, 4000, 250, "S-ANNO", ox)
    P.txt("RADYE ÜST KOTU ±0.00", 1000, 11000, 250, "S-ANNO", ox)
    for x, y, hw in cols():
        P.rect((x - hw, y - hw, x + hw, y + hw), "S-COLS", ox)
    # kalıp planları
    for i, (title, kot, merd, cati) in enumerate((("ZEMİN KAT KALIP PLANI", "+3.00", True, False),
                                                  ("1. KAT KALIP PLANI", "+6.00", True, False),
                                                  ("2. KAT KALIP PLANI", "+9.00", False, True)), 1):
        ox = P.sheet(i, title)
        for k, (x, y, hw) in enumerate(cols(), 1):
            P.rect((x - hw, y - hw, x + hw, y + hw), "S-COLS", ox)
            P.txt(f"S{k} 40/40", x + hw + 50, y + hw + 50, 120, "S-ANNO", ox)
        for name, b, h, (xa, ya), (xb, yb) in beams():
            if ya == yb:
                for yy in (ya - b / 2, ya + b / 2):
                    P.line((xa, yy), (xb, yy), "S-BEAM", ox)
                P.txt(f"{name} {b // 10}/{h // 10}", (xa + xb) / 2 - 500, ya + b / 2 + 60, 120, "S-ANNO", ox)
            else:
                for xx in (xa - b / 2, xa + b / 2):
                    P.line((xx, ya), (xx, yb), "S-BEAM", ox)
                P.txt(f"{name} {b // 10}/{h // 10}", xa + b / 2 + 60, (ya + yb) / 2, 120, "S-ANNO", ox)
        P.rect((X0, Y0, X1, Y1), "S-SLAB", ox)
        for xa, xb in zip(XS[:-1], XS[1:]):
            for ya, yb in zip(YS[:-1], YS[1:]):
                P.txt("D h=15", (xa + xb) / 2 - 300, (ya + yb) / 2 - 1500, 150, "S-ANNO", ox)
        if merd:
            P.rect(BOSLUK, "S-BOSLUK", ox)
            _merdiven(P, ox, "S-STAIR", True)
        if cati:
            for yy in (Y0, Y0 + PAR_B):
                P.line((X0, yy), (X1, yy), "S-PARAPET", ox)
            for yy in (Y1, Y1 - PAR_B):
                P.line((X0, yy), (X1, yy), "S-PARAPET", ox)
            for xx in (X0, X0 + PAR_B):
                P.line((xx, Y0 + PAR_B), (xx, Y1 - PAR_B), "S-PARAPET", ox)
            for xx in (X1, X1 - PAR_B):
                P.line((xx, Y0 + PAR_B), (xx, Y1 - PAR_B), "S-PARAPET", ox)
            P.txt(f"PARAPET {PAR_B // 10}/{PAR_H // 10}", 5000, Y1 + 150, 150, "S-ANNO", ox)
        P.txt(f"DÖŞEME ÜST KOTU {kot}", 1000, 11000, 250, "S-ANNO", ox)
    # mimari planlar
    for j, (title, kot) in enumerate((("ZEMİN KAT PLANI", "±0.00"), ("1. KAT PLANI", "+3.00"), ("2. KAT PLANI", "+6.00"))):
        ox = P.sheet(4 + j, title)
        for x, y, hw in cols():
            P.rect((x - hw, y - hw, x + hw, y + hw), "S-COLS", ox)
        for layer, (x0, y0, x1, y1), gaps in walls(j):
            yatay = (x1 - x0) >= (y1 - y0)
            a0, a1 = (x0, x1) if yatay else (y0, y1)
            c0, c1 = (y0, y1) if yatay else (x0, x1)
            parca, cur = [], a0
            for s, e in sorted(gaps):
                parca.append((cur, s)); cur = e
            parca.append((cur, a1))
            for p0, p1 in parca:
                for c in (c0, c1):
                    P.line((p0, c) if yatay else (c, p0), (p1, c) if yatay else (c, p1), layer, ox)
                for v in (p0, p1):
                    P.line((v, c0) if yatay else (c0, v), (v, c1) if yatay else (c1, v), layer, ox)
        for t, ad, wd, hh, (cx, cy), yon, tk in openings(j):
            blk, lay = ("WIN", "A-GLAZ") if t == "P" else ("DOOR", "A-DOOR")
            msp.add_blockref(blk, P.p(cx, cy, ox), dxfattribs={"layer": lay, "rotation": 0 if yon == "x" else 90,
                                                                "xscale": wd / 1000, "yscale": tk / 250 if t == "P" else wd / 1000})
            lx, ly = (cx - 300, cy + tk / 2 + 150) if yon == "x" else (cx + tk / 2 + 150, cy)
            P.txt(f"{ad} {wd // 10}/{hh // 10}", lx, ly, 120, "A-ANNO", ox)
        _merdiven(P, ox, "A-STAIR", False)
        for ad, r in ROOMS:
            pg = room_poly(r)
            pt = (r[0] + 300, (r[1] + r[3]) / 2) if ad == "MERDİVEN HOLÜ" else (pg.representative_point().x, pg.representative_point().y)
            if ad == "MERDİVEN HOLÜ":
                pt = (10600, 6500)
            P.txt(f"{ad} {pg.area / 1e6:.2f} m²".replace(".", ","), pt[0] - 800, pt[1], 180, "A-AREA-IDEN", ox)
        P.txt(kot, 3000, 11000, 250, "A-ANNO", ox)
    # çatı planı
    ox = P.sheet(7, "ÇATI PLANI")
    P.rect((X0, Y0, X1, Y1), "A-ROOF", ox)
    P.rect((X0 + PAR_B, Y0 + PAR_B, X1 - PAR_B, Y1 - PAR_B), "A-ROOF", ox)
    P.txt("TERAS ÇATI (GEZİLMEYEN)", 3000, 5000, 250, "A-ANNO", ox)
    P.txt("+9.00", 3000, 4000, 250, "A-ANNO", ox)
    # kesit
    ox = P.sheet(8, "A-A KESİTİ")
    for z in (-600, 0, 3000, 6000, 9000):
        P.line((X0 - 500, z), (X1 + 500, z), "A-SECT", ox)
        P.txt(f"{z / 1000:+.2f}".replace("+0.00", "±0.00"), X1 + 800, z, 250, "A-ANNO", ox)
    path = Path(path)
    doc.saveas(path)
    return path


# ------------------------------------------------------------------ doğru metraj (elle)
def stair_truth() -> dict:
    """Bir merdiven (bir kat). Kurallar: beton = eğik plak + basamak üçgenleri + ara sahanlık; kalıp = plak altı (eğik)
    + sahanlık altı + rıht yüzleri; kaplama = basamak + rıht + sahanlık; korkuluk = iki kolun eğik boyu + göz;
    merdiven altı sıva-boya = plak altı + sahanlık altı."""
    m = 1e-3
    rise_kol = (ST_N // 2) * ST_H * m
    egik = math.hypot(ST_RUN * m, rise_kol)
    w, t, a, h = ST_W * m, ST_T * m, ST_A * m, ST_H * m
    sah = (2 * ST_W + ST_GOZ) * ST_W * m * m
    basamak = 2 * ST_TREADS
    return {"beton": 2 * egik * w * t + basamak * a * h / 2 * w + sah * t,
            "kalip": 2 * egik * w + sah + ST_N * h * w,
            "kaplama": basamak * a * w + ST_N * h * w + sah,
            "korkuluk": 2 * egik + ST_GOZ * m,
            "alti": 2 * egik * w + sah,
            "plan": (BOSLUK[2] - BOSLUK[0]) * (BOSLUK[3] - BOSLUK[1]) * m * m}


def golden_truth4() -> dict:
    m = 1e-3
    s = stair_truth()
    t = {}
    t["kolon"] = 3 * sum((2 * hw * m) ** 2 for *_, hw in cols()) * (H - D) * m
    t["kiris"] = 3 * sum((abs(xb - xa) + abs(yb - ya)) * m * b * m * (h - D) * m for _, b, h, (xa, ya), (xb, yb) in beams())
    alan = (X1 - X0) * (Y1 - Y0) * m * m
    bos = (BOSLUK[2] - BOSLUK[0]) * (BOSLUK[3] - BOSLUK[1]) * m * m
    t["doseme"] = (3 * alan - 2 * bos) * D * m                      # +3.00 ve +6.00 döşemelerinde merdiven boşluğu
    t["merdiven_beton"] = 2 * s["beton"]
    t["merdiven_kalip"] = 2 * s["kalip"]
    t["merdiven_kaplama"] = 2 * s["kaplama"]
    t["korkuluk"] = 2 * s["korkuluk"]
    t["merdiven_alti"] = 2 * s["alti"]
    t["parapet_beton"] = 2 * ((X1 - X0 - PAR_B) + (Y1 - Y0 - PAR_B)) * m * PAR_B * m * PAR_H * m
    t["parapet_kalip"] = 2 * 2 * ((X1 - X0 - PAR_B) + (Y1 - Y0 - PAR_B)) * m * PAR_H * m
    t["cati"] = (X1 - X0 - 2 * PAR_B) * (Y1 - Y0 - 2 * PAR_B) * m * m
    t["radye"] = (X1 - X0 + 1000) * (Y1 - Y0 + 1000) * m * m * 0.6
    # mahaller: merdiven holünün zemini ve (üstünde kat olan katlarda) tavanı merdiven boşluğu kadar eksik
    oda = {ad: room_poly(r).area * m * m for ad, r in ROOMS}
    t["kuru"] = 3 * sum(oda.values()) - 3 * s["plan"]
    t["tavan"] = 3 * sum(oda.values()) - 2 * s["plan"] + t["merdiven_alti"]
    t["kapi"] = 3 * 4 + 1
    t["pencere"] = 3 * 6
    t["kat_sayisi"] = 3
    return t
