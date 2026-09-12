"""Demir raporu: "toplamda kaç ton, hangi çaptan kaç kilo" tek yerde.

Keşif listesinde demir üç ayrı yerde durur — donatı tablosundan / poz yazılarından okunan gerçek miktar
(`demir:o12`), donatı paftası olmayan elemanın beton × oran tahmini (`demir:shear_wall:o12`) ve kesim firesi
(`demir:fire:o12`). Sipariş verilecek sayı üçünün toplamıdır; metraj kontrolü için ise fireden arınmış sayı
gerekir. Bu modül ikisini de çap bazında yan yana koyar, demir işçiliğini (hazırlık / taşıma / montaj) ve
demire bağlı sarf kalemlerini (bağ teli, sehpa demiri) ekler.

Çapa bölünemeyen demir ("çizimde donatı yazısı yok, çap dağılımı okunamadı") ayrı satırda durur; toplama girer
ama hangi çaptan sipariş verileceği bilinmez — bu bilgi kaybolmasın diye gizlenmez.
"""
from __future__ import annotations

import re

from ..parser.layer_profile import ELEMENT_TYPES

# demir kaleminin anahtarı: "o12" (tablo/poz), "fire:o12", "shear_wall:o12" (oranla), "fire", "shear_wall"
_DIA = re.compile(r"(?:^|:)o(\d{1,2})$")
# demir işçiliği türleri, keşifteki sırasıyla
LABOUR_KINDS = ("demir_hazirlik", "demir_tasima", "demir_montaj")
# demire bağlı sarf / yardımcı malzeme
EXTRA_KINDS = ("bag_teli", "sehpa_demiri")
SOURCE_LABEL = {"tablo": "donatı tablosu", "poz": "poz yazıları", "elle": "elle girildi", "oran": "beton × oran"}


def _dia_of(group: str) -> int | None:
    m = _DIA.search(group or "")
    return int(m.group(1)) if m else None


def _bucket(item) -> str:
    """Kalemin hangi sütuna gireceği: metraj (ölçülen), oran (tahmin) ya da fire.

    Kaynak kalemin kendi işaretinden okunur (`detail["rebar_source"]`); anahtarın biçiminden tahmin etmek
    kırılgandı — KSF katmanından **ölçülen** "demir:12" oran sanılıp düşük güvenli gösteriliyordu."""
    if (item.group or "").split(":")[0] == "fire":
        return "fire_kg"
    return "ratio_kg" if (item.detail or {}).get("rebar_source") == "oran" else "metraj_kg"


def build(items, summary: dict | None = None) -> dict:
    """BoqItem listesinden çap bazında demir raporu. `summary` verilirse çapın uzunluğu ve hangi elemanda
    olduğu da yazılır (summary["rebar_by_dia"])."""
    summary = summary or {}
    by_dia: dict[int, dict] = {}
    unsized = {"metraj_kg": 0.0, "ratio_kg": 0.0, "fire_kg": 0.0, "groups": []}

    def row(d: int) -> dict:
        return by_dia.setdefault(d, {"dia_mm": d, "metraj_kg": 0.0, "ratio_kg": 0.0, "fire_kg": 0.0,
                                     "length_m": 0.0, "targets": {}, "sources": {}})

    for it in items:
        if it.kind != "demir" or not it.quantity:
            continue
        d = _dia_of(it.group)
        col = _bucket(it)
        if d is None:
            unsized[col] += it.quantity
            if it.label not in unsized["groups"]:
                unsized["groups"].append(it.label)
            continue
        row(d)[col] += it.quantity

    for d in summary.get("rebar_by_dia", []) or []:
        r = by_dia.get(int(d["dia_mm"]))
        if r is None:
            continue
        r["length_m"] = float(d.get("length_m") or 0.0)
        r["targets"] = {ELEMENT_TYPES.get(k, k): v for k, v in (d.get("targets") or {}).items()}
        r["sources"] = {SOURCE_LABEL.get(k, k): v for k, v in (d.get("sources") or {}).items()}

    rows = []
    for r in sorted(by_dia.values(), key=lambda x: x["dia_mm"]):
        r["order_kg"] = r["metraj_kg"] + r["ratio_kg"] + r["fire_kg"]
        if r["order_kg"] > 0:
            rows.append(r)
    totals = {k: round(sum(r[k] for r in rows) + (unsized[k] if k in unsized else 0.0), 3)
              for k in ("metraj_kg", "ratio_kg", "fire_kg")}
    totals["order_kg"] = round(totals["metraj_kg"] + totals["ratio_kg"] + totals["fire_kg"], 3)

    labour = [{"key": it.kind, "label": it.label, "hours": it.quantity}
              for it in items if it.kind in LABOUR_KINDS and it.quantity]
    labour.sort(key=lambda x: LABOUR_KINDS.index(x["key"]))
    # sarf kalemleri çapa bölünmüş olabilir (sehpa demiri Ø başına bir satır); türe göre toplanır
    ex: dict[str, dict] = {}
    for it in items:
        if it.kind not in EXTRA_KINDS or not it.quantity:
            continue
        cur = ex.setdefault(it.kind, {"key": it.kind, "label": it.kind_label or it.label, "quantity": 0.0, "unit": it.unit})
        cur["quantity"] += it.quantity
    extras = [{**v, "quantity": round(v["quantity"], 2)} for v in ex.values()]
    return {"rows": rows, "totals": totals,
            "unsized": unsized if (unsized["metraj_kg"] or unsized["ratio_kg"] or unsized["fire_kg"]) else None,
            "labour": labour, "labour_hours": round(sum(x["hours"] for x in labour), 2), "extras": extras}
