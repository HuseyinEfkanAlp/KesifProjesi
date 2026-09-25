"""Altın bina: ölçüleri bilinen 2 katlı konut (cm). Çizimi üretir ve doğru metrajı elle (formülle) hesaplar.

Keşfin uçtan uca doğruluk kapısıdır (tests/test_golden_building.py): kullanıcı gibi yüklenir, sonuç formülle
hesaplanmış doğru metrajla karşılaştırılır. Buradaki formüller programın kodunu KULLANMAZ — yoksa neyi
doğruladığımız belirsizleşir.

Taşıyıcı: 9 kolon 40x40 (x 0/580/1160, y 0/480/960 sol-alt köşe), kirişler 25/50 aks üstünde (kolon
ortası), döşeme h=15 tüm plan 1200x1000, radye h=60 50 cm taşmalı (1300x1100), radye üstü ±0.00.
Kat yüksekliği 3,00 (±0.00 / +3.00 / +6.00). Mimari: dış duvar gazbeton 20 (dış yüz bina hattında),
iç duvar tuğla 10 (aks üstünde), 4 mahal/kat. Doğramalar blok + etiket.
"""
from pathlib import Path

import ezdxf

SHEET_DX = 4000
COLS = [(x, y) for y in (0, 480, 960) for x in (0, 580, 1160)]
CW = 40
BW, BH, SLAB = 25, 50, 15
H = 300


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


_msp = None                 # make_golden_building doldurur


def txt(s, x, y, h=12, layer="YAZI"):
    _msp.add_text(s, dxfattribs={"layer": layer, "height": h}).set_placement((x, y))


def sheet(i, title, scale="1/50"):
    ox = i * SHEET_DX
    _msp.add_lwpolyline(rect(ox - 300, -500, 2000, 1900), close=True, dxfattribs={"layer": "ANTET"})
    txt(title, ox, -350, 40, "ANTET")
    txt(f"ÖLÇEK {scale}", ox, -420, 20, "ANTET")
    return ox


# ------------------------------------------------------------------ taşıyıcı
def kalip_plani(i, title, kot):
    ox = sheet(i, title)
    for k, (x, y) in enumerate(COLS, 1):
        _msp.add_lwpolyline(rect(ox + x, y, CW, CW), close=True, dxfattribs={"layer": "KOLON"})
        txt(f"S{k} 40/40", ox + x + 45, y + 45, 10)
    n = 101
    for y in (0, 480, 960):            # x yönü kirişleri (kolon ortası y+20)
        yc = y + 20
        for x0, x1 in ((40, 580), (620, 1160)):
            _msp.add_line((ox + x0, yc - BW / 2), (ox + x1, yc - BW / 2), dxfattribs={"layer": "KIRIS"})
            _msp.add_line((ox + x0, yc + BW / 2), (ox + x1, yc + BW / 2), dxfattribs={"layer": "KIRIS"})
            txt(f"K{n} 25/50", ox + (x0 + x1) / 2 - 40, yc + 20, 10); n += 1
    for x in (0, 580, 1160):           # y yönü
        xc = x + 20
        for y0, y1 in ((40, 480), (520, 960)):
            _msp.add_line((ox + xc - BW / 2, y0), (ox + xc - BW / 2, y1), dxfattribs={"layer": "KIRIS"})
            _msp.add_line((ox + xc + BW / 2, y0), (ox + xc + BW / 2, y1), dxfattribs={"layer": "KIRIS"})
            txt(f"K{n} 25/50", ox + xc + 20, (y0 + y1) / 2, 10); n += 1
    _msp.add_lwpolyline(rect(ox, 0, 1200, 1000), close=True, dxfattribs={"layer": "DOSEME"})
    for j, (x, y) in enumerate(((280, 230), (870, 230), (280, 720), (870, 720)), 1):
        txt(f"D{j} h=15", ox + x, y, 12)
    txt(f"DÖŞEME ÜST KOTU {kot}", ox + 300, 1100, 20, "KOT")


def temel_plani(i):
    ox = sheet(i, "TEMEL KALIP PLANI")
    _msp.add_lwpolyline(rect(ox - 50, -50, 1300, 1100), close=True, dxfattribs={"layer": "TEMEL"})
    txt("R1 RADYE h=60", ox + 500, 500, 15)
    txt("RADYE ÜST KOTU ±0.00", ox + 400, 1100, 20, "KOT")
    txt("RADYE ALT KOTU -0.60", ox + 400, 1150, 20, "KOT")
    txt("ALTINDA 10 cm GROBETON", ox + 400, 1200, 15)
    for x, y in COLS:
        _msp.add_lwpolyline(rect(ox + x, y, CW, CW), close=True, dxfattribs={"layer": "KOLON"})


# ------------------------------------------------------------------ mimari
# açıklıklar: (duvar, konum başlangıç, genişlik, yükseklik, tür, etiket)
EXT = "DUVAR GAZBETON 20"
INT = "DUVAR TUGLA 10"


def openings(kat):
    o = [
        ("S", 800, 150, 150, "P", "P1 150/150"),     # güney, mutfak
        ("N", 200, 150, 150, "P", "P1 150/150"),     # kuzey, yatak
        ("N", 800, 150, 150, "P", "P1 150/150"),
        ("W", 650, 150, 150, "P", "P1 150/150"),
        ("E", 200, 150, 150, "P", "P1 150/150"),
        ("E", 650, 150, 150, "P", "P1 150/150"),
        ("IY", 250, 90, 210, "K", "K1 90/210"),      # y=500 duvarı, sol
        ("IY", 850, 90, 210, "K", "K1 90/210"),      # y=500 duvarı, sağ
        ("IX", 200, 90, 210, "K", "K1 90/210"),      # x=600 duvarı, alt
    ]
    if kat == 0:
        o.append(("S", 250, 100, 210, "K", "K2 100/210"))   # giriş
    else:
        o.append(("S", 250, 150, 150, "P", "P1 150/150"))
    return o


# duvar parçaları kolonlar arası: (duvar, sabit koordinat aralığı, hat boyunca [a,b] aralıkları)
WALLS = {
    "S": (EXT, "x", (0, 20), [(40, 580), (620, 1160)]),
    "N": (EXT, "x", (980, 1000), [(40, 580), (620, 1160)]),
    "W": (EXT, "y", (0, 20), [(40, 480), (520, 960)]),
    "E": (EXT, "y", (1180, 1200), [(40, 480), (520, 960)]),
    "IY": (INT, "x", (495, 505), [(40, 580), (620, 1160)]),
    "IX": (INT, "y", (595, 605), [(40, 480), (520, 960)]),
}


def wall_lines(ox, kat):
    ops = openings(kat)
    for w, (layer, axis, (c0, c1), spans) in WALLS.items():
        cuts = sorted((a, a + wd) for ww, a, wd, *_ in ops if ww == w)
        for a, b in spans:
            pieces, cur = [], a
            for s, e in cuts:
                if a <= s < b:
                    pieces.append((cur, s)); cur = e
            pieces.append((cur, b))
            for p0, p1 in pieces:
                for c in (c0, c1):
                    if axis == "x":
                        _msp.add_line((ox + p0, c), (ox + p1, c), dxfattribs={"layer": layer})
                    else:
                        _msp.add_line((ox + c, p0), (ox + c, p1), dxfattribs={"layer": layer})
            # açıklık kenarlarında duvar kapanışı
            for s, e in cuts:
                if a <= s < b:
                    for v in (s, e):
                        if axis == "x":
                            _msp.add_line((ox + v, c0), (ox + v, c1), dxfattribs={"layer": layer})
                        else:
                            _msp.add_line((ox + c0, v), (ox + c1, v), dxfattribs={"layer": layer})
    for w, a, wd, hh, kind, lab in ops:
        layer, axis, (c0, c1), _ = WALLS[w]
        if axis == "x":
            ins, rot, lx, ly = (ox + a, c0), 0, ox + a, c1 + 25
        else:
            ins, rot, lx, ly = (ox + c1, a), 90, ox + c1 + 25, a
        if kind == "P":
            _msp.add_blockref("PENCERE", ins, dxfattribs={"layer": "PENCERE", "rotation": rot,
                                                        "xscale": wd / 100, "yscale": (c1 - c0) / 20})
        else:
            _msp.add_blockref("KAPI", ins, dxfattribs={"layer": "KAPI", "rotation": rot,
                                                     "xscale": wd / 100, "yscale": wd / 100})
        txt(lab, lx, ly, 10)


ROOMS = [  # ad, iç sınır (duvar yüzleri), etiket konumu
    ("SALON", (20, 20, 595, 495)),
    ("MUTFAK", (605, 20, 1180, 495)),
    ("YATAK ODASI", (20, 505, 595, 980)),
    ("BANYO", (605, 505, 1180, 980)),
]


def room_polygon(x0, y0, x1, y1):
    """Mahal iç sınırı: duvar yüzleri, içeri taşan kolonlar düşülmüş."""
    from shapely.geometry import box
    p = box(x0, y0, x1, y1)
    for cx, cy in COLS:
        p = p.difference(box(cx, cy, cx + CW, cy + CW))
    return p


def mimari_plan(i, title, kat, kot):
    ox = sheet(i, title)
    for x, y in COLS:
        _msp.add_lwpolyline(rect(ox + x, y, CW, CW), close=True, dxfattribs={"layer": "KOLON"})
        h = _msp.add_hatch(color=8, dxfattribs={"layer": "KOLON"})
        h.set_pattern_fill("ANSI31", scale=5)
        h.paths.add_polyline_path(rect(ox + x, y, CW, CW), is_closed=True)
    wall_lines(ox, kat)
    for name, bb in ROOMS:
        p = room_polygon(*bb)
        cx, cy = p.representative_point().x, p.representative_point().y
        txt(name, ox + cx - 60, cy + 20, 15, "MAHAL")
        txt(f"{p.area / 1e4:.2f} m²".replace(".", ","), ox + cx - 40, cy - 10, 12, "MAHAL")
    txt(kot, ox + 250, 150, 15, "KOT")
    txt("DIŞ DUVARLAR 20 cm GAZBETON, İÇ DUVARLAR 10 cm TUĞLA", ox, 1150, 15)


def kesit(i):
    ox = sheet(i, "A-A KESİTİ")
    for z in (-60, 0, 300, 600):
        _msp.add_line((ox - 50, z), (ox + 1250, z), dxfattribs={"layer": "KESIT"})
    for x in (0, 580, 1160):
        _msp.add_lwpolyline(rect(ox + x, 0, CW, 285), close=True, dxfattribs={"layer": "KESIT"})
        _msp.add_lwpolyline(rect(ox + x, 300, CW, 285), close=True, dxfattribs={"layer": "KESIT"})
    for z, lab in ((0, "±0.00"), (300, "+3.00"), (600, "+6.00"), (-60, "-0.60")):
        txt(lab, ox + 1300, z, 15, "KOT")
    txt("ZEMİN KAT", ox + 1400, 150, 15)
    txt("1. KAT", ox + 1400, 450, 15)


def make_golden_building(path: str | Path) -> Path:
    """Altın binanın çok paftalı DXF'i (temel, iki kalıp planı, iki mimari plan, kesit)."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for n in ("ANTET", "YAZI", "KOT", "KOLON", "KIRIS", "DOSEME", "TEMEL", "DUVAR GAZBETON 20", "DUVAR TUGLA 10",
              "KAPI", "PENCERE", "MAHAL", "KESIT", "OLCU"):
        doc.layers.add(n)
    global _msp
    _msp = doc.modelspace()

    kapi = doc.blocks.new("KAPI")          # birim kapı 100 cm, ölçeklenir
    kapi.add_line((0, 0), (100, 0))
    kapi.add_line((0, 0), (0, 100))
    kapi.add_arc((0, 0), 100, 0, 90)
    pen = doc.blocks.new("PENCERE")        # birim 100 cm, duvar kalınlığı 20
    pen.add_lwpolyline([(0, 0), (100, 0), (100, 20), (0, 20)], close=True)
    pen.add_line((0, 7), (100, 7))
    pen.add_line((0, 13), (100, 13))

    temel_plani(0)
    kalip_plani(1, "ZEMİN KAT KALIP PLANI", "+3.00")
    kalip_plani(2, "1. KAT KALIP PLANI", "+6.00")
    mimari_plan(3, "ZEMİN KAT PLANI", 0, "±0.00")
    mimari_plan(4, "1. KAT PLANI", 1, "+3.00")
    kesit(5)
    path = Path(path)
    doc.saveas(path)
    return path


def golden_truth() -> dict:
    """Doğru metraj, elle (formülle). Kurallar Türkiye metraj alışkanlığıdır:
      - kolon betonu döşeme altına (H − d); kiriş yüzden yüze, döşeme altı gövde; döşeme tam alan
      - duvar örgüsü kolonlar arası net boy × kiriş altı yükseklik (H − kiriş), boşluklar düşülür
      - iç sıva / boya mahal çevresi × tavana kadar (H − d), odaya taşan kolon yüzleri dahil; boşluk iç kapıda
        iki yüz, dış doğramada bir yüz düşülür
      - tavan = mahal alanları; şap tüm mahaller; kaplama kuru mahaller; ıslak hacim ayrı (seramik)
      - geri dolgu = kazı − temel betonu − grobeton"""
    from shapely.geometry import box
    m = 0.01
    beams_len = (6 * 540 + 6 * 440) * m                       # kolon yüzünden yüze
    ext_len = sum(b - a for w in "SNWE" for a, b in WALLS[w][3]) * m
    int_len = sum(b - a for w in ("IY", "IX") for a, b in WALLS[w][3]) * m
    orgu_h, yuzey_h = (H - BH) * m, (H - SLAB) * m
    t = {"kolon_beton": 0.0, "kiris_beton": 0.0, "doseme_beton": 0.0, "gazbeton": 0.0, "tugla": 0.0,
         "kapi": 0, "pencere": 0, "siva": 0.0, "tavan": 0.0, "kuru_mahal": 0.0, "islak_mahal": 0.0,
         "islak_cevre": 0.0}
    for kat in (0, 1):
        ops = openings(kat)
        ext_op = sum(wd * hh for w, a, wd, hh, *_ in ops if w in "SNWE") * m * m
        int_op = sum(wd * hh for w, a, wd, hh, *_ in ops if w in ("IY", "IX")) * m * m
        t["kolon_beton"] += len(COLS) * (CW * m) ** 2 * (H - SLAB) * m
        t["kiris_beton"] += beams_len * BW * m * (BH - SLAB) * m
        t["doseme_beton"] += 12 * 10 * SLAB * m
        t["gazbeton"] += ext_len * orgu_h - ext_op
        t["tugla"] += int_len * orgu_h - int_op
        t["kapi"] += sum(1 for o in ops if o[4] == "K")
        t["pencere"] += sum(1 for o in ops if o[4] == "P")
        # sıva: mahal çevresi × tavana kadar (odaya taşan kolon yüzleri dahil) − boşluk (iç kapı iki yüz, dış bir yüz)
        cevre = sum(room_polygon(*bb).length for _n, bb in ROOMS) * m
        t["siva"] += cevre * yuzey_h - ext_op - 2 * int_op
        for name, bb in ROOMS:
            a = box(*bb).area * m * m                          # mahal: duvar yüzleri arası
            t["tavan"] += a
            if name == "BANYO":
                t["islak_mahal"] += a
                x0, y0, x1, y1 = bb
                t["islak_cevre"] += 2 * ((x1 - x0) + (y1 - y0)) * m
            else:
                t["kuru_mahal"] += a
    t["radye_beton"] = 13 * 11 * 0.60
    t["grobeton"] = 13 * 11 * 0.10
    return t
