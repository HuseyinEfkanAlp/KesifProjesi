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
    if item.kind == "duvar":
        # sezgisel duvar: malzemeye göre katalog reçetesi (tuğlaya gazbeton tutkalı yazılmasın)
        mat = (item.group or "").split(":")[0].lower()
        code = {"ytong": "DUVAR_YTONG", "gazbeton": "DUVAR_YTONG", "tugla": "DUVAR_TUGLA", "bims": "DUVAR_BIMS",
                "alcipan": "DUVAR_ALCIPAN"}.get(mat)
        wit = catalog.get(code) if code else None
        if wit and wit.recipe:
            return list(wit.recipe)
    return list(RECIPES_BY_KIND.get(item.kind, []))


def expand_recipes(items: list[BoqItem], catalog: Catalog, storey_height: float | None = None,
                   off: bool = False) -> list[BoqItem]:
    """Kalem listesine reçete satırlarını ekler (var olanlar korunur). off=True: reçete kapalı.

    Seviye seviye açılır: bir derinlikteki tüm üst kalemler işlendikten sonra o derinlikte oluşan her alt kalem **bir kez**
    (toplanmış miktarıyla) bir sonraki seviyenin üst kalemi olur. Böylece aynı alt kaleme birden çok üst kalemden gelen
    katkılar torun kalemlerde tekrar çarpılmaz (170 lento 14 pozdan geliyorsa lento betonu yine 170 × 0,03'tür)."""
    if off:
        return items
    H = float(storey_height or 0.0)
    acc = _Acc()
    existing = {it.key for it in items}
    chains: dict[str, frozenset] = {it.key: frozenset([it.kind]) for it in items}
    frontier: list[BoqItem] = [it for it in items if not it.detail.get("recipe")]
    depth = 0
    while frontier and depth < RECIPE_MAX_DEPTH:
        new_keys: dict[str, frozenset] = {}
        for parent in frontier:
            if parent.quantity <= 0:
                continue
            chain = chains.get(parent.key, frozenset([parent.kind]))
            for comp in recipe_of(parent, catalog):
                code = comp["code"]
                kind = code.lower()
                if kind in chain:
                    continue
                cit = catalog.get(code)
                if not cit:
                    continue
                when = str(comp.get("when") or "")
                if when and parent.detail.get("opening_kind", "window") != when:
                    continue   # yalnız pencere (ya da yalnız kapı) pozlarına uygulanan bileşen
                factor = float(comp.get("factor") or 1.0)
                times = str(comp.get("times") or "").upper()
                times_h = times == "H"
                base = parent.quantity
                if times_h:
                    if H <= 0:
                        continue
                    factor *= H
                elif times in ("PER", "WID", "AREA"):
                    key_d = {"PER": "perimeter_m", "WID": "width_m", "AREA": "area_m2"}[times]
                    base = float(parent.detail.get(key_d) or 0.0)
                    if base <= 0:
                        continue   # boşluk ölçüsü bilinmiyor (poz ölçüsü okunmadı): çevre / genişlik kalemi yazılmaz
                spec = str(comp.get("spec") or "").strip()
                if spec == "$SIZE":
                    spec = str(parent.detail.get("size") or "")     # üst kalemin ölçüsü (körkasa 140x190, kasa 90x210)
                group = slug(spec) if spec else "*"
                qty = base * factor
                key = f"{kind}:{group}"
                first = key not in acc.items
                times_txt = {"H": " × H", "PER": " × boşluk çevresi", "WID": " × boşluk genişliği", "AREA": " × boşluk alanı"}.get(times, "")
                note = (f"Reçete varsayılanı: {parent.kind_label} × {float(comp.get('factor') or 1.0):g}{times_txt}"
                        + "; çarpan katalogdan düzenlenir") if first else None
                child = acc.add(kind, group, cit.name + (f" {spec}" if spec else ""), qty, note=note,
                                meta=(cit.name, cit.unit, f"ksf:{cit.discipline}", catalog.discipline_name(cit.discipline)),
                                poz=cit.poz, recipe=True, parents=1, **({"parent": parent.key, "depth": depth + 1} if first else {}),
                                **({"size": spec} if spec and comp.get("spec") == "$SIZE" else {}))
                src = child.detail.setdefault("from", [])
                if isinstance(src, list) and len(src) < 8 and parent.label not in src:
                    src.append(parent.label)
                new_keys[key] = new_keys.get(key, frozenset()) | chain | {kind}
        chains.update(new_keys)
        frontier = [acc.items[k] for k in new_keys]
        depth += 1
    out = list(items)
    for it in acc.items.values():
        if it.key in existing:
            # aynı kalem zaten ölçülmüş (ör. çizimde iskele çizilmiş): reçete miktarı üstüne eklenmez, not düşülür
            base = next(x for x in items if x.key == it.key)
            base.notes.append(f"Reçete de {it.quantity:,.1f} {it.unit} öneriyor (çizimden ölçülen esas alındı)")
            continue
        out.append(it)
    return out
