"""Bir iş kalemi mahale mi yazılır, bina geneline mi?

"A mahalinde şu kadar seramik" cümlesi her kalem için kurulamaz. Kolonun betonu bir mahalin değil
binanın işidir; kolon iki mahalin arasındaysa m³'ünü birine yazmak yanlıştır. Kablo katlar boyunca
uzanır, geçtiği odalara bölüştürülünce ortaya kimsenin sipariş edemeyeceği sayılar çıkar. Buna
karşılık seramik, şap, boya, armatür ve kapı **mahalin kendisine** aittir — bir odayı bitirmenin
maliyeti bunlardan çıkar.

| Bina geneli | Mahal kırılımı |
|---|---|
| beton, demir, kalıp, iskele, sarf | seramik / granit / parke, şap, derz, yapıştırıcı |
| kazı, dolgu, grobeton, temel yalıtımı | sıva, boya, astar, süpürgelik, duvar kaplaması |
| **duvar gövdesi**, kablo, boru, tava, kanal | asma tavan, tavan alçıpanı, tavan boyası |
| cephe, çatı, altyapı, peyzaj, asansör | armatür, priz, anahtar, kamera, dedektör, sprinkler, menfez, radyatör, vitrifiye, kapı, pencere |

**Duvar** özel bir karardır: bir duvar iki mahalin ortak sınırıdır, gövdesinin m²'sini tek mahale
yazmak yanlıştır — o yüzden **gövde bina geneli**. Ama duvarın her **yüzü** tek bir mahale bakar:
sıva ve boya mahal bazlıdır. Bu ayrım, duvar elemanının mahal dağıtımına girmeye devam etmesini
gerektirir (sıvası oraya düşsün diye); ayıklama eleman düzeyinde değil **kalem** düzeyinde yapılır.

Kaynak sırası: katalog kaleminin açık `scope` alanı > buradaki kod istisnaları > disiplin
varsayılanı. Reçete çocukları ayrıca ele alınmaz — kodları zaten burada sınıflanır, sınıflanmayan
çocuk ebeveyninin disiplinini taşır.
"""
from __future__ import annotations

GENEL, MAHAL = "genel", "mahal"
SCOPES = (MAHAL, GENEL)
SCOPE_LABEL = {MAHAL: "Mahal bazlı", GENEL: "Bina geneli"}

# Disiplin varsayılanı. Tesisat disiplinleri "genel"dir: hattı (kablo, boru, kanal) bina geneli,
# ucundaki cihazı (armatür, priz, menfez, radyatör) CODE_SCOPE mahale çeker.
DISCIPLINE_SCOPE = {
    "STA": GENEL, "CAT": GENEL, "CEP": GENEL, "ALT": GENEL, "PEY": GENEL, "ASN": GENEL, "IZO": GENEL,
    "ELK": GENEL, "HAV": GENEL, "MEK": GENEL, "SIH": GENEL, "YAN": GENEL,
    "INC": MAHAL, "MIM": MAHAL, "ZAY": MAHAL,
    # sezgisel disiplin adları (katalog kodu olmayan kalemler: duvar, sıva, armatür…)
    "STRUCTURAL": GENEL, "ARCHITECTURAL": MAHAL, "ELECTRICAL": GENEL, "MECHANICAL": GENEL,
    "REBAR": GENEL, "MAPPED": GENEL, "STANDARD": GENEL,
}

# Disiplin varsayılanının dışında kalanlar. Kalem kodu (KÇS) ya da sezgisel tür adı, büyük harf.
CODE_SCOPE = {
    # --- MIM: duvar GÖVDESİ bina geneli (iki mahalin ortak sınırı), yüzeyleri mahal bazlı
    "DUVAR": GENEL, "DUVAR_YTONG": GENEL, "DUVAR_TUGLA": GENEL, "DUVAR_BIMS": GENEL,
    "DUVAR_ALCIPAN": GENEL, "DUVAR_ISCILIK": GENEL, "DUVAR_TUTKAL": GENEL, "HARC": GENEL,
    "LENTO": GENEL, "ALCIPAN_PROFIL": GENEL, "ALCIPAN_VIDA": GENEL, "DERZ_BANDI": GENEL,
    # --- ELK / ZAY: hat bina geneli, uç cihaz mahal bazlı
    "ARMATUR": MAHAL, "ARMATUR_MONTAJ": MAHAL, "ACIL_AYDINLATMA": MAHAL,
    "PRIZ": MAHAL, "PRIZ_MONTAJ": MAHAL, "ANAHTAR": MAHAL, "BUAT": MAHAL,
    "DATA_PRIZ": MAHAL, "KAMERA": MAHAL, "HOPARLOR": MAHAL, "KARTLI_GECIS": MAHAL,
    "YANGIN_DEDEKTOR": MAHAL, "YANGIN_BUTON": MAHAL,
    "KABLO": GENEL, "BORU": GENEL, "TAVA": GENEL, "DATA_KABLO": GENEL,
    # --- MEK / HAV / SIH / YAN: hat bina geneli, uç cihaz mahal bazlı
    "RADYATOR": MAHAL, "FANCOIL": MAHAL, "VRF_IC_UNITE": MAHAL, "MENFEZ": MAHAL, "DAMPER": MAHAL,
    "KLOZET": MAHAL, "LAVABO": MAHAL, "PISUAR": MAHAL, "BATARYA": MAHAL, "YER_SUZGECI": MAHAL,
    "VITRIFIYE_MONTAJ": MAHAL, "SPRINKLER": MAHAL, "SPRINKLER_MONTAJ": MAHAL,
    "YANGIN_DOLABI": MAHAL, "SONDURME_TUPU": MAHAL,
    # --- IZO: ıslak hacim zemini mahalin, yapı kabuğu binanın
    "SURME_IZOLASYON": MAHAL, "KORUMA_SAPI": MAHAL,
}


def scope_of(kind: str, discipline: str = "", catalog=None) -> str:
    """Kalemin kapsamı: "mahal" (mahal kırılımına girer) ya da "genel" (bina geneli).

    kind: KÇS kalem kodu ya da sezgisel tür adı ("duvar", "armatur"). discipline: "ksf:INC" ya da
    "architectural". Katalogda kalemin kendi `scope` alanı varsa o kazanır — /standard ekranından
    düzenlenebilsin diye."""
    kod = (kind or "").upper()
    if catalog is not None:
        it = catalog.get(kod)
        if it is not None and getattr(it, "scope", ""):
            return it.scope
    if kod in CODE_SCOPE:
        return CODE_SCOPE[kod]
    disc = (discipline or "").split(":")[-1].upper()
    return DISCIPLINE_SCOPE.get(disc, GENEL)
