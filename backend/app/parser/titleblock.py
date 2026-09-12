"""Ruhsat antedi (proje bilgi tablosu): çizimin köşesindeki etiket–değer tablosunu okur.

Antet bir pafta değildir; ölçülecek geometri taşımaz, bu yüzden plan listesine girmemeli. Ama keşfin elle
sorduğu proje verisini taşır: beton ve donatı sınıfı ("MALZEME: C35-S420"), temel tipi ("TEMEL TİPİ: RADYE"),
döşeme cinsi ("B.A.K: plak"), kat adedi, inşaat alanı, zemin taşıma gücü. Okunan değerler kullanıcıya
**öneri** olarak sunulur; kendi girdiği parametrenin üstüne yazılmaz.

Nasıl okunur: antet katmanlarındaki ("Başlık_Yazı", "VM_Antet", "ANTET"…) yazılar toplanır, her tanınan
etiketin değeri **aynı satırda sağındaki** ya da **hemen altındaki** yazıdan alınır — Türk ruhsat antetlerinde
iki yerleşim de kullanılır. Değer yerinde başka bir etiket varsa alan boş kabul edilir (ruhsat antetlerinin
yarısı doldurulmadan çizilir).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Antet yazılarının durduğu katmanlar. "VM Pafta" gibi çerçeve katmanları kasten dışarıda: onlar çizgi taşır.
ANTET_LAYER_RE = re.compile(r"BA[ŞS]LIK|ANTET|TITLE ?BLOCK|PROJE ?B[İI]LG", re.IGNORECASE)

# TS 500 beton sınıfı çiftleri: antette çoğu zaman yalnız silindir dayanımı yazılır ("C35")
CONCRETE_PAIR = {"C16": "C16/20", "C20": "C20/25", "C25": "C25/30", "C30": "C30/37", "C35": "C35/45",
                 "C40": "C40/50", "C45": "C45/55", "C50": "C50/60"}
# Eski TS 708 çelik adı -> yürürlükteki sınıf
REBAR_GRADE = {"S220": "B220B", "S420": "B420C", "S500": "B500C",
               "B420C": "B420C", "B500C": "B500C", "B420B": "B420B"}
FOUNDATION_KIND = {"RADYE": "radye", "MUNFERIT": "tekil", "TEKIL": "tekil", "SUREKLI": "sürekli",
                   "MUTEMADI": "sürekli", "KAZIK": "kazık"}


def _fold(s: str) -> str:
    """Türkçe harfleri ve noktalamayı atarak karşılaştırma anahtarı: "İNŞ. ALANI" -> "INSALANI"."""
    s = s.replace("ı", "i").replace("I", "i").replace("İ", "i")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


# Tanınan antet etiketleri: katlanmış etiket -> alan adı. Aynı alana birden çok etiket bakabilir.
LABELS: dict[str, str] = {
    "MALZEME": "malzeme", "BETON": "malzeme", "BETONSINIFI": "malzeme", "MALZEMESINIFI": "malzeme",
    "TEMELTIPI": "temel_tipi", "TEMELCINSI": "temel_tipi",
    "PERDE": "perde", "DOSEMECINSI": "doseme_cinsi", "BAK": "doseme_cinsi",
    "KATADEDI": "kat_adedi", "INSALANI": "insaat_alani", "INSAATALANI": "insaat_alani",
    "TASIYICISIS": "tasiyici_sistem", "TASIYICISISTEM": "tasiyici_sistem",
    "ZEMINTASIMAGUCU": "zemin_tasima_gucu", "HAREKETLIYUK": "hareketli_yuk", "KATYUK": "kat_yuku",
    "KIRISACIKLIGI": "kiris_acikligi", "YSINIFIKATSAYISI": "yapi_sinifi", "MGRUBU": "malzeme_grubu",
    "ADANO": "ada_no", "PARSELNO": "parsel_no", "PAFTANO": "pafta_no",
    "ILCESI": "ilce", "MAHALLESI": "mahalle", "BELEDIYESI": "belediye", "PROJENO": "proje_no",
}
# Antetin öteki kutu başlıkları: değer olarak okunmamaları için tanınır (yoksa "TEMEL TİPİ"nin değeri
# aynı satırdaki komşu başlık "İNŞAAT SÜRESİ" sanılır). Bunlardan veri çıkarılmaz.
OTHER_LABELS = {_fold(s) for s in (
    "PAFTA SAYISI", "İNŞAAT SURESİ", "İNŞAAT SÜRESİ", "ONAY", "TARİH", "TARİHİ NO", "PROJE", "KONTROL",
    "KALIP PL. S.", "İMAR DURUMU", "Arsanın", "SOKAĞI", "MİMARİ PROJE", "SORUMLUSU", "PROJE SORUMLUSU",
    "STATİK PROJE", "TESİSAT PROJE", "ELEKTRİK PROJE", "DİPLAMA NO", "DİPLOMA NO", "VERGİ HESAP NO",
    "VERGİ DAİRESİ", "BEL. KART NO", "BEL. SİCİL NO", "ADRESİ", "İMZASI", "AMACI", "KULLANMA", "ÜNVANI",
    "UNVANI", "ADI SOYADI", "YAPININ", "SAHİBİ", "İNŞ. Y. MÜH.", "YAPI DENETİM", "BELEDİYE ONAYI",
    "STATİK RAP.", "İMAR MÜDÜR.", "JEOLOJİ RAP.", "ŞEF", "İ.M.O.vizesi", "İ.M.O. BELGE NO",
    "İ.M.O. SİCİL NO", "MALZEME GRUBU", "YAPI SINIFI", "İSKELE", "NOTLAR", "AÇIKLAMA",
)}
LABEL_KEYS = set(LABELS) | OTHER_LABELS
# Değer sayılmayacak yazılar: tek harflik tablo işareti ya da iki nokta ile biten başlık
_NOT_A_VALUE = re.compile(r"^([A-ZÇĞİÖŞÜ]|.*:)$")


@dataclass
class TitleBlock:
    """Antetten okunanlar. `fields` ham etiket->değer, öteki alanlar yorumlanmış hâli."""
    fields: dict[str, str] = field(default_factory=dict)
    concrete_class: str = ""      # "C35/45"
    rebar_grade: str = ""         # "B420C"
    foundation_kind: str = ""     # "radye"
    storey_count: int | None = None
    area_m2: float | None = None

    @property
    def empty(self) -> bool:
        return not self.fields

    def to_dict(self) -> dict:
        return {"fields": dict(self.fields), "concrete_class": self.concrete_class, "rebar_grade": self.rebar_grade,
                "foundation_kind": self.foundation_kind, "storey_count": self.storey_count, "area_m2": self.area_m2}

    @classmethod
    def from_dict(cls, d: dict | None) -> "TitleBlock":
        d = d or {}
        return cls(dict(d.get("fields") or {}), d.get("concrete_class", "") or "", d.get("rebar_grade", "") or "",
                   d.get("foundation_kind", "") or "",
                   int(d["storey_count"]) if d.get("storey_count") else None,
                   float(d["area_m2"]) if d.get("area_m2") else None)

    def summary(self) -> str:
        """Kullanıcıya gösterilecek tek satır özet; okunacak bir şey yoksa boş."""
        parts = []
        if self.concrete_class:
            parts.append(f"beton {self.concrete_class}")
        if self.rebar_grade:
            parts.append(f"donatı {self.rebar_grade}")
        if self.foundation_kind:
            parts.append(f"temel {self.foundation_kind}")
        if self.storey_count:
            parts.append(f"{self.storey_count} kat")
        if self.area_m2:
            parts.append(f"{self.area_m2:,.0f} m² inşaat".replace(",", "."))
        return ", ".join(parts)


def is_titleblock_layer(name: str) -> bool:
    return bool(ANTET_LAYER_RE.search(name or ""))


@dataclass
class _Txt:
    x: float
    y: float
    h: float
    text: str


def _pair(items: list[_Txt]) -> dict[str, str]:
    """Etiketleri değerleriyle eşler: değer aynı satırda sağda ya da hemen altta durur."""
    # yalnız veri çıkardığımız etiketler taranır; OTHER_LABELS sadece "değer değildir" filtresi olarak kullanılır
    labels = [(i, t) for i, t in enumerate(items) if _fold(t.text) in LABELS]
    out: dict[str, str] = {}
    for i, lab in labels:
        hh = lab.h or 1.0
        best: tuple[float, str] | None = None
        for j, cand in enumerate(items):
            if j == i or not cand.text or _fold(cand.text) in LABEL_KEYS or _NOT_A_VALUE.match(cand.text):
                continue
            dx, dy = cand.x - lab.x, cand.y - lab.y
            if abs(dy) <= 0.6 * hh and 0 < dx <= 40 * hh:                 # aynı satır, sağda
                score = dx
            elif -hh <= dx <= 6 * hh and -4 * hh <= dy < -0.6 * hh:       # hemen altta (hücre sola dayalı)
                score = 40 * hh + abs(dy)
            else:
                continue
            if best is None or score < best[0]:
                best = (score, cand.text)
        if best:
            out.setdefault(LABELS[_fold(lab.text)], best[1].strip())
    return out


def _num(s: str) -> float | None:
    m = re.search(r"\d[\d.,]*", s or "")
    if not m:
        return None
    v = m.group(0).replace(".", "").replace(",", ".") if "," in m.group(0) else m.group(0).replace(",", "")
    try:
        return float(v)
    except ValueError:
        return None


def interpret(fields: dict[str, str]) -> TitleBlock:
    """Ham etiket–değer çiftlerinden proje parametrelerini çıkarır."""
    tb = TitleBlock(fields=dict(fields))
    mal = (fields.get("malzeme") or "").upper().replace(" ", "")
    m = re.search(r"C\s*(\d{2})(?:\s*/\s*\d{2})?", mal)
    if m:
        tb.concrete_class = CONCRETE_PAIR.get(f"C{m.group(1)}", f"C{m.group(1)}")
    # "C35-S420", "C30/37 B420C", "BETON C25 ÇELİK S220": boşluklar atıldığı için kelime sınırı aranamaz;
    # adayların ilk tanınanı alınır (tanınmayan "S123" gibi bir sayı sınıf sanılmasın).
    for m in re.finditer(r"[SB]\d{3}[ABC]?", mal):
        grade = REBAR_GRADE.get(m.group(0))
        if grade:
            tb.rebar_grade = grade
            break
    tem = _fold(fields.get("temel_tipi", ""))
    for key, val in FOUNDATION_KIND.items():
        if key in tem:
            tb.foundation_kind = val
            break
    n = _num(fields.get("kat_adedi", ""))
    if n and 1 <= n <= 100:
        tb.storey_count = int(n)
    a = _num(fields.get("insaat_alani", ""))
    if a and a > 1:
        tb.area_m2 = a
    return tb


def read_texts(texts: list[tuple[float, float, float, str, str]]) -> TitleBlock:
    """(x, y, yazı yüksekliği, katman, yazı) listesinden anteti okur."""
    items = [_Txt(x, y, h, t.strip()) for x, y, h, layer, t in texts if t.strip() and is_titleblock_layer(layer)]
    if len(items) < 4:                      # antet sayılacak kadar yazı yok
        return TitleBlock()
    return interpret(_pair(items))


def label_points(texts: list[tuple[float, float, float, str, str]]) -> list[tuple[float, float]]:
    """Tanınan antet etiketlerinin konumları. Bir kutunun antet olup olmadığı buna bakılarak anlaşılır:
    katman adı kanıt değildir (pafta çerçevesi de çoğu projede "ANTET" katmanında çizilir), kutunun içindeki
    "TEMEL TİPİ / MALZEME / KAT ADEDİ" etiketleri kanıttır."""
    return [(x, y) for x, y, _h, layer, t in texts
            if is_titleblock_layer(layer) and _fold(t) in LABEL_KEYS]
