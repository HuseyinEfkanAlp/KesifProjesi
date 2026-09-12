"""Farkı sebebe bağlar: "%4 fazla" demek yetmez, **hangi değişken** yüzünden fazla olduğu yazılmalı.

Teşhis formüllerin kendisinden türetilir (`quantity/engine.py`):

    kolon/perde beton = alan × Hk        kalıp = çevre (ya da 2×L) × Hf
    Hk = H (döşeme net alansa) ya da H − d        Hf = H − (kattaki baskın kiriş yüksekliği)

Geometri doğruysa oran doğrudan yüksekliğe düşer, yani referansla eşleşmek için gereken yüksekliği
**geri hesaplayabiliriz**:  h_dogru = h_kullanilan × referans / bizim.

Asıl iş bundan sonra: geri hesaplanan yükseklik, formüldeki adaylardan (H, H − d, H − kiriş) hangisine
denk düşüyor? Denk düşüyorsa suçlu belli bir kabuldür (net/brüt döşeme, kiriş altı payı); hiçbirine
denk düşmüyorsa suçlu yükseklik değil, eleman tespitidir.

Teşhis bir iddiadır, kanıt değildir: hangi değişkene bakılacağını söyler, düzeltmeyi kendisi yapmaz.
"""
from __future__ import annotations

ESIK = 2.0          # bu yüzdenin altındaki sapma "eşleşti" sayılır (ölçüm ve yuvarlama gürültüsü)
YUKSEKLIK_TOL = 0.05   # geri hesaplanan yükseklik bir adaya bu kadar yakınsa o adayla açıklanmış sayılır


def _get(kat, olcu: str):
    return next((d for d in kat.farklar if d.olcu == olcu), None)


def _geri_hesap(kullanilan: float, bizim: float, referans: float) -> float | None:
    """Referansla eşleşmek için gereken yükseklik: h_dogru = h_kullanilan × referans / bizim."""
    if bizim <= 0 or referans <= 0 or kullanilan <= 0:
        return None
    return kullanilan * referans / bizim


def _adaylar(kat) -> list[tuple[str, float]]:
    """Formülde geçen yükseklik adayları; geri hesaplanan değer bunlardan birine denk gelirse sebep bulunmuştur."""
    H, d = kat.kat_yuksekligi, kat.doseme_kalinligi
    kiris = kat.kiris_yuksekligi
    out = [("H (kat yüksekliği, net döşeme kabulü)", H), ("H − d (brüt döşeme kabulü)", max(H - d, 0.0))]
    if kiris:
        out.append(("H − kiriş (kalıp gören yüz)", max(H - kiris, 0.0)))
    return out


def _acikla(kat, gereken: float, kullanilan: float, ne: str) -> str:
    """Geri hesaplanan yüksekliği formüldeki adaylarla eşleştirir."""
    yakin = [(ad, v) for ad, v in _adaylar(kat) if abs(v - gereken) <= YUKSEKLIK_TOL]
    if yakin:
        ad, v = min(yakin, key=lambda t: abs(t[1] - gereken))
        return (f"Referansla eşleşen {ne} {gereken:.2f} m; bu tam olarak **{ad}** = {v:.2f} m. "
                f"Biz {kullanilan:.2f} m kullandık. Fark geometriden değil **kabulden** geliyor — referans da "
                f"müellifin kabulüdür, hangisinin doğru olduğunu tek başına söylemez; aynı hipotez birden çok "
                f"katta ve projede çıkmadan kural değiştirilmemeli.")
    return (f"Referansla eşleşen {ne} {gereken:.2f} m (biz {kullanilan:.2f} m kullandık, fark "
            f"{kullanilan - gereken:+.2f} m). Formüldeki adayların hiçbirine denk düşmüyor "
            f"({', '.join(f'{ad.split(chr(40))[0].strip()}={v:.2f}' for ad, v in _adaylar(kat))}): "
            f"suçlu yükseklik değil, eleman tespiti olabilir.")


def diagnose(kat) -> list[str]:
    out: list[str] = []
    H, d = kat.kat_yuksekligi, kat.doseme_kalinligi
    hk = H if kat.net_doseme else max(H - d, 0.0)
    hf = max(H - (kat.kiris_yuksekligi or d), 0.0)

    for s in kat.paftalar:
        ad = s.dosya.split("/")[-1]
        if s.hata:
            out.append(f"Pafta okunamadı ({ad}): {s.hata} — bu katın metrajı eksik.")
        elif not s.elemanlar:
            out.append(f"Pafta hiç eleman vermedi ({ad}): katman eşleşmesini ve birimi kontrol edin.")

    beton, kalip = _get(kat, "kolon_perde_beton_m3"), _get(kat, "kolon_perde_kalip_m2")
    if beton and kalip and beton.referans and kalip.referans:
        yb, yk = beton.yuzde, kalip.yuzde
        sapan_b, sapan_k = abs(yb) >= ESIK, abs(yk) >= ESIK
        if sapan_b and not sapan_k:
            g = _geri_hesap(hk, beton.bizim, beton.referans)
            msg = f"Kalıp eşleşiyor (%{yk:+.1f}) ama beton sapıyor (%{yb:+.1f}): geometri doğru, suçlu **beton yüksekliği**. "
            out.append(msg + (_acikla(kat, g, hk, "beton yüksekliği Hk") if g else ""))
        elif sapan_k and not sapan_b:
            g = _geri_hesap(hf, kalip.bizim, kalip.referans)
            msg = f"Beton eşleşiyor (%{yb:+.1f}) ama kalıp sapıyor (%{yk:+.1f}): geometri doğru, suçlu **kalıp yüksekliği**. "
            out.append(msg + (_acikla(kat, g, hf, "kalıp yüksekliği Hf") if g else ""))
        elif sapan_b and sapan_k and abs(yb - yk) < ESIK:
            g = _geri_hesap(hk, beton.bizim, beton.referans)
            msg = (f"Beton ve kalıp **aynı** oranda sapıyor (%{yb:+.1f} / %{yk:+.1f}): suçlu ortak çarpan — "
                   f"kat yüksekliği ya da eleman sayısı. ")
            out.append(msg + (_acikla(kat, g, hk, "beton yüksekliği Hk") if g else ""))
        elif sapan_b and sapan_k and yb * yk < 0:
            out.append(f"Beton %{yb:+.1f} ama kalıp %{yk:+.1f} — **ters yönde**: perde kalıp formülü "
                       f"(2 × uzunluk yerine çevre) ya da kolon / perde ayrımı yanlış olabilir. "
                       f"Kolon {kat.elemanlar.get('column', 0)}, perde {kat.elemanlar.get('shear_wall', 0)} adet.")
        elif sapan_b and sapan_k:
            out.append(f"Beton %{yb:+.1f}, kalıp %{yk:+.1f} — aynı yönde, farklı oranda: hem eleman tespiti hem "
                       f"yükseklik payı bakılmalı. Kolon {kat.elemanlar.get('column', 0)}, "
                       f"perde {kat.elemanlar.get('shear_wall', 0)} adet bulundu.")

    for olcu, etype, ad in [("kiris_beton_m3", "beam", "Kiriş"), ("doseme_beton_m3", "slab", "Döşeme"),
                            ("temel_beton_m3", "foundation", "Temel")]:
        dd = _get(kat, olcu)
        if dd and dd.referans and abs(dd.yuzde) >= ESIK:
            out.append(f"{ad} betonu %{dd.yuzde:+.1f} sapıyor ({dd.bizim:,.1f} / {dd.referans:,.1f}); "
                       f"{kat.elemanlar.get(etype, 0)} adet bulundu.".replace(",", "."))

    for s in kat.paftalar:
        if not s.hata and s.elemanlar and not s.birim_dogrulandi:
            out.append(f"Not: birim doğrulanmadı ({s.dosya.split('/')[-1]}, '{s.birim}' kullanıldı); "
                       f"miktarlar tutuyorsa birim de doğrudur.")

    if not out:
        out.append(f"Bütün ölçüler %{ESIK:g} bandında eşleşti. Bu, müellifin tablosuyla aynı sonucu verdiğimiz "
                   f"anlamına gelir; bağımsız doğruluk kanıtı değildir.")
    return out
