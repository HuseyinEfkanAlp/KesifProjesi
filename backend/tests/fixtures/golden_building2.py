"""Altın bina 2: ilkinden BİLEREK farklı çizim alışkanlıklarıyla, ölçüsü bilinen 4 katlı apartman (mm).

İlk altın binanın (golden_building.py) sınamadığı alışkanlıklar:
  - birim mm ($INSUNITS=4), İngilizce katman adları (A-WALL-*, S-COLS, S-BEAM, S-SLAB, S-SAFT, A-GLAZ)
  - bodrum + zemin + TİP KAT planı (1.-2. NORMAL KAT: bir pafta iki kat) + düz çatı
  - bodrumda çevre betonarme perde (kalıp planında S-WALL-PERDE, mimaride A-WALL-PERDE)
  - farklı kesitler: çevre kolon 40/40, iç kolon 50/50; çevre kirişi 25/60 (dış yüzle aynı hizada), iç kiriş 30/50
  - döşemede iki şaft boşluğu (1 x 1 m)
  - her katta iki ayna daire: aynı adlı, aynı alanlı odalar
  - pencerede duvar KESİLMEZ (pencere bloğu sürekli duvarın üstünde); kapıda duvar kesilir
  - doğrama blokları ORTASINDAN yerleştirilir (ilk binada köşeden)
  - mahal etiketi tek yazı: "SALON 21,82 m²"
  - kolon aksında olmayan duvar (daireler arası, mutfak–banyo) döşeme altına kadar örülür

Eksenler: x 0 / 5000 / 10000 / 15000, y 0 / 4500 / 9000. Kolon merkezleri eksen kesişimlerinde.
Kat yükseklikleri: bodrum 3,20 (−3,20 → ±0,00), zemin ve normal katlar 3,00; çatı döşemesi +9,00.
Döşeme 15 cm, radye 70 cm (−3,20 üstü, −3,90 altı), altında 10 cm grobeton, radye bina hattından 60 cm taşar.
"""
from pathlib import Path

import ezdxf

XS = (0, 5000, 10000, 15000)
YS = (0, 4500, 9000)
H_BODRUM, H_KAT, D = 3200, 3000, 150
PER, INT = 200, 250                      # kolon yarı genişlikleri: çevre 40/40, iç 50/50
X0, X1, Y0, Y1 = -PER, 15000 + PER, -PER, 9000 + PER        # bina dış hattı
T_EXT, T_PARTY, T_INT = 250, 200, 100    # dış duvar 25 gazbeton, daire arası 20 gazbeton, bölme 10 tuğla
SHAFTS = [(5500, 7000, 6500, 8000), (8500, 7000, 9500, 8000)]
SHEET_DX = 40000
_msp = None


def _half(x, y):
    return INT if (x in (5000, 10000) and y == 4500) else PER


COLS = [(x, y, _half(x, y)) for y in YS for x in XS]


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def txt(s, x, y, h=150, layer="A-ANNO"):
    _msp.add_text(s, dxfattribs={"layer": layer, "height": h}).set_placement((x, y))


def sheet(i, title):
    ox = i * SHEET_DX
    _msp.add_lwpolyline(rect(ox - 3000, -4000, ox + 27000, 17000), close=True, dxfattribs={"layer": "A-ANNO-TTLB"})
    txt(title, ox, -3000, 500, "A-ANNO-TTLB")
    txt("ÖLÇEK 1/50", ox, -3700, 250, "A-ANNO-TTLB")
    return ox


# ------------------------------------------------------------------ taşıyıcı
def beams(bodrum: bool):
    """(ad, b, h, merkez hattı) — kolon yüzünden yüze. Çevre kirişi dış yüzle aynı hizada (kolon dış yüzü)."""
    out, n = [], 101
    for y in YS:
        cevre = y in (0, 9000)
        if cevre and bodrum:
            continue                     # bodrumda çevrede perde var, kiriş yok
        b, h = (250, 600) if cevre else (300, 500)
        yc = (Y0 + b / 2) if y == 0 else (Y1 - b / 2) if y == 9000 else y
        for xa, xb in zip(XS[:-1], XS[1:]):
            out.append((f"K{n}", b, h, (xa + _half(xa, y), yc), (xb - _half(xb, y), yc))); n += 1
    for x in XS:
        cevre = x in (0, 15000)
        if cevre and bodrum:
            continue
        b, h = (250, 600) if cevre else (300, 500)
        xc = (X0 + b / 2) if x == 0 else (X1 - b / 2) if x == 15000 else x
        for ya, yb in zip(YS[:-1], YS[1:]):
            out.append((f"K{n}", b, h, (xc, ya + _half(x, ya)), (xc, yb - _half(x, yb)))); n += 1
    return out


def perdes():
    """Bodrum çevre perdesi 25 cm, dış yüz bina hattında, kolonlar arası."""
    out = []
    for y in (0, 9000):
        y0 = Y0 if y == 0 else Y1 - 250
        for xa, xb in zip(XS[:-1], XS[1:]):
            out.append((xa + PER, y0, xb - PER, y0 + 250))
    for x in (0, 15000):
        x0 = X0 if x == 0 else X1 - 250
        for ya, yb in zip(YS[:-1], YS[1:]):
            out.append((x0, ya + PER, x0 + 250, yb - PER))
    return out


def kalip_plani(i, title, kot, bodrum):
    ox = sheet(i, title)
    for k, (x, y, hw) in enumerate(COLS, 1):
        _msp.add_lwpolyline(rect(ox + x - hw, y - hw, ox + x + hw, y + hw), close=True, dxfattribs={"layer": "S-COLS"})
        txt(f"S{k} {2 * hw // 10}/{2 * hw // 10}", ox + x + hw + 50, y + hw + 50, 120, "S-ANNO")
    for name, b, h, (xa, ya), (xb, yb) in beams(bodrum):
        if ya == yb:
            for yy in (ya - b / 2, ya + b / 2):
                _msp.add_line((ox + xa, yy), (ox + xb, yy), dxfattribs={"layer": "S-BEAM"})
            txt(f"{name} {b // 10}/{h // 10}", ox + (xa + xb) / 2 - 500, ya + b / 2 + 80, 120, "S-ANNO")
        else:
            for xx in (xa - b / 2, xa + b / 2):
                _msp.add_line((ox + xx, ya), (ox + xx, yb), dxfattribs={"layer": "S-BEAM"})
            txt(f"{name} {b // 10}/{h // 10}", ox + xa + b / 2 + 80, (ya + yb) / 2, 120, "S-ANNO")
    if bodrum:
        for j, (a, b_, c, d) in enumerate(perdes(), 1):
            _msp.add_lwpolyline(rect(ox + a, b_, ox + c, d), close=True, dxfattribs={"layer": "S-WALL-PERDE"})
            L = max(c - a, d - b_)
            txt(f"P{j} 25/{L // 10}", ox + (a + c) / 2 - 300, (b_ + d) / 2 + 200, 120, "S-ANNO")
    _msp.add_lwpolyline(rect(ox + X0, Y0, ox + X1, Y1), close=True, dxfattribs={"layer": "S-SLAB"})
    for (a, b_, c, d) in SHAFTS:
        _msp.add_lwpolyline(rect(ox + a, b_, ox + c, d), close=True, dxfattribs={"layer": "S-SAFT"})
        txt("ŞAFT", ox + a + 100, b_ + 400, 120, "S-ANNO")
    for xa, xb in zip(XS[:-1], XS[1:]):
        for ya, yb in zip(YS[:-1], YS[1:]):
            txt("D h=15", ox + (xa + xb) / 2 - 300, (ya + yb) / 2 - 600, 150, "S-ANNO")
    txt(f"DÖŞEME ÜST KOTU {kot}", ox + 2000, 10500, 250, "S-ANNO")


def temel_plani(i):
    ox = sheet(i, "TEMEL KALIP PLANI")
    _msp.add_lwpolyline(rect(ox + X0 - 600, Y0 - 600, ox + X1 + 600, Y1 + 600), close=True, dxfattribs={"layer": "S-FOOTING"})
    txt("R1 RADYE h=70", ox + 6000, 4000, 250, "S-ANNO")
    txt("RADYE ÜST KOTU -3.20", ox + 2000, 10500, 250, "S-ANNO")
    txt("RADYE ALT KOTU -3.90", ox + 2000, 11000, 250, "S-ANNO")
    txt("ALTINDA 10 cm GROBETON", ox + 2000, 11500, 200, "S-ANNO")


# ------------------------------------------------------------------ mimari
# Duvar: (katman, x0, y0, x1, y1, kapı boşlukları [(a, b)] duvar ekseni boyunca, eksende kiriş var mı)
def walls(bodrum: bool):
    w = []
    ext = "A-WALL-PERDE" if bodrum else "A-WALL-YTONG-25"
    kapilar = [] if bodrum else [o for o in openings(False) if o[1] == "DK"]
    # dış duvarlar kolonlar arası, dış yüz bina hattında (bodrumda perde); daire giriş kapısında kesik
    for (a, b_, c, d) in perdes():
        gaps = [(cx - wd / 2, cx + wd / 2) for _t, _n, wd, _h, (cx, cy), _y, _tt in kapilar
                if a <= cx <= c and b_ <= cy <= d]
        w.append((ext, a, b_, c, d, gaps, True))
    # daireler arası 20 gazbeton, x = 7500 (eksen değil: döşeme altına kadar), dış duvarın iç yüzünden
    if bodrum:
        w.append(("A-WALL-YTONG-20", 7400, Y0 + T_EXT, 7600, Y1 - T_EXT, [(1500, 2400)], False))
        return w
    # daire arası duvar kesişimden geçerek süreklidir (kalın duvar), 10'luk bölmeler ona dayanır
    w.append(("A-WALL-YTONG-20", 7400, Y0 + T_EXT, 7600, Y1 - T_EXT, [], False))
    # iç bölmeler 10 tuğla
    for x in (5000, 10000):                                   # eksen duvarları (iç kiriş altında), kolon yüzünden
        w.append(("A-WALL-TUGLA-10", x - 50, 0 + PER, x + 50, 4500 - INT, [(1000, 1900)], True))
        w.append(("A-WALL-TUGLA-10", x - 50, 4500 + INT, x + 50, 9000 - PER, [(6000, 6900)], True))
    for xa, xb in ((0 + PER, 5000 - INT), (10000 + INT, 15000 - PER)):   # y = 4500 ekseni, salon–yatak
        dx = (2000, 2900) if xa < 7500 else (12100, 13000)
        w.append(("A-WALL-TUGLA-10", xa, 4450, xb, 4550, [dx], True))
    for xa, xb, kapi in ((5000 + INT, 7400, (6000, 6800)), (7600, 10000 - INT, (8200, 9000))):  # y=4500, banyo–hol
        w.append(("A-WALL-TUGLA-10", xa, 4450, xb, 4550, [kapi], True))
    for xa, xb in ((5000 + 50, 7400), (7600, 10000 - 50)):   # y = 2500, mutfak–banyo (eksen değil)
        w.append(("A-WALL-TUGLA-10", xa, 2450, xb, 2550, [], False))
    return w


def openings(bodrum: bool):
    """(tür, ad, genişlik, yükseklik, duvar merkez hattı üstündeki orta nokta, yön 'x'|'y', duvar kalınlığı)."""
    if bodrum:
        return [("K", "K1", 900, 2100, (7500, 1950), "y", T_PARTY)]
    o = []
    for m in (False, True):                                   # iki ayna daire
        X = (lambda x: 15000 - x) if m else (lambda x: x)
        ys = Y0 + T_EXT / 2
        yn = Y1 - T_EXT / 2
        xw = (X1 - T_EXT / 2) if m else (X0 + T_EXT / 2)
        o += [("P", "P1", 1500, 1400, (X(2250), ys), "x", T_EXT),        # salon güney
              ("P", "P1", 1500, 1400, (xw, 2250), "y", T_EXT),           # salon batı
              ("P", "P1", 1500, 1400, (X(2250), yn), "x", T_EXT),        # yatak kuzey
              ("P", "P3", 1000, 1400, (X(6250), ys), "x", T_EXT),        # mutfak güney
              ("K", "DK", 1000, 2100, (X(6300), yn), "x", T_EXT),        # daire girişi, hol kuzey (duvar kesik)
              ("K", "K1", 900, 2100, (X(5000), 1450), "y", T_INT),       # salon–mutfak
              ("K", "K1", 900, 2100, (X(5000), 6450), "y", T_INT),       # hol–yatak
              ("K", "K1", 900, 2100, (X(2450), 4500), "x", T_INT),       # salon–yatak
              ("K", "K2", 800, 2100, (X(6400), 4500), "x", T_INT)]       # hol–banyo
    return o


ROOMS = [  # ad, (x0, y0, x1, y1) iç yüzler (sol daire); sağ daire aynası
    ("SALON", (X0 + T_EXT, Y0 + T_EXT, 5000 - 50, 4450)),
    ("YATAK ODASI", (X0 + T_EXT, 4550, 5000 - 50, Y1 - T_EXT)),
    ("MUTFAK", (5000 + 50, Y0 + T_EXT, 7400, 2450)),
    ("BANYO", (5000 + 50, 2550, 7400, 4450)),
    ("HOL", (5000 + 50, 4550, 7400, Y1 - T_EXT)),
]
BODRUM_ROOMS = [("DEPO", (X0 + T_EXT, Y0 + T_EXT, 7400, Y1 - T_EXT)),
                ("KAZAN DAİRESİ", (7600, Y0 + T_EXT, X1 - T_EXT, Y1 - T_EXT))]


def _mirror(bb):
    x0, y0, x1, y1 = bb
    return (15000 - x1, y0, 15000 - x0, y1)


def room_list(bodrum: bool):
    if bodrum:
        return BODRUM_ROOMS
    return ROOMS + [(n, _mirror(bb)) for n, bb in ROOMS]


def room_polygon(bb):
    """Mahal: duvar iç yüzleri arası, içeri taşan kolonlar düşülmüş."""
    from shapely.geometry import box
    p = box(*bb)
    for x, y, hw in COLS:
        p = p.difference(box(x - hw, y - hw, x + hw, y + hw))
    for (a, b_, c, d) in SHAFTS:
        p = p.difference(box(a, b_, c, d))
    return p


def mimari_plan(i, title, kot, bodrum):
    ox = sheet(i, title)
    for x, y, hw in COLS:
        _msp.add_lwpolyline(rect(ox + x - hw, y - hw, ox + x + hw, y + hw), close=True, dxfattribs={"layer": "S-COLS"})
        h = _msp.add_hatch(dxfattribs={"layer": "S-COLS"})
        h.set_pattern_fill("ANSI31", scale=50)
        h.paths.add_polyline_path(rect(ox + x - hw, y - hw, ox + x + hw, y + hw), is_closed=True)
    for layer, x0, y0, x1, y1, kapilar, _aks in walls(bodrum):
        yatay = (x1 - x0) >= (y1 - y0)
        a0, a1 = (x0, x1) if yatay else (y0, y1)
        c0, c1 = (y0, y1) if yatay else (x0, x1)
        parcalar, cur = [], a0
        for s, e in sorted(kapilar):
            parcalar.append((cur, s)); cur = e
        parcalar.append((cur, a1))
        for p0, p1 in parcalar:
            for c in (c0, c1):
                pts = ((p0, c), (p1, c)) if yatay else ((c, p0), (c, p1))
                _msp.add_line((ox + pts[0][0], pts[0][1]), (ox + pts[1][0], pts[1][1]), dxfattribs={"layer": layer})
            for v in (p0, p1):          # uç kapanışı
                pts = ((v, c0), (v, c1)) if yatay else ((c0, v), (c1, v))
                _msp.add_line((ox + pts[0][0], pts[0][1]), (ox + pts[1][0], pts[1][1]), dxfattribs={"layer": layer})
    for tur, ad, w, h, (cx, cy), yon, t in openings(bodrum):
        rot = 0 if yon == "x" else 90
        blk = "WIN" if tur == "P" else "DOOR"
        _msp.add_blockref(blk, (ox + cx, cy), dxfattribs={"layer": "A-GLAZ" if tur == "P" else "A-DOOR", "rotation": rot,
                                                           "xscale": w / 1000, "yscale": t / 250 if tur == "P" else w / 1000})
        lx, ly = (ox + cx - 300, cy + t / 2 + 150) if yon == "x" else (ox + cx + t / 2 + 150, cy)
        txt(f"{ad} {w // 10}/{h // 10}", lx, ly, 120, "A-ANNO")
    for (a, b_, c, d) in SHAFTS:
        _msp.add_lwpolyline(rect(ox + a, b_, ox + c, d), close=True, dxfattribs={"layer": "A-SHAFT"})
    for name, bb in room_list(bodrum):
        p = room_polygon(bb)
        pt = p.representative_point()
        txt(f"{name} {p.area / 1e6:.2f} m²".replace(".", ","), ox + pt.x - 800, pt.y, 180, "A-AREA-IDEN")
    txt(kot, ox + 3000, 10500, 250, "A-ANNO")


def kesit(i):
    ox = sheet(i, "A-A KESİTİ")
    for z in (-3900, -3200, 0, 3000, 6000, 9000):
        _msp.add_line((ox + X0 - 600, z), (ox + X1 + 600, z), dxfattribs={"layer": "A-SECT"})
    for z, lab in ((-3900, "-3.90"), (-3200, "-3.20"), (0, "±0.00"), (3000, "+3.00"), (6000, "+6.00"), (9000, "+9.00")):
        txt(lab, ox + X1 + 1000, z, 200, "A-ANNO")


def make_golden_building2(path: str | Path) -> Path:
    global _msp
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for n in ("A-ANNO", "A-ANNO-TTLB", "S-ANNO", "S-COLS", "S-BEAM", "S-SLAB", "S-SAFT", "S-WALL-PERDE", "S-FOOTING",
              "A-WALL-YTONG-25", "A-WALL-YTONG-20", "A-WALL-TUGLA-10", "A-WALL-PERDE", "A-DOOR", "A-GLAZ",
              "A-AREA-IDEN", "A-SHAFT", "A-SECT"):
        doc.layers.add(n)
    _msp = doc.modelspace()
    win = doc.blocks.new("WIN")             # 1000 mm pencere, 250 mm duvar; ORTADAN yerleşir
    win.add_lwpolyline(rect(-500, -125, 500, 125), close=True)
    win.add_line((-500, -30), (500, -30))
    win.add_line((-500, 30), (500, 30))
    door = doc.blocks.new("DOOR")           # 1000 mm kapı, ORTADAN yerleşir (kanat + açılım yayı)
    door.add_line((-500, 0), (-500, 1000))
    door.add_arc((-500, 0), 1000, 0, 90)

    temel_plani(0)
    kalip_plani(1, "BODRUM KAT KALIP PLANI", "±0.00", True)
    kalip_plani(2, "ZEMİN KAT KALIP PLANI", "+3.00", False)
    kalip_plani(3, "1.-2. NORMAL KAT KALIP PLANI", "+6.00 / +9.00", False)
    mimari_plan(4, "BODRUM KAT PLANI", "-3.20", True)
    mimari_plan(5, "ZEMİN KAT PLANI", "±0.00", False)
    mimari_plan(6, "1.-2. NORMAL KAT PLANI", "+3.00 / +6.00", False)
    kesit(7)
    path = Path(path)
    doc.saveas(path)
    return path


def golden_truth2() -> dict:
    """Doğru metraj, elle. Kurallar altın bina 1 ile aynı (golden_building.golden_truth)."""
    m = 1e-3
    kat = [("bodrum", H_BODRUM, 1, True), ("zemin", H_KAT, 1, False), ("normal", H_KAT, 2, False)]
    t = {k: 0.0 for k in ("kolon", "kiris", "perde", "doseme", "ytong25", "ytong20", "tugla10", "siva",
                          "tavan", "kuru", "islak", "sap_alan", "islak_cevre")}
    t.update(kapi=0, pencere=0, siva_cevre=0.0, siva_bosluk=0.0)
    alan = (X1 - X0) * (Y1 - Y0) * m * m - sum((c - a) * (d - b) for a, b, c, d in SHAFTS) * m * m
    for ad, H, n, bodrum in kat:
        t["kolon"] += n * sum((2 * hw * m) ** 2 for _, _, hw in COLS) * (H - D) * m
        t["kiris"] += n * sum((abs(xb - xa) + abs(yb - ya)) * m * b * m * (h - D) * m for _, b, h, (xa, ya), (xb, yb) in beams(bodrum))
        t["doseme"] += n * alan * D * m
        if bodrum:
            t["perde"] += sum(max(c - a, d - b) * m * 0.25 * (H - D) * m for a, b, c, d in perdes())
        ops = openings(bodrum)
        for layer, x0, y0, x1, y1, kapilar, aks in walls(bodrum):
            L = max(x1 - x0, y1 - y0) * m
            if aks:
                ext = x0 in (X0,) or x1 == X1 or y0 == Y0 or y1 == Y1
                kiris_h = (600 if ext else 500)
                h_orgu = (H - kiris_h) * m if not bodrum or not ext else (H - D) * m
            else:
                h_orgu = (H - D) * m
            h_yuzey = (H - D) * m
            # bu duvarın üstündeki boşluklar (orta noktası duvar dikdörtgeninde)
            mine = [(w, hh) for _t, _a, w, hh, (cx, cy), _y, _tt in ops if x0 - 1 <= cx <= x1 + 1 and y0 - 1 <= cy <= y1 + 1]
            op = sum(w * hh for w, hh in mine) * m * m
            # kesik kapı boşluğu dahil brüt boy × yükseklik − boşluk (lento üstü duvar sayılır)
            orgu = L * h_orgu - op
            key = {"A-WALL-YTONG-25": "ytong25", "A-WALL-YTONG-20": "ytong20", "A-WALL-TUGLA-10": "tugla10"}.get(layer)
            if key:
                t[key] += n * orgu
            yuz = 1 if (layer in ("A-WALL-YTONG-25", "A-WALL-PERDE")) else 2
            t["siva_bosluk"] += n * yuz * op
        from shapely.geometry import box as _box
        for name, bb in room_list(bodrum):
            # sıva: mahal çevresi (kolon notları dahil, şaft sıvanmaz) × tavana kadar
            kutu = _box(*bb)
            for x, y, hw in COLS:
                kutu = kutu.difference(_box(x - hw, y - hw, x + hw, y + hw))
            t["siva_cevre"] += n * kutu.length * m * (H - D) * m
            a = room_polygon(bb).area * m * m
            t["tavan"] += n * a
            t["sap_alan"] += n * a
            if name == "BANYO":
                t["islak"] += n * a
                t["islak_cevre"] += n * room_polygon(bb).length * m
            else:
                t["kuru"] += n * a
        t["kapi"] += n * sum(1 for o in ops if o[0] == "K")
        t["pencere"] += n * sum(1 for o in ops if o[0] == "P")
    t["siva"] = t["siva_cevre"] - t["siva_bosluk"]
    t["radye"] = (X1 - X0 + 1200) * (Y1 - Y0 + 1200) * m * m * 0.70
    t["grobeton"] = (X1 - X0 + 1200) * (Y1 - Y0 + 1200) * m * m * 0.10
    t["kat_sayisi"] = 4
    return t
