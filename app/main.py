from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.websocket import registry, router as websocket_router
from app.core.config import get_settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    registry.ensure_storage()
    yield


settings = get_settings()
app = FastAPI(title="BridgeAI POC", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(websocket_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
