"""Kapsam sahipliği: bir kez okunan miktar ikinci paftadan tekrar okunmaz (app/quantity/scope.py)."""
from __future__ import annotations

import pytest

from app.quantity.scope import ScopeDrawing, ScopeElement, authority, resolve


def _tray(eid: int, x0: float, x1: float, y: float = 0.0, spec: str = "200x60", manual: bool = False) -> ScopeElement:
    return ScopeElement(id=eid, etype="tray", subtype=spec, points=[(x0, y), (x1, y)], length=abs(x1 - x0), manual=manual)


def _col(eid: int, x: float, y: float) -> ScopeElement:
    pts = [(x, y), (x + 0.4, y), (x + 0.4, y + 0.4), (x, y + 0.4)]
    return ScopeElement(id=eid, etype="column", points=pts, area=0.16)


def _dwg(did: int, label: str, plan_type: str, discipline: str, els: list[ScopeElement], kot: str | None = "+3.00",
         block: str = "") -> ScopeDrawing:
    """kot: paftanın kat kimliği (None = katı bilinmeyen pafta)."""
    return ScopeDrawing(id=did, label=label, elements=els, block=block, floor=f"kot:{kot}" if kot else None,
                        floor_label=kot or "", plan_type=plan_type, discipline=discipline)


# ---------------------------------------------------------------- yetki

def test_authority_order():
    """Tavanın sahibi tava planıdır; zayıf akım aynı tavayı çizse de altlıktır, mimari pafta hiç yetkili değildir."""
    assert authority("elk_tava", "electrical", "tray") == 0
    assert authority("elk_zayif", "electrical", "tray") == 1
    assert authority("mim_kat_plani", "architectural", "tray") == 3
    assert authority("mim_kat_plani", "architectural", "wall") == 0
    assert authority("sta_kat_kalip", "structural", "column") == 0


# ---------------------------------------------------------------- aynı nesne bir kez sayılır

def test_zayif_akim_tavayi_ikinci_kez_saymaz():
    """Kullanıcının örneği: tava planından tava metrajı çıktı; zayıf akım paftasındaki aynı tava sayılmaz."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10, 0, 20), _tray(11, 0, 20, y=5)])
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(20, 0, 20), _tray(21, 0, 20, y=5)])
    res = resolve([tava, zayif])
    assert res.dropped == {20, 21}
    note = next(n for n in res.notes if n.kind == "duplicate")
    assert note.owner == "Kablo tava planı" and note.drawing == "Zayıf akım planı"
    assert note.dropped_count == 2 and note.dropped_qty == pytest.approx(40.0) and note.unit == "m"
    assert note.method == "geometri"


def test_zayif_akimdaki_ek_tava_kolu_eklenir():
    """"Sadece eklemeler varsa onları belirtip ekleyelim": yalnız zayıf akımda olan kol metraja girer."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10, 0, 20)])
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(20, 0, 20), _tray(21, 0, 12, y=9)])
    res = resolve([tava, zayif])
    assert res.dropped == {20}                     # aynı kol düştü
    add = next(n for n in res.notes if n.kind == "addition")
    assert add.added_count == 1 and add.added_qty == pytest.approx(12.0)
    assert "ek olarak sayıldı" in add.message


def test_farkli_kesit_ayri_nesnedir():
    """Aynı güzergâhta 200x60 ile 100x50 tava iki ayrı kalemdir; biri diğerinin kopyası sayılmaz."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10, 0, 20, spec="200x60")])
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(20, 0, 20, spec="100x50")])
    assert resolve([tava, zayif]).dropped == set()


def test_mimari_altliktaki_kolon_ikinci_kez_sayilmaz():
    """Mimari kat planının altlığındaki kolonlar statik kalıp planında zaten ölçüldü."""
    kalip = _dwg(1, "Kat kalıp planı", "sta_kat_kalip", "structural", [_col(10, 0, 0), _col(11, 5, 0)])
    mim = _dwg(2, "Mimari kat planı", "mim_kat_plani", "architectural", [_col(20, 0, 0), _col(21, 5, 0)])
    res = resolve([kalip, mim])
    assert res.dropped == {20, 21}


# ---------------------------------------------------------------- ayrı nesne her zaman sayılır

def test_bir_katin_iki_yarisi_toplanir():
    """B Blok bodrumu iki yarıya kırpılmıştır: eşit yetkili, ayrık geometri — ikisi de sayılır (calib korpusu)."""
    sol = _dwg(1, "Bodrum sol", "sta_kat_kalip", "structural", [_col(10, 0, 0), _col(11, 5, 0)])
    sag = _dwg(2, "Bodrum sağ", "sta_kat_kalip", "structural", [_col(20, 100, 0), _col(21, 105, 0)])
    res = resolve([sol, sag])
    assert res.dropped == set() and not [n for n in res.notes if n.kind == "duplicate"]


def test_ayri_kotlar_birbirini_elemez():
    """Aynı yere çizilmiş iki kat aynı nesne değildir: kapsam kot bazındadır."""
    kat1 = _dwg(1, "1. kat kalıp", "sta_kat_kalip", "structural", [_col(10, 0, 0)], kot="+3.00")
    kat2 = _dwg(2, "2. kat kalıp", "sta_kat_kalip", "structural", [_col(20, 0, 0)], kot="+6.00")
    assert resolve([kat1, kat2]).dropped == set()


def test_esit_yetki_kot_bilinmiyorsa_elenmez():
    """Kot yoksa hangi kat olduğu ayırt edilemez; eşit yetkili iki pafta birbirini elemez."""
    a = _dwg(1, "Aydınlatma 1", "elk_aydinlatma", "electrical", [_tray(10, 0, 20)], kot=None)
    b = _dwg(2, "Aydınlatma 2", "elk_aydinlatma", "electrical", [_tray(20, 0, 20)], kot=None)
    assert resolve([a, b]).dropped == set()


def test_farkli_blok_elenmez():
    """A bloğun tavası B bloğun tavasının kopyası değildir."""
    a = _dwg(1, "A blok tava", "elk_tava", "electrical", [_tray(10, 0, 20)], block="A")
    b = _dwg(2, "B blok zayıf akım", "elk_zayif", "electrical", [_tray(20, 0, 20)], block="B")
    assert resolve([a, b]).dropped == set()


def test_elle_eklenen_eleman_hicbir_zaman_elenmez():
    """Kullanıcının kendi eklediği eleman program kararıyla düşmez."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10, 0, 20)])
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(20, 0, 20, manual=True)])
    assert resolve([tava, zayif]).dropped == set()


# ---------------------------------------------------------------- koordinat kanıtı yoksa

def test_ayri_orijindeki_pafta_kati_biliniyorsa_otelenip_eslestirilir():
    """Aynı katın ayrı orijinde çizilmiş ikinci paftası: öteleme bulunur, kopya düşer, gerçek ek eklenir.
    Öteleme bir çıkarımdır — az sayıda nesneyle kabul edilmez ve düşüm "kontrol edilmeli" işaretlenir."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10 + i, 0, 20, y=i * 3.0) for i in range(6)])
    uzak = [_tray(20 + i, 9000, 9020, y=i * 3.0) for i in range(6)] + [_tray(30, 9000, 9012, y=20)]
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", uzak)
    res = resolve([tava, zayif])
    assert res.dropped == {20, 21, 22, 23, 24, 25}          # ötelenince üst üste düşen altı kol
    dup = next(n for n in res.notes if n.kind == "duplicate")
    assert "ötelenip eşleştirildi" in dup.message and dup.severity == "review"
    add = next(n for n in res.notes if n.kind == "addition")
    assert add.added_count == 1 and add.added_qty == pytest.approx(12.0)


def test_zayif_hizalama_kabul_edilmez():
    """Üç nesneden azıyla ya da yarısından azı tutan bir ötelemeyle hiçbir şey düşürülmez: zayıf hizalama
    ayrı bir yapı bloğunun gerçek ölçümünü kopya sanıp sildirebilir."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10, 0, 20), _tray(11, 0, 20, y=5)])
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(20, 9000, 9020), _tray(21, 9000, 9020, y=5)])
    res = resolve([tava, zayif])
    assert res.dropped == set()
    assert next(n for n in res.notes if n.kind == "unmatched").severity == "review"


def test_kat_bilinmiyorsa_ortusmeyen_pafta_hicbir_seyi_dusurmez():
    """Kat bilinmiyorsa "aynı katın ikinci çizimi" ile "aynı dosyada yan yana duran ayrı bölge" ayırt edilemez.
    Sessizce kaybolan miktar çift sayımdan zararlıdır: hiçbir şey düşmez, kullanıcıya ne yapacağı söylenir."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10, 0, 20)], kot=None)
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(20, 9000, 9020)], kot=None)
    res = resolve([tava, zayif])
    assert res.dropped == set()
    note = next(n for n in res.notes if n.kind == "unmatched")
    assert note.severity == "review" and "kat adını netleştirin" in note.message


def test_ayni_dosyada_yan_yana_paftalar_birbirini_elemez():
    """Bir DXF'te yan yana duran temel ve kat kalıp paftası aynı koordinat sistemindedir ama ayrı bölgelerdir:
    yetkileri farklı olsa bile (temel paftası kolonun sahibi değildir) hiçbir kolon düşmez."""
    temel = _dwg(1, "Temel kalıp", "sta_temel_kalip", "structural", [_col(10, 0, 0), _col(11, 5, 0)], kot=None)
    zemin = _dwg(2, "Zemin kalıp", "sta_kat_kalip", "structural", [_col(20, 500, 0), _col(21, 505, 0), _col(22, 510, 0)], kot=None)
    assert resolve([temel, zemin]).dropped == set()


def test_ayri_koordinat_esit_yetki_ikisi_de_sayilir():
    """Aynı katın iki dosyaya bölünmüş yarısı ayrı orijinde olabilir: eşit yetkide hiçbir şey düşmez."""
    a = _dwg(1, "Tava sol", "elk_tava", "electrical", [_tray(10, 0, 20)])
    b = _dwg(2, "Tava sağ", "elk_tava", "electrical", [_tray(20, 9000, 9020)])
    assert resolve([a, b]).dropped == set()


# ---------------------------------------------------------------- sahipsiz kalem

def test_yetkili_pafta_yuklenmemisse_devralinir_ama_bildirilir():
    """Tava planı hiç yüklenmediyse zayıf akımdaki tava sayılır — ama sayının altlıktan geldiği söylenir."""
    zayif = _dwg(1, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(10, 0, 20)])
    res = resolve([zayif])
    assert res.dropped == set()
    orphan = next(n for n in res.notes if n.kind == "orphan" and n.etype == "tray")
    assert orphan.severity == "review" and "yetkili paftası yüklenmedi" in orphan.message


def test_donati_elemanlari_kapsam_disi():
    """Demir tablosu satırlarının sahipliği kot eşleşmesiyle summarize() içinde kurulur; burada dokunulmaz."""
    a = _dwg(1, "Donatı planı", "sta_doseme_donati", "rebar", [ScopeElement(id=10, etype="rebar", points=[(0, 0)])])
    b = _dwg(2, "Kolon aplikasyon", "sta_kolon", "rebar", [ScopeElement(id=20, etype="rebar", points=[(0, 0)])])
    assert resolve([a, b]).dropped == set()


# ---------------------------------------------------------------- uçtan uca (API)

def test_api_ayni_tava_iki_paftada_bir_kez_sayilir(client, elec_dxf):
    """Kullanıcının örneği uçtan uca: aynı plan önce tava planı, sonra zayıf akım planı olarak yüklenir.
    Tava metrajı ikiye katlanmaz; ikinci paftanın ne kattığı keşif raporunda yazar."""
    pid = client.post("/api/projects", json={"name": "Tava kapsamı", "storey_height": 3.0}).json()["id"]
    ids = []
    for label, ptype in (("Kablo tava planı", "elk_tava"), ("Zayıf akım planı", "elk_zayif")):
        with open(elec_dxf, "rb") as f:
            r = client.post(f"/api/projects/{pid}/drawings", files={"file": (f"{ptype}.dxf", f, "application/dxf")},
                            data={"label": label, "plan_type": ptype, "discipline": "electrical"})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    q = client.get(f"/api/projects/{pid}/quantities").json()
    tava = [i for i in q["boq"]["items"] if i["kind"] == "tava"]
    assert tava, "tava kalemi üretilmedi"
    tek = client.get(f"/api/drawings/{ids[0]}/boq").json()
    tek_tava = {i["group"]: i["quantity"] for i in tek["items"] if i["kind"] == "tava"}
    for i in tava:
        assert i["quantity"] == pytest.approx(tek_tava[i["group"]], rel=1e-6), "tava ikinci paftadan tekrar sayıldı"

    scope = q["quality"]["scope"]
    assert scope["duplicate_count"] > 0
    note = next(n for n in scope["notes"] if n["kind"] == "duplicate" and n["etype"] == "tray")
    assert note["owner"] == "Kablo tava planı" and note["drawing"] == "Zayıf akım planı"


def test_uc_pafta_ayni_tavayi_ciziyorsa_ucu_de_tekilleşir():
    """Üçüncü paftadaki kopya "ek" sanılmamalı: sahibin nesnesi ikinci paftada tüketilmez, yalnız o pafta
    içinde bir kez eşleşir."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10, 0, 20)])
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(20, 0, 20)])
    yangin = _dwg(3, "Yangın algılama planı", "elk_zayif", "electrical", [_tray(30, 0, 20)])
    res = resolve([tava, zayif, yangin])
    assert res.dropped == {20, 30}
    assert not [n for n in res.notes if n.kind == "addition"]


def test_ayni_paftada_iki_kopya_varken_ikincisi_ektir():
    """Sahipte bir tava varken ikinci paftada iki tane çiziliyse: biri kopya, öbürü gerçek ikinci koldur."""
    tava = _dwg(1, "Kablo tava planı", "elk_tava", "electrical", [_tray(10, 0, 20)])
    zayif = _dwg(2, "Zayıf akım planı", "elk_zayif", "electrical", [_tray(20, 0, 20), _tray(21, 0.2, 20.2)])
    res = resolve([tava, zayif])
    assert len(res.dropped) == 1
    add = next(n for n in res.notes if n.kind == "addition")
    assert add.added_count == 1


def test_farkli_yoldan_olculen_ayni_nesne_eslesir():
    """Aynı duvar bir paftada uzunlukla, öbüründe alanla ölçülmüş olabilir: miktar birimleri tutmasa da
    aynı yerde aynı büyüklükteki nesne aynı nesnedir."""
    pts = [(0, 0), (10, 0), (10, 0.2), (0, 0.2)]
    mim = _dwg(1, "Mimari kat planı", "mim_kat_plani", "architectural",
               [ScopeElement(id=10, etype="wall", points=pts, length=10.0)])
    tavan = _dwg(2, "Tavan planı", "mim_tavan", "mapped",
                 [ScopeElement(id=20, etype="wall", points=pts, area=2.0)])
    assert resolve([mim, tavan]).dropped == {20}


def test_ikizi_komsusuna_kaptirmaz_sahte_ek_uretmez():
    """Eşleştirme "uyan ilk nesne"yi değil **en yakınını** alır. İlk uyanı almak, birebir ikizi olan bir
    elemanın ikizini komşusuna kaptırmasına ve ikizin sonra "ek" sanılmasına yol açıyordu: B Blok zemin
    planı iki kez yüklendiğinde 830 nesnenin 10'u ek sayılıp metrajı %1,2 şişiriyordu."""
    def kirisler(base: int) -> list[ScopeElement]:
        # 6 paralel kiriş, 1 m aralıkla: tolerans (0,35 × 7 m) komşuları da kapsıyor
        return [ScopeElement(id=base + i, etype="beam", points=[(0, i * 1.0), (7, i * 1.0)], length=7.0) for i in range(6)]

    kalip = _dwg(1, "Kat kalıp planı", "sta_kat_kalip", "structural", kirisler(10), kot=None)
    mim = _dwg(2, "Mimari altlık", "mim_kat_plani", "architectural", list(reversed(kirisler(20))), kot=None)
    res = resolve([kalip, mim])
    assert len(res.dropped) == 6
    assert not [n for n in res.notes if n.kind == "addition"]


# ---------------------------------------------------------------- kat kimliği çizimden okunur

def test_kat_kimligi_kottan_ve_plan_adindan_okunur():
    """Kat kimliği kullanıcıdan istenmez: kot yazan pafta kotundan, kat adı yazan pafta adından tanınır.
    İkisini birden taşıyan bir pafta ("2. KAT (+7.95) KALIP PLANI") iki kimliği birbirine bağlar: kotla
    adlandırılmış statik pafta ile kat adıyla adlandırılmış elektrik paftası aynı kata düşer."""
    from app.models import Drawing
    from app.services import _floor_identity

    def d(did, label):
        return Drawing(id=did, project_id=1, filename=f"{label}.dxf", stored_path="", label=label)

    kat = _floor_identity([d(1, "+7.95 KOTU KALIP PLANI"), d(2, "2. KAT AYDINLATMA PLANI"),
                           d(3, "ZEMİN KAT KUVVET PLANI"), d(4, "DETAY")])
    assert kat[1][0] and kat[2][0] and kat[1][0] != kat[2][0]      # bağlayan pafta yokken ayrı kimlikler
    assert kat[3][0] != kat[1][0] and kat[3][1] == "zemin kat"
    assert kat[4] == (None, "")                                    # katı bilinmeyen pafta

    kat = _floor_identity([d(1, "+7.95 KOTU KALIP PLANI"), d(2, "2. KAT AYDINLATMA PLANI"),
                           d(5, "2. KAT (+7.95) KALIP PLANI")])
    assert kat[1][0] == kat[2][0] == kat[5][0]                     # bağlandılar
    assert kat[2][1] == "+7.95"                                    # görünen ad kotu olan paftadan


def test_kotsuz_elektrik_paftalari_kat_adindan_eslesir():
    """Elektrik paftasında kot çoğu zaman yazmaz, kat adı yazar: tava planı ile zayıf akım planı aynı
    katta buluşur ve tava ikinci kez sayılmaz — kullanıcı hiçbir şey girmeden."""
    from app.models import Drawing
    from app.services import _floor_identity

    def d(did, label):
        return Drawing(id=did, project_id=1, filename=f"{label}.dxf", stored_path="", label=label)

    kat = _floor_identity([d(1, "2. KAT KABLO TAVA PLANI"), d(2, "2. KAT ZAYIF AKIM PLANI")])
    assert kat[1][0] == kat[2][0] is not None and kat[1][1] == "2. kat"
    tava = ScopeDrawing(id=1, label="2. kat tava", elements=[_tray(10, 0, 20)], floor=kat[1][0],
                        floor_label=kat[1][1], plan_type="elk_tava", discipline="electrical")
    zayif = ScopeDrawing(id=2, label="2. kat zayıf akım", elements=[_tray(20, 0, 20)], floor=kat[2][0],
                         floor_label=kat[2][1], plan_type="elk_zayif", discipline="electrical")
    res = resolve([tava, zayif])
    assert res.dropped == {20}
    assert next(n for n in res.notes if n.kind == "duplicate").kot == "2. kat"
