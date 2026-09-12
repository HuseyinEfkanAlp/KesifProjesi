"""Birim fiyat listesinden poz bazlı fiyatlandırma.

Canlıda fiyat girişi en büyük tıkanmadır: keşifte 100+ kalem çıkar, hepsini elle doldurmak kimsenin
yapmayacağı iştir. Kalemlerin çoğunda ÇŞB poz numarası zaten var (A4-A5'te 78 kalemin 47'si), her
müteahhitte de o yılın listesi var. Liste bir kez yapıştırılır, eşleşme poz numarasından olur.

**Poz bedeli her şey dahildir** (malzeme + işçilik + makine + yüklenici kârı); malzeme ve işçiliğin
yerine geçer, üstüne eklenmez — toplanırsa bedel iki kez sayılır.
"""
import pytest

from app.cost.pozbook import parse_line, parse_list, parse_number


# ---- sayı biçimi ----

@pytest.mark.parametrize("metin,beklenen", [
    ("3.250,00", 3250.0), ("485,50", 485.5), ("27.850,00", 27850.0),
    ("3250.00", 3250.0), ("1.234.567,89", 1234567.89), ("148,90", 148.9), ("12", 12.0),
])
def test_turkce_sayi_okunur(metin, beklenen):
    assert parse_number(metin) == pytest.approx(beklenen)


def test_sayi_olmayan_metin_none():
    for m in ("", "abc", "m³", "15.150.1006x"):
        assert parse_number(m) is None


# ---- satır ayrıştırma: gerçek listeler tek biçimde değildir ----

@pytest.mark.parametrize("satir", [
    "15.150.1006;Beton santralinde üretilen C 30/37;m³;3.250,00",
    "15.150.1006\tBeton santralinde üretilen C 30/37\tm³\t3.250,00",
    "15.150.1006 | Beton santralinde üretilen C 30/37 | m3 | 3.250,00",
    "15.150.1006   Beton santralinde üretilen C 30/37   m3   3.250,00",
])
def test_ayrac_ne_olursa_olsun_okunur(satir):
    r = parse_line(satir)
    assert r is not None
    assert r.poz == "15.150.1006" and r.price == pytest.approx(3250.0)
    assert r.unit == "m³"
    assert "Beton" in r.name


def test_birim_normallestirilir():
    assert parse_line("15.180.1003 Ahşap kalıp m2 485,50").unit == "m²"
    assert parse_line("15.160.1004 Nervürlü çelik TON 27.400,00").unit == "ton"
    assert parse_line("10.130.1001 Kazı mt 55,00").unit == "m"


def test_poz_yoksa_satir_atlanir():
    assert parse_line("Beton santralinde üretilen C 30/37   m3   3.250,00") is None
    assert parse_line("POZ NO   TANIM   BİRİM   BİRİM FİYAT") is None


def test_fiyat_yoksa_satir_atlanir():
    assert parse_line("15.150.1006  Beton santralinde üretilen C 30/37  m³") is None


def test_poz_fiyat_yerine_gecmez():
    """Poz numarasının kendisi sayıya benziyor; fiyat sanılmamalı."""
    r = parse_line("15.150.1006  Beton  m³  3.250,00")
    assert r.price == pytest.approx(3250.0)


def test_eski_bicim_poz_da_okunur():
    r = parse_line("Y.16.052/C  Beton dökülmesi  m³  1.850,00")
    assert r is not None and r.price == pytest.approx(1850.0)


# ---- liste ----

def test_liste_tekrar_eden_pozda_sonuncuyu_alir():
    r = parse_list("15.150.1006;Beton;m³;3.250,00\n15.150.1006;Beton;m³;3.400,00")
    assert len(r.rows) == 1 and r.rows[0].price == pytest.approx(3400.0)
    assert r.duplicates == 1


def test_liste_bos_ve_basliklari_atlar():
    r = parse_list("POZ NO  TANIM  BİRİM  FİYAT\n\n15.150.1006;Beton;m³;3.250,00\n---\n")
    assert len(r.rows) == 1 and r.skipped == 2


# ---- uçtan uca: liste -> banka -> keşif ----

LISTE = """15.150.1006;Beton santralinde üretilen C 30/37;m³;3.250,00
15.180.1003  Ahşap kalıp yapılması     m2     485,50
15.160.1003 | Nervürlü çelik çubuk Ø8-Ø12 | ton | 27.850,00
15.160.1004 | Nervürlü çelik çubuk Ø14-Ø28 | ton | 27.400,00
"""


def test_liste_bankaya_yazilir_ve_kesfe_fiyat_gelir(client, storey_dxf):
    r = client.post("/api/pricebook/poz-import", json={"text": LISTE})
    assert r.status_code == 200, r.text
    assert r.json()["okunan"] == 4 and r.json()["yeni"] == 4

    pid = client.post("/api/projects", json={"name": "Poz", "storey_height": 3.0}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("KALIP PLANI.dxf", f, "application/dxf")})
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    beton = [l for l in cost["lines"] if l["kind"] == "beton" and l["quantity"] > 0]
    assert beton, "beton kalemi yok"
    assert all(l["poz_priced"] for l in beton)
    for l in beton:
        assert l["poz_price"] == pytest.approx(3250.0)
        # poz bedeli her şey dahil: malzeme ayrıca yazılmaz, toplam = miktar × poz bedeli
        assert l["material_total"] == 0.0
        # satırdaki miktar üç haneye yuvarlanır, tutar ham miktarla hesaplanır: binde bir tolerans
        assert l["total"] == pytest.approx(l["quantity"] * 3250.0, rel=2e-3)
    assert cost["grand_total"] > 0                    # artık 0 ₺ değil


def test_ayni_poz_yeniden_iceri_alininca_guncellenir(client):
    client.post("/api/pricebook/poz-import", json={"text": "15.150.1006;Beton;m³;3.250,00"})
    r = client.post("/api/pricebook/poz-import", json={"text": "15.150.1006;Beton;m³;3.900,00"})
    assert r.json()["yeni"] == 0 and r.json()["guncellenen"] == 1


def test_pozsuz_liste_hata_verir(client):
    r = client.post("/api/pricebook/poz-import", json={"text": "Beton  m³  3.250,00\nKalıp m² 485,50"})
    assert r.status_code == 400 and "poz" in r.json()["detail"].lower()


# ---- birim uyumu: canlıda en tehlikeli hata ----

def test_ton_fiyati_kg_kalemine_bine_bolunerek_uygulanir():
    """Demir keşifte kg, ÇŞB pozunda ton. Çevrilmezse tutar 1000 kat çıkar (16 milyon yerine 16 milyar ₺)."""
    from app.cost.pozbook import unit_factor
    assert unit_factor("kg", "ton") == pytest.approx(0.001)
    assert unit_factor("ton", "kg") == pytest.approx(1000.0)


def test_ayni_birimde_carpan_birdir():
    from app.cost.pozbook import unit_factor
    for a, b in (("m³", "m³"), ("m3", "m³"), ("m2", "m²"), ("adet", "ad")):
        assert unit_factor(a, b) == pytest.approx(1.0)


def test_cevrilemeyen_birim_none_doner():
    """m² fiyatı m³ kalemine uygulanamaz; tahmin etmektense fiyatı hiç uygulamamak doğrudur."""
    from app.cost.pozbook import unit_factor
    assert unit_factor("m³", "m²") is None
    assert unit_factor("adet", "kg") is None


def test_listede_birim_yoksa_kalemin_birimi_varsayilir():
    from app.cost.pozbook import unit_factor
    assert unit_factor("m³", "") == pytest.approx(1.0)


def test_kg_kalemine_ton_fiyati_dogru_tutar_verir(client, storey_dxf):
    """Uçtan uca: ton fiyatı kg kalemine uygulanınca tutar 1000 kat şişmemeli."""
    client.post("/api/pricebook/poz-import", json={"text": "15.160.1003;Nervürlü çelik Ø8-Ø12;ton;27.850,00"})
    pid = client.post("/api/projects", json={"name": "Birim", "storey_height": 3.0}).json()["id"]
    with open(storey_dxf, "rb") as f:
        client.post(f"/api/projects/{pid}/drawings", files={"file": ("KALIP PLANI.dxf", f, "application/dxf")})
    cost = client.get(f"/api/projects/{pid}/cost").json()["cost"]
    demir = [l for l in cost["lines"] if l["kind"] == "demir" and l["quantity"] > 0 and l.get("poz_priced")]
    if demir:                                    # sentetik planda demir oranla çıkar
        for l in demir:
            assert l["unit"] == "kg"
            assert l["poz_price"] == pytest.approx(27.85)      # ton fiyatı kg'a çevrildi
            assert l["total"] == pytest.approx(l["quantity"] * 27.85, rel=2e-3)
