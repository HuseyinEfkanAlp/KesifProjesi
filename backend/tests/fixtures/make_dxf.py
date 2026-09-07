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


def make_standard_dxf(path: str | Path) -> Path:
    """KÇS standart çizim (mm). Katman adı kendini tanıtır. Beklenen keşif:
      KSF-HAV-HAVA_KANAL-600x400        polyline 10 m + 5 m            -> 15 m
      KSF-SIH-BORU_PPRC_TEMIZ-25        çizgi 8 m                      -> 8 m
      KSF-YAN-SPRINKLER-K80_UST         6 blok                         -> 6 adet
      KSF-CEP-KOMPOZIT_PANEL-4MM        kapalı polyline 10 x 3 m       -> 30 m²
      KSF-IZO-XPS-5                     tarama 5 x 4 m                 -> 20 m²
      KSF-MIM-DUVAR_YTONG-20x300        çizgi 6 m, yükseklik 3.00 m    -> 18 m²
      KSF-STA-DOLGU-30                  kapalı polyline 4 x 5 m, 0.30  -> 6 m³
      KSF-PEY-AGAC-CINAR                3 blok                         -> 3 adet
      KSF-ALT-YENI_KALEM-X              katalog dışı çizgi 3 m         -> 3 m (uyarı)
      YAZI / AKS                        standart dışı, metraja girmez
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    layers = ["KSF-HAV-HAVA_KANAL-600x400", "KSF-SIH-BORU_PPRC_TEMIZ-25", "KSF-YAN-SPRINKLER-K80_UST",
              "KSF-CEP-KOMPOZIT_PANEL-4MM", "KSF-IZO-XPS-5", "KSF-MIM-DUVAR_YTONG-20x300", "KSF-STA-DOLGU-30",
              "KSF-PEY-AGAC-CINAR", "KSF-ALT-YENI_KALEM-X", "YAZI", "AKS"]
    for name in layers:
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10000, 0), (10000, 5000)], dxfattribs={"layer": "KSF-HAV-HAVA_KANAL-600x400"})
    msp.add_line((0, 1000), (8000, 1000), dxfattribs={"layer": "KSF-SIH-BORU_PPRC_TEMIZ-25"})
    spk = doc.blocks.new("SPRINKLER")
    spk.add_circle((0, 0), 100)
    for x in range(6):
        msp.add_blockref("SPRINKLER", (x * 3000, 3000), dxfattribs={"layer": "KSF-YAN-SPRINKLER-K80_UST"})
    msp.add_lwpolyline(_rect(0, 20000, 10000, 3000), close=True, dxfattribs={"layer": "KSF-CEP-KOMPOZIT_PANEL-4MM"})
    h = msp.add_hatch(dxfattribs={"layer": "KSF-IZO-XPS-5"})
    h.paths.add_polyline_path(_rect(20000, 0, 5000, 4000), is_closed=True)
    msp.add_line((0, 30000), (6000, 30000), dxfattribs={"layer": "KSF-MIM-DUVAR_YTONG-20x300"})
    msp.add_lwpolyline(_rect(30000, 0, 4000, 5000), close=True, dxfattribs={"layer": "KSF-STA-DOLGU-30"})
    tree = doc.blocks.new("AGAC")
    tree.add_circle((0, 0), 1500)
    for x in range(3):
        msp.add_blockref("AGAC", (40000 + x * 5000, 0), dxfattribs={"layer": "KSF-PEY-AGAC-CINAR"})
    msp.add_line((0, 40000), (3000, 40000), dxfattribs={"layer": "KSF-ALT-YENI_KALEM-X"})
    msp.add_text("ZEMİN KAT TESİSAT PLANI", dxfattribs={"layer": "YAZI", "height": 300}).set_placement((0, -2000))
    msp.add_line((-5000, -5000), (60000, -5000), dxfattribs={"layer": "AKS"})
    path = Path(path)
    doc.saveas(path)
    return path


def make_rebar_table_dxf(path: str | Path, kot: str = "+7.95") -> Path:
    """Donatı paftası metraj tablosu (cm). Poz satırları + çap bazında TOPLAM BOY / AĞIRLIK satırları.
    Beklenen: Ø10 1212 m -> 747.8 kg (0.617), Ø12 762 m -> 676.7 kg (0.888), Ø16 ağırlık satırı '---' -> 0.
    İkinci küçük tablo: Ø14 100 m -> 120.8 kg."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for n in ("VM-METRAJ", "YAZI"):
        doc.layers.add(n)
    msp = doc.modelspace()
    def T(x, y, t, h=6):
        msp.add_text(t, dxfattribs={"layer": "VM-METRAJ", "height": h}).set_placement((x, y))
    y = 1000
    T(0, y, "POZ"); T(100, y, "ÇAP"); T(200, y, "ADET"); T(300, y, "BOY"); T(500, y, "DEMIR UZUNLUGU (m)")
    T(500, y - 30, "ƒ10"); T(620, y - 30, "Ø12"); T(740, y - 30, "Ø16")
    rows = [("01", "12", "254", "300", 620, "762.00"), ("02", "10", "101", "1200", 500, "1212.00")]
    for i, (poz, cap, adet, boy, xcol, L) in enumerate(rows):
        yy = y - 80 - i * 40
        T(0, yy, poz); T(100, yy, cap); T(200, yy, adet); T(300, yy, boy); T(xcol, yy, L)
    y2 = y - 200
    T(-20, y2, "TOPLAM BOY / TOTAL LENGTH (m)"); T(500, y2, "1212.00"); T(620, y2, "762.00"); T(740, y2, "---")
    T(-20, y2 - 40, "BIRIM AGIRLIK / UNIT WEIGTH (kg/m)"); T(500, y2 - 40, "0.617"); T(620, y2 - 40, "0.888"); T(740, y2 - 40, "1.578")
    T(-20, y2 - 80, "AGIRLIK / WEIGTH (kg)"); T(500, y2 - 80, "747.80"); T(620, y2 - 80, "676.66"); T(740, y2 - 80, "0.00")
    T(-20, y2 - 120, "TOPLAM AGIRLIK / TOTAL WEIGTH (kg)"); T(620, y2 - 120, "1424.46")
    T(-20, y2 - 160, "GENEL TOPLAM / GENERAL WEIGTH (kg)"); T(620, y2 - 160, "1424.46")
    # ikinci tablo (ağırlık satırı yok -> boydan hesaplanır)
    T(1500, 1000 - 30, "Ø14")
    T(1400, 800, "03"); T(1450, 800, "14"); T(1470, 800, "10"); T(1490, 800, "1000"); T(1500, 800, "100.00")
    T(1380, 700, "TOPLAM BOY (m)"); T(1500, 700, "100.00")
    msp.add_text(f"{kot} KOTU DÖŞEME DONATI PLANI", dxfattribs={"layer": "YAZI", "height": 20}).set_placement((0, 1200))
    path = Path(path)
    doc.saveas(path)
    return path


def make_beam_detail_dxf(path: str | Path) -> Path:
    """Kiriş açılımı (cm): adetli poz yazıları + adetsiz kesit tekrarları. Beklenen (sadece adetli satırlar):
    P05 72 Ø8 l=160 -> 72×1.60×0.395 = 45.5 kg ; P45 4 Ø14 l=160 -> 4×1.60×1.208 = 7.7 kg ; P90 4 Ø16 l=525 -> 4×5.25×1.578 = 33.1 kg
    Ayrıca bir blok içinde 'KOLON DETAYI' metraj tablosu (Ø12 1000 m -> 888 kg) pafta çerçevesi içinde INSERT edilir."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for n in ("REBAR_DET2", "BEAM4", "TABLO", "YAZI"):
        doc.layers.add(n)
    msp = doc.modelspace()
    # pafta çerçevesi (çok paftalı algılama için iki çerçeve)
    msp.add_lwpolyline(_rect(0, 0, 3000, 2000), close=True, dxfattribs={"layer": "TABLO"})
    msp.add_lwpolyline(_rect(3200, 0, 3000, 2000), close=True, dxfattribs={"layer": "TABLO"})
    msp.add_text("KİRİŞ DETAYLARI", dxfattribs={"layer": "YAZI", "height": 40}).set_placement((100, 1900))
    msp.add_text("KOLON DETAYLARI", dxfattribs={"layer": "YAZI", "height": 40}).set_placement((3300, 1900))
    def T(x, y, t, h=8):
        msp.add_text(t, dxfattribs={"layer": "REBAR_DET2", "height": h}).set_placement((x, y))
    T(300, 1500, "K1018 KIRISI", 12)
    T(600, 1400, "P05 72ƒ8/10 etr. l=160")
    T(600, 1300, "P45 4ƒ14 ila. l= 160")
    T(600, 1200, "P90 4ƒ16 l= 525")
    T(400, 1000, "4ƒ16"); T(400, 950, "P05 ƒ8 l=160")      # kesit tekrarları, sayılmaz
    # kolon paftası: tüm içerik blok
    blk = doc.blocks.new("KOLON_PAFTA")
    blk.add_text("POZ", dxfattribs={"height": 8}).set_placement((100, 1500))
    blk.add_text("ƒ12", dxfattribs={"height": 8}).set_placement((800, 1450))
    blk.add_text("01", dxfattribs={"height": 8}).set_placement((100, 1400))
    blk.add_text("12", dxfattribs={"height": 8}).set_placement((200, 1400))
    blk.add_text("100", dxfattribs={"height": 8}).set_placement((300, 1400))
    blk.add_text("1000", dxfattribs={"height": 8}).set_placement((400, 1400))
    blk.add_text("1000.00", dxfattribs={"height": 8}).set_placement((800, 1400))
    blk.add_text("TOPLAM BOY / TOTAL LENGTH (m)", dxfattribs={"height": 8}).set_placement((100, 1300))
    blk.add_text("1000.00", dxfattribs={"height": 8}).set_placement((800, 1300))
    blk.add_text("AGIRLIK / WEIGTH (kg)", dxfattribs={"height": 8}).set_placement((100, 1200))
    blk.add_text("888.00", dxfattribs={"height": 8}).set_placement((800, 1200))
    blk.add_line((100, 1100), (900, 1100))
    msp.add_blockref("KOLON_PAFTA", (3200, 0), dxfattribs={"layer": "TABLO"})
    path = Path(path)
    doc.saveas(path)
    return path


def make_facade_dxf(path: str | Path) -> Path:
    """Cephe görünüşü (cm), ofis katman adlarıyla (KSF değil). Beklenen (eşleme sonrası):
    brn_hatch_gazbeton: 2 tarama 10x3 m + 6x3 m = 48 m² ; brn_glass: kapalı polyline 2x1.5 m x 3 = 9 m² ;
    Söve: çizgiler 4 x 2 m = 8 m ; Kartonpiyer: 5 blok -> 5 adet ; brn_dim: ölçü (eşlenmez)."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for n in ("brn_hatch_gazbeton", "brn_glass", "Söve", "Kartonpiyer", "brn_dim", "TABLO"):
        doc.layers.add(n)
    msp = doc.modelspace()
    msp.add_lwpolyline(_rect(-100, -100, 3000, 1500), close=True, dxfattribs={"layer": "TABLO"})
    for x, w in ((0, 1000), (1200, 600)):
        h = msp.add_hatch(dxfattribs={"layer": "brn_hatch_gazbeton"})
        h.paths.add_polyline_path(_rect(x, 0, w, 300), is_closed=True)
    for x in (100, 400, 700):
        msp.add_lwpolyline(_rect(x, 50, 200, 150), close=True, dxfattribs={"layer": "brn_glass"})
    for x in (100, 400, 700, 1300):
        msp.add_line((x, 250), (x + 200, 250), dxfattribs={"layer": "Söve"})
    k = doc.blocks.new("KARTONPIYER")
    k.add_lwpolyline([(0, 0), (30, 0), (30, 10), (0, 10)], close=True)
    for x in range(5):
        msp.add_blockref("KARTONPIYER", (x * 300, 320), dxfattribs={"layer": "Kartonpiyer"})
    msp.add_line((0, -50), (1000, -50), dxfattribs={"layer": "brn_dim"})
    msp.add_text("ÖN GÖRÜNÜŞ", dxfattribs={"layer": "TABLO", "height": 30}).set_placement((0, 1300))
    path = Path(path)
    doc.saveas(path)
    return path


def make_roof_dxf(path: str | Path) -> Path:
    """Çatı planı + detay notları (cm), ofis katmanlarıyla. Beklenen: ÇATI katmanında 20x10 m = 200 m² çatı alanı;
    yazılarda kenet çatı sistemi kanıtı (KENET, OSB 11 mm, 10 cm TAŞYÜNÜ, MERTEK); buhar kesici ve aşık yazmıyor."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5
    for n in ("ÇATI", "OLUK", "NOT", "TABLO"):
        doc.layers.add(n)
    msp = doc.modelspace()
    msp.add_lwpolyline(_rect(-100, -100, 2500, 1500), close=True, dxfattribs={"layer": "TABLO"})
    msp.add_lwpolyline(_rect(0, 0, 2000, 1000), close=True, dxfattribs={"layer": "ÇATI"})
    msp.add_line((0, 0), (2000, 0), dxfattribs={"layer": "OLUK"})
    msp.add_text("ÇATI PLANI", dxfattribs={"layer": "TABLO", "height": 30}).set_placement((0, 1300))
    y = 1100
    for note in ("ÇATI DETAYI - KENET ÇATI SİSTEMİ", "1- TİTANYUM ÇİNKO KENET KAPLAMA", "2- AYIRICI KEÇE",
                 "3- OSB 11 mm", "4- NEFES ALAN SU YALITIM ÖRTÜSÜ", "5- 10 cm TAŞYÜNÜ", "6- MERTEK 5x10 AHŞAP"):
        msp.add_text(note, dxfattribs={"layer": "NOT", "height": 8}).set_placement((2100, y))
        y -= 20
    path = Path(path)
    doc.saveas(path)
    return path


def make_precast_dxf(path: str | Path) -> Path:
    """Prekast cephe görünüşü (mm): 'inova prekast - YAZI' katmanında panel kodları (GP-4 ×3, EP17 ×2, GP-3-a ×1),
    aynı katmanda kot yazıları (+4.15) ve tek harf (A) sayılmaz; 'CEPHE HAT' katmanında 20x9 m dış hat (180 m²)."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for n in ("inova prekast - YAZI", "CEPHE HAT", "brn_glass"):
        doc.layers.add(n)
    msp = doc.modelspace()
    msp.add_lwpolyline(_rect(0, 0, 20000, 9000), close=True, dxfattribs={"layer": "CEPHE HAT"})
    for i, code in enumerate(("GP-4", "GP-4", "GP-4", "EP17", "EP17", "GP-3-a", "+4.15", "-4.03 (+0.12)", "A")):
        msp.add_text(code, dxfattribs={"layer": "inova prekast - YAZI", "height": 150}).set_placement((500 + i * 2000, 4000))
    for x in (2000, 8000):
        msp.add_lwpolyline(_rect(x, 1000, 2000, 1500), close=True, dxfattribs={"layer": "brn_glass"})
    path = Path(path)
    doc.saveas(path)
    return path
