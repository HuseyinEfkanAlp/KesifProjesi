"""Kapsam: kalem mahale mi yazılır, bina geneline mi (app/scope.py).

Kullanıcının isteği "A mahalinde şu kadar seramik" idi — ama bu cümle her kalem için kurulamaz.
Testler ayrımı ve özellikle **duvar kararını** sabitler: gövde bina geneli, yüzeyleri mahal bazlı.
"""
from app.quantity.boq import BoqItem
from app.scope import GENEL, MAHAL, scope_of


def test_duvar_govdesi_bina_geneli_yuzeyleri_mahal_bazli():
    """Bir duvar iki mahalin ortak sınırıdır: m²'sini tek mahale yazmak yanlıştır.
    Ama her yüzü tek bir mahale bakar — sıva ve boya mahalin işidir."""
    assert scope_of("duvar", "architectural") == GENEL
    assert scope_of("DUVAR_YTONG", "ksf:MIM") == GENEL
    assert scope_of("siva", "architectural") == MAHAL
    assert scope_of("boya", "architectural") == MAHAL


def test_tasiyici_ve_kabuk_bina_geneli():
    for kind, disc in [("beton", "structural"), ("demir", "structural"), ("kalip", "structural"),
                       ("KAZI", "ksf:STA"), ("GROBETON", "ksf:STA"), ("KENET_CATI", "ksf:CAT"),
                       ("MANTOLAMA", "ksf:CEP"), ("ASFALT", "ksf:ALT"), ("ASANSOR", "ksf:ASN"),
                       ("TEMEL_SU_YALITIMI", "ksf:IZO")]:
        assert scope_of(kind, disc) == GENEL, kind


def test_tesisatta_hat_genel_uc_cihaz_mahal():
    """Bir kablo kattan kata uzanır; geçtiği odalara bölününce sipariş edilemeyecek sayılar çıkar."""
    for kind in ("kablo", "boru", "tava"):
        assert scope_of(kind, "electrical") == GENEL, kind
    for kind in ("armatur", "PRIZ", "ANAHTAR", "KAMERA", "YANGIN_DEDEKTOR"):
        assert scope_of(kind, "electrical") == MAHAL, kind
    assert scope_of("BORU_PPRC", "ksf:MEK") == GENEL
    assert scope_of("RADYATOR", "ksf:MEK") == MAHAL
    assert scope_of("MENFEZ", "ksf:HAV") == MAHAL
    assert scope_of("KLOZET", "ksf:SIH") == MAHAL


def test_ince_isler_mahal_bazli():
    for kind in ("SERAMIK_ZEMIN", "SAP", "DERZ_DOLGU", "ASMA_TAVAN", "SUPURGELIK", "ASTAR"):
        assert scope_of(kind, "ksf:INC") == MAHAL, kind


def test_islak_hacim_zemini_mahalin_yapi_kabugu_binanin():
    assert scope_of("SURME_IZOLASYON", "ksf:IZO") == MAHAL
    assert scope_of("XPS", "ksf:IZO") == GENEL


def test_taninmayan_kalem_bina_geneli_sayilir():
    """Bilinmeyen bir kalemi mahale yazmak uydurmadır; bina geneli güvenli taraftır."""
    assert scope_of("YENI_BIR_KALEM", "ksf:???") == GENEL


def test_boq_kalemi_kapsamini_kendisi_belirler():
    it = BoqItem(key="siva:*", kind="siva", group="*", label="Sıva", unit="m²", quantity=1.0,
                 discipline="architectural")
    assert it.scope == MAHAL
    assert it.to_dict()["scope_label"] == "Mahal bazlı"
    duvar = BoqItem(key="duvar:a", kind="duvar", group="a", label="Duvar", unit="m²", quantity=1.0,
                    discipline="architectural")
    assert duvar.scope == GENEL


def test_acikca_verilen_kapsam_korunur():
    it = BoqItem(key="duvar:a", kind="duvar", group="a", label="Duvar", unit="m²", quantity=1.0,
                 discipline="architectural", scope=MAHAL)
    assert it.scope == MAHAL
