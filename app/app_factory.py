# app/app_factory.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .http_routes import http_router
from .ws_bridge import router as ws_router
from .orders_store import init_store, clear_store

def _setup_logging():
    level = logging.getLevelName((__import__("os").getenv("LOG_LEVEL") or "INFO").upper())
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)
    # Quieter websockets spam
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    init_store()
    print("🚀 Server starting, orders.json reset")
    try:
        yield
    finally:
        print("🔌 Server shutting down...")
        clear_store()

def create_app() -> FastAPI:
    app = FastAPI(title="Twilio ⇄ Deepgram Voice Agent", lifespan=lifespan)
    app.include_router(http_router)
    app.include_router(ws_router)
    return app
