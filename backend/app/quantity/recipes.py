"""Reçete açılımı: her keşif kalemi, zaman ya da maliyet doğuran alt işlerine (sarf, yardımcı imalat, işçilik) açılır.

  Çelik çatı 1.000 m²  → çelik konstrüksiyon 25 t → ankraj 250 adet → tij 250, somun 500, pul 500
                                                 → kaynak 1.000 m, antipas 500 m², boya 500 m², montaj 750 saat, vinç 100 saat
  Kalıp 800 m²         → kalıp iskelesi 800 × H m³
  Cephe boyası 600 m²  → iş iskelesi 600 m²
  Pencere 82 adet      → lento 82, montaj 82 saat, köpük 82 tüp

Reçete kaynağı: katalog kaleminin `recipe` alanı (katalog kodlu kalemler: kind == kod) ya da rules.RECIPES_BY_KIND
(sezgisel türler: kalip, beton, duvar, pencere, kapi). Bileşenin kendi reçetesi de açılır (derinlik ≤ RECIPE_MAX_DEPTH);
aynı kod zincirde tekrar etmez. Üretilen satır: detail.recipe = True, detail.parent = üst kalem anahtarı.
"""
from __future__ import annotations

from ..standard.catalog import Catalog
from ..standard.rules import RECIPE_MAX_DEPTH, RECIPES_BY_KIND
from .boq import BoqItem, _Acc, slug


def recipe_of(item: BoqItem, catalog: Catalog) -> list[dict]:
    if item.detail.get("system") or item.detail.get("info") or item.group == "fire":
        return []   # sistem başlığı, bilgi satırı ve fire satırları reçete açmaz
    cit = catalog.get(item.kind)
    if cit and cit.recipe:
        return list(cit.recipe)
    return list(RECIPES_BY_KIND.get(item.kind, []))


def expand_recipes(items: list[BoqItem], catalog: Catalog, storey_height: float | None = None,
                   off: bool = False) -> list[BoqItem]:
    """Kalem listesine reçete satırlarını ekler (var olanlar korunur). off=True: reçete kapalı."""
    if off:
        return items
    H = float(storey_height or 0.0)
    acc = _Acc()
    queue: list[tuple[BoqItem, int, tuple[str, ...]]] = [(it, 0, (it.kind,)) for it in items if not it.detail.get("recipe")]
    warnings: list[str] = []
    while queue:
        parent, depth, chain = queue.pop(0)
        if depth >= RECIPE_MAX_DEPTH or parent.quantity <= 0:
            continue
        for comp in recipe_of(parent, catalog):
            code = comp["code"]
            kind = code.lower()
            if kind in chain:
                continue
            cit = catalog.get(code)
            if not cit:
                warnings.append(f"{parent.label}: reçetedeki {code} katalogda yok")
                continue
            factor = float(comp.get("factor") or 1.0)
            times_h = str(comp.get("times") or "").upper() == "H"
            if times_h:
                if H <= 0:
                    warnings.append(f"{parent.label} → {cit.name}: kat yüksekliği girilmedi, miktar hesaplanamadı")
                    continue
                factor *= H
            spec = str(comp.get("spec") or "").strip()
            group = slug(spec) if spec else "*"
            qty = parent.quantity * factor
            key = f"{kind}:{group}"
            first = key not in acc.items
            note = (f"Reçete varsayılanı: {parent.kind_label} × {float(comp.get('factor') or 1.0):g}" + (" × H" if times_h else "")
                    + "; çarpan katalogdan düzenlenir") if first else None
            child = acc.add(kind, group, cit.name + (f" {spec}" if spec else ""), qty, note=note,
                            meta=(cit.name, cit.unit, f"ksf:{cit.discipline}", catalog.discipline_name(cit.discipline)),
                            poz=cit.poz, recipe=True, parents=1, **({"parent": parent.key, "depth": depth + 1} if first else {}))
            src = child.detail.setdefault("from", [])
            if isinstance(src, list) and len(src) < 8 and parent.label not in src:
                src.append(parent.label)
            queue.append((child, depth + 1, chain + (kind,)))
    out = list(items)
    existing = {it.key for it in items}
    for it in acc.items.values():
        if it.key in existing:
            # aynı kalem zaten ölçülmüş (ör. çizimde iskele çizilmiş): reçete miktarı üstüne eklenmez, not düşülür
            base = next(x for x in items if x.key == it.key)
            base.notes.append(f"Reçete de {it.quantity:,.1f} {it.unit} öneriyor (çizimden ölçülen esas alındı)")
            continue
        out.append(it)
    for w in warnings:
        if out and w not in out[0].notes:
            pass
    return out
