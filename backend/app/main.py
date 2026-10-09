import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.categories import router as categories_router
from app.api.emails import router as emails_router
from app.config import get_settings
from app.db.models import Base
from app.db.seed import seed
from app.db.session import SessionLocal, engine

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Email Classifier", version="0.1.0", lifespan=lifespan)
allowed_origins = list(
    dict.fromkeys(
        [
            settings.frontend_url,
            "http://localhost:5173",
            settings.api_public_url,
        ]
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(emails_router)
app.include_router(categories_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
