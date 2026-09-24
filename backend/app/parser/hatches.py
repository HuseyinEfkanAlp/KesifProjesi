"""Taramalar (HATCH) ve lejant: malzemenin çizimdeki ikinci dili.

Mimar malzemeyi her zaman yazmaz; çoğu zaman **tarar**. Duvarın içi tuğla deseniyle, perde beton
deseniyle, dolgu toprak deseniyle doldurulur. Bu modül bir taramanın ne olduğunu üç kaynaktan, bu
öncelikle okur:

  1. **Lejant** — çizimin kendi sözlüğü: küçük bir desen örneği ve hemen sağında "19 cm TUĞLA DUVAR".
     Mimarın beyanıdır; aynı desen bu projede ne demekse o demektir.
  2. **Katman adı** — "DUVAR-TUGLA-TARAMA" gibi taramanın katmanı malzemeyi söylüyorsa.
  3. **Desen adı** — AutoCAD'in standart desenleri (AR-CONC beton, EARTH toprak, AR-B816 tuğla…).
     Yalnız anlamı yerleşik olanlar sözlükte durur; ANSI31, DOTS, NET gibi çizerine göre anlam
     değiştiren desenler bilerek YOK: "bilmiyorum" demek yanlış malzeme uydurmaktan iyidir.

Kullanıldığı yer: malzemesi katman adından ya da yakın yazıdan okunamayan duvar, üstünü örten
taramanın malzemesini alır (`assign_wall_materials`). Kaynak her zaman kayda yazılır — "tarama
AR-B816 → tuğla (lejant: '19 cm tuğla duvar')" — çünkü kural tabanlıdır ve açıklanabilir olmalıdır.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass

from shapely.geometry import Polygon
from shapely.strtree import STRtree

from ..planset import normalize_title
from .labels_ext import WALL_MATERIALS, wall_material
from .loader import Drawing, Entity

# Malzeme sözlüğü: anahtar -> görünen ad. Duvar malzemeleri labels_ext ile aynı anahtarları kullanır
# ki taramadan gelen malzeme duvar kalemine doğrudan bağlansın ("tugla:19").
MATERIAL_NAMES: dict[str, str] = {k: v[0] for k, v in WALL_MATERIALS.items()} | {
    "toprak": "Toprak / dolgu",
    "cakil": "Çakıl / blokaj",
    "kum": "Kum / harç",
    "yalitim": "Isı yalıtımı",
    "ahsap": "Ahşap",
}

# Yerleşik anlamı olan standart desenler. Anlamı çizere göre değişenler (ANSI31 "genel kesit",
# DOTS, NET, DASH, ANSI33, ANSI37, LINE, SOLID) sözlükte YOK — gerçek projede (Yat Kulübü, 445
# tarama) bunlar hem cephe süslemesi hem döşeme kaplaması için kullanılmış.
PATTERN_MATERIALS: dict[str, str] = {
    "AR-CONC": "beton",
    "EARTH": "toprak",
    "GRAVEL": "cakil",
    "AR-SAND": "kum",
    "INSUL": "yalitim",
    "AR-B816": "tugla", "AR-B816C": "tugla", "AR-B88": "tugla", "AR-BRSTD": "tugla",
    "AR-BRELM": "tugla", "AR-BRSTK": "tugla", "BRICK": "tugla", "BRSTONE": "tugla",
    "ANSI32": "tugla",          # ANSI tanımında "tuğla, kiremit, pişmiş toprak"
    "ANSI35": "tugla",          # ANSI: ateş tuğlası / refrakter
    "WOOD": "ahsap", "AR-PARQ1": "ahsap",
}

# Yazıdan malzeme: duvar malzemeleri + taramayla sık gösterilen diğerleri.
_TEXT_EXTRA: list[tuple[str, re.Pattern]] = [
    ("yalitim", re.compile(r"YALITIM|IZOLASYON|TAS\s*YUNU|TASYUNU|CAM\s*YUNU|\bXPS\b|\bEPS\b|STRAFOR")),
    ("toprak", re.compile(r"TOPRAK|DOLGU\b|TABII\s*ZEMIN")),
    ("cakil", re.compile(r"CAKIL|BLOKAJ|MICIR|STABILIZE")),
    ("kum", re.compile(r"\bKUM\b|HARC|\bSAP\b")),
    ("ahsap", re.compile(r"AHSAP|KERESTE|PARKE")),
]

# Lejant kutusunun (desen örneği) en büyük boyu ve kutu-yazı eşleşme toleransları (metre).
SWATCH_MAX = 5.0          # 1/100 planda kağıtta 5 cm; lejant örnekleri bundan küçüktür
SWATCH_MAX_ASPECT = 6.0
TEXT_GAP_FACTOR = 4.0     # yazı, örneğin sağ kenarından en fazla bu kadar örnek boyu uzakta başlar
COLUMN_TOL = 0.5          # aynı sütundaki örneklerin sol kenarları arasındaki fark
LEGEND_TITLE = re.compile(r"LEJAN[TD]|GOSTERIM|ACIKLAMA|LEGEND|MALZEME\s*LISTESI|TARAMA")
LEGEND_TITLE_REACH = 15.0  # başlık, örnek sütununun en fazla bu kadar üstünde / yanında
# Bir duvarı taramanın malzemesiyle etiketlemek için taramanın duvarı örtmesi gereken pay.
WALL_COVER_MIN = 0.5


@dataclass
class LegendRow:
    pattern: str
    material: str          # MATERIAL_NAMES anahtarı
    text: str              # lejanttaki yazı


def material_of_text(text: str) -> str | None:
    """Yazıdan malzeme anahtarı; tanınmazsa None."""
    if not text:
        return None
    m = wall_material(text)
    if m:
        return m
    t = normalize_title(text)
    for key, pat in _TEXT_EXTRA:
        if pat.search(t):
            return key
    return None


def _hatches(drawing: Drawing) -> list[Entity]:
    return [e for e in drawing.entities if e.pattern and e.kind == "polygon" and len(e.points) >= 3]


def _poly(e: Entity) -> Polygon | None:
    try:
        p = Polygon(e.points)
        if not p.is_valid:
            p = p.buffer(0)
        return p if not p.is_empty and p.area > 0 else None
    except Exception:
        return None


def read_legend(drawing: Drawing) -> tuple[list[LegendRow], list[str]]:
    """Lejant satırları: desen örneği + sağındaki malzeme yazısı. Döner: (satırlar, uyarılar).

    Tek başına "küçük tarama + yanında yazı" yetmez (mahal etiketinin yanındaki kaplama taraması da
    öyle görünür). Satır sayılması için örnek **bir sütunun parçası** olmalı (sol kenarları hizalı en az
    iki örnek) ya da yakınında lejant başlığı ("LEJANT", "GÖSTERİM", "AÇIKLAMA") bulunmalı."""
    texts = sorted((e for e in drawing.entities if e.kind == "text" and e.text and e.points), key=lambda e: e.points[0][0])
    text_x = [t.points[0][0] for t in texts]
    cands: list[tuple[Entity, tuple[float, float, float, float], Entity]] = []
    for h in _hatches(drawing):
        xs = [p[0] for p in h.points]
        ys = [p[1] for p in h.points]
        w, ht = max(xs) - min(xs), max(ys) - min(ys)
        size = max(w, ht)
        if size <= 0 or size > SWATCH_MAX or size / max(min(w, ht), 1e-6) > SWATCH_MAX_ASPECT:
            continue
        x1, y0, y1 = max(xs), min(ys), max(ys)
        best, best_d = None, None
        lo, hi = x1 - 0.05 * size, x1 + TEXT_GAP_FACTOR * size + 1.0
        for k in range(bisect_left(text_x, lo), len(texts)):
            t = texts[k]
            tx, ty = t.points[0][0], t.points[0][1]
            if tx > hi:
                break
            dx = tx - x1
            if not (y0 - ht <= ty <= y1 + ht):
                continue
            if best_d is None or dx < best_d:
                best, best_d = t, dx
        if best is not None and material_of_text(best.text):
            cands.append((h, (min(xs), y0, x1, y1), best))
    if not cands:
        return [], []
    titles = [t.points[0] for t in texts if LEGEND_TITLE.search(normalize_title(t.text or ""))]
    rows: list[LegendRow] = []
    for h, (x0, y0, x1, y1), t in cands:
        in_column = sum(1 for _, b, _ in cands if abs(b[0] - x0) <= COLUMN_TOL) >= 2
        near_title = any(abs(px - x0) <= LEGEND_TITLE_REACH and -2.0 <= py - y1 <= LEGEND_TITLE_REACH for px, py in titles)
        if not (in_column or near_title):
            continue
        rows.append(LegendRow(pattern=h.pattern, material=material_of_text(t.text) or "",
                              text=re.sub(r"\s+", " ", t.text.replace(r"\P", " ")).strip()[:80]))
    # aynı desen iki farklı malzemeyle eşleşiyorsa lejant bu desen için kararsızdır: kullanılmaz
    by_pat: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        by_pat[r.pattern].add(r.material)
    warns = [f"Lejantta {p} deseni birden çok malzemeyle eşleşiyor ({', '.join(sorted(MATERIAL_NAMES.get(m, m) for m in ms))}); "
             f"bu desen lejanttan okunmadı." for p, ms in by_pat.items() if len(ms) > 1]
    rows = [r for r in rows if len(by_pat[r.pattern]) == 1]
    uniq: dict[str, LegendRow] = {}
    for r in rows:
        uniq.setdefault(r.pattern, r)
    return list(uniq.values()), warns


class HatchReader:
    """Bir çizimin taramalarını malzemeye çevirir; kaynağı (lejant / katman / desen) söyler."""

    def __init__(self, drawing: Drawing):
        self.legend, self.warnings = read_legend(drawing)
        self._legend = {r.pattern: r for r in self.legend}
        self.hatches = [(h, p) for h in _hatches(drawing) if (p := _poly(h)) is not None]
        self._tree = STRtree([p for _, p in self.hatches]) if self.hatches else None

    def material(self, h: Entity) -> tuple[str | None, str, str]:
        """(malzeme anahtarı, kaynak, açıklama). Kaynak: lejant | katman | desen | "" (bilinmiyor)."""
        row = self._legend.get(h.pattern)
        if row:
            return row.material, "lejant", f"tarama {h.pattern} → lejant: “{row.text}”"
        m = wall_material(h.layer) or material_of_text(h.layer)
        if m:
            return m, "katman", f"tarama katmanı “{h.layer}”"
        m = PATTERN_MATERIALS.get(h.pattern)
        if m:
            return m, "desen", f"tarama deseni {h.pattern} (standart anlamı)"
        return None, "", ""

    def covering(self, polygon: list, min_cover: float = WALL_COVER_MIN):
        """Çokgeni en az `min_cover` oranında örten ve malzemesi bilinen tarama: (malzeme, kaynak, açıklama) ya da None.

        Birden çok tarama örtüyorsa en çok örten kazanır; lejant kaynaklı olan eşitlikte öne geçer."""
        if self._tree is None or len(polygon) < 3:
            return None
        try:
            target = Polygon(polygon).buffer(0)
        except Exception:
            return None
        if target.is_empty or target.area <= 0:
            return None
        rank = {"lejant": 3, "katman": 2, "desen": 1}
        best, best_key = None, None
        for i in self._tree.query(target):
            h, p = self.hatches[int(i)]
            cover = p.intersection(target).area / target.area
            if cover < min_cover:
                continue
            mat, src, why = self.material(h)
            if not mat:
                continue
            key = (round(cover, 2), rank.get(src, 0))
            if best_key is None or key > best_key:
                best, best_key = (mat, src, why, cover), key
        return best

    def summary(self) -> dict:
        """Paftanın tarama özeti (Drawing.hatches): desen başına adet, alan ve tanınan malzeme."""
        rows: dict[str, dict] = {}
        for h, p in self.hatches:
            r = rows.setdefault(h.pattern, {"pattern": h.pattern, "count": 0, "area_m2": 0.0, "layers": {},
                                            "material": None, "source": "", "why": ""})
            r["count"] += 1
            r["area_m2"] += p.area
            r["layers"][h.layer] = r["layers"].get(h.layer, 0) + 1
            if not r["material"]:
                mat, src, why = self.material(h)
                if mat:
                    r["material"], r["source"], r["why"] = mat, src, why
        out = []
        for r in sorted(rows.values(), key=lambda r: -r["count"]):
            r["area_m2"] = round(r["area_m2"], 2)
            r["layers"] = [k for k, _ in sorted(r["layers"].items(), key=lambda kv: -kv[1])[:4]]
            r["material_name"] = MATERIAL_NAMES.get(r["material"] or "", "")
            out.append(r)
        return {"total": len(self.hatches), "patterns": out,
                "legend": [{"pattern": r.pattern, "material": r.material, "material_name": MATERIAL_NAMES.get(r.material, r.material),
                            "text": r.text} for r in self.legend],
                "recognized": sum(r["count"] for r in out if r["material"])}


def assign_wall_materials(reader: HatchReader, elements) -> int:
    """Malzemesi bilinmeyen duvarlara üstlerini örten taramanın malzemesini verir. Döner: atanan duvar sayısı.

    Yalnız duvar malzemesi olan anahtarlar atanır (toprak / çakıl bir duvarın malzemesi olamaz; öyle bir
    tarama duvarı örtüyorsa çizim başka bir şey anlatıyordur)."""
    n = 0
    for el in elements:
        if el.etype != "wall" or el.subtype:
            continue
        hit = reader.covering(el.points)
        if not hit:
            continue
        mat, src, why, cover = hit
        if mat not in WALL_MATERIALS:
            continue
        el.subtype = mat
        el.warnings = [w for w in el.warnings if not w.startswith("Duvar malzemesi bilinmiyor")]
        el.meta = {**(el.meta or {}), "material_source": f"tarama-{src}", "material_note": f"{why}; duvarın %{cover*100:.0f}'ini örtüyor"}
        n += 1
    return n

