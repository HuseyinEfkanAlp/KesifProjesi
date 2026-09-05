"""Donatı paftalarındaki metraj tablolarını okur (poz / çap / adet / boy / toplam boy / ağırlık).

Tablo yoksa poz yazıları toplanır (kiriş / kolon açılımı): "P45 4ƒ14 ila. l= 160", "P05 72ƒ8/10 etr. l=160"
= poz 45: 4 adet Ø14, her biri 160 cm. Ağırlık = adet × boy × birim ağırlık. Adetsiz kesit yazıları ("4ƒ12",
"P05 ƒ8 l=160") sayılmaz (aynı çubuğun kesitteki tekrarıdır).

Statik ofis programları (ideCAD, Sta4CAD, ProtaStructure...) donatı planının yanına poz tablosu basar:
    POZ | ÇAP | ADET | BOY | DEMİR ŞEKLİ | DEMİR UZUNLUĞU (m):  Ø10 | Ø12 | Ø16
    01  | 12  | 254  | 300 | ...          |                            762.00
    ...
    TOPLAM BOY (m)          46208.81 | 2000.10 | ---
    BİRİM AĞIRLIK (kg/m)     0.617   | 0.888   | 1.578
    AĞIRLIK (kg)            28510.84 | 1776.09 | 0.00
    TOPLAM AĞIRLIK (kg)               30286.92
Çap sütunları başlıktaki "Ø10" / "ƒ10" (font glyph) yazılarından, değerler aynı satırdaki en yakın sütundan alınır.
Ağırlık satırı yoksa toplam boy × birim ağırlık (0.006165·d²) ile hesaplanır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .loader import Drawing

DIA_HEADER = re.compile(r"^\s*(?:[ØøΦφ∅ƒ]|%%c|Q|F)\s*(?P<d>\d{1,2})\s*(?:mm)?\s*$", re.IGNORECASE)
NUM = re.compile(r"^-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?$|^-?\d+(?:[.,]\d+)?$")
ROW_TOTAL_LEN = re.compile(r"TOPLAM\s*BOY|TOTAL\s*LENGTH", re.IGNORECASE)
ROW_UNIT_W = re.compile(r"B[Iİ]R[Iİ]M\s*A[GĞ]IRLIK|UNIT\s*WEIG", re.IGNORECASE)
ROW_WEIGHT = re.compile(r"^\s*A[GĞ]IRLIK|^\s*WEIG", re.IGNORECASE)
ROW_TOTAL_W = re.compile(r"TOPLAM\s*A[GĞ]IRLIK|TOTAL\s*WEIG|GENEL\s*TOPLAM|GENERAL", re.IGNORECASE)


def unit_weight(d_mm: int) -> float:
    return 0.006165 * d_mm * d_mm       # kg/m (7850 kg/m³)


def _num(s: str) -> float | None:
    s = s.strip().replace(" ", "")
    if not NUM.match(s):
        return None
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(".") > 1 or (s.count(",") >= 1 and s.count(".") == 1 and s.rfind(",") > s.rfind(".")):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class RebarTable:
    columns: dict[int, float]                    # çap (mm) -> sütun x
    total_length: dict[int, float] = field(default_factory=dict)   # m
    weight: dict[int, float] = field(default_factory=dict)         # kg
    pos_count: int = 0
    total_kg_declared: float | None = None
    anchor: tuple[float, float] = (0.0, 0.0)
    warnings: list[str] = field(default_factory=list)

    def finalize(self) -> None:
        for d in self.columns:
            if d not in self.weight or self.weight[d] <= 0:
                if d in self.total_length and self.total_length[d] > 0:
                    self.weight[d] = self.total_length[d] * unit_weight(d)
                    self.warnings.append(f"Ø{d}: ağırlık satırı yok; toplam boy × birim ağırlık ile hesaplandı")
        if self.total_kg_declared and self.total_kg:
            diff = abs(self.total_kg - self.total_kg_declared) / self.total_kg_declared
            if diff > 0.02:
                self.warnings.append(f"Tablo genel toplamı ({self.total_kg_declared:.0f} kg) çap toplamıyla ({self.total_kg:.0f} kg) uyuşmuyor")

    @property
    def total_kg(self) -> float:
        return sum(self.weight.values())

    def to_dict(self) -> dict:
        return {"by_dia": {str(d): {"length_m": round(self.total_length.get(d, 0.0), 2), "weight_kg": round(self.weight.get(d, 0.0), 1)}
                           for d in sorted(self.columns)},
                "total_kg": round(self.total_kg, 1), "declared_kg": self.total_kg_declared, "pos_count": self.pos_count,
                "warnings": self.warnings}


def _rows(drawing: Drawing, y_tol: float) -> list[tuple[float, list[tuple[float, str]]]]:
    texts = sorted(((e.points[0][1], e.points[0][0], e.text.strip()) for e in drawing.texts() if e.text.strip()),
                   key=lambda r: (-r[0], r[1]))
    rows: list[tuple[float, list[tuple[float, str]]]] = []
    for y, x, t in texts:
        if rows and abs(rows[-1][0] - y) <= y_tol:
            rows[-1][1].append((x, t))
        else:
            rows.append((y, [(x, t)]))
    return rows


def _split_header(dia_cells: list[tuple[float, int]]) -> list[list[tuple[float, int]]]:
    """Aynı satırdaki çap başlıklarını yan yana duran ayrı tablolara böler (büyük x boşluğu = yeni tablo)."""
    cells = sorted(dia_cells)
    if len(cells) <= 1:
        return [cells]
    gaps = [b[0] - a[0] for a, b in zip(cells, cells[1:])]
    base = min(g for g in gaps if g > 1e-6) if any(g > 1e-6 for g in gaps) else 1.0
    groups: list[list[tuple[float, int]]] = [[cells[0]]]
    for (x, d), g in zip(cells[1:], gaps):
        if g > 3.0 * base:
            groups.append([])
        groups[-1].append((x, d))
    return groups


def _tol(t: RebarTable, default: float) -> float:
    xs = sorted(t.columns.values())
    gaps = [b - a for a, b in zip(xs, xs[1:]) if b - a > 1e-6]
    return (min(gaps) * 0.5) if gaps else default


def parse_rebar_tables(drawing: Drawing) -> list[RebarTable]:
    """Çizimdeki tüm donatı metraj tablolarını döndürür (birden çok tablo, yan yana ya da alt alta olabilir)."""
    heights = [e.height for e in drawing.texts() if e.height > 0]
    med_h = sorted(heights)[len(heights) // 2] if heights else 0.08
    y_tol = med_h * 0.6
    default_tol = max(med_h * 12, 0.5)          # tek sütunlu tabloda sütun eşleme toleransı
    rows = _rows(drawing, y_tol)
    tables: list[RebarTable] = []
    open_tables: list[RebarTable] = []
    for y, cells in rows:
        cells = sorted(cells)
        dia_cells = [(x, int(m.group("d"))) for x, t in cells if (m := DIA_HEADER.match(t)) and 6 <= int(m.group("d")) <= 50]
        if dia_cells:
            # aynı satırda paftanın başka yerlerinde yazılar olabilir (koca pafta); başlık = yan yana duran çap hücreleri
            new_tables = [RebarTable(columns={d: x for x, d in grp}, anchor=(grp[0][0], y)) for grp in _split_header(dia_cells)]
            # yeni başlık, aynı x aralığındaki eski tabloyu kapatır (alt alta tablolar)
            for nt in new_tables:
                lo, hi = min(nt.columns.values()), max(nt.columns.values())
                for ot in list(open_tables):
                    olo, ohi = min(ot.columns.values()), max(ot.columns.values())
                    if not (hi + default_tol < olo or lo - default_tol > ohi):
                        ot.finalize(); tables.append(ot); open_tables.remove(ot)
            open_tables.extend(new_tables)
            continue
        if not open_tables:
            continue
        nums = [(x, _num(t)) for x, t in cells if _num(t) is not None]
        # satır etiketi: hücre hücre bakılır (aynı hizada paftanın başka yazıları da olabilir)
        kind, lx = None, None
        for x, t in cells:
            if _num(t) is not None or DIA_HEADER.match(t):
                continue
            if ROW_TOTAL_LEN.search(t):
                kind, lx = "total_length", x
            elif ROW_UNIT_W.search(t):
                kind, lx = "unit", x
            elif ROW_TOTAL_W.search(t):
                kind, lx = "declared", x
            elif ROW_WEIGHT.search(t):
                kind, lx = "weight", x
            if kind:
                break
        # etiketli satır yalnız etiketin sağındaki en yakın tabloya ait
        scope = open_tables
        if lx is not None:
            cands = [t for t in open_tables if max(t.columns.values()) >= lx - default_tol]
            if cands:
                scope = [min(cands, key=lambda t: abs(min(t.columns.values()) - lx))]

        def nearest(x: float):
            best = None
            for t in scope:
                for d, cx in t.columns.items():
                    dist = abs(cx - x)
                    if dist <= _tol(t, default_tol) and (best is None or dist < best[0]):
                        best = (dist, t, d)
            return best

        def by_col(attr: str) -> None:
            for x, v in nums:
                hit = nearest(x)
                if hit:
                    tgt = getattr(hit[1], attr)
                    tgt[hit[2]] = tgt.get(hit[2], 0.0) + v

        if kind == "total_length":
            by_col("total_length")
        elif kind == "unit":
            pass
        elif kind == "declared":
            for x, v in nums:
                hit = nearest(x)
                if hit:
                    hit[1].total_kg_declared = max(hit[1].total_kg_declared or 0.0, v)
        elif kind == "weight":
            by_col("weight")
        elif nums and len(nums) >= 3:
            hit = nearest(nums[-1][0])
            if hit:
                hit[1].pos_count += 1          # poz satırı: POZ ÇAP ADET BOY ... uzunluk (son sayı çap sütununda)
    for t in open_tables:
        t.finalize()
        tables.append(t)
    return [t for t in tables if t.total_kg > 0]


def _col_gap(t: RebarTable) -> float:
    xs = sorted(t.columns.values())
    gaps = [b - a for a, b in zip(xs, xs[1:]) if b - a > 1e-6]
    return min(gaps) if gaps else 1.0


TARGET_WORDS = [
    ("foundation", re.compile(r"TEMEL|RADYE|FOUND|RAFT", re.IGNORECASE)),
    ("column", re.compile(r"KOLON|COLUMN", re.IGNORECASE)),
    ("beam", re.compile(r"K[Iİ]R[Iİ][SŞ]|BEAM", re.IGNORECASE)),
    ("shear_wall", re.compile(r"PERDE|SHEAR", re.IGNORECASE)),
    ("stair", re.compile(r"MERD[Iİ]VEN|STAIR", re.IGNORECASE)),
]


def target_from_label(label: str) -> str:
    """Donatı paftası hangi elemanın demiri? Başlıktan: TEMEL -> foundation, KOLON -> column, ...; yoksa döşeme."""
    for etype, pat in TARGET_WORDS:
        if pat.search(label or ""):
            return etype
    return "slab"


KOT_RE = re.compile(r"([+\-]\s*\d+[.,]\d{2})")


def kot_from_label(label: str) -> str | None:
    """'+7.95 KOTU KALIP PLANI' -> '+7.95' (kat eşlemesi için)."""
    m = KOT_RE.search(label or "")
    return m.group(1).replace(" ", "").replace(",", ".") if m else None


POZ_LINE = re.compile(
    r"^\s*P\s*(?P<poz>\d+)\s+(?P<n>\d+)\s*(?:[ØøΦφ∅ƒ]|%%c)\s*(?P<d>\d{1,2})(?:\s*/\s*(?P<s>\d+))?"
    r"\s*(?P<tip>[A-Za-zçğıöşüÇĞİÖŞÜ]+)?\.?\s*[lL]\s*=\s*(?P<L>\d+(?:[.,]\d+)?)",
)
POZ_TYPES = {"etr": "etriye", "ila": "ilave", "mon": "montaj", "gov": "gövde", "duz": "düz", "pil": "pilye", "cir": "çiroz"}


def parse_rebar_labels(drawing: Drawing) -> RebarTable | None:
    """Adetli poz yazılarını toplar; RebarTable biçiminde tek 'tablo' döndürür (kaynak: yazılar)."""
    per: dict[int, float] = {}
    lengths: dict[int, float] = {}
    n_lines = 0
    types: dict[str, int] = {}
    for e in drawing.texts():
        m = POZ_LINE.match(e.text.strip())
        if not m:
            continue
        d = int(m.group("d"))
        if not 6 <= d <= 50:
            continue
        n = int(m.group("n"))
        L = float(m.group("L").replace(",", ".")) / 100.0      # cm -> m
        if n <= 0 or L <= 0:
            continue
        per[d] = per.get(d, 0.0) + n * L * unit_weight(d)
        lengths[d] = lengths.get(d, 0.0) + n * L
        n_lines += 1
        tip = (m.group("tip") or "duz").lower()[:3]
        types[tip] = types.get(tip, 0) + 1
    if not per:
        return None
    t = RebarTable(columns={d: 0.0 for d in per}, total_length=lengths, weight=per, pos_count=n_lines)
    t.warnings.append(f"Metraj tablosu yok; {n_lines} adetli poz yazısından hesaplandı "
                      f"({', '.join(f'{POZ_TYPES.get(k, k)} {v}' for k, v in sorted(types.items()))}). "
                      "Boylar yazıdaki değerdir; kanca / bindirme payı yazıda yoksa eksik olabilir")
    return t
