"""Yüklenen dosyadan hangi paftaların ölçüleceğine sistem karar verir.

Ürün prensibi: kullanıcıya soru sorulmaz. Ruhsat dosyası gibi çok paftalı bir DXF yüklendiğinde
"hangi paftaları analiz edelim?" diye sormak, teknik olmayan kullanıcı için akışın kilitlendiği
yerdir. Karar verecek bilgi zaten elimizde: her pafta için başlığından ve katmanlarından plan tipi
ve disiplin tanınıyor (`planset.resolve_plan`).

Kural:
  ölç   — plan tipi tanınmış ve ölçülebilir paftalar
  ölç   — cetvel / liste paftaları (geometrisi ölçülmez ama doğrama poz listesi adet taşır)
  oku   — kesit, detay, vaziyet, kolon şeması: geometrisi ölçülmez ama KANIT taşır (kat yüksekliği
          kotlardan, şap kalınlığı ve kazı kotu kesit notlarından, blok listesi vaziyet planından)
  atla  — antet, boş çerçeve, başlıksız küçük kümeler (detay / lejant parçası)
  bildir— plan büyüklüğünde olduğu hâlde tipi tanınmayan paftalar

Seçilmeyen her pafta gerekçesiyle rapora girer: metraja **sessizce** girmeyen hiçbir şey olmamalı.
Bu modül saf karardır (dosya açmaz, veritabanına yazmaz); yürütme `api/drawings.py` içindedir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .planset import PLAN_TYPE_BY_CODE, resolve_plan

FRAGMENT_MAX_ENTITIES = 200   # başlıksız ve bu kadar az nesneli küme: detay / tablo / lejant parçası, plan değil
# Pafta olmayan içerik türlerinin listedeki açıklaması
KIND_NOTE = {"antet": "antet / proje bilgi tablosu — plan değil, ölçülecek geometri taşımaz",
             "bos": "boş çerçeve — başlığı var ama çizim yok",
             "cetvel": "cetvel / liste — geometrisi ölçülmez, yazılarındaki poz ve adet okunur"}
# Bu türlerin geometrisi ölçülmez; listede işaretsiz gelir. "cetvel" bunlara dahil DEĞİLDİR: okunacak
# verisi olduğu için eklenir (doğrama poz listesi tek başına 170 adet taşıyabilir).
NOT_A_PLAN = {"antet", "bos"}
# Tipi tanınmayan bir pafta bu kadar nesne taşıyorsa "atlanan artık" değil, bildirilmesi gereken
# bir kapsam boşluğudur: kullanıcı neyin ölçülmediğini görmeli.
REPORT_MIN_ENTITIES = 500


def sheet_verdict(sh) -> dict:
    """Pafta bilgisi + başlığından / katmanlarından tanınan plan tipi ve disiplin önerisi.

    Plan olmayan içerik ölçülmez: başlıksız küçük kümeler (merdiven detayı, pano tablosu, lejant) ve
    başlığı olduğu hâlde plan olmayan çerçeveler — ruhsat antedi ve boş şablon kutusu. Bunlar listede
    kalır ama etiketlenir; uzman görünümünde yine seçilebilir."""
    code, disc = resolve_plan([sh.title, *sh.titles], sh.layers)
    fragment = (not sh.titled and (sh.entity_count < FRAGMENT_MAX_ENTITIES or not disc)) or sh.kind in NOT_A_PLAN
    if fragment:
        code, disc = "", ""
    pt = PLAN_TYPE_BY_CODE.get(code)
    return {**sh.to_dict(), "plan_type": code, "plan_type_label": pt.label if pt else "",
            "discipline": disc if (pt or disc) else "", "analyze": (pt.analyze if pt else bool(disc)) and not fragment,
            "fragment": fragment, "kind_note": KIND_NOTE.get(sh.kind, "")}


@dataclass
class IntakeReport:
    """Hangi pafta neden alındı / alınmadı. Kullanıcıya gösterilir; sessiz eksik bırakılmaz."""
    picked: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)   # geometrisi ölçülmez, notları okunur
    skipped: list[dict] = field(default_factory=list)
    unknown: list[dict] = field(default_factory=list)

    @property
    def note(self) -> str:
        p = [f"{len(self.picked)} pafta ölçüldü"]
        if self.evidence:
            p.append(f"{len(self.evidence)} pafta kanıt için okundu (kesit / detay / vaziyet)")
        if self.skipped:
            p.append(f"{len(self.skipped)} pafta plan değil (antet / boş çerçeve / detay parçası)")
        if self.unknown:
            n = sum(int(u.get("entity_count") or 0) for u in self.unknown)
            p.append(f"{len(self.unknown)} paftanın tipi tanınamadı ({n:,} nesne) — metraja girmedi")
        return " · ".join(p)

    def to_dict(self) -> dict:
        return {"picked": self.picked, "evidence": self.evidence, "skipped": self.skipped,
                "unknown": self.unknown, "note": self.note}


def auto_pick_sheets(scan) -> tuple[list[dict], IntakeReport]:
    """Analiz edilecek paftaları seçer. Döner: seçimler (index + tanınan tip), rapor.

    Seçim, kullanıcıya gösterilen listedekiyle **aynı** karardır (`sheet_verdict`): arayüzde
    işaretli gelen paftalar neyse sistem de onları alır."""
    picks: list[dict] = []
    rapor = IntakeReport()
    for i, sh in enumerate(scan.sheets):
        v = sheet_verdict(sh)
        ad = sh.title if sh.titled else f"Pafta {i + 1}"
        kayit = {"index": i, "title": ad, "plan_type": v["plan_type"], "plan_type_label": v["plan_type_label"],
                 "discipline": v["discipline"], "entity_count": sh.entity_count}
        if v["analyze"] or sh.kind == "cetvel":
            picks.append({"index": i, "plan_type": v["plan_type"], "discipline": v["discipline"]})
            rapor.picked.append(kayit)
            continue
        # Tipi TANINMIŞ ama geometrisi ölçülmeyen pafta (kesit, detay, vaziyet, kolon şeması) yine alınır:
        # "bilgiyi önce projede ara" ilkesinin en verimli kaynağı burasıdır — kat yüksekliği kotlardan,
        # şap kalınlığı ve kazı kotu kesit notlarından, blok listesi vaziyet planından okunur. Sahte metraj
        # riski yok: `services.analyze_and_store` bu plan tiplerinde otomatik katman eşlemeyi kapatıyor.
        if v["plan_type"] and not v["fragment"]:
            picks.append({"index": i, "plan_type": v["plan_type"], "discipline": v["discipline"]})
            rapor.evidence.append({**kayit, "reason": "geometrisi ölçülmez, notları (kot, malzeme, ölçü) okunur"})
            continue
        sebep = v["kind_note"] or ("tipi tanınamadı" if sh.entity_count >= REPORT_MIN_ENTITIES
                                   else "başlıksız küçük küme — detay / lejant parçası")
        atlandi = {"index": i, "title": ad, "reason": sebep, "entity_count": sh.entity_count}
        (rapor.unknown if sebep == "tipi tanınamadı" else rapor.skipped).append(atlandi)
    return picks, rapor
