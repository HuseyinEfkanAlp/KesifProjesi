"""Keşif kalemi × (malzeme + işçilik birim fiyatı) = maliyet; × adam-saat/birim = süre.

**Malzeme** fiyatı ürüne girilir (C30/37 beton, Ø12 demir, Ytong 20 cm): kalemin ürünü cost.materials.material_of
ile bulunur, fiyatı ürün listesinden okunur. Aynı ürünü kullanan bütün kalemler tek fiyattan hesaplanır.
**İşçilik** fiyatı ve adam-saat keşif kalemine girilir; anahtarı "<tür>:<grup>" (bkz. quantity.boq), "<tür>:*"
o türün genel satırıdır ve kaleme özel değer girilmemişse uygulanır. Marka üründen gelir (raporda görünür).

Ürün fiyatı girilmemişse eski (ürün öncesi) kalem malzeme fiyatına düşülür; böylece eski projelerin girilmiş
fiyatları kaybolmaz.

Süre: kalem saati = miktar × adam-saat/birim; kalem günü = saat / (ekip × günlük saat).
  - "ardışık" toplam: tüm kalem günlerinin toplamı (tek ekip her işi sırayla yapar)
  - "disiplin bazlı": her disiplinin toplam günü; disiplinler paralel çalışırsa süre = en uzun disiplin

**Birimi "saat" olan kalemlerde miktar zaten adam-saattir** (reçeteden gelir: kalıp 800 m² × 1,2 = 960 saat);
adam-saat/birim girilmemişse 1,0 kabul edilir, yani süre fiyat girilmeden çıkar. Kullanıcı yine de bir değer
girerse (normu değiştirmek için) o değer geçerlidir.

Çift sayım: bir kalemin reçetesi işçilik kalemi doğuruyorsa (kalıp → kalıp işçiliği) ve kullanıcı ayrıca üst
kaleme adam-saat/birim girdiyse aynı iş iki kez sayılırdı. Üst kaleme açıkça girilen değer geçerlidir; o üst
kalemden gelen reçete işçiliği süreye katılmaz (satırda hours_source = "üst kalemde sayıldı").
"""
from __future__ import annotations

from dataclasses import dataclass

from ..quantity.boq import KIND_META, BoqItem
from .materials import MaterialData, is_labor_only, material_of

# Geriye uyumluluk (eski içe aktarmalar)
QUANTITY_KINDS: dict[str, tuple[str, str]] = {k: (v[0], v[1]) for k, v in KIND_META.items()}


@dataclass
class PriceItem:
    key: str
    name: str
    unit: str
    unit_price: float = 0.0        # malzeme
    labor_price: float = 0.0       # işçilik
    brand: str = ""
    hours_per_unit: float = 0.0    # adam-saat / birim
    crew_size: float = 0.0         # 0 = belirtilmedi (genel satır ya da 1 kişi)
    set_fields: tuple[str, ...] = ()   # kullanıcının açıkça girdiği alanlar: 0 girildiyse genel satıra düşülmez
    # ÇŞB / firma birim fiyatı: **her şey dahil** (malzeme + işçilik + makine + yüklenici kârı). Doluysa
    # malzeme ve işçiliğin yerine geçer — ikisini toplamak bedeli iki kez saymak olur.
    poz_price: float = 0.0


def default_price_items(items: list[BoqItem]) -> list[PriceItem]:
    """Keşifteki her kalem için sıfır fiyatlı satır + her tür için genel satır (kullanıcı doldurur)."""
    out: list[PriceItem] = []
    seen: set[str] = set()
    for it in items:
        if it.detail.get("system") or it.detail.get("info"):
            continue   # katmanlı sistem başlığı / bilgi satırı: fiyatlanmaz
        if it.kind not in seen:
            seen.add(it.kind)
            out.append(PriceItem(f"{it.kind}:*", f"{it.kind_label} (genel)", it.unit))
    for it in items:
        if it.group != "*" and not (it.detail.get("system") or it.detail.get("info")):
            out.append(PriceItem(it.key, it.label, it.unit))
    return out


def _missing_ranked(lines: list[dict]) -> dict:
    """Fiyatı girilmemiş kalemleri **etki sırasına** koyar: 65 satırlık düz liste kullanılabilir değildir.

    Sıralama uydurma fiyata dayanmaz — bildiğimiz büyüklükleri kullanır:
      * işçilik satırı saat cinsindeyse miktarın kendisi adam-saattir; doğrudan sıralanır
      * diğer kalemlerde hesaplanan adam-saat (miktar × norm) varsa o kullanılır
      * hiçbiri yoksa kalem kendi türü içinde miktara göre sıralanır (türler arası kıyas yapılmaz)
    Böylece kullanıcı "hangi 10 satırı doldurursam tutarın çoğu çıkar" sorusunu cevaplayabilir."""
    def row(l: dict, eksik: str) -> dict:
        return {"key": l["key"], "label": l["group_label"], "kind": l["kind"], "kind_label": l["kind_label"],
                "unit": l["unit"], "quantity": l["quantity"], "hours": l["hours"], "poz": l.get("poz", ""),
                "material_key": l.get("material_key", ""), "material_name": l.get("material_name", ""),
                "eksik": eksik}

    iscilik = [row(l, "isçilik") for l in lines if l["labor_price"] <= 0 and l["quantity"] > 0
               and not l.get("poz_priced")]
    iscilik.sort(key=lambda r: (-(r["hours"] or 0.0), -(r["quantity"] or 0.0)))
    # malzeme: aynı ürün birçok kalemde geçer; ürün bazında toplanır
    urun: dict[str, dict] = {}
    for l in lines:
        if l["unit_price"] > 0 or not l.get("material_key") or l["quantity"] <= 0 or l.get("poz_priced"):
            continue
        r = urun.setdefault(l["material_key"], {"key": l["material_key"], "name": l["material_name"] or l["material_key"],
                                                "unit": l["unit"], "quantity": 0.0, "kalem": 0})
        r["quantity"] += l["quantity"]
        r["kalem"] += 1
    malzeme = sorted(urun.values(), key=lambda r: -r["quantity"])
    for r in malzeme:
        r["quantity"] = round(r["quantity"], 2)
    return {"labor": iscilik, "materials": malzeme,
            "notice": "Sıralama kalemin büyüklüğüne göredir (adam-saat, yoksa miktar); tutar tahmini değildir. "
                      "Üstteki birkaç satır maliyetin çoğunu belirler."}


def compute_cost(items: list[BoqItem], prices: list[PriceItem], vat_rate: float = 0.0,
                 hours_per_day: float = 8.0, materials: list[MaterialData] | None = None,
                 params: dict | None = None) -> dict:
    price_map = {p.key: p for p in prices}
    mat_map = {m.key: m for m in (materials or [])}
    params = params or {}
    hours_per_day = hours_per_day if hours_per_day and hours_per_day > 0 else 8.0

    def explicit_hours(key: str) -> bool:
        """Kullanıcı bu kaleme kendi eliyle adam-saat/birim girdi mi?"""
        p = price_map.get(key)
        return bool(p) and (p.hours_per_unit or 0) > 0

    # üst kalemine açıkça adam-saat girilmiş reçete işçilikleri: saatleri orada sayıldı, burada tekrar sayılmaz
    covered: set[str] = set()
    for it in items:
        if is_labor_only(it) and it.detail.get("recipe"):
            pkeys = it.detail.get("parent_keys") or ([it.detail["parent"]] if it.detail.get("parent") else [])
            if pkeys and all(explicit_hours(k) for k in pkeys):
                covered.add(it.key)

    lines = []
    for it in items:
        if it.quantity <= 0 or it.detail.get("system") or it.detail.get("info"):
            continue
        own = price_map.get(it.key)
        gen = price_map.get(f"{it.kind}:*")

        def pick(attr: str, default=0.0):
            v = getattr(own, attr, None) if own else None
            explicit = bool(own) and attr in (getattr(own, "set_fields", None) or [])
            if explicit and v is not None:
                return v, "özel"           # açıkça girilen 0 da özeldir (işçiliği yok / ekip yok)
            if v not in (None, 0, 0.0, ""):
                return v, "özel"
            g = getattr(gen, attr, None) if gen else None
            if g not in (None, 0, 0.0, ""):
                return g, "genel"
            return default, "girilmedi"

        lab, lab_src = pick("labor_price")
        hpu, hpu_src = pick("hours_per_unit")
        labor_only = is_labor_only(it)
        if labor_only and not hpu:
            hpu, hpu_src = 1.0, "birim saat"    # miktarın kendisi adam-saat (reçete normundan)
        if it.key in covered:
            hpu, hpu_src = 0.0, "üst kalemde sayıldı"
        crew, crew_src = pick("crew_size", 0.0)
        if not crew:
            # Norm: bir ekipteki kişi sayısı. Kaç ekibin aynı anda çalışacağı saha kararıdır (crew_count).
            from ..standard.rules import crew_size as _crew
            crew = _crew(it.kind) * max(1.0, float((params or {}).get("crew_count") or 1))
            crew_src = "norm" if float((params or {}).get("crew_count") or 1) <= 1 else "norm × ekip sayısı"
        brand, _ = pick("brand", "")
        # malzeme: kalemin ürünü (C30/37 beton, Ø12 demir…) — fiyat ürün listesinden gelir
        m = material_of(it, params)
        mkey, mname = m if m else ("", "")
        mrec = mat_map.get(mkey) if mkey else None
        mat = float(mrec.unit_price or 0.0) if mrec else 0.0
        mat_src = "ürün" if mat > 0 else ("malzemesiz" if not mkey else "fiyat girilmedi")
        if mrec and mrec.brand:
            brand = mrec.brand
        hours = it.quantity * float(hpu)
        days = hours / (max(float(crew), 0.01) * hours_per_day) if hours > 0 else 0.0
        poz_bf, poz_src = pick("poz_price")
        if poz_bf and float(poz_bf) > 0:
            # Poz bedeli her şeyi kapsar: malzeme + işçilik ayrı ayrı yazılmaz, tek satır poz bedelidir.
            mat_total = 0.0
            lab_total = round(it.quantity * float(poz_bf), 2)
            mat, lab = 0.0, float(poz_bf)
            mat_src = f"poz bedeli ({it.poz})" if it.poz else "poz bedeli"
            lab_src = mat_src
        else:
            mat_total = round(it.quantity * float(mat), 2)
            lab_total = round(it.quantity * float(lab), 2)
        lines.append({
            "key": it.key, "kind": it.kind, "kind_label": it.kind_label,
            "group": it.group, "group_label": it.label, "discipline": it.discipline,
            "discipline_label": it.discipline_label,
            "unit": it.unit, "quantity": round(it.quantity, 3),
            "work_group": it.work_group, "work_group_label": it.to_dict()["work_group_label"], "poz": it.poz,
            "recipe": bool(it.detail.get("recipe")),
            "brand": brand or "",
            "material_key": mkey, "material_name": mname,
            "unit_price": float(mat), "labor_price": float(lab),
            "poz_price": float(poz_bf or 0.0), "poz_priced": bool(poz_bf and float(poz_bf) > 0),
            "material_total": mat_total, "labor_total": lab_total, "total": round(mat_total + lab_total, 2),
            "price_source": mat_src,
            "labor_source": lab_src if lab else "işçilik girilmedi",
            "hours_per_unit": float(hpu), "crew_size": float(crew), "hours_source": hpu_src,
            "crew_source": crew_src,
            "hours": round(hours, 1), "days": round(days, 2),
        })
    material_subtotal = round(sum(l["material_total"] for l in lines), 2)
    labor_subtotal = round(sum(l["labor_total"] for l in lines), 2)
    subtotal = round(material_subtotal + labor_subtotal, 2)
    vat = round(subtotal * vat_rate, 2)
    by_kind: dict[str, float] = {}
    by_disc: dict[str, dict] = {}
    by_group: dict[str, dict] = {}
    by_mat: dict[str, dict] = {}
    for l in lines:
        if l["material_key"]:
            m = by_mat.setdefault(l["material_key"], {"key": l["material_key"], "name": l["material_name"],
                                                      "unit": l["unit"], "brand": l["brand"], "unit_price": l["unit_price"],
                                                      "quantity": 0.0, "total": 0.0, "lines": 0})
            m["quantity"] = round(m["quantity"] + l["quantity"], 3)
            m["total"] = round(m["total"] + l["material_total"], 2)
            m["lines"] += 1
        by_kind[l["kind"]] = round(by_kind.get(l["kind"], 0.0) + l["total"], 2)
        g = by_group.setdefault(l["work_group"], {"group": l["work_group"], "label": l["work_group_label"],
                                                  "material": 0.0, "labor": 0.0, "total": 0.0, "hours": 0.0, "days": 0.0, "lines": 0})
        g["material"] = round(g["material"] + l["material_total"], 2)
        g["labor"] = round(g["labor"] + l["labor_total"], 2)
        g["total"] = round(g["total"] + l["total"], 2)
        g["hours"] = round(g["hours"] + l["hours"], 1)
        g["days"] = round(g["days"] + l["days"], 2)
        g["lines"] += 1
        d = by_disc.setdefault(l["discipline"], {"discipline": l["discipline"], "label": l["discipline_label"],
                                                 "material": 0.0, "labor": 0.0, "total": 0.0, "hours": 0.0, "days": 0.0})
        d["material"] = round(d["material"] + l["material_total"], 2)
        d["labor"] = round(d["labor"] + l["labor_total"], 2)
        d["total"] = round(d["total"] + l["total"], 2)
        d["hours"] = round(d["hours"] + l["hours"], 1)
        d["days"] = round(d["days"] + l["days"], 2)
    total_hours = round(sum(l["hours"] for l in lines), 1)
    # ekip girilmemiş kalemde "gün" aslında adam-gündür (1 kişi varsayımı); takvim günü için ekip gerekir
    missing_crew = [l["key"] for l in lines if l["hours"] > 0 and l["crew_source"] == "girilmedi"]
    sequential_days = round(sum(l["days"] for l in lines), 1)
    parallel_days = round(max((d["days"] for d in by_disc.values()), default=0.0), 1)
    return {
        "lines": lines,
        "material_subtotal": material_subtotal, "labor_subtotal": labor_subtotal,
        "subtotal": subtotal, "vat_rate": vat_rate, "vat": vat,
        "grand_total": round(subtotal + vat, 2),
        "by_kind": by_kind,
        "by_material": sorted(by_mat.values(), key=lambda m: -m["total"]),
        "by_discipline": list(by_disc.values()),
        "by_group": list(by_group.values()),
        "missing_prices": [l["key"] for l in lines if l["unit_price"] <= 0 and l["material_key"]],
        "missing_materials": sorted({l["material_key"] for l in lines if l["unit_price"] <= 0 and l["material_key"]}),
        "missing_labor": [l["key"] for l in lines if l["labor_price"] <= 0],
        "missing_ranked": _missing_ranked(lines),
        "duration": {
            "hours_per_day": hours_per_day,
            "total_hours": total_hours,
            "sequential_days": sequential_days,
            "parallel_days": parallel_days,
            "man_days": round(total_hours / hours_per_day, 1),
            # Bu süreyi tutturmak için sahada ortalama kaç kişi olmalı: kullanıcı gerçekçiliği buradan görür
            "implied_headcount": round(total_hours / (parallel_days * hours_per_day), 1) if parallel_days > 0 else 0.0,
            "crew_count": float((params or {}).get("crew_count") or 1),
            "missing_rates": [l["key"] for l in lines if l["hours_per_unit"] <= 0
                              and l["hours_source"] != "üst kalemde sayıldı"],
            "missing_crew": missing_crew,
            # Ekibi programın normundan gelen kalemler: kullanıcı girişi değildir, doğrulanmalıdır
            "norm_crew": [l["key"] for l in lines if l["hours"] > 0 and str(l["crew_source"]).startswith("norm")],
        },
    }
