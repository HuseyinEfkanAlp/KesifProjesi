"""Kendini doğrulayan ve **yanlışlayan** kontroller: sonucu ikinci bir yoldan sınar.

`quality.py` "ne eksik" diye sorar (pafta okunmadı mı, katman eşleşti mi). Bu modül başka bir şey sorar:
**ürettiğimiz sayı kendi içinde tutarlı mı?** Aynı büyüklüğe iki bağımsız yoldan bakar ve ikisini çarpıştırır.

Tek kural her şeyi belirler: **dairesel kontrol hiçbir şey kanıtlamaz.** Demiri "beton × 140" ile bulup sonra
"demir/beton 140 çıktı, demek doğru" demek bir doğrulama değil, aynı sayıyı iki kez yazmaktır. Böyle bir
kontrol asla `destekliyor` demez; `kararsiz` der ve sebebini yazar. Bir kontrolün değeri, girdilerinin
birbirinden bağımsız olmasından gelir:

    demir  ← donatı tablosu / poz yazısı   (çizimdeki yazılar)
    beton  ← eleman geometrisi × yükseklik  (çizimdeki çizgiler)

İkisi birbirini hiç görmez; oranları fizik ve yönetmelikle sınırlıdır. Bu yüzden oran bandı dışına çıkmak
**gerçek bir çelişkidir** ve hangisinin yanlış olduğunu aramak gerekir.

Sonuç üç değerlidir — "doğru" yoktur:
    destekliyor  bağımsız ikinci kanıt aynı şeyi söylüyor
    celisiyor    bağımsız ikinci kanıt aksini söylüyor (aranacak bir hata var)
    kararsiz     kontrol yapılamadı ya da dairesel olurdu
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

# Donatı oranı bandı (kg/m³). Üst sınırlar yönetmelik donatı oranından türer, "yaygın uygulama"dan değil:
# çelik yoğunluğu 7850 kg/m³ olduğu için ρ = %1 ≈ 78,5 kg/m³.
#   kolon    TS500 / TBDY boyuna ρ ≤ %4 -> 314 kg/m³, + etriye payı ≈ 400 üst sınır; ρ ≥ %1 -> ~100 alt sınır
#   perde    ρ gövdede düşük, uç bölgelerde yüksek; pratik aralık
#   kiriş    boyuna ρ ≈ %0,3–2,5 + etriye
#   döşeme   ρ ≈ %0,2–1,5 (çift kat hasır dahil)
#   temel    radyede ρ düşüktür; A4-A5'te ölçülen 97, B Blok'ta benzer
# Bant dışı bir değer "yanlış" demek değildir; "bu iki bağımsız sayı birlikte duramaz" demektir.
REBAR_RATIO_BAND: dict[str, tuple[float, float]] = {
    "column": (100.0, 400.0),
    "shear_wall": (60.0, 300.0),
    "beam": (60.0, 280.0),
    "slab": (30.0, 150.0),
    "foundation": (40.0, 140.0),
    "parapet": (40.0, 200.0),
}

# Kalıp / beton oranı (m²/m³). Geometrinin kendisinden gelir, kabulden değil:
#   döşeme    kalıp = alan, beton = alan × t  ->  oran = 1/t  (t = 8..40 cm -> 2,5..12,5)
#   kolon     çevre × Hf / (alan × Hk); 30x30'dan 100x100'e ~3..13
#   kiriş     (b + 2h) × L / (b × h × L); dar-yüksek kirişte büyür
FORMWORK_RATIO_BAND: dict[str, tuple[float, float]] = {
    "column": (2.0, 15.0),
    "shear_wall": (2.0, 20.0),
    "beam": (2.0, 14.0),
    "slab": (2.5, 12.5),
    "parapet": (2.0, 25.0),
}

SLAB_THICKNESS_BAND = (0.07, 0.45)      # m; bunun dışındaki "türetilmiş kalınlık" ölçü hatasıdır


@dataclass
class Check:
    kod: str
    ad: str
    kapsam: str
    sonuc: str                     # destekliyor | celisiyor | kararsiz
    aciklama: str
    olculen: float | None = None
    beklenen: str = ""
    bagimsizlik: str = ""          # bu kontrolü dairesel olmaktan çıkaran şey

    def to_dict(self) -> dict:
        return {"kod": self.kod, "ad": self.ad, "kapsam": self.kapsam, "sonuc": self.sonuc,
                "aciklama": self.aciklama, "olculen": None if self.olculen is None else round(self.olculen, 3),
                "beklenen": self.beklenen, "bagimsizlik": self.bagimsizlik}


@dataclass
class SelfCheckReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def celisen(self) -> list[Check]:
        return [c for c in self.checks if c.sonuc == "celisiyor"]

    @property
    def destekleyen(self) -> list[Check]:
        return [c for c in self.checks if c.sonuc == "destekliyor"]

    @property
    def kararsiz(self) -> list[Check]:
        return [c for c in self.checks if c.sonuc == "kararsiz"]

    def to_dict(self) -> dict:
        n_d, n_c, n_k = len(self.destekleyen), len(self.celisen), len(self.kararsiz)
        return {
            "checks": [c.to_dict() for c in self.checks],
            "destekleyen": n_d, "celisen": n_c, "kararsiz": n_k,
            "ozet": _ozet(n_d, n_c, n_k),
            "notice": "Bu kontroller sonucu ikinci bir yoldan sınar. Hepsinin desteklemesi sonucun doğru "
                      "olduğunu kanıtlamaz; yalnız bilinen çelişkilerin bulunmadığını gösterir.",
        }


def _ozet(d: int, c: int, k: int) -> str:
    if c:
        return f"{c} bağımsız kontrol sonuçla çelişiyor; önce onlar açıklanmalı."
    if d:
        return f"{d} bağımsız kontrol sonucu destekliyor, çelişen yok ({k} kontrol karar veremedi)."
    return "Bağımsız kontrol yapılamadı; sonucu sınayacak ikinci kanıt yok."


def _band(v: float, band: tuple[float, float]) -> bool:
    return band[0] <= v <= band[1]


# Mahal çokgeninin ölçülen alanı ile mahal yazısındaki alan arasında kabul edilen azami fark (%).
# `parser/spaces.AREA_TOLERANCE_PCT` (12) sınırın KABUL eşiğidir: üzerindeki mahal zaten ölçülmemiş
# sayılır. Burada sorulan başka bir şey: kabul edilmiş mahallerin içinde de sistematik bir kayma
# var mı (ölçek hatası, yanlış birim, duvar ekseni / iç yüz karışıklığı).
SPACE_AREA_TOL_PCT = 8.0
# Mahallerin toplamı bina dış hattının bu oranını geçemez: duvar, şaft ve kolon payları düşülür.
SPACES_IN_FOOTPRINT_MAX = 1.02
# Antetteki inşaat alanı ile ölçülen kat alanları toplamı arasında kabul edilen fark (%).
# Antet brüt alanı anlatır, ölçülen mahal toplamı nettir; aradaki fark doğal olarak büyüktür.
TITLEBLOCK_AREA_TOL_PCT = 35.0


def build(summary: dict, elements=None, rebar_mix: dict | None = None,
          spaces: list[dict] | None = None, footprints: list[dict] | None = None,
          titleblock: dict | None = None) -> SelfCheckReport:
    """summary: quantity/summary.py çıktısı. elements: proje elemanları (birim sağlaması için).

    spaces / footprints / titleblock verilirse **mekânsal** kontroller de yapılır: aynı büyüklüğe
    birbirini hiç görmeyen iki kaynaktan bakılır (mimarın yazdığı alan ↔ bizim ölçtüğümüz çokgen)."""
    r = SelfCheckReport()
    _rebar_ratio(r, summary)
    _slab_thickness(r, summary)
    _formwork_ratio(r, summary)
    _diameters(r, summary, rebar_mix or {})
    _floor_consistency(r, summary)
    _arithmetic(r, summary)
    _space_areas(r, spaces or [])
    _spaces_in_footprint(r, spaces or [], footprints or [])
    _titleblock_area(r, footprints or [], titleblock or {})
    return r


def _space_areas(r: SelfCheckReport, spaces: list[dict]) -> None:
    """Ölçtüğümüz mahal çokgeni ↔ mimarın mahal yazısına yazdığı alan.

    **Bağımsızlık buradan gelir:** yazıdaki alanı mimar kendi hesabıyla yazmış, biz çizgilerden
    ölçtük. İkisi birbirini hiç görmez. Tek tek küçük farklar normaldir (duvar ekseni / iç yüz);
    ama fark **sistematikse** ortada bir ölçek ya da birim hatası vardır ve bütün metrajı kaydırır."""
    esli = [sp for sp in spaces
            if float(sp.get("label_area") or 0) > 0 and sp.get("area_source") == "drawing"]
    if len(esli) < 3:
        r.checks.append(Check("mahal_alani", "Mahal alanı", "mahaller", "kararsiz",
                              "Yazısında alanı olan ve sınırı ölçülen mahal sayısı karşılaştırma için yetersiz.",
                              bagimsizlik="mimarın yazdığı alan ↔ çizgilerden ölçülen çokgen"))
        return
    farklar = [(float(sp["area"]) - float(sp["label_area"])) / float(sp["label_area"]) * 100.0 for sp in esli]
    ort = median(farklar)
    sapan = [sp for sp, f in zip(esli, farklar) if abs(f) > SPACE_AREA_TOL_PCT]
    if abs(ort) > SPACE_AREA_TOL_PCT:
        yon = "büyük" if ort > 0 else "küçük"
        r.checks.append(Check(
            "mahal_alani", "Mahal alanı", f"{len(esli)} mahal", "celisiyor",
            f"Ölçtüğümüz alanlar mimarın yazdığı alanlardan sistematik olarak %{abs(ort):.0f} {yon}. "
            "Tek tek sapma değil, bütününe yayılan bir kayma: ölçek ya da birim hatası olabilir; "
            "böyleyse kaplama, şap ve tavan metrajı aynı oranda yanlıştır.",
            olculen=ort, beklenen=f"±%{SPACE_AREA_TOL_PCT:g} medyan fark",
            bagimsizlik="mimarın yazdığı alan ↔ çizgilerden ölçülen çokgen"))
        return
    ad = ", ".join(f"{sp.get('name') or '?'} ({sp['area']:,.0f} / {sp['label_area']:,.0f} m²)"
                   for sp in sapan[:4]).replace(",", ".")
    r.checks.append(Check(
        "mahal_alani", "Mahal alanı", f"{len(esli)} mahal", "destekliyor",
        f"Ölçülen alanlar yazıdaki alanlarla örtüşüyor (medyan fark %{ort:+.1f})."
        + (f" {len(sapan)} mahalde tek tek sapma var: {ad}." if sapan else ""),
        olculen=ort, beklenen=f"±%{SPACE_AREA_TOL_PCT:g} medyan fark",
        bagimsizlik="mimarın yazdığı alan ↔ çizgilerden ölçülen çokgen"))


def _spaces_in_footprint(r: SelfCheckReport, spaces: list[dict], footprints: list[dict]) -> None:
    """Bir katın mahalleri o katın dış hattının içine sığmalı.

    Mahaller iç yüzlerden, dış hat kabuktan ölçülür; mahal toplamı dış hattı GEÇİYORSA
    geometrilerden biri yanlış yerdedir (yanlış kat eşlemesi, ikinci kopyanın karışması)."""
    by_dwg: dict[int, float] = {}
    for sp in spaces:
        if sp.get("kind") == "grup" or sp.get("parent") is not None:
            continue            # grup ve iç içe mahal iki kez sayılmasın
        by_dwg[sp.get("drawing_id")] = by_dwg.get(sp.get("drawing_id"), 0.0) + float(sp.get("area") or 0)
    # **Dairesellik yasağı:** dış hat mahal sınırlarından türetilmişse (services._plan_footprints
    # önce mahalleri kullanır) bu karşılaştırma aynı sayıya iki kez bakmaktır ve hiçbir şey
    # kanıtlamaz — üstelik mahalleri kopuk olan bir katta (ayrık teras) sahte çelişki üretir.
    # Yalnız taşıyıcı / duvar geometrisinden çıkan dış hatlar karşılaştırılır.
    fp = {f.get("drawing_id"): float(f.get("area") or 0)
          for f in footprints if f.get("source") != "spaces"}
    ortak = [(d, by_dwg[d], fp[d]) for d in by_dwg if fp.get(d)]
    if not ortak:
        r.checks.append(Check("mahal_oturum", "Mahaller bina içinde", "mahaller", "kararsiz",
                              "Bina dış hattı mahal sınırlarından türetildiği için karşılaştırma dairesel olurdu; "
                              "bağımsız kontrol için taşıyıcı (kalıp) planı gerekir.",
                              bagimsizlik="mahal çokgenleri ↔ taşıyıcı / duvar dış hattı"))
        return
    tasan = [(d, a, f) for d, a, f in ortak if f > 0 and a / f > SPACES_IN_FOOTPRINT_MAX]
    ad = {f.get("drawing_id"): f.get("drawing") for f in footprints}
    if tasan:
        d, a, f = max(tasan, key=lambda t: t[1] / t[2])
        r.checks.append(Check(
            "mahal_oturum", "Mahaller bina içinde", f"{len(ortak)} kat", "celisiyor",
            f"“{ad.get(d, '?')}” katında mahallerin toplamı ({a:,.0f} m²) bina dış hattını "
            f"({f:,.0f} m²) aşıyor. Mahaller iç yüzlerden ölçülür, dış hattı geçemez: "
            "geometrilerden biri yanlış katta ya da planın ikinci kopyası karışmış olabilir.".replace(",", "."),
            olculen=a / f, beklenen=f"≤ {SPACES_IN_FOOTPRINT_MAX:g}",
            bagimsizlik="mahal çokgenleri ↔ taşıyıcı / duvar dış hattı"))
        return
    r.checks.append(Check(
        "mahal_oturum", "Mahaller bina içinde", f"{len(ortak)} kat", "destekliyor",
        "Her katta mahallerin toplamı bina dış hattının içinde kalıyor.",
        olculen=max(a / f for _d, a, f in ortak), beklenen=f"≤ {SPACES_IN_FOOTPRINT_MAX:g}",
        bagimsizlik="mahal çokgenleri ↔ taşıyıcı / duvar dış hattı"))


def _titleblock_area(r: SelfCheckReport, footprints: list[dict], titleblock: dict) -> None:
    """Antetteki inşaat alanı ↔ ölçtüğümüz kat alanları toplamı.

    Anteti ruhsat için mimar yazar, kat alanlarını biz çizimden ölçeriz — tam bağımsız iki kaynak.
    Bu kontrolün asıl değeri **birim hatasını** yakalamasıdır: cm yerine mm okunan bir çizimde
    alanlar 100 kat çıkar ve başka hiçbir kontrol bunu görmez."""
    antet = float(titleblock.get("area_m2") or 0)
    olculen = sum(float(f.get("area") or 0) * max(1, int(f.get("storey_count") or 1)) for f in footprints)
    if antet <= 0 or olculen <= 0:
        return
    fark = (olculen - antet) / antet * 100.0
    if abs(fark) > TITLEBLOCK_AREA_TOL_PCT:
        r.checks.append(Check(
            "antet_alani", "İnşaat alanı", "proje", "celisiyor",
            f"Antette {antet:,.0f} m² inşaat alanı yazıyor, çizimden ölçülen kat alanları toplamı "
            f"{olculen:,.0f} m² (%{fark:+.0f}). Bu büyüklükte bir fark ölçek / birim hatasına ya da "
            "eksik yüklenmiş kata işaret eder; bütün metraj aynı oranda kayar.".replace(",", "."),
            olculen=fark, beklenen=f"±%{TITLEBLOCK_AREA_TOL_PCT:g}",
            bagimsizlik="ruhsat anteti ↔ çizimden ölçülen kat alanları"))
        return
    r.checks.append(Check(
        "antet_alani", "İnşaat alanı", "proje", "destekliyor",
        f"Ölçülen kat alanları toplamı ({olculen:,.0f} m²) antetteki inşaat alanıyla "
        f"({antet:,.0f} m²) tutarlı (%{fark:+.0f}).".replace(",", "."),
        olculen=fark, beklenen=f"±%{TITLEBLOCK_AREA_TOL_PCT:g}",
        bagimsizlik="ruhsat anteti ↔ çizimden ölçülen kat alanları"))


def _rebar_ratio(r: SelfCheckReport, summary: dict) -> None:
    """Demir (yazılardan) ÷ beton (geometriden): iki bağımsız kaynak, fizikle sınırlı oran."""
    for g in summary.get("groups", []):
        etype, label = g.get("etype"), g.get("label", "")
        conc, rebar = float(g.get("concrete_m3") or 0), float(g.get("rebar_kg") or 0)
        band = REBAR_RATIO_BAND.get(etype)
        if band is None or conc <= 0:
            continue
        kaynak = g.get("rebar_source", "")
        if kaynak == "oran":
            r.checks.append(Check(
                kod="demir_orani", ad="Donatı oranı (kg/m³)", kapsam=label, sonuc="kararsiz",
                olculen=rebar / conc, beklenen=f"{band[0]:g}–{band[1]:g}",
                bagimsizlik="YOK — demir zaten beton × oran ile bulundu",
                aciklama=("Bu kalemin demiri betondan türetildiği için oran kontrolü dairesel olur ve hiçbir şey "
                          "kanıtlamaz. Donatı paftası yüklenirse kontrol anlamlı hale gelir.")))
            continue
        oran = rebar / conc
        tamam = _band(oran, band)
        r.checks.append(Check(
            kod="demir_orani", ad="Donatı oranı (kg/m³)", kapsam=label,
            sonuc="destekliyor" if tamam else "celisiyor", olculen=oran, beklenen=f"{band[0]:g}–{band[1]:g}",
            bagimsizlik=f"demir {kaynak} kaynağından (çizim yazıları), beton eleman geometrisinden — birbirini görmüyor",
            aciklama=(f"{oran:,.0f} kg/m³ beklenen bantta.".replace(",", ".") if tamam else
                      f"{oran:,.0f} kg/m³".replace(",", ".")
                      + f" bandın {'üstünde' if oran > band[1] else 'altında'} ({band[0]:g}–{band[1]:g}). "
                      f"İki sayıdan biri yanlış: ya {label.lower()} betonu "
                      f"{'az' if oran > band[1] else 'çok'} ölçüldü (kat yüksekliği / eleman sayısı), ya da demir "
                      f"{'fazla' if oran > band[1] else 'eksik'} toplandı (çift sayım / eksik kat).")))


def _slab_thickness(r: SelfCheckReport, summary: dict) -> None:
    """Döşemede kalıp = alan, beton = alan × t. Oranın tersi kalınlığı verir; ölçülen kalınlıkla çakışmalı."""
    for g in summary.get("groups", []):
        if g.get("etype") != "slab":
            continue
        conc, form = float(g.get("concrete_m3") or 0), float(g.get("formwork_m2") or 0)
        if conc <= 0 or form <= 0:
            continue
        t = conc / form
        tamam = _band(t, SLAB_THICKNESS_BAND)
        r.checks.append(Check(
            kod="doseme_kalinlik", ad="Döşeme kalınlığı (beton ÷ kalıp)", kapsam=g.get("label", "Döşeme"),
            sonuc="destekliyor" if tamam else "celisiyor", olculen=t * 100,
            beklenen=f"{SLAB_THICKNESS_BAND[0]*100:g}–{SLAB_THICKNESS_BAND[1]*100:g} cm",
            bagimsizlik="kalıp alandan, beton alan × kalınlıktan; oran doğrudan kalınlığı verir",
            aciklama=(f"Metrajın ima ettiği ortalama döşeme kalınlığı {t*100:.1f} cm."
                      + ("" if tamam else " Bu bir döşeme kalınlığı olamaz: kalınlık etiketleri ya da birim yanlış okunmuş."))))


def _formwork_ratio(r: SelfCheckReport, summary: dict) -> None:
    """Kalıp ÷ beton oranı geometrinin kendisinden gelir; bant dışı değer biçim hatasına işaret eder."""
    for g in summary.get("groups", []):
        etype, label = g.get("etype"), g.get("label", "")
        conc, form = float(g.get("concrete_m3") or 0), float(g.get("formwork_m2") or 0)
        band = FORMWORK_RATIO_BAND.get(etype)
        if band is None or conc <= 0 or form <= 0:
            continue
        oran = form / conc
        tamam = _band(oran, band)
        r.checks.append(Check(
            kod="kalip_beton", ad="Kalıp / beton (m²/m³)", kapsam=label,
            sonuc="destekliyor" if tamam else "celisiyor", olculen=oran, beklenen=f"{band[0]:g}–{band[1]:g}",
            bagimsizlik="kalıp yüzeyden, beton hacimden; ikisi farklı formülle hesaplanıyor",
            aciklama=(f"{oran:.1f} m²/m³ beklenen bantta." if tamam else
                      f"{oran:.1f} m²/m³ bant dışı ({band[0]:g}–{band[1]:g}): eleman kesiti ya da "
                      f"kalıp / beton yüksekliği kabulü kontrol edilmeli.")))


def _diameters(r: SelfCheckReport, summary: dict, rebar_mix: dict) -> None:
    """Keşifte çıkan çaplar, çizimde gerçekten yazan çaplar mı? Yazılmayan bir çapı sipariş ettiremeyiz."""
    cikan = {int(x["dia_mm"]) for x in summary.get("rebar_by_dia", []) if x.get("dia_mm")}
    yazan = {int(d) for pay in rebar_mix.values() for d in pay}
    if not cikan:
        return
    if not yazan:
        r.checks.append(Check(
            kod="cap_tutarliligi", ad="Çap dökümü ↔ çizimdeki donatı yazıları", kapsam="Demir", sonuc="kararsiz",
            bagimsizlik="YOK — çizimde taranabilir donatı yazısı bulunamadı",
            aciklama="Keşifteki çapları sınayacak ikinci kaynak yok."))
        return
    fazla = sorted(cikan - yazan)
    r.checks.append(Check(
        kod="cap_tutarliligi", ad="Çap dökümü ↔ çizimdeki donatı yazıları", kapsam="Demir",
        sonuc="celisiyor" if fazla else "destekliyor",
        beklenen=f"çizimde geçen çaplar: {', '.join('Ø' + str(d) for d in sorted(yazan))}",
        bagimsizlik="keşif çapları tablodan / orandan, karşılaştırılan çaplar plandaki serbest yazılardan",
        aciklama=("Keşifteki bütün çaplar çizimde de geçiyor." if not fazla else
                  f"Keşifte {', '.join('Ø' + str(d) for d in fazla)} var ama çizimin hiçbir yerinde bu çap yazmıyor; "
                  f"tablo okuması ya da çap karışımı yanlış olabilir.")))


def _floor_consistency(r: SelfCheckReport, summary: dict) -> None:
    """Aynı binanın normal katları birbirine benzer. Bir kat medyandan çok ayrılıyorsa sebebi olmalı."""
    rows = [x for x in summary.get("by_drawing", []) if float(x.get("concrete_m3") or 0) > 0]
    if len(rows) < 3:
        r.checks.append(Check(
            kod="kat_tutarliligi", ad="Katlar arası tutarlılık", kapsam="Proje", sonuc="kararsiz",
            bagimsizlik="YOK — karşılaştırmaya yetecek kadar kat yok",
            aciklama=f"{len(rows)} kat metraja girdi; katlar arası karşılaştırma en az 3 kat ister."))
        return
    vals = [float(x["concrete_m3"]) for x in rows]
    med = median(vals)
    sapan = [(x, float(x["concrete_m3"])) for x in rows if med > 0 and abs(float(x["concrete_m3"]) - med) > 2.0 * med]
    r.checks.append(Check(
        kod="kat_tutarliligi", ad="Katlar arası tutarlılık (beton)", kapsam="Proje",
        sonuc="celisiyor" if sapan else "destekliyor", olculen=med,
        beklenen=f"kat betonu medyanın 3 katını aşmamalı (medyan {med:,.0f} m³)".replace(",", "."),
        bagimsizlik="her kat ayrı paftadan, ayrı geometriden ölçülüyor; biri diğerini kullanmıyor",
        aciklama=("Katların betonu birbirine yakın." if not sapan else
                  "Bu paftalar diğer katlardan çok ayrılıyor: "
                  + "; ".join(f"{x.get('drawing', '?')} {v:,.0f} m³" for x, v in sapan[:4]).replace(",", ".")
                  + ". Temel / birleşik podyum katı ise normaldir; değilse çift sayım ya da ölçek hatası olabilir.")))


def _arithmetic(r: SelfCheckReport, summary: dict) -> None:
    """En basit sağlama: grupların toplamı proje toplamına eşit olmalı. Tutmuyorsa hata bizdedir."""
    tot = summary.get("totals") or {}
    for alan, ad in [("concrete_m3", "Beton"), ("formwork_m2", "Kalıp"), ("rebar_kg", "Demir")]:
        beklenen = float(tot.get(alan) or 0)
        toplam = sum(float(g.get(alan) or 0) for g in summary.get("groups", []))
        if beklenen <= 0 and toplam <= 0:
            continue
        fark = abs(toplam - beklenen)
        tamam = fark <= max(0.01, 0.001 * max(toplam, beklenen))
        r.checks.append(Check(
            kod="toplam_saglama", ad=f"Toplam sağlaması ({ad})", kapsam="Proje",
            sonuc="destekliyor" if tamam else "celisiyor", olculen=fark,
            beklenen="grup toplamı = proje toplamı",
            bagimsizlik="iki toplam ayrı yerlerde hesaplanıyor",
            aciklama=("Gruplar proje toplamını veriyor." if tamam else
                      f"Grupların toplamı {toplam:,.2f}, proje toplamı {beklenen:,.2f}; "
                      f"{fark:,.2f} fark var. Bu bir program hatasıdır, çizim sorunu değil.".replace(",", "."))))
