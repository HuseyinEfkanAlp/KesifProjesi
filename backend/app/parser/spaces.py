"""Mahal tespiti: mimari plandaki duvarlardan kapalı alanlar, yazılardan adları.

Keşif "bina toplamı" değil **mahal bazında** çıkar: "Hol: 2 kamera, 4 priz, 8,2 m²". Bunun için önce
mahallerin sınırı gerekir; mimari planda mahal sınırı ayrı çizilmez, **duvarlar** çizilir:

1. Duvar (+ kolon / perde) katmanlarındaki çizgiler ağ olarak birleştirilir ve `polygonize` ile kapalı
   yüzler bulunur. Kapı boşlukları duvarda gedik bırakır ve yüz kapanmaz; bu yüzden sarkan uçlar
   `snap_tol` (varsayılan 1,2 m ~ kapı genişliği) içinde köprülenir (`detectors/base._bridge_gaps`).
2. Duvar gövdesine denk gelen ince dilimler elenir (alan / çevre oranı küçük olanlar).
3. Çizimde ayrıca **kapalı çizilmiş** polyline'lar (daire sınırı, bağımsız bölüm sınırı) aday alan sayılır;
   bunlar yüzleri kapsadığı için hiyerarşinin üst ucunu verir.
4. Yazılar alanlara dağıtılır: bir yazı kendisini içeren EN KÜÇÜK alanın adıdır. "LOBİ 45.20 m²" gibi
   alanlı yazılar mahal adı + beyan alanı verir; "DAİRE 1", "HOL" gibi yalın adlar da mahal adıdır.
5. Hiyerarşi kapsamadan kurulur: bir alan diğerini içeriyorsa üsttür (daire → mahal). `GROUP_WORDS`
   geçen ad (DAİRE, DÜKKAN, OFİS, BLOK…) bir GRUPtur; yalnız yaprak alana denk geldiyse ve üstünde
   adsız bir alan varsa ad üste taşınır (daire sınırı çizili, yazı içindeki odaya yazılmış hali).

Sonuç `drawing.spaces` alanında saklanır; eleman → mahal ataması `services.space_breakdown` içinde yapılır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point as SPoint, Polygon
from shapely.ops import polygonize, unary_union
import shapely

from .detectors.base import _bridge_gaps
from .loader import Drawing, Point
from .schedules import parse_room_area

# Bir GRUP (bağımsız bölüm) adı: içindeki odalar onun mahalleridir.
GROUP_WORDS = re.compile(r"DA[İI]RE|D[AÜU]KKAN|MA[GĞ]AZA|OF[İI]S|B[ÜU]RO|BLOK|V[İI]LLA|BA[GĞ]IMSIZ\s*B[ÖO]L[ÜU]M"
                         r"|[İI][SŞ]\s*YER[İI]|KAT\s*\d|UN[İI]TE|[ÜU]N[İI]TE", re.IGNORECASE)
# Mahal adı sayılmayan yazılar: kotlar, poz / eleman adları, ölçüler, pafta işaretleri.
_NOT_NAME = re.compile(r"^[+\-±]?\d[\d.,/xX*\s-]*$|^[SKPDTM]\d+([./]\d+)?$|KES[İI]T|DETAY|PLAN\b|[ÖO]L[ÇC]EK|KOT"
                       r"|^\d+[.,]\d+$|^[A-Z]$", re.IGNORECASE)
MIN_SPACE_AREA = 1.0        # m² — bundan küçük yüz mahal sayılmaz
AREA_TOLERANCE_PCT = 12.0   # ölçülen çokgen ile yazıdaki alan arasında kabul edilen azami fark (%)
MIN_NAMELESS_AREA = 4.0     # m² — adı olmayan bu kadar büyük alan "adı yazılmamış mahal" diye bildirilir
MIN_WIDTH = 0.45            # m — alan/çevre oranı bundan küçükse duvar dilimi, mahal değil
DOOR_GAP = 1.2              # m — kapı boşluğu köprüleme toleransı
MAX_NAME = 40


@dataclass
class Space:
    index: int
    name: str
    kind: str                       # "mahal" | "grup"
    points: list[Point]
    area: float                     # çizimden ölçülen alan (m²)
    label_area: float = 0.0         # yazıda beyan edilen alan (m²)
    parent: int | None = None
    evidence: str = ""
    code: str = ""                  # mahal kodu (L_Z_01) — projenin mahal listesindeki kimlik
    children: list[int] = field(default_factory=list)
    # Alan nereden: "drawing" çokgen ölçüldü ve yazıyla tutuyor, "label" yalnız yazıdan (çokgen yok /
    # tutmadı), "polygon" çokgen var ama yazıda alan yok. Karşılaştırma yapılabilen yerde fark yüzde olarak durur.
    area_source: str = "polygon"
    diff_pct: float = 0.0

    def to_dict(self) -> dict:
        return {"index": self.index, "name": self.name, "kind": self.kind, "area": round(self.area, 2),
                "label_area": round(self.label_area, 2), "parent": self.parent, "evidence": self.evidence,
                "code": self.code, "area_source": self.area_source, "diff_pct": round(self.diff_pct, 1),
                "children": list(self.children), "points": [[round(x, 3), round(y, 3)] for x, y in self.points]}


def _is_name(text: str) -> bool:
    t = (text or "").replace("\\P", " ").strip()
    return bool(t) and len(t) <= MAX_NAME and not _NOT_NAME.match(t)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\\P", " ")).strip(" -:·")


def _faces(drawing: Drawing, layers: list[str], snap_tol: float) -> list[Polygon]:
    """Duvar ağından kapalı yüzler + çizimde zaten kapalı çizilmiş çokgenler."""
    segs: list[LineString] = []
    closed: list[Polygon] = []
    for e in drawing.entities:
        if e.layer not in layers or len(e.points) < 2:
            continue
        if e.is_closed_polygon:
            try:
                p = Polygon(e.points)
                if p.is_valid and p.area >= MIN_SPACE_AREA:
                    closed.append(p)
            except Exception:
                pass
        if e.kind in ("line", "polyline", "polygon"):
            pts = list(e.points) + ([e.points[0]] if e.closed else [])
            for i in range(len(pts) - 1):
                if pts[i] != pts[i + 1]:
                    segs.append(LineString([pts[i], pts[i + 1]]))
    out: list[Polygon] = []
    if segs and len(segs) < 20000:
        try:
            merged = shapely.set_precision(unary_union(segs + _bridge_gaps(segs, snap_tol)), 0.001)
            for poly in polygonize(merged):
                if poly.area < MIN_SPACE_AREA or poly.area / max(poly.length, 1e-9) < MIN_WIDTH / 2:
                    continue        # duvar gövdesine denk gelen ince dilim
                out.append(poly)
        except Exception:
            pass
    for p in closed:
        if not any(p.equals(q) for q in out):
            out.append(p)
    return out


# Mahal kodu: "L_Z_01", "L_CK_M02", "A-101" gibi. Gerçek projelerde mahal etiketi ÜÇ ayrı yazıdır:
#     RESTORAN          <- ad
#     L_Z_01 : 309.49 m²  <- kod ve alan (ayrı TEXT nesneleri, aralarında ":" bile ayrı olabilir)
# Bu yüzden yakın yazılar tek etikette birleştirilir.
_CODE = re.compile(r"^[A-Z]{1,3}[_\-][A-Z0-9]{1,4}([_\-][A-Z]?\d{1,3}[A-Z]?)?$")
_PUNCT = re.compile(r"^[:;.\-–/]+$")
LABEL_REACH = 2.0           # m — ad / kod / alan yazılarının birbirine azami uzaklığı
LABEL_REACH_H = 10.0        # × yazı yüksekliği (küçük ölçekli paftada yazı küçük, aralık da küçüktür)


@dataclass
class Label:
    name: str
    area: float                 # yazıda beyan edilen alan (m²)
    pt: SPoint
    raw: str
    code: str = ""              # mahal kodu (L_Z_01)


def _labels(drawing: Drawing) -> list[Label]:
    """Mahal etiketleri. Ad, kod ve alan ayrı yazılarsa yakınlıktan birleştirilir."""
    areas: list[Label] = []     # içinde m² geçen yazılar
    names: list[tuple[str, SPoint, str]] = []
    codes: list[tuple[str, SPoint]] = []
    for e in drawing.entities:
        if e.kind != "text" or not e.text or not e.points:
            continue
        raw = _clean(e.text)
        pt = SPoint(e.points[0][:2])
        h = float(e.height or 0.0)
        r = parse_room_area(e.text)
        if r:
            # "MAHAL" = adı olmayan yalın alan yazısı ("309.49 m²"): adı komşu yazıdan gelecek
            areas.append(Label("" if r.name == "MAHAL" else r.name, r.area_m2, pt, raw))
            setattr(areas[-1], "_h", h)
            continue
        if _CODE.match(raw.upper()):
            codes.append((raw.upper(), pt))
            continue
        if _PUNCT.match(raw):
            continue
        if _is_name(raw):
            names.append((raw.upper(), pt, raw))
    used: set[int] = set()
    for lab in areas:
        reach = max(LABEL_REACH, LABEL_REACH_H * getattr(lab, "_h", 0.0))
        if not lab.name:
            cand = sorted(((lab.pt.distance(p), i) for i, (_n, p, _r) in enumerate(names) if i not in used
                           and lab.pt.distance(p) <= reach))
            if cand:
                d, i = cand[0]
                used.add(i)
                lab.name, lab.raw = names[i][0], f"{names[i][2]} {lab.raw}"
        near_code = sorted(((lab.pt.distance(p), c) for c, p in codes if lab.pt.distance(p) <= reach))
        if near_code:
            lab.code = near_code[0][1]
    out = [lab for lab in areas if lab.name]
    # adı eşleşmeyen yalın adlar (alansız mahal / bağımsız bölüm yazısı) da etiket sayılır
    out += [Label(n, 0.0, p, r) for i, (n, p, r) in enumerate(names) if i not in used]
    return out


def has_space_labels(drawing: Drawing) -> bool:
    """Bu paftada mahal aramaya değer mi: en az bir mahal alanı yazısı ("HOL 32 m²") ya da
    bağımsız bölüm adı ("DAİRE 1") olmalı. Kalıp / donatı paftasında boşuna çokgen aramayız."""
    for lab in _labels(drawing):
        if lab.area > 0 or GROUP_WORDS.search(lab.name):
            return True
    return False


def detect_spaces(drawing: Drawing, layers: list[str], snap_tol: float = DOOR_GAP) -> tuple[list[Space], list[str]]:
    """Mahalleri ve aralarındaki daire / mahal hiyerarşisini çıkarır. Döner: mahaller, uyarılar."""
    warnings: list[str] = []
    faces = _faces(drawing, layers, snap_tol)
    if not faces:
        return [], []
    faces.sort(key=lambda p: -p.area)
    spaces = [Space(index=i, name="", kind="mahal", points=[(x, y) for x, y in p.exterior.coords[:-1]], area=p.area)
              for i, p in enumerate(faces)]
    # 1) hiyerarşi: bir alanı içeren en küçük alan onun üstüdür
    for i, p in enumerate(faces):
        best, best_area = None, None
        for j, q in enumerate(faces):
            if i == j or q.area <= p.area:
                continue
            if q.contains(p.representative_point()) and (best_area is None or q.area < best_area):
                best, best_area = j, q.area
        spaces[i].parent = best
        if best is not None:
            spaces[best].children.append(i)
    # 2) yazılar: her yazı kendisini içeren EN KÜÇÜK alanın adı olur
    for lab in _labels(drawing):
        name, label_area, pt, raw = lab.name, lab.area, lab.pt, lab.raw
        hit, hit_area = None, None
        for i, p in enumerate(faces):
            if p.contains(pt) and (hit_area is None or p.area < hit_area):
                hit, hit_area = i, p.area
        if hit is None:
            continue
        sp = spaces[hit]
        group = bool(GROUP_WORDS.search(name))
        # daire sınırı çizili ama yazı içindeki odaya yazılmış: adı adsız üst alana taşı
        if group and not sp.children and sp.parent is not None and not spaces[sp.parent].name:
            sp = spaces[sp.parent]
        if sp.name and not group:
            continue                       # alanın adı var: ilk yazı geçerli (grup adı üste yazabilir)
        sp.name = name
        sp.kind = "grup" if group else sp.kind
        sp.evidence = raw
        sp.code = lab.code or sp.code
        if label_area > 0:
            sp.label_area = label_area
    # 3) grup: çocuğu olan adlı alan da gruptur (daire içindeki odalar)
    for sp in spaces:
        if sp.name and sp.children and any(spaces[c].name for c in sp.children):
            sp.kind = "grup"
    # Çokgeni yazıdaki alanla DOĞRULA: mimari plan mahalin alanını zaten yazıyor, bu bizim ölçtüğümüzün
    # denetimidir. Tutmuyorsa çokgen atılır (duvar ağı kapanmamış, komşu mahalle taşmış demektir) ve
    # mahal yazıdaki alanıyla listede kalır — mahal listesi eksilmez.
    for sp in spaces:
        if not sp.name:
            continue
        if sp.label_area > 0 and sp.area > 0:
            sp.diff_pct = abs(sp.area - sp.label_area) / sp.label_area * 100.0
            if sp.diff_pct <= AREA_TOLERANCE_PCT:
                sp.area_source = "drawing"
            else:
                sp.area, sp.area_source, sp.points = sp.label_area, "label", []
        elif sp.label_area > 0:
            sp.area, sp.area_source = sp.label_area, "label"
    # hiçbir çokgene düşmemiş etiketler de mahaldir (çokgensiz): liste projedeki mahal listesiyle aynı olmalı
    def same(a: float, b: float) -> bool:
        return abs(a - b) <= max(0.05, 0.01 * max(a, b))     # aynı mahal iki kez yazılmış olabilir

    def dup(n1: str, a1: float, c1: str, n2: str, a2: float, c2: str) -> bool:
        """Aynı mahalin ikinci yazısı mı? Kodları farklıysa AYRI mahaldir (aynı alanlı iki merdiven gibi)."""
        return n1 == n2 and same(a1, a2) and (not c1 or not c2 or c1 == c2)

    placed = [(sp.name, sp.label_area, sp.code) for sp in spaces if sp.name]
    nxt = len(spaces)
    for lab in _labels(drawing):
        if not lab.name or lab.area <= 0 or any(dup(n, a, c, lab.name, lab.area, lab.code) for n, a, c in placed):
            continue
        placed.append((lab.name, lab.area, lab.code))
        spaces.append(Space(index=nxt, name=lab.name, kind="grup" if GROUP_WORDS.search(lab.name) else "mahal",
                            points=[], area=lab.area, label_area=lab.area, evidence=lab.raw, code=lab.code,
                            area_source="label"))
        nxt += 1
    seen_named: list[tuple[str, float, str]] = []
    for sp in sorted([x for x in spaces if x.name], key=lambda x: (not x.code, x.area_source != "drawing", -x.area)):
        if sp.label_area > 0 and any(dup(n, a, c, sp.name, sp.label_area, sp.code) for n, a, c in seen_named):
            sp.name = ""                      # aynı mahalin ikinci yazısı: tek satır kalsın
            continue
        seen_named.append((sp.name, sp.label_area, sp.code))
    named = [s for s in spaces if s.name]
    if not named:
        return [], [f"Mahal sınırı bulundu ({len(spaces)} kapalı alan) ama hiçbirinin içinde mahal adı yazmıyor: "
                    "mahaller adlandırılamadı."]
    def has_named_desc(sp: Space, guard: int = 0) -> bool:
        return guard < 8 and any(spaces[c].name or has_named_desc(spaces[c], guard + 1)
                                 for c in sp.children if c < len(spaces))

    unnamed = [s for s in spaces if not s.name and not has_named_desc(s) and s.area >= MIN_NAMELESS_AREA]
    # Adı olmayan yüz mahal değildir: listeye girmez. Çocukları en yakın ADLI üste bağlanır.
    def named_ancestor(sp: Space, guard: int = 0) -> int | None:
        if sp.parent is None or sp.parent >= len(spaces) or guard > 8:
            return None
        up = spaces[sp.parent]
        return up.index if up.name else named_ancestor(up, guard + 1)

    for sp in spaces:
        sp.parent = named_ancestor(sp)
    keep = {sp.index for sp in spaces if sp.name}
    for sp in spaces:
        sp.children = [c for c in sp.children if c in keep]
    out = [s for s in spaces if s.name]
    groups = [s for s in out if s.kind == "grup"]
    ver = len([s for s in out if s.area_source == "drawing"])
    lab_only = len([s for s in out if s.area_source == "label"])
    warnings.append(f"Mahal okundu: {len([s for s in out if s.kind == 'mahal'])} mahal"
                    + f" ({ver} tanesinin sınırı çizimden ölçüldü ve yazıdaki alanla tutuyor"
                    + (f", {lab_only} tanesi yalnız mahal yazısından" if lab_only else "") + ")"
                    + (f", {len(groups)} bağımsız bölüm ({', '.join(g.name for g in groups[:4])}…)" if groups else "")
                    + f"; toplam {sum(s.area for s in out if s.kind == 'mahal'):,.0f} m².")
    if unnamed:
        warnings.append(f"{len(unnamed)} kapalı alanın ({sum(s.area for s in unnamed):,.0f} m²) içinde mahal adı yok; "
                        "mahal listesine girmedi — adı yazılmamış ya da duvarı kapanmamış olabilir.")
    return out, warnings


def space_of(spaces: list[dict], pt: tuple[float, float]) -> dict | None:
    """Bir noktanın düştüğü EN KÜÇÜK mahal (grup değil mahal; yoksa grup)."""
    hit = None
    for s in spaces:
        if len(s.get("points") or []) < 3:
            continue
        try:
            if Polygon(s["points"]).contains(SPoint(pt)):
                if hit is None or s["area"] < hit["area"]:
                    hit = s
        except Exception:
            continue
    return hit
