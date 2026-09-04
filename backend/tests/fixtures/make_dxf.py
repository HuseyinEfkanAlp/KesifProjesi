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
