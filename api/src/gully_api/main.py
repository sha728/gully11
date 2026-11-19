from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings

app = FastAPI(title="Gully11 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter(prefix="/api/v1")


@v1.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(v1)
