"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import config
from app.database import Base, engine
from app.routers import jobs

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)  # simple bootstrap; use Alembic for real migrations
    yield


app = FastAPI(
    title="Bulk Certificate Generator",
    description="Submit many recipients in one request; certificates are generated in the background.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(jobs.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
