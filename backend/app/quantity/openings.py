"""Boşluğu (kapı / pencere) taşıyan duvarı bulur; alanı malzemeler arasında asla paylaştırmaz.

Koordinatlar metredir. Buradaki asıl karar "hangi duvardan düşülecek" değil, **düşülecek mi**:

  Duvar kesiksiz çizilmişse boşluk duvarın üstünde durur (mesafe ≈ 0) — alan brüttür, boşluk düşülür.
  Duvar boşlukta kesilerek çizilmişse boşluk iki duvar parçası arasındaki açıklığa düşer — o alan zaten
  duvar değildir, **tekrar düşülürse metraj eksik çıkar**.

Gerçek ölçüm (B2 blok, 93 boşluk): 86'sı hiçbir duvarla çakışmıyor, en yakın duvar medyan 0,51 m ötede ve
iki duvar parçası arasındaki açıklık boşluk genişliğine eşit (1,42 m ≈ 1,40 m pencere). Yani bu projede duvar
alanı zaten net. Toleransı büyütüp hepsini düşmek %17 çift düşüm demekti.

Çakışma toleransı duvarın kendi kalınlığından türer (sabit bir mesafe her ölçekte yanlıştır): boşluk işareti
duvarın yarı kalınlığı kadar içinde olabilir. Hiçbir duvara yakın olmayan boşluk gerçekten eşleşmemiştir ve
uyarı üretir.
"""
from math import isfinite

from shapely.geometry import LineString, Point, Polygon
from shapely.errors import GEOSException


def value(element, key, default=None):
    return element.get(key, default) if isinstance(element, dict) else getattr(element, key, default)


def geometry(element):
    points = value(element, 'points') or []
    try:
        if not points or not all(isfinite(float(v)) for p in points for v in p[:2]):
            return None
        if len(points) == 1:
            return Point(points[0])
        if len(points) == 2:
            return LineString(points)
        poly = Polygon(points)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.geom_type == "Polygon" and poly.area > 1e-10:
            return poly
        # Çizgiye çökmüş kutu: duvar üstündeki kapı / pencere bloğunun sınırı sıfır yükseklikte olabilir
        # (blok tek bir yatay çizgiden ibarettir). Bu da geçerli bir konumdur; None dönersek boşluk
        # "yakınında duvar yok" sayılır ve hiçbir duvardan düşülmez.
        line = LineString(points)
        return line if not line.is_empty else None
    except (ValueError, TypeError, GEOSException):
        return None


# Boşluğun "duvarın üstünde" sayılması için duvara olan en büyük mesafe: duvarın yarı kalınlığı + bu pay.
# Duvar kalınlığı okunamazsa yalnız bu pay kullanılır.
HOST_MARGIN = .05
# Bu kadar uzakta hiç duvar yoksa boşluk gerçekten eşleşmemiştir (duvarı silinmiş / başka paftada).
NEAR_WALL = 2.5


def _host_tolerance(wall) -> float:
    """Bir duvarın "üstünde" sayılma mesafesi: yarı kalınlık + pay. Sabit mesafe her ölçekte yanlıştır."""
    b = value(wall['element'], 'b') or 0.0
    try:
        b = float(b)
    except (TypeError, ValueError):
        b = 0.0
    return max(b, 0.0) / 2.0 + HOST_MARGIN


def allocate_openings(walls, openings, deductible, tolerance=None):
    """walls: [{element, gross}], openings: [{element, width, height, count}].

    Sonuçlar duvar başına, kat çarpanından öncedir. Koordinatı olmayan tek duvarlı elle giriş desteklenir
    ve açıkça varsayım olarak işaretlenir.
    """
    allocations = [{'deducted': 0.0, 'all': 0.0, 'already_net': 0.0, 'matches': []} for _ in walls]
    shapes = [geometry(w['element']) for w in walls]
    tols = [_host_tolerance(w) if tolerance is None else tolerance for w in walls]
    issues = []
    already_net = {'count': 0, 'area_m2': 0.0}
    for opening in openings:
        e = opening['element']
        width, height, count = opening['width'], opening['height'], opening['count']
        name = value(e, 'name') or value(e, 'handle') or 'Adsız boşluk'
        area = width * height * count
        record = {'opening_id': value(e, 'id'), 'opening': name, 'area_m2': area}
        if width <= 0 or height <= 0 or not isfinite(area) or count <= 0:
            issues.append({**record, 'reason': 'missing_dimensions', 'message': f'{name}: boşluk ölçüsü eksik veya geçersiz; duvardan düşülmedi.'})
            continue
        shape = geometry(e)
        chosen = None
        method = 'geometry'
        nearest = None
        if shape is not None:
            candidates = sorted((shape.distance(s), i) for i, s in enumerate(shapes) if s is not None)
            nearest = candidates[0] if candidates else None
            # duvarın üstünde mi: her duvarın kendi yarı kalınlığı kadar tolerans
            on_wall = [(d, i) for d, i in candidates if d <= tols[i]]
            if on_wall and (len(on_wall) == 1 or on_wall[1][0] - on_wall[0][0] > .05):
                chosen = on_wall[0][1]
        # Koordinatsız elle girişte tek duvar varsa malzeme tektir; konum kanıtı yoktur.
        if chosen is None and len(walls) == 1 and (shape is None or shapes[0] is None):
            chosen, method = 0, 'single_wall_assumption'
        if chosen is None:
            if nearest is not None and nearest[0] <= NEAR_WALL:
                # Duvar boşlukta kesilerek çizilmiş: açıklık zaten duvar alanına girmemiş. Tekrar düşülmez.
                already_net['count'] += 1
                already_net['area_m2'] += area
                allocations[nearest[1]]['already_net'] += area
                allocations[nearest[1]]['matches'].append({**record, 'wall_id': value(walls[nearest[1]]['element'], 'id'),
                                                           'method': 'already_net', 'distance_m': round(nearest[0], 3)})
                continue
            issues.append({**record, 'reason': 'unmatched',
                           'message': f'{name}: yakınında duvar yok; {area:g} m² boşluk hiçbir duvarla ilişkilendirilemedi.'})
            continue
        a = allocations[chosen]
        a['all'] += area
        if deductible(width * height):
            a['deducted'] += area
        a['matches'].append({**record, 'wall_id': value(walls[chosen]['element'], 'id'), 'method': method})
        if method != 'geometry':
            issues.append({**record, 'reason': method, 'message': f'{name}: konum kanıtı yok; paftadaki tek duvara ait olduğu varsayıldı.'})
    for wall, allocation in zip(walls, allocations):
        if allocation['all'] > wall['gross'] + 1e-6:
            issues.append({'opening': '', 'area_m2': allocation['all'], 'reason': 'exceeds_wall',
                           'message': 'Eşleştirilen boşluk alanı duvar brüt alanını aşıyor; ölçü, adet ve duvar ilişkisi kontrol edilmeli.'})
    if already_net['count']:
        issues.append({'opening': '', 'area_m2': round(already_net['area_m2'], 2), 'reason': 'already_net',
                       'message': f"{already_net['count']} boşluk ({already_net['area_m2']:.1f} m²) duvar parçaları arasındaki "
                                  "açıklığa düşüyor: duvar zaten kesilerek çizilmiş, alan net. Tekrar düşülmedi."})
    return allocations, issues
