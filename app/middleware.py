"""CORS + request logging middleware."""
import time
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from config import settings

logger = logging.getLogger(__name__)


def setup_middleware(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.time()
        response = await call_next(request)
        ms = int((time.time() - t0) * 1000)
        if not request.url.path.startswith("/static"):
            logger.debug(f"{request.method} {request.url.path} → {response.status_code} ({ms}ms)")
        return response
