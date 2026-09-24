from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Company(SQLModel, table=True):
    """Kiracı: projelerin sahibi olan şirket / ofis.

    Tek kiracılı kurulumda tek satır vardır (`tenancy.DEFAULT_COMPANY_SLUG`), ama tablo ve bağ
    baştan durur — kiracı ayrımı sonradan eklenemez."""
    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)     # URL / başlıkta kullanılan kısa ad
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    """Giriş yapan kişi. Her kullanıcı tek bir şirkete bağlıdır; şirketi o belirler (bkz. app/auth.py).

    Kullanıcı silinmez, pasifleştirilir: metraj kontrol kararlarında adı yazılı durur ("kim onayladı"),
    silinirse o iz kopar."""
    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id", index=True)
    email: str = Field(index=True, unique=True)     # küçük harfe çevrilmiş
    name: str = ""
    password_hash: str = ""
    role: str = "uzman"                             # tenancy.ROLES: sahibi | uzman | goruntuleyen
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime | None = None


class UserSession(SQLModel, table=True):
    """Açık oturum. Tarayıcıdaki çerez rastgele bir anahtar taşır; burada yalnız onun özeti durur —
    veritabanı ele geçse bile oturum çalınamaz. Çıkışta ve şifre değişince satır silinir."""
    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True, unique=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # Kiracı. None = kiracılık öncesi kayıt; varsayılan şirket onları da görür (bkz. tenancy.owned).
    company_id: int | None = Field(default=None, foreign_key="company.id", index=True)
    name: str
    description: str = ""
    storey_height: float = 3.0
    slab_thickness: float = 0.15
    # Kullanıcının açıkça girdiği döşeme kalınlığı; None = planda ölçülenden türetilsin (derive.slab_thicknesses)
    slab_manual: float | None = None
    # Ruhsat antedinden okunanlar (parser/titleblock.py): beton sınıfı, donatı, kat adedi, inşaat alanı.
    # Çapraz doğrulama kaynağıdır: çizimden çıkan kat sayısı antetle çelişirse kullanıcıya söylenir.
    titleblock: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    vat_rate: float = 0.0
    rebar_ratios: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    layer_profile: dict[str, list[str]] = Field(default_factory=dict, sa_column=Column(JSON))
    # Disiplin parametreleri (duvar yüksekliği, sıva/boya yüzü, kablo iniş payı, günlük çalışma saati...)
    params: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Plan seti: plan tipi kodu -> required / optional / skip (varsayılandan farklı olanlar; bkz. planset.py)
    plan_set: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    # Projedeki yapı blokları: ["C1", "C2", "C3", "C4"]. Yüklenen çizimlerin adından kendiliğinden dolar, elle
    # eklenir / silinir. Bir bloğun hiç çizimi yüklenmediyse ancak buradan bilinir — plan seti kontrolü buna bakar.
    blocks: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Katmanlı sistem bileşen kararları: {sistem_kodu: {bileşen_kodu: {"include": bool, "spec": str}}} (bkz. services.project_systems)
    systems: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Job(SQLModel, table=True):
    """Arka planda çalışan uzun iş (büyük dosya analizi). Bkz. app/jobs.py.

    177 MB'lık bir ruhsat dosyasında kırpma + analiz 6 dakika sürüyor; tarayıcı ve vekil sunucu
    o kadar beklemez. Yükleme bu kaydı açar ve hemen döner, istemci ilerlemeyi buradan okur."""
    id: int | None = Field(default=None, primary_key=True)
    project_id: int | None = Field(default=None, foreign_key="project.id", index=True)
    # Kiracı: iş başka bir iş parçacığında çalışır, bağlam değişkeni oraya taşınmaz — kaydın
    # kendisiyle taşınır ve işçi onu `tenancy.use_company` ile yeniden kurar.
    company_slug: str = ""
    kind: str = ""                   # "upload" gibi iş türü (jobs.register ile kaydedilir)
    label: str = ""                  # kullanıcıya gösterilen ad (dosya adı)
    status: str = "kuyrukta"         # kuyrukta | calisiyor | bitti | hata
    progress: float = 0.0            # %
    message: str = ""                # "3/6 pafta analiz edildi"
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column("payload", JSON))
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column("result", JSON))
    error: str = ""                  # kullanıcıya tek cümle
    detail: str = ""                 # yığın izi (kayıt için)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class QuantityOverride(SQLModel, table=True):
    """Keşif satırında kullanıcının verdiği karar: onay, ret ya da elle miktar.

    **Hesaplanan değer silinmez.** Kullanıcı 1.240 m² yerine 1.280 yazdıysa raporda ikisi de durur
    ("hesaplanan 1.240 · elle 1.280") — metrajın izlenebilirliği bunu gerektirir: hangi sayının
    programdan, hangisinin insandan geldiği sonradan sorulacaktır.

    Yeniden analizde korunur: kalem anahtarına (`kind:group`) bağlıdır, elemana değil. Bu, eleman
    düzeyindeki `Element.manual` deseninin keşif düzeyindeki karşılığıdır."""
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    item_key: str = Field(index=True)        # "duvar:ytong_20" — BoqItem.key
    status: str = "kontrol"                  # onaylandi | kontrol | reddedildi
    quantity: float | None = None            # elle girilen miktar; None = hesaplanan kullanılır
    computed: float | None = None            # değiştirildiği andaki hesaplanan değer (karşılaştırma için)
    reason: str = ""                         # gerekçe (şantiye ölçümü, şartname, müşavir kararı…)
    author: str = ""                         # kim
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Drawing(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    filename: str
    stored_path: str
    label: str = ""                 # "Zemin Kat", "Temel" vb.
    # Yapı bloğu: "C1", "A4-A5"; "" = ortak / tüm bina (bodrum, zemin, vaziyet, altyapı — bloklara bölünmeyen plan).
    # Dosya adından tanınır (parser/blocks.py), çizim listesinden değiştirilir.
    block: str = ""
    discipline: str = "structural"  # structural | architectural | electrical | rebar | standard | mapped
    # Aynı paftada çizilen ek sezgisel disiplinler (mimari paftada elektrik gibi); analizde ana disipline eklenir
    disciplines: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Analizin bulduğu ama açılmamış disiplin kanıtı: {"electrical": 42} (katmanlardaki geometrik nesne sayısı)
    discipline_hints: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Kot yazılarından seviyeler (mutlak sistem) ve bu paftanın kat kotu (parser/levels.py) — kat yüksekliği bunlardan türer
    levels: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    kot: float | None = None
    # Parantezli kot yazılarından ('+0.00 (+4.15)') bulunan iki sistem arası fark: yapı ±0,00'ının mutlak kotu.
    # Kat sırasını kot dizisine oturtmanın sıfır noktasıdır (parser/levels.level_for_rank).
    level_offset: float | None = None
    plan_type: str = ""             # plan seti tipi (sta_kat_kalip, elk_tava, mim_tavan ...; bkz. planset.py)
    storey_count: int = 1           # bu planın temsil ettiği kat sayısı (derive.storey_counts yazar)
    # Kullanıcının bu pafta için açıkça girdiği kat sayısı; None = çizimden türetilsin. Asla ezilmez.
    storey_manual: int | None = None
    storey_height: float | None = None   # bu katın yüksekliği (m); None -> projenin H değeri
    unit: str = "m"
    unit_override: str | None = None
    unit_detected: bool = True
    unit_verdict: str | None = None      # yazı yükseklikleri / etiketlerin desteklediği birim (aynı dosyanın paftaları arasında oylama için)
    layers: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Çizim yazılarından tanınan malzeme / sistem kanıtı: {"OSB": {"evidence": [...], "spec": "11MM"}} (parser/materials.py)
    materials: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Donatı yazılarından çap payları: {"14": 5009.0, "20": 26800.0} (parser/rebar_mix.py); oran demirini çaplara böler
    rebar_mix: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    # Alt / üst donatı kanıt sayısı: {"alt": 558, "ust": 869} -> çift kat (parser/rebar_mix.py: layer_verdict)
    rebar_layers: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    # Yazılarda geçen blok adları: {"A1": 1, "C2": 1} — vaziyet planında sitenin bütün blokları çıkar (parser/blocks.py)
    blocks_seen: dict[str, int] = Field(default_factory=dict, sa_column=Column(JSON))
    # Mahal alanı yazıları: [{"name": "LOBİ", "area_m2": 45.2}] (parser/schedules.py: parse_rooms)
    rooms: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    # Mahaller: duvarlardan çıkarılmış kapalı alanlar + daire / mahal hiyerarşisi (parser/spaces.py)
    spaces: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    # Tarama özeti (parser/hatches.py): desen başına adet / alan / tanınan malzeme ve lejant satırları
    hatches: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Doğrama pozları: {"sizes": {"EMP1": [1.9, 1.4]}, "kinds": {"EMP3": "door"}} (detectors/openings.py: poz_catalog)
    poz: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    analyzed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Element(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    drawing_id: int = Field(foreign_key="drawing.id", index=True)
    etype: str
    subtype: str | None = None
    name: str | None = None
    layer: str = ""
    b: float | None = None
    h: float | None = None
    thickness: float | None = None
    area: float = 0.0
    length: float = 0.0
    perimeter: float = 0.0
    count: int = 1
    confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    label_raw: str | None = None
    source: str = ""
    handle: str = ""
    points: list[list[float]] = Field(default_factory=list, sa_column=Column(JSON))
    included: bool = True
    manual: bool = False            # kullanıcı düzenledi/ekledi
    # yapısal ek bilgi (donatı tablosu satırı: dia_mm, weight_kg, length_m, target, kot)
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class PriceItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    key: str
    name: str
    unit: str
    unit_price: float = 0.0         # malzeme birim fiyatı (₺/birim)
    labor_price: float = 0.0        # işçilik birim fiyatı (₺/birim)
    brand: str = ""                 # tercih edilen marka / ürün
    hours_per_unit: float = 0.0     # işçilik süresi: adam-saat / birim
    crew_size: float = 0.0          # bu kalemde aynı anda çalışan kişi sayısı (0 = genel satırdan / 1)
    equipment_price: float = 0.0    # ekipman / makine birim bedeli (vinç, pompa, ekskavatör)
    # Taşeron birim fiyatı (her şey dahil): doluysa malzeme + işçilik + ekipmanın yerine geçer
    subcontract_price: float = 0.0
    # ÇŞB / firma birim fiyatı (her şey dahil): doluysa malzeme + işçiliğin yerine geçer
    poz_price: float = 0.0
    set_fields: list[str] = Field(default_factory=list, sa_column=Column(JSON))   # kullanıcının açıkça girdiği alanlar (0 dahil)


class MaterialPrice(SQLModel, table=True):
    """Ürün (malzeme) birim fiyatı: C30/37 hazır beton, Ø12 nervürlü demir, Ytong 20 cm…

    Anahtar cost.materials.material_of ile üretilir; aynı ürünü kullanan bütün keşif kalemleri bu fiyattan
    hesaplanır. İşçilik fiyatı kalemin kendi satırındadır (PriceItem)."""
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    key: str                        # ürün anahtarı (beton:c30_37, demir:o12, duvar:ytong:20…)
    name: str
    unit: str
    unit_price: float = 0.0         # ₺ / birim (KDV hariç)
    brand: str = ""                 # tercih edilen marka / tedarikçi
    note: str = ""


class Supplier(SQLModel, table=True):
    """Tedarikçi / taşeron: fiyat bankasındaki satırlar buna bağlanır."""
    id: int | None = Field(default=None, primary_key=True)
    name: str
    contact: str = ""               # yetkili kişi
    phone: str = ""
    email: str = ""
    note: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PriceBookItem(SQLModel, table=True):
    """Proje bağımsız fiyat bankası satırı: bir ürünün (ya da işçilik kaleminin) bir tedarikçideki fiyatı.

    Aynı ürün için birden çok tedarikçi satırı olabilir; geçerli fiyat `preferred` işaretli satır, yoksa en
    düşük pozitif fiyattır. Yeni projede ürün ve işçilik satırları bu bankadan doldurulur."""
    id: int | None = Field(default=None, primary_key=True)
    scope: str = "material"         # material (ürün) | labor (işçilik) | poz (ÇŞB birim fiyatı, her şey dahil)
    poz: str = Field(default="", index=True)   # ÇŞB poz numarası (scope="poz" satırlarında anahtar budur)
    key: str = Field(index=True)    # ürün anahtarı: beton:c30_37, demir:o12, duvar_ytong:*
    name: str = ""
    unit: str = ""
    supplier_id: int | None = Field(default=None, foreign_key="supplier.id", index=True)
    unit_price: float = 0.0         # malzeme ₺/birim (KDV hariç)
    labor_price: float = 0.0        # işçilik ₺/birim
    hours_per_unit: float = 0.0     # adam-saat / birim
    crew_size: float = 0.0
    brand: str = ""
    note: str = ""
    preferred: bool = False         # aynı anahtarın satırları arasında seçili olan
    updated_at: datetime = Field(default_factory=datetime.utcnow)
