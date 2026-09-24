"""Çizimden türetilen proje parametreleri — tek sözleşme, tek yer.

Ürün prensibi: **kullanıcıya sorulmaz.** Kat sayısı, döşeme kalınlığı, kat yüksekliği gibi metrajı
mertebe olarak değiştiren değerler bir forma girilmez; çizimin kendi kanıtından okunur. Okunamıyorsa
uydurulmaz: varsayılan uygulanır ve **varsayım olduğu söylenir**.

Her türetme aynı sözlüğü döndürür:

```
{"per_drawing": {çizim_id: {"value": v, "source": "kot +3.30 → +6.60", "kind": "drawing", "conf": 0.9}},
 "effective": v, "source": "...", "kind": "user|drawing|default", "conf": 0.0-1.0,
 "warnings": ["..."]}
```

`kind` üç değer alır ve raporun dilini belirler:
  user    — kullanıcı açıkça girdi (asla ezilmez)
  drawing — çizimden okundu (kot dizisi, pafta başlığı, ölçülen geometri)
  default — çıkarılamadı, varsayılan kullanıldı → kalite raporunda uyarı, güven rozetinde en düşük kademe

`quality.build_quality` bu sözleşmeyi tek döngüde `assumptions`'a çevirir; yeni bir türetme eklemek
kalite raporunu ve güven rozetini kendiliğinden günceller.
"""
from __future__ import annotations

from typing import Any

from .models import Drawing, Project
from .parser.levels import (MIN_STOREY, floor_levels, floor_rank, is_typical_floor, level_for_rank,
                            storey_count_in_label, storey_span)

# Bu disiplinlerin paftaları bir katı temsil eder; tesisat paftaları aynı katı tekrar saymasın diye
# kat dizisinin sahipliğinde sayılmaz (ama kendi kat sayılarını aynı kanıttan alırlar).
PLAN_DISCIPLINES = ("structural", "architectural", "mapped", "standard")
DEFAULT_SLAB_THICKNESS = 0.15


def _label(d: Drawing) -> str:
    return d.label or d.filename or ""


# --------------------------------------------------------------------------------------- kat sayısı

# Binanın tamamını anlatan paftalar: kat çarpanı yoktur, kat sayısı sorulmaz.
WHOLE_BUILDING_TYPES = {"mim_cephe", "mim_dograma", "mim_prekast", "mim_kesit", "mim_detay", "mim_vaziyet", "mim_cati",
                        "sta_temel_kalip", "sta_temel_donati", "pey_peyzaj", "alt_altyapi", "asn_asansor", "elk_kolon_sema"}


def storey_counts(project: Project, drawings: list[Drawing]) -> dict:
    """Her paftanın temsil ettiği kat sayısı ve kaynağı.

    Bu, metrajı **mertebe olarak** kaydıran en büyük sessiz varsayımdır: bir tip kat planı 5 katı
    temsil ediyorsa beton, kalıp, demir ve duvar beş katıdır. Bugünkü varsayılan 1'dir ve 10 katlı
    binayı 1 kat sayan rapor işe yaramaz.

    Kanıt sırası:
      1. Kullanıcının pafta için açıkça girdiği sayı (`storey_manual`) — asla ezilmez.
      2. Pafta başlığındaki kat aralığı: "1.-5. NORMAL KAT PLANI" → 5 kat.
      3. Başlıkta açıkça yazan adet: "TİP KAT (5 KAT)", "5 KATLI".
      4. Kot dizisi eşlemesi: kotlarda kaç kat var, kaçının ayrı paftası yüklenmiş? Sahipsiz kalan
         seviyeler en yakın **tip kat** planına yüklenir.
      5. Hiçbiri yoksa 1 — ve bunun bir varsayım olduğu söylenir.

    Antetteki kat adedi (`Project.titleblock`) çapraz doğrulama olarak kullanılır: çelişirse uyarı
    yazılır ama sayı değiştirilmez (antet bütün bloğu, pafta tek bloğu anlatıyor olabilir)."""
    from .parser.levels import building_datum, building_floors
    datum = building_datum(drawings)
    katlar = building_floors(drawings, datum)

    per: dict[int, dict] = {}
    uyarilar: list[dict] = []
    # Kanıt 1-3: paftanın kendi başlığı / kullanıcı. Bunlar kot dizisinden bağımsızdır.
    kalan: list[Drawing] = []
    for d in drawings:
        elle = getattr(d, "storey_manual", None)
        if elle and int(elle) > 0:
            per[d.id] = {"value": int(elle), "source": "çizime girildi", "kind": "user", "conf": 1.0}
            continue
        if (getattr(d, "plan_type", "") or "") in WHOLE_BUILDING_TYPES:
            # Görünüş, doğrama listesi, kesit, çatı planı binanın TAMAMINI anlatır: "kaç katı temsil ediyor"
            # sorusu bunlara uygulanmaz. C1 ruhsatında doğrama listesinin 166 adedi bu yüzden "tahmin" sayılıyordu.
            per[d.id] = {"value": 1, "kind": "whole", "conf": 1.0, "source": "bina geneli pafta — kat çarpanı uygulanmaz"}
            continue
        ad = _label(d)
        aralik = storey_span(ad)
        if aralik:
            lo, hi = aralik
            per[d.id] = {"value": hi - lo + 1, "kind": "drawing", "conf": 0.95,
                         "source": f"pafta başlığında {lo}.–{hi}. kat aralığı yazıyor"}
            continue
        adet = storey_count_in_label(ad)
        if adet:
            per[d.id] = {"value": adet, "kind": "drawing", "conf": 0.9,
                         "source": f"pafta başlığında {adet} kat yazıyor"}
            continue
        kalan.append(d)

    # Kanıt 4: kot dizisi. Hangi seviyenin paftası yüklenmiş, hangisi sahipsiz?
    sahipli: set[float] = set()
    kot_of: dict[int, float] = {}
    for d in drawings:
        if d.discipline not in PLAN_DISCIPLINES:
            continue
        sira = floor_rank(_label(d))
        lvl = float(d.kot) if d.kot is not None else (level_for_rank(katlar, sira, datum) if sira is not None else None)
        if lvl is None:
            continue
        yakin = min(katlar, key=lambda f: abs(f - lvl)) if katlar else None
        if yakin is not None and abs(yakin - lvl) <= MIN_STOREY / 2:
            sahipli.add(yakin)
            kot_of[d.id] = yakin
    sahipsiz = [f for f in katlar if f not in sahipli]

    # Sahipsiz seviyeler tip kat planlarına bölüştürülür: her seviye en yakın tip kat planına gider.
    tipler = [d for d in kalan if is_typical_floor(_label(d)) and d.discipline in PLAN_DISCIPLINES]
    yuklenen: dict[int, list[float]] = {d.id: [] for d in tipler}
    if tipler and sahipsiz:
        for f in sahipsiz:
            hedef = min(tipler, key=lambda d: abs(kot_of.get(d.id, 0.0) - f))
            yuklenen[hedef.id].append(f)

    for d in kalan:
        ek = yuklenen.get(d.id) or []
        if ek:
            # Tip kat planının kendi kotu varsa o kat da sayılır; yoksa yalnız üstlendiği sahipsiz seviyeler.
            n = len(ek) + (1 if d.id in kot_of else 0)
            per[d.id] = {"value": n, "kind": "drawing", "conf": 0.7,
                         "source": (f"kotlarda {len(katlar)} kat var, {len(sahipli)} katın ayrı paftası yüklenmiş; "
                                    f"bu tip kat planı {n} katı temsil ediyor")}
            continue
        if d.id in kot_of:
            per[d.id] = {"value": 1, "kind": "drawing", "conf": 0.8,
                         "source": f"kot {kot_of[d.id]:+.2f} — tek kat"}
            continue
        per[d.id] = {"value": 1, "kind": "default", "conf": 0.3,
                     "source": "kat sayısı çizimden çıkarılamadı, 1 kat kabul edildi"}

    # Uyarıların ağırlığı kanıta göre: tek katlı küçük projede "1 kat" doğrudur ve rapor "eksik" olmamalı;
    # ama çizimin kendi kotları daha fazla kat olduğunu söylüyorsa metraj mertebe olarak eksiktir — blocking.
    if sahipsiz and not tipler:
        uyarilar.append({"code": "storey_missing_plans", "severity": "blocking",
                         "message": f"Kotlarda {len(katlar)} kat seviyesi var ama {len(sahipsiz)} katın planı "
                                    "yüklenmedi ve bunları temsil edecek bir tip kat planı da yok — bu katların "
                                    "metrajı hesaba girmedi."})
    bilinmeyen = [d for d in drawings if per[d.id]["kind"] == "default" and d.discipline in PLAN_DISCIPLINES]
    if bilinmeyen:
        uyarilar.append({"code": "storey_count_default",
                         "severity": "blocking" if len(katlar) > 1 else "review",
                         "message": f"{len(bilinmeyen)} paftanın kat sayısı çizimden çıkarılamadı; 1 kat kabul edildi. "
                                    "Bina çok katlıysa beton, kalıp, demir ve duvar miktarları kat sayısı kadar eksiktir."})

    # Binanın kat sayısı yalnız kot dizisinden bilinir. Kot yoksa **bilinmiyor** (None) — disiplinlerin
    # pafta sayısını toplamak aynı katı birkaç kez sayar ve savunulamaz bir rakam üretir.
    toplam = len(katlar) or None
    antet = ((project.titleblock or {}).get("storey_count") if getattr(project, "titleblock", None) else None)
    if antet and toplam and int(antet) != toplam:
        uyarilar.append({"code": "storey_count_titleblock", "severity": "review",
                         "message": f"Antette {antet} kat yazıyor, çizimdeki kotlardan {toplam} kat çıkıyor — "
                                    "paftalardan biri eksik ya da antet başka bloğu anlatıyor olabilir."})

    gecerli = [v for v in per.values() if v["kind"] != "default"]
    return {"per_drawing": per, "levels": katlar, "total": toplam, "unowned": sahipsiz,
            "effective": 1, "source": f"{toplam} kat seviyesi" if katlar else "kot bulunamadı",
            "kind": "drawing" if gecerli else "default",
            "conf": min((v["conf"] for v in per.values()), default=0.3), "warnings": uyarilar}


def storey_count_of(project: Project, d: Drawing, sc: dict | None = None) -> int:
    """Paftanın temsil ettiği kat sayısı. `storey_height_of` ile aynı imza."""
    sc = sc or storey_counts(project, [d])
    return max(1, int(sc["per_drawing"].get(d.id, {}).get("value") or 1))


# ---------------------------------------------------------------------------------- döşeme kalınlığı

def slab_thicknesses(project: Project, drawings: list[Drawing], elements_of) -> dict:
    """Her paftanın baskın döşeme kalınlığı; kolon/perde beton yüksekliği ve kiriş gövdesi bununla düşülür.

    Kullanıcı açıkça girmediyse **çizim kazanır**: kalınlık etiketi planda yazar (`parser/detectors/slabs.py`),
    tek bir proje parametresi bodrum perdesi ile çatı döşemesini aynı sayamaz.

    elements_of: çizim → eleman listesi (çağıran verir; bu modül veritabanı okumaz)."""
    from .services import dominant_slab_thickness

    elle = float(getattr(project, "slab_manual", 0) or 0)
    per: dict[int, dict] = {}
    olculen: list[float] = []
    for d in drawings:
        if elle > 0:
            per[d.id] = {"value": elle, "source": "projeye girildi", "kind": "user", "conf": 1.0}
            continue
        t = dominant_slab_thickness(elements_of(d))
        if t:
            per[d.id] = {"value": float(t), "kind": "drawing", "conf": 0.9,
                         "source": f"planda ölçülen baskın döşeme kalınlığı {float(t)*100:.0f} cm"}
            olculen.append(float(t))
        else:
            per[d.id] = {"value": 0.0, "kind": "default", "conf": 0.3, "source": ""}

    if elle > 0:
        etkin, kaynak, kind, conf = elle, "projeye girildi", "user", 1.0
    elif olculen:
        etkin = sorted(olculen)[len(olculen) // 2]
        etkin, kaynak, kind, conf = etkin, f"çizimlerden ölçüldü (medyan {etkin*100:.0f} cm)", "drawing", 0.8
    else:
        etkin = float(project.slab_thickness or DEFAULT_SLAB_THICKNESS)
        kaynak, kind, conf = f"varsayılan {etkin*100:.0f} cm", "default", 0.3

    uyarilar: list[str] = []
    for v in per.values():
        if not v["value"]:
            v.update(value=etkin, source=kaynak, kind=kind, conf=conf)
    if kind == "default":
        uyarilar.append(f"Döşeme kalınlığı hiçbir planda ölçülemedi; {etkin*100:.0f} cm varsayıldı. "
                        "Kolon, perde ve kiriş net yükseklikleri bu sayıya bağlıdır.")
    return {"per_drawing": per, "effective": etkin, "source": kaynak, "kind": kind, "conf": conf,
            "warnings": uyarilar}


def slab_thickness_of(project: Project, d: Drawing, st: dict | None = None) -> float:
    st = st or {}
    v = float(st.get("per_drawing", {}).get(d.id, {}).get("value") or 0.0)
    return v or float(project.slab_thickness or DEFAULT_SLAB_THICKNESS)


# ------------------------------------------------------------------------------------------ toplayıcı

def derivations(project: Project, drawings: list[Drawing]) -> dict[str, Any]:
    """Çizimden türetilen bütün parametreler tek sözlükte — `quality` ve güven rozeti buradan okur."""
    from .services import storey_heights

    sh = storey_heights(project, drawings)
    return {
        "storey_height": {"per_drawing": {k: {"value": v["height"], "source": v["source"],
                                              "kind": ("user" if "girildi" in v["source"] else
                                                       "default" if "varsayılan" in v["source"] else "drawing"),
                                              "conf": 0.3 if "varsayılan" in v["source"] else 0.9}
                                          for k, v in sh["per_drawing"].items()},
                          "effective": sh["effective"], "source": sh["source"],
                          "kind": ("user" if sh["source"] == "parametre" else
                                   "default" if sh["source"] == "varsayılan" else "drawing"),
                          "conf": 0.3 if sh["source"] == "varsayılan" else 0.9, "warnings": []},
        "storey_count": storey_counts(project, drawings),
    }
