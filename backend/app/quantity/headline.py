"""Ana kalemler: beton, kalıp, demir, duvar — "ne kadar, neyden, ne kadarı ölçüldü".

Keşif listesi 70+ satırdır; sahada sorulan dört sayı onun içinde kaybolur. Bu modül her ana kalem için
demir raporuyla aynı üç şeyi üretir:

  başlık sayısı   — sipariş edilecek / uygulanacak miktar
  ayrıştırma      — brüt, düşülen boşluk, fire; hangisi ölçüm hangisi varsayım
  döküm           — betonda eleman grubu, demirde çap, duvarda malzeme + kalınlık

`net` her zaman **ölçülen** miktardır; `total` sipariş miktarıdır (fire dahil). Duvarda ayrıca brüt ve
düşülen boşluk durur: boşluğu çizimde duvar kesilerek gösterilmiş bir projede düşülen 0'dır ve bu bir
eksiklik değildir (bkz. quantity/openings.py) — o yüzden "zaten net" ayrı bir sütundur.
"""
from __future__ import annotations

from . import rebar_report

# kalem -> (başlık, o kalemin işçilik türleri, o kaleme bağlı sarf türleri)
SECTIONS: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = [
    ("beton", "Beton", ("beton_iscilik", "vibrator"), ("beton_kur", "beton_pompaj", "grobeton")),
    ("kalip", "Kalıp", ("kalip_kurma", "kalip_imalat", "kalip_sokum"), ("plywood", "kalip_yagi", "civi", "kalip_iskelesi")),
    ("demir", "Demir", rebar_report.LABOUR_KINDS, rebar_report.EXTRA_KINDS),
    ("duvar", "Duvar", ("duvar_iscilik",), ("duvar_tutkal",)),
    ("siva", "Sıva", ("siva_iscilik",), ("astar",)),
    ("boya", "Boya", ("boya_iscilik",), ()),
]
# "fire" grubu ayrı sayılır: metraj değil, kesim / döküm kaybıdır
WASTE_GROUP = "fire"


def _hours(items, kinds: tuple[str, ...]) -> list[dict]:
    out = [{"key": it.kind, "label": it.label, "hours": it.quantity}
           for it in items if it.kind in kinds and it.unit == "saat" and it.quantity]
    out.sort(key=lambda x: kinds.index(x["key"]))
    return out


def _extras(items, kinds: tuple[str, ...]) -> list[dict]:
    """Sarf kalemleri çapa / sınıfa bölünmüş gelebilir; türe göre tek satırda toplanır."""
    acc: dict[str, dict] = {}
    for it in items:
        if it.kind not in kinds or not it.quantity:
            continue
        cur = acc.setdefault(it.kind, {"key": it.kind, "label": it.kind_label or it.label,
                                       "quantity": 0.0, "unit": it.unit})
        cur["quantity"] += it.quantity
    return [{**v, "quantity": round(v["quantity"], 2)} for v in acc.values()]


def _wall_rows(items) -> tuple[list[dict], dict]:
    """Duvar: malzeme + kalınlık bazında net, brüt, düşülen boşluk ve "zaten net" alan."""
    rows, tot = [], {"gross": 0.0, "deducted": 0.0, "already_net": 0.0}
    for it in items:
        if it.kind != "duvar" or not it.quantity:
            continue
        d = it.detail or {}
        g = float(d.get("gross_m2") or it.quantity)
        ded = float(d.get("openings_m2") or 0.0)
        an = float(d.get("openings_already_net_m2") or 0.0)
        tot["gross"] += g
        tot["deducted"] += ded
        tot["already_net"] += an
        rows.append({"label": it.label, "quantity": it.quantity, "gross_m2": round(g, 2),
                     "openings_m2": round(ded, 2), "already_net_m2": round(an, 2),
                     "review": bool(d.get("openings_review_required"))})
    rows.sort(key=lambda r: -r["quantity"])
    return rows, tot


def _group_rows(items, kind: str) -> tuple[list[dict], float, float]:
    """Eleman grubu bazında döküm; fire ayrı. (satırlar, net, fire) döner."""
    rows, net, waste = [], 0.0, 0.0
    for it in items:
        if it.kind != kind or not it.quantity:
            continue
        if it.group.split(":")[0] == WASTE_GROUP:
            waste += it.quantity
            continue
        net += it.quantity
        rows.append({"label": it.label, "quantity": it.quantity, "count": it.count or 0})
    rows.sort(key=lambda r: -r["quantity"])
    return rows, net, waste


def build(items, summary: dict | None = None) -> list[dict]:
    """Ana kalemlerin listesi; miktarı olmayan kalem listeye girmez."""
    out: list[dict] = []
    for kind, label, labour_kinds, extra_kinds in SECTIONS:
        if not any(it.kind == kind and it.quantity for it in items):
            continue
        unit = next(it.unit for it in items if it.kind == kind and it.quantity)
        sec = {"kind": kind, "label": label, "unit": unit, "rows": [],
               "labour": _hours(items, labour_kinds), "extras": _extras(items, extra_kinds)}
        sec["labour_hours"] = round(sum(x["hours"] for x in sec["labour"]), 2)
        if kind == "demir":
            r = rebar_report.build(items, summary)
            sec["rows"] = [{"label": f"Ø{x['dia_mm']}", "quantity": x["order_kg"], **x} for x in r["rows"]]
            sec["net"], sec["waste"] = r["totals"]["metraj_kg"] + r["totals"]["ratio_kg"], r["totals"]["fire_kg"]
            sec["total"] = r["totals"]["order_kg"]
            sec["estimated"] = r["totals"]["ratio_kg"]
            sec["unsized"] = r["unsized"]
        elif kind == "duvar":
            rows, tot = _wall_rows(items)
            sec["rows"] = rows
            sec["net"] = sec["total"] = round(sum(r["quantity"] for r in rows), 3)
            sec["waste"] = 0.0
            sec["gross"] = round(tot["gross"], 3)
            sec["deducted"] = round(tot["deducted"], 3)
            sec["already_net"] = round(tot["already_net"], 3)
        else:
            rows, net, waste = _group_rows(items, kind)
            sec["rows"] = rows
            sec["net"], sec["waste"] = round(net, 3), round(waste, 3)
            sec["total"] = round(net + waste, 3)
        out.append(sec)
    return out
