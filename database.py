import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLITE_URL = "sqlite:///./myfans_control.db"
DATABASE_URL = os.getenv("MYFANS_DB_URL", SQLITE_URL)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_col(cur, table, col_name, col_def):
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    if col_name not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")


def migrate_db():
    if "sqlite" not in DATABASE_URL:
        return
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    asset_cols = [
        ("source_type", "VARCHAR(50) DEFAULT 'unknown'"),
        ("source_url", "VARCHAR(500)"),
        ("file_path", "VARCHAR(500)"),
        ("allowed_platforms", "VARCHAR(200) DEFAULT 'none'"),
        ("adult_level", "VARCHAR(50) DEFAULT 'none'"),
        ("sensitive_required", "BOOLEAN DEFAULT 0"),
        ("usage_expiry_date", "DATE"),
        ("myfans_ad_review_status", "VARCHAR(50) DEFAULT 'not_required'"),
        ("creator_permission_note", "TEXT"),
        ("ng_notes", "TEXT"),
        ("updated_at", "DATETIME"),
    ]
    try:
        for col, defn in asset_cols:
            _add_col(cur, "assets", col, defn)
    except Exception:
        pass

    conn.commit()
    conn.close()


def init_db():
    from models import (  # noqa
        Creator, CreatorCandidate, LinkQueueItem, AffiliateLink,
        Asset, GeneratedCard, PostDraft, PerformanceReport,
        ComplianceLog, AppSettings
    )
    Base.metadata.create_all(bind=engine)
    migrate_db()

    db = SessionLocal()
    from models import AppSettings
    settings = db.query(AppSettings).first()
    if not settings:
        db.add(AppSettings())
        db.commit()
    db.close()
