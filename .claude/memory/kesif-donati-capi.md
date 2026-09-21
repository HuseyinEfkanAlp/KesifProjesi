---
name: kesif-donati-capi
description: "Keşif projesinde donatı çapının çizimden okunması: ƒ glyph'i, blok öznitelikleri, çap karışımı"
metadata:
  type: project
---

Kıyı İstanbul A4-A5 statik çizimlerinde donatı yazıları `20ƒ14/20`, `4X7ƒ12/10`, `ƒ14/18`, `P01 182ƒ8/10 etr. l=196`
biçiminde. Çap simgesi **ISOCPEUR fontunun `ƒ` (U+0192) glyph'i**, Ø değil; `Q` ve `%%c` de görülür.

İki kritik bulgu (9 Eyl 2026):
1. **Donatı yazılarının çoğu blok yerleşimine bağlı öznitelikte (ATTRIB) duruyor.** ezdxf'te `Insert.virtual_entities()`
   bunları vermez, `insert.attribs` ayrı okunmalıdır. Düzeltilmeden önce temel paftasında 3.145 yazı / 87 donatı yazısı
   görünüyordu, sonra 11.298 / 786. Kolon adları, poz ve `L=1200` boy yazıları da bu yolla geliyor.
2. Ham DXF metin taraması (grup 1/3) yanıltıcıdır: blok tanımlarını bir kez sayar, `P1626` / `S1026` gibi eleman adları
   çap regex'ine takılır. Ölçüm daima `parser/loader.load_dxf` üzerinden yapılmalı.

Okunan gerçek dağılım: temel Ø20 %69 / Ø26 %18 / Ø14 %13, kolon Ø26 %36 / Ø14 %32 / Ø12 %21, döşeme Ø10 %70 / Ø12 %24,
kiriş Ø8 %26 / Ø26 %25 / Ø20 %15. Kalıp planlarında (dosya 3) donatı yazısı yok.

**Why:** Kullanıcı "projede hangi nervürlü demirin kullanıldığını çıkaramaz mıyız" diye sordu; oran demiri tek "çap
karışık" ürüne düşüyordu ve fiyatlanamıyordu.
**How to apply:** Yeni bir çap / donatı biçimi eklerken `parser/rebar_mix.py` DIA_SYM'e bak; ATTRIB'siz okuma yapan
başka bir yol eklenirse aynı kayıp tekrar eder. İlgili: [[kesif-fiyat-modeli]], [[kesif-standart-poz]]
