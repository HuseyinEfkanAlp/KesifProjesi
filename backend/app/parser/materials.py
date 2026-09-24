"""Çizim yazılarından malzeme / sistem bileşeni tarama.

Cephe ve çatı detaylarında katmanlar çizilmez, yazılır: "5 cm TAŞYÜNÜ", "OSB 11 mm", "BUHAR KESİCİ", "KENET ÇATI".
Bu modül bir çizimin bütün yazılarını (TEXT / MTEXT / blok içi yazılar) tarar ve katalog bileşen kodlarına
kanıt toplar: {"OSB": {"evidence": ["OSB 11 mm"], "spec": "11"}, "KENET_CATI": {...}}.

Sistem paneli bu kanıta göre "projede yazıyor / projede yok" der; katman önerisi çatı katmanı için kenet / kiremit /
teras sistemini buradan seçer.
"""
from __future__ import annotations

import re

from ..planset import normalize_title
from .loader import Drawing

# (bileşen / sistem kodu, ASCII büyük harf metinde düzenli ifade). Sıra: özel önce.
MATERIAL_RULES: list[tuple[str, str]] = [
    # sistemler
    ("KENET_CATI", r"KENET"),
    ("TERAS_CATI", r"TERAS\s*CATI|GEZIL(EN|MEYEN)\s*(TERAS|CATI)|TERS\s*CATI"),
    ("KIREMIT_CATI", r"KIREMIT|SHINGLE"),
    ("CELIK_CATI", r"CELIK\s*CATI|CATI\s*MAKAS|MAKAS\s*CATI|CELIK\s*KONSTR\w*\s*CATI"),
    ("MANTOLAMA_SISTEM", r"MANTOLAMA|ISI\s*YALITIM\s*SISTEM|ETICS|DIS\s*CEPHE\s*ISI"),
    # çatı bileşenleri
    ("KENET_KAPLAMA", r"KENET\s*(KAPLAMA|LEVHA|SAC)|KENETLI|GALVANIZ\s*SAC|TITANYUM\s*CINKO|CINKO\s*(KAPLAMA|LEVHA)|ALUMINYUM\s*KENET"),
    ("AYIRICI_KECE", r"AYIRICI\s*KECE|YAPISAL\s*MAT|DRENAJ\s*MAT"),
    ("OSB", r"\bOSB\b"),
    ("CATI_TAHTASI", r"CATI\s*TAHTA|AHSAP\s*KAPLAMA\s*TAHTA|\bTAHTA\b"),
    ("MERTEK", r"MERTEK"),
    ("ASIK", r"\bASIK\b|Z\s*PROFIL|C\s*PROFIL"),
    ("CATI_LATA", r"\bLATA\b|KONTR\s*LATA|KONTRLATA"),
    ("CATI_KIREMIT", r"KIREMIT|SHINGLE"),
    ("EGIM_BETONU", r"EGIM\s*(BETON|SAP)|MEYIL\s*(BETON|SAP)"),
    ("GROBETON", r"GROBETON|GROB\s*BETON|TEMEL\s*ALTI\s*BETON|BLOKAJ\s*BETON"),
    ("KORUMA_SAPI", r"KORUMA\s*SAPI?\b"),          # temel yalıtımı üstü; aynı yazı KORUMA_BETONU'na da düşer
    ("KORUMA_BETONU", r"KORUMA\s*(BETON|SAP)"),
    ("KAZI_CALISMA_PAYI", r"CALISMA\s*(PAYI|BOSLUGU|ARALIGI)"),   # kazıda temel kenarından bırakılan boşluk
    ("CATI_CAKIL", r"\bCAKIL\b|BALAST"),
    ("CELIK_PROFIL", r"CELIK\s*(KIRIS|PROFIL|KONSTR)"),
    ("CATI_SANDVIC_PANEL", r"SANDVIC\s*PANEL|TRAPEZ\s*(SAC|PANEL|LEVHA)"),
    ("CATI_MEMBRAN", r"CATI\s*MEMBRAN|\bPVC\s*MEMBRAN|TPO"),
    # yalıtım
    ("TASYUNU", r"TAS\s*YUNU|TASYUNU|MINERAL\s*YUN|ROCKWOOL|CAM\s*YUNU"),
    ("XPS", r"\bXPS\b|EKSTRUDE"),
    ("EPS", r"\bEPS\b|EKSPANDE|KARBONLU|STRAFOR"),
    ("BUHAR_KESICI", r"BUHAR\s*(KESICI|DENGELEYICI|BARIYER)|VAPOR"),
    ("SU_YALITIM_MEMBRAN", r"(SU\s*YALITIM|BITUM|NEFES\s*ALAN|SU\s*TUTUCU)\s*(MEMBRAN|ORTU)?|MEMBRAN"),
    ("GEOTEKSTIL", r"GEOTEKSTIL|GEOTEXTILE|KECE"),
    ("SURME_IZOLASYON", r"SURME\s*(IZOLASYON|YALITIM)|POLIURE|POLYUREA"),
    # mantolama bileşenleri
    ("MANTOLAMA_YAPISTIRICI", r"YAPISTIRICI|YAPISTIRMA\s*HARC"),
    ("MANTOLAMA_DUBEL", r"DUBEL|DÜBEL"),
    ("MANTOLAMA_FILE", r"(SIVA|DONATI|CAM)\s*FILE|\bFILE\b"),
    ("MANTOLAMA_SIVA", r"(FILE|DEKORATIF|MINERAL|SILIKON)\s*SIVA|SIVA\s*(FILE|DEKORATIF)"),
    ("CEPHE_BOYA", r"(DIS\s*CEPHE|SILIKON|AKRILIK)\s*BOYA|BOYA"),
    ("KOSE_PROFILI", r"KOSE\s*PROFIL|SUBASMAN\s*PROFIL|DAMLALIK"),
    ("SOVE", r"\bSOVE\b|SOVE\b"),
    ("SILME", r"\bSILME\b"),
    ("DENIZLIK", r"DENIZLIK"),
]
_RULES = [(code, re.compile(pat)) for code, pat in MATERIAL_RULES]
# "5 cm", "50mm", "d=11 mm", "11mm OSB", "OSB 11"
_THICK = re.compile(r"(\d+(?:[.,]\d+)?)\s*(CM|MM)\b")
MAX_EVIDENCE = 5
MAX_TEXT = 160


def _spec_from(text: str) -> str:
    """Yazıdaki kalınlığı özellik olarak alır: cm → sayı (cm), mm → sayı + 'MM'."""
    m = _THICK.search(text)
    if not m:
        return ""
    num = m.group(1).replace(",", ".")
    num = num[:-2] if num.endswith(".0") else num
    return num if m.group(2) == "CM" else f"{num}MM"


def scan_texts(texts: list[str]) -> dict[str, dict]:
    """Düz metin listesinden kanıt toplar."""
    found: dict[str, dict] = {}
    for raw in texts:
        raw = (raw or "").strip()
        if not raw or len(raw) > MAX_TEXT:
            continue
        t = normalize_title(raw)
        if not t:
            continue
        for code, pat in _RULES:
            if not pat.search(t):
                continue
            ev = found.setdefault(code, {"evidence": [], "spec": ""})
            if raw not in ev["evidence"] and len(ev["evidence"]) < MAX_EVIDENCE:
                ev["evidence"].append(raw)
            if not ev["spec"]:
                ev["spec"] = _spec_from(t)
    return found


def scan_materials(drawing: Drawing) -> dict[str, dict]:
    """Çizimdeki bütün yazılardan (blok içi dahil) malzeme kanıtı; şap kalınlığı da buraya yazılır."""
    texts = [e.text for e in drawing.entities if e.kind == "text" and e.text]
    found = scan_texts(texts)
    cm, note = screed_cm_from(texts)
    if cm > 0:
        found.setdefault("SAP", {"evidence": [note], "spec": f"{cm:g}"})
    # kazı kotları da kanıt olarak saklanır: derinlik varsayılana düşmeden kesitten okunsun
    from .levels import excavation_levels
    exc = excavation_levels(texts)
    for key, code in (("ground", "KOT_ZEMIN"), ("bottom", "KOT_KAZI_TABAN"), ("depth", "KAZI_DERINLIK")):
        if exc.get(key) is not None:
            found.setdefault(code, {"evidence": [exc[f"{key}_note"]], "spec": f"{exc[key]:g}"})
    n, note = slope_from(texts)
    if n is not None:
        found.setdefault("KAZI_SEV", {"evidence": [note], "spec": f"{n:g}"})
    return found


# ---------- Kazı şevi: "ŞEV 1:1", "1/1,5 ŞEV", "ŞEV AÇISI 60°". Oran düşey:yatay okunur (1:1,5 = 1 m inişte
# 1,5 m açılır); döndürülen değer metre düşey başına yatay açılmadır. normalize_title noktalamayı sildiği
# için ham yazıdan okunur.
_SEV = re.compile(r"(?:\bSEV\w*\D{0,15}?(?P<a>\d+(?:[.,]\d+)?)\s*[:/]\s*(?P<b>\d+(?:[.,]\d+)?))"
                  r"|(?:(?P<a2>\d+(?:[.,]\d+)?)\s*[:/]\s*(?P<b2>\d+(?:[.,]\d+)?)\s*\bSEV)"
                  r"|(?:\bSEV\w*\D{0,15}?(?P<deg>\d{2}(?:[.,]\d+)?)\s*(?:°|%%D|DERECE))")


def slope_from(texts: list[str]) -> tuple[float | None, str]:
    """Kazı şevi: (düşey metre başına yatay açılma, kanıt yazısı) ya da (None, "")."""
    import math
    for raw in texts:
        if not raw or len(raw) > MAX_TEXT:
            continue
        t = raw.upper().replace("Ş", "S").replace("İ", "I").replace("Ç", "C").replace("Ğ", "G")
        m = _SEV.search(t)
        if not m:
            continue
        f = lambda s: float(s.replace(",", "."))   # noqa: E731
        try:
            if m.group("deg"):
                deg = f(m.group("deg"))
                n = 1.0 / math.tan(math.radians(deg)) if 10 <= deg < 90 else None
            else:
                a, b = (m.group("a"), m.group("b")) if m.group("a") else (m.group("a2"), m.group("b2"))
                n = f(b) / f(a) if f(a) > 0 else None
        except ValueError:
            n = None
        if n is not None and 0 < n <= 3:
            return round(n, 3), re.sub(r"\s+", " ", raw.replace(r"\P", " ")).strip()[:60]
    return None, ""


def merge_materials(per_drawing: list[dict]) -> dict[str, dict]:
    """Birden çok çizimin kanıtını birleştirir (proje geneli)."""
    out: dict[str, dict] = {}
    for mats in per_drawing:
        for code, ev in (mats or {}).items():
            cur = out.setdefault(code, {"evidence": [], "spec": ""})
            for e in ev.get("evidence", []):
                if e not in cur["evidence"] and len(cur["evidence"]) < MAX_EVIDENCE:
                    cur["evidence"].append(e)
            if not cur["spec"] and ev.get("spec"):
                cur["spec"] = ev["spec"]
    return out


# ---------- Döşeme bitişi: mahal yazısının yanındaki / döşeme kaplama planındaki notlar
# "ŞAP 5 CM", "SERAMİK 60x60", "LAMİNAT PARKE" — kaplamanın TİPİ ve şapın KALINLIĞI buradan okunur;
# karşılığı katalogda olmayan tipler (epoksi, mermer, halı) DOSEME_KAPLAMA'nın özelliği olur.
FINISH_RULES: list[tuple[str, str, str]] = [   # (katalog kodu, sabit özellik, desen)
    ("SERAMIK_ZEMIN", "", r"SERAMIK|FAYANS|PORSELEN|SIRLI\s*GRANIT|GRANIT\s*SERAMIK"),
    ("LAMINAT", "", r"LAMINAT|\bPARKE\b(?!\s*TAS)|AHSAP\s*(ZEMIN|KAPLAMA\s*ZEMIN)"),
    ("DOSEME_KAPLAMA", "EPOKSI", r"EPOKSI|POLIURETAN\s*ZEMIN"),
    ("DOSEME_KAPLAMA", "MERMER", r"\bMERMER\b"),
    ("DOSEME_KAPLAMA", "HALI", r"\bHALI\b|KARO\s*HALI"),
    ("DOSEME_KAPLAMA", "DOGALTAS", r"DOGAL\s*TAS|ANDEZIT|BAZALT|TRAVERTEN"),
]
_FINISH = [(code, spec, re.compile(pat)) for code, spec, pat in FINISH_RULES]
# "60x60", "30 X 60", "20*20" -> seramik / doğaltaş ebadı
_SIZE = re.compile(r"(\d{1,3})\s*[X*]\s*(\d{1,3})")
# şap: "ŞAP 5 CM", "5 CM ŞAP", "TESVİYE ŞAPI". Eğim / koruma şapı ayrı kalemdir, kaplama altı şapı değildir.
_SCREED = re.compile(r"\bSAP\b|\bSAPI\b|SAP\s*BETON|TESVIYE\s*(SAP|BETON)")
_SCREED_SKIP = re.compile(r"EGIM|MEYIL|KORUMA|SIZDIRMAZ|ASFALT|CATI")


def _cm(text: str) -> float:
    """Yazıdaki kalınlık, cm cinsinden (0 = yazmıyor)."""
    m = _THICK.search(text)
    if not m:
        return 0.0
    try:
        v = float(m.group(1).replace(",", "."))
    except ValueError:
        return 0.0
    return v / 10.0 if m.group(2) == "MM" else v


def finish_of(text: str) -> dict | None:
    """Tek yazıdan döşeme bitişi: {"code", "spec", "screed_cm", "text"} ya da None.
    Aynı yazı hem kaplamayı hem şapı anlatabilir ("ŞAP + SERAMİK 60x60")."""
    raw = (text or "").strip()
    if not raw or len(raw) > MAX_TEXT:
        return None
    t = normalize_title(raw)
    if not t:
        return None
    out = {"code": "", "spec": "", "screed_cm": 0.0, "text": re.sub(r"\s+", " ", raw.replace(r"\P", " "))[:60]}
    for code, spec, pat in _FINISH:
        if pat.search(t):
            out["code"], out["spec"] = code, spec
            if not spec:
                m = _SIZE.search(t)
                if m:
                    out["spec"] = f"{m.group(1)}x{m.group(2)}"
            break
    if _SCREED.search(t) and not _SCREED_SKIP.search(t):
        out["screed_cm"] = _cm(t)
    # kalınlıksız yalın "ŞAP" yazısı bilgi taşımaz; kaplama tipi de yoksa not değildir
    return out if out["code"] or out["screed_cm"] > 0 else None


def screed_cm_from(texts: list[str]) -> tuple[float, str]:
    """Çizimin genel notlarından şap kalınlığı (cm) ve kanıt yazısı; bulunamazsa (0, "")."""
    for raw in texts:
        f = finish_of(raw)
        if f and f["screed_cm"] > 0:
            return f["screed_cm"], f["text"]
    return 0.0, ""

# ---------- Konumlu sistem yazıları: çatı planında "burası kenet, şurası kiremit" yazar.
# Bölge bazlı okuma (detectors/standard.py: assign_roof_zones) bu yazıların hangi kapalı alanın içine
# düştüğüne bakar. Sıra önceliktir: bir yazı birden çok sisteme uyarsa ilki seçilir.
ROOF_SYSTEM_CODES = ("CELIK_CATI", "KENET_CATI", "TERAS_CATI", "KIREMIT_CATI", "CATI_MEMBRAN")


def system_notes(drawing: Drawing, codes: tuple[str, ...] = ROOF_SYSTEM_CODES) -> list[dict]:
    """Konumu bilinen sistem yazıları: [{"code", "text", "pt"}]. Konumsuz yazı (blok içi) bölgeye bağlanamaz."""
    out: list[dict] = []
    for e in drawing.entities:
        if e.kind != "text" or not e.text or not e.points:
            continue
        hits = scan_texts([e.text])
        code = next((c for c in codes if c in hits), "")
        if code:
            out.append({"code": code, "text": re.sub(r"\s+", " ", e.text.replace(r"\P", " ")).strip()[:60],
                        "pt": tuple(e.points[0][:2])})
    return out
