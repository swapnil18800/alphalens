"""
StockAnalysis.com Earnings Call Transcript Ingestion

Scrapes real earnings call transcripts from stockanalysis.com (free, no API key needed).
Covers 24 tickers × ~12-16 quarterly earnings calls each = ~300 transcripts.

Usage:
    python db/ingestion/ingest_stockanalysis.py --replace
    python db/ingestion/ingest_stockanalysis.py --tickers NVDA AAPL MSFT --replace
    python db/ingestion/ingest_stockanalysis.py --years 2023 2024 2025 --replace
"""
import argparse
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import asyncpg
import requests
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

log_dir = Path(__file__).parent / "logs" / "transcripts_stockanalysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"sa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to {log_file}")

BASE_URL = "https://stockanalysis.com"
CHUNK_SIZE = 1400
CHUNK_OVERLAP = 200
REQUEST_DELAY = 0.8  # polite delay between requests (seconds)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "AMD", "INTC", "CRM",
    "ORCL", "ADBE", "QCOM", "NFLX", "UBER",
    "IBM", "PANW", "NOW", "PYPL", "PLTR",
    "LRCX", "AMAT", "AVGO", "MU", "CSCO",
    "TXN", "SNOW",
]

DEFAULT_YEARS = (2023, 2024, 2025, 2026)


def _get_earnings_links(ticker: str, years: tuple) -> list[dict]:
    """Fetch transcript listing page and return quarterly earnings links with metadata."""
    url = f"{BASE_URL}/stocks/{ticker.lower()}/transcripts/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        logger.warning(f"[{ticker}] Failed to fetch transcript list: {e}")
        return []

    if r.status_code != 200:
        logger.warning(f"[{ticker}] HTTP {r.status_code} for transcript list")
        return []

    links = list(dict.fromkeys(re.findall(
        rf'href="(/stocks/{ticker.lower()}/transcripts/[^"]+)"', r.text
    )))

    results = []
    for link in links:
        m = re.search(r"-(q([1-4])-(20\d{2}))/?$", link, re.IGNORECASE)
        if not m:
            continue
        fy_year = int(m.group(3))
        quarter = int(m.group(2))
        if fy_year in years:
            results.append({
                "path": link,
                "fiscal_year": fy_year,
                "quarter": quarter,
                "slug": m.group(1),
            })

    return results


def _extract_transcript_text(path: str) -> Optional[str]:
    """Fetch one transcript page and extract clean text."""
    url = BASE_URL + path
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {path}: {e}")
        return None

    if r.status_code != 200:
        logger.warning(f"HTTP {r.status_code} for {path}")
        return None

    text = r.text

    # Find body start: prefer "Prepared Remarks" or "Operator"
    start = len(text)
    for marker in ["Prepared Remarks", "Operator"]:
        pos = text.find(marker)
        if 0 < pos < start:
            start = pos

    if start >= len(text) - 200:
        logger.warning(f"No transcript body found in {path}")
        return None

    body = text[start:]

    # Strip scripts, styles, then all HTML tags
    body = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.DOTALL)
    body = re.sub(r"<style[^>]*>.*?</style>", " ", body, flags=re.DOTALL)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"&[a-zA-Z]+;", " ", body)
    body = re.sub(r"&#\d+;", " ", body)

    # Normalize whitespace
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = body.strip()

    # Trim navigation/footer noise appended after transcript body
    # Look for common footer markers and cut there
    for cutoff in ["\nInvestor Relations", "\nDisclosure", "\nRecent Events", "\nAbout StockAnalysis"]:
        pos = body.find(cutoff)
        if pos > 5000:  # only cut if we already have substantial content
            body = body[:pos].strip()

    return body if len(body) > 500 else None


def _chunk_text(text: str) -> list[str]:
    """Sliding-window chunker matching SEC ingestion style."""
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        if start + CHUNK_SIZE >= len(text):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


async def ingest_ticker(
    conn: asyncpg.Connection,
    model: SentenceTransformer,
    ticker: str,
    years: tuple,
    replace: bool,
) -> tuple[int, int]:
    """Returns (chunks_inserted, transcripts_fetched)."""
    links = _get_earnings_links(ticker, years)
    if not links:
        logger.info(f"[{ticker}] No earnings transcripts found for years {years}")
        return 0, 0

    logger.info(f"[{ticker}] Found {len(links)} earnings transcripts to ingest")
    time.sleep(REQUEST_DELAY)

    if replace:
        deleted = await conn.execute(
            "DELETE FROM transcript_chunks WHERE ticker=$1 AND metadata->>'source'='stockanalysis'",
            ticker.upper(),
        )
        logger.info(f"[{ticker}] Deleted existing stockanalysis rows: {deleted}")

    chunks_inserted = 0
    transcripts_fetched = 0

    for entry in links:
        path = entry["path"]
        fiscal_year = entry["fiscal_year"]
        quarter = entry["quarter"]
        slug = entry["slug"]

        text = _extract_transcript_text(path)
        time.sleep(REQUEST_DELAY)

        if not text:
            logger.info(f"[{ticker}] {slug}: extraction failed")
            continue

        chunks = _chunk_text(text)
        embeddings = model.encode(chunks, batch_size=32, show_progress_bar=False)

        citation = f"{ticker} Q{quarter} FY{fiscal_year} Earnings Call"
        metadata_json = json.dumps({
            "source": "stockanalysis",
            "citation": citation,
            "slug": slug,
            "url": BASE_URL + path,
        })

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            emb_str = "[" + ",".join(f"{x:.6f}" for x in emb.tolist()) + "]"
            await conn.execute(
                """INSERT INTO transcript_chunks
                   (ticker, company_name, year, quarter, chunk_text, embedding, metadata, chunk_index)
                   VALUES ($1,$2,$3,$4,$5,$6::vector,$7::jsonb,$8)""",
                ticker.upper(), ticker.upper(),
                fiscal_year, quarter,
                chunk, emb_str, metadata_json, i,
            )
            chunks_inserted += 1

        transcripts_fetched += 1
        logger.info(
            f"[{ticker}] {slug}: {len(text)} chars -> {len(chunks)} chunks inserted"
        )

    return chunks_inserted, transcripts_fetched


async def main(args):
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set in .env")

    tickers = [t.upper() for t in args.tickers] if args.tickers else DEFAULT_TICKERS
    years = tuple(args.years) if args.years else DEFAULT_YEARS

    logger.info(f"Plan: {len(tickers)} tickers, fiscal years {years}")
    logger.info("Loading sentence transformer model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    conn = await asyncpg.connect(db_url, command_timeout=60, statement_cache_size=0)
    try:
        total_chunks = 0
        total_transcripts = 0

        for ticker in tickers:
            ins, fetched = await ingest_ticker(conn, model, ticker, years, args.replace)
            total_chunks += ins
            total_transcripts += fetched
            logger.info(
                f"[{ticker}] done — transcripts: {fetched}, chunks: {ins} "
                f"(cumulative: {total_transcripts} transcripts, {total_chunks} chunks)"
            )

        logger.info(f"\nDone. Total: {total_transcripts} transcripts, {total_chunks} chunks")

        # Coverage summary
        rows = await conn.fetch(
            """SELECT ticker, year, quarter, COUNT(*) AS n
               FROM transcript_chunks
               WHERE metadata->>'source'='stockanalysis'
               GROUP BY ticker, year, quarter
               ORDER BY ticker, year, quarter"""
        )
        logger.info(f"StockAnalysis coverage: {len(rows)} (ticker, year, quarter) combos")
        ticker_counts = {}
        for r in rows:
            ticker_counts[r["ticker"]] = ticker_counts.get(r["ticker"], 0) + 1
        for t, c in sorted(ticker_counts.items()):
            logger.info(f"  {t}: {c} quarters")

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest StockAnalysis earnings transcripts")
    parser.add_argument("--tickers", nargs="+", help="Tickers to ingest (default: all 24)")
    parser.add_argument("--years", nargs="+", type=int, help="Fiscal years to include (default: 2023-2026)")
    parser.add_argument("--replace", action="store_true", help="Delete existing stockanalysis rows before insert")
    args = parser.parse_args()
    asyncio.run(main(args))
