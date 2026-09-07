"""Proje plan seti: bir keşif için hangi paftaların gerekli olduğu, pafta başlığından plan tipinin tanınması
ve eksik plan kontrolü.

Yeni proje açılırken kullanıcı planlarını (ayrı dosyalar ya da bütün paftaların yan yana durduğu ruhsat projesi)
yükler. Her çizim / pafta başlığından PLAN TİPİ tanınır ("ZEMİN KAT KALIP PLANI" -> kat kalıp planı, "KABLO TAVA
PLANI" -> elektrik tava planı) ve o tipin analiz disiplini önerilir. Proje sayfasında plan seti kontrol listesi
gösterilir: yüklenmemiş zorunlu planlar için uyarı ("Altyapı planı yüklenmedi", "Elektrik kablo tava planı
yüklenmedi", "Mimari tavan planı yüklenmedi" ...). Kullanıcı bir tipi "bu projede yok" diye işaretleyebilir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

REQUIRED = "required"
OPTIONAL = "optional"
SKIP = "skip"
LEVELS = (REQUIRED, OPTIONAL, SKIP)

PLAN_GROUPS: dict[str, str] = {
    "STA": "Statik",
    "MIM": "Mimari",
    "ELK": "Elektrik",
    "MEK": "Mekanik",
    "ALT": "Altyapı",
    "PEY": "Peyzaj",
    "ASN": "Asansör",
}


@dataclass(frozen=True)
class PlanType:
    code: str
    group: str
    label: str
    discipline: str            # analiz disiplini önerisi (structural / rebar / architectural / electrical / mapped / standard)
    level: str = REQUIRED      # varsayılan gereklilik
    pattern: str = ""          # ASCII'ye indirgenmiş büyük harf başlıkta aranan düzenli ifade
    exclude: str = ""          # bu ifade geçiyorsa eşleşmez
    satisfies: tuple[str, ...] = ()   # bu plan varsa şu tipler de karşılanmış sayılır
    hint: str = ""             # kullanıcıya not
    analyze: bool = True       # False: yüklenir ama metraja girmez (kesit, detay); pafta seçiminde önceden işaretlenmez

    def to_dict(self) -> dict:
        return {"code": self.code, "group": self.group, "group_label": PLAN_GROUPS[self.group], "label": self.label,
                "discipline": self.discipline, "level": self.level, "hint": self.hint, "analyze": self.analyze,
                "satisfies": list(self.satisfies)}


# Sıra önemli: ilk eşleşen kazanır. Özel olanlar (donatı, tava, yangın...) genel "kat planı"ndan önce gelir.
PLAN_TYPES: list[PlanType] = [
    # --- Prekast / doğrama paftaları (statik KALIP kuralından önce: "PREKAST KALIP" kalıp planı değildir)
    PlanType("mim_prekast", "MIM", "Prekast panel / kalıp paftası", "mapped", level=OPTIONAL,
             pattern=r"PREKAST|PRECAST", hint="Panel kodları etiket sayımıyla (PREKAST_PANEL) sayılır."),
    PlanType("mim_dograma", "MIM", "Doğrama listesi / detayları", "mapped", level=OPTIONAL,
             pattern=r"DOGRAMA", hint="Poz listesi (Poz / Adet) otomatik okunur."),
    # --- Statik
    PlanType("sta_temel_donati", "STA", "Temel donatı planı", "rebar",
             pattern=r"(TEMEL|RADYE).*DONATI|DONATI.*(TEMEL|RADYE)", hint="Temel demir metraj tablosu buradan okunur."),
    PlanType("sta_temel_kalip", "STA", "Temel kalıp planı", "structural",
             pattern=r"(TEMEL|RADYE).*(KALIP|PLAN)|KALIP.*(TEMEL|RADYE)", exclude="DETAY|KESIT",
             hint="Radye / sürekli temel betonu ve kalıbı."),
    PlanType("elk_kolon_sema", "ELK", "Elektrik kolon şeması", "mapped", level=OPTIONAL, analyze=False,
             pattern=r"KOLON\s*SEMA|TEK\s*HAT\s*SEMA"),
    PlanType("sta_kolon", "STA", "Kolon aplikasyon / detay paftası", "rebar",
             pattern=r"KOLON.*(APLIKASYON|DETAY|ACILIM|DONATI|BOY\s*KESIT)|(APLIKASYON|ACILIM).*KOLON",
             hint="Kolon demiri: paftadaki metraj tablosu ya da adetli poz yazıları."),
    PlanType("sta_kiris", "STA", "Kiriş detay paftası", "rebar",
             pattern=r"KIRIS.*(DETAY|ACILIM|DONATI)|(DETAY|ACILIM).*KIRIS", hint="Kiriş demiri adetli poz yazılarından hesaplanır."),
    PlanType("sta_perde", "STA", "Perde detay paftası", "rebar", level=OPTIONAL,
             pattern=r"PERDE.*(DETAY|ACILIM|DONATI)|(DETAY|ACILIM).*PERDE"),
    PlanType("sta_merdiven", "STA", "Merdiven detay paftası", "rebar", level=OPTIONAL,
             pattern=r"MERDIVEN.*(DETAY|DONATI|KALIP)"),
    PlanType("sta_doseme_donati", "STA", "Döşeme (kat) donatı planı", "rebar",
             pattern=r"DONATI", hint="Döşeme alt / üst demir metraj tablosu."),
    PlanType("sta_kat_kalip", "STA", "Kat kalıp planları", "structural",
             pattern=r"KALIP", exclude="DETAY(?!L)|KESIT", hint="Kolon, perde, kiriş, döşeme: beton m³, kalıp m²."),
    # --- Elektrik
    PlanType("elk_tava", "ELK", "Elektrik kablo tava planı", "electrical",
             pattern=r"\bTAVA(SI|LARI)?\b|KABLO\s*TAVA|KABLO\s*TASIMA", hint="Tava m (boyut bazında), kablo m."),
    PlanType("elk_zayif", "ELK", "Zayıf akım planı", "electrical",
             pattern=r"ZAYIF|YANGIN\s*(ALGILAMA|IHBAR|ALARM)|DATA|TELEFON|\bTV\b|CCTV|KAMERA|OTOMASYON|SES\s*SISTEM|GORUNTULU",
             hint="Data / telefon / TV / yangın algılama hatları ve cihazları."),
    PlanType("elk_topraklama", "ELK", "Topraklama / paratoner planı", "electrical", level=OPTIONAL,
             pattern=r"TOPRAKLAMA|PARATONER|YILDIRIM"),
    PlanType("elk_aydinlatma", "ELK", "Aydınlatma planı", "electrical",
             pattern=r"AYDINLATMA|ARMATUR", hint="Armatür adedi, aydınlatma hatları."),
    PlanType("elk_kuvvet", "ELK", "Kuvvet / priz planı", "electrical",
             pattern=r"KUVVET|PRIZ|GUC\s*PLAN", hint="Priz adedi, kuvvet hatları."),
    PlanType("elk_genel", "ELK", "Elektrik tesisat planı (genel)", "electrical", level=OPTIONAL,
             pattern=r"ELEKTRIK", satisfies=("elk_aydinlatma", "elk_kuvvet"),
             hint="Aydınlatma ve kuvvet tek paftadaysa bu tip ikisini de karşılar."),
    # --- Mekanik
    PlanType("mek_yangin", "MEK", "Yangın tesisatı (sprinkler / dolap) planı", "mapped",
             pattern=r"SPRINK|YANGIN|HIDRANT|SONDURME", hint="KSF katmanlıysa disiplini 'KSF standart' seçin."),
    PlanType("mek_hav", "MEK", "Havalandırma planı", "mapped",
             pattern=r"HAVALANDIRMA|HAVA\s*KANAL|EGZOZ|KLIMA\s*SANTRAL", hint="Kanal m² / m, menfez adet."),
    PlanType("mek_isitma", "MEK", "Isıtma / soğutma planı", "mapped",
             pattern=r"ISITMA|SOGUTMA|KLIMA|RADYATOR|FANCOIL|\bVRF\b|\bVRV\b|KAZAN|CHILLER|MEKANIK",
             hint="Boru m (çap bazında), cihaz adet."),
    PlanType("mek_sihhi", "MEK", "Sıhhi tesisat planı", "mapped",
             pattern=r"SIHHI|TEMIZ\s*SU|PIS\s*SU|ATIK\s*SU|KULLANMA\s*SUYU|VITRIFIYE|TESISAT", exclude="ELEKTRIK",
             hint="Temiz / pis su boruları, vitrifiye adet."),
    # --- Altyapı / peyzaj / asansör
    PlanType("alt_altyapi", "ALT", "Altyapı planı", "mapped",
             pattern=r"ALTYAPI|ALT\s*YAPI|KANALIZASYON|YAGMUR\s*SUYU|ICME\s*SUYU|DRENAJ|ROGAR|SAHA\s*TESISAT|DIS\s*TESISAT",
             hint="Kanalizasyon, yağmur suyu, içme suyu hatları; rögar adet."),
    PlanType("pey_peyzaj", "PEY", "Peyzaj planı", "mapped",
             pattern=r"PEYZAJ|BITKI|SERT\s*ZEMIN|CEVRE\s*DUZEN", hint="Sert zemin m², bitki adet."),
    PlanType("asn_asansor", "ASN", "Asansör planı", "mapped", level=OPTIONAL, pattern=r"ASANSOR"),
    # --- Mimari (özel olanlar önce, genel kat planı en sonda)
    PlanType("mim_vaziyet", "MIM", "Vaziyet planı", "mapped", level=OPTIONAL, pattern=r"VAZIYET"),
    PlanType("mim_tavan", "MIM", "Mimari tavan planı", "mapped",
             pattern=r"TAVAN", hint="Asma tavan / tavan kaplaması m²."),
    PlanType("mim_doseme_kaplama", "MIM", "Mimari döşeme (kaplama) planı", "mapped",
             pattern=r"DOSEME|KAPLAMA|ZEMIN\s*KAPLAMA", exclude=r"DUVAR\s*KAPLAMA",
             hint="Zemin kaplaması m² (seramik, parke, epoksi...)."),
    PlanType("mim_cati", "MIM", "Çatı planı", "mapped",
             pattern=r"CATI", exclude=r"CATI\s*KAT", hint="Çatı örtüsü m², oluk / dere m."),
    PlanType("mim_cephe", "MIM", "Cephe görünüşleri", "mapped",
             pattern=r"CEPHE|GORUNUS", hint="Cephe kaplaması / mantolama / boya m², doğrama."),
    PlanType("mim_kesit", "MIM", "Kesitler", "mapped", level=OPTIONAL, analyze=False, pattern=r"KESIT"),
    PlanType("mim_detay", "MIM", "Kapı / pencere / merdiven detayları", "mapped", level=OPTIONAL, analyze=False,
             pattern=r"(KAPI|PENCERE|DOGRAMA|MERDIVEN|ISLAK\s*HACIM|BANYO|WC).*DETAY|DETAY"),
    PlanType("mim_kat_plani", "MIM", "Mimari kat planları", "architectural",
             pattern=r"KAT\s*PLAN|MIMARI|\bPLAN",
             hint="Duvar m² (malzeme bazında), sıva, boya, kapı / pencere adet."),
]

PLAN_TYPE_BY_CODE: dict[str, PlanType] = {p.code: p for p in PLAN_TYPES}

_TR = str.maketrans({"İ": "I", "I": "I", "ı": "I", "Ş": "S", "ş": "S", "Ç": "C", "ç": "C", "Ğ": "G", "ğ": "G",
                     "Ü": "U", "ü": "U", "Ö": "O", "ö": "O"})


def normalize_title(s: str) -> str:
    """Türkçe harfleri ASCII'ye indirger, büyük harfe çevirir, ayraçları boşluğa dönüştürür."""
    s = (s or "").translate(_TR).upper()
    s = re.sub(r"[_\-./\\()\[\]:,;]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def classify_title(*titles: str) -> PlanType | None:
    """Verilen başlıklardan (pafta başlığı, dosya adı, diğer adaylar) ilk tanınan plan tipini döndürür."""
    fallback: PlanType | None = None
    for raw in titles:
        t = normalize_title(raw)
        if not t:
            continue
        for p in PLAN_TYPES:
            if not p.pattern:
                continue
            if p.exclude and re.search(p.exclude, t):
                continue
            if re.search(p.pattern, t):
                if p.analyze:
                    return p
                fallback = fallback or p   # kesit / detay: başka aday plan yoksa
                break
    return fallback


def discipline_for(plan_type: str | None, fallback: str = "structural") -> str:
    p = PLAN_TYPE_BY_CODE.get(plan_type or "")
    return p.discipline if p else fallback


# Başlıktan tanınan ama tek başına zayıf sayılan tipler: katman adları aksini söylüyorsa katmanlar kazanır
# ("ZEMİN KAT PLANI" adlı bir kalıp planı KOLON / KİRİŞ katmanlarından statik olarak tanınır).
WEAK_TYPES = {"mim_kat_plani"}
# Katmanlardan tanınan disiplin için varsayılan plan tipi
DEFAULT_TYPE_FOR_DISCIPLINE = {"structural": "sta_kat_kalip", "architectural": "mim_kat_plani",
                               "electrical": "elk_genel", "standard": ""}
MIN_LAYER_HITS = 8
MIN_LAYER_SHARE = 0.6


def discipline_from_layers(layers: dict[str, int] | None) -> str | None:
    """Katman adlarından (KOLON, KIRIS / DUVAR, KAPI / TAVA, KABLO / KSF-…) baskın disiplini tahmin eder.

    Tanınan nesnelerin en az %60'ı tek disipline düşüyorsa ve yeterince nesne varsa o disiplin; yoksa None.
    """
    if not layers:
        return None
    from .parser.layer_profile import LayerProfile
    prof = LayerProfile()
    hits: dict[str, int] = {}
    for name, n in layers.items():
        if not name or n <= 0:
            continue
        if name.upper().startswith("KSF-") or name.upper().startswith("KSF_"):
            hits["standard"] = hits.get("standard", 0) + n
            continue
        for disc in ("structural", "architectural", "electrical"):
            if prof.classify(name, disc):
                hits[disc] = hits.get(disc, 0) + n
                break
    if not hits:
        return None
    best = max(hits, key=hits.get)
    total = sum(hits.values())
    if hits[best] < MIN_LAYER_HITS or hits[best] < MIN_LAYER_SHARE * total:
        return None
    return best


def resolve_plan(titles: list[str], layers: dict[str, int] | None = None, explicit: str = "") -> tuple[str, str]:
    """(plan tipi kodu, disiplin). explicit verilmişse o tip; yoksa başlıklardan, zayıfsa katmanlardan."""
    if explicit:
        return explicit, discipline_for(explicit)
    found = classify_title(*titles)
    code = found.code if found else ""
    # "… KAT PLANI" açıkça mimari kat planıdır (statik ofis "KALIP PLANI" yazar); yalnız genel "PLAN" eşleşmesi zayıftır
    strong_arch = any(re.search(r"KAT\s*PLAN|MIMARI", normalize_title(t)) for t in titles if t)
    if found is None or (found.code in WEAK_TYPES and not strong_arch):
        ld = discipline_from_layers(layers)
        if ld and (found is None or found.discipline != ld):
            code = DEFAULT_TYPE_FOR_DISCIPLINE.get(ld, "")
            return code, ld
    return code, (discipline_for(code) if code else "")   # tanınmadı: disiplin boş (çağıran varsayılanı seçer)


def effective_levels(plan_set: dict | None) -> dict[str, str]:
    """Varsayılan gereklilikler + projenin değişiklikleri (code -> required / optional / skip)."""
    out = {p.code: p.level for p in PLAN_TYPES}
    for k, v in (plan_set or {}).items():
        if k in out and v in LEVELS:
            out[k] = v
    return out


@dataclass
class PlanStatus:
    plan: PlanType
    level: str
    drawings: list[dict] = field(default_factory=list)
    via: str | None = None       # başka bir tipin karşıladığı (ör. elk_genel -> elk_aydinlatma)

    @property
    def status(self) -> str:
        if self.drawings or self.via:
            return "present"
        if self.level == SKIP:
            return "skipped"
        return "missing" if self.level == REQUIRED else "optional_missing"

    def to_dict(self) -> dict:
        return {**self.plan.to_dict(), "level": self.level, "status": self.status, "drawings": self.drawings, "via": self.via}


def plan_check(drawings: list, plan_set: dict | None) -> dict:
    """Projenin çizimlerine göre plan seti durumu.

    drawings: plan_type / id / label alanları olan nesneler (Drawing modeli ya da sözlük).
    """
    levels = effective_levels(plan_set)
    statuses = {p.code: PlanStatus(p, levels[p.code]) for p in PLAN_TYPES}
    unknown: list[dict] = []
    for d in drawings:
        get = (lambda k: d.get(k)) if isinstance(d, dict) else (lambda k: getattr(d, k, None))
        code = get("plan_type") or ""
        info = {"id": get("id"), "label": get("label") or get("filename") or "", "discipline": get("discipline")}
        if code in statuses:
            statuses[code].drawings.append(info)
        else:
            unknown.append(info)
    for code, st in statuses.items():
        if st.drawings:
            for other in st.plan.satisfies:
                if other in statuses and not statuses[other].drawings and not statuses[other].via:
                    statuses[other].via = st.plan.label
    groups = []
    for gcode, glabel in PLAN_GROUPS.items():
        types = [statuses[p.code].to_dict() for p in PLAN_TYPES if p.group == gcode]
        groups.append({"code": gcode, "label": glabel, "types": types,
                       "missing": sum(1 for t in types if t["status"] == "missing"),
                       "present": sum(1 for t in types if t["status"] == "present")})
    missing = [statuses[p.code] for p in PLAN_TYPES if statuses[p.code].status == "missing"]
    warnings = [f"{PLAN_GROUPS[st.plan.group]}: {st.plan.label} yüklenmedi" for st in missing]
    if unknown:
        warnings.append(f"{len(unknown)} çizimin plan tipi tanınamadı; çizim listesinden plan tipini seçin")
    return {
        "groups": groups,
        "warnings": warnings,
        "missing_required": len(missing),
        "present": sum(1 for st in statuses.values() if st.status == "present"),
        "total_required": sum(1 for st in statuses.values() if st.level == REQUIRED),
        "unknown": unknown,
        "complete": not missing and not unknown,
    }
