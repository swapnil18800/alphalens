"""Wire all routers into the FastAPI app."""
from fastapi import FastAPI
from app.routers import health, chat, sessions
from app.websocket.routes import router as ws_router


def setup_routes(app: FastAPI):
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(sessions.router)
    app.include_router(ws_router)
