"""
PostgreSQL connection manager for RAG queries.
Uses asyncpg with a shared pool injected from app startup.
"""
import logging
import asyncio
from typing import Optional, List, Dict, Any
import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


def set_pool(pool: asyncpg.Pool) -> None:
    global _pool
    _pool = pool


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call set_pool() at app startup.")
    return _pool


async def fetch(query: str, *args, timeout: float = None) -> List[asyncpg.Record]:
    return await get_pool().fetch(query, *args, timeout=timeout)


async def fetchval(query: str, *args) -> Any:
    return await get_pool().fetchval(query, *args)


async def execute(query: str, *args) -> str:
    return await get_pool().execute(query, *args)


async def search_chunks(
    table: str,
    embedding: List[float],
    ticker_filter: Optional[str] = None,
    limit: int = 8,
    years: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Vector similarity search against ten_k_chunks or transcript_chunks.
    Returns chunks sorted by cosine similarity (highest first).

    `years` (optional): list of integer years. When provided, filters by
    `filing_year` (ten_k_chunks) or `year` (transcript_chunks). Empty/None = no filter.
    """
    embedding_str = f"[{','.join(str(v) for v in embedding)}]"

    # ten_k_chunks has `section`, `filing_year`, `chunk_type`; transcript_chunks has `year`/`quarter`
    if table == "ten_k_chunks":
        extra_cols = "filing_year AS year, NULL::integer AS quarter, section, chunk_type"
        year_col = "filing_year"
    else:
        extra_cols = "year, quarter, NULL::text AS section, NULL::text AS chunk_type"
        year_col = "year"

    where_parts = []
    params: List[Any] = [embedding_str]

    if ticker_filter:
        params.append(ticker_filter.upper())
        where_parts.append(f"ticker = ${len(params)}")

    if years:
        params.append(list(years))
        where_parts.append(f"{year_col} = ANY(${len(params)}::int[])")

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    params.append(limit)
    limit_idx = len(params)

    rows = await fetch(
        f"""
        SELECT id, ticker, chunk_text,
               1 - (embedding <=> $1::vector) AS similarity,
               {extra_cols}
        FROM {table}
        {where_clause}
        ORDER BY embedding <=> $1::vector
        LIMIT ${limit_idx}
        """,
        *params,
    )

    return [dict(r) for r in rows]


async def list_companies(search: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Return distinct companies from ten_k_chunks."""
    if search:
        rows = await fetch(
            """
            SELECT DISTINCT ticker, company_name
            FROM ten_k_chunks
            WHERE ticker ILIKE $1 OR company_name ILIKE $1
            ORDER BY ticker
            LIMIT $2
            """,
            f"%{search}%", limit,
        )
    else:
        rows = await fetch(
            """
            SELECT DISTINCT ticker, company_name
            FROM ten_k_chunks
            ORDER BY ticker
            LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]
