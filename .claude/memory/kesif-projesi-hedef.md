---
name: kesif-projesi-hedef
description: "KesifProjesi'nin amacı ve 8 Eyl 2026 itibarıyla kapsamı — tüm disiplinlerde keşif + maliyet + süre; KÇS ana yol, sezgisel tanıma dört disiplinde"
metadata: 
  node_type: memory
  type: project
  originSessionId: 13be935c-a3e8-4d44-8d34-639816dc47ed
  modified: 2026-09-08T11:12:28.677Z
---

Amaç: DXF / DWG planlarından tüm disiplinler için metraj, keşif (iş grubu + ÇŞB pozu + ölçü kuralı + reçeteli alt işler ve
işçilik), maliyet ve süre. Ana yol KÇS standart çizim (katman adı = kalem); standart dışı çizimde sezgisel tanıma.

Kapsam (8 Eyl 2026): sezgisel disiplinler statik, mimari, elektrik ve **mekanik** (boru / kanal / cihaz; `detectors/mechanical.py`);
aynı paftada ek disiplin açılabilir; eşlemeli paftalarda (tavan, kaplama, cephe, çatı, peyzaj, altyapı) katman adından otomatik
eşleme (onay / ölçülmez); kaba yapıda kazı + geri dolgu + lento türetmesi; 137 kalemde reçete. Kullanıcı bundan sonra gerçek
tam setli bir projeyle uçtan uca test edecek ("daha sonra test ederiz hepsini"). 9 Eyl 2026 güven paketi ile
zayıf noktalar kapatıldı: bkz. [[kesif-guven-paketi]].

Kullanıcı ilkesi (8 Eyl 2026): "kat yüksekliği zaten planda yok mu, kotlardan belli olur" — çizimden okunabilecek hiçbir şey
kullanıcıdan istenmemeli; `parser/levels.py` + `services.storey_heights` kotlardan kat yüksekliğini türetir, H parametresi yalnız düzeltme.

**Why:** Kullanıcı "bir eksiğimiz kalmasın" dedi; eksik listesi (mekanik sezgisel yok, eşleme elle, kazı yok, poz kısmi) kapatıldı.
**How to apply:** Yeni eksik bulunursa önce README'deki "Gerçek çizimde öğrenilenler" bölümlerine bak; gerçek çizimle doğrulanmamış
kalibrasyonları (reçete çarpanları, mekanik sistem tahmini) sonuçta not olarak işaretle. İlgili: [[kesif-standart-poz]], [[kesif-projesi-ortam]]
