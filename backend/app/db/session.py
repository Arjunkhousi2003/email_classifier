from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

settings = get_settings()
if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # Supabase session pooler allows a small number of clients. Keep the pool tight.
    pool_kwargs: dict = {"pool_pre_ping": True}
    if "supabase.com" in settings.database_url or "supabase.co" in settings.database_url:
        pool_kwargs["pool_size"] = 5
        pool_kwargs["max_overflow"] = 0
    engine = create_engine(settings.database_url, **pool_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
