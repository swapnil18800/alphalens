# AlphaLens — Build, Data Ingestion & Test Order

This document is the definitive runbook. Follow steps in order. Each step has a
verification command so you know it worked before moving to the next.

---

## Prerequisites

```
Python 3.11    python --version
Node.js 18+    node --version
Git            git --version
Railway CLI    railway --version   (npm install -g @railway/cli)
```

---

## ⚠️ Step 0 — Create a New Railway PostgreSQL Database

> Do this BEFORE running any scripts. AlphaLens needs its own DB separate from finance-agent.

1. Go to [railway.app](https://railway.app) → your project (or create a new one)
2. Click **+ New** → **Database** → **PostgreSQL**
3. Wait ~60 seconds for provisioning
4. Click the PostgreSQL service → **Variables** tab
5. Copy the `DATABASE_URL` value — it looks like:
   ```
   postgresql://postgres:randompassword@roundhouse.proxy.rlwy.net:PORT/railway
   ```
6. Paste it into your `.env`:
   ```
   DATABASE_URL=postgresql://postgres:...@...railway.internal:5432/railway
   ```

> Railway PostgreSQL includes pgvector pre-installed — no manual `CREATE EXTENSION` needed.
> If you use **Supabase** instead: go to SQL Editor → run `CREATE EXTENSION IF NOT EXISTS vector;`

---

## Step 1 — Clone & Environment Setup

```bash
cd C:\Users\HP\Desktop\ai-projects\alphalens

# Create and activate virtual env
python -m venv venv
venv\Scripts\activate        # Windows

# Install dependencies (~3-5 min — sentence-transformers downloads PyTorch)
pip install -r requirements.txt
```

**Verify:**
```bash
pip list | findstr "fastapi langgraph sentence-transformers rank-bm25"
# Expected: all four shown with version numbers
```

---

## Step 2 — Configure Environment

```bash
copy .env.example .env
# Open .env and fill in:
#   DATABASE_URL   ← from Step 0
#   CEREBRAS_API_KEY
#   OPENAI_API_KEY
#   TAVILY_API_KEY  (optional)
#   JWT_SECRET_KEY  ← generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Step 3 — Initialize Database Schema

```bash
python scripts/setup/setup_db.py
```

**Expected output:**
```
INFO Connecting to database...
INFO Running schema: db/schema.sql
INFO Schema applied successfully
INFO Tables present: ['eval_logs', 'messages', 'semantic_cache', 'sessions', 'ten_k_chunks', 'transcript_chunks', 'users']
```

**If pgvector error:** Go to your Railway DB → Connect → run `CREATE EXTENSION IF NOT EXISTS vector;`

---

## Step 4 — Minimal Data Ingestion (for local testing, ~10 min)

Ingest just 3 tickers to verify the full pipeline works before ingesting everything.

### 4a. yfinance quarterly summaries (fast, ~2 min)
```bash
python scripts/ingestion/ingest_yfinance.py --tickers NVDA AAPL MSFT --lookback-quarters 8
```

**Expected:** ~15 rows inserted (5 quarters × 3 tickers)

**Verify:**
```bash
python -c "
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()
async def check():
    c = await asyncpg.connect(os.getenv('DATABASE_URL'))
    n = await c.fetchval('SELECT COUNT(*) FROM transcript_chunks')
    tickers = await c.fetch('SELECT DISTINCT ticker FROM transcript_chunks')
    print(f'transcript_chunks: {n} rows, tickers: {[r[0] for r in tickers]}')
    await c.close()
asyncio.run(check())
"
```

### 4b. SEC 10-K filings (slower, ~5-10 min for 3 tickers)
```bash
python scripts/ingestion/ingest_sec.py --tickers NVDA AAPL MSFT --years 2
```

**Expected:** ~900-1500 chunks inserted (300-500 per ticker)

**Verify:**
```bash
python -c "
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()
async def check():
    c = await asyncpg.connect(os.getenv('DATABASE_URL'))
    n = await c.fetchval('SELECT COUNT(*) FROM ten_k_chunks')
    tickers = await c.fetch('SELECT DISTINCT ticker FROM ten_k_chunks')
    print(f'ten_k_chunks: {n} rows, tickers: {[r[0] for r in tickers]}')
    await c.close()
asyncio.run(check())
"
```

---

## Step 5 — Start Backend & Smoke Test

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

**Watch for:**
```
INFO [startup] BM25 corpus ready              ← hybrid search active
INFO [startup] LangGraph research graph ready
INFO [startup] AlphaLens is ready → http://localhost:8000
```

**Basic health check:**
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy"}
```

---

## Step 6 — Run Fast API Tests (no LLM calls)

```bash
python tests/api/test_apis.py
```

**Expected:** 4-5 tests pass: health, companies, conversations, db_coverage, hybrid_search

---

## Step 7 — Test LangGraph Pipeline End-to-End

```bash
python tests/api/test_apis.py --all
```

This runs slow tests that call Cerebras/OpenAI. Expect ~30-60s per test.

**Minimum passing criteria:**
- `[PASS] Received streaming events`
- `[PASS] Got a result event`
- `[PASS] Answer mentions revenue figure`

If RAG returns empty: re-check Step 4 — data must be in the DB the `DATABASE_URL` points to.

---

## Step 8 — Frontend

```bash
cd frontend
npm install
npm run dev        # dev server at http://localhost:5173
```

Or build for production (Railway serve):
```bash
npm run build
cd ..
```

**Test:** Open `http://localhost:5173`, click "Launch App", ask: *"What are NVDA's risk factors?"*

---

## Step 9 — Full Data Ingestion (all 28 tickers, ~30-60 min)

Only run this after Step 7 confirms the pipeline works.

```bash
# Transcripts: all 28 tickers (~5 min total, yfinance is fast)
python scripts/ingestion/ingest_yfinance.py --ticker-file data/tickers.txt --lookback-quarters 8

# 10-K filings: all 28 tickers (~30-60 min, EDGAR rate-limited)
python scripts/ingestion/ingest_sec.py --all
```

**Data copy from finance-agent DB (alternative to re-ingesting):**

If you want to copy data from finance-agent's Railway DB instead of re-ingesting:
```bash
# 1. Dump 3 test tickers from finance-agent DB (ask for finance-agent DATABASE_URL first)
pg_dump "$FINANCE_AGENT_DATABASE_URL" \
  -t ten_k_chunks -t transcript_chunks \
  --data-only \
  -f /tmp/finance_agent_data.sql

# 2. Filter to just 3 tickers (saves time)
grep -E "(NVDA|AAPL|MSFT)" /tmp/finance_agent_data.sql > /tmp/test_tickers.sql

# 3. Load into alphalens DB
psql "$DATABASE_URL" -f /tmp/test_tickers.sql
```

> **Recommendation:** Re-ingest from yfinance + EDGAR instead of copying. Both are free, yfinance 
> takes 5 min for 28 tickers, and you avoid DB compatibility issues between Railway instances.

---

## Step 10 — Run RAGAS Evaluation

```bash
python scripts/eval/run_ragas.py
# Results saved to evals/results/ragas_YYYY-MM-DD.csv
```

**Target scores:**
- `faithfulness` ≥ 0.65
- `context_precision` ≥ 0.60

---

## Step 11 — Deploy to Railway

```bash
# Commit built frontend (Railway serves it as static)
cd frontend && npm run build && cd ..
git add frontend/dist
git commit -m "Build frontend for Railway deployment"
git push origin main
```

In Railway dashboard:
1. **New Service** → **Deploy from GitHub repo** → select `alphalens`
2. **Variables** tab → paste all `.env` values (use Railway's Raw Editor)
3. Watch **Deployments** → **View Logs** for `AlphaLens is ready`
4. Verify: `curl https://your-app.up.railway.app/health`

---

## LLM Inference Flow (for reference)

```
User question
    │
    ▼
[Node 1: analyze_question]
  LLM (Cerebras/OpenAI) extracts:
    - tickers (e.g. ["NVDA"])
    - intent (e.g. "revenue")
    - sub_questions
    - is_out_of_scope
    │
    ├─ out_of_scope → [finalize_early] → reply
    │
    ▼
[Node 2: execute_search]  ← also used on retry
  1. Embed query → all-MiniLM-L6-v2 (384-dim, CPU)
  2. Check semantic_cache (cosine ≥ 0.92) → if HIT, skip
  3. pgvector ANN search → top-24 chunks from ten_k_chunks
  4. pgvector ANN search → top-24 chunks from transcript_chunks
  5. BM25 search (in-memory rank_bm25) → top-24 per source
  6. RRF merge (1/(60+rank)) per source
  7. Cross-encoder rerank (ms-marco-TinyBERT) → top-8 per source
  8. Optionally Tavily news search
    │
    ▼
[Node 3: generate_response]
  LLM (Cerebras/OpenAI) synthesizes answer from top-8+8+5 chunks
  Returns: answer text + [SEC-TICKER-YEAR] / [Q#-YEAR-TICKER] citations
    │
    ▼
[Node 4: evaluate_response]
  LLM-as-judge (OpenAI) scores faithfulness 0.0–1.0
  Returns: eval_score, eval_reason
    │
    ├─ score ≥ 0.65 or iter ≥ 2 → [finalize] → return to user
    │
    └─ score < 0.65 → [query_rewriter]
                          LLM rewrites query with synonyms
                          → back to [execute_search] (iter++)
```

**Typical latency:**
- Cache HIT: ~200ms
- Cold pipeline: ~8-15s (Cerebras fast, OpenAI fallback ~15-25s)
- With reranking: +1-2s on CPU

---

## Data Ingestion Flow (for reference)

```
yfinance (free, no key)
    │
    ▼
scripts/ingestion/ingest_yfinance.py
  - yf.Ticker(ticker).quarterly_income_stmt
  - build_quarter_summary() → rich text per quarter
    (revenue, gross margin, EPS, YoY change, company overview)
  - all-MiniLM-L6-v2 encode → 384-dim vector
  - INSERT INTO transcript_chunks (chunk_text, embedding, metadata, ticker, year, quarter)
  - ~5 quarters per ticker, ~2 min for 28 tickers

SEC EDGAR (free, no key)
    │
    ▼
scripts/ingestion/ingest_sec.py
  - GET https://data.sec.gov/submissions/CIK{ticker}.json → find 10-K accession numbers
  - Download .htm file → strip HTML → 200k chars max
  - Chunk: 800 tokens, 150 overlap
  - all-MiniLM-L6-v2 encode → 384-dim vector
  - INSERT INTO ten_k_chunks (ticker, filing_year, embedding, chunk_text)
  - ~300-1500 chunks per ticker, ~5-10 min per ticker (EDGAR rate-limited)
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: DB pool not initialized` | DATABASE_URL missing or wrong | Check `.env`, re-run `setup_db.py` |
| `pgvector extension not found` | pgvector not enabled | Railway: automatic; Supabase: `CREATE EXTENSION IF NOT EXISTS vector;` |
| BM25 corpus empty at startup | No data in DB yet | Run ingestion first (Step 4) |
| `CEREBRAS_API_KEY not set` | Missing key | Add to `.env`; LLM_PROVIDER=openai as fallback |
| Cross-encoder import error | sentence-transformers version | `pip install sentence-transformers>=3.4.0` |
| `rank_bm25` import error | Missing package | `pip install rank-bm25` |
| RAG returns "no data found" | DB has data but wrong DATABASE_URL | Confirm both `.env` and Railway vars point to same DB |
| CORS error in browser | Missing origin in CORS_ORIGINS | Set `CORS_ORIGINS=https://your-app.up.railway.app` in Railway vars |
