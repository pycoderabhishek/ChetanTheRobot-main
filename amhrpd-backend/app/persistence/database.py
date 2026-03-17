"""Database Configuration and Session Management"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# SQLite database path
DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./amhrpd.db")

# Use StaticPool for SQLite in-memory operations
engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool if "sqlite:///:memory:" in DB_PATH else None,
    echo=False  # Set to True for SQL debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database - creates all tables"""
    from app.persistence.models import Base
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully")


# Enable foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key support in SQLite"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
