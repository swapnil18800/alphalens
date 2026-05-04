"""
SEC 10-K Ingestion for AlphaLens (v2)

Improvements over v1:
  - CHUNK_SIZE 800 → 1400 chars (better fits all-MiniLM-L6-v2 512-token window)
  - CHUNK_OVERLAP 150 → 200 chars
  - BeautifulSoup table extraction: HTML tables → markdown pipe chunks (not destroyed by regex)
  - Section detection: stores raw "ITEM 7", "ITEM 1A", "PART II" etc. verbatim (no hardcoded mapping)
  - New DB columns: chunk_type ('prose'|'table'), citation, company_name populated
  - --replace flag: delete existing chunks before re-ingesting
  - --years default changed to 3 (needed for trend analysis)
  - Reads tickers from data/tickers.txt by default

Usage:
    python scripts/ingestion/ingest_sec.py --start-year 2023 --end-year 2025 --replace
    python scripts/ingestion/ingest_sec.py --tickers NVDA AAPL MSFT --start-year 2023 --end-year 2025 --replace
    python scripts/ingestion/ingest_sec.py --all --start-year 2023 --end-year 2025 --replace
"""
import argparse
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

import requests
import asyncpg
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

# Create log directory and file
log_dir = Path(__file__).parent / "logs" / "sec_10k"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"sec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to {log_file}")

HEADERS = {"User-Agent": "AlphaLens research (swapnil18800@gmail.com)"}
CHUNK_SIZE    = 1400   # all-MiniLM-L6-v2 max context ~512 tokens ≈ 2000 chars; 1400 is the sweet spot
CHUNK_OVERLAP = 200

# Default S&P 500 tech stocks
TOP_25 = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "INTC", "CRM", "ORCL", "ADBE", "QCOM", "NFLX", "UBER",
    "JPM", "GS", "BAC", "V", "PYPL",
    "SNOW", "PLTR", "ARM", "SMCI", "TSM",
]

# ── Row-aware table splitter ──────────────────────────────────────────────────

def _split_table_by_rows(tbl_md: str, max_chars: int = 4000, overlap_rows: int = 1) -> list:
    """Split a markdown pipe table into chunks of ~max_chars, breaking only at row boundaries.
    Preserves the header row in every chunk so the LLM sees column labels in every piece."""
    if len(tbl_md) <= max_chars:
        return [tbl_md]
    rows = tbl_md.split("\n")
    if len(rows) <= 3:
        return [tbl_md[:max_chars]]
    # Identify header lines (first row + optional separator row)
    header_lines = []
    body_start = 0
    if rows and rows[0].startswith("|"):
        header_lines.append(rows[0])
        body_start = 1
        if len(rows) > 1 and re.match(r'^\|\s*[-:]+', rows[1]):
            header_lines.append(rows[1])
            body_start = 2
    header = "\n".join(header_lines)
    body = rows[body_start:]
    chunks, current, i = [], header, 0
    while i < len(body):
        row = body[i]
        if len(current) + len(row) + 1 > max_chars and current != header:
            chunks.append(current)
            overlap = body[max(0, i - overlap_rows):i]
            current = header + ("\n" + "\n".join(overlap) if overlap else "")
        current = (current + "\n" + row) if current else row
        i += 1
    if current and current != header:
        chunks.append(current)
    return chunks or [tbl_md[:max_chars]]


# ── Section detection ──────────────────────────────────────────────────────────
# Matches "ITEM 7", "ITEM 1A", "ITEM 7A.", "PART II" etc. — stores raw text verbatim.
# No hardcoded name mapping: avoids overfitting and handles any filing structure.
_SECTION_RE = re.compile(r'(ITEM\s+\d+[A-Z]?\.?|PART\s+[IVX]+)', re.IGNORECASE)


def _detect_section(text: str) -> str:
    """Return the first SEC Item/Part header found in text, verbatim and uppercased.
    Returns empty string if no header is found.
    Examples: "ITEM 7", "ITEM 1A", "ITEM 7A.", "PART II" → stored as-is.
    NOTE: section is informational only — it enriches citations but is NOT used
    as a WHERE filter in retrieval (no overfitting risk).
    """
    m = _SECTION_RE.search(text)
    return m.group(1).strip().upper() if m else ""


# ── CIK lookup ────────────────────────────────────────────────────────────────

def get_cik_from_tickers_json(ticker: str) -> Optional[str]:
    """Get CIK from SEC's company_tickers.json"""
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=HEADERS,
            timeout=10
        )
        if r.status_code != 200:
            return None

        tickers_map = r.json()
        ticker_upper = ticker.upper()

        for entry in tickers_map.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                cik = entry.get("cik_str")
                if cik:
                    return str(cik).zfill(10)
        return None
    except Exception as e:
        logger.warning(f"Error fetching CIK for {ticker}: {e}")
        return None


# ── 10-K filing fetcher ───────────────────────────────────────────────────────

def get_10k_filings(cik: str, ticker: str, lookback_years: int = 3,
                    start_year: Optional[int] = None, end_year: Optional[int] = None) -> List[Dict]:
    """Fetch 10-K filings from SEC EDGAR.

    Returns list of dicts with keys:
      year, text (prose), tables (list of markdown strings), accession
    Tables are extracted from HTML <table> tags and converted to markdown
    BEFORE the HTML is stripped — preserving financial statement structure.

    Args:
      lookback_years: Years to look back from today (default 3). Ignored if start_year/end_year provided.
      start_year: Explicit start year (inclusive). Overrides lookback_years if provided.
      end_year: Explicit end year (inclusive). Defaults to current year if start_year provided.
    """
    filings = []
    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            logger.warning(f"Failed to fetch submissions for {ticker} (CIK {cik})")
            return filings

        data = r.json()

        all_filings = []
        recent_filings = data.get("filings", {}).get("recent", {})
        if recent_filings:
            all_filings.append(recent_filings)

        for file_obj in data.get("filings", {}).get("files", []):
            file_url = file_obj.get("name", "")
            if file_url:
                try:
                    rf = requests.get(
                        f"https://data.sec.gov/submissions/{file_url}",
                        headers=HEADERS, timeout=10
                    )
                    if rf.status_code == 200:
                        all_filings.append(rf.json())
                except Exception:
                    pass

        from datetime import date as _date
        # Use explicit year range if provided, otherwise compute from lookback_years
        if start_year is not None:
            min_year = start_year
            max_year = end_year if end_year is not None else _date.today().year
        else:
            min_year = _date.today().year - lookback_years
            max_year = _date.today().year

        records = []
        for filing_obj in all_filings:
            forms_list   = filing_obj.get("form", [])
            accs_list    = filing_obj.get("accessionNumber", [])
            dates_list   = filing_obj.get("filingDate", [])
            primary_list = filing_obj.get("primaryDocument", [])

            for i, (form, acc, date) in enumerate(zip(forms_list, accs_list, dates_list)):
                primary_doc = primary_list[i] if i < len(primary_list) else ""
                records.append((form, acc, date, primary_doc))

        for form, acc, date_str, primary_doc in records:
            if form != "10-K":
                continue
            year = int(date_str[:4]) if date_str else 0
            if year < min_year or year > max_year:
                continue

            try:
                acc_clean = acc.replace("-", "")
                base_url  = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}"
                doc_url   = None

                if primary_doc and primary_doc.lower().endswith((".htm", ".html")):
                    doc_url = f"{base_url}/{primary_doc}"

                if not doc_url:
                    index_url = f"{base_url}/{acc}-index.json"
                    r2 = requests.get(index_url, headers=HEADERS, timeout=15)
                    if r2.status_code == 200:
                        for item in r2.json().get("directory", {}).get("item", []):
                            name = item.get("name", "")
                            if name.lower().endswith((".htm", ".html")) and "index" not in name.lower():
                                doc_url = f"{base_url}/{name}"
                                break

                if not doc_url:
                    logger.warning(f"No 10-K document found in {acc} for {ticker}")
                    continue

                r3 = requests.get(doc_url, headers=HEADERS, timeout=30)
                if r3.status_code != 200:
                    continue

                # ── Parse HTML: extract tables first, then prose ──
                soup = BeautifulSoup(r3.text, "html.parser")

                # Convert each <table> to:
                #   (a) markdown pipe table → stored as dedicated table chunk
                #   (b) flat text replacement in DOM → kept inline in prose chunks
                # This ensures prose chunks retain the numeric data in context
                # while table chunks provide structured markdown for precise retrieval.
                table_mds = []
                for table in soup.find_all("table"):
                    md_rows = []
                    flat_rows = []
                    for i, row in enumerate(table.find_all("tr")):
                        cells = row.find_all(["th", "td"])
                        cell_texts = [c.get_text(strip=True).replace("|", " ") for c in cells]
                        if not any(cell_texts):
                            continue
                        md_rows.append("| " + " | ".join(cell_texts) + " |")
                        if i == 0:
                            md_rows.append("|" + " --- |" * len(cell_texts))
                        # Flat text: drop empty cells so prose isn't cluttered with "| | |"
                        non_empty = [t for t in cell_texts if t.strip()]
                        if non_empty:
                            flat_rows.append(" ".join(non_empty))
                    if md_rows:
                        table_mds.append("\n".join(md_rows))
                    # Replace table in DOM with clean flat text so prose chunks keep the numbers
                    from bs4 import NavigableString
                    table.replace_with(NavigableString(" " + " | ".join(flat_rows) + " "))

                # Extract prose (tables replaced with flat text — numbers still present)
                prose = soup.get_text(separator=" ")
                prose = re.sub(r"\s+", " ", prose).strip()

                if len(prose) < 1000:
                    logger.warning(f"  Document too short ({len(prose)} chars), skipping {acc}")
                    continue

                filings.append({
                    "year":      year,
                    "text":      prose[:300000],
                    "tables":    table_mds[:120],  # increased from 60 to capture full appendices
                    "accession": acc,
                    "source":    f"SEC EDGAR {year} 10-K",
                })
                logger.info(
                    f"  Downloaded {ticker} {year} 10-K "
                    f"({len(prose):,} chars prose + {len(table_mds)} tables)"
                )

                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"Error processing {acc}: {e}")
                continue

        return filings
    except Exception as e:
        logger.warning(f"Error fetching 10-K for {ticker}: {e}")
        return filings


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, ticker: str, year: int,
               tables: list = None) -> List[Dict]:
    """
    Split 10-K content into overlapping prose chunks + one chunk per markdown table.

    Prose chunks:
      - Fixed-size sliding window (CHUNK_SIZE=1400, CHUNK_OVERLAP=200)
      - Section detection: each chunk tagged with first "ITEM X" / "PART X" found
      - chunk_type = 'prose'

    Table chunks:
      - One un-split chunk per extracted markdown table (max 2000 chars)
      - Section detection applied to table text (often contains section context lines above table)
      - chunk_type = 'table'

    Both chunk types stored in ten_k_chunks table — differentiated by chunk_type column.
    Section tag is informational only; retrieval does not filter by it.
    """
    chunks = []

    # ── Prose: overlapping sliding window ──
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        body = text[start:end]
        section = _detect_section(body)
        citation = f"{ticker} 10-K {year}" + (f" {section}" if section else "")
        chunks.append({
            "ticker":       ticker,
            "company_name": ticker,      # ticker as company_name fallback (no lookup in ingest)
            "filing_year":  year,
            "chunk_text":   body,
            "section":      section,
            "chunk_type":   "prose",
            "citation":     citation,
        })
        start += CHUNK_SIZE - CHUNK_OVERLAP

    # ── Tables: row-integrity splitting (never breaks mid-row) ──
    for tbl_md in (tables or []):
        if not tbl_md.strip():
            continue
        section = _detect_section(tbl_md)
        citation_base = f"{ticker} 10-K {year}" + (f" {section} table" if section else " table")
        for i, piece in enumerate(_split_table_by_rows(tbl_md, max_chars=4000, overlap_rows=1)):
            suffix = f" (part {i+1})" if i > 0 else ""
            chunks.append({
                "ticker":       ticker,
                "company_name": ticker,
                "filing_year":  year,
                "chunk_text":   piece,
                "section":      section,
                "chunk_type":   "table",
                "citation":     citation_base + suffix,
            })

    return chunks


# ── Embed + store ─────────────────────────────────────────────────────────────

async def embed_and_store(conn: asyncpg.Connection, chunks: List[Dict]):
    """Generate embeddings and store in database (includes new chunk_type + citation columns)."""
    if not chunks:
        return

    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [c["chunk_text"] for c in chunks]

    logger.info(f"  Embedding {len(chunks)} chunks...")
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)

    records = [
        (
            c["ticker"],
            c.get("company_name"),
            c["filing_year"],
            f"[{','.join(str(v) for v in emb.tolist())}]",
            c["chunk_text"],
            c.get("section") or None,
            c.get("chunk_type", "prose"),
            c.get("citation"),
        )
        for c, emb in zip(chunks, embeddings)
    ]

    await conn.executemany(
        """INSERT INTO ten_k_chunks
           (ticker, company_name, filing_year, embedding, chunk_text,
            section, chunk_type, citation)
           VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8)""",
        records,
    )
    table_count = sum(1 for c in chunks if c.get("chunk_type") == "table")
    prose_count = len(records) - table_count
    logger.info(f"  Stored {len(records)} chunks ({prose_count} prose, {table_count} table)")


# ── Main ingestion ────────────────────────────────────────────────────────────

async def ingest(tickers: List[str], lookback_years: int = 3, replace: bool = False,
                 start_year: Optional[int] = None, end_year: Optional[int] = None):
    """Ingest 10-K filings for given tickers."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")

    conn = await asyncpg.connect(url)
    year_range = f"{start_year}-{end_year}" if start_year else f"last {lookback_years} years"
    logger.info(f"Ingesting 10-K for {len(tickers)} tickers, {year_range}\n")

    for ticker in tickers:
        logger.info(f"── {ticker} ──")

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM ten_k_chunks WHERE ticker=$1", ticker
        )
        if count > 0:
            if replace:
                await conn.execute("DELETE FROM ten_k_chunks WHERE ticker=$1", ticker)
                logger.info(f"  Deleted {count} existing chunks (--replace)")
            else:
                logger.info(f"  Already have {count} chunks — skipping (use --replace to re-ingest)")
                continue

        cik = get_cik_from_tickers_json(ticker)
        if not cik:
            logger.warning(f"  ⚠ CIK not found for {ticker}")
            continue

        logger.info(f"  CIK: {cik}")

        filings = get_10k_filings(cik, ticker, lookback_years, start_year, end_year)
        if not filings:
            logger.warning(f"  ⚠ No 10-K documents found for {ticker}")
            continue

        all_chunks = []
        for filing in filings:
            chunks = chunk_text(
                filing["text"],
                ticker,
                filing["year"],
                tables=filing.get("tables", []),
            )
            all_chunks.extend(chunks)

        if all_chunks:
            logger.info(f"  {len(filings)} filings → {len(all_chunks)} total chunks")
            await embed_and_store(conn, all_chunks)

        time.sleep(0.5)

    await conn.close()
    logger.info("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest SEC 10-K filings (v2)")
    parser.add_argument("--tickers", nargs="+", default=None,
                        help="Tickers to ingest (default: read from tickers.txt)")
    parser.add_argument("--ticker-file", type=str, default="tickers.txt",
                        help="File with one ticker per line (default: tickers.txt in same directory)")
    parser.add_argument("--years", type=int, default=3,
                        help="Years to look back (default: 3). Ignored if --start-year is provided")
    parser.add_argument("--start-year", type=int, default=None,
                        help="Start year (inclusive). Overrides --years if provided")
    parser.add_argument("--end-year", type=int, default=None,
                        help="End year (inclusive). Defaults to current year if --start-year is provided")
    parser.add_argument("--all", action="store_true",
                        help="Use full TOP_25 list (overrides ticker file)")
    parser.add_argument("--replace", action="store_true",
                        help="Delete existing chunks and re-ingest (required to apply new chunking)")
    args = parser.parse_args()

    # Determine which tickers to use
    if args.all:
        tickers = TOP_25
    elif args.tickers:
        tickers = args.tickers
    else:
        # Read from ticker file (in same directory as script)
        script_dir = Path(__file__).parent
        ticker_file_path = script_dir / args.ticker_file

        if ticker_file_path.exists():
            with open(ticker_file_path, 'r') as f:
                tickers = [line.strip().upper() for line in f if line.strip()]
            logger.info(f"Loaded {len(tickers)} tickers from {ticker_file_path}")
        else:
            logger.error(f"Ticker file not found: {ticker_file_path}")
            logger.info(f"Falling back to TOP_25 ({len(TOP_25)} tickers)")
            tickers = TOP_25

    asyncio.run(ingest(tickers, args.years, replace=args.replace,
                       start_year=args.start_year, end_year=args.end_year))
