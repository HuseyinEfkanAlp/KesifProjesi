"""Plandan donatı metrajı: **tabloya bakmadan**, çizimin kendisinden kilogram.

İki hesap var; ikisi de "metraj yapan mühendisin elle yaptığı" işi tekrarlar.

**1) Adetli çağrı × çizilen kol boyu** (`plan_bar_groups`) — döşeme, temel, ilave donatı.
Donatı planında her donatı grubu bir çağrı yazısıyla anlatılır ve çubuğun kendisi çizilir:

    çağrı   "21ƒ10/18"                 21 adet Ø10, 18 cm aralıkla
    çizgi   donatı katmanında 4,95 m   çubuğun boyu (kırık çubukta her kol ayrı çizgi)
    ağırlık = 21 × 4,95 m × 0,617 kg/m = 64,2 kg

Çubuk çizildiği için boy **ölçülür**, tahmin edilmez. A4-A5'in "X -YÖNÜ DONATI PLANI" paftasında bu hesap
55.834 kg veriyor; aynı paftanın müellif poz tablosu 55.862 kg diyor — **%0,05 fark**. Yani tablo olmadan da
aynı sayıya varıyoruz; tablo artık kaynak değil, doğrulama.

**2) Etriye** (`stirrup_weight`) — elemanın kesiti ve boyu biliniyorsa aralık yazısından hesaplanır:

    adet   = boy / aralık + 1
    çevre  = 2 × (b + h) − 8 × paspayı + 2 × kanca
    ağırlık = adet × çevre × birim ağırlık

Etriye yazısı her zaman elemana bağlanamaz (bazı ofisler yalnız kolon detay tablosuna yazar); bağlanamıyorsa
hesap yapılmaz ve sebebi bildirilir — uydurulmuş bir aralıkla sayı üretmek tablodan kopyalamaktan kötüdür.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .loader import Drawing, Entity

DIA_SYM = r"(?:[ØøΦφ∅ƒ]|%%[cC]|Q)"

# "21ƒ10/18", "4X7ƒ12/10" (çarpımlı adet), "24ƒ14/18"; aralıksız "20ƒ26" de kabul edilir (düz çubuk grubu)
CALLOUT = re.compile(
    rf"^\s*(?:(?P<mult>\d{{1,2}})\s*[xX×]\s*)?(?P<n>\d{{1,4}})\s*{DIA_SYM}\s*(?P<d>\d{{1,2}})"
    rf"(?:\s*/\s*(?P<s>\d{{1,3}}))?\s*$")
# "ƒ8/10", "Ø10/15" — adetsiz aralık yazısı (etriye ya da yayılı donatı tarifi)
SPACING_ONLY = re.compile(rf"{DIA_SYM}\s*(?P<d>\d{{1,2}})\s*/\s*(?P<s>\d{{1,3}})")
STIRRUP_WORD = re.compile(r"ETR|ET\.|ETR[İI]YE|STIRRUP", re.IGNORECASE)

REBAR_LAYER = re.compile(r"DONAT|REBAR|DEMIR|DEM[İI]R", re.IGNORECASE)
# Etiket / marka / poz katmanları çubuk taşımaz; yalnız yazı ve sembol vardır
NOT_BAR_LAYER = re.compile(r"MARKA|YAZI|TEXT|POZ|TAR[İI]F|GRUP|BENZER|AYRA[CÇ]|METRAJ|TABLO", re.IGNORECASE)

MIN_DIA, MAX_DIA = 6, 40
MIN_BAR_M = 0.50               # bundan kısa çizgi çubuk değil (kanca, detay, tarama parçası)
MAX_BAR_M = 20.0               # bundan uzun çizgi çubuk değil (aks, çerçeve, tarama çizgisi)
MAX_LINK_M = 3.0               # çubuk çağrısına bu mesafeden uzaksa o çağrıya ait değildir
COVER_M = 0.025                # paspayı (etriye çevresi için)
HOOK_M = 0.10                  # etriye kanca payı (bir uç); 2 × alınır
UNIT_TOL = 0.15                # yazılan boy / ölçülen boy bu kadar sapabilir; fazlası birim hatasıdır


def unit_weight(dia_mm: int) -> float:
    """kg/m (çelik 7850 kg/m³): π/4 · d² · 7850 = 0,006165 · d²."""
    return 0.006165 * dia_mm * dia_mm


@dataclass
class BarGroup:
    """Bir donatı çağrısı ve ona bağlanan çizili çubuk kolları."""
    adet: int
    dia_mm: int
    aralik_cm: int | None
    carpan: int
    kol_boyu_m: float                 # bir çubuğun toplam boyu (kırık çubukta kolların toplamı)
    kol_sayisi: int
    layer: str
    point: tuple[float, float]
    raw: str

    @property
    def toplam_boy_m(self) -> float:
        return self.adet * self.carpan * self.kol_boyu_m

    @property
    def agirlik_kg(self) -> float:
        return self.toplam_boy_m * unit_weight(self.dia_mm)

    def to_dict(self) -> dict:
        return {"adet": self.adet, "dia_mm": self.dia_mm, "aralik_cm": self.aralik_cm, "carpan": self.carpan,
                "kol_boyu_m": round(self.kol_boyu_m, 3), "kol_sayisi": self.kol_sayisi,
                "toplam_boy_m": round(self.toplam_boy_m, 2), "agirlik_kg": round(self.agirlik_kg, 2),
                "layer": self.layer, "raw": self.raw}


# Donatı boyu yazıları (VM Poz Kollar gibi): çubuğun boyu **cm** olarak yazılır. Çizilen çubuğun
# ölçülen boyu bu sayıyla tutmuyorsa çizim birimi yanlıştır — çizim kendi birimini böyle ele verir.
BAR_LEN_TEXT = re.compile(r"^\s*(\d{2,4})\s*$")


@dataclass
class UnitEvidence:
    """Donatı boyu yazılarının ima ettiği birim: ölçülen boy ile yazılan cm değeri karşılaştırılır."""
    oran: float                 # yazılan (m) / ölçülen (m); 1,0 ise birim doğru
    ornek: int
    onerilen_olcek: float | None = None      # mevcut ölçek bununla çarpılmalı


def suggested_unit(drawing: Drawing) -> str | None:
    """Donatı boyu yazılarının ima ettiği birim adı ("cm" / "mm" / "m"), çizimin birimi yanlışsa.

    Çizim kendi çubuk boylarını cm olarak yazar; ölçülen boy bunu vermiyorsa $INSUNITS yanılıyor demektir.
    Bu, yazı yüksekliği tahmininden **daha güçlü** bir kanıttır: tahmin değil, çizimin kendi beyanı."""
    from .loader import UNIT_SCALE
    k = unit_evidence(drawing)
    if not k or not k.onerilen_olcek:
        return None
    yeni = drawing.scale * k.onerilen_olcek
    for ad, sc in UNIT_SCALE.items():
        if abs(yeni - sc) < sc * 1e-6:
            return ad
    return None


def unit_evidence(drawing: Drawing, radius: float = 1.5) -> UnitEvidence | None:
    """Her boy yazısını en yakın çubuğa bağlar; yazılan cm ile ölçülen metreyi karşılaştırır."""
    segs = [(a, b, L) for a, b, L, _ in _bar_segments_raw(drawing)]
    if not segs:
        return None
    oranlar = []
    for e in drawing.texts():
        m = BAR_LEN_TEXT.match((e.text or "").strip())
        if not m or not e.points:
            continue
        yazilan = int(m.group(1)) / 100.0          # cm -> m
        if not (0.3 <= yazilan <= 20.0):
            continue
        p = e.points[0]
        yakin = [(L, _seg_distance(p, a, b)) for a, b, L in segs]
        yakin = [(L, d) for L, d in yakin if d <= radius]
        if not yakin:
            continue
        L = min(yakin, key=lambda x: x[1])[0]
        if L > 0:
            oranlar.append(yazilan / L)
    if len(oranlar) < 10:
        return None
    oranlar.sort()
    med = oranlar[len(oranlar) // 2]
    onerilen = None
    for kat in (10.0, 100.0, 0.1, 0.01):
        if abs(med - kat) / kat < 0.05:
            onerilen = kat
    return UnitEvidence(oran=med, ornek=len(oranlar), onerilen_olcek=onerilen)


@dataclass
class PlanRebarResult:
    groups: list[BarGroup] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    baglanmamis_cizgi: int = 0
    boysuz_cagri: int = 0

    @property
    def toplam_kg(self) -> float:
        return sum(g.agirlik_kg for g in self.groups)

    def by_dia(self) -> dict[int, float]:
        out: dict[int, float] = {}
        for g in self.groups:
            out[g.dia_mm] = out.get(g.dia_mm, 0.0) + g.agirlik_kg
        return out

    def to_dict(self) -> dict:
        return {"toplam_kg": round(self.toplam_kg, 2),
                "by_dia": {d: round(v, 2) for d, v in sorted(self.by_dia().items())},
                "grup_sayisi": len(self.groups), "boysuz_cagri": self.boysuz_cagri,
                "baglanmamis_cizgi": self.baglanmamis_cizgi, "warnings": self.warnings}


def _seg_distance(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def _bar_segments_raw(drawing: Drawing) -> list[tuple[tuple[float, float], tuple[float, float], float, str]]:
    """Donatı katmanlarındaki bütün parçalar (boy filtresi yok): birim kanıtı için ham liste."""
    out = []
    for e in drawing.entities:
        if e.kind not in ("line", "polyline", "polygon") or len(e.points) < 2:
            continue
        if not REBAR_LAYER.search(e.layer) or NOT_BAR_LAYER.search(e.layer):
            continue
        for a, b in zip(e.points, e.points[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L > 0:
                out.append((a, b, L, e.layer))
    return out


def _bar_segments(drawing: Drawing) -> list[tuple[tuple[float, float], tuple[float, float], float, str]]:
    """Çubuk sayılabilecek parçalar: çok kısa (kanca, detay) ve çok uzun (aks, çerçeve) olanlar elenir."""
    return [x for x in _bar_segments_raw(drawing) if MIN_BAR_M <= x[2] <= MAX_BAR_M]


def _callouts(drawing: Drawing) -> list[tuple[Entity, re.Match]]:
    out = []
    for e in drawing.texts():
        m = CALLOUT.match((e.text or "").strip())
        if not m or not e.points:
            continue
        d = int(m.group("d"))
        if MIN_DIA <= d <= MAX_DIA and int(m.group("n")) > 0:
            out.append((e, m))
    return out


def plan_bar_groups(drawing: Drawing, group_multiplier: bool = True) -> PlanRebarResult:
    """Adetli donatı çağrılarını çizili çubuk kollarıyla eşleştirip ağırlık üretir.

    Her çubuk parçası **en yakın çağrıya** bağlanır (çağrı çubuğun üstüne / yanına yazılır). MAX_LINK_M'den
    uzak parça hiçbir çağrıya bağlanmaz ve sayılmaz — sayılsaydı aks / çerçeve çizgileri demire dönüşürdü."""
    res = PlanRebarResult()
    cags = _callouts(drawing)
    if not cags:
        return res
    # Birim sağlaması: çizim çubuk boylarını cm olarak yazar; ölçülen boy bunu vermiyorsa hesap yapılmaz.
    # Yanlış birimle üretilen bir tonaj, hesap yapmamaktan çok daha zararlıdır.
    kanit = unit_evidence(drawing)
    if kanit and abs(kanit.oran - 1.0) > UNIT_TOL:
        oneri = (f" Birim {kanit.onerilen_olcek:g} kat yanlış görünüyor."
                 if kanit.onerilen_olcek else " Temiz bir kat sayısı çıkmadı; çizim birimini elle doğrulayın.")
        res.warnings.append(
            f"Çizim birimi '{drawing.unit}' ile donatı boyu yazıları çelişiyor: yazılan boylar ölçülen boyun "
            f"{kanit.oran:.3g} katı ({kanit.ornek} örnek).{oneri} Plandan donatı hesaplanmadı.")
        return res
    segs = _bar_segments(drawing)
    if not segs:
        res.warnings.append("Donatı çağrıları var ama donatı katmanında çizili çubuk bulunamadı; "
                            "çubuk boyu ölçülemediği için plandan ağırlık hesaplanamadı.")
        return res

    carpanlar = _group_multipliers(drawing) if group_multiplier else []
    kol_boy = [0.0] * len(cags)
    kol_say = [0] * len(cags)
    pts = [c[0].points[0] for c in cags]
    for a, b, L, _lay in segs:
        best_i, best_d = -1, MAX_LINK_M
        for i, p in enumerate(pts):
            d = _seg_distance(p, a, b)
            if d < best_d:
                best_i, best_d = i, d
        if best_i < 0:
            res.baglanmamis_cizgi += 1
            continue
        kol_boy[best_i] += L
        kol_say[best_i] += 1

    buyuk_carpan = 0
    for i, (e, m) in enumerate(cags):
        if kol_boy[i] <= 0:
            res.boysuz_cagri += 1
            continue
        mult = int(m.group("mult") or 1)
        carpan = mult * _nearest_multiplier(pts[i], carpanlar)
        if carpan > mult:
            buyuk_carpan += 1
        res.groups.append(BarGroup(
            adet=int(m.group("n")), dia_mm=int(m.group("d")),
            aralik_cm=int(m.group("s")) if m.group("s") else None, carpan=carpan,
            kol_boyu_m=kol_boy[i], kol_sayisi=kol_say[i], layer=e.layer, point=pts[i], raw=(e.text or "").strip()))

    if res.boysuz_cagri:
        res.warnings.append(f"{res.boysuz_cagri} donatı çağrısına çizili çubuk bağlanamadı (çubuk çizilmemiş ya da "
                            f"{MAX_LINK_M:g} m'den uzak); bu gruplar plandan hesaba girmedi.")
    if res.baglanmamis_cizgi:
        res.warnings.append(f"{res.baglanmamis_cizgi} donatı çizgisi hiçbir çağrıya bağlanamadı; adedi "
                            f"bilinmediği için sayılmadı (eksik kalabilir).")
    if buyuk_carpan:
        res.warnings.append(f"{buyuk_carpan} grupta 1'den büyük tekrar çarpanı bulundu. Bu yol gerçek bir "
                            f"referansla doğrulanmadı; çarpanları kontrol edin.")
    return res


def _group_multipliers(drawing: Drawing) -> list[tuple[tuple[float, float], int]]:
    """'Grup' / 'benzer' katmanındaki tam sayılar: aynı donatı grubunun kaç kez tekrarlandığı."""
    out = []
    for e in drawing.texts():
        if not re.search(r"GRUP|BENZER", e.layer, re.IGNORECASE) or not e.points:
            continue
        t = (e.text or "").strip()
        if t.isdigit() and 1 <= int(t) <= 99:
            out.append((e.points[0], int(t)))
    return out


def _nearest_multiplier(p: tuple[float, float], carpanlar: list, radius: float = 1.0) -> int:
    best, best_d = 1, radius
    for q, v in carpanlar:
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        if d < best_d:
            best, best_d = v, d
    return best


# ---------------------------------------------------------------- etriye

@dataclass
class StirrupSpec:
    dia_mm: int
    aralik_m: float
    raw: str


def find_stirrup_spec(drawing: Drawing, point: tuple[float, float] | None = None,
                      radius: float = 2.0) -> StirrupSpec | None:
    """Etriye aralığı yazısını bulur: önce noktanın yakınında, yoksa paftanın baskın etriye yazısı.

    Yalnız "ETR" geçen yazılar alınır; "ƒ12/15" tek başına döşeme donatısı da olabilir, etriye sanılmamalı."""
    adaylar = []
    for e in drawing.texts():
        t = (e.text or "").strip()
        if not STIRRUP_WORD.search(t):
            continue
        m = SPACING_ONLY.search(t)
        if not m:
            continue
        d, s = int(m.group("d")), int(m.group("s"))
        if not (MIN_DIA <= d <= MAX_DIA) or not (5 <= s <= 50):
            continue
        adaylar.append((e, StirrupSpec(d, s / 100.0, t)))
    if not adaylar:
        return None
    if point is not None:
        yakin = [(math.hypot(e.points[0][0] - point[0], e.points[0][1] - point[1]), sp)
                 for e, sp in adaylar if e.points]
        yakin = [x for x in yakin if x[0] <= radius]
        if yakin:
            return min(yakin, key=lambda x: x[0])[1]
    # baskın aralık: paftada en çok tekrar eden etriye tarifi
    say: dict[tuple[int, float], int] = {}
    for _e, sp in adaylar:
        say[(sp.dia_mm, sp.aralik_m)] = say.get((sp.dia_mm, sp.aralik_m), 0) + 1
    (d, s), _ = max(say.items(), key=lambda kv: kv[1])
    return StirrupSpec(d, s, f"paftanın baskın etriyesi Ø{d}/{s*100:.0f}")


def stirrup_weight(b: float, h: float, boy: float, spec: StirrupSpec,
                   cover: float = COVER_M, hook: float = HOOK_M) -> tuple[float, dict]:
    """Bir elemanın etriye ağırlığı (kg) ve hesabın dökümü.

    b, h: eleman kesiti (m). boy: etriyenin dizildiği uzunluk (kolonda kat yüksekliği, kirişte açıklık).
    çevre = 2 × (b + h) − 8 × paspayı + 2 × kanca   (köşelerde paspayı iki yönden düşülür)
    """
    if b <= 0 or h <= 0 or boy <= 0 or spec.aralik_m <= 0:
        return 0.0, {}
    adet = int(boy / spec.aralik_m) + 1
    cevre = 2.0 * (b + h) - 8.0 * cover + 2.0 * hook
    if cevre <= 0:
        return 0.0, {}
    kg = adet * cevre * unit_weight(spec.dia_mm)
    return kg, {"adet": adet, "cevre_m": round(cevre, 3), "aralik_m": spec.aralik_m,
                "dia_mm": spec.dia_mm, "boy_m": round(boy, 2), "kaynak": spec.raw}
