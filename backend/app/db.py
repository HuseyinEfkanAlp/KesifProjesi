from __future__ import annotations

import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("KESIF_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = os.environ.get("KESIF_DB_URL", f"sqlite:///{(DATA_DIR / 'kesif.db').as_posix()}")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})


def init_db() -> None:
    from . import models  # noqa: F401  (tabloların kaydı)

    SQLModel.metadata.create_all(engine)
    _migrate(engine)


# Sonradan eklenen sütunlar: (tablo, sütun, SQL tipi). create_all var olan tabloya sütun eklemez.
_ADDED_COLUMNS = [
    ("drawing", "storey_height", "FLOAT"),
    ("drawing", "discipline", "VARCHAR DEFAULT 'structural'"),
    ("project", "params", "JSON"),
    ("priceitem", "labor_price", "FLOAT DEFAULT 0"),
    ("priceitem", "brand", "VARCHAR DEFAULT ''"),
    ("priceitem", "hours_per_unit", "FLOAT DEFAULT 0"),
    ("priceitem", "crew_size", "FLOAT DEFAULT 0"),
    ("element", "meta", "JSON"),
]


def _migrate(eng) -> None:
    """Var olan SQLite veritabanına eksik sütunları ekler (basit ileri yönlü geçiş)."""
    from sqlalchemy import inspect, text

    insp = inspect(eng)
    with eng.begin() as conn:
        for table, column, sqltype in _ADDED_COLUMNS:
            if table in insp.get_table_names():
                existing = {c["name"] for c in insp.get_columns(table)}
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sqltype}"))


def get_session():
    with Session(engine) as session:
        yield session
