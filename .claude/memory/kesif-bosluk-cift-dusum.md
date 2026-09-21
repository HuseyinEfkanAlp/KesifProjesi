---
name: kesif-bosluk-cift-dusum
description: "Kapı/pencere boşluğu duvardan düşülmeden önce sorulacak soru: duvar zaten kesilerek mi çizilmiş?"
metadata:
  type: project
---

11 Eyl 2026: Kullanıcı "duvar metrekaresi de net olsun, gerçekçi ve güvenilir olsun" dedi. İnceleyince duvar
kaleminde `openings_m2 = 0` çıkıyordu ve uyarı "eşleşmeyen boşluklar düşülmedi, ilgili alan brüt kalabilir"
diyordu. İlk refleks toleransı büyütmekti — **yanlış olurdu.**

Ölçüm (B2 blok, 93 boşluk): 86'sı hiçbir duvarla çakışmıyor; en yakın duvar medyan **0,51 m** ötede ve iki
duvar parçası arasındaki açıklık boşluk genişliğine eşit (1,42 m ≈ 1,40 m pencere). Yani **duvar boşlukta
kesilerek çizilmiş, alan zaten net**. Hepsini düşmek ~%17 çift düşüm demekti.

Kural (`quantity/openings.py`): boşluk duvarın **üstünde** mi (mesafe ≤ duvarın yarı kalınlığı + 5 cm) →
düşülür. Yakında duvar var ama üstünde değil → `already_net`, düşülmez, "çizimde kesilmiş" diye bildirilir.
Hiç duvar yok → gerçek uyarı. Tolerans duvar kalınlığından türer; sabit mesafe her ölçekte yanlıştır.

Yanında çıkan ayrı hata: `geometry()` çizgiye çökmüş (dejenere) blok sınırına `None` dönüyordu — KSF
duvarlarında bütün kapı/pencereler "yakınında duvar yok" sayılıp 15,75 m² boşluk hiç düşülmüyordu. Bir yıldır
kırık duran `test_ksf_wall_openings_deducted_and_finishes` bu yüzden kırıktı; düzeldi (331 test geçiyor).

**How to apply:** Bir metraj düzeltmesinde eşiği büyütmeden önce "bu düzeltme çift sayıma yol açar mı" diye
sor ve gerçek dosyada dağılıma bak. İlgili: [[kesif-gercek-dosya-dogrulama]], [[kesif-demir-raporu]]
