"""Altın bina 3: büyük karma yapı — 2 bodrum otopark + zemin 4 dükkân + 5 normal kat (katta 4 daire), ölçüsü bilinen.

Öncekilerin sınamadığı:
  - statik ve mimari AYRI DOSYA: statik cm ve orijini kaydırılmış (+500 m, +200 m), mimari mm ve orijinde
  - karma kullanım: zemin dükkân (kaba teslim, proje ayarı tenant_shell=1), üstü konut, bodrum otopark
  - kattan kata değişen kesitler: bodrum iç kolon 60/60 ve iç kiriş 30/60; zemin iç kiriş 30/70 (H=4,00); normal
    kat iç kiriş 30/50; çevre kolon 40/40, çevre kirişi 25/60 (dış yüzle aynı hizada); iç kolon 50/50
  - iki bodrum boyunca çevre perdesi; otoparkta serbest duran kolonlar
  - tip kat "1.-5. NORMAL KAT" (bir pafta beş kat), koridorda iki şaft boşluğu
  - her normal katta dört ayna daire (x ve y aynası): aynı adlı odalar

Eksenler x 0/6000/12000/18000/24000, y 0/5000/10000/15000 (mm). Kotlar: 2. bodrum −6,40, 1. bodrum −3,20, zemin ±0,00,
normal katlar +4,00 … +16,00, çatı +19,00. Döşeme 15 cm; radye 80 cm (üstü −6,40), 10 cm grobeton, 60 cm taşma.
"""
from pathlib import Path

import ezdxf
from shapely.geometry import LineString, box

XS = (0, 6000, 12000, 18000, 24000)
YS = (0, 5000, 10000, 15000)
D = 150
PER = 200
X0, X1, Y0, Y1 = -PER, 24000 + PER, -PER, 15000 + PER
T_EXT = 250
SHAFTS = [(5500, 7000, 6500, 8000), (17500, 7000, 18500, 8000)]
STATIK_OFS = (500000.0, 200000.0)        # statik dosyada orijin kayması (mm cinsinden; dosya cm)
SHEET_DX = 60000

# kat tipleri: (anahtar, ad, kat yüksekliği, kaç kat, taban kotu)
KATLAR = [("b2", "2. BODRUM", 3200, 1, -6400), ("b1", "1. BODRUM", 3200, 1, -3200), ("z", "ZEMİN", 4000, 1, 0),
          ("n", "1.-5. NORMAL", 3000, 5, 4000)]


def half(x, y, kat):
    ic = x in (6000, 12000, 18000) and y in (5000, 10000)
    if not ic:
        return PER
    return 300 if kat in ("b1", "b2") else 250


def cols(kat):
    return [(x, y, half(x, y, kat)) for y in YS for x in XS]


def beams(kat):
    """(ad, b, h, a, b) — kolon yüzünden yüze. Bodrumda çevre kirişi yok (perde)."""
    ic_h = {"b1": 600, "b2": 600, "z": 700, "n": 500}[kat]
    out, n = [], 101
    for y in YS:
        cevre = y in (0, 15000)
        if cevre and kat in ("b1", "b2"):
            continue
        b, h = (250, 600) if cevre else (300, ic_h)
        yc = (Y0 + b / 2) if y == 0 else (Y1 - b / 2) if y == 15000 else y
        for xa, xb in zip(XS[:-1], XS[1:]):
            out.append((f"K{n}", b, h, (xa + half(xa, y, kat), yc), (xb - half(xb, y, kat), yc))); n += 1
    for x in XS:
        cevre = x in (0, 24000)
        if cevre and kat in ("b1", "b2"):
            continue
        b, h = (250, 600) if cevre else (300, ic_h)
        xc = (X0 + b / 2) if x == 0 else (X1 - b / 2) if x == 24000 else x
        for ya, yb in zip(YS[:-1], YS[1:]):
            out.append((f"K{n}", b, h, (xc, ya + half(x, ya, kat)), (xc, yb - half(x, yb, kat)))); n += 1
    return out


def cevre_parcalari(kat):
    """Kolonlar arası dış duvar / perde dikdörtgenleri (dış yüz bina hattında, 25 cm)."""
    out = []
    for y in (0, 15000):
        y0 = Y0 if y == 0 else Y1 - 250
        for xa, xb in zip(XS[:-1], XS[1:]):
            out.append((xa + PER, y0, xb - PER, y0 + 250))
    for x in (0, 24000):
        x0 = X0 if x == 0 else X1 - 250
        for ya, yb in zip(YS[:-1], YS[1:]):
            out.append((x0, ya + PER, x0 + 250, yb - PER))
    return out


# ------------------------------------------------------------------ mimari: dört yönlü ayna
def _mx(r):
    x0, y0, x1, y1 = r
    return (24000 - x1, y0, 24000 - x0, y1)


def _my(r):
    x0, y0, x1, y1 = r
    return (x0, 15000 - y1, x1, 15000 - y0)


def _dort(r):
    return [r, _mx(r), _my(r), _my(_mx(r))]


def _pt4(p):
    x, y = p
    return [(x, y), (24000 - x, y), (x, 15000 - y), (24000 - x, 15000 - y)]


def walls(kat):
    """(katman, dikdörtgen, kapı boşlukları [(a, b)] duvar ekseni boyunca)."""
    w = []
    if kat in ("b1", "b2"):
        for r in cevre_parcalari(kat):
            w.append(("A-WALL-PERDE", r, []))
        return w
    op = openings(kat)
    for r in cevre_parcalari(kat):                       # dış duvar; kapı varsa kesik
        x0, y0, x1, y1 = r
        gaps = [(c - wd / 2, c + wd / 2) if yon == "x" else (cy - wd / 2, cy + wd / 2)
                for t, _n, wd, _h, (c, cy), yon, _tt in op
                if t == "K" and x0 - 1 <= c <= x1 + 1 and y0 - 1 <= cy <= y1 + 1]
        w.append(("A-WALL-YTONG-25", r, gaps))
    # koridor duvarları y 6400–6600 ve 8400–8600, dış duvar iç yüzünden iç yüzüne (sürekli)
    for y0 in (6400, 8400):
        gaps = [(c - wd / 2, c + wd / 2) for t, _n, wd, _h, (c, cy), yon, _tt in op
                if t == "K" and yon == "x" and y0 <= cy <= y0 + 200]
        w.append(("A-WALL-YTONG-20", (X0 + T_EXT, y0, X1 - T_EXT, y0 + 200), sorted(gaps)))
    # daire / dükkân arası x = 12000 (eksen), kolon yüzünden koridor duvarına
    for r in [(11900, 0 + PER, 12100, 5000 - 250), (11900, 5000 + 250, 12100, 6400)]:
        for rr in (r, _my(r)):
            w.append(("A-WALL-YTONG-20", rr, []))
    if kat == "z":
        return w
    # normal kat bölmeleri (10 tuğla), sol-alt daire tanımı, dört yöne aynalanır
    tek = [((5950, 0 + PER, 6050, 5000 - 250), []),                                   # salon | yatak (eksen)
           ((9450, 50, 9550, 4950), [(1000, 1800)]),                                  # yatak | banyo-mutfak
           ((9550, 2950, 11900, 3050), []),                                           # banyo | mutfak
           ((0 + PER, 4950, 6000 - 250, 5050), [(2000, 2900)]),                       # salon | hol (eksen)
           ((6000 + 250, 4950, 12000 - 250, 5050), [(7000, 7900), (10200, 11100)])]   # yatak, mutfak | hol (eksen)
    for r, gaps in tek:
        yatay = (r[2] - r[0]) >= (r[3] - r[1])
        for k, rr in enumerate(_dort(r)):
            gg = []
            for a, b in gaps:
                if yatay:
                    gg.append((24000 - b, 24000 - a) if k in (1, 3) else (a, b))
                else:
                    gg.append((15000 - b, 15000 - a) if k in (2, 3) else (a, b))
            w.append(("A-WALL-TUGLA-10", rr, sorted(gg)))
    return w


def openings(kat):
    """(tür, ad, genişlik, yükseklik, orta nokta, yön, duvar kalınlığı). Bloklar ortadan yerleşir."""
    ys, xw = Y0 + T_EXT / 2, X0 + T_EXT / 2
    o = []
    if kat in ("b1", "b2"):
        return o
    if kat == "z":
        for (x, y) in _pt4((3000, ys)) + _pt4((9000, ys)):
            o.append(("P", "V1", 3000, 2500, (x, y), "x", T_EXT))                          # vitrin
        for (x, y) in _pt4((xw, 2500)):
            o.append(("P", "V1", 3000, 2500, (x, y), "y", T_EXT))
        for (x, y) in _pt4((6000, 6500)):
            o.append(("K", "DK", 1000, 2100, (x, y), "x", 200))                              # dükkân kapısı
        o.append(("K", "BK", 1500, 2500, (xw, 7500), "y", T_EXT))                            # bina girişi
        o.append(("P", "P3", 1200, 1500, (X1 - T_EXT / 2, 7500), "y", T_EXT))                 # koridor ucu
        return o
    for (x, y) in _pt4((2400, ys)):
        o.append(("P", "P1", 1800, 1500, (x, y), "x", T_EXT))           # salon güney
    for (x, y) in _pt4((xw, 2400)):
        o.append(("P", "P1", 1800, 1500, (x, y), "y", T_EXT))           # salon batı
    for (x, y) in _pt4((7750, ys)):
        o.append(("P", "P2", 1500, 1500, (x, y), "x", T_EXT))           # yatak güney
    for (x, y) in _pt4((10700, ys)):
        o.append(("P", "P4", 600, 600, (x, y), "x", T_EXT))             # banyo
    for (x, y) in _pt4((6000 - 1500, 6500)):
        o.append(("K", "DK", 1000, 2100, (x, y), "x", 200))             # daire girişi (hol | koridor)
    for (x, y) in _pt4((2450, 5000)):
        o.append(("K", "K1", 900, 2100, (x, y), "x", 100))              # salon | hol
    for (x, y) in _pt4((7450, 5000)):
        o.append(("K", "K1", 900, 2100, (x, y), "x", 100))              # yatak | hol
    for (x, y) in _pt4((10650, 5000)):
        o.append(("K", "K1", 900, 2100, (x, y), "x", 100))              # mutfak | hol
    for (x, y) in _pt4((9500, 1400)):
        o.append(("K", "K2", 800, 2100, (x, y), "y", 100))              # yatak | banyo
    for x in (X0 + T_EXT / 2, X1 - T_EXT / 2):
        o.append(("P", "P3", 1200, 1500, (x, 7500), "y", T_EXT))        # koridor uçları
    return o


def rooms(kat):
    """(ad, dikdörtgen iç yüzlerle, bitirilir mi)."""
    kor = ("KORİDOR", (X0 + T_EXT, 6600, X1 - T_EXT, 8400), True)
    if kat in ("b1", "b2"):
        return [("OTOPARK", (X0 + T_EXT, Y0 + T_EXT, X1 - T_EXT, Y1 - T_EXT), False)]
    if kat == "z":
        out = [kor]
        for k, r in enumerate(_dort((X0 + T_EXT, Y0 + T_EXT, 11900, 6400)), 1):
            out.append((f"DÜKKAN {k}", r, False))
        return out
    out = [kor]
    tek = [("SALON", (50, 50, 5950, 4950)), ("YATAK ODASI", (6050, 50, 9450, 4950)), ("BANYO", (9550, 50, 11900, 2950)),
           ("MUTFAK", (9550, 3050, 11900, 4950)), ("HOL", (50, 5050, 11900, 6400))]
    for ad, r in tek:
        for rr in _dort(r):
            out.append((ad, rr, True))
    return out


def room_poly(r, kat, shafts=True):
    p = box(*r)
    for x, y, hw in cols(kat):
        p = p.difference(box(x - hw, y - hw, x + hw, y + hw))
    if shafts:
        for s in SHAFTS:
            p = p.difference(box(*s))
    return p


# ------------------------------------------------------------------ çizim
class _Pafta:
    def __init__(self, msp, scale, ofs):
        self.msp, self.k, self.ofs = msp, scale, ofs      # mm → çizim birimi, orijin kayması (mm)

    def p(self, x, y, ox=0.0):
        return ((x + ox + self.ofs[0]) * self.k, (y + self.ofs[1]) * self.k)

    def rect(self, r, layer, ox=0.0):
        x0, y0, x1, y1 = r
        self.msp.add_lwpolyline([self.p(x0, y0, ox), self.p(x1, y0, ox), self.p(x1, y1, ox), self.p(x0, y1, ox)],
                                close=True, dxfattribs={"layer": layer})

    def line(self, a, b, layer, ox=0.0):
        self.msp.add_line(self.p(*a, ox), self.p(*b, ox), dxfattribs={"layer": layer})

    def txt(self, s, x, y, h, layer, ox=0.0):
        self.msp.add_text(s, dxfattribs={"layer": layer, "height": h * self.k}).set_placement(self.p(x, y, ox))

    def sheet(self, i, title, layer):
        ox = i * SHEET_DX
        self.rect((-4000, -6000, 30000, 22000), layer, ox)
        self.txt(title, 0, -4500, 600, layer, ox)
        return ox


def _statik(path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5                  # cm
    for n in ("S-COLS", "S-BEAM", "S-SLAB", "S-SAFT", "S-WALL-PERDE", "S-FOOTING", "S-ANNO", "S-TTLB"):
        doc.layers.add(n)
    P = _Pafta(doc.modelspace(), 0.1, STATIK_OFS)
    ox = P.sheet(0, "TEMEL KALIP PLANI", "S-TTLB")
    P.rect((X0 - 600, Y0 - 600, X1 + 600, Y1 + 600), "S-FOOTING", ox)
    P.txt("R1 RADYE h=80", 10000, 7000, 300, "S-ANNO", ox)
    P.txt("RADYE ÜST KOTU -6.40", 2000, 16500, 300, "S-ANNO", ox)
    P.txt("RADYE ALT KOTU -7.20", 2000, 17200, 300, "S-ANNO", ox)
    P.txt("ALTINDA 10 cm GROBETON", 2000, 17900, 250, "S-ANNO", ox)
    plans = [("b2", "2. BODRUM KAT KALIP PLANI", "-3.20"), ("b1", "1. BODRUM KAT KALIP PLANI", "±0.00"),
             ("z", "ZEMİN KAT KALIP PLANI", "+4.00"), ("n", "1.-5. NORMAL KAT KALIP PLANI", "+7.00 / +10.00 / +13.00 / +16.00 / +19.00")]
    for i, (kat, title, kot) in enumerate(plans, 1):
        ox = P.sheet(i, title, "S-TTLB")
        for k, (x, y, hw) in enumerate(cols(kat), 1):
            P.rect((x - hw, y - hw, x + hw, y + hw), "S-COLS", ox)
            P.txt(f"S{k} {2 * hw // 10}/{2 * hw // 10}", x + hw + 50, y + hw + 50, 120, "S-ANNO", ox)
        for name, b, h, (xa, ya), (xb, yb) in beams(kat):
            if ya == yb:
                for yy in (ya - b / 2, ya + b / 2):
                    P.line((xa, yy), (xb, yy), "S-BEAM", ox)
                P.txt(f"{name} {b // 10}/{h // 10}", (xa + xb) / 2 - 600, ya + b / 2 + 80, 120, "S-ANNO", ox)
            else:
                for xx in (xa - b / 2, xa + b / 2):
                    P.line((xx, ya), (xx, yb), "S-BEAM", ox)
                P.txt(f"{name} {b // 10}/{h // 10}", xa + b / 2 + 80, (ya + yb) / 2, 120, "S-ANNO", ox)
        if kat in ("b1", "b2"):
            for j, r in enumerate(cevre_parcalari(kat), 1):
                P.rect(r, "S-WALL-PERDE", ox)
                L = max(r[2] - r[0], r[3] - r[1])
                P.txt(f"P{j} 25/{int(L) // 10}", (r[0] + r[2]) / 2 - 300, (r[1] + r[3]) / 2 + 200, 120, "S-ANNO", ox)
        P.rect((X0, Y0, X1, Y1), "S-SLAB", ox)
        for s in SHAFTS:
            P.rect(s, "S-SAFT", ox)
        for xa, xb in zip(XS[:-1], XS[1:]):
            for ya, yb in zip(YS[:-1], YS[1:]):
                P.txt("D h=15", (xa + xb) / 2 - 300, (ya + yb) / 2 - 700, 150, "S-ANNO", ox)
        P.txt(f"DÖŞEME ÜST KOTU {kot}", 2000, 16500, 300, "S-ANNO", ox)
    doc.saveas(path)


def _mimari(path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4                  # mm
    for n in ("A-ANNO", "A-TTLB", "S-COLS", "A-WALL-YTONG-25", "A-WALL-YTONG-20", "A-WALL-TUGLA-10", "A-WALL-PERDE",
              "A-DOOR", "A-GLAZ", "A-AREA-IDEN", "A-SHAFT", "A-SECT"):
        doc.layers.add(n)
    msp = doc.modelspace()
    win = doc.blocks.new("WIN")
    win.add_lwpolyline([(-500, -125), (500, -125), (500, 125), (-500, 125)], close=True)
    win.add_line((-500, -30), (500, -30))
    win.add_line((-500, 30), (500, 30))
    door = doc.blocks.new("DOOR")
    door.add_line((-500, 0), (-500, 1000))
    door.add_arc((-500, 0), 1000, 0, 90)
    P = _Pafta(msp, 1.0, (0.0, 0.0))
    plans = [("b2", "2. BODRUM KAT PLANI", "-6.40"), ("b1", "1. BODRUM KAT PLANI", "-3.20"),
             ("z", "ZEMİN KAT PLANI", "±0.00"), ("n", "1.-5. NORMAL KAT PLANI", "+4.00 / +7.00 / +10.00 / +13.00 / +16.00")]
    for i, (kat, title, kot) in enumerate(plans):
        ox = P.sheet(i, title, "A-TTLB")
        for x, y, hw in cols(kat):
            P.rect((x - hw, y - hw, x + hw, y + hw), "S-COLS", ox)
        for layer, (x0, y0, x1, y1), gaps in walls(kat):
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
        for t, ad, wd, h, (cx, cy), yon, tk in openings(kat):
            rot = 0 if yon == "x" else 90
            blk, lay = ("WIN", "A-GLAZ") if t == "P" else ("DOOR", "A-DOOR")
            ref = msp.add_blockref(blk, P.p(cx, cy, ox), dxfattribs={"layer": lay, "rotation": rot, "xscale": wd / 1000,
                                                                     "yscale": tk / 250 if t == "P" else wd / 1000})
            lx, ly = (cx - 300, cy + tk / 2 + 150) if yon == "x" else (cx + tk / 2 + 150, cy)
            P.txt(f"{ad} {wd // 10}/{h // 10}", lx, ly, 120, "A-ANNO", ox)
        for s in SHAFTS:
            if kat not in ("b1", "b2"):
                P.rect(s, "A-SHAFT", ox)
        for ad, r, _ in rooms(kat):
            pg = room_poly(r, kat, shafts=kat not in ("b1", "b2"))
            pt = pg.representative_point()
            P.txt(f"{ad} {pg.area / 1e6:.2f} m²".replace(".", ","), pt.x - 800, pt.y, 180, "A-AREA-IDEN", ox)
        P.txt(kot, 3000, 16500, 300, "A-ANNO", ox)
    ox = P.sheet(4, "A-A KESİTİ", "A-TTLB")
    for z in (-7200, -6400, -3200, 0, 4000, 7000, 10000, 13000, 16000, 19000):
        P.line((X0 - 600, z), (X1 + 600, z), "A-SECT", ox)
        P.txt(f"{z / 1000:+.2f}".replace("+0.00", "±0.00"), X1 + 1000, z, 250, "A-ANNO", ox)
    doc.saveas(path)


def make_golden_building3(folder: str | Path) -> tuple[Path, Path]:
    folder = Path(folder)
    s, m = folder / "STATIK PROJE.dxf", folder / "MIMARI PROJE.dxf"
    _statik(s)
    _mimari(m)
    return s, m


# ------------------------------------------------------------------ doğru metraj (elle)
def golden_truth3() -> dict:
    m = 1e-3
    t = {k: 0.0 for k in ("kolon", "kiris", "perde", "doseme", "ytong25", "ytong20", "tugla10", "siva", "tavan",
                          "kuru", "islak", "islak_cevre", "kapi", "pencere")}
    alan = (X1 - X0) * (Y1 - Y0) * m * m - sum((c - a) * (d - b) for a, b, c, d in SHAFTS) * m * m
    for kat, _ad, H, n, _taban in KATLAR:
        t["kolon"] += n * sum((2 * hw * m) ** 2 for _, _, hw in cols(kat)) * (H - D) * m
        bl = beams(kat)
        t["kiris"] += n * sum((abs(xb - xa) + abs(yb - ya)) * m * b * m * (h - D) * m for _, b, h, (xa, ya), (xb, yb) in bl)
        t["doseme"] += n * alan * D * m
        if kat in ("b1", "b2"):
            t["perde"] += sum(max(c - a, d - b) * m * 0.25 * (H - D) * m for a, b, c, d in cevre_parcalari(kat))
        ops = openings(kat)
        rects = [(box(xa, ya - b / 2, xb, yb + b / 2) if ya == yb else
                  box(xa - b / 2, ya, xa + b / 2, yb), h) for _, b, h, (xa, ya), (xb, yb) in bl]
        for layer, (x0, y0, x1, y1), _gaps in walls(kat):
            yatay = (x1 - x0) >= (y1 - y0)
            L = max(x1 - x0, y1 - y0) * m
            cl = LineString([(x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)]) if yatay else \
                LineString([((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)])
            kir = [h for g, h in rects if g.buffer(1).intersection(cl).length > 0]
            ortu = sum(g.buffer(1).intersection(cl).length for g, _h in rects)
            h_orgu = (H - max(kir)) * m if kir and ortu >= 0.5 * cl.length else (H - D) * m
            op = sum(wd * hh for _t, _a, wd, hh, (cx, cy), _y, _tt in ops
                     if x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1) * m * m
            key = {"A-WALL-YTONG-25": "ytong25", "A-WALL-YTONG-20": "ytong20", "A-WALL-TUGLA-10": "tugla10"}.get(layer)
            if key:
                t[key] += n * (L * h_orgu - op)
        # sıva: bitirilen mahallerin çevresi (kolon notları dahil) × tavana kadar − o mahale bakan boşluklar
        for ad, r, bitir in rooms(kat):
            if not bitir:
                continue
            pg = room_poly(r, kat, shafts=False)
            t["siva"] += n * pg.length * m * (H - D) * m
            ar = room_poly(r, kat).area * m * m
            t["tavan"] += n * ar
            if ad == "BANYO":
                t["islak"] += n * ar
                t["islak_cevre"] += n * pg.length * m
            else:
                t["kuru"] += n * ar
        for _t, _a, wd, hh, (cx, cy), yon, _tt in ops:
            yuz = 0
            for ad, r, bitir in rooms(kat):
                if bitir and box(*r).buffer(200).contains(box(cx - 1, cy - 1, cx + 1, cy + 1)):
                    yuz += 1
            t["siva"] -= n * yuz * wd * hh * m * m
        t["kapi"] += n * sum(1 for o in ops if o[0] == "K")
        t["pencere"] += n * sum(1 for o in ops if o[0] == "P")
    t["radye"] = (X1 - X0 + 1200) * (Y1 - Y0 + 1200) * m * m * 0.80
    t["grobeton"] = (X1 - X0 + 1200) * (Y1 - Y0 + 1200) * m * m * 0.10
    t["kat_sayisi"] = 8
    return t
