"""Kot yazılarından kat seviyeleri ve kat yüksekliği; proje H girilmemişse kotlardan türetme."""
import pytest

from app.parser.levels import floor_levels, floor_rank, kot_from_label, parse_levels


def test_parse_levels_two_systems():
    texts = ["-4.15 (+0.00)", "+0.00 (+4.15 sıfır kotu)", "+3.80(+7.95)", "+6.50 (+10.65)", "+11.50 (+15.65)", "+13.30 (+17.45)",
             "+0.82", "+0.42", "+0.12", "+4.15", "+15.65 MEKANİK PLATFORM İZİ", "+4.00", "+1.00 KOTU", "+0.05(+4.20 peyzaj kotu)", "LOBİ 45 m2"]
    sc = parse_levels(texts)
    assert sc.offset == pytest.approx(4.15)
    assert sc.floors == [0.0, 4.15, 7.95, 10.65, 15.65]          # 0.82 / 1.00 / 4.20 / 17.45: kat aralığı altı, elenir
    assert sc.storey_heights == [4.15, 3.8, 2.7, 5.0]
    assert sc.kot is None                                          # "sıfır kotu" referans, "+1.00 KOTU" kat seviyesi değil: pafta kotu yok
    assert parse_levels(texts + ["+7.95 DÖŞEME KOTU"]).kot == pytest.approx(7.95)
    assert 8.15 not in sc.levels                                   # belirsiz sistemdeki çıplak "+4.00" sayılmaz


def test_parse_levels_single_system_and_label():
    sc = parse_levels(["±0,00", "+3,20", "+6,40", "+9,60", "+0,10", "ÇATI +12,80"], label="+3.20 KOTU KALIP PLANI")
    assert sc.floors == [0.0, 3.2, 6.4, 9.6, 12.8] and sc.storey_heights == [3.2, 3.2, 3.2, 3.2]
    assert sc.kot == pytest.approx(3.2)
    assert kot_from_label("B2 BLOK / 15.65 KOTU PLANI") == pytest.approx(15.65) and kot_from_label("ZEMİN KAT PLANI") is None
    assert floor_levels([0, 0.1, 0.5, 3.2, 3.3, 6.4]) == [0.0, 3.2, 6.4]


@pytest.mark.parametrize("label,rank", [
    ("TEMEL KALIP PLANI", -100), ("2. BODRUM KAT PLANI", -2), ("BODRUM KAT KALIP PLANI", -1), ("ZEMİN KAT PLANI", 0),
    ("ASMA KAT PLANI", 0.5), ("BİRİNCİ KAT PLANI", 1), ("3. NORMAL KAT KALIP PLANI", 3), ("ÇATI KATI PLANI", 99), ("KESİTLER", None),
])
def test_floor_rank(label, rank):
    assert floor_rank(label) == rank


def test_storey_height_from_levels_api(client, storey_dxf):
    """H = 0 girilen projede kat kalıp planlarının kotlarından kat yüksekliği türer ve H = 3,2 girilen projeyle aynı metraj çıkar."""
    def project(h):
        pid = client.post("/api/projects", json={"name": f"Kot {h}", "storey_height": h, "slab_thickness": 0.15}).json()["id"]
        for kot in ("+0.00", "+3.20"):
            with open(storey_dxf, "rb") as f:
                r = client.post(f"/api/projects/{pid}/drawings", files={"file": (f"{kot} KOTU KALIP PLANI.dxf", f, "application/dxf")},
                                data={"label": f"{kot} KOTU KALIP PLANI", "discipline": "structural"})
            assert r.status_code == 201, r.text
        return pid
    a, b = project(0), project(3.2)
    pa = client.get(f"/api/projects/{a}").json()
    assert pa["levels"]["levels"] == [0.0, 3.2] and pa["levels"]["effective"] == pytest.approx(3.2) and "kot" in pa["levels"]["source"]
    per = pa["levels"]["per_drawing"]
    assert any(v["height"] == pytest.approx(3.2) and v["source"].startswith("kot") for v in per.values())
    qa = client.get(f"/api/projects/{a}/quantities").json()["summary"]["totals"]
    qb = client.get(f"/api/projects/{b}/quantities").json()["summary"]["totals"]
    assert qa["concrete_m3"] == pytest.approx(qb["concrete_m3"], rel=1e-6) and qa["formwork_m2"] == pytest.approx(qb["formwork_m2"], rel=1e-6)


def test_explicit_height_wins_over_intermediate_level():
    from app.models import Drawing, Project
    from app.services import storey_heights
    p = Project(name="Zemin", storey_height=3.8)
    d = Drawing(id=1, project_id=1, filename="zemin.dxf", stored_path="unused", label="ZEMİN KAT PLANI", levels=[0, 3.55])
    assert storey_heights(p, [d])["per_drawing"][1]["height"] == 3.8
    d.storey_height = 4.2
    assert storey_heights(p, [d])["per_drawing"][1]["height"] == 4.2
    d.storey_height = None
    p.storey_height = 0
    assert storey_heights(p, [d])["per_drawing"][1]["height"] == 3.55


def test_degisken_katta_proje_yuksekligi_uygulanmaz_ve_bildirilir():
    """Yeni proje formunda H varsayılan 3,0 m gelirdi ve kat yüksekliği değişen binada çizimde yazan
    kotların yerine geçip kolon/perde betonunu sessizce kaydırıyordu (A4-A5'te %2,4).

    Artık kanıt sıralaması geçerli: kotlar kat kat değişiyorsa tek bir H hiçbir katta doğru olamaz,
    uygulanmaz. Kullanıcının girdiği değer silinmez; yalnız kullanılmadığı ve etkisi bildirilir."""
    from app.services import _storey_height_override

    class D:
        def __init__(self, i, kot, label):
            self.id, self.kot, self.label = i, kot, label
            self.filename, self.storey_height, self.levels, self.discipline = label, None, [], "structural"

    class P:
        storey_height = 3.0

    # kotlar: +0.00 → +4.00 → +7.95 → +10.65 (yükseklikler 4,00 / 3,95 / 2,70 — hiçbiri 3,0 değil)
    drawings = [D(1, 0.0, "zemin"), D(2, 4.0, "1. kat"), D(3, 7.95, "2. kat")]
    for d in drawings:
        d.levels = [0.0, 4.0, 7.95, 10.65]
    for d in drawings:
        d.storey_count = 1
    issues = _storey_height_override(P(), drawings)
    assert len(issues) == 1
    assert issues[0]["code"] == "storey_height_auto_applied"
    assert issues[0]["severity"] == "review"        # düzeltildi: engelleyici bir eksik kalmadı
    assert "kullanılmadı" in issues[0]["message"]
    assert "kat kat değişiyor" in issues[0]["message"]

    P.storey_height = 0.0                      # otomatik mod: bildirilecek bir şey yok
    assert _storey_height_override(P(), drawings) == []


def test_yukseklik_farkinin_beton_kalip_bedeli_yazilir():
    """Uyarı soyut kalmasın: kotlardan hesaplansa kolon + perde betonunun / kalıbının ne kadar değişeceği
    elemanlardan hesaplanıp yazılır (A4-A5'te ölçülen gerçek bedel +358 m³ / +1.497 m²)."""
    from app.services import _storey_height_override

    class D:
        def __init__(self, i, kot):
            self.id, self.kot = i, kot
            self.label = self.filename = f"kat{i}"
            self.storey_height, self.levels, self.discipline = None, [0.0, 4.0, 8.0], "structural"
            self.storey_count = 1

    class E:
        def __init__(self, did, etype, area, perimeter):
            self.drawing_id, self.etype, self.area, self.perimeter = did, etype, area, perimeter
            self.length, self.included = 0.0, True

    class P:
        storey_height = 3.0

    drawings = [D(1, 0.0), D(2, 4.0)]
    # her paftada 10 m² kolon kesiti, 40 m çevre; kotlardan yükseklik 4,00 m -> paftada +1,00 m fark
    elements = [E(1, "column", 10.0, 40.0), E(2, "column", 10.0, 40.0)]
    issues = _storey_height_override(P(), drawings, elements)
    assert len(issues) == 1
    # beton 2 × 10 m² × 1,00 m = +20 m³, kalıp 2 × 40 m × 1,00 m = +80 m²
    assert "+20 m³" in issues[0]["message"]
    assert "+80 m²" in issues[0]["message"]

    # eleman verilmezse hesap yapılmaz ama uyarı yine çıkar (bedel cümlesi olmadan)
    plain = _storey_height_override(P(), drawings)
    assert plain and "m³" not in plain[0]["message"].split("değişirdi")[0]


def test_kotlar_proje_yuksekligiyle_ayniysa_uyari_yok():
    """Kat yüksekliği gerçekten sabitse proje H'si kotlarla uyuşur; gereksiz uyarı çıkmaz."""
    from app.services import _storey_height_override

    class D:
        def __init__(self, i, kot):
            self.id, self.kot = i, kot
            self.label = self.filename = f"kat{i}"
            self.storey_height, self.levels, self.discipline = None, [0.0, 3.0, 6.0, 9.0], "structural"

    class P:
        storey_height = 3.0

    assert _storey_height_override(P(), [D(1, 0.0), D(2, 3.0)]) == []


# ---- Kanıt sıralaması: tek bir H, değişken katlı binada uygulanamaz ----

def _proje(H):
    from types import SimpleNamespace
    return SimpleNamespace(storey_height=H)


def _pafta(i, kot, levels, elle=None, label=None):
    from types import SimpleNamespace
    return SimpleNamespace(id=i, kot=kot, levels=levels, storey_height=elle, storey_count=1,
                           label=label or f"kat{i}", filename=f"kat{i}.dxf", discipline="structural")


DEGISKEN = [0.0, 2.5, 6.45, 9.15, 14.15]        # yükseklikler 2,50 / 3,95 / 2,70 / 5,00 — A4-A5 deseni
SABIT = [0.0, 3.0, 6.0, 9.0]                    # hepsi 3,00


def test_degisken_kotlarda_proje_yuksekligi_uygulanmaz():
    """Tek bir H hiçbir katta doğru olamaz; çizimin kendi kotları esas alınır."""
    from app.services import storey_heights
    ds = [_pafta(1, 0.0, DEGISKEN), _pafta(2, 2.5, DEGISKEN), _pafta(3, 6.45, DEGISKEN)]
    sh = storey_heights(_proje(3.0), ds)
    assert sh["per_drawing"][1]["height"] == 2.5      # projeye girilen 3,0 değil, kotun kendisi
    assert sh["per_drawing"][2]["height"] == 3.95
    assert sh["source"] != "parametre"
    assert "çelişiyor" in sh["source"]


def test_sabit_kotlarda_kullanicinin_yuksekligi_korunur():
    """Bina gerçekten sabit katlıysa kullanıcının kararı ezilmez — düzeltme yalnız çelişki varken devreye girer."""
    from app.services import storey_heights
    ds = [_pafta(1, 0.0, SABIT), _pafta(2, 3.0, SABIT), _pafta(3, 6.0, SABIT)]
    sh = storey_heights(_proje(2.8), ds)
    assert sh["per_drawing"][1]["height"] == 2.8
    assert sh["source"] == "parametre"


def test_paftaya_elle_girilen_yukseklik_her_zaman_kazanir():
    """Kullanıcının pafta bazındaki açık kararı otomatik düzeltmeden de üstündür."""
    from app.services import storey_heights
    ds = [_pafta(1, 0.0, DEGISKEN, elle=4.2), _pafta(2, 2.5, DEGISKEN)]
    sh = storey_heights(_proje(3.0), ds)
    assert sh["per_drawing"][1]["height"] == 4.2
    assert sh["per_drawing"][1]["source"] == "çizime girildi"


def test_uygulanmayan_H_bilgi_notu_olarak_bildirilir():
    """Düzeltme sessiz olmamalı: ne yapıldığı ve H uygulansaydı ne olacağı yazılır."""
    from app.services import _storey_height_override
    ds = [_pafta(1, 0.0, DEGISKEN), _pafta(2, 2.5, DEGISKEN), _pafta(3, 6.45, DEGISKEN)]
    issues = _storey_height_override(_proje(3.0), ds)
    assert len(issues) == 1
    i = issues[0]
    assert i["code"] == "storey_height_auto_applied"
    assert i["severity"] == "review"          # düzeltildi; engelleyici bir eksik yok
    assert "kullanılmadı" in i["message"] and "kat kat değişiyor" in i["message"]
    assert "fix" not in i                      # düzeltilecek bir şey kalmadı


def test_sabit_katta_fark_varsa_hala_uyarilir_ve_duzeltme_sunulur():
    """H uygulandıysa ve kotla uyuşmuyorsa karar kullanıcınındır: fark bildirilir, düğme sunulur."""
    from app.services import _storey_height_override
    ds = [_pafta(1, 0.0, SABIT), _pafta(2, 3.0, SABIT), _pafta(3, 6.0, SABIT)]
    issues = _storey_height_override(_proje(2.8), ds)
    assert len(issues) == 1 and issues[0]["code"] == "storey_height_override"
    assert issues[0]["fix"]["action"] == "storey_height_auto"


def test_temel_kotu_kat_kotu_sayilmaz():
    """C1 ruhsatı: bodrum planındaki "-3.10 Temel Alt Kot" bodrumun kat kotu sanılıyordu. Temel paftasında ise
    temel kotu paftanın kendi kotudur (kazı derinliği ona dayanır)."""
    from app.parser.levels import parse_levels
    s = parse_levels(["-3.33(+0.82)", "-3.10 Temel Alt Kot", "-1.70 Temel Üst Kot"], "C1 BLOK / BODRUM KAT PLANI")
    assert s.levels == [0.82] and s.kot is None
    s = parse_levels(["-2.55 TEMEL ÜST KOTU"], "TEMEL KALIP PLANI")
    assert s.kot == -2.55


def test_vaziyet_kotlari_kat_dizisine_girmez():
    from types import SimpleNamespace as NS
    from app.parser.levels import building_levels, floor_levels
    paftalar = [NS(plan_type="mim_kat_plani", levels=[0.82], kot=None), NS(plan_type="mim_kat_plani", levels=[4.15], kot=None),
                NS(plan_type="mim_kesit", levels=[0.82, 4.15, 7.95, 11.65], kot=None),
                NS(plan_type="mim_vaziyet", levels=[0.0, 2.5], kot=0.82)]
    assert floor_levels(building_levels(paftalar)) == [0.82, 4.15, 7.95, 11.65]


def test_kat_sirasi_mutlak_sistemde_sifir_kotuna_oturur():
    """C1: ±0,00 = +4,15 (mutlak). Zemin kat 0,00'a en yakın seviyeye (bodrumun +0,82'si) oturuyordu."""
    from types import SimpleNamespace as NS
    from app.parser.levels import building_datum, level_for_rank
    katlar = [0.82, 4.15, 7.95, 11.65, 14.55]
    datum = building_datum([NS(level_offset=4.15, plan_type="mim_kat_plani"), NS(level_offset=None, plan_type="mim_kesit"),
                            NS(level_offset=0.0, plan_type="mim_vaziyet")])
    assert datum == 4.15
    assert level_for_rank(katlar, 0, datum) == 4.15        # zemin
    assert level_for_rank(katlar, -1, datum) == 0.82       # bodrum
    assert level_for_rank(katlar, 1, datum) == 7.95        # birinci
    assert level_for_rank([-3.0, 0.0, 3.0], 0) == 0.0      # tek sistemli projede eski davranış
