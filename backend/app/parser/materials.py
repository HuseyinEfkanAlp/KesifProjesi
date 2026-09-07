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
    ("KORUMA_BETONU", r"KORUMA\s*(BETON|SAP)"),
    ("CATI_CAKIL", r"\bCAKIL\b|BALAST"),
    ("CELIK_PROFIL", r"CELIK\s*(KIRIS|PROFIL|KONSTR)"),
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
    """Çizimdeki bütün yazılardan (blok içi dahil) malzeme kanıtı."""
    return scan_texts([e.text for e in drawing.entities if e.kind == "text" and e.text])


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
