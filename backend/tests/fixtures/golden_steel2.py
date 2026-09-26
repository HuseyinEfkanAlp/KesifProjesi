"""Altın çelik 2: tek / çift çizgiyle çizilmiş elemanlar ve EĞİMLİ çatı (cm çizim, tek dosya, iki pafta).

Beşik çatı 12 × 8 m: saçak y = 0 ve y = 800 (+4.00), mahya y = 400 (+6.00); kolonlar köşelerde (±0.00'dan).
Sınadığı:
  - IPE200 saçak kirişi ÇİFT ÇİZGİ (iki paralel çizgi, 10 cm arayla; kapalı dikdörtgen değil)
  - 80x40x3 aşık TEK ÇİZGİ, markası çizgiye paralel ve üstünde (kılavuzsuz); bir aşık markasız (katmandaki öteki
    aşıklar gibi kabul, tahmin)
  - HEA160 makas dikdörtgen, iki ucunda kot yazısı (+4.00 / +6.00) → gerçek boy √(4² + 2²)
  - Ø48.3x3 çapraz TEK ÇİZGİ, çatı düzleminde köşegen; iki ucunda kot yazısı → gerçek boy √(4² + 4² + 2²) = 6
  - kot=False, egim_yazisi=True: kot yazısı yok, yalnız eğim oku yazısı "%50" (eğim doğrultusunda, y): makas tam,
    köşegen çapraz eğim doğrultusundaki bileşeni kadar uzar, aşık / saçak / mahya uzamaz
  - tuzaklar: mahya kirişi dikdörtgen + aynı katmanda iki kenar çizgisi ve eksen çizgisi (ikinci kez sayılmaz);
    gizli (kesikli) katmanda çizgi; markasız kısa yardımcı çizgi
  - kot=False, egim_yazisi=False: aynı çatı kot / eğim yazısız → izdüşümden, kullanıcıya sorulur
kg/m bağımsız yazılır (EN 10365 anma; boru / kutu kesitten, 7850 kg/m³).
"""
import math
from pathlib import Path

import ezdxf

SHEET_DX = 3000
XS = (0, 1200)
KOT_SACAK, KOT_MAHYA = 4.00, 6.00
H_KOLON = (KOT_SACAK + KOT_MAHYA) / 2          # eğimli çatı: kolon üst kotu iki kotun ortalaması (tahmin)
KG = {"HEB160": 42.6, "IPE200": 22.4, "HEA160": 30.4,
      "80x40x3": (2 * 3 * (80 + 40) - 4 * 3 * 3) * 7850e-6,
      "Ø48.3x3": math.pi * (48.3 - 3) * 3 * 7850e-6}
ASIK_Y = (100, 200, 300, 500, 600, 700)
ASIK_MARKASIZ = 700
MAKAS_X = (0, 400, 800, 1200)
CAPRAZ = [((0, 0), (400, 400)), ((400, 0), (0, 400)), ((800, 400), (1200, 800)), ((1200, 400), (800, 800))]

_msp = None


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def txt(s, x, y, h=10, layer="C-Marka-Yazi", rot=0.0):
    t = _msp.add_text(s, dxfattribs={"layer": layer, "height": h, "rotation": rot})
    t.set_placement((x, y))


def line(ox, a, b, layer):
    _msp.add_line((ox + a[0], a[1]), (ox + b[0], b[1]), dxfattribs={"layer": layer})


def sheet(i, title):
    ox = i * SHEET_DX
    _msp.add_lwpolyline(rect(ox - 300, -400, 1900, 1500), close=True, dxfattribs={"layer": "ANTET"})
    txt(title, ox, -300, 40, "G-Detay-Tanim")
    return ox


def kolonlar(ox):
    for x in XS:
        for y in (0, 800):
            _msp.add_lwpolyline(rect(ox + x - 8, y - 8, 16, 16), close=True, dxfattribs={"layer": "G-Kolon"})
            tx, ty = ox + x + 50, y + (-60 if y == 0 else 60)
            _msp.add_line((ox + x + 8, y - 8 if y == 0 else y + 8), (tx, ty), dxfattribs={"layer": "C-Marka-Cizgi"})
            txt("Kolon-HEB160", tx, ty)


def make_golden_steel2(path: str | Path, kot: bool = True, egim_yazisi: bool = False) -> Path:
    global _msp
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    _msp = doc.modelspace()
    ox = sheet(0, "±0.00 KOTU ÇELİK KOLON YERLEŞİM PLANI")
    kolonlar(ox)
    ox = sheet(1, "+4.00/+6.00 ARASI ÇELİK ÇATI PLANI")
    kolonlar(ox)
    # saçak kirişleri: çift çizgi, 10 cm arayla, kılavuzsuz marka üstünde
    for y in (0, 800):
        line(ox, (8, y - 5), (1192, y - 5), "C-Kiris")
        line(ox, (8, y + 5), (1192, y + 5), "C-Kiris")
        txt("IPE200", ox + 500, y + (15 if y == 0 else -25))
    # mahya kirişi: kapalı dikdörtgen + kenar ve eksen çizgileri (tuzak), kılavuzlu marka
    _msp.add_lwpolyline(rect(ox + 8, 395, 1184, 10), close=True, dxfattribs={"layer": "C-Kiris"})
    for yy in (395, 400, 405):
        line(ox, (8, yy), (1192, yy), "C-Kiris")
    _msp.add_line((ox + 1000, 405), (ox + 1030, 440), dxfattribs={"layer": "C-Marka-Cizgi"})
    txt("IPE200", ox + 1030, 440)
    # makaslar: dikdörtgen, eave → mahya; kılavuzlu marka
    for x in MAKAS_X:
        for y0, y1 in ((0, 400), (400, 800)):
            _msp.add_lwpolyline(rect(ox + x - 8, y0, 16, y1 - y0), close=True, dxfattribs={"layer": "C-Makas"})
            my = (y0 + y1) / 2 + 50
            _msp.add_line((ox + x + 8, my), (ox + x + 45, my + 20), dxfattribs={"layer": "C-Marka-Cizgi"})
            txt("HEA160", ox + x + 45, my + 20)
    if kot:
        for x in MAKAS_X:
            txt("+4.00", ox + x + 20, -30, 8, "G-Kot")
            txt("+4.00", ox + x + 20, 822, 8, "G-Kot")
            txt("+6.00", ox + x + 20, 418, 8, "G-Kot")
    # aşıklar: tek çizgi (x doğrultusu), marka üstünde paralel; biri markasız
    for y in ASIK_Y:
        line(ox, (0, y), (1200, y), "C-Asik")
        if y != ASIK_MARKASIZ:
            txt("80x40x3", ox + 520, y + 8, 8)
    # çaprazlar: tek çizgi köşegen, marka paralel
    for a, b in CAPRAZ:
        line(ox, a, b, "C-Capraz")
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        mx, my = a[0] + (b[0] - a[0]) * 0.3, a[1] + (b[1] - a[1]) * 0.3
        nx, ny = -math.sin(math.radians(ang)) * 8, math.cos(math.radians(ang)) * 8
        txt("Ø48.3x3", ox + mx + nx, my + ny, 6, rot=ang)
    if egim_yazisi:
        # eğim oku yazısı: eğim doğrultusunda (y), iki çatı yüzünde
        txt("%50", ox + 1000, 150, 10, "G-Egim", rot=90)
        txt("%50", ox + 1000, 550, 10, "G-Egim", rot=90)
    # tuzaklar
    line(ox, (0, 830), (1200, 830), "C-Kiris-Kesikli")         # gizli çizgi
    line(ox, (600, 440), (600, 470), "C-Asik")                 # markasız kısa yardımcı çizgi
    path = Path(path)
    doc.saveas(path)
    return path


def golden_truth_steel2(egim_bilgisi: bool = True) -> dict:
    """egim_bilgisi: çizimde kot ya da eğim yazısı var (ikisi de aynı eğimi verir: 2 m / 4 m = %50)."""
    rise = KOT_MAHYA - KOT_SACAK
    boy = {
        "HEB160": 2 * len(XS) * H_KOLON,
        "IPE200": 2 * 11.84 + 11.84,                                   # iki saçak (çift çizgi) + mahya (dikdörtgen)
        "HEA160": len(MAKAS_X) * 2 * (math.hypot(4.0, rise) if egim_bilgisi else 4.0),
        "80x40x3": len(ASIK_Y) * 12.0,
        "Ø48.3x3": len(CAPRAZ) * (math.sqrt(4.0 ** 2 + 4.0 ** 2 + rise ** 2) if egim_bilgisi else math.hypot(4.0, 4.0)),
    }
    kg = {p: boy[p] * KG[p] for p in boy}
    return {"boy": boy, "kg": kg, "toplam": sum(kg.values()), "kolon_adet": 2 * len(XS),
            "egimli_adet": (len(MAKAS_X) * 2 + len(CAPRAZ)) if egim_bilgisi else 0}
