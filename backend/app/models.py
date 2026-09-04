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
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Drawing(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    filename: str
    stored_path: str
    label: str = ""                 # "Zemin Kat", "Temel" vb.
    storey_count: int = 1           # bu planın temsil ettiği kat sayısı
    storey_height: float | None = None   # bu katın yüksekliği (m); None -> projenin H değeri
    unit: str = "m"
    unit_override: str | None = None
    unit_detected: bool = True
    layers: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
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


class PriceItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    key: str
    name: str
    unit: str
    unit_price: float = 0.0
