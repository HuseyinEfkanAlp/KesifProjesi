"""Kalibrasyon döngüsü: ölç → doğru metrajla karşılaştır → farkı sebebe bağla → düzelt → gerileme var mı bak.

Bu paket metraj üretmez; ürettiğimiz metrajı **bilinen doğru metrajla** karşılaştırır. Amaç, bir kuralı
değiştirdiğimizde "bu dosyada düzeldi ama diğerinde bozuldu mu" sorusunun elle değil ölçerek cevaplanması.

Doğru metraj (referans) iki yerden gelir:
  1. **Çizimin kendi metraj tablosu** — Türk statik ofisleri kendi icmallerini paftaya çizer
     (`TABLE4`, `VM-METRAJ`, `mtr_tb`). Müellifin kendi sayısıdır; dosya geldiği anda hazır referanstır.
  2. **Elle girilen referans** — hakediş icmali, ihale keşfi, bağımsız ölçüm.

Referansın güveni her zaman kayıtlıdır (`guven`): aktarılmış bir tablo bağımsız ölçüm değildir ve
"eşleşti" demek "doğru" demek değildir — yalnız müellifle aynı sonucu verdiğimiz anlamına gelir.

Kullanım:  python -m app.calib            (bütün korpusu ölç, rapor yaz)
           python -m app.calib --kaydet   (sonucu taban olarak kaydet: sonraki koşular buna göre kıyaslanır)
"""
from .corpus import Corpus, Floor, load_corpus, corpus_dir
from .runner import FloorResult, RunResult, run_corpus, run_one
from .diagnose import diagnose

__all__ = ["Corpus", "Floor", "load_corpus", "corpus_dir",
           "FloorResult", "RunResult", "run_corpus", "run_one", "diagnose"]
