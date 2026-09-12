"""python -m app.calib [--kaydet] [--korpus AD]

Bütün korpusu ölçer, referansla karşılaştırır, farkı sebebe bağlar ve varsa önceki tabanla kıyaslar.
Çıkış kodu: taban varsa ve genel sapma kötüleştiyse 1 (gerileme kapısı; CI'da kullanılabilir).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .corpus import load_all, corpus_dir
from .runner import run_corpus

TABAN = Path(__file__).resolve().parents[2] / "calib" / "taban.json"


def _yaz(results) -> None:
    for r in results:
        print(f"\n{'=' * 78}\n{r.proje}  ({r.korpus})")
        print(f"referansın güveni: {r.guven}")
        for kat in r.katlar:
            el = ", ".join(f"{k} {v}" for k, v in sorted(kat.elemanlar.items())) or "eleman yok"
            print(f"\n  ── {kat.kat}  (H={kat.kat_yuksekligi:.2f} d={kat.doseme_kalinligi:.2f} "
                  f"kiriş={kat.kiris_yuksekligi or 0:.2f} {'net' if kat.net_doseme else 'brüt'} döşeme)")
            print(f"     {el}")
            if kat.farklar:
                print(f"     {'ölçü':26s} {'bizim':>12s} {'referans':>12s} {'fark':>10s}  %")
                for dd in kat.farklar:
                    print(f"     {dd.olcu:26s} {dd.bizim:>12,.1f} {dd.referans:>12,.1f} "
                          f"{dd.fark:>+10,.1f}  {dd.yuzde:+6.2f}".replace(",", "."))
            for t in kat.teshis:
                print(f"     → {t}")
        s = r.skor()["_genel"]
        print(f"\n  GENEL: ortalama mutlak sapma %{s['ortalama_mutlak_yuzde']}, "
              f"en kötü %{s['en_kotu_yuzde']} ({s['kat_sayisi']} karşılaştırma, {r.saniye:.1f} s)")


def _kiyasla(results) -> int:
    """Önceki tabanla kıyaslar; kötüleşme varsa 1 döndürür (gerileme kapısı)."""
    if not TABAN.exists():
        print(f"\nTaban yok ({TABAN.name}). --kaydet ile bu koşuyu taban yapın.")
        return 0
    taban = {x["korpus"]: x for x in json.loads(TABAN.read_text(encoding="utf-8"))}
    kotu = False
    print(f"\n{'=' * 78}\nTABANLA KIYAS ({TABAN.name})")
    for r in results:
        onceki = taban.get(r.korpus)
        if not onceki:
            print(f"  {r.korpus}: tabanda yok (yeni korpus)")
            continue
        a = onceki["skor"]["_genel"]["ortalama_mutlak_yuzde"]
        b = r.skor()["_genel"]["ortalama_mutlak_yuzde"]
        isaret = "=" if abs(a - b) < 0.01 else ("↓ iyileşti" if b < a else "↑ GERİLEME")
        if b > a + 0.01:
            kotu = True
        print(f"  {r.korpus}: %{a} → %{b}  {isaret}")
        for kat in r.katlar:
            eski = next((k for k in onceki["katlar"] if k["kat"] == kat.kat), None)
            if not eski:
                continue
            for dd in kat.farklar:
                e = next((x for x in eski["farklar"] if x["olcu"] == dd.olcu), None)
                if e and abs(dd.yuzde) > abs(e["yuzde"]) + 0.01:
                    print(f"      {kat.kat}/{dd.olcu}: %{e['yuzde']:+.2f} → %{dd.yuzde:+.2f}")
    return 1 if kotu else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.calib", description=__doc__)
    ap.add_argument("--kaydet", action="store_true", help="bu koşuyu taban olarak kaydet")
    ap.add_argument("--korpus", help="yalnız bu korpusu çalıştır (dosya adı, uzantısız)")
    ap.add_argument("--json", dest="json_out", help="sonucu bu dosyaya JSON yaz")
    a = ap.parse_args(argv)

    corpora = load_all()
    if a.korpus:
        corpora = [c for c in corpora if c.ad == a.korpus]
    if not corpora:
        print(f"Korpus bulunamadı: {corpus_dir()}")
        return 2

    results = run_corpus(corpora)
    _yaz(results)
    payload = [r.to_dict() for r in results]
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nJSON yazıldı: {a.json_out}")
    if a.kaydet:
        TABAN.parent.mkdir(parents=True, exist_ok=True)
        TABAN.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nTaban kaydedildi: {TABAN}")
        return 0
    return _kiyasla(results)


if __name__ == "__main__":
    sys.exit(main())
