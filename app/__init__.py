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

# Serve built React frontend from frontend/dist (disabled in dev, use Vite at :5175 instead)
# Uncomment when building for production
# _dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
# if os.path.isdir(_dist):
#     from fastapi.responses import FileResponse
#     from fastapi.staticfiles import StaticFiles
#
#     app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")
#
#     @app.get("/{full_path:path}", include_in_schema=False)
#     async def serve_spa(full_path: str):
#         """Serve React SPA for all non-API routes."""
#         index = os.path.join(_dist, "index.html")
#         return FileResponse(index)
