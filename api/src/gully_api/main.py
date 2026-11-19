from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import compare, players, venues
from .db import close_pool, open_pool
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(title="Gully11 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter(prefix="/api/v1")


@v1.get("/health")
def health() -> dict:
    return {"status": "ok"}


v1.include_router(players.router)
v1.include_router(compare.router)
v1.include_router(venues.router)
app.include_router(v1)
