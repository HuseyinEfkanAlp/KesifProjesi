"""Her metraj kaleminin güven kademesi: sayının nereden geldiği, teknik terim olmadan.

Ürün prensibi: **tahmin, ölçüm gibi sunulmaz.** Kullanıcı teknik değil; "conf 0.55" ya da
"auto_mapped" ona bir şey anlatmaz. Dört kademe anlatır:

| kod         | rozet                       | ne demek |
|-------------|-----------------------------|----------|
| `olculdu`   | 🟢 Çizimden ölçüldü         | geometri plandan, kimlik kesin (KÇS kodu, uzman eşlemesi, elle onaylanmış) |
| `tanindi`   | 🟡 Katman adından tanındı   | geometri plandan, kimlik yalnız katman adından |
| `turetildi` | 🟠 Varsayımla türetildi     | reçete, kural ya da katsayı (sıva duvardan, derz seramikten) |
| `tahmin`    | 🔴 Tahmini — doğrulanmalı | oran donatısı, tahmini cephe, kat sayısı bilinmeyen paftadan gelen her şey |

**En kötü girdi kazanır.** Türetilen bir kalem en iyi ihtimalle `turetildi`'dir; girdisi daha
kötüyse onun kademesini alır. Otomatik eşlenmiş duvardan türetilen sıva `turetildi`, oranla tahmin
edilen cepheden türetilen mantolama `tahmin`'dir. Kademe **birikmez**: üç basamaklı bir reçete
zinciri kendiliğinden kırmızıya düşmez, çünkü belirsizlik her adımda yeniden doğmaz.

Kat sayısı çıkarılamamış çok katlı bir paftadaki ölçülmüş kolon `tahmin`'dir: geometri doğru,
miktar kat sayısı kadar yanlış olabilir.

Rozet **dahil / hariç kararını etkilemez** (`services.MIN_INCLUDED_CONFIDENCE` ve
`quality.certified` değişmez): burada söylenen şey "bu sayıyı yazmadık" değil, "bu sayı şuradan
geldi"dir.
"""
from __future__ import annotations

from typing import Any

OLCULDU, TANINDI, TURETILDI, TAHMIN = "olculdu", "tanindi", "turetildi", "tahmin"
# En iyiden en kötüye. `worse` bu sıraya bakar.
TIERS = (OLCULDU, TANINDI, TURETILDI, TAHMIN)
TIER_META = {
    OLCULDU: ("Çizimden ölçüldü", "🟢", "Geometri plandan ölçüldü, kalemin ne olduğu kesin."),
    TANINDI: ("Katman adından tanındı", "🟡", "Geometri plandan ölçüldü ama kalemin ne olduğu yalnız katman adından anlaşıldı."),
    TURETILDI: ("Varsayımla türetildi", "🟠", "Doğrudan ölçülmedi; başka bir kalemden kural ya da reçeteyle hesaplandı."),
    TAHMIN: ("Tahmini — doğrulanmalı", "🔴", "Oran ya da katsayıyla tahmin edildi, ya da ölçüldüğü pafta bir "
                                                "belirsizlik taşıyor (kat sayısı gibi). Doğrulanması gerekir."),
}
_RANK = {t: i for i, t in enumerate(TIERS)}

# Kimliği kesin sayılan eleman güveni. Altındaki her şey "adından tanındı"dır.
CERTAIN_CONF = 0.7
# Geometrisi bile ölçülmemiş, oturum hattından tahmin edilmiş eleman kaynakları
ESTIMATE_SOURCES = ("ESTIMATE", "SCHEMA")


def worse(*tiers: str | None) -> str:
    """Verilen kademelerin en kötüsü. Boş / tanınmayan değerler yok sayılır."""
    bilinen = [t for t in tiers if t in _RANK]
    return max(bilinen, key=lambda t: _RANK[t]) if bilinen else OLCULDU


def demote(tier: str, adim: int = 1) -> str:
    """Kademeyi `adim` kadar aşağı çeker (türetme / reçete girdisini bir kademe düşürür)."""
    return TIERS[min(_RANK.get(tier, 0) + adim, len(TIERS) - 1)]


def _get(o: Any, k: str, default=None):
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def element_tier(e: Any) -> str:
    """Bir elemanın kimlik güveni. Ölçüm kuralı değil **kimlik** sorgulanır: geometri neredeyse hiç
    yanılmaz, yanılan "bu ne?" sorusudur."""
    if _get(e, "manual"):
        return OLCULDU                       # kullanıcı kendisi girdi ya da onayladı
    src = str(_get(e, "source") or "")
    if any(x in src for x in ESTIMATE_SOURCES):
        return TAHMIN                        # oturum hattından / şemadan tahmin: geometri bile ölçülmedi
    meta = _get(e, "meta") or {}
    if meta.get("auto_mapped"):
        return TANINDI                       # katman adından otomatik eşlendi (detect_mapped, conf 0.55)
    if meta.get("ksf_code"):
        return OLCULDU                       # KÇS kodu ya da uzman eşlemesi: kimlik belgeli
    conf = float(_get(e, "confidence") or 0.0)
    return OLCULDU if conf >= CERTAIN_CONF else TANINDI


def merge(a: dict[str, float] | None, b: dict[str, float] | str | None, qty: float = 0.0) -> dict[str, float]:
    """Kanıt sözlüklerini toplar. `b` bir kademe adıysa `qty` o kademeye yazılır."""
    out = dict(a or {})
    if isinstance(b, str):
        b = {b: qty}
    for t, v in (b or {}).items():
        if t in _RANK:
            out[t] = out.get(t, 0.0) + float(v or 0.0)
    return out


def shift(ev: dict[str, float] | None, tier: str | None = None, adim: int = 0) -> dict[str, float]:
    """Kanıtı bir türetmeden geçirir: her kademe `adim` kadar düşer, `tier` ile de en kötüsü alınır."""
    out: dict[str, float] = {}
    for t, v in (ev or {}).items():
        yeni = worse(demote(t, adim) if adim else t, tier)
        out[yeni] = out.get(yeni, 0.0) + float(v or 0.0)
    return out


def grade(ev: dict[str, float] | None, fallback: str = TURETILDI) -> dict:
    """Kanıt dağılımından rozet. **Miktarı sıfır olmayan en kötü kademe** kazanır.

    Kanıt hiç yoksa `fallback`: kalem bir üreticiden kanıtsız geldiyse ölçülmüş sayılamaz."""
    var = {t: v for t, v in (ev or {}).items() if t in _RANK and abs(float(v or 0.0)) > 1e-9}
    if not var:
        kod = fallback if fallback in _RANK else TURETILDI
        pay = {}
    else:
        kod = max(var, key=lambda t: _RANK[t])
        toplam = sum(var.values())
        pay = {t: round(v / toplam, 4) for t, v in var.items()} if toplam else {}
    label, icon, aciklama = TIER_META[kod]
    return {"code": kod, "label": label, "icon": icon, "note": aciklama, "shares": pay}


def distribution(items: list) -> dict:
    """Keşfin güven dağılımı ve kullanıcıya gösterilecek tek cümle.

    Pay **kalem sayısı** üzerindendir: m³ ile adedi toplamak anlamsız olurdu."""
    sayim = {t: 0 for t in TIERS}
    for it in items:
        kod = (it.confidence if hasattr(it, "confidence") else (it.get("confidence") or {}))["code"]
        if kod in sayim:
            sayim[kod] += 1
    n = sum(sayim.values())
    if not n:
        return {"counts": sayim, "total": 0, "shares": {}, "sentence": ""}
    pay = {t: round(100 * v / n) for t, v in sayim.items()}
    # "%4'i" / "%9'u" gibi ekler Türkçede sayının okunuşuna göre değişir; cümle eki gerektirmeyecek
    # biçimde kurulur — yanlış ek, ürünü özensiz gösterir.
    parcalar = [f"%{pay[t]} {TIER_META[t][0][0].lower()}{TIER_META[t][0][1:]}" for t in TIERS if sayim[t]]
    return {"counts": sayim, "total": n, "shares": pay,
            "sentence": ("Metrajın kaynağı: " + " · ".join(parcalar) + ".") if parcalar else ""}
