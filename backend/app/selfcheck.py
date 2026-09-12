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


def build(summary: dict, elements=None, rebar_mix: dict | None = None) -> SelfCheckReport:
    """summary: quantity/summary.py çıktısı. elements: proje elemanları (birim sağlaması için)."""
    r = SelfCheckReport()
    _rebar_ratio(r, summary)
    _slab_thickness(r, summary)
    _formwork_ratio(r, summary)
    _diameters(r, summary, rebar_mix or {})
    _floor_consistency(r, summary)
    _arithmetic(r, summary)
    return r


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
