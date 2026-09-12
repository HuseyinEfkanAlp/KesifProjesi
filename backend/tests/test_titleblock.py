"""Ruhsat antedi: pafta sayılmaz, ama içindeki proje verisi okunur."""
import pytest

from app.parser.sheets import Sheet, classify_sheets
from app.parser.titleblock import interpret, label_points, read_texts

# (x, y, yazı yüksekliği, katman, metin) — gerçek A4-A5 antedindeki yerleşim:
# değer ya etiketin sağında aynı satırda ("MALZEME  C35-S420") ya da hemen altında ("TEMEL TİPİ" / "RADYE").
ANTET = [
    (-30841, -99876, 30, "Başlık_Yazı", "MALZEME"),
    (-30415, -99871, 30, "Başlık_Yazı", "C35-S420"),
    (-31330, -102406, 30, "Başlık_Yazı", "TEMEL TİPİ"),
    (-31307, -102483, 30, "Başlık_Yazı", "RADYE"),
    (-31514, -102406, 30, "Başlık_Yazı", "PERDE"),
    (-31495, -102483, 30, "Başlık_Yazı", "VAR"),
    (-30519, -102406, 30, "Başlık_Yazı", "İNŞAAT SURESİ"),
    (-30903, -102243, 30, "Başlık_Yazı", "DÖŞEME CİNSİ"),
    (-30843, -102321, 30, "Başlık_Yazı", "plak"),
    (-30689, -102243, 30, "Başlık_Yazı", "KAT ADEDİ"),
    (-31372, -101123, 30, "Başlık_Yazı", "MAHALLESI"),
    (-31034, -101125, 30, "Başlık_Yazı", "FATİH"),
]


def test_antet_okunur():
    tb = read_texts(ANTET)
    assert tb.fields["malzeme"] == "C35-S420"
    assert tb.fields["temel_tipi"] == "RADYE"
    assert tb.fields["perde"] == "VAR"
    assert tb.fields["doseme_cinsi"] == "plak"
    assert tb.fields["mahalle"] == "FATİH"
    assert tb.concrete_class == "C35/45" and tb.rebar_grade == "B420C" and tb.foundation_kind == "radye"
    assert tb.summary() == "beton C35/45, donatı B420C, temel radye"


def test_komsu_baslik_deger_sanilmaz():
    """"TEMEL TİPİ"nin sağındaki "İNŞAAT SÜRESİ" bir başka kutu başlığıdır, değeri değil; değer alttaki
    "RADYE". Aynı şekilde "KAT ADEDİ" doldurulmamıştır: soluna düşen "plak" onun değeri değildir."""
    tb = read_texts(ANTET)
    assert tb.fields["temel_tipi"] == "RADYE"
    assert "kat_adedi" not in tb.fields


def test_bos_antet_bos_doner():
    assert read_texts([]).empty
    assert read_texts(ANTET[:2]).empty        # 4 yazıdan az: antet sayılmaz


@pytest.mark.parametrize("malzeme,beton,celik", [
    ("C35-S420", "C35/45", "B420C"),
    ("C30/37 B420C", "C30/37", "B420C"),
    ("BETON C25 ÇELİK S220", "C25/30", "B220B"),
    ("", "", ""),
])
def test_malzeme_satiri_yorumlanir(malzeme, beton, celik):
    tb = interpret({"malzeme": malzeme})
    assert tb.concrete_class == beton and tb.rebar_grade == celik


def _sheet(idx, title, geo, bbox=(0, 0, 100, 100)):
    return Sheet(idx, title, bbox, geo, 1, True, "frame", [], {"VM Kolon": geo})


def test_bos_cerceve_plan_sayilmaz():
    """Başlığı olan ama çizimi olmayan kutu ("VAZİYET PLANI" yazan 11 nesnelik şablon) plan değildir."""
    sheets = [_sheet(0, "VAZİYET PLANI", 10), _sheet(1, "TEMEL KALIP PLANI", 678),
              _sheet(2, "TEMEL X YÖNÜ DONATI PLANI", 1868), _sheet(3, "İLAVE DONATI PLANI", 1771)]
    classify_sheets(sheets)
    assert [s.kind for s in sheets] == ["bos", "plan", "plan", "plan"]


def test_esit_buyuklukteki_kucuk_paftalar_bos_sayilmaz():
    """Eşik göreli: küçük bir projede bütün paftalar az nesne taşır, hiçbiri boş değildir."""
    sheets = [_sheet(i, f"PAFTA {i}", 8) for i in range(3)]
    classify_sheets(sheets)
    assert all(s.kind == "plan" for s in sheets)


def test_antet_kutusu_etiketlerinden_taninir():
    """Antet kanıtı katman adı değil, kutunun içindeki tanınmış etiketlerdir: pafta çerçevesi de çoğu
    projede "ANTET" katmanında çizilir."""
    sheets = [Sheet(0, "PROJE BİLGİLERİ", (-32000, -103000, -30000, -98000), 120, 1, True, "frame", [],
                    {"Başlık": 113, "VM_Antet": 9}),
              _sheet(1, "TEMEL KALIP PLANI", 678, (0, 0, 1000, 1000))]
    classify_sheets(sheets, label_points(ANTET))
    assert sheets[0].kind == "antet" and sheets[1].kind == "plan"


def test_cerceve_katmani_antet_adini_tasisa_da_plan_kalir():
    """Çerçevesi "ANTET" katmanında çizilmiş normal pafta plan olarak kalmalı (etiket yoksa antet yok)."""
    sheets = [Sheet(i, t, (i * 2000, 0, i * 2000 + 1800, 1200), 5, 1, True, "frame", [], {"ANTET": 2, "KOLON": 3})
              for i, t in enumerate(("TEMEL KALIP PLANI", "ZEMİN KAT KALIP PLANI", "KOLON DETAYLARI"))]
    classify_sheets(sheets, [])
    assert all(s.kind == "plan" for s in sheets)


def test_cetvel_bos_cerceve_gibi_elenmez():
    """Poz / ürün cetvelinin geometrisi yoktur, boş çerçeve gibi görünür. Elenirse yazılarındaki adet de
    kaybolur: B2 blokta doğrama cetveli tek başına 14 poz / 170 adet taşıyor."""
    sheets = [_sheet(0, "B2 BLOK DOĞRAMALAR", 12, (0, 0, 100, 100)),
              _sheet(1, "VAZİYET PLANI", 10, (200, 0, 300, 100)),
              _sheet(2, "ZEMİN KAT PLANI", 600, (400, 0, 900, 500)),
              _sheet(3, "BİRİNCİ KAT PLANI", 800, (1000, 0, 1500, 500))]
    # cetvel kutusunun içine düşen tanınmış satırlar ("Poz: EMP1 82" gibi)
    cetvel_pts = [(10, 10), (10, 20), (10, 30), (10, 40)]
    classify_sheets(sheets, [], cetvel_pts)
    assert [s.kind for s in sheets] == ["cetvel", "bos", "plan", "plan"]


def test_cetvel_plan_listesinde_secili_kalir():
    """Cetvel "plan değil" diye işaretsiz gelmemeli: verisi okunacağı için eklenir."""
    from app.api.drawings import _sheet_out
    sh = _sheet(0, "B2 BLOK DOĞRAMALAR", 12)
    sh.kind = "cetvel"
    out = _sheet_out(sh)
    assert out["plan_type"] == "mim_dograma" and out["analyze"] and not out["fragment"]
    assert "poz ve adet" in out["kind_note"]

    bos = _sheet(1, "VAZİYET PLANI", 10)
    bos.kind = "bos"
    assert _sheet_out(bos)["plan_type"] == "" and not _sheet_out(bos)["analyze"]


def test_poz_satiri_cetvel_kaniti_sayilir():
    """Tarama sırasında cetvel kanıtı toplayan desenler: poz satırı ve lejant başlıkları."""
    from app.parser.schedules import parse_schedule_text
    from app.parser.sheets import CETVEL_RE
    assert parse_schedule_text("Poz: EMP1 82") is not None
    assert parse_schedule_text("Poz: EMP3 9 Adet AÇILIR KAPI") is not None
    for t in ("LEJANT", "GÖSTERİM", "DOĞRAMA LİSTESİ", "MAHAL LİSTESİ", "Çiroz Donatı Tablosu", "SEMBOL"):
        assert CETVEL_RE.search(t), t
    for t in ("TEMEL KALIP PLANI", "KİRİŞ DETAYLARI", "ZEMİN KAT PLANI"):
        assert not CETVEL_RE.search(t), t
