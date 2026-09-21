---
name: kesif-cetvel-lejant
description: "Cetvel / poz listesi pafta değildir ama elenmez: geometrisi ölçülmez, yazıları veri olarak okunur"
metadata:
  type: feedback
---

11 Eyl 2026: Kullanıcı "bazı planların yanında o planda kullanılan ürünlerin cetvelleri var, bunu pafta olarak
görmeyeceğiz, bu cetvellerden bilgileri alacağız" dedi. Pafta içeriği dört türe ayrıldı (`Sheet.kind`):
`plan` · `antet` · `bos` · `cetvel`.

**Tuzak:** önce yalnız `bos` kuralını yazmıştım (geometrisi medyanın %5'inden az olan kutu elenir). Bu kural
B2 blokta doğrama cetvelini de eledi — cetvelin geometrisi zaten yoktur, **değeri yazılarındadır**: tek başına
14 poz / 170 adet doğrama taşıyor. Bu yüzden `cetvel`, `bos`tan önce gelir: poz satırı (`parse_schedule_text`)
ya da lejant başlığı (`CETVEL_RE`) taşıyan düşük-geometrili kutu elenmez, eklenir ve okunur; listede
"geometrisi ölçülmez, poz ve adetleri okunur" diye işaretlenir, "Tümünü seç" onu atlamaz.

**Ölçülen gerçek:** kullanıcının dosyalarında (A4-A5 5 DXF, B2, C1–C4, C BLOK Ruhsat, Ortak Alan) **sembol
lejantı yok** — "bu çizgi şu ürün" tablosu hiçbirinde geçmiyor. Var olanlar: doğrama poz cetveli (B2), ruhsat
anteti, donatı metraj tabloları, "Çiroz Donatı Tablosu" (C BLOK Ruhsat). Yazdığım sembol-lejantı bulucu
prototipi hep yanlış pozitif verdi (aks balonu, mahal alanı yazısı, kot yazısı). Sembol→ürün eşlemesi
**kalibre edilecek gerçek örnek gelmeden yazılmamalı**.

**Why:** Cetvel hem pafta sayılmamalı (sahte metraj) hem elenmemeli (gerçek adet kaybı); ikisi ayrı karar.
**How to apply:** Yeni bir "pafta değil" kuralı eklerken önce sor: bu kutunun **yazılarında** veri var mı?
Varsa elenmez, `kind` ile işaretlenip okunur. İlgili: [[kesif-antet-verisi]], [[kesif-gercek-dosya-dogrulama]]
