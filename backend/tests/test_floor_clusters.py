"""Tesisat paftasındaki yan yana kat kümeleri (app/services.floor_clusters / assign_clusters).

Bir aydınlatma paftası çoğu projede bir katı değil BÜTÜN katları yan yana gösterir. Hepsi tek küme
sayılırsa her kat aynı kümeye hizalanır ve armatürler yanlış odalara yazılır — gerçek projede
üç katın üçü de ortadaki kümeyi aldı, soldaki ve sağdaki (551 armatür) boşta kaldı.
"""
from app.services import CLUSTER_MIN, assign_clusters, floor_clusters


class El:
    """Nokta eleman benzeri (armatür): uzunluğu yok, alanı küçük."""
    def __init__(self, x, y, layer="E-AYD-BLK"):
        self.points, self.layer = [(x, y)], layer
        self.length = 0.0
        self.area = 0.0


def _kume(x0, n=40, en=90.0, boy=25.0):
    """x0'dan başlayan, en × boy kutuya yayılmış n eleman."""
    return [El(x0 + (i % 10) * en / 9, (i // 10) * boy / max(1, n // 10 - 1)) for i in range(n)]


def test_yan_yana_katlar_ayri_kumelere_bolunur():
    els = _kume(0) + _kume(300) + _kume(600)
    ks = floor_clusters(els)
    assert len(ks) == 3
    assert [len(k) for k in ks] == [40, 40, 40]
    # soldan sağa sıralı gelmeli: atama sırayı buna göre kurar
    assert ks[0][0].points[0][0] < ks[1][0].points[0][0] < ks[2][0].points[0][0]


def test_tek_kat_tek_kume_kalir():
    assert len(floor_clusters(_kume(0, n=60))) == 1


def test_lejant_kume_sayilmaz():
    """Sembol listesi eleman sayısı bir katı andırır ama kapsadığı alan bir mertebe küçüktür.
    Ayıklanmazsa en tehlikeli yanlışı yapar: sıkışık olduğu için herhangi bir kaymayla büyük bir
    mahalin içine tamamen düşer, %100 isabet verir ve sıralı eşlemeyi kaydırır."""
    lejant = [El(-500 + (i % 2) * 2.0, (i // 2) * 1.0) for i in range(CLUSTER_MIN + 6)]
    ks = floor_clusters(lejant + _kume(0) + _kume(300))
    assert len(ks) == 2                       # lejant elendi
    assert all(k[0].points[0][0] >= 0 for k in ks)


def test_az_elemanli_kume_kat_sayilmaz():
    assert len(floor_clusters(_kume(0) + [El(300, 0), El(302, 0)])) == 1


# ------------------------------------------------------------------ atama

class Sahte:
    """Sahte kat paftasi."""
    def __init__(self, i):
        self.id, self.label = i, f"kat{i}"


class SahtePoly:
    """polys_by_src icindeki cokgen yerine: yalniz bounds okunuyor (kat sirasi icin)."""
    def __init__(self, x0):
        self.bounds = (x0, 0.0, x0 + 50.0, 20.0)


def _polys(*x0):
    """{kat id: [(mahal, cokgen)]} — kat sirasi bu kutulardan cikar."""
    return {i + 1: [(None, SahtePoly(x))] for i, x in enumerate(x0)}


def test_bir_kume_tek_kata_atanir(monkeypatch):
    """Asıl hata buydu: katlar ayrı ayrı hizalanınca üçü de en iyi puanı aynı kümeden alıp
    onu paylaşıyordu."""
    import app.services as S
    katlar = [Sahte(1), Sahte(2)]
    kumeler = [_kume(0), _kume(300)]
    # her iki kat da 2. kümeyi daha çok seviyor
    puan = {(0, 0): 0.50, (0, 1): 0.45, (1, 0): 0.90, (1, 1): 0.85}

    def sahte_align(target, source, elements, polys):
        i = 0 if elements[0].points[0][0] < 150 else 1
        j = katlar.index(source)
        return {"dx": 0.0, "dy": 0.0, "hit": int(100 * puan[(i, j)]), "total": len(elements),
                "source": "test", "bbox": None}

    monkeypatch.setattr(S, "align_drawing", sahte_align)
    eslesme, bosta = assign_clusters(Sahte(9), katlar, kumeler, _polys(0.0, 300.0))
    assert len(eslesme) == 2 and not bosta
    assert [m["source"].id for m in eslesme] == [1, 2]      # sıra korunur, küme paylaşılmaz


def test_zayif_eslesen_kume_atanmaz(monkeypatch):
    """Eşleşmesi eşiğin altında kalan küme uydurma bir kata yazılmaz: o katın mimari planı
    yüklenmemiş olabilir (gerçek projede kotlarda 5 kat var, 3'ünün planı yüklü)."""
    import app.services as S
    katlar = [Sahte(1)]
    kumeler = [_kume(0), _kume(300)]

    def sahte_align(target, source, elements, polys):
        oran = 0.70 if elements[0].points[0][0] < 150 else 0.10
        return {"dx": 0.0, "dy": 0.0, "hit": int(oran * len(elements)), "total": len(elements),
                "source": "test", "bbox": None}

    monkeypatch.setattr(S, "align_drawing", sahte_align)
    eslesme, bosta = assign_clusters(Sahte(9), katlar, kumeler, _polys(0.0))
    assert len(eslesme) == 1 and eslesme[0]["source"].id == 1
    assert len(bosta) == 1 and len(bosta[0]) == 40


def test_konum_sirasi_puandan_once_gelir(monkeypatch):
    """İki pafta da katları aynı sırada dizer. Gerçek projede isabet oranı hiçbir eşleşmeyi
    ayırt edemedi (1.206 m²'lik spor salonu hangi küme gelirse yüksek puan veriyor); sıralı
    atama, puanı biraz daha yüksek olan kaydırılmış atamaya tercih edilmeli."""
    import app.services as S
    katlar = [Sahte(1), Sahte(2)]
    kumeler = [_kume(0), _kume(300), _kume(600)]
    # kaydırılmış atama (küme2→kat1, küme3→kat2) toplamda biraz daha yüksek puanlı
    puan = {(0, 0): 0.55, (0, 1): 0.50, (1, 0): 0.67, (1, 1): 0.62, (2, 0): 0.47, (2, 1): 0.58}

    def sahte_align(target, source, elements, polys):
        i = min(2, int(elements[0].points[0][0] // 300))
        j = katlar.index(source)
        return {"dx": 0.0, "dy": 0.0, "hit": int(puan[(i, j)] * len(elements)), "total": len(elements),
                "source": "test", "bbox": None}

    monkeypatch.setattr(S, "align_drawing", sahte_align)
    eslesme, bosta = assign_clusters(Sahte(9), katlar, kumeler, _polys(0.0, 300.0))
    assert [m["source"].id for m in eslesme] == [1, 2]
    assert [round(m["cluster"][0].points[0][0]) for m in eslesme] == [0, 300]   # soldan başlar
    assert len(bosta) == 1                                                      # sağdaki küme boşta
