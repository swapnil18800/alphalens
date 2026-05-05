#!/usr/bin/env python3
"""
Ingest quarterly financial data from yfinance into transcript_chunks table.

Substitutes paid earnings-call transcripts with structured quarterly summaries
from Yahoo Finance (free, no API key). Each quarter gets one rich text chunk
covering revenue, margins, EPS, and key metrics.

Reads tickers from data/tickers.txt by default.

Usage (run from repo root):
    python scripts/ingestion/ingest_yfinance.py --start-quarter "Q1 2023" --end-quarter "Q4 2025" --replace
    python scripts/ingestion/ingest_yfinance.py --tickers NVDA AAPL MSFT --start-quarter "Q1 2023" --end-quarter "Q4 2025" --replace
    python scripts/ingestion/ingest_yfinance.py --ticker-file data/tickers.txt --start-quarter "Q1 2023" --end-quarter "Q4 2025" --replace
"""

import os
import sys
import json
import logging
import argparse
import time
from datetime import datetime
from typing import Optional
from pathlib import Path

# Run from repo root: python scripts/ingestion/ingest_yfinance.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env", override=True)

import numpy as np
import psycopg2
from psycopg2.extras import execute_values

try:
    import yfinance as yf
except ImportError:
    print("Install yfinance: pip install yfinance")
    sys.exit(1)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Install sentence-transformers: pip install sentence-transformers")
    sys.exit(1)

# Create log directory and file
log_dir = Path(__file__).parent / "logs" / "yfinance_transcripts"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to {log_file}")

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def fmt(val, prefix="$", suffix="", decimals=2, billions=False, millions=False):
    """Format a number nicely."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    if billions:
        return f"{prefix}{val/1e9:.{decimals}f}B{suffix}"
    if millions:
        return f"{prefix}{val/1e6:.{decimals}f}M{suffix}"
    return f"{prefix}{val:,.{decimals}f}{suffix}"


def pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val*100:.1f}%"


def yoy_change(new_val, old_val):
    """Compute YoY % change string."""
    try:
        if old_val and old_val != 0:
            chg = (new_val - old_val) / abs(old_val) * 100
            direction = "up" if chg >= 0 else "down"
            return f"{direction} {abs(chg):.1f}% YoY"
    except Exception:
        pass
    return ""


def build_quarter_summary(ticker: str, info: dict, quarterly_financials: dict,
                          year: int, quarter: int) -> Optional[str]:
    """
    Build a rich text summary for a single quarter's financial data.
    Returns None if insufficient data.
    """
    qkey = f"{year}_q{quarter}"
    data = quarterly_financials.get(qkey, {})
    if not data:
        return None

    company_name = info.get("longName", ticker)
    sector = info.get("sector", "")
    industry = info.get("industry", "")

    revenue = data.get("revenue")
    gross_profit = data.get("gross_profit")
    operating_income = data.get("operating_income")
    net_income = data.get("net_income")
    eps = data.get("eps_diluted")
    ebitda = data.get("ebitda")
    prev_revenue = data.get("prev_year_revenue")
    prev_net_income = data.get("prev_year_net_income")

    if revenue is None:
        return None

    # Quarter month mapping
    quarter_months = {1: "Q1 (Jan-Mar)", 2: "Q2 (Apr-Jun)", 3: "Q3 (Jul-Sep)", 4: "Q4 (Oct-Dec)"}
    q_label = quarter_months.get(quarter, f"Q{quarter}")

    lines = [
        f"# {company_name} ({ticker}) — {q_label} {year} Financial Results",
        f"Sector: {sector} | Industry: {industry}",
        "",
        f"## Revenue",
        f"Total revenue for {q_label} {year}: {fmt(revenue, billions=True)} "
        f"({yoy_change(revenue, prev_revenue)})",
    ]

    if gross_profit is not None:
        gm = gross_profit / revenue if revenue else None
        lines.append(f"Gross profit: {fmt(gross_profit, billions=True)} | Gross margin: {pct(gm)}")

    if operating_income is not None:
        om = operating_income / revenue if revenue else None
        lines.append(f"Operating income: {fmt(operating_income, billions=True)} | Operating margin: {pct(om)}")

    if net_income is not None:
        nm = net_income / revenue if revenue else None
        lines.append(f"Net income: {fmt(net_income, billions=True)} ({yoy_change(net_income, prev_net_income)}) | Net margin: {pct(nm)}")

    if ebitda is not None:
        lines.append(f"EBITDA: {fmt(ebitda, billions=True)}")

    if eps is not None:
        lines.append(f"Diluted EPS: {fmt(eps, prefix='$', decimals=2)}")

    # Market context from info
    market_cap = info.get("marketCap")
    if market_cap:
        lines.extend(["", f"## Company Overview",
                       f"Market cap: {fmt(market_cap, billions=True)}"])
        if info.get("trailingPE"):
            lines.append(f"P/E ratio (trailing): {info['trailingPE']:.1f}x")
        if info.get("forwardPE"):
            lines.append(f"P/E ratio (forward): {info['forwardPE']:.1f}x")

    lines.extend([
        "",
        f"## Business Context",
        info.get("longBusinessSummary", "")[:500] if info.get("longBusinessSummary") else "",
    ])

    return "\n".join(l for l in lines if l is not None)


def parse_quarter_str(qstr: str) -> tuple[int, int]:
    """Parse 'Q1 2023' or 'Q1-2023' or similar into (year, quarter).
    Raises ValueError if format is invalid.
    """
    qstr = qstr.strip().upper()
    # Try various separators: space, dash, underscore
    parts = None
    for sep in [' ', '-', '_']:
        if sep in qstr:
            parts = qstr.split(sep)
            break
    if not parts:
        raise ValueError(f"Cannot parse quarter string: {qstr}")

    q_part, y_part = parts[0].strip(), parts[-1].strip()

    if not q_part.startswith('Q'):
        raise ValueError(f"Quarter part must start with 'Q': {qstr}")

    try:
        quarter = int(q_part[1:])
        year = int(y_part)
    except ValueError:
        raise ValueError(f"Invalid quarter string: {qstr}")

    if quarter < 1 or quarter > 4:
        raise ValueError(f"Quarter must be 1-4, got: {quarter}")

    return year, quarter


def fetch_quarterly_data(ticker_symbol: str, lookback_quarters: int = 8,
                        start_year: Optional[int] = None, start_quarter: Optional[int] = None,
                        end_year: Optional[int] = None, end_quarter: Optional[int] = None) -> tuple[dict, dict]:
    """
    Fetch quarterly financial data from yfinance.
    Returns (company_info, quarterly_data_by_quarter_key).

    Args:
      lookback_quarters: Quarters to look back from today (default 8). Ignored if start_year provided.
      start_year, start_quarter: Explicit date range start (inclusive).
      end_year, end_quarter: Explicit date range end (inclusive). Defaults to today if start_year provided.
    """
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info or {}
        logger.info(f"  Fetched info for {ticker_symbol}: {info.get('longName', 'N/A')}")
    except Exception as e:
        logger.warning(f"  Could not fetch info for {ticker_symbol}: {e}")
        info = {}

    quarterly_data = {}

    try:
        income_stmt = t.quarterly_income_stmt
        if income_stmt is None or income_stmt.empty:
            logger.warning(f"  No quarterly income statement for {ticker_symbol}")
            return info, quarterly_data

        # income_stmt columns are Timestamps (quarter end dates)
        cols = list(income_stmt.columns)[:lookback_quarters]

        def safe_get(df, row_names, col):
            for name in row_names:
                try:
                    val = df.loc[name, col]
                    if val is not None and not (isinstance(val, float) and np.isnan(val)):
                        return float(val)
                except Exception:
                    pass
            return None

        for col in cols:
            dt = col.to_pydatetime() if hasattr(col, 'to_pydatetime') else col
            year = dt.year
            month = dt.month
            # Fiscal quarter from calendar month (approximate)
            quarter = (month - 1) // 3 + 1
            qkey = f"{year}_q{quarter}"

            revenue = safe_get(income_stmt, ["Total Revenue", "Revenue"], col)
            gross_profit = safe_get(income_stmt, ["Gross Profit"], col)
            operating_income = safe_get(income_stmt, ["Operating Income", "EBIT"], col)
            net_income = safe_get(income_stmt, ["Net Income", "Net Income Common Stockholders"], col)
            ebitda = safe_get(income_stmt, ["EBITDA"], col)

            # EPS from separate call
            eps = None
            try:
                eps_row = safe_get(income_stmt, ["Diluted EPS", "Basic EPS"], col)
                if eps_row:
                    eps = eps_row
            except Exception:
                pass

            quarterly_data[qkey] = {
                "revenue": revenue,
                "gross_profit": gross_profit,
                "operating_income": operating_income,
                "net_income": net_income,
                "ebitda": ebitda,
                "eps_diluted": eps,
                "year": year,
                "quarter": quarter,
                "quarter_end_date": dt.strftime("%Y-%m-%d"),
            }

        # Add YoY comparisons (compare with same quarter 1 year back)
        for qkey, qdata in quarterly_data.items():
            year, q = qdata["year"], qdata["quarter"]
            prev_key = f"{year-1}_q{q}"
            if prev_key in quarterly_data:
                qdata["prev_year_revenue"] = quarterly_data[prev_key]["revenue"]
                qdata["prev_year_net_income"] = quarterly_data[prev_key]["net_income"]

        # Filter by date range if provided
        if start_year is not None or start_quarter is not None:
            # Default end to current date if not provided
            from datetime import datetime as dt_module
            today = dt_module.today()
            eff_end_year = end_year if end_year is not None else today.year
            eff_end_q = end_quarter if end_quarter is not None else ((today.month - 1) // 3 + 1)
            eff_start_year = start_year if start_year is not None else today.year
            eff_start_q = start_quarter if start_quarter is not None else ((today.month - 1) // 3 + 1)

            filtered = {}
            for qkey, qdata in quarterly_data.items():
                year, q = qdata["year"], qdata["quarter"]
                # Check if (year, quarter) falls within [start, end]
                start_cmp = (year, q) >= (eff_start_year, eff_start_q)
                end_cmp = (year, q) <= (eff_end_year, eff_end_q)
                if start_cmp and end_cmp:
                    filtered[qkey] = qdata
            quarterly_data = filtered

    except Exception as e:
        logger.warning(f"  Error fetching quarterly data for {ticker_symbol}: {e}")

    logger.info(f"  Got {len(quarterly_data)} quarters for {ticker_symbol}")
    return info, quarterly_data


def ensure_transcript_chunks_table(cur):
    """Create transcript_chunks table if it doesn't exist."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transcript_chunks (
            id BIGSERIAL PRIMARY KEY,
            chunk_text TEXT NOT NULL,
            embedding VECTOR(384),
            metadata JSONB DEFAULT '{}',
            ticker VARCHAR(10) NOT NULL,
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            chunk_index INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    # Index for fast ticker+quarter lookups
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_transcript_chunks_ticker_year_quarter
        ON transcript_chunks (ticker, year, quarter)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_transcript_chunks_ticker
        ON transcript_chunks (ticker)
    """)


def ingest_ticker(
    ticker_symbol: str,
    conn,
    model: SentenceTransformer,
    lookback_quarters: int = 8,
    replace_existing: bool = False,
    start_year: Optional[int] = None,
    start_quarter: Optional[int] = None,
    end_year: Optional[int] = None,
    end_quarter: Optional[int] = None
) -> int:
    """
    Ingest quarterly financial summaries for one ticker.
    Returns number of chunks inserted.
    """
    cur = conn.cursor()
    ticker_upper = ticker_symbol.upper()

    # Check existing data
    cur.execute("SELECT DISTINCT year, quarter FROM transcript_chunks WHERE ticker = %s", (ticker_upper,))
    existing = {(r[0], r[1]) for r in cur.fetchall()}

    info, quarterly_data = fetch_quarterly_data(
        ticker_symbol, lookback_quarters,
        start_year=start_year, start_quarter=start_quarter,
        end_year=end_year, end_quarter=end_quarter
    )

    rows_inserted = 0
    for qkey, qdata in quarterly_data.items():
        year, quarter = qdata["year"], qdata["quarter"]

        if (year, quarter) in existing and not replace_existing:
            logger.info(f"    Skipping {ticker_upper} {year} Q{quarter} (already exists)")
            continue

        if replace_existing and (year, quarter) in existing:
            cur.execute(
                "DELETE FROM transcript_chunks WHERE ticker = %s AND year = %s AND quarter = %s",
                (ticker_upper, year, quarter)
            )

        summary = build_quarter_summary(ticker_upper, info, quarterly_data, year, quarter)
        if not summary or len(summary.strip()) < 100:
            logger.warning(f"    Insufficient data for {ticker_upper} Q{quarter} {year}, skipping")
            continue

        # Generate embedding
        embedding = model.encode(summary, normalize_embeddings=True).tolist()

        metadata = {
            "source": "yfinance",
            "ticker": ticker_upper,
            "year": year,
            "quarter": quarter,
            "quarter_end_date": qdata.get("quarter_end_date", ""),
            "revenue": qdata.get("revenue"),
            "net_income": qdata.get("net_income"),
            "company_name": info.get("longName", ticker_upper),
            "sector": info.get("sector", ""),
        }

        cur.execute("""
            INSERT INTO transcript_chunks
                (chunk_text, embedding, metadata, ticker, year, quarter, chunk_index)
            VALUES (%s, %s::vector, %s, %s, %s, %s, %s)
        """, (
            summary,
            f"[{','.join(str(x) for x in embedding)}]",
            json.dumps(metadata),
            ticker_upper,
            year,
            quarter,
            0,
        ))
        rows_inserted += 1
        logger.info(f"    Inserted {ticker_upper} {year} Q{quarter}")

    conn.commit()
    return rows_inserted


def main():
    parser = argparse.ArgumentParser(description="Ingest yfinance quarterly data as transcript_chunks")
    parser.add_argument("--ticker", type=str, help="Single ticker")
    parser.add_argument("--tickers", type=str, nargs="+", help="Multiple tickers")
    parser.add_argument("--ticker-file", type=str, default="tickers.txt", help="File with one ticker per line (default: tickers.txt in same directory)")
    parser.add_argument("--lookback-quarters", type=int, default=8, help="Quarters to look back (default 8 = 2 years). Ignored if --start-quarter is provided")
    parser.add_argument("--start-quarter", type=str, help="Start quarter as 'Q1 2023' (inclusive). Overrides --lookback-quarters")
    parser.add_argument("--end-quarter", type=str, help="End quarter as 'Q4 2025' (inclusive). Defaults to today if --start-quarter provided")
    parser.add_argument("--replace", action="store_true", help="Replace existing data")

    args = parser.parse_args()

    # Parse quarter strings if provided
    start_year, start_q = None, None
    end_year, end_q = None, None

    if args.start_quarter:
        try:
            start_year, start_q = parse_quarter_str(args.start_quarter)
            logger.info(f"Using explicit start quarter: {start_year} Q{start_q}")
        except ValueError as e:
            logger.error(f"Invalid --start-quarter: {e}")
            sys.exit(1)

    if args.end_quarter:
        try:
            end_year, end_q = parse_quarter_str(args.end_quarter)
            logger.info(f"Using explicit end quarter: {end_year} Q{end_q}")
        except ValueError as e:
            logger.error(f"Invalid --end-quarter: {e}")
            sys.exit(1)

    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.ticker_file and os.path.exists(args.ticker_file):
        tickers = [l.strip().upper() for l in open(args.ticker_file) if l.strip()]
        logger.info(f"Loaded {len(tickers)} tickers from {args.ticker_file}")
    else:
        # Try reading from script directory
        script_dir = Path(__file__).parent
        ticker_file_path = script_dir / args.ticker_file
        if ticker_file_path.exists():
            tickers = [l.strip().upper() for l in open(ticker_file_path) if l.strip()]
            logger.info(f"Loaded {len(tickers)} tickers from {ticker_file_path}")
        else:
            parser.print_help()
            logger.error(f"No tickers provided and ticker file not found: {ticker_file_path}")
            sys.exit(1)

    logger.info(f"Loading embedding model {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    db_url = os.getenv("PG_VECTOR") or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("No database URL found. Set PG_VECTOR or DATABASE_URL.")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    ensure_transcript_chunks_table(cur)
    conn.commit()

    total_inserted = 0
    for i, ticker in enumerate(tickers, 1):
        logger.info(f"[{i}/{len(tickers)}] Processing {ticker}...")
        try:
            n = ingest_ticker(ticker, conn, model,
                              lookback_quarters=args.lookback_quarters,
                              replace_existing=args.replace,
                              start_year=start_year, start_quarter=start_q,
                              end_year=end_year, end_quarter=end_q)
            logger.info(f"  {ticker}: {n} quarters inserted")
            total_inserted += n
            time.sleep(0.5)  # Light rate limiting between tickers
        except Exception as e:
            logger.error(f"  {ticker} failed: {e}")
            conn.rollback()

    conn.close()
    logger.info(f"\nDone! Total quarters inserted: {total_inserted} across {len(tickers)} tickers")


if __name__ == "__main__":
    main()
