# Data Ingestion & Audit Guide

All DB-related scripts live under `db/`.

---

## 1. Setup — Schema & pgvector

Run once on a fresh database. Applies `db/schema.sql` which creates all tables, enables pgvector, and creates ivfflat indexes:

```bash
python db/setup_db.py
```

The schema already includes:
- `CREATE EXTENSION IF NOT EXISTS vector` (pgvector)
- `embedding vector(384)` on `ten_k_chunks` and `transcript_chunks`
- `ivfflat (lists=100)` indexes on both tables

If you need to enable pgvector separately (e.g., new Supabase project before schema is applied):

```bash
python db/setup_pgvector_supabase.py
```

Or paste `db/schema.sql` directly into the Supabase SQL Editor and run it.

---

## 2. SEC 10-K Ingestion

Downloads 10-K filings from SEC EDGAR, chunks prose + tables, embeds with `all-MiniLM-L6-v2`, stores in `ten_k_chunks`.

```bash
# All tickers in db/ingestion/tickers.txt, FY2023–2025
python db/ingestion/ingest_sec.py --start-year 2023 --end-year 2025 --replace

# Specific tickers only
python db/ingestion/ingest_sec.py --tickers NVDA AAPL MSFT --start-year 2023 --end-year 2025 --replace

# All 25 default tickers (hardcoded TOP_25 list in script)
python db/ingestion/ingest_sec.py --all --start-year 2023 --end-year 2025 --replace
```

**Key parameters:**
- `--start-year` / `--end-year`: Filing year range (inclusive). A filing year = year the 10-K was filed, not the fiscal year end.
- `--replace`: Delete existing chunks for each ticker before re-ingesting. Required to avoid duplicates on re-runs.
- `--tickers`: Override ticker list. Defaults to reading `db/ingestion/tickers.txt`.

**Chunking:** 1400-char sliding window, 200-char overlap, separate chunks for HTML tables.  
**Logs:** `db/ingestion/logs/sec_10k/sec_YYYYMMDD_HHMMSS.log`

---

## 3. Earnings Transcript Ingestion

Scrapes earnings call transcripts from StockAnalysis.com, chunks, embeds, stores in `transcript_chunks`.

```bash
# All 27 default tickers, 2023–2026
python db/ingestion/ingest_stockanalysis.py --replace

# Specific tickers and/or years
python db/ingestion/ingest_stockanalysis.py --tickers NVDA MSFT --years 2024 2025 --replace
```

**Key parameters:**
- `--tickers`: Override default list of 27 tickers.
- `--years`: Fiscal years to include (default: 2023 2024 2025 2026). Space-separated.
- `--replace`: Delete existing `stockanalysis`-sourced rows before re-inserting.

**Coverage:** Q1 2023 – Q4 2026 (varies by company; fiscal year offsets apply for NVDA, MSFT, CRM, etc.).  
**Logs:** `db/ingestion/logs/transcripts_stockanalysis/sa_YYYYMMDD_HHMMSS.log`

---

## 4. Generate Audit Report

After ingestion, run the audit script to generate a markdown report with coverage stats, vector counts, and data quality notes:

```bash
python db/generate_data_audit.py
```

Output: `docs/DATA_AUDIT_SUPABASE_INGESTION_2026.md`

The report includes:
- Total chunks and vector coverage (% embedded) for both tables
- Per-ticker, per-year chunk counts for 10-K
- Per-ticker quarterly coverage for transcripts
- Section distribution (ITEM 1, ITEM 1A, etc.)
- Known gaps and data quality notes

---

## 5. Monitoring Ingestion Progress

```bash
# SEC logs (live tail)
tail -f db/ingestion/logs/sec_10k/sec_*.log | grep -E "Downloaded|Stored|done"

# Transcript logs (live tail)
tail -f db/ingestion/logs/transcripts_stockanalysis/sa_*.log | grep -E "done|chunks"

# Check for errors
grep -i "ERROR\|WARNING" db/ingestion/logs/*/*.log
```

**Windows (find running Python processes):**
```powershell
Get-Process python | Select-Object Id, @{Name='MB';Expression={[math]::Round($_.WorkingSet/1MB)}}
```

---

## 6. Tickers Covered

Edit `db/ingestion/tickers.txt` to change the default ticker list for `ingest_sec.py`.

Current default (`ingest_stockanalysis.py` has its own `DEFAULT_TICKERS` list of 27):

| Category | Tickers |
|----------|---------|
| Tech/Cloud | AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD, INTC, CRM, ORCL, ADBE, QCOM, NFLX, UBER |
| Semiconductors | AVGO, LRCX, AMAT, MU, KLAC, TXN |
| SaaS/Data | SNOW, PLTR, PANW, NOW, IBM, CSCO, PYPL |
| Financial (10-K only) | BAC, GS, JPM, V |

---

## 7. Known Anomalies

| Issue | Detail |
|-------|--------|
| SMCI FY2024 | No 10-K filed on EDGAR (accounting scandal). Two filings under FY2025 in DB. |
| TSLA/NFLX Q1-2026 | 1-chunk stub only — transcript not published at ingestion time. |
| PYPL Q3/Q4-2024 | Were missing due to network timeout; fixed on re-ingest. |
| KLAC transcripts | Not on StockAnalysis; 10-K data present, transcripts excluded. |
| Fiscal year offsets | NVDA Jan 31, MSFT Jun 30, CRM Jan 31 — `filing_year` = year filed, not FY end. |
