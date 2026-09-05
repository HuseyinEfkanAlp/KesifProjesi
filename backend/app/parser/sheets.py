"""Çok paftalı / büyük DXF dosyaları: ezdxf'siz akış taraması, pafta tespiti ve pafta kırpma.

Ruhsat projelerinde bütün paftalar (temel, kat kalıp planları, donatı, detaylar...) tek model uzayında yan yana
durur ve dosya yüzlerce MB olabilir. ezdxf ile tümünü belleğe almak yerine dosya satır satır okunur:

  scan_sheets(path)  -> paftaları bulur. Önce pafta ÇERÇEVELERİ aranır: 4 çizgiden ya da kapalı polyline'dan
                        oluşan büyük dikdörtgenler ile büyük antet bloklarının (INSERT) yerleşimleri. Her çerçeve
                        bir paftadır; başlığı çerçevenin içindeki en büyük "... PLANI / KESİTİ / DETAYI" yazısıdır.
                        Çerçeve bulunamazsa nesne konumları boşluklara göre kümelenir (yedek yöntem).
  crop_sheets(...)   -> seçilen paftaların sınır kutusundaki nesneleri (çizgi, polyline, yazı, daire, yay, solid)
                        tek geçişte küçük DXF'lere yazar; bunlar normal yükleyici (loader.load_dxf) ile analiz edilir.

Blok referansları (INSERT) ve tarama (HATCH) kırpmaya alınmaz: kalıp planlarında taşıyıcı elemanlar çizgi /
polyline olarak durur; bloklar aks balonu, kesit simgesi gibi metraja girmeyen şeylerdir.
"""
from __future__ import annotations

import json
import math
import re
from array import array
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

import ezdxf
import numpy as np

# Pafta başlığı sayılan yazılar
TITLE_RE = re.compile(r"PLAN|KES[İI]T|DETAY|APL[İI]KASYON|G[ÖO]R[ÜU]N[ÜU]Ş|Ç[İI]Z[İI]M|CIZIM", re.IGNORECASE)
CODEPAGES = {"ANSI_1254": "cp1254", "ANSI_1252": "cp1252", "ANSI_1250": "cp1250", "ANSI_1251": "cp1251"}
# Bu boyutun üstündeki dosyalar ezdxf ile hiç açılmaz; pafta seçimi zorunludur
BIG_FILE_BYTES = 40 * 1024 * 1024
MIN_SHEET_ENTITIES = 5
FRAME_COVERAGE_MIN = 0.5   # çerçevelerin içine düşen nesne oranı bunun altındaysa "çerçeve" sanılanlar çerçeve değildir
# Kümelemede kullanılan nesne tipleri: kırpmaya alınanlar + INSERT (konumu güvenilir).
# HATCH'in 10/20 kodu "yükseklik noktası"dır (çoğu zaman 0,0); DIMENSION tanım noktası pafta dışına düşebilir.
CLUSTER_TYPES = {"LINE", "LWPOLYLINE", "VERTEX", "TEXT", "MTEXT", "ATTRIB", "CIRCLE", "ARC", "SOLID", "TRACE",
                 "INSERT", "SPLINE", "ELLIPSE", "POINT"}

Bbox = tuple[float, float, float, float]   # x0, y0, x1, y1 (çizim birimi)


@dataclass
class Sheet:
    index: int
    title: str
    bbox: Bbox
    entity_count: int
    text_count: int
    titled: bool = True
    source: str = "frame"     # frame | cluster
    titles: list[str] = field(default_factory=list)   # paftadaki diğer başlık adayları (büyükten küçüğe)

    def to_dict(self) -> dict:
        return {"index": self.index, "title": self.title, "bbox": [round(v, 3) for v in self.bbox],
                "entity_count": self.entity_count, "text_count": self.text_count, "titled": self.titled,
                "source": self.source, "titles": list(self.titles)}

    @classmethod
    def from_dict(cls, d: dict) -> "Sheet":
        return cls(int(d["index"]), d["title"], tuple(d["bbox"]), int(d["entity_count"]),
                   int(d.get("text_count", 0)), bool(d.get("titled", True)), d.get("source", "frame"),
                   list(d.get("titles", [])))


@dataclass
class SheetScan:
    path: str
    insunits: int
    entity_count: int
    extent: Bbox | None
    sheets: list[Sheet] = field(default_factory=list)

    @property
    def multi_sheet(self) -> bool:
        return len(self.sheets) >= 2

    def to_dict(self) -> dict:
        return {"path": self.path, "insunits": self.insunits, "entity_count": self.entity_count,
                "extent": list(self.extent) if self.extent else None, "sheets": [s.to_dict() for s in self.sheets]}

    @classmethod
    def from_dict(cls, d: dict) -> "SheetScan":
        return cls(d["path"], int(d.get("insunits", 0)), int(d.get("entity_count", 0)),
                   tuple(d["extent"]) if d.get("extent") else None, [Sheet.from_dict(s) for s in d.get("sheets", [])])

    def cache_path(self) -> Path:
        return _cache_path(self.path)

    def save(self) -> None:
        self.cache_path().write_text(json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "SheetScan | None":
        cache = _cache_path(path)
        if not cache.exists():
            return None
        try:
            return cls.from_dict(json.loads(cache.read_text(encoding="utf-8")))
        except Exception:
            return None


def _cache_path(path: str | Path) -> Path:
    p = Path(path)
    return p.with_name(p.name + ".sheets.json")


# ---------- Akış okuyucu ----------

def _open_dxf_text(path: str | Path):
    """DXF metin dosyasını doğru kodlamayla açar (R2007+ UTF-8, eskiler $DWGCODEPAGE)."""
    with Path(path).open("rb") as fh:
        head = fh.read(16384).decode("ascii", errors="ignore")
    m = re.search(r"\$ACADVER\s*\r?\n\s*1\s*\r?\n\s*(AC\d+)", head)
    ver = m.group(1) if m else "AC1009"
    enc = "utf-8"
    if ver < "AC1021":
        m = re.search(r"\$DWGCODEPAGE\s*\r?\n\s*3\s*\r?\n\s*(\S+)", head)
        enc = CODEPAGES.get((m.group(1).upper() if m else ""), "cp1252")
    return open(path, "r", encoding=enc, errors="replace")


def _iter_entities(f, with_blocks: bool = False):
    """ENTITIES bölümündeki nesneleri sözlük olarak verir.

    Ayrıca HEADER'dan $INSUNITS'i ({"t": "__header__"}) ve with_blocks=True ise BLOCKS bölümündeki her blok
    tanımının sınır kutusunu ({"t": "__block__", "name", "bbox"}) bildirir.
    """
    it = iter(f)
    section = None
    cur: dict | None = None
    header: dict = {}
    hkey = None
    blk_name = None
    blk_xs: list[float] = []
    blk_ys: list[float] = []
    in_blk_entity = False
    while True:
        try:
            code = next(it).strip()
            val = next(it).rstrip("\r\n")
        except StopIteration:
            break
        if code == "0":
            if cur is not None:
                yield cur
                cur = None
            if val == "SECTION":
                section = None
                continue
            if val == "ENDSEC":
                if section == "HEADER":
                    yield {"t": "__header__", **header}
                section = None
                continue
            if section == "ENTITIES":
                cur = {"t": val, "xs": [], "ys": []}
            elif section == "BLOCKS" and with_blocks:
                if val == "BLOCK":
                    blk_name, blk_xs, blk_ys, in_blk_entity = None, [], [], False
                elif val == "ENDBLK":
                    if blk_name and blk_xs and blk_ys:
                        yield {"t": "__block__", "name": blk_name,
                               "bbox": (min(blk_xs), min(blk_ys), max(blk_xs), max(blk_ys))}
                    blk_name, in_blk_entity = None, False
                else:
                    in_blk_entity = val not in ("INSERT", "HATCH", "DIMENSION", "ATTDEF")
            continue
        if code == "2" and section is None:
            section = val.strip()
            continue
        if section == "HEADER":
            if code == "9":
                hkey = val.strip()
            elif hkey == "$INSUNITS" and code == "70":
                try:
                    header["insunits"] = int(val)
                except ValueError:
                    pass
            continue
        if section == "BLOCKS" and with_blocks:
            if code == "2" and blk_name is None:
                blk_name = val.strip()
            elif in_blk_entity and code in ("10", "11"):
                blk_xs.append(float(val))
            elif in_blk_entity and code in ("20", "21"):
                blk_ys.append(float(val))
            continue
        if cur is None:
            continue
        if code in ("10", "11", "12", "13"):
            cur["xs"].append(float(val))
        elif code in ("20", "21", "22", "23"):
            cur["ys"].append(float(val))
        elif code == "8":
            cur["8"] = val.strip()
        elif code == "1":
            cur["1"] = val
        elif code == "3":
            cur.setdefault("3", []).append(val)
        elif code == "2":
            cur["2"] = val.strip()
        elif code in ("40", "41", "42", "43", "50", "51"):
            try:
                cur[code] = float(val)
            except ValueError:
                pass
        elif code == "70":
            try:
                cur["70"] = int(val)
            except ValueError:
                pass
    if cur is not None:
        yield cur


def _clean_text(s: str) -> str:
    s = re.sub(r"\\[A-Za-z][^;]*;", "", s)
    s = s.replace("{", "").replace("}", "").replace("\\P", " ").replace("%%U", "").replace("%%u", "")
    return re.sub(r"\s+", " ", s).strip()


# ---------- Çerçeve (pafta sınırı) tespiti ----------

def _rect_of_polyline(xs: list[float], ys: list[float]) -> Bbox | None:
    """4 (ya da kapanış noktasıyla 5) köşeli, eksenlere paralel dikdörtgen polyline -> bbox."""
    pts = list(zip(xs, ys))
    if len(pts) == 5 and math.dist(pts[0], pts[4]) < 1e-6:
        pts = pts[:4]
    if len(pts) != 4:
        return None
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return None
    tol = 1e-6 * max(x1 - x0, y1 - y0)
    for px, py in pts:
        if not ((abs(px - x0) < tol or abs(px - x1) < tol) and (abs(py - y0) < tol or abs(py - y1) < tol)):
            return None
    return (x0, y0, x1, y1)


def _rects_from_lines(lines: np.ndarray, min_len: float) -> list[Bbox]:
    """Yatay/dikey uzun çizgilerden köşeleri buluşan dikdörtgenler (4 ayrı LINE ile çizilmiş çerçeveler)."""
    if len(lines) == 0:
        return []
    q = max(min_len / 200.0, 1e-9)   # köşe eşleşme toleransı

    def key(v: float) -> int:
        return int(round(v / q))

    horiz: dict[tuple[int, int], list[float]] = defaultdict(list)   # (x0,x1) -> y'ler
    vert: set[tuple[int, int, int]] = set()                          # (x, y0, y1)
    for x1, y1, x2, y2 in lines:
        if abs(y1 - y2) <= q and abs(x1 - x2) >= min_len:
            a, b = sorted((x1, x2))
            horiz[(key(a), key(b))].append(y1)
        elif abs(x1 - x2) <= q and abs(y1 - y2) >= min_len:
            a, b = sorted((y1, y2))
            vert.add((key(x1), key(a), key(b)))

    def has_vert(x: int, y0: int, y1: int) -> bool:
        for dx in (-1, 0, 1):
            for d0 in (-1, 0, 1):
                for d1 in (-1, 0, 1):
                    if (x + dx, y0 + d0, y1 + d1) in vert:
                        return True
        return False

    rects: list[Bbox] = []
    for (kx0, kx1), ys in horiz.items():
        ys = sorted(set(round(y / q) for y in ys))
        for i in range(len(ys)):
            for j in range(i + 1, len(ys)):
                ky0, ky1 = ys[i], ys[j]
                if (ky1 - ky0) * q < min_len:
                    continue
                if has_vert(kx0, ky0, ky1) and has_vert(kx1, ky0, ky1):
                    rects.append((kx0 * q, ky0 * q, kx1 * q, ky1 * q))
    return rects


def _select_frames(rects: list[Bbox], extent: float) -> list[Bbox]:
    """Aday dikdörtgenlerden pafta çerçevelerini seçer: yeterince büyük, birbirinin içinde olmayanlar."""
    if not rects:
        return []
    min_side = extent * 1e-4
    cands = [r for r in rects if (r[2] - r[0]) >= min_side and (r[3] - r[1]) >= min_side]
    if not cands:
        return []
    areas = [(r[2] - r[0]) * (r[3] - r[1]) for r in cands]
    amax = max(areas)
    side_min = 0.05 * math.sqrt(amax)
    cands = [r for r, a in zip(cands, areas)
             if a >= 0.12 * amax and (r[2] - r[0]) >= side_min and (r[3] - r[1]) >= side_min]
    cands.sort(key=lambda r: -(r[2] - r[0]) * (r[3] - r[1]))
    kept: list[Bbox] = []
    for r in cands:
        ra = (r[2] - r[0]) * (r[3] - r[1])
        nested = False
        for k in kept:
            ix = max(0.0, min(r[2], k[2]) - max(r[0], k[0]))
            iy = max(0.0, min(r[3], k[3]) - max(r[1], k[1]))
            if ix * iy >= 0.9 * ra:
                nested = True
                break
        if not nested and not any(abs(r[0] - k[0]) < 1e-6 and abs(r[1] - k[1]) < 1e-6 and
                                  abs(r[2] - k[2]) < 1e-6 and abs(r[3] - k[3]) < 1e-6 for k in kept):
            kept.append(r)
    # tüm çizimi saran tek bir "dış" dikdörtgen varsa (diğerlerinin çoğunu kapsıyorsa) onu çıkar
    if len(kept) >= 3:
        for k in list(kept):
            inside = sum(1 for r in kept if r is not k and r[0] >= k[0] - 1e-6 and r[1] >= k[1] - 1e-6 and
                         r[2] <= k[2] + 1e-6 and r[3] <= k[3] + 1e-6)
            if inside >= 2:
                kept.remove(k)
    return kept


# ---------- Yedek yöntem: konum kümeleme ----------

def _split_positions(values: np.ndarray, gap: float) -> list[float]:
    """Yoğunluk tabanlı 1B bölme: 'gap' genişliğinde kayan pencerede neredeyse hiç nesne olmayan aralıklar
    pafta arası boşluk sayılır; boşluğa düşen tek tük nesne bölmeyi bozmaz."""
    if len(values) < 2:
        return []
    vmin, vmax = float(values.min()), float(values.max())
    if vmax - vmin <= gap:
        return []
    binw = gap / 4.0
    nbins = int((vmax - vmin) / binw) + 1
    counts = np.bincount(((values - vmin) / binw).astype(np.int64), minlength=nbins)
    win = np.convolve(counts, np.ones(4, dtype=float), mode="valid")   # 4 kutu = gap
    nonzero = counts[counts > 0]
    thresh = max(1.0, 0.02 * 4 * float(np.median(nonzero)))   # seyrek çizimde 1, yoğun çizimde medyanın %2'si
    empty = win < thresh
    splits: list[float] = []
    run_start = None
    for i, e in enumerate(np.append(empty, False)):
        if e and run_start is None:
            run_start = i
        elif not e and run_start is not None:
            if run_start > 0 and i < len(win):
                splits.append(vmin + (run_start + i + 3) / 2.0 * binw)
            run_start = None
    return splits


def _clusters_1d(values: np.ndarray, gap: float) -> list[tuple[float, float, np.ndarray]]:
    splits = _split_positions(values, gap)
    if not splits:
        return [(float(values.min()), float(values.max()), np.arange(len(values)))]
    ids = np.searchsorted(np.array(splits), values)
    out = []
    for k in range(len(splits) + 1):
        idx = np.where(ids == k)[0]
        if len(idx):
            v = values[idx]
            lo, hi = float(np.percentile(v, 0.5)), float(np.percentile(v, 99.5))
            out.append((lo, hi, idx))
    return out


def _cells(xs: np.ndarray, ys: np.ndarray, gap: float, min_count: int) -> list[tuple[Bbox, int]]:
    """Önce x'te, sonra her x kümesi içinde y'de böler. Pafta içinde plan ile antet/başlık arasında dikey boşluk
    olağandır; bu yüzden y bölmesi daha geniş boşluk ister (3 × gap)."""
    cells: list[tuple[Bbox, int]] = []
    for x0, x1, idx in _clusters_1d(xs, gap):
        if len(idx) < min_count:
            continue
        for y0, y1, jdx in _clusters_1d(ys[idx], 3.0 * gap):
            if len(jdx) < min_count:
                continue
            cells.append(((x0, y0, x1, y1), int(len(jdx))))
    return cells


def cluster_sheets(xs: np.ndarray, ys: np.ndarray, extent: float) -> list[Bbox]:
    """Nesne noktalarını boşluklara göre kümeler; küme sayısının değişmediği ilk eşik (plato) seçilir."""
    n = len(xs)
    if n == 0 or extent <= 0:
        return []
    min_count = max(MIN_SHEET_ENTITIES, int(n * 0.0002))
    gaps = [extent / 20000 * (1.35 ** k) for k in range(30)]
    gaps = [g for g in gaps if g <= extent / 6]
    counts = [len(_cells(xs, ys, g, min_count)) for g in gaps]
    for k in range(len(gaps) - 2):
        c0, c1, c2 = counts[k], counts[k + 1], counts[k + 2]
        if c0 >= 2 and c1 >= 0.9 * c0 and c2 >= 0.85 * c0:
            return [b for b, _ in _cells(xs, ys, gaps[k], min_count)]
    return []


# ---------- Pafta tespiti ----------

def _build_sheets(boxes: list[tuple[Bbox, str]], xs: np.ndarray, ys: np.ndarray,
                  titles: list[tuple[float, float, float, str]], extent: float) -> list[Sheet]:
    sheets: list[Sheet] = []
    # Başlık kutunun içinde değilse (kümeleme yedeğinde antet yazısı plandan ayrı kalabilir) en yakın kutuya bağlanır
    def _dist(t, b) -> float:
        dx = max(b[0] - t[0], 0.0, t[0] - b[2])
        dy = max(b[1] - t[1], 0.0, t[1] - b[3])
        return math.hypot(dx, dy)

    owner: dict[int, int] = {}
    for ti, t in enumerate(titles):
        best, best_d = None, extent * 0.3
        for bi, (bbox, _) in enumerate(boxes):
            d = _dist(t, bbox)
            if d < best_d:
                best, best_d = bi, d
        if best is not None:
            owner[ti] = best
    for bi, (bbox, source) in enumerate(boxes):
        x0, y0, x1, y1 = bbox
        count = int(np.count_nonzero((xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)))
        inside = [t for ti, t in enumerate(titles) if owner.get(ti) == bi]
        title, titled = "", False
        alts: list[str] = []
        if inside:
            inside.sort(key=lambda t: -t[2])
            title, titled = inside[0][3], True
            for t in inside[1:]:
                if t[3] not in alts and t[3] != title:
                    alts.append(t[3])
                if len(alts) >= 5:
                    break
        sheets.append(Sheet(0, title, bbox, count, len(inside), titled, source, alts))
    # sıralama: üst satırdan alta, soldan sağa. Aynı satır = y aralıkları çakışan paftalar.
    sheets.sort(key=lambda s: -(s.bbox[1] + s.bbox[3]) / 2)
    rows: list[list[Sheet]] = []
    for s in sheets:
        if rows and min(rows[-1][0].bbox[3], s.bbox[3]) > max(rows[-1][0].bbox[1], s.bbox[1]):
            rows[-1].append(s)
        else:
            rows.append([s])
    sheets = [s for row in rows for s in sorted(row, key=lambda s: s.bbox[0])]
    for i, s in enumerate(sheets):
        s.index = i
        if not s.titled:
            s.title = f"Pafta {i + 1} (başlıksız, {s.entity_count} nesne)"
    return sheets


def scan_sheets(path: str | Path) -> SheetScan:
    """Dosyayı bir kez akış halinde okur; çerçeveleri (yoksa kümeleri) ve başlıkları bulup paftaları verir."""
    xs = array("d")
    ys = array("d")
    heights = array("d")
    lines = array("d")                    # x1,y1,x2,y2 dörtlüleri
    rects: list[Bbox] = []                # kapalı dikdörtgen polyline'lar
    inserts: list[tuple[str, float, float, float, float]] = []   # ad, x, y, sx, sy
    blocks: dict[str, Bbox] = {}
    texts: list[tuple[float, float, float, str]] = []
    insunits = 0
    count = 0
    with _open_dxf_text(path) as f:
        for ent in _iter_entities(f, with_blocks=True):
            t = ent["t"]
            if t == "__header__":
                insunits = int(ent.get("insunits", 0) or 0)
                continue
            if t == "__block__":
                blocks[ent["name"]] = ent["bbox"]
                continue
            if not ent["xs"] or not ent["ys"]:
                continue
            count += 1
            if t not in CLUSTER_TYPES:
                continue
            xs.append(ent["xs"][0])
            ys.append(ent["ys"][0])
            if t == "LINE" and len(ent["xs"]) >= 2 and len(ent["ys"]) >= 2:
                lines.extend((ent["xs"][0], ent["ys"][0], ent["xs"][1], ent["ys"][1]))
            elif t == "LWPOLYLINE" and (ent.get("70", 0) & 1 or len(ent["xs"]) == 5):
                r = _rect_of_polyline(ent["xs"], ent["ys"])
                if r:
                    rects.append(r)
            elif t == "INSERT" and ent.get("2"):
                inserts.append((ent["2"], ent["xs"][0], ent["ys"][0],
                                float(ent.get("41", 1.0) or 1.0), float(ent.get("42", 1.0) or 1.0)))
            elif t in ("TEXT", "MTEXT", "ATTRIB"):
                h = float(ent.get("40", 0.0) or 0.0)
                txt = _clean_text(ent.get("1", "") + "".join(ent.get("3", [])))
                if h > 0 and txt:
                    heights.append(h)
                    if len(txt) <= 120 and TITLE_RE.search(txt):
                        texts.append((ent["xs"][0], ent["ys"][0], h, txt))
    npx = np.frombuffer(xs, dtype="d").copy() if len(xs) else np.zeros(0)
    npy = np.frombuffer(ys, dtype="d").copy() if len(ys) else np.zeros(0)
    if len(npx) == 0:
        return SheetScan(str(path), insunits, count, None, [])
    extent_box = (float(npx.min()), float(npy.min()), float(npx.max()), float(npy.max()))
    extent = max(extent_box[2] - extent_box[0], extent_box[3] - extent_box[1])
    titles: list[tuple[float, float, float, str]] = []
    if len(heights):
        med = median(heights)
        titles = [t for t in texts if t[2] >= 1.8 * med]

    # 1) çerçeveler
    cands: list[Bbox] = list(rects)
    if extent > 0:
        ln = np.frombuffer(lines, dtype="d").reshape(-1, 4) if len(lines) else np.zeros((0, 4))
        cands.extend(_rects_from_lines(ln, min_len=extent * 0.003))
        for name, x, y, sx, sy in inserts:
            b = blocks.get(name)
            if b:
                w, h = (b[2] - b[0]) * abs(sx), (b[3] - b[1]) * abs(sy)
                if w >= extent * 0.003 and h >= extent * 0.003:
                    cands.append((x + b[0] * sx, y + b[1] * sy, x + b[0] * sx + w, y + b[1] * sy + h)
                                 if sx > 0 and sy > 0 else (min(x + b[0] * sx, x + b[2] * sx), min(y + b[1] * sy, y + b[3] * sy),
                                                            max(x + b[0] * sx, x + b[2] * sx), max(y + b[1] * sy, y + b[3] * sy)))
    frames = _select_frames(cands, extent) if extent > 0 else []
    # boş çerçeveler (şablon antet vb.) atılır; çerçeveler nesnelerin çoğunu kapsamıyorsa bunlar pafta çerçevesi değildir
    mask = np.zeros(len(npx), dtype=bool)
    kept_frames: list[Bbox] = []
    for x0, y0, x1, y1 in frames:
        m = (npx >= x0) & (npx <= x1) & (npy >= y0) & (npy <= y1)
        if int(np.count_nonzero(m)) >= MIN_SHEET_ENTITIES:
            kept_frames.append((x0, y0, x1, y1))
            mask |= m
    frames = kept_frames if np.count_nonzero(mask) >= FRAME_COVERAGE_MIN * len(npx) else []
    boxes: list[tuple[Bbox, str]] = []
    if len(frames) >= 2:
        boxes = [(fr, "frame") for fr in frames]
        # çerçeve dışında kalan nesneler (varsa) kümelenerek eklenir
        rest = ~mask
        if np.count_nonzero(rest) >= max(MIN_SHEET_ENTITIES, int(0.01 * len(npx))):
            for b in cluster_sheets(npx[rest], npy[rest], extent) or [
                    (float(npx[rest].min()), float(npy[rest].min()), float(npx[rest].max()), float(npy[rest].max()))]:
                boxes.append((b, "cluster"))
    else:
        boxes = [(b, "cluster") for b in cluster_sheets(npx, npy, extent)]
    sheets = _build_sheets(boxes, npx, npy, titles, extent) if len(boxes) >= 2 else []
    return SheetScan(str(path), insunits, count, extent_box, sheets)


# ---------- Kırpma ----------

class _Target:
    def __init__(self, bbox: Bbox, dest: Path, margin_ratio: float):
        x0, y0, x1, y1 = bbox
        mx = (x1 - x0) * margin_ratio
        my = (y1 - y0) * margin_ratio
        self.box = (x0 - mx, y0 - my, x1 + mx, y1 + my)
        self.dest = dest
        self.doc = ezdxf.new("R2010")
        self.msp = self.doc.modelspace()
        self.layers: set[str] = set()
        self.written = 0

    def inside(self, xs: list[float], ys: list[float]) -> bool:
        x0, y0, x1, y1 = self.box
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in zip(xs, ys))


def crop_sheet(src: str | Path, bbox: Bbox, dest: str | Path, margin_ratio: float = 0.02) -> int:
    """bbox içindeki nesneleri yeni bir DXF'e yazar; yazılan nesne sayısını döndürür."""
    return crop_sheets(src, [(bbox, dest)], margin_ratio)[0]


BLOCK_PASS_MAX_BYTES = 500 * 1024 * 1024   # blok / tarama içeriği için ezdxf ile ikinci geçiş yapılacak en büyük dosya


def crop_sheets(src: str | Path, targets: list[tuple[Bbox, str | Path]], margin_ratio: float = 0.02,
                include_blocks: bool = True) -> list[int]:
    """Birden çok paftayı tek geçişte kırpar; her hedef için yazılan nesne sayısını döndürür.

    include_blocks: pafta içine düşen blok yerleşimlerinin (INSERT) içeriği de yazılır (bazı ofisler tüm paftayı ya da
    donatı tablosunu blok olarak koyar). Bu ikinci geçiş ezdxf ile yapılır; çok büyük dosyalarda atlanır.
    """
    tg = [_Target(b, Path(d), margin_ratio) for b, d in targets]
    poly: dict | None = None      # POLYLINE + VERTEX ... SEQEND
    insunits = 0
    inserts_hit = 0
    with _open_dxf_text(src) as f:
        for ent in _iter_entities(f):
            t = ent["t"]
            if t == "__header__":
                insunits = int(ent.get("insunits", 0) or 0)
                continue
            layer = ent.get("8", "0")
            if t in ("INSERT", "HATCH"):
                xs, ys = ent.get("xs") or [], ent.get("ys") or []
                if xs and ys and any(g.inside(xs, ys) for g in tg):
                    inserts_hit += 1
                elif t == "HATCH":
                    inserts_hit += 1          # tarama sınır noktaları akışta okunmaz; ezdxf geçişinde kontrol edilir
                continue
            if t == "POLYLINE":
                poly = {"layer": layer, "closed": bool(ent.get("70", 0) & 1), "pts": []}
                continue
            if t == "VERTEX":
                if poly is not None and ent["xs"] and ent["ys"]:
                    poly["pts"].append((ent["xs"][0], ent["ys"][0]))
                continue
            if t == "SEQEND":
                if poly is not None and len(poly["pts"]) >= 2:
                    pxs = [p[0] for p in poly["pts"]]
                    pys = [p[1] for p in poly["pts"]]
                    for g in tg:
                        if g.inside(pxs, pys):
                            g.msp.add_lwpolyline(poly["pts"], close=poly["closed"], dxfattribs={"layer": poly["layer"]})
                            g.layers.add(poly["layer"])
                            g.written += 1
                poly = None
                continue
            xs, ys = ent["xs"], ent["ys"]
            if not xs or not ys:
                continue
            for g in tg:
                if g.inside(xs, ys):
                    _write_entity(g, t, ent, xs, ys, layer)
    if include_blocks and inserts_hit and Path(src).stat().st_size <= BLOCK_PASS_MAX_BYTES:
        try:
            _add_block_contents(src, tg)
        except Exception:
            pass
    out = []
    for g in tg:
        for name in g.layers:
            if name not in g.doc.layers:
                try:
                    g.doc.layers.add(name)
                except Exception:
                    pass
        g.doc.header["$INSUNITS"] = insunits
        g.doc.saveas(str(g.dest))
        out.append(g.written)
    return out


def _add_block_contents(src: str | Path, tg: list["_Target"]) -> None:
    """Hedef paftalara düşen taramaları (sınır çokgeni) ve INSERT içeriğini (patlatılmış) yazar."""
    import ezdxf
    from ezdxf import path as ezpath

    doc = ezdxf.readfile(str(src))
    msp = doc.modelspace()
    # taramalar (HATCH): sınır yolları kapalı polyline olarak yazılır (cephe / mimari alan ölçümü)
    for h in msp.query("HATCH"):
        try:
            for pth in ezpath.from_hatch(h):
                pts = [(v.x, v.y) for v in pth.flattening(0.5)]
                if len(pts) < 3:
                    continue
                xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
                for g in tg:
                    if g.inside(xs, ys):
                        g.msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": h.dxf.layer}); g.layers.add(h.dxf.layer); g.written += 1
        except Exception:
            continue
    for ins in msp.query("INSERT"):
        try:
            subs = list(ins.virtual_entities())
        except Exception:
            continue
        if not subs:
            continue
        for sub in subs:
            t = sub.dxftype()
            layer = sub.dxf.layer if sub.dxf.hasattr("layer") else "0"
            if layer == "0":
                layer = ins.dxf.layer
            try:
                if t in ("TEXT", "ATTRIB"):
                    txt = sub.dxf.text
                    p = sub.dxf.insert
                    xs, ys = [p.x], [p.y]
                    for g in tg:
                        if g.inside(xs, ys) and txt.strip():
                            g.msp.add_text(txt, height=float(sub.dxf.height or 1.0), rotation=float(sub.dxf.rotation or 0.0),
                                           dxfattribs={"layer": layer}).set_placement((p.x, p.y))
                            g.layers.add(layer); g.written += 1
                elif t == "MTEXT":
                    txt = sub.plain_text()
                    p = sub.dxf.insert
                    for g in tg:
                        if g.inside([p.x], [p.y]) and txt.strip():
                            m = g.msp.add_mtext(txt, dxfattribs={"layer": layer, "char_height": float(sub.dxf.char_height or 1.0)})
                            m.set_location((p.x, p.y), rotation=float(sub.dxf.rotation or 0.0))
                            g.layers.add(layer); g.written += 1
                elif t == "LINE":
                    a, b = sub.dxf.start, sub.dxf.end
                    for g in tg:
                        if g.inside([a.x, b.x], [a.y, b.y]):
                            g.msp.add_line((a.x, a.y), (b.x, b.y), dxfattribs={"layer": layer}); g.layers.add(layer); g.written += 1
                elif t in ("LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
                    pth = ezpath.make_path(sub)
                    pts = [(v.x, v.y) for v in pth.flattening(0.5)]
                    if len(pts) < 2:
                        continue
                    closed = bool(getattr(sub, "is_closed", False)) or t == "CIRCLE" or pth.is_closed
                    xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
                    for g in tg:
                        if g.inside(xs, ys):
                            g.msp.add_lwpolyline(pts, close=closed, dxfattribs={"layer": layer}); g.layers.add(layer); g.written += 1
            except Exception:
                continue


def _write_entity(g: _Target, t: str, ent: dict, xs: list[float], ys: list[float], layer: str) -> None:
    msp = g.msp
    attrs = {"layer": layer}
    try:
        if t == "LINE" and len(xs) >= 2 and len(ys) >= 2:
            msp.add_line((xs[0], ys[0]), (xs[1], ys[1]), dxfattribs=attrs)
        elif t == "LWPOLYLINE" and len(xs) >= 2:
            msp.add_lwpolyline(list(zip(xs, ys)), close=bool(ent.get("70", 0) & 1), dxfattribs=attrs)
        elif t in ("TEXT", "ATTRIB"):
            txt = ent.get("1", "")
            if not txt.strip():
                return
            h = float(ent.get("40", 0.0) or 0.0) or 1.0
            msp.add_text(txt, height=h, rotation=float(ent.get("50", 0.0) or 0.0), dxfattribs=attrs
                         ).set_placement((xs[0], ys[0]))
        elif t == "MTEXT":
            txt = "".join(ent.get("3", [])) + ent.get("1", "")
            if not txt.strip():
                return
            h = float(ent.get("40", 0.0) or 0.0) or 1.0
            m = msp.add_mtext(txt, dxfattribs={**attrs, "char_height": h})
            m.set_location((xs[0], ys[0]), rotation=float(ent.get("50", 0.0) or 0.0))
        elif t == "CIRCLE":
            msp.add_circle((xs[0], ys[0]), float(ent.get("40", 0.0) or 0.0), dxfattribs=attrs)
        elif t == "ARC":
            msp.add_arc((xs[0], ys[0]), float(ent.get("40", 0.0) or 0.0),
                        float(ent.get("50", 0.0) or 0.0), float(ent.get("51", 360.0) or 360.0), dxfattribs=attrs)
        elif t in ("SOLID", "TRACE") and len(xs) >= 3:
            pts = list(zip(xs, ys))
            if len(pts) == 3:
                pts.append(pts[2])
            msp.add_solid(pts[:4], dxfattribs=attrs)
        else:
            return
    except Exception:
        return
    g.layers.add(layer)
    g.written += 1
