---
name: kesif-kapsam-sahipligi
description: "Kullanıcı ilkesi: okunmuşu tekrar okuma — her kalemin tek sahibi vardır, ikinci pafta yalnız eklemesini yazar (21 Eyl 2026)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8f9f0f1b-f0c3-447e-a589-3aecc3af9593
  modified: 2026-09-21T07:25:52.367Z
---

21 Eyl 2026, kullanıcı: "Okunmuşu tekrar okumayalım. Statik attım, ondan çıkardıklarımı başka plandan
çıkarmayayım; elektrik tava planından tava çıktıysa zayıf akımdan tekrar çıkarmayayım, **sadece eklemeler
varsa onları belirtip ekleyeyim**." Aynı mesajda hedef de yinelendi: "planda gerekli her şey yazar, o plandan
çıkarmalıyız her şeyi" (bkz. [[kesif-projesi-hedef]]).

Kurulan: `backend/app/quantity/scope.py` + `planset.PlanType.owns` (yetki tablosu) + `services.measured_elements`
(project_quantities ve project_boq buradan besleniyor) + Metraj ekranında **Kapsam** paneli.

**Kural: aynı nesne bir kez sayılır, ayrı nesne her zaman sayılır.** Aynılığın kanıtı konumdur (blok + kot +
tip + merkez + büyüklük). Yetki sırası: 0 kalemi ölçmek için çizilen pafta, 1 disiplini taşıyan pafta,
2 disiplini tutan çizim, 3 ilgisiz. **Eşit yetkili iki pafta birbirini asla elemez.**

**Kat kimliği de kullanıcıdan istenmez** (`services._floor_identity`): kot ya da plan adındaki kat sırası
(`levels.floor_rank`) — elektrik/mekanik paftasında kot yazmaz, kat adı yazar. İkisini birden taşıyan pafta
iki kimliği birbirine bağlar. Bu, kullanıcının "tablo falan bilmem, en doğru metraj nasıl çıkarsa öyle olsun"
talimatının karşılığı: kuralın çalışması için kullanıcıdan kot girmesi istenmiyor.

**Kanıt yoksa düşürme yok** — bu kuralın omurgası: örtüşmeyen iki pafta aynı dosyada yan yana duran ayrı
bölgeler de olabilir (bir DXF'te temel + zemin). Kat biliniyorsa öteleme denenir ve doğrulanır (en az 3 nesne, %70 eşleşme; bu yolla düşen miktar
"kontrol edilmeli" işaretlenir — öteleme çıkarımdır, ayrı bir bloğun gerçek ölçümünü sildirebilir); kot yoksa
hiçbir miktar düşmez, iki miktar ve yapılacak iş kullanıcıya yazılır. Sessizce kaybolan miktar, çift
sayımdan zararlıdır (bkz. [[kesif-gercek-dosya-dogrulama]], [[kesif-kanit-siralamasi]]).

Geliştirirken çıkan üç gerçek hata (üçü de testle kilitlendi): (1) aynı DXF'te yan yana duran temel/zemin
paftası "ayrı orijin" sanılıp temelin kolonları düşüyordu; (2) üç pafta aynı nesneyi çizince üçüncüdeki kopya
"ek" sanılıyordu; (3) eşleştirme "uyan ilki"ni alınca birebir ikiz komşuya kapılıyor, ikiz ek sanılıyordu —
B Blok zemin planında 830 nesnenin 10'u, %1,2 fazla metraj. Eşleşme artık **en yakın** nesneyi seçer.

Ölçüldü: B Blok zemin planı iki kez yüklendi — kapsam kapalı 4.341,7 m³, açık 2.170,9 m³ = tek pafta ile
birebir, 830/830 eşleşme, 0 sahte ek. A4-A5 mimari seti (16 pafta) kapsam açık/kapalı birebir aynı, tek uyarı
yok (yanlış alarm yok). Kalibrasyon kapısı %2,14 → %2,14. Commit 118d774, 469 test.

**Why:** Kullanıcı tam setli projede (statik + mimari + elektrik + mekanik, çoğu birbirinin altlığı) güvenilir
tek bir metraj istiyor; hem çift sayım hem sessiz kayıp ihaleyi bozar.
**How to apply:** Yeni bir disiplin / plan tipi eklerken `PlanType.owns` satırını da doldur (yoksa kalemin
sahibi olmaz, "yetkili paftası yüklenmedi" uyarısı çıkar). Metraja girmeyen pafta (donatı, kesit, detay)
sahiplik kuramaz. Kapsam kuralını ölçmek için kapatmak: proje parametresi `scope_off=1`. Kapsamı etkileyen
her değişiklikten sonra `cd backend && python calib/senaryo_altlik.py` koştur (çift sayım kapısı, repoda).
