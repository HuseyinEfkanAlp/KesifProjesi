"""Kalibrasyon döngüsü: korpus okuma, fark hesabı, teşhis ve gerileme kapısı.

Gerçek DXF okumaz (o `python -m app.calib` işidir); burada test edilen, farkın **sebebe doğru
bağlanması**: aynı yüzde sapma, hangi ölçüde çıktığına göre farklı suçluyu göstermelidir.
"""
import json
from types import SimpleNamespace as Obj

import pytest

from app.calib.corpus import MEASURES, load_corpus
from app.calib.diagnose import ESIK, diagnose
from app.calib.runner import Delta


def kat(beton=(1000.0, 1000.0), kalip=(4000.0, 4000.0), H=3.30, d=0.15, kiris=0.50,
        net=True, elemanlar=None, paftalar=None, ekstra=()):
    farklar = [Delta("kolon_perde_beton_m3", *beton), Delta("kolon_perde_kalip_m2", *kalip), *ekstra]
    return Obj(kat="zemin", kat_yuksekligi=H, doseme_kalinligi=d, kiris_yuksekligi=kiris, net_doseme=net,
               elemanlar=elemanlar or {"column": 100, "shear_wall": 20}, farklar=farklar,
               paftalar=paftalar or [Obj(dosya="a.dxf", birim="cm", birim_dogrulandi=True, elemanlar={"column": 100},
                                         uyarilar=[], hata="")])


def test_delta_yuzde_ve_isaret():
    d = Delta("kolon_perde_beton_m3", bizim=1500.0, referans=1443.68)
    assert round(d.fark, 2) == 56.32
    assert 3.8 < d.yuzde < 4.0


def test_beton_sapiyor_kalip_tutuyorsa_suclu_beton_yuksekligi():
    """Kalıp ve beton farklı yükseklik kullanır; yalnız biri sapıyorsa suçlu o yüksekliktir."""
    # Hk = H = 3.30 (net döşeme). Referans H − d = 3.15 ile hesaplanmışsa bizim %4.8 fazla çıkarız.
    t = diagnose(kat(beton=(1000.0, 1000.0 * 3.15 / 3.30), kalip=(4000.0, 4000.0)))
    metin = " ".join(t)
    assert "beton yüksekliği" in metin
    assert "brüt döşeme kabulü" in metin      # geri hesap tam olarak H − d'ye denk düşmeli
    assert "kabulden" in metin                # geometri değil kabul farkı


def test_kalip_sapiyor_beton_tutuyorsa_suclu_kalip_yuksekligi():
    # Hf = H − kiriş = 2.80. Referans H − d = 3.15 ile hesaplanmışsa bizim %11 eksik çıkarız.
    t = diagnose(kat(beton=(1000.0, 1000.0), kalip=(4000.0, 4000.0 * 3.15 / 2.80)))
    metin = " ".join(t)
    assert "kalıp yüksekliği" in metin
    assert "brüt döşeme kabulü" in metin


def test_ikisi_de_ayni_oranda_sapiyorsa_ortak_carpan():
    t = diagnose(kat(beton=(1100.0, 1000.0), kalip=(4400.0, 4000.0)))
    assert "ortak çarpan" in " ".join(t)


def test_ters_yonde_sapma_formul_suphesi():
    t = diagnose(kat(beton=(1100.0, 1000.0), kalip=(3600.0, 4000.0)))
    assert "ters yönde" in " ".join(t)


def test_hicbir_adaya_denk_gelmeyen_fark_eleman_tespitine_isaret_eder():
    """Geri hesaplanan yükseklik H, H−d, H−kiriş'in hiçbirine denk değilse suçlu yükseklik değildir."""
    t = diagnose(kat(beton=(1000.0, 700.0), kalip=(4000.0, 4000.0)))
    assert "eleman tespiti" in " ".join(t)


def test_esik_altinda_sapma_eslesmis_sayilir():
    t = diagnose(kat(beton=(1000.0, 1000.0 * (1 - (ESIK - 0.5) / 100)), kalip=(4000.0, 4000.0)))
    assert "bandında eşleşti" in " ".join(t)
    assert "bağımsız doğruluk kanıtı değildir" in " ".join(t)


def test_okunamayan_pafta_teshiste_gorunur():
    bozuk = [Obj(dosya="x.dxf", birim="", birim_dogrulandi=False, elemanlar={}, uyarilar=[], hata="DXFStructureError: bozuk")]
    t = diagnose(kat(paftalar=bozuk))
    assert "Pafta okunamadı" in " ".join(t)


def test_bos_pafta_teshiste_gorunur():
    bos = [Obj(dosya="x.dxf", birim="cm", birim_dogrulandi=True, elemanlar={}, uyarilar=[], hata="")]
    assert "hiç eleman vermedi" in " ".join(diagnose(kat(paftalar=bos)))


def test_kiris_doseme_referansi_da_karsilastirilir():
    t = diagnose(kat(ekstra=[Delta("kiris_beton_m3", 1200.0, 1000.0)],
                     elemanlar={"column": 100, "shear_wall": 20, "beam": 400}))
    assert "Kiriş betonu" in " ".join(t)


def test_korpus_okunur_ve_yollar_cozulur(tmp_path):
    p = tmp_path / "deneme.json"
    p.write_text(json.dumps({
        "proje": "Deneme", "kaynak": "test", "guven": "bagimsiz",
        "varsayilan": {"doseme_kalinligi": 0.12},
        "katlar": [{"ad": "zemin", "kat_yuksekligi": 3.0, "paftalar": ["samples/a.dxf"],
                    "referans": {"beton_m3": 100.0}}],
    }, ensure_ascii=False), encoding="utf-8")
    c = load_corpus(p, repo_root=tmp_path)
    assert c.katlar[0].doseme_kalinligi == 0.12                 # varsayılan kata iner
    assert c.katlar[0].paftalar[0].endswith("samples/a.dxf")
    assert str(tmp_path) in c.katlar[0].paftalar[0]             # yol depo köküne göre çözülür
    assert "Bağımsız" in c.guven_aciklama


def test_taninmayan_referans_olcusu_hata_verir(tmp_path):
    p = tmp_path / "kotu.json"
    p.write_text(json.dumps({"proje": "X", "katlar": [{"ad": "z", "referans": {"uydurma_olcu": 1}}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="uydurma_olcu"):
        load_corpus(p, repo_root=tmp_path)


def test_her_olcu_bilinen_eleman_tipleri_kullanir():
    """MEASURES'daki eleman tipleri metraj motorunun tanıdığı tipler olmalı; yazım hatası sessizce 0 verir."""
    from app.parser.layer_profile import STRUCTURAL_TYPES
    for olcu, (etypes, buyukluk) in MEASURES.items():
        assert buyukluk in ("concrete", "formwork"), olcu
        for e in etypes:
            assert e in STRUCTURAL_TYPES, f"{olcu}: {e} bilinen bir eleman tipi değil"
