"""Kapsam sahipliği: bir kez okunan miktar ikinci paftadan tekrar okunmaz.

Aynı yapı bloğunun aynı katını gösteren iki pafta çoğu zaman birbirinin üstüne çizilir: zayıf akım
paftasının altlığında kablo tavası, donatı paftasının altlığında kalıp planı, kuvvet planının altlığında
mimari duvar vardır. İkisini de saymak miktarı ikiye katlar; ikinci paftayı toptan atmak ise o paftadaki
**gerçek eklemeyi** (yalnız zayıf akımda çizilen ek tava kolu) kaybettirir. İkisi de metrajı bozar.

Kural: **aynı nesne bir kez sayılır, ayrı nesne her zaman sayılır.** Aynılığın kanıtı konumdur — kırpılan
paftalar dünya koordinatını koruduğu için aynı katta aynı yere düşen aynı tipteki eleman aynı elemandır.
Katın kimliği de çizimden gelir: kot ("+7.95 KOTU KALIP PLANI") ya da plan adı ("2. KAT AYDINLATMA PLANI").
Konum kanıtı yoksa (iki dosya ayrı koordinat sisteminde çizilmiş) neyin ek olduğu **ölçülemez**: o zaman
yetkili paftanın ölçümü esas alınır, diğerinin miktarı fark olarak bildirilir ama uydurulmuş bir ek
üretilmez (bkz. kanıt sıralaması, services.storey_heights).

Yetki sırası (`authority`): kalemin sahibi, o kalemi ölçmek için çizilen pafta tipidir (tava -> elektrik
kablo tava planı, duvar -> mimari kat planı). Aynı yetkideki iki pafta birbirini asla elemez — ikisi de
gerçek ölçümdür (bir katın iki yarıya kırpılmış paftası gibi); yalnız katı bilinen ve aynı olan eşit
yetkili paftalarda üst üste çizilmiş nesne tekilleştirilir.

Hiçbir şey veritabanından silinmez: sahiplik her hesapta yeniden kurulur, `Resolution.dropped` yalnız o
hesapta toplanmayan eleman id'leridir ve düşen her miktar raporda görünür.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ..parser.layer_profile import ALL_ELEMENT_TYPES, TYPE_DISCIPLINE

# Aynı nesne sayılmak için: merkezler bu kadar yakın (m) ve büyüklükleri bu orandan fazla ayrışmayacak.
POS_TOL_M = 0.35            # taban tolerans: aynı prizin iki paftada birkaç santim kayması
POS_TOL_RATIO = 0.35        # elemanın kendi boyunun oranı (uzun tava kolunda tolerans da büyür)
QTY_RATIO = 1.6             # uzunluk / alan oranı bundan fazla ayrışıyorsa aynı nesne değildir
FRAME_OVERLAP = 0.20        # iki paftanın koordinat sistemi ortak sayılması için en küçük örtüşme oranı
GRID_M = 5.0                # konum indeksi hücre boyu


@dataclass
class ScopeElement:
    """Kapsam çözümlemesine giren eleman (DB Element ya da test nesnesi)."""
    id: int
    etype: str
    subtype: str | None = None
    points: Sequence[Sequence[float]] = ()
    length: float = 0.0
    area: float = 0.0
    count: int = 1
    manual: bool = False


@dataclass
class ScopeDrawing:
    id: int
    label: str
    elements: list[ScopeElement]
    block: str = ""
    # Kat kimliği: aynı katı gösteren paftalar aynı anahtarı taşır. Kanıt kottan ("+7.95") ya da plan adından
    # ("2. KAT AYDINLATMA PLANI") gelir — kullanıcıdan istenmez (bkz. services._floor_identity). None = katı
    # bilinmeyen pafta; o paftada hiçbir miktar düşürülmez.
    floor: str | None = None
    floor_label: str = ""       # kullanıcıya görünen ad: "+7.95" ya da "2. kat"
    plan_type: str = ""
    discipline: str = ""


@dataclass
class ScopeNote:
    """Bir paftanın bir kapsamdaki ölçümüne ne olduğu — düşen her miktar burada görünür."""
    kind: str                       # duplicate (sayılmadı) | addition (ek olarak sayıldı) | orphan (yetkili pafta yok)
    etype: str
    etype_label: str
    block: str
    kot: str | None
    drawing_id: int
    drawing: str
    owner_id: int | None = None
    owner: str = ""
    method: str = "geometri"        # geometri | miktar
    dropped_count: int = 0
    dropped_qty: float = 0.0
    added_count: int = 0
    added_qty: float = 0.0
    unit: str = ""
    severity: str = "info"          # info | review
    message: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Resolution:
    dropped: set[int] = field(default_factory=set)
    notes: list[ScopeNote] = field(default_factory=list)

    def keep(self, elements: Iterable[Any]) -> list[Any]:
        return [e for e in elements if e.id not in self.dropped]

    def to_dict(self) -> dict:
        return {"notes": [n.to_dict() for n in self.notes],
                "duplicate_count": sum(n.dropped_count for n in self.notes if n.kind == "duplicate"),
                "addition_count": sum(n.added_count for n in self.notes if n.kind == "addition")}


# ------------------------------------------------------------------ yetki

def authority(plan_type: str, discipline: str, etype: str) -> int:
    """Küçük olan daha yetkili: 0 = kalemi ölçmek için çizilen pafta, 3 = kalemle ilgisi olmayan pafta."""
    from ..planset import PLAN_TYPE_BY_CODE
    pt = PLAN_TYPE_BY_CODE.get(plan_type or "")
    if pt is not None and etype in pt.owns:
        return 0
    native = TYPE_DISCIPLINE.get(etype)
    if pt is not None and native and pt.discipline == native:
        return 1
    if native and discipline == native:
        return 2
    return 3


def _owner_types(etype: str) -> list[str]:
    from ..planset import PLAN_TYPES
    return [p.code for p in PLAN_TYPES if etype in p.owns]


# ------------------------------------------------------------------ geometri

def _bbox(pts) -> tuple[float, float, float, float] | None:
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _centroid(pts) -> tuple[float, float]:
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _diag(bb) -> float:
    return math.hypot(bb[2] - bb[0], bb[3] - bb[1])


def _qty(e: ScopeElement) -> tuple[float, str]:
    """Karşılaştırılacak miktar: uzunluk -> alan -> adet (birimiyle)."""
    n = max(int(e.count or 1), 1)
    if e.length:
        return float(e.length) * n, "m"
    if e.area:
        return float(e.area) * n, "m²"
    return float(n), "adet"


def _union_bbox(els: list[ScopeElement]):
    boxes = [b for b in (_bbox(e.points) for e in els) if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _pad(bb, ratio: float = 0.02, floor: float = 0.5):
    """Sınır kutusunu kendi boyunun oranı kadar genişletir: tek sıra hâlinde çizilmiş nesnelerin kutusu
    yassıdır (yükseklik 0) ve genişletilmeden hiçbir kutuyla kesişmez."""
    m = max(floor, ratio * _diag(bb))
    return (bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m)


def _frames_overlap(a: list[ScopeElement], b: list[ScopeElement]) -> bool:
    """İki paftanın nesneleri aynı koordinat sisteminde mi: sınır kutuları örtüşüyor mu."""
    ba, bb = _union_bbox(a), _union_bbox(b)
    if ba is None or bb is None:
        return False
    ba, bb = _pad(ba), _pad(bb)
    ix = max(0.0, min(ba[2], bb[2]) - max(ba[0], bb[0]))
    iy = max(0.0, min(ba[3], bb[3]) - max(ba[1], bb[1]))
    aa = max((ba[2] - ba[0]) * (ba[3] - ba[1]), 1e-9)
    ab = max((bb[2] - bb[0]) * (bb[3] - bb[1]), 1e-9)
    return (ix * iy) / min(aa, ab) >= FRAME_OVERLAP


def same_object(a: ScopeElement, b: ScopeElement) -> bool:
    """İki eleman aynı fiziksel nesne mi: aynı tip, aynı yer, yakın büyüklük."""
    if a.etype != b.etype:
        return False
    sa, sb = (a.subtype or ""), (b.subtype or "")
    if sa and sb and sa != sb:
        return False               # 200x60 tava ile 100x60 tava aynı nesne değildir
    ba, bb = _bbox(a.points), _bbox(b.points)
    if ba is None or bb is None:
        return False               # konum kanıtı yok: geometriyle karar verilmez
    ca, cb = _centroid(a.points), _centroid(b.points)
    if math.hypot(ca[0] - cb[0], ca[1] - cb[1]) > max(POS_TOL_M, POS_TOL_RATIO * max(_diag(ba), _diag(bb))):
        return False
    qa, ua = _qty(a)
    qb, ub = _qty(b)
    if ua == ub:
        lo, hi = min(qa, qb), max(qa, qb)
        return hi <= max(lo, 1e-9) * QTY_RATIO
    # Aynı nesne iki paftada farklı yoldan ölçülmüş olabilir (birinde uzunluk, öbüründe alan): miktarlar
    # karşılaştırılamaz, büyüklük sınır kutusundan karşılaştırılır. Kutusu da tutmuyorsa ayrı nesnedir.
    da, db = _diag(ba), _diag(bb)
    return max(da, db) <= max(min(da, db), 1e-9) * 1.3


def _shift(e: ScopeElement, off: tuple[float, float]) -> ScopeElement:
    if off == (0.0, 0.0):
        return e
    return ScopeElement(id=e.id, etype=e.etype, subtype=e.subtype, count=e.count, length=e.length, area=e.area,
                        manual=e.manual, points=[(p[0] + off[0], p[1] + off[1]) for p in e.points])


def _mean_centroid(els: list[ScopeElement]) -> tuple[float, float] | None:
    cs = [_centroid(e.points) for e in els if e.points]
    if not cs:
        return None
    return (sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs))


def _align(owner_els: list[ScopeElement], els: list[ScopeElement]) -> tuple[float, float] | None:
    """Aynı katın iki paftası ayrı orijinde çizilmişse ikisini örtüştüren ötelemeyi bulur — ve DOĞRULAR.

    Aday öteleme nesne merkezlerinden (ve sınır kutusu köşesinden) çıkar; ancak elemanların yarısından çoğu
    eşleşiyorsa kabul edilir. Doğrulanmayan öteleme kullanılmaz: yanlış hizalama gerçek miktarı sildirir."""
    cands: list[tuple[float, float]] = []
    ma, mb = _mean_centroid(owner_els), _mean_centroid(els)
    if ma and mb:
        cands.append((ma[0] - mb[0], ma[1] - mb[1]))
    ba, bb = _union_bbox(owner_els), _union_bbox(els)
    if ba and bb:
        cands.append((ba[0] - bb[0], ba[1] - bb[1]))
    best, best_hits = None, 0
    # Eşik yüksek tutulur: öteleme bir **çıkarımdır**, konum kanıtı kadar güçlü değildir. Zayıf bir
    # hizalama, ayrı bir yapı bloğunun gerçek ölçümünü kopya sanıp sildirebilir.
    need = max(3, int(0.7 * min(len(owner_els), len(els))))
    for off in cands:
        index = _Index()
        for e in owner_els:
            index.add(e)
        used: set[int] = set()
        hits = sum(1 for e in els if index.match(_shift(e, off), used) is not None)
        if hits > best_hits:
            best, best_hits = off, hits
    return best if best_hits >= need else None


class _Index:
    """Konum indeksi: elemanlar merkezlerine göre kovalanır."""

    def __init__(self):
        self.cells: dict[tuple[int, int], list[ScopeElement]] = defaultdict(list)

    def add(self, e: ScopeElement) -> None:
        if not e.points:
            return
        cx, cy = _centroid(e.points)
        self.cells[(int(cx // GRID_M), int(cy // GRID_M))].append(e)

    def match(self, e: ScopeElement, used: set[int] | None = None) -> ScopeElement | None:
        """Eşleşen nesneyi döndürür: uyan ilk nesne değil, **en yakını** (eşitlikte miktarı en yakın olan).

        İlk uyanı almak, birebir ikizi olan bir elemanın ikizini komşusuna kaptırmasına yol açar; ikiz sonra
        boşta kalıp "ek" sanılır. Gerçek paftada bu, aynı planın iki kez yüklenmesinde %1 fazla metraj demekti.

        `used`: bu paftada eşleşmiş sahip nesneleri — bir nesne tek bir kopyayı karşılar (sahipte bir tava
        varken bu paftada iki tane varsa ikincisi kopya değil ektir), ama havuzdan silinmez: üçüncü paftadaki
        kopya da aynı nesneyle eşleşebilmelidir."""
        if not e.points:
            return None
        cx, cy = _centroid(e.points)
        tol = max(POS_TOL_M, POS_TOL_RATIO * _diag(_bbox(e.points)))
        r = int(tol // GRID_M) + 1
        gx, gy = int(cx // GRID_M), int(cy // GRID_M)
        q = _qty(e)[0]
        best, best_key = None, None
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for cand in self.cells.get((gx + dx, gy + dy), ()):
                    if used is not None and cand.id in used:
                        continue
                    if not same_object(cand, e):
                        continue
                    cc = _centroid(cand.points)
                    key = (math.hypot(cc[0] - cx, cc[1] - cy), abs(_qty(cand)[0] - q))
                    if best_key is None or key < best_key:
                        best, best_key = cand, key
        if best is not None and used is not None:
            used.add(best.id)
        return best


# ------------------------------------------------------------------ çözümleme

def _n(v: float, d: int = 1) -> str:
    """Türkçe sayı: binlik nokta, ondalık virgül (1.234,5)."""
    return f"{v:,.{d}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _label(etype: str) -> str:
    return ALL_ELEMENT_TYPES.get(etype, etype)


def _blocks_compatible(a: str, b: str) -> bool:
    """"" = ortak / tüm bina: her blokla karşılaştırılır. İki ayrı blok birbirinin kopyası değildir."""
    return not a or not b or a == b


def resolve(drawings: Sequence[ScopeDrawing], skip_types: Iterable[str] = ("rebar",)) -> Resolution:
    """Paftaların ölçümlerini kapsam kapsam sahiplendirir: tekrar okunan nesne elenir, ek olan korunur."""
    res = Resolution()
    skip = set(skip_types)
    groups: dict[tuple[str | None, str], list[tuple[int, ScopeDrawing, list[ScopeElement]]]] = defaultdict(list)
    for d in drawings:
        by_type: dict[str, list[ScopeElement]] = defaultdict(list)
        for e in d.elements:
            if e.etype not in skip:
                by_type[e.etype].append(e)
        for etype, els in by_type.items():
            groups[(d.floor, etype)].append((authority(d.plan_type, d.discipline, etype), d, els))

    seen_types: set[str] = set()
    owned_types: set[str] = set()
    for (floor, etype), entries in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        seen_types.add(etype)
        entries.sort(key=lambda t: (t[0], -len(t[2]), t[1].id))
        if entries[0][0] == 0:
            owned_types.add(etype)
        if len(entries) < 2:
            continue
        owner_rank, owner_d, owner_els = entries[0]
        index = _Index()
        for e in owner_els:
            index.add(e)
        for rank, d, els in entries[1:]:
            if not _blocks_compatible(owner_d.block, d.block):
                continue
            equal = rank == owner_rank
            if equal and floor is None:
                continue     # eşit yetki, kot bilinmiyor: hangi kat olduğu ayırt edilemez, hiçbir şey elenmez
            offset: tuple[float, float] = (0.0, 0.0)
            if not _frames_overlap(owner_els, els):
                # Nesneler üst üste düşmüyor. Bu iki şey olabilir ve ikisi karıştırılamaz: (a) aynı dosyada yan
                # yana duran iki pafta — ayrı bölgeler, ayrı nesneler, hepsi sayılır; (b) aynı katın ayrı orijinde
                # çizilmiş ikinci paftası. Ayrımın tek kanıtı kottur: kot bilinmiyorsa hiçbir şey düşürülmez.
                if floor is None:
                    _unmatched_note(res, etype, floor, owner_d, owner_els, d, els, equal)
                    continue
                if equal:
                    continue     # eşit yetki, ayrı bölge: bir katın iki yarısı — ikisi de gerçek ölçümdür
                aligned = _align(owner_els, els)
                if aligned is None:
                    _unmatched_note(res, etype, floor, owner_d, owner_els, d, els, equal)
                    continue
                offset = aligned
            dropped: list[ScopeElement] = []
            used: set[int] = set()          # bu paftada eşleşen sahip nesneleri (her biri bir kez)
            dq, added, aq, unit = 0.0, 0, 0.0, ""
            for e in els:
                if e.manual:
                    index.add(_shift(e, offset))
                    continue     # kullanıcının kendi eklediği / düzelttiği eleman hiçbir zaman elenmez
                q, u = _qty(e)
                unit = unit or u
                if index.match(_shift(e, offset), used) is not None:
                    dropped.append(e)
                    dq += q
                else:
                    index.add(_shift(e, offset))
                    added += 1
                    aq += q
            if not dropped:
                continue
            res.dropped.update(e.id for e in dropped)
            msg = (f"{owner_d.label} paftasında ölçülen {_label(etype).lower()} bu paftada da çizili: "
                   f"{len(dropped)} nesne / {_n(dq)} {unit} ikinci kez sayılmadı")
            if added:
                msg += f"; {added} nesne / {_n(aq)} {unit} yalnız bu paftada olduğu için eklendi"
            if floor is None:
                msg += " (paftaların katı bilinmiyor: aynı kat varsayıldı)"
            elif offset != (0.0, 0.0):
                msg += f" (paftalar ayrı orijinde çizilmiş; {_n(offset[0])} / {_n(offset[1])} m ötelenip eşleştirildi)"
            res.notes.append(ScopeNote(kind="duplicate", etype=etype, etype_label=_label(etype), block=d.block,
                                       kot=d.floor_label or None, drawing_id=d.id, drawing=d.label, owner_id=owner_d.id,
                                       owner=owner_d.label, method="geometri", dropped_count=len(dropped),
                                       dropped_qty=round(dq, 3), added_count=added, added_qty=round(aq, 3),
                                       unit=unit, message=msg,
                                       # doğrudan konum kanıtı = bilgi; katı belirsiz ya da ötelenerek
                                       # eşleştirilmiş düşüm = çıkarım, kullanıcı görsün
                                       severity="info" if floor is not None and offset == (0.0, 0.0) else "review"))
            if added:
                res.notes.append(ScopeNote(kind="addition", etype=etype, etype_label=_label(etype), block=d.block,
                                           kot=d.floor_label or None, drawing_id=d.id, drawing=d.label, owner_id=owner_d.id,
                                           owner=owner_d.label, method="geometri", added_count=added,
                                           added_qty=round(aq, 3), unit=unit, severity="info",
                                           message=f"{d.label}: {added} nesne / {_n(aq)} {unit} {_label(etype).lower()} "
                                                   f"{owner_d.label} paftasında yok, ek olarak sayıldı"))

    _orphan_notes(res, seen_types - owned_types)
    return res


def _orphan_notes(res: Resolution, types: set[str]) -> None:
    """Yetkili paftası hiç yüklenmemiş kalem: sayı altlıktan geliyor, nereden geldiği söylenmeli."""
    from ..planset import PLAN_TYPE_BY_CODE
    for etype in sorted(types):
        codes = _owner_types(etype)
        if not codes:
            continue
        names = ", ".join(PLAN_TYPE_BY_CODE[c].label for c in codes)
        res.notes.append(ScopeNote(kind="orphan", etype=etype, etype_label=_label(etype), block="", kot=None,
                                   drawing_id=0, drawing="", severity="review",
                                   message=f"{_label(etype)} ölçüldü ama yetkili paftası yüklenmedi ({names}); "
                                           f"sayı altlıktan ya da başka disiplinin paftasından geliyor, düşük güven"))


def _unmatched_note(res: Resolution, etype: str, floor: str | None, owner_d: ScopeDrawing,
                    owner_els: list[ScopeElement], d: ScopeDrawing, els: list[ScopeElement], equal: bool) -> None:
    """Aynı kalem iki paftada var ama nesneler örtüşmüyor ve hizalanamıyor: **hiçbir şey düşürülmez.**

    Sessizce kaybolan miktar, çift sayımdan daha zararlıdır (bkz. README "Sessizce kaybolan miktar"): örtüşmeyen
    iki pafta aynı dosyada yan yana duran ayrı bölgeler de olabilir. Karar kullanıcınındır; ne yapması gerektiği
    söylenir (kat adını netleştirmek çoğu zaman yeter — kat bilinince paftalar ötelenip eşleştirilir)."""
    if equal and floor is not None:
        return      # eşit yetki, aynı kot, ayrı bölge: bir katın iki yarısı; ikisi de gerçek ölçümdür
    qo = sum(_qty(e)[0] for e in owner_els)
    qd, unit = 0.0, ""
    for e in els:
        q, u = _qty(e)
        unit = unit or u
        qd += q
    neden = ("iki paftanın katı bilinmiyor" if floor is None else "nesneler hizalanamadı")
    res.notes.append(ScopeNote(kind="unmatched", etype=etype, etype_label=_label(etype), block=d.block, kot=d.floor_label or None,
                               drawing_id=d.id, drawing=d.label, owner_id=owner_d.id, owner=owner_d.label,
                               method="miktar", dropped_count=0, dropped_qty=0.0, unit=unit, severity="review",
                               message=(f"{_label(etype)} iki paftada da ölçüldü ({owner_d.label}: {_n(qo)} {unit}, "
                                        f"{d.label}: {_n(qd)} {unit}) ama nesneler üst üste düşmüyor: {neden}. "
                                        f"İkisi de sayıldı — ayrı bölgelerse doğrudur, aynı yerin ikinci çizimiyse "
                                        f"çift sayımdır; paftaların kot / kat adını netleştirin ya da fazlasını metraj dışı bırakın")))
