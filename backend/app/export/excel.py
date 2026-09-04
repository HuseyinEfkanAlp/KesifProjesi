"""Metraj ve maliyet Excel raporu (openpyxl)."""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..parser.layer_profile import ELEMENT_TYPES
from ..quantity.engine import QuantityLine
from ..quantity.summary import SUBTYPE_LABELS

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)


def _header(ws, row: int, headers: list[str]) -> None:
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _autosize(ws) -> None:
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(width + 2, 10), 45)


def build_workbook(project: dict, lines: list[QuantityLine], summary: dict, cost: dict,
                   element_info: dict | None = None) -> bytes:
    """element_info: element_id -> {"drawing": str, "layer": str, "b":..., "h":..., ...} (isteğe bağlı)."""
    element_info = element_info or {}
    wb = Workbook()

    # ---- Metraj Özeti ----
    ws = wb.active
    ws.title = "Metraj Özeti"
    ws["A1"] = f"Proje: {project.get('name', '')}"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"Kat yüksekliği: {project.get('storey_height', '')} m   Döşeme kalınlığı: {project.get('slab_thickness', '')} m"
    _header(ws, 4, ["Eleman Grubu", "Adet", "Beton (m³)", "Kalıp (m²)", "Demir (kg)"])
    r = 5
    for g in summary["groups"]:
        ws.append([g["label"], g["element_count"], g["concrete_m3"], g["formwork_m2"], g["rebar_kg"]])
        r += 1
    t = summary["totals"]
    ws.append(["TOPLAM", "", t["concrete_m3"], t["formwork_m2"], t["rebar_kg"]])
    for c in ws[r]:
        c.font = BOLD
    _autosize(ws)

    # ---- Eleman Listesi ----
    ws2 = wb.create_sheet("Eleman Metrajı")
    _header(ws2, 1, ["Çizim", "Tip", "Ad", "Katman", "b (m)", "h (m)", "Kalınlık (m)", "Alan (m²)",
                     "Uzunluk (m)", "Adet", "Kat Çarpanı", "Beton (m³)", "Kalıp (m²)", "Demir (kg)",
                     "Toplam Beton (m³)", "Toplam Kalıp (m²)", "Toplam Demir (kg)", "Notlar"])
    for ln in lines:
        info = element_info.get(ln.element_id, {})
        label = ELEMENT_TYPES.get(ln.etype, ln.etype)
        if ln.subtype:
            label = SUBTYPE_LABELS.get(ln.subtype, label)
        ws2.append([
            info.get("drawing", ""), label, ln.name or "", info.get("layer", ""),
            info.get("b"), info.get("h"), info.get("thickness"), info.get("area"), info.get("length"),
            ln.count, ln.multiplier, round(ln.concrete_m3, 4), round(ln.formwork_m2, 4), round(ln.rebar_kg, 2),
            round(ln.total_concrete, 4), round(ln.total_formwork, 4), round(ln.total_rebar, 2),
            "; ".join(ln.notes + list(info.get("warnings", []))),
        ])
    _autosize(ws2)

    # ---- Maliyet ----
    ws3 = wb.create_sheet("Maliyet")
    _header(ws3, 1, ["Kalem", "Grup", "Birim", "Miktar", "Birim Fiyat (₺)", "Tutar (₺)", "Fiyat Kaynağı"])
    for l in cost["lines"]:
        ws3.append([l["kind_label"], l["group_label"], l["unit"], l["quantity"], l["unit_price"], l["total"],
                    l["price_source"]])
    r = ws3.max_row + 2
    ws3.cell(row=r, column=5, value="Ara Toplam").font = BOLD
    ws3.cell(row=r, column=6, value=cost["subtotal"]).font = BOLD
    if cost.get("vat_rate"):
        ws3.cell(row=r + 1, column=5, value=f"KDV (%{cost['vat_rate']*100:.0f})")
        ws3.cell(row=r + 1, column=6, value=cost["vat"])
        r += 1
    ws3.cell(row=r + 1, column=5, value="GENEL TOPLAM").font = BOLD
    ws3.cell(row=r + 1, column=6, value=cost["grand_total"]).font = BOLD
    for row in ws3.iter_rows(min_row=2, min_col=5, max_col=6):
        for c in row:
            c.number_format = "#,##0.00"
    _autosize(ws3)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
