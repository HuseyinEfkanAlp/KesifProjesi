"""Keşif listesi (bill of quantities): tüm disiplinlerin metrajını tek tip kalem listesine çevirir.

Kalem anahtarı "<tür>:<grup>" biçimindedir; tür fiyat kategorisidir (beton, kalip, demir, duvar, siva, boya, pencere,
cam, kapi, tava, kablo, boru, armatur), grup eleman grubudur (kolon, ytong:20, NYY_4x16, 200x60, priz ...).
"<tür>:*" fiyat kalemi o türün genel fiyatıdır.

Statik:  beton / kalıp / demir (quantity.engine + summary'den)
Mimari:  duvar m² = uzunluk × duvar yüksekliği × kat çarpanı − kapı/pencere boşlukları (malzeme + kalınlık bazında)
         sıva m² = net duvar × sıva yüzü sayısı, boya m² = net duvar × boya yüzü sayısı
         pencere adet (ad / ölçü bazında), cam m² = pencere genişlik × yükseklik, kapı adet
Elektrik: tava m (boyut bazında), kablo m (kesit bazında; iniş payı × hat sayısı, fire %), boru m, armatür adet (kategori)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..parser.labels_ext import FIXTURE_CATEGORIES, WALL_MATERIALS
from ..parser.layer_profile import DISCIPLINES, ELEMENT_TYPES
from ..standard.catalog import Catalog, parse_layer, spec_numbers
from ..standard.rules import RULES, WORK_GROUPS, WORK_GROUP_ORDER, deductible_opening, default_poz, work_group_of

# tür -> (görünen ad, birim, disiplin)
KIND_META: dict[str, tuple[str, str, str]] = {
    "beton": ("Beton", "m³", "structural"),
    "kalip": ("Kalıp", "m²", "structural"),
    "demir": ("Demir", "kg", "structural"),
    "bag_teli": ("Bağ teli", "kg", "structural"),
    "plywood": ("Plywood kalıp levhası", "adet", "structural"),
    "kalip_yagi": ("Kalıp yağı", "L", "structural"),
    "civi": ("Çivi / kalıp aksesuarı", "kg", "structural"),
    "duvar": ("Duvar", "m²", "architectural"),
    "siva": ("Sıva", "m²", "architectural"),
    "boya": ("Boya", "m²", "architectural"),
    "pencere": ("Pencere", "adet", "architectural"),
    "cam": ("Cam", "m²", "architectural"),
    "kapi": ("Kapı", "adet", "architectural"),
    "tava": ("Kablo tavası", "m", "electrical"),
    "kablo": ("Kablo", "m", "electrical"),
    "boru": ("Boru", "m", "electrical"),
    "armatur": ("Armatür / priz / anahtar", "adet", "electrical"),
}

DEFAULT_PARAMS: dict[str, Any] = {
    "wall_height": None,          # m; None -> kat yüksekliği − döşeme kalınlığı
    "plaster_sides": 2,           # sıva yüzü sayısı (0 = sıva yok)
    "paint_sides": 2,             # boya yüzü sayısı
    "cable_drop": 0.0,            # her kablo hattına eklenen iniş/çıkış payı (m)
    "cable_waste_pct": 5.0,       # kablo fire %
    "tray_waste_pct": 5.0,
    "work_hours_per_day": 8.0,    # süre hesabı: günlük çalışma saati
    # sarf / fire (statik)
    "concrete_waste_pct": 3.0,    # beton fire %
    "rebar_waste_pct": 5.0,       # demir fire % (bindirme + kesim)
    "tie_wire_kg_per_t": 8.0,     # bağ teli: kg / ton demir
    "plywood_sheet_m2": 3.125,    # 125 x 250 cm levha
    "formwork_reuse": 5.0,        # bir levhanın kullanım sayısı
    "formwork_oil_l_per_m2": 0.05,   # kalıp yağı L / m² (her kullanımda)
    "nails_kg_per_m2": 0.10,      # çivi / aksesuar kg / m² kalıp
    # cephe
    "facade_gross_m2": None,      # brüt cephe alanı (m²); None -> görünüşteki CEPHE_BRUT kalemi, yoksa kalıp planı oturum çevresi × H
    "facade_system": "",          # cephe sistemi katalog kodu (MANTOLAMA_SISTEM, KOMPOZIT_PANEL…); miktarı net cephe alanından
    # çatı
    "roof_area_m2": None,         # çatı alanı (m²); None -> ölçülen çatı kalemi, yoksa en üst kat planı oturumu
    "roof_system": "",            # çatı sistemi kodu (KENET_CATI / KIREMIT_CATI / TERAS_CATI …); boş -> kesit notlarından
    # türetilmiş kalemler
    "finish_rooms": "",           # şap / kaplama yapılan mahal türleri (virgülle; boş -> LOBİ, VİTRİN, GİRİŞ, HOL, KORİDOR, FUAYE)
    "finish_area_m2": None,       # şap / kaplama alanı elle (m²); doluysa mahal yazıları kullanılmaz
    "screed_cm": 5.0,             # şap kalınlığı (cm) — seçili mahal alanından türetilir
    "lean_concrete_cm": 10.0,     # grobeton kalınlığı (cm) — temel alanından türetilir
    "excavation_depth_m": 1.5,    # temel altı kazı derinliği (m; 0 = kazı türetme) — temel alanı × derinlik × şev / çalışma payı
    "excavation_margin": 1.15,    # kazı şev + çalışma payı çarpanı
    "derived_off": "",            # kapatılan türetme kuralları (virgülle: astar,tavan,sap,kaplama,temel_yalitim,grobeton,koruma_sapi,kazi,geri_dolgu,recete)
}


def effective_params(raw: dict[str, Any] | None) -> dict[str, Any]:
    p = dict(DEFAULT_PARAMS)
    for k, v in (raw or {}).items():
        if k in p:
            p[k] = v
    return p


def slug(s: str) -> str:
    s = s.strip().replace("ı", "i").replace("İ", "I").replace("ş", "s").replace("Ş", "S").replace("ğ", "g").replace("Ğ", "G")
    s = s.replace("ç", "c").replace("Ç", "C").replace("ö", "o").replace("Ö", "O").replace("ü", "u").replace("Ü", "U")
    s = re.sub(r"[ØøΦφ∅]", "o", s)
    s = re.sub(r"[^A-Za-z0-9.+/x×-]+", "_", s)
    return s.strip("_").lower() or "x"


@dataclass
class BoqItem:
    key: str
    kind: str
    group: str
    label: str
    unit: str
    quantity: float
    discipline: str
    kind_label: str = ""
    discipline_label: str = ""
    count: float = 0.0                     # adet (eleman/hat sayısı) bilgi amaçlı
    notes: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    poz: str = ""                          # ÇŞB poz numarası (katalogdan ya da varsayılan eşlemeden)
    poz_name: str = ""
    work_group: str = ""                   # KABA / INCE / MEK / ELK / ALT

    def __post_init__(self):
        if not self.kind_label:
            self.kind_label = KIND_META.get(self.kind, (self.kind,))[0]
        if not self.discipline_label:
            self.discipline_label = DISCIPLINES.get(self.discipline, self.discipline)
        if not self.work_group:
            self.work_group = work_group_of(self.discipline)
        if not self.poz:
            dp = default_poz(self.kind, self.group)
            if dp:
                self.poz, self.poz_name = dp

    def to_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "kind_label": self.kind_label, "group": self.group,
                "label": self.label, "unit": self.unit, "quantity": round(self.quantity, 3), "count": self.count,
                "discipline": self.discipline, "discipline_label": self.discipline_label,
                "work_group": self.work_group, "work_group_label": WORK_GROUPS.get(self.work_group, self.work_group),
                "poz": self.poz, "poz_name": self.poz_name,
                "notes": self.notes, "detail": self.detail}


class _Acc:
    def __init__(self):
        self.items: dict[str, BoqItem] = {}

    def add(self, kind: str, group: str, label: str, qty: float, count: float = 0.0, note: str | None = None,
            meta: tuple[str, str, str, str] | None = None, poz: str = "", **detail) -> BoqItem:
        """meta: (tür adı, birim, disiplin kodu, disiplin adı) — KIND_META dışındaki (katalog) kalemler için.
        poz: katalogdan gelen ÇŞB poz numarası (boşsa varsayılan eşleme)."""
        key = f"{kind}:{group}"
        it = self.items.get(key)
        if it is None:
            if meta:
                kname, unit, disc, dlabel = meta
            else:
                kname, unit, disc = KIND_META[kind]
                dlabel = DISCIPLINES.get(disc, disc)
            it = BoqItem(key=key, kind=kind, group=group, label=label, unit=unit, quantity=0.0, discipline=disc,
                         kind_label=kname, discipline_label=dlabel, poz=poz)
            self.items[key] = it
        it.quantity += qty
        it.count += count
        if note and note not in it.notes:
            it.notes.append(note)
        for k, v in detail.items():
            it.detail[k] = it.detail.get(k, 0) + v if isinstance(v, (int, float)) else v
        return it


# ------------------------------------------------------------------ statik

def structural_items(summary: dict, params: dict[str, Any] | None = None) -> list[BoqItem]:
    """Beton / kalıp / demir + fire ve sarf (bağ teli, plywood, kalıp yağı, çivi).

    Demir: donatı tablosu olan eleman tiplerinde çap bazında (demir:o12 …), tablosu olmayanlarda eleman grubu bazında oranla."""
    params = effective_params(params)
    acc = _Acc()
    for g in summary.get("groups", []):
        if g.get("concrete_m3", 0) > 0:
            acc.add("beton", g["key"], f"Beton - {g['label']}", g["concrete_m3"], count=g.get("element_count", 0),
                    note=RULES["concrete"].text)
        if g.get("formwork_m2", 0) > 0:
            acc.add("kalip", g["key"], f"Kalıp - {g['label']}", g["formwork_m2"], count=g.get("element_count", 0),
                    note=RULES["formwork"].text)
        if g.get("rebar_kg", 0) > 0 and g.get("rebar_source", "oran") == "oran":
            acc.add("demir", g["key"], f"Demir - {g['label']} (oranla)", g["rebar_kg"], count=g.get("element_count", 0),
                    note="Beton × kg/m³ oranı; donatı paftası yüklenince tablodan alınır")
    for d in summary.get("rebar_by_dia", []):
        tg = ", ".join(f"{ELEMENT_TYPES.get(k, k)} {v/1000:.1f} t" for k, v in d["targets"].items())
        acc.add("demir", f"o{d['dia_mm']}", f"Demir Ø{d['dia_mm']}", d["weight_kg"], count=0,
                note=f"Donatı tablosundan; {tg}", length_m=d["length_m"])
    tot = summary.get("totals", {})
    conc = float(tot.get("concrete_m3") or 0.0)
    form = float(tot.get("formwork_m2") or 0.0)
    rebar = float(tot.get("rebar_kg") or 0.0)
    cw = float(params.get("concrete_waste_pct") or 0.0)
    rw = float(params.get("rebar_waste_pct") or 0.0)
    if conc > 0 and cw > 0:
        acc.add("beton", "fire", f"Beton fire (%{cw:g})", conc * cw / 100.0, note="Toplam beton × fire yüzdesi")
    if rebar > 0 and rw > 0:
        acc.add("demir", "fire", f"Demir fire / bindirme (%{rw:g})", rebar * rw / 100.0, note="Toplam demir × fire yüzdesi")
    if rebar > 0:
        tw = float(params.get("tie_wire_kg_per_t") or 0.0)
        if tw > 0:
            acc.add("bag_teli", "*", "Bağ teli", rebar / 1000.0 * tw, note=f"{tw:g} kg / ton demir")
    if form > 0:
        sheet = float(params.get("plywood_sheet_m2") or 3.125)
        reuse = max(float(params.get("formwork_reuse") or 1.0), 1.0)
        acc.add("plywood", "*", f"Plywood levha ({sheet:g} m², {reuse:g} kullanım)", form / sheet / reuse, count=0,
                note=f"Kalıp {form:,.0f} m² / {sheet:g} m² / {reuse:g} kullanım")
        oil = float(params.get("formwork_oil_l_per_m2") or 0.0)
        if oil > 0:
            acc.add("kalip_yagi", "*", "Kalıp yağı", form * oil, note=f"{oil:g} L / m² kalıp")
        nails = float(params.get("nails_kg_per_m2") or 0.0)
        if nails > 0:
            acc.add("civi", "*", "Çivi / kalıp aksesuarı", form * nails, note=f"{nails:g} kg / m² kalıp")
    return list(acc.items.values())


# ------------------------------------------------------------------ mimari

def _fmt_cm(v: float | None) -> str:
    return f"{round(v * 100):.0f}" if v else "?"


def architectural_items(drawings: list[dict], params: dict[str, Any], schedule_poz: set[str] | None = None) -> list[BoqItem]:
    """drawings: [{"label", "storey_count", "storey_height", "slab_thickness", "elements": [Element-benzeri]}]
    schedule_poz: doğrama poz listesinde geçen pozlar; plandan sayılan bu pozlu boşluklar duvardan düşülür ama adet ve
    cam poz listesinden (proje toplamı) gelir, burada tekrar yazılmaz."""
    acc = _Acc()
    schedule_poz = schedule_poz or set()
    for d in drawings:
        mult = int(d.get("storey_count") or 1)
        wall_h = params.get("wall_height") or max((d.get("storey_height") or 3.0) - (d.get("slab_thickness") or 0.0), 0.0)
        src = str(d.get("height_source") or "")
        h_note = None if params.get("wall_height") or src in ("", "parametre", "çizime girildi") else f"Kat yüksekliği {d.get('storey_height'):g} m: {src}"
        elements = [e for e in d["elements"] if _g(e, "etype") in ("wall", "door", "window")]
        wall_groups: dict[str, float] = {}      # anahtar -> brüt alan (tek kat)
        wall_labels: dict[str, str] = {}
        for e in elements:
            if _g(e, "etype") != "wall":
                continue
            b = _g(e, "b") or 0.2
            length = _g(e, "length") or 0.0
            h = _g(e, "h") or wall_h                 # duvar elemanına özel yükseklik girilmişse o
            mat = _g(e, "subtype") or "duvar"
            key = f"{slug(mat)}:{_fmt_cm(b)}"
            mat_label = WALL_MATERIALS.get(mat, (mat.capitalize(),))[0] if mat != "duvar" else "Duvar (malzeme belirsiz)"
            wall_groups[key] = wall_groups.get(key, 0.0) + length * h * (_g(e, "count") or 1)
            wall_labels[key] = f"{mat_label} {_fmt_cm(b)} cm"
        opening_area = 0.0        # duvardan düşülen boşluk (0,10 m² ve üstü; ÇŞB 15.225)
        opening_all = 0.0         # sıva / boyadan düşülen boşluk (tümü; ÇŞB 15.280 / 15.540)
        small_openings = 0
        for e in elements:
            et = _g(e, "etype")
            if et not in ("door", "window"):
                continue
            b, h = _g(e, "b") or 0.0, _g(e, "h") or 0.0
            n = _g(e, "count") or 1
            area = b * h * n
            opening_all += area
            if deductible_opening(b * h):
                opening_area += area
            else:
                small_openings += n
            if (_g(e, "meta") or {}).get("poz") in schedule_poz:
                continue
            name = _g(e, "name") or f"{_fmt_cm(b)}x{_fmt_cm(h)}"
            group = slug(f"{name}_{_fmt_cm(b)}x{_fmt_cm(h)}")
            kind = "kapi" if et == "door" else "pencere"
            acc.add(kind, group, f"{KIND_META[kind][0]} {name} ({_fmt_cm(b)}×{_fmt_cm(h)} cm)", n * mult, count=n * mult,
                    width_cm=0, area_m2=area * mult, perimeter_m=2 * (b + h) * n * mult, width_m=b * n * mult)
            if et == "window":
                acc.add("cam", "*", "Cam (pencere alanı)", area * mult, count=n * mult,
                        note="Pencere genişlik × yükseklik; doğrama payı düşülmedi")
        gross = sum(wall_groups.values())
        # boşluklar duvar gruplarından alanlarıyla orantılı düşülür (0,10 m² altı boşluk düşülmez: ÇŞB 15.225)
        net_total = 0.0
        for key, area in wall_groups.items():
            share = opening_area * (area / gross) if gross > 0 else 0.0
            net = max(area - share, 0.0) * mult
            net_total += net
            it = acc.add("duvar", key, wall_labels[key], net, gross_m2=area * mult, openings_m2=share * mult)
            # pafta bazlı döküm nota değil ayrıntıya yazılır (not sütunu kural ve uyarı için)
            it.detail.setdefault("by_drawing", []).append(
                {"drawing": d.get("label", ""), "gross_m2": round(area * mult, 2), "openings_m2": round(share * mult, 2), "net_m2": round(net, 2)})
            if h_note and h_note not in it.notes:
                it.notes.append(h_note)
            rule = RULES["wall_opening"].text
            if rule not in it.notes:
                it.notes.append(rule)
            if small_openings:
                it.detail["small_openings"] = it.detail.get("small_openings", 0) + small_openings
        if gross > 0:
            # sıva ve boya: tüm boşluklar düşülür (küçükler dahil), yüz sayısı ile çarpılır
            finish_net = max(gross - opening_all, 0.0) * mult
            ps, bs = float(params.get("plaster_sides") or 0), float(params.get("paint_sides") or 0)
            if ps > 0 and finish_net > 0:
                acc.add("siva", "*", f"Sıva ({ps:g} yüz)", finish_net * ps, note=RULES["plaster_openings"].text + "; × yüz sayısı")
            if bs > 0 and finish_net > 0:
                acc.add("boya", "*", f"Boya ({bs:g} yüz)", finish_net * bs, note=RULES["paint_openings"].text + "; × yüz sayısı")
    return list(acc.items.values())


# ------------------------------------------------------------------ elektrik

def electrical_items(drawings: list[dict], params: dict[str, Any]) -> list[BoqItem]:
    acc = _Acc()
    drop = float(params.get("cable_drop") or 0.0)
    cw = 1.0 + float(params.get("cable_waste_pct") or 0.0) / 100.0
    tw = 1.0 + float(params.get("tray_waste_pct") or 0.0) / 100.0
    for d in drawings:
        mult = int(d.get("storey_count") or 1)
        for e in d["elements"]:
            et = _g(e, "etype")
            n = _g(e, "count") or 1
            if et == "tray":
                spec = _g(e, "subtype") or "boyut_belirsiz"
                acc.add("tava", slug(spec), f"Kablo tavası {spec} mm", (_g(e, "length") or 0.0) * n * mult * tw, count=n * mult,
                        note=f"Fire %{(tw-1)*100:g} dahil" if tw > 1 else None)
            elif et == "cable":
                spec = _g(e, "subtype") or "kesit_belirsiz"
                L = ((_g(e, "length") or 0.0) + drop) * n * mult * cw
                acc.add("kablo", slug(spec), f"Kablo {spec}", L, count=n * mult,
                        note=("İniş payı " + f"{drop:g} m/hat, " if drop else "") + (f"fire %{(cw-1)*100:g}" if cw > 1 else "") or None)
            elif et == "conduit":
                spec = _g(e, "subtype") or "cap_belirsiz"
                acc.add("boru", slug(spec), f"Boru {spec}", (_g(e, "length") or 0.0) * n * mult, count=n * mult)
            elif et == "fixture":
                cat = _g(e, "subtype") or "diger"
                label = FIXTURE_CATEGORIES.get(cat, ("Diğer eleman",))[0]
                name = _g(e, "name") or ""
                group = slug(f"{cat}_{name}") if name else slug(cat)
                acc.add("armatur", group, f"{label}" + (f" ({name})" if name else ""), n * mult, count=n * mult)
    return list(acc.items.values())


def _g(o: Any, k: str, default=None):
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


# ------------------------------------------------------------------ KSF standart çizim

def standard_items(drawings: list[dict], params: dict[str, Any], catalog: Catalog) -> list[BoqItem]:
    """Standart çizim elemanları: katman adından kalem + özellik, katalogdan ölçüm kuralı.
    Disiplin anahtarı 'ksf:<KOD>' (ör. ksf:HAV) — sezgisel disiplinlerle çakışmaz."""
    acc = _Acc()
    for d in drawings:
        mult = int(d.get("storey_count") or 1)
        wall_h_default = params.get("wall_height") or max((d.get("storey_height") or 3.0) - (d.get("slab_thickness") or 0.0), 0.0)
        for e in d["elements"]:
            p = parse_layer(_g(e, "layer") or "", catalog)
            meta = _g(e, "meta") or {}
            if p is None and meta.get("ksf_code"):
                # katman eşlemeli çizim: kalem kodu ve ölçüm kuralı elemanın meta bilgisinde
                item = catalog.get(meta["ksf_code"])
                from ..standard.catalog import ParsedLayer
                p = ParsedLayer(item.discipline if item else str(meta.get("discipline") or "???"), meta["ksf_code"], meta.get("spec"), item, _g(e, "layer") or "")
            if p is None:
                continue
            item = p.item
            measure = meta.get("measure") or (item.measure if item else None)
            spec = _g(e, "subtype") or p.spec
            n = _g(e, "count") or 1
            length = _g(e, "length") or 0.0
            area = _g(e, "area") or 0.0
            nums = spec_numbers(spec)
            note = None
            if measure is None:
                # katalog dışı: geometriye göre
                if length > 0:
                    measure = "length"
                elif area > 0:
                    measure = "area"
                else:
                    measure = "count"
                note = "Katalogda yok; geometriye göre ölçüldü"
            if measure in ("count", "label_count"):
                qty = n
            elif measure == "length":
                qty = length * n
            elif measure == "area":
                qty = area * n
            elif measure == "wall_area":
                h = _g(e, "h") or (nums[1] / 100.0 if len(nums) >= 2 and nums[1] > 50 else None) or wall_h_default
                qty = length * h * n
                note = f"uzunluk × yükseklik {h:g} m"
            else:  # volume
                t = _g(e, "thickness") or (nums[0] / 100.0 if nums else None)
                if not t:
                    t = 0.0
                    note = "Kalınlık özellikte yok (ör. KSF-STA-DOLGU-30); hacim 0"
                else:
                    note = f"alan × kalınlık {t:g} m"
                qty = area * t * n
            kind = p.code.lower()
            unit = item.unit if item else {"count": "adet", "length": "m", "area": "m²"}.get(measure, "")
            kname = item.name if item else p.code
            disc_key = f"ksf:{p.discipline}"
            group = slug(spec) if spec else "*"
            label = f"{kname}" + (f" {spec}" if spec else "")
            b, h = _g(e, "b"), _g(e, "h")
            extra: dict[str, Any] = {}
            if kind in ("dograma", "kapi", "pencere"):
                okind = meta.get("opening_kind") or ("door" if kind == "kapi" else "window")
                extra["opening_kind"] = okind
                if not (b and h):
                    dims = [x for x in nums if 30 <= x <= 600]
                    if len(dims) >= 2:
                        b, h = dims[-2] / 100.0, dims[-1] / 100.0
                if b and h:
                    extra.update(area_m2=b * h * n * mult, perimeter_m=2 * (b + h) * n * mult, width_m=b * n * mult)
                    if kind == "dograma":
                        note = f"{_fmt_cm(b)}×{_fmt_cm(h)} cm ({'kapı' if okind == 'door' else 'pencere / vitrin'}); ölçü görünüş / doğrama paftasından"
            acc.add(kind, group, label, qty * mult, count=n * mult, note=note,
                    meta=(kname, unit, disc_key, catalog.discipline_name(p.discipline)), poz=(item.poz if item else ""), **extra)
            if kind == "dograma" and b and h and meta.get("opening_kind", "window") == "window":
                acc.add("cam", "*", "Cam (doğrama poz listesi)", b * h * n * mult, count=n * mult,
                        note="Poz adedi × doğrama ölçüsü (genişlik × yükseklik); kapı pozları hariç, doğrama payı düşülmedi")
    return list(acc.items.values())


# ------------------------------------------------------------------ birleşik

KIND_ORDER = list(KIND_META)


def expand_systems(items: list[BoqItem], systems: list[dict], catalog: Catalog) -> list[BoqItem]:
    """Katmanlı sistem kalemlerini bileşenlerine açar (services.project_systems çıktısına göre).

    Sistem satırı listede kalır ama fiyatlanmaz (detail.system = True); dahil edilen her bileşen için
    miktar = sistem miktarı × çarpan olan ayrı bir kalem eklenir (anahtar <bileşen>:<özellik>)."""
    by_kind = {sys["code"].lower(): sys for sys in systems}
    acc = _Acc()
    out: list[BoqItem] = []
    for it in items:
        sys = by_kind.get(it.kind)
        if not sys:
            out.append(it)
            continue
        it.detail["system"] = True
        it.detail["system_code"] = sys["code"]
        note = "Katmanlı sistem: bileşenleri ayrı kalem olarak yazıldı, bu satır fiyatlanmaz"
        if note not in it.notes:
            it.notes.append(note)
        out.append(it)
        for comp in sys["components"]:
            if not comp["include"]:
                continue
            citem = catalog.get(comp["code"])
            unit = citem.unit if citem else "m²"
            name = citem.name if citem else comp["code"]
            disc = citem.discipline if citem else sys["discipline"]
            spec = comp.get("spec") or ""
            group = slug(spec) if spec else "*"
            src = {"project": "projede yazıyor", "manual": "elle eklendi", "default": "sistem varsayılanı"}.get(comp.get("source"), "")
            acc.add(comp["code"].lower(), group, f"{name}" + (f" {spec}" if spec else ""), it.quantity * comp["factor"],
                    count=0.0, note=f"{sys['name']} bileşeni × {comp['factor']:g}" + (f" ({src})" if src else ""),
                    meta=(name, unit, f"ksf:{disc}", catalog.discipline_name(disc)), poz=(citem.poz if citem else ""),
                    system_code=sys["code"])
    return out + list(acc.items.values())


def sort_items(items: list[BoqItem]) -> list[BoqItem]:
    def k(i: BoqItem):
        wg = WORK_GROUP_ORDER.index(i.work_group) if i.work_group in WORK_GROUPS else 99
        return (wg, KIND_ORDER.index(i.kind) if i.kind in KIND_META else 100, i.discipline, i.kind_label, i.group != "*", i.label)
    return sorted(items, key=k)


def boq_summary(items: list[BoqItem]) -> dict:
    by_disc: dict[str, tuple[str, list[dict]]] = {}
    by_group: dict[str, list[dict]] = {}
    for it in sort_items(items):
        d = it.to_dict()
        by_disc.setdefault(it.discipline, (it.discipline_label, []))[1].append(d)
        by_group.setdefault(it.work_group, []).append(d)
    kinds = {k: {"label": v[0], "unit": v[1], "discipline": v[2]} for k, v in KIND_META.items()}
    for it in items:
        kinds.setdefault(it.kind, {"label": it.kind_label, "unit": it.unit, "discipline": it.discipline})
    return {
        "items": [it.to_dict() for it in sort_items(items)],
        "by_discipline": [{"discipline": d, "label": lbl, "items": its} for d, (lbl, its) in by_disc.items()],
        "by_group": [{"group": g, "label": WORK_GROUPS.get(g, g), "items": by_group[g]}
                     for g in WORK_GROUP_ORDER + [g for g in by_group if g not in WORK_GROUPS] if g in by_group],
        "work_groups": WORK_GROUPS,
        "rules": {k: {"text": r.text, "source": r.source} for k, r in RULES.items()},
        "kinds": kinds,
    }
