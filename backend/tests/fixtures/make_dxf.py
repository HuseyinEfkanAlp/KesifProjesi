"""Sonucu bilinen sentetik DXF çizimleri üretir (cm biriminde, $INSUNITS=5).

Kat planı (make_storey_dxf):
  - 4 kolon 30x60 (S1..S4): (0,0), (500,0), (0,600), (500,600) sol-alt köşeli
      * S2 blok (INSERT) olarak, S3 hem polyline hem hatch (tekrar eleme testi)
  - K101 25/50: S1-S2 arası x yönünde, kolon yüzünden yüze 470 cm
  - K102 25/50: S1-S3 arası y yönünde, 540 cm
  - D101 h=15: 530 x 660 cm döşeme (34.98 m²)
  - P1 20/250 perde: x 700..720, y 0..250
Temel planı (make_foundation_dxf):
  - Radye h=60: 600 x 700 cm (42 m²)
  - TK1 60/80 sürekli temel: paralel çizgi çifti, 400 cm
"""
from __future__ import annotations

from pathlib import Path

import ezdxf

COLUMN_ORIGINS = [(0, 0), (500, 0), (0, 600), (500, 600)]
COL_W, COL_H = 30, 60


def _rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def make_storey_dxf(path: str | Path) -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for name in ("KOLON", "KIRIS", "DOSEME", "PERDE", "YAZI", "AKS"):
        doc.layers.add(name)
    msp = doc.modelspace()

    # kolon bloğu
    blk = doc.blocks.new("KOLON_30x60")
    blk.add_lwpolyline(_rect(0, 0, COL_W, COL_H), close=True)  # katman "0" -> INSERT katmanını alır

    for i, (x, y) in enumerate(COLUMN_ORIGINS, start=1):
        if i == 2:
            msp.add_blockref("KOLON_30x60", (x, y), dxfattribs={"layer": "KOLON"})
        else:
            msp.add_lwpolyline(_rect(x, y, COL_W, COL_H), close=True, dxfattribs={"layer": "KOLON"})
        if i == 3:
            h = msp.add_hatch(dxfattribs={"layer": "KOLON"})
            h.paths.add_polyline_path(_rect(x, y, COL_W, COL_H), is_closed=True)
        msp.add_text(f"S{i} 30/60", dxfattribs={"layer": "YAZI", "height": 10}).set_placement((x + 35, y + 65))

    # K101: y merkez 30, b=25 -> y 17.5 / 42.5, x 30..500
    msp.add_line((30, 17.5), (500, 17.5), dxfattribs={"layer": "KIRIS"})
    msp.add_line((30, 42.5), (500, 42.5), dxfattribs={"layer": "KIRIS"})
    msp.add_text("K101 25/50", dxfattribs={"layer": "YAZI", "height": 10}).set_placement((250, 30))
    # K102: x merkez 15, b=25 -> x 2.5 / 27.5, y 60..600
    msp.add_line((2.5, 60), (2.5, 600), dxfattribs={"layer": "KIRIS"})
    msp.add_line((27.5, 60), (27.5, 600), dxfattribs={"layer": "KIRIS"})
    msp.add_mtext("K102 25/50", dxfattribs={"layer": "YAZI", "char_height": 10}).set_location((15, 300))

    # döşeme
    msp.add_lwpolyline(_rect(0, 0, 530, 660), close=True, dxfattribs={"layer": "DOSEME"})
    msp.add_text("D101 h=15", dxfattribs={"layer": "YAZI", "height": 10}).set_placement((265, 330))

    # perde
    msp.add_lwpolyline(_rect(700, 0, 20, 250), close=True, dxfattribs={"layer": "PERDE"})
    msp.add_text("P1 20/250", dxfattribs={"layer": "YAZI", "height": 10}).set_placement((725, 125))

    # aks çizgileri (yok sayılmalı)
    msp.add_line((-100, 30), (900, 30), dxfattribs={"layer": "AKS"})
    msp.add_text("A", dxfattribs={"layer": "AKS", "height": 15}).set_placement((-120, 30))

    path = Path(path)
    doc.saveas(path)
    return path


def make_foundation_dxf(path: str | Path) -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for name in ("TEMEL", "YAZI"):
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_lwpolyline(_rect(0, 0, 600, 700), close=True, dxfattribs={"layer": "TEMEL"})
    msp.add_text("RADYE h=60", dxfattribs={"layer": "YAZI", "height": 10}).set_placement((300, 350))
    # sürekli temel: 60 cm genişlik, 400 cm uzunluk, x 1000..1400, y merkez 100
    msp.add_line((1000, 70), (1400, 70), dxfattribs={"layer": "TEMEL"})
    msp.add_line((1000, 130), (1400, 130), dxfattribs={"layer": "TEMEL"})
    msp.add_text("TK1 60/80", dxfattribs={"layer": "YAZI", "height": 10}).set_placement((1200, 100))
    path = Path(path)
    doc.saveas(path)
    return path


def make_unitless_mm_dxf(path: str | Path) -> Path:
    """$INSUNITS yok, mm ile çizilmiş tek kolon 300x600 -> birim tahmini testi."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0  # birimsiz
    doc.layers.add("KOLON")
    msp = doc.modelspace()
    msp.add_lwpolyline(_rect(0, 0, 300, 600), close=True, dxfattribs={"layer": "KOLON"})
    msp.add_lwpolyline(_rect(60000, 0, 300, 600), close=True, dxfattribs={"layer": "KOLON"})
    path = Path(path)
    doc.saveas(path)
    return path


def make_network_dxf(path: str | Path) -> Path:
    """Gerçek kalıp planı tarzı: döşeme çokgeni yok, kirişler çift çizgi, etiketler ayrı yazılar.

    Kasıtlı olarak $INSUNITS=4 (mm) yazılır ama çizim cm ile yapılır (gerçek dosyada görülen hata).
      - 6 kolon 50x50 merkezleri (0,0),(600,0),(1200,0),(0,500),(600,500),(1200,500); "S1".."S6" + "(50/50)" ayrı
      - x yönü kirişler K1..K4 (30/50): kolon yüzünden yüze 550 cm, y yönü K5..K7: 450 cm
      - 2 döşeme paneli "D1" + "d=12" + "+4.00"; 1. panelde 100x100 şaft (DOSEME SAFT katmanı)
    Beklenen: kolon alanı 0.25 m², kiriş net uzunlukları 5.5 / 4.5 m, panel alanı 26.75 m² (şaftlı 25.75).
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for name in ("VM Kolon", "VM Kiriş", "VM Kolon Markası", "VM Kiriş Markası", "VM Döşeme Markası", "VM Döşeme Şaft"):
        doc.layers.add(name)
    msp = doc.modelspace()
    cols = [(0, 0), (600, 0), (1200, 0), (0, 500), (600, 500), (1200, 500)]
    for i, (cx, cy) in enumerate(cols, start=1):
        msp.add_lwpolyline(_rect(cx - 25, cy - 25, 50, 50), close=True, dxfattribs={"layer": "VM Kolon"})
        msp.add_text(f"S{i}", dxfattribs={"layer": "VM Kolon Markası", "height": 8}).set_placement((cx - 20, cy + 30))
        msp.add_text("(50/50)", dxfattribs={"layer": "VM Kolon Markası", "height": 6}).set_placement((cx - 20, cy + 40))
    k = 1
    for cy in (0, 500):                       # x yönü kirişler
        for x0 in (0, 600):
            msp.add_line((x0 + 25, cy - 15), (x0 + 575, cy - 15), dxfattribs={"layer": "VM Kiriş"})
            msp.add_line((x0 + 25, cy + 15), (x0 + 575, cy + 15), dxfattribs={"layer": "VM Kiriş"})
            msp.add_text(f"K{k} (30/50)", dxfattribs={"layer": "VM Kiriş Markası", "height": 6}).set_placement((x0 + 300, cy - 3))
            k += 1
    for cx in (0, 600, 1200):                 # y yönü kirişler
        msp.add_line((cx - 15, 25), (cx - 15, 475), dxfattribs={"layer": "VM Kiriş"})
        msp.add_line((cx + 15, 25), (cx + 15, 475), dxfattribs={"layer": "VM Kiriş"})
        msp.add_text(f"K{k} (30/50)", dxfattribs={"layer": "VM Kiriş Markası", "height": 6, "rotation": 90}).set_placement((cx + 3, 250))
        k += 1
    for x0 in (0, 600):                       # döşeme etiketleri
        msp.add_text("D1", dxfattribs={"layer": "VM Döşeme Markası", "height": 8}).set_placement((x0 + 300, 260))
        msp.add_text("d=12", dxfattribs={"layer": "VM Döşeme Markası", "height": 6}).set_placement((x0 + 300, 245))
        msp.add_text("+4.00", dxfattribs={"layer": "VM Döşeme Markası", "height": 6}).set_placement((x0 + 300, 230))
    msp.add_lwpolyline(_rect(100, 100, 100, 100), close=True, dxfattribs={"layer": "VM Döşeme Şaft"})
    path = Path(path)
    doc.saveas(path)
    return path


if __name__ == "__main__":
    out = Path(__file__).parent
    print(make_storey_dxf(out / "kat_plani.dxf"))
    print(make_foundation_dxf(out / "temel_plani.dxf"))


def make_arch_dxf(path: str | Path) -> Path:
    """Mimari kat planı (cm). Sonucu bilinen:
      - Dış duvarlar: YTONG 20 cm, çift çizgi; 1000 x 800 cm dikdörtgen oda (dış ölçü), iç ölçü 960 x 760
        Katman "A-DUVAR-YTONG". Alt duvarda 90 cm kapı boşluğu (parçalar birleştirilir).
      - İç bölme: "DUVAR TUGLA" katmanı, 10 cm, x=500, y 20..780 (uzunluk 760) -> tuğla 10 cm
      - Kapılar: 2 adet "KAPI_90" bloğu (katman KAPI) + "K1 90/210" etiketi biri, diğeri etiketsiz
      - Pencereler: 3 adet "PENCERE" bloğu (katman PENCERE) + "P1 120/140" etiketleri (2 tanesi), bir "P2 60/60"
    Beklenen duvar uzunlukları (merkez hattı): dış çevre 2*(990+790) = 3560 cm ≈ 35.6 m ; iç 7.6 m
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for name in ("A-DUVAR-YTONG", "DUVAR TUGLA", "KAPI", "PENCERE", "YAZI", "MOBILYA"):
        doc.layers.add(name)
    msp = doc.modelspace()
    W, H, t = 1000, 800, 20
    # dış çift çizgi (dış ve iç hat); alt duvarda x 400..490 kapı boşluğu
    outer = [(0, 0), (W, 0), (W, H), (0, H)]
    inner = [(t, t), (W - t, t), (W - t, H - t), (t, H - t)]
    for pts in (outer, inner):
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            if a[1] == b[1] and a[1] in (0, t) and a[0] < b[0]:      # alt duvar: kapı boşluğu bırak
                msp.add_line(a, (400, a[1]), dxfattribs={"layer": "A-DUVAR-YTONG"})
                msp.add_line((490, a[1]), b, dxfattribs={"layer": "A-DUVAR-YTONG"})
            else:
                msp.add_line(a, b, dxfattribs={"layer": "A-DUVAR-YTONG"})
    msp.add_text("YTONG 20", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((W / 2, -30))
    # iç bölme 10 cm, x 495..505
    msp.add_line((495, t), (495, H - t), dxfattribs={"layer": "DUVAR TUGLA"})
    msp.add_line((505, t), (505, H - t), dxfattribs={"layer": "DUVAR TUGLA"})
    msp.add_text("TUGLA 10", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((510, 400))

    door = doc.blocks.new("KAPI_90")
    door.add_line((0, 0), (90, 0))
    door.add_arc((0, 0), 90, 0, 90)
    win = doc.blocks.new("PENCERE")
    win.add_lwpolyline([(0, 0), (120, 0), (120, 20), (0, 20)], close=True)
    win.add_line((0, 10), (120, 10))

    msp.add_blockref("KAPI_90", (400, 0), dxfattribs={"layer": "KAPI"})
    msp.add_text("K1 90/210", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((420, 40))
    msp.add_blockref("KAPI_90", (495, 300), dxfattribs={"layer": "KAPI", "rotation": 90})  # etiketsiz
    for x in (150, 700):
        msp.add_blockref("PENCERE", (x, H - t), dxfattribs={"layer": "PENCERE"})
        msp.add_text("P1 120/140", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((x + 10, H + 20))
    msp.add_blockref("PENCERE", (W - t, 300), dxfattribs={"layer": "PENCERE", "rotation": 90})
    msp.add_text("P2 60/60", dxfattribs={"layer": "YAZI", "height": 8}).set_placement((W + 30, 310))
    # mobilya (yok sayılmalı)
    msp.add_lwpolyline([(100, 100), (200, 100), (200, 180), (100, 180)], close=True, dxfattribs={"layer": "MOBILYA"})
    path = Path(path)
    doc.saveas(path)
    return path


def make_elec_dxf(path: str | Path) -> Path:
    """Elektrik tava/kuvvet planı (mm). Sonucu bilinen:
      - Tava: "E-TAVA" katmanı, polyline (0,0)->(20000,0)->(20000,8000) = 28 m, etiket "TAVA 200x60"
              ikinci tava çift çizgi: y=15000 ve y=15100 arasında x 0..10000 -> 100 mm genişlik, 10 m, etiket "100x50"
      - Kablo: "E-KABLO" katmanı: 3 hat
              L1: (0,500)->(12000,500) 12 m, etiket "NYY 4x16"
              L2: (0,1000)->(6000,1000)->(6000,4000) 9 m, iki parça uç uca, etiket "3x2,5 NYM"
              L3: (0,2000)->(5000,2000) 5 m, katman adından: "E-KABLO-5x6" katmanında, etiketsiz
      - Boru: "E-BORU" katmanı (0,3000)->(4000,3000) 4 m, etiket "Ø20 PVC"
      - Armatür: "E-ARMATUR" katmanı: 4 adet "LED_PANEL" bloğu, "E-PRIZ": 3 adet "PRIZ_TOPRAKLI", "E-ANAHTAR": 2 adet "ANAHTAR"
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for name in ("E-TAVA", "E-KABLO", "E-KABLO-5x6", "E-BORU", "E-ARMATUR", "E-PRIZ", "E-ANAHTAR", "E-YAZI", "AKS"):
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (20000, 0), (20000, 8000)], dxfattribs={"layer": "E-TAVA"})
    msp.add_text("TAVA 200x60", dxfattribs={"layer": "E-YAZI", "height": 150}).set_placement((10000, 200))
    msp.add_line((0, 15000), (10000, 15000), dxfattribs={"layer": "E-TAVA"})
    msp.add_line((0, 15100), (10000, 15100), dxfattribs={"layer": "E-TAVA"})
    msp.add_text("100x50", dxfattribs={"layer": "E-YAZI", "height": 150}).set_placement((5000, 15200))

    msp.add_line((0, 500), (12000, 500), dxfattribs={"layer": "E-KABLO"})
    msp.add_text("NYY 4x16", dxfattribs={"layer": "E-YAZI", "height": 100}).set_placement((6000, 600))
    msp.add_line((0, 1000), (6000, 1000), dxfattribs={"layer": "E-KABLO"})
    msp.add_line((6000, 1000), (6000, 4000), dxfattribs={"layer": "E-KABLO"})
    msp.add_text("3x2,5 NYM", dxfattribs={"layer": "E-YAZI", "height": 100}).set_placement((3000, 1100))
    msp.add_line((0, 2000), (5000, 2000), dxfattribs={"layer": "E-KABLO-5x6"})

    msp.add_line((0, 3000), (4000, 3000), dxfattribs={"layer": "E-BORU"})
    msp.add_text("Ø20 PVC", dxfattribs={"layer": "E-YAZI", "height": 100}).set_placement((2000, 3100))

    led = doc.blocks.new("LED_PANEL")
    led.add_lwpolyline([(0, 0), (600, 0), (600, 600), (0, 600)], close=True)
    priz = doc.blocks.new("PRIZ_TOPRAKLI")
    priz.add_circle((0, 0), 100)
    anahtar = doc.blocks.new("ANAHTAR")
    anahtar.add_circle((0, 0), 80)
    anahtar.add_line((0, 80), (150, 200))
    for x in (2000, 6000, 10000, 14000):
        msp.add_blockref("LED_PANEL", (x, 5000), dxfattribs={"layer": "E-ARMATUR"})
    for x in (1000, 5000, 9000):
        msp.add_blockref("PRIZ_TOPRAKLI", (x, 7000), dxfattribs={"layer": "E-PRIZ"})
    for x in (3000, 7000):
        msp.add_blockref("ANAHTAR", (x, 7500), dxfattribs={"layer": "E-ANAHTAR"})
    msp.add_line((-1000, -1000), (25000, -1000), dxfattribs={"layer": "AKS"})
    path = Path(path)
    doc.saveas(path)
    return path
