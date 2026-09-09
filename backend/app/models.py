from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    storey_height: float = 3.0
    slab_thickness: float = 0.15
    vat_rate: float = 0.0
    rebar_ratios: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    layer_profile: dict[str, list[str]] = Field(default_factory=dict, sa_column=Column(JSON))
    # Disiplin parametreleri (duvar yüksekliği, sıva/boya yüzü, kablo iniş payı, günlük çalışma saati...)
    params: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Plan seti: plan tipi kodu -> required / optional / skip (varsayılandan farklı olanlar; bkz. planset.py)
    plan_set: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    # Katmanlı sistem bileşen kararları: {sistem_kodu: {bileşen_kodu: {"include": bool, "spec": str}}} (bkz. services.project_systems)
    systems: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Drawing(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    filename: str
    stored_path: str
    label: str = ""                 # "Zemin Kat", "Temel" vb.
    discipline: str = "structural"  # structural | architectural | electrical | rebar | standard | mapped
    # Aynı paftada çizilen ek sezgisel disiplinler (mimari paftada elektrik gibi); analizde ana disipline eklenir
    disciplines: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Analizin bulduğu ama açılmamış disiplin kanıtı: {"electrical": 42} (katmanlardaki geometrik nesne sayısı)
    discipline_hints: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Kot yazılarından seviyeler (mutlak sistem) ve bu paftanın kat kotu (parser/levels.py) — kat yüksekliği bunlardan türer
    levels: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    kot: float | None = None
    plan_type: str = ""             # plan seti tipi (sta_kat_kalip, elk_tava, mim_tavan ...; bkz. planset.py)
    storey_count: int = 1           # bu planın temsil ettiği kat sayısı
    storey_height: float | None = None   # bu katın yüksekliği (m); None -> projenin H değeri
    unit: str = "m"
    unit_override: str | None = None
    unit_detected: bool = True
    unit_verdict: str | None = None      # yazı yükseklikleri / etiketlerin desteklediği birim (aynı dosyanın paftaları arasında oylama için)
    layers: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Çizim yazılarından tanınan malzeme / sistem kanıtı: {"OSB": {"evidence": [...], "spec": "11MM"}} (parser/materials.py)
    materials: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # Mahal alanı yazıları: [{"name": "LOBİ", "area_m2": 45.2}] (parser/schedules.py: parse_rooms)
    rooms: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
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
    set_fields: list[str] = Field(default_factory=list, sa_column=Column(JSON))   # kullanıcının açıkça girdiği alanlar (0 dahil)
