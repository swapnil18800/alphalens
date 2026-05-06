"""
AlphaLens FastAPI application factory.
Imported by uvicorn as: uvicorn app:app
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

from config import settings
from app.lifespan import lifespan
from app.middleware import setup_middleware
from app.routes import setup_routes

app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

setup_middleware(app)
setup_routes(app)

# Serve built React SPA from frontend/dist in production.
# In dev the Vite dev server runs at :5175 (proxy via vite.config.ts).
_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(_dist):
    from fastapi.responses import FileResponse

    # Mount Vite's hashed asset bundles (JS/CSS/images) and public static dirs
    for _subdir, _name in [("assets", "static-assets"), ("logos", "static-logos"), ("stack_logos", "static-stack-logos")]:
        _path = os.path.join(_dist, _subdir)
        if os.path.isdir(_path):
            app.mount(f"/{_subdir}", StaticFiles(directory=_path), name=_name)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Catch-all: serve index.html for all non-API routes (React Router handles them)."""
        return FileResponse(os.path.join(_dist, "index.html"))
