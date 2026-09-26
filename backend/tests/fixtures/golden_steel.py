"""Altın çelik: ağırlığı bilinen tek katlı çelik çatı taşıyıcısı (cm çizim, tek dosya, iki pafta).

Sınadığı (Yat Kulübü çelik çatılarındaki çizim alışkanlığıyla):
  - "±0.00 KOTU ÇELİK KOLON YERLEŞİM PLANI": 6 kolon HEB200 kesit (20x20 kare), "Kolon-HEB200" kılavuzlu marka
  - "+4.50 KOTU ÇELİK KİRİŞ PLANI": aynı 6 kolon kesiti + HEA200 ana kiriş, IPE160 tali kiriş, Ø76.1x5 boru çapraz
    (eğik dikdörtgen), 100x50x3 kutu aşık; markalar kılavuzlu ya da elemanın yanında
Doğru sonuç: kolon boyu kotlardan 4,50 m (yerleşim ±0.00 → kiriş planı +4.50), kolonlar bir kez sayılır.
kg/m burada bağımsız yazılır (EN 10365 anma değeri; boru / kutu kesitten, 7850 kg/m³) — programın tablosu kullanılmaz.
"""
import math
from pathlib import Path

import ezdxf

SHEET_DX = 3000
XS = (0, 600, 1200)          # kolon aksları (cm)
YS = (0, 500)
C = 20                       # HEB200 kesit 20 cm
H_KOLON = 4.50
KG = {"HEB200": 61.3, "HEA200": 42.3, "IPE160": 15.8,
      "Ø76.1x5": math.pi * (76.1 - 5) * 5 * 7850e-6,
      "100x50x3": (2 * 3 * (100 + 50) - 4 * 3 * 3) * 7850e-6}

_msp = None


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def txt(s, x, y, h=10, layer="C-Marka-Yazi"):
    _msp.add_text(s, dxfattribs={"layer": layer, "height": h}).set_placement((x, y))


def sheet(i, title):
    ox = i * SHEET_DX
    _msp.add_lwpolyline(rect(ox - 300, -400, 1900, 1300), close=True, dxfattribs={"layer": "ANTET"})
    txt(title, ox, -300, 40, "G-Detay-Tanim")
    txt("(Ölçek: 1/50)", ox, -360, 20, "G-Detay-Tanim")
    return ox


def uye(ox, a, b, gen, layer):
    """a→b eksenli, `gen` genişlikli eleman dikdörtgeni (eğik olabilir)."""
    (x1, y1), (x2, y2) = a, b
    L = math.hypot(x2 - x1, y2 - y1)
    nx, ny = -(y2 - y1) / L * gen / 2, (x2 - x1) / L * gen / 2
    pts = [(ox + x1 + nx, y1 + ny), (ox + x2 + nx, y2 + ny), (ox + x2 - nx, y2 - ny), (ox + x1 - nx, y1 - ny)]
    _msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
    return L / 100.0


def kolonlar(ox):
    for x in XS:
        for y in YS:
            _msp.add_lwpolyline(rect(ox + x - C / 2, y - C / 2, C, C), close=True, dxfattribs={"layer": "G-Kolon"})
            # kılavuzlu marka: çizgi kolonun köşesinden yazıya
            tx, ty = ox + x + 60, y + (60 if y == 0 else -80)
            _msp.add_line((ox + x + C / 2, y + C / 2 if y == 0 else y - C / 2), (tx, ty), dxfattribs={"layer": "C-Marka-Cizgi"})
            txt("Kolon-HEB200", tx, ty)


def members():
    """(profil, a, b, genişlik cm, katman, marka yeri) — kiriş planındaki elemanlar."""
    out = []
    for y in YS:                                   # x yönü ana kirişler: kolon yüzünden kolon yüzüne
        for xa, xb in zip(XS[:-1], XS[1:]):
            out.append(("HEA200", (xa + C / 2, y), (xb - C / 2, y), 20, "C-Kiris"))
    for x in XS:                                   # y yönü ana kirişler
        out.append(("HEA200", (x, C / 2), (x, 500 - C / 2), 20, "C-Kiris"))
    for x in (300, 900):                           # tali kirişler: ana kiriş yüzünden yüzüne
        out.append(("IPE160", (x, 10), (x, 490), 8.2, "C-TaliKiris"))
    out.append(("Ø76.1x5", (20, 20), (280, 480), 7.61, "C-Capraz"))      # 1. açıklıkta çapraz
    out.append(("Ø76.1x5", (920, 20), (1180, 480), 7.61, "C-Capraz"))    # 2. açıklıkta çapraz
    out.append(("100x50x3", (10, 250), (290, 250), 5, "C-Asik"))         # aşıklar (tali kirişler arası)
    out.append(("100x50x3", (310, 250), (890, 250), 5, "C-Asik"))
    out.append(("100x50x3", (910, 250), (1190, 250), 5, "C-Asik"))
    return out


def golden_truth_steel() -> dict:
    kg: dict[str, float] = {}
    boy: dict[str, float] = {}
    for prof, a, b, _, _ in members():
        L = math.hypot(b[0] - a[0], b[1] - a[1]) / 100.0
        boy[prof] = boy.get(prof, 0.0) + L
        kg[prof] = kg.get(prof, 0.0) + L * KG[prof]
    n = len(XS) * len(YS)
    boy["HEB200"] = n * H_KOLON
    kg["HEB200"] = n * H_KOLON * KG["HEB200"]
    return {"kg": kg, "boy": boy, "toplam": sum(kg.values()), "kolon_adet": n}


def make_golden_steel(path: str | Path) -> Path:
    global _msp
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    _msp = doc.modelspace()
    ox = sheet(0, "±0.00 KOTU ÇELİK KOLON YERLEŞİM PLANI")
    kolonlar(ox)
    ox = sheet(1, "+4.50 KOTU ÇELİK KİRİŞ PLANI")
    kolonlar(ox)
    for prof, a, b, gen, layer in members():
        uye(ox, a, b, gen, layer)
        # 1/3 noktası: 1. açıklıkta aşığın ortası çaprazın ortasıyla çakışıyor
        mx, my = a[0] + (b[0] - a[0]) / 3, a[1] + (b[1] - a[1]) / 3
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        # marka: elemanın 1/3 noktasından dik yönde 25 cm ötede, kılavuz çizgisiyle
        nx, ny = -dy / L * 25, dx / L * 25
        _msp.add_line((ox + mx, my), (ox + mx + nx, my + ny), dxfattribs={"layer": "C-Marka-Cizgi"})
        txt(prof, ox + mx + nx, my + ny, 8)
    path = Path(path)
    doc.saveas(path)
    return path


# ---------------------------------------------------------------- boya yüzeyi, bağlantı, işçilik doğruları
# Boya yüzeyi: Euronorm tablolarındaki AL (m²/m) — programın 2h+4b formülü DEĞİL (formül bunlara ±%5 yakın olmalı)
AL = {"HEB200": 1.151, "HEA200": 1.136, "IPE160": 0.623, "Ø76.1x5": math.pi * 0.0761, "100x50x3": 0.29}
# Saha başlangıç normları (kullanıcı kararı 26 Eyl 2026): (imalat, montaj) saat/ton — kg/m ≤20 hafif, ≤60 orta, üstü ağır
NORM = {"HEB200": (18, 14), "HEA200": (25, 20), "IPE160": (40, 35), "Ø76.1x5": (40, 35), "100x50x3": (40, 35)}


def golden_connections() -> dict:
    """Tipik detay: betona oturan kolona taban plakası (h+10)×(b+10) cm × 20 mm + 4 ankraj; I kiriş ucuna alın levhası
    h × b × 10 mm + 4 bulon (h ≤ 200); boru çapraz ucuna guse (d+10)² × 8 mm + 2 bulon; kutu aşık uçları kaynaklı."""
    t = golden_truth_steel()
    n_kolon = t["kolon_adet"]
    say = {}
    for prof, *_ in members():
        say[prof] = say.get(prof, 0) + 1
    levha = n_kolon * 0.30 * 0.30 * 0.020 * 7850
    levha += say["HEA200"] * 2 * 0.190 * 0.200 * 0.010 * 7850
    levha += say["IPE160"] * 2 * 0.160 * 0.082 * 0.010 * 7850
    levha += say["Ø76.1x5"] * 2 * (0.0761 + 0.10) ** 2 * 0.008 * 7850
    bulon = (say["HEA200"] + say["IPE160"]) * 2 * 4 + say["Ø76.1x5"] * 2 * 2
    kaynak = n_kolon * AL["HEB200"] + sum(n * 2 * AL[p] for p, n in say.items())
    yuzey = {p: t["boy"][p] * AL[p] for p in t["boy"]}
    imalat = sum(t["kg"][p] * NORM[p][0] for p in t["kg"]) / 1000 + levha * 0.04
    montaj = sum(t["kg"][p] * NORM[p][1] for p in t["kg"]) / 1000 + bulon * 0.15
    vinc = sum(t["kg"][p] * NORM[p][1] for p in t["kg"]) / 1000 * 0.2
    return {"levha": levha, "bulon": bulon, "ankraj": 4 * n_kolon, "kaynak": kaynak, "yuzey": yuzey,
            "imalat": imalat, "montaj": montaj, "vinc": vinc}
