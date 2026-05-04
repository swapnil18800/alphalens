"""Application lifespan — startup and shutdown logic."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.utils.logging import setup_logging
from app.utils.database import create_pool, close_pool

logger = logging.getLogger(__name__)

_bm25_task: asyncio.Task | None = None


async def _warm_models_background():
    """Pre-load embedding + cross-encoder models so first query is fast."""
    try:
        import asyncio as _asyncio
        from agent.rag.search_engine import _get_embedding_model, _get_rerank_model
        loop = _asyncio.get_event_loop()
        await loop.run_in_executor(None, _get_embedding_model)
        logger.info("[startup] Embedding model loaded (all-MiniLM-L6-v2, 384-dim)")
        await loop.run_in_executor(None, _get_rerank_model)
        logger.info("[startup] Re-ranker loaded (ms-marco-TinyBERT-L-2-v2)")
    except Exception as e:
        logger.warning(f"[startup] Model warm-up failed: {e} — will load on first query")


async def _build_bm25_background():
    """Build BM25 index in the background — does not block startup."""
    try:
        from agent.rag.search_engine import build_bm25_corpus
        await build_bm25_corpus()
        logger.info("[startup] BM25 hybrid search index ready")
    except Exception as e:
        logger.warning(f"[startup] BM25 build failed: {e} — pgvector-only search active")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bm25_task
    # ── Startup ─────────────────────────────────────────────
    setup_logging()

    logger.info("━" * 52)
    logger.info("  AlphaLens  |  Agentic AI Equity Research")
    logger.info("━" * 52)

    # Database
    try:
        await create_pool()
        logger.info("[startup] PostgreSQL pool connected")
    except Exception as e:
        logger.error(f"[startup] DB connection failed: {e}")
        logger.warning("[startup] RAG search disabled — reconnect DB and restart")

    # Pre-compile LangGraph
    try:
        from agent.graph.graph import research_graph  # noqa: F401
        logger.info("[startup] LangGraph agent compiled")
    except Exception as e:
        logger.error(f"[startup] LangGraph compile failed: {e}")

    # Background: ML model warm-up + BM25
    asyncio.create_task(_warm_models_background())
    _bm25_task = asyncio.create_task(_build_bm25_background())
    logger.info("[startup] ML models + BM25 index loading in background…")

    logger.info("[startup] Ready → http://localhost:8000  (Ctrl+C to stop)")
    logger.info("━" * 52)

    yield  # ← app runs here

    # ── Shutdown ─────────────────────────────────────────────
    if _bm25_task and not _bm25_task.done():
        _bm25_task.cancel()
    await close_pool()
    logger.info("[shutdown] AlphaLens stopped cleanly.")
