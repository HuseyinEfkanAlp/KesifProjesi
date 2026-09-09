"""Fiyat bankası: proje bağımsız ürün ve işçilik fiyatları, tedarikçi bazında.

Kullanıcı bütün ürünlerin fiyatını bir kez girer (C30/37 beton, Ø12 demir, Ytong duvar, NYY kablo…); yeni bir
proje açılınca ürün ve işçilik satırları buradan doldurulur. Aynı ürüne birden çok tedarikçi fiyatı girilebilir;
geçerli fiyat `preferred` işaretli satır, yoksa en düşük pozitif fiyattır (mukayese).

Ürün anahtarı proje tarafındakiyle aynıdır (cost.materials.material_of). Tam anahtar bankada yoksa türün genel
satırı ("<tür>:*") uygulanır: "duvar_ytong:*" fiyatı, projedeki "duvar_ytong:20x300" ürününe de geçer.
"""
from __future__ import annotations

from ..parser.layer_profile import DISCIPLINES
from ..quantity.boq import KIND_META
from ..standard.catalog import Catalog
from ..standard.rules import WORK_GROUPS, work_group_of
from .materials import CONCRETE_CLASSES, FORMWORK_MATERIALS, DEFAULT_REBAR_GRADE, _slug

# Fiyatı girilebilen yaygın donatı çapları (mm)
REBAR_DIAS = [8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32]


def _p(key: str, name: str, unit: str, discipline: str, group: str = "") -> dict:
    wg = group or work_group_of(discipline)
    return {"key": key, "name": name, "unit": unit, "discipline": discipline,
            "discipline_label": DISCIPLINES.get(discipline, discipline),
            "work_group": wg, "work_group_label": WORK_GROUPS.get(wg, wg)}


def known_products(catalog: Catalog, rebar_grade: str = DEFAULT_REBAR_GRADE) -> list[dict]:
    """Fiyat girilebilecek ürünler: beton sınıfları, demir çapları, kalıp malzemeleri, tür genel satırları ve
    katalog kalemleri. Projelerde geçen ürünler API katmanında bunlara eklenir."""
    out: list[dict] = []
    for c in CONCRETE_CLASSES:
        out.append(_p(f"beton:{_slug(c)}", f"Hazır beton {c}", "m³", "structural"))
    for d in REBAR_DIAS:
        out.append(_p(f"demir:o{d}", f"Nervürlü inşaat demiri Ø{d} ({rebar_grade})", "kg", "structural"))
    out.append(_p("demir:karisik", f"Nervürlü inşaat demiri, çap karışık ({rebar_grade})", "kg", "structural"))
    for code, label in FORMWORK_MATERIALS.items():
        out.append(_p(f"kalip:{code}", label, "m²", "structural"))
    seen = {p["key"] for p in out}
    for kind, (label, unit, disc) in KIND_META.items():
        if kind in ("beton", "demir", "kalip"):
            continue          # bunlar ürün bazında yukarıda
        key = f"{kind}:*"
        if key not in seen:
            seen.add(key)
            out.append(_p(key, f"{label} (tür geneli)", unit, disc))
    for it in catalog.items.values():
        key = f"{it.code.lower()}:*"
        if key in seen:
            continue
        seen.add(key)
        out.append(_p(key, it.name, it.unit or "adet", f"ksf:{it.discipline}"))
    return out


def best_row(rows: list) -> object | None:
    """Bir ürünün geçerli fiyat satırı: seçili (preferred) satır, yoksa en düşük pozitif fiyatlı satır."""
    if not rows:
        return None
    pref = [r for r in rows if getattr(r, "preferred", False)]
    if pref:
        return pref[0]
    priced = [r for r in rows if (r.unit_price or 0) > 0 or (r.labor_price or 0) > 0 or (r.hours_per_unit or 0) > 0]
    if not priced:
        return rows[0]
    return min(priced, key=lambda r: (r.unit_price or 0) if (r.unit_price or 0) > 0 else float("inf"))


def lookup(book: dict[str, list], key: str) -> object | None:
    """Anahtara göre geçerli banka satırı; tam eşleşme yoksa türün genel satırı ("<tür>:*")."""
    row = best_row(book.get(key) or [])
    if row is not None and ((row.unit_price or 0) > 0 or (row.labor_price or 0) > 0 or (row.hours_per_unit or 0) > 0):
        return row
    kind = key.split(":")[0]
    return best_row(book.get(f"{kind}:*") or []) if kind else None
