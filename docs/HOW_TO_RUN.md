# AlphaLens — How to Run

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Supabase project (free tier is fine)
- At least one LLM API key: Cerebras **or** OpenAI

---

## 1. Clone and configure

```bash
git clone https://github.com/swapnil18800/alphalens.git
cd alphalens
cp .env.example .env
```

Edit `.env` — minimum required keys:

```env
# LLM (one of these)
CEREBRAS_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Supabase
DATABASE_URL=postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres

# Auth (set true to skip Clerk for local dev)
AUTH_DISABLED=true
```

---

## 2. Backend setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. Database schema

Apply the schema to your Supabase project:

```bash
python scripts/setup_db.py
```

This creates: `ten_k_chunks`, `transcript_chunks`, `sessions`, `messages`, `users` tables + ivfflat indexes.

---

## 4. Ingest data (one-time)

### SEC 10-K filings (free, no API key needed)

```bash
# Default: top 25 tickers, 2022-2023
python scripts/ingest_sec_filings.py

# Custom tickers / years
python scripts/ingest_sec_filings.py --tickers NVDA MSFT AAPL --years 2023 2024
```

Duration: ~10–20 min for 25 tickers.

### Earnings transcripts (costs API Ninjas credits)

```bash
# Default: 20 tickers × 2 years = 160 calls (5% of 3000/month limit)
python scripts/download_transcripts.py

# Then embed and store
python scripts/create_embeddings.py
```

### Stock screener data (free, uses yfinance)

```bash
python scripts/build_screener_db.py
```

Creates `agent/screener/financial_data.duckdb` (~50 MB).

---

## 5. Run the backend

```bash
uvicorn app:app --reload --port 8000
```

Test: `curl http://localhost:8000/health`

---

## 6. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend starts at `http://localhost:5173`. The Vite dev proxy forwards all `/api`, `/ws`, and `/health` requests to the backend at port 8000.

---

## 7. Verify end-to-end

1. Open `http://localhost:5173`
2. Click **Launch App**
3. Ask: *"What are NVDA's key risk factors?"*
4. You should see a streamed response with citations

---

## Optional: LangFuse observability

```env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

Then open your LangFuse project to see traces for every graph run.

---

## Optional: RAGAS evaluation

After data ingestion, run the offline eval suite:

```bash
python evals/run_ragas.py
```

Results (faithfulness, relevancy, precision, recall) are saved to `evals/results.json`.

---

## Environment variables reference

See `.env.example` for the full list with descriptions.

---

## Production (Railway)

1. Push to GitHub
2. Connect repo to Railway
3. Set all env vars in Railway dashboard
4. Railway uses the `Procfile` automatically: `uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1`
5. Frontend is served from `frontend/dist` (built during deploy via `nixpacks.toml` or `railway.toml`)

See `docs/STAGES.md` for a phased deployment roadmap.
