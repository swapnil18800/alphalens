"""
PostgreSQL connection pool lifecycle.
Pool is created at startup and injected into agent.rag.database_manager.
"""
import logging
from typing import Optional
import asyncpg
from config import settings
from agent.rag import database_manager as db_mgr

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def create_pool() -> asyncpg.Pool:
    global _pool
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Check your .env file.")

    logger.info("[db] Creating connection pool…")
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN,
        max_size=settings.DB_POOL_MAX,
        command_timeout=60,
        statement_cache_size=0,  # pgbouncer transaction-mode compatibility
    )
    db_mgr.set_pool(_pool)
    logger.info(f"[db] Pool ready (min={settings.DB_POOL_MIN} max={settings.DB_POOL_MAX})")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        logger.info("[db] Pool closed")
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool
