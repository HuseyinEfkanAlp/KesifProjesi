"""KÇS şablon DXF: katalogdaki her kalem için hazır katman (disipline göre renk) + açıklama notu.

Tasarımcı bu şablonu açar (ya da kendi çizimine katmanları aktarır) ve her şeyi doğru katmana çizer.
Birim: mm ($INSUNITS = 4). Özellik alanı katman adının sonuna eklenir (KSF-HAV-HAVA_KANAL-600x400).
"""
from __future__ import annotations

from io import StringIO
from pathlib import Path

import ezdxf

from .catalog import MEASURES, Catalog

# disiplin -> AutoCAD renk indeksi
DISC_COLORS: dict[str, int] = {
    "STA": 1, "MIM": 30, "INC": 40, "CEP": 6, "CAT": 200, "IZO": 210, "ELK": 2, "ZAY": 52,
    "MEK": 4, "HAV": 140, "YAN": 10, "SIH": 5, "ALT": 8, "PEY": 3, "ASN": 250,
}


def build_template(catalog: Catalog) -> bytes:
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("KSF-NOT", color=7)
    for disc_code, name in catalog.disciplines.items():
        color = DISC_COLORS.get(disc_code, 7)
        for it in catalog.items.values():
            if it.discipline != disc_code:
                continue
            layer = it.example if it.example.startswith("KSF-") else f"KSF-{disc_code}-{it.code}"
            if layer not in doc.layers:
                lay = doc.layers.add(layer, color=color)
                lay.description = f"{name} · {it.name} · {MEASURES[it.measure][0]} · özellik: {it.spec_label or '-'}"
    msp = doc.modelspace()
    y = 0.0
    lines = [
        "KEŞİF ÇİZİM STANDARDI (KÇS) — şablon",
        "Katman adı: KSF-<DİSİPLİN>-<KALEM>-<ÖZELLİK>   örn. KSF-HAV-HAVA_KANAL-600x400",
        "Alan ayracı '-', kelime içi '_'. Özellik: boyut / kesit / çap / malzeme (serbest, bir katmanda tek özellik).",
        "Adet kalemleri BLOK olarak yerleştirilir; uzunluk kalemleri çizgi / polyline; alan kalemleri KAPALI polyline ya da tarama.",
        "Duvar tipi kalemler (m²): uzunluk × duvar yüksekliği; özellikte 2. sayı yükseklik (cm) olabilir: KSF-MIM-DUVAR_YTONG-20x300.",
        "Hacim kalemleri (m³): kapalı alan × özellikteki kalınlık (cm): KSF-STA-DOLGU-30.",
        "Her plan / kat ayrı pafta; birim mm; yazı ve ölçü katmanları KSF ile başlamaz (metraja girmez).",
    ]
    for t in lines:
        msp.add_text(t, dxfattribs={"layer": "KSF-NOT", "height": 250}).set_placement((0, y))
        y -= 400
    y -= 400
    for d in catalog.by_discipline():
        msp.add_text(f"{d['code']}  {d['name']}", dxfattribs={"layer": "KSF-NOT", "height": 220}).set_placement((0, y))
        y -= 320
        for it in d["items"]:
            msp.add_text(f"   {it['example']:<48} {it['name']}  [{it['unit']}]  {it['spec_label']}",
                         dxfattribs={"layer": "KSF-NOT", "height": 160}).set_placement((0, y))
            y -= 240
        y -= 200
    sbuf = StringIO()
    doc.write(sbuf)   # ezdxf ASCII DXF için metin akışı ister
    return sbuf.getvalue().encode("utf-8")


def save_template(catalog: Catalog, path: str | Path) -> Path:
    path = Path(path)
    path.write_bytes(build_template(catalog))
    return path
