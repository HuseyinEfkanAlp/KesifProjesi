---
name: kesif-antet-verisi
description: "Ruhsat antedi ve benzeri listeler pafta sayılmaz ama içerikleri proje verisi olarak okunur"
metadata:
  type: feedback
---

11 Eyl 2026: Kullanıcı "plandaki her şey pafta değil, listeyi de pafta diye tanıyorsun, yapma" dedi; ne
yapılsın diye sorulunca "o listeler aslında o projede nelerin kullanıldığını gösteriyor, sen o listeleri de
kullanabilirsin bir şekilde" dedi. Yani: metraja sokma, **ama oku**.

A4-A5 dosyasındaki somut örnek: `Başlık_Yazı` / `VM_Antet` katmanlarındaki ruhsat antedi — MALZEME "C35-S420",
TEMEL TİPİ "RADYE", PERDE "VAR", B.A.K "plak", KAT ADEDİ, İNŞ. ALANI, ZEMİN TAŞIMA GÜCÜ. Ayrıca "VAZİYET
PLANI" yazan 11 nesnelik boş şablon çerçevesi pafta listesine giriyordu.

**Why:** Antet ölçülecek geometri taşımaz; plan sanılırsa sahte metraj üretir. Ama beton/donatı sınıfını
kullanıcı bugün elle giriyor — antet zaten söylüyor.
**How to apply:** `backend/app/parser/titleblock.py` anteti okur (etiketin sağındaki ya da hemen altındaki
değer); `Sheet.kind` = plan/antet/bos. Antet kanıtı **katman adı değil** kutunun içindeki tanınmış etiketlerdir
— pafta çerçevesi de çoğu projede "ANTET" katmanında çizilir. "Boş çerçeve" eşiği göreli (dosyadaki paftaların
medyanına göre), mutlak eşik küçük projelerin gerçek paftalarını eliyordu. Okunan değer yalnız **boş** proje
parametresine yazılır, kullanıcının girdiği ezilmez. İlgili: [[kesif-standart-poz]], [[kesif-fiyat-modeli]]
