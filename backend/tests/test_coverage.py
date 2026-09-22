"""Kapsam raporu: hangi imalat neden hesaplanamadı (app/planset.coverage).

`plan_check` hangi planın eksik olduğunu zaten biliyor ama çıktısı pafta cümlesidir
("Statik: Kat kalıp planları yüklenmedi"). Kullanıcı teknik değil; ona pafta adı değil
**eksik kalan iş** söylenmeli.
"""
from app.planset import PRODUCES, coverage, plan_check
from app.quantity.boq import BoqItem


def _dwg(i, label, plan_type, discipline="architectural", hints=None, warnings=None):
    return {"id": i, "label": label, "plan_type": plan_type, "discipline": discipline,
            "block": "", "discipline_hints": hints or {}, "warnings": warnings or []}


def _item(kind, qty=1.0):
    return BoqItem(key=f"{kind}:*", kind=kind, group="*", label=kind, unit="m²", quantity=qty,
                   discipline="architectural")


def test_eksik_plan_imalat_diliyle_anlatilir():
    check = plan_check([_dwg(1, "Mimari kat planı", "mim_kat_plani")], None)
    cov = coverage(check, [_item("duvar")], [])
    kalip = [r for r in cov["rows"] if r.get("plan_type") == "sta_kat_kalip"]
    assert kalip, "kat kalıp planı eksik olmalı"
    m = kalip[0]["message"]
    assert m.startswith("Beton")                    # pafta adıyla değil imalatla başlar
    assert "Kat kalıp planları" in m                # sebebi de yazar
    assert "beton" in kalip[0]["missing_kinds"]


def test_zaten_olculen_imalat_eksik_sayilmaz():
    """Kalem keşifte varsa planı eksik olsa da 'hesaplanamadı' denmez — ölçüm başka paftadan gelmiş olabilir."""
    check = plan_check([_dwg(1, "Mimari kat planı", "mim_kat_plani")], None)
    cov = coverage(check, [_item("beton"), _item("kalip"), _item("demir")], [])
    kalip = [r for r in cov["rows"] if r.get("plan_type") == "sta_kat_kalip"]
    assert kalip
    for k in ("beton", "kalip", "demir"):
        assert k not in kalip[0]["missing_kinds"]
    # geriye yalnız gerçekten ölçülmemişler kalır (iskele, plywood, pompaj)
    assert kalip[0]["missing_kinds"] and not kalip[0]["message"].startswith("Beton,")


def test_sifir_miktarli_kalem_olculmus_sayilmaz():
    check = plan_check([_dwg(1, "Mimari kat planı", "mim_kat_plani")], None)
    cov = coverage(check, [_item("beton", qty=0.0)], [])
    kalip = next(r for r in cov["rows"] if r.get("plan_type") == "sta_kat_kalip")
    assert "beton" in kalip["missing_kinds"]


def test_paftadaki_okunmamis_disiplin_kaniti_bildirilir():
    """"Mimari paftada mekanik katmanları var ama mekanik planı yüklenmedi" — bugüne kadar hiç gösterilmiyordu."""
    d = _dwg(1, "Zemin kat planı", "mim_kat_plani", hints={"mechanical": 5328})
    cov = coverage(plan_check([d], None), [], [d])
    kanit = [r for r in cov["rows"] if r["kind"] == "hint"]
    assert len(kanit) == 1
    assert "mekanik" in kanit[0]["message"] and "5.328" in kanit[0]["message"]
    assert kanit[0]["drawing_id"] == 1


def test_baskin_eslenmemis_katman_uyarisi_kapsama_girer():
    d = _dwg(1, "1. kat planı", "mim_kat_plani",
             warnings=["“FB_Prekast” katmanı nesnelerin %94'ünü tutuyor ama hiçbir kalem üretmedi"])
    cov = coverage(plan_check([d], None), [], [d])
    assert any(r["kind"] == "layer" and "FB_Prekast" in r["message"] for r in cov["rows"])


def test_zorunlu_eksikler_once_gelir():
    cov = coverage(plan_check([_dwg(1, "Mimari kat planı", "mim_kat_plani")], None), [], [])
    seviyeler = [r.get("level") for r in cov["rows"] if r["kind"] == "plan"]
    assert seviyeler, "plan satırı olmalı"
    assert seviyeler.index("required") < (seviyeler.index("optional") if "optional" in seviyeler else 99)


def test_ozet_cumlesi_sayilari_verir():
    d = _dwg(1, "Mimari kat planı", "mim_kat_plani", hints={"electrical": 42})
    cov = coverage(plan_check([d], None), [], [d])
    assert cov["required"] > 0 and cov["evidence"] == 1
    assert "imalat grubu hesaplanamadı" in cov["sentence"]
    assert "okunmamış katman kanıtı" in cov["sentence"]


def test_bos_projede_kapsam_cumlesi_bos_kalmaz_ama_uydurmaz():
    """Hiç çizim yoksa her plan eksiktir; yine de yalnız 'bu yok ve sebebi şu' denir."""
    cov = coverage(plan_check([], None), [], [])
    assert cov["count"] > 0
    assert all("hesaplanamadı" in r["message"] for r in cov["rows"] if r["kind"] == "plan")


def test_produces_tablosu_gercek_plan_tiplerini_kullanir():
    """Yanlış yazılmış bir kod sessizce hiçbir şey üretmez — tablo plan tipleriyle tutmalı."""
    from app.planset import PLAN_TYPE_BY_CODE
    bilinmeyen = sorted(set(PRODUCES) - set(PLAN_TYPE_BY_CODE))
    assert not bilinmeyen, f"PRODUCES'ta olmayan plan tipi: {bilinmeyen}"
