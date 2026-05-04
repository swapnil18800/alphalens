# AlphaLens — Development Roadmap by Stage

This is a phased guide for what to build, test, and deploy at each stage. You can move at your own pace; each stage is self-contained.

---

## Stage 1: Local Dev + Core RAG (2–3 days)

**Goal:** Get the full stack running locally with real data and end-to-end chat working.

### Checklist
- [ ] Clone repo, install Python + Node deps
- [ ] Configure `.env` with at least one LLM key (Cerebras or OpenAI)
- [ ] Set up Supabase account, update `DATABASE_URL`
- [ ] Run `scripts/setup_db.py` to create schema
- [ ] Run `scripts/ingest_sec_filings.py` (default 25 tickers)
- [ ] Run `scripts/create_embeddings.py` if ingesting transcripts
- [ ] Start backend: `uvicorn app:app --reload`
- [ ] Start frontend: `npm run dev` in `frontend/`
- [ ] Open http://localhost:5173, click "Launch App", ask about NVDA
- [ ] Verify chat response, citations, and confidence badge appear

**Testing:** Chat endpoint works; embeddings are searchable; LLM responds correctly.

---

## Stage 2: Observability + Evaluation (1–2 days)

**Goal:** Add LangFuse tracing and RAGAS eval suite so you can demo production-readiness.

### Checklist
- [ ] Sign up for LangFuse (https://langfuse.com), create project
- [ ] Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` to `.env`
- [ ] Restart backend
- [ ] Run a chat query and verify trace appears in LangFuse dashboard (check latency, token counts)
- [ ] Review `evals/test_dataset.json` — 10 gold Q&A pairs
- [ ] Run `python evals/run_ragas.py`
- [ ] Open `evals/results.json` — verify faithfulness, relevancy, precision scores
- [ ] Add results screenshot to LinkedIn/GitHub as proof of SOTA evaluation

**Testing:** Every graph node is traced; RAGAS scores are reproducible and > 0.7 on faithfulness.

---

## Stage 3: Screener + Data Enrichment (1–2 days)

**Goal:** Stock screener works end-to-end; Companies page is searchable.

### Checklist
- [ ] Run `scripts/build_screener_db.py` — creates `agent/screener/financial_data.duckdb`
- [ ] Unlock Companies page in `frontend/src/components/Sidebar.tsx` (set `disabled: false`)
- [ ] Unlock Screener page in the same file
- [ ] Test Companies page: search for "NVDA", click a company, verify chat opens
- [ ] Test Screener page: ask "Show tech companies with PE under 25"
- [ ] Verify generated SQL in result and table output
- [ ] (Optional) Add more financial columns to screener — edit `scripts/build_screener_db.py`

**Testing:** Screener returns correct SQL and results; Companies search is fast.

---

## Stage 4: Auth + Multi-User Sessions (1–2 days)

**Goal:** Users can sign up, save chat history, and revisit conversations.

### Checklist
- [ ] Set `AUTH_DISABLED=false` in `.env`
- [ ] Sign up for Clerk (https://clerk.com), create application
- [ ] Add `CLERK_SECRET_KEY` to backend `.env`
- [ ] Add `VITE_CLERK_PUBLISHABLE_KEY` to `frontend/.env`
- [ ] Restart both backend and frontend
- [ ] Sign up a test account in the app (Clerk UI appears automatically)
- [ ] Create a chat session, ask a question, close browser
- [ ] Sign in again, verify previous session appears in sidebar
- [ ] Click old session, verify chat history is restored

**Testing:** Auth flow works; sessions persist; history is per-user.

---

## Stage 5: Deployment to Railway (1 day)

**Goal:** App is live and shareable; stop running local dev.

### Checklist
- [ ] Commit and push to GitHub
- [ ] Create Railway account (https://railway.app), connect GitHub repo
- [ ] Add all env vars in Railway dashboard (DATABASE_URL, LLM keys, Langfuse, Clerk)
- [ ] Trigger deploy (automatic on push or manual via dashboard)
- [ ] Wait for build to complete (~3–5 min)
- [ ] Test `/health` endpoint on deployed domain
- [ ] Test full chat flow in deployed app
- [ ] Share app URL with friends / post on LinkedIn

**Testing:** Cold start completes in < 2 min; chat latency < 5 sec for typical queries.

---

## Stage 6: Polish + Extras (optional, 1–2 days)

**Goal:** Delight users with UX and features that impress recruiters.

### Ideas
- [ ] Add real-time chart of stock price during chat (via yfinance API)
- [ ] Dark mode toggle (Tailwind already supports `dark:`)
- [ ] Export chat as PDF (use `pdfkit` Python lib)
- [ ] Multi-company comparison view
- [ ] Saved "watchlists" of favorite companies
- [ ] API endpoint for programmatic access (no UI needed, just FastAPI)
- [ ] Add code-syntax highlighting to LLM responses (use `react-syntax-highlighter`)
- [ ] Streaming answer text (parse SSE from backend WebSocket)

**Testing:** Features don't break existing chat; performance stays snappy.

---

## Metrics for Success

By end of Stage 2, you have:
- ✅ Working chat with citations
- ✅ RAGAS eval scores > 0.7 (proof of quality)
- ✅ Full LangFuse trace (proof of SOTA observability)

By end of Stage 5, you have:
- ✅ Live deployed app (proof of fullstack competence)
- ✅ Multi-user auth (proof of production-readiness)

These three things together make a strong GenAI portfolio project for recruiting.

---

## Troubleshooting

**Chat returns "out of scope"?**  
→ The query analysis node thinks it's not a finance question. Check the system prompt in `agent/rag/prompts.py:ANALYSIS_SYSTEM`.

**Search returns no results?**  
→ No data ingested. Run `scripts/ingest_sec_filings.py` with your target tickers.

**LLM response is slow?**  
→ Cerebras key missing or invalid. Check `.env` and `CEREBRAS_API_KEY`. Falls back to OpenAI which is slower.

**LangFuse trace missing?**  
→ Keys not set. Either set them and restart, or leave unset (graceful no-op).

**Clerk sign-up not appearing?**  
→ `AUTH_DISABLED=true` in `.env`. Set to `false` and ensure `VITE_CLERK_PUBLISHABLE_KEY` is in `frontend/.env`.

**Screener returns "Internal Server Error"?**  
→ DuckDB file not built. Run `scripts/build_screener_db.py`.
