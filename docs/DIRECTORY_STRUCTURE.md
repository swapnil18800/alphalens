# AlphaLens — Directory Structure

> Last updated to reflect commits through `a811cb7` (May 2026): Supabase migration, Clerk auth wiring, SVG diagrams, new frontend components, logos, website screenshots, and ingestion scripts reorganized under `db/`.

---

## Full Tree

```
alphalens/
│
├── agent/                              # Core AI / RAG engine
│   ├── graph/                          # LangGraph state machine (state.py, nodes.py, edges.py, graph.py)
│   ├── llm/                            # LLM providers: deepseek, cerebras, openai (factory.py, token_tracker.py)
│   └── rag/                            # RAG pipeline: search_engine.py, database_manager.py, response_generator.py, prompts.py
│
├── app/                                # FastAPI application
│   ├── auth/                           # Clerk JWT verification (clerk.py)
│   ├── routers/                        # API routes: health.py, chat.py, sessions.py
│   ├── utils/                          # Helpers: database.py, logging.py
│   ├── websocket/                      # WS handler, manager, routes
│   ├── __init__.py                     # App factory + middleware + static mounts
│   ├── lifespan.py                     # Startup/shutdown: pool, graph, ML warmup, BM25 index
│   └── middleware.py                   # CORS, request logging
│
├── db/                                 # Database schema + ingestion
│   ├── schema.sql                      # CREATE TABLE + pgvector + IVFFlat indexes
│   ├── setup_db.py                     # Apply schema to Supabase
│   ├── setup_pgvector_supabase.py      # Enable pgvector extension
│   ├── generate_data_audit.py          # Generate live data audit markdown
│   ├── migrations/                     # Migration scripts (Railway → Supabase)
│   └── ingestion/                      # ingest_sec.py, ingest_stockanalysis.py, tickers.txt, logs/
│
├── scripts/                            # Utility scripts
│   ├── eval/                           # run_ragas.py — lightweight RAGAS runner
│   └── logos/                          # 4× logo download scripts (company + stack logos)
│
├── evals/qa_eval/                      # Evaluation harness (M1–M8 metrics)
│   ├── run_eval.py                     # Compute metrics on question sets
│   ├── generate_ground_truth.py        # GPT-4o ground truth synthesis
│   ├── question_v*.txt                 # Question sets (v3, v4, ....)
│   ├── EVAL_WORKFLOW_GUIDE.md          # Eval workflow reference
│   ├── results/                        # Per-run outputs: <timestamp>/ with JSON + MD analysis
│   ├── docs/                           # Historical eval docs (9 improvement summary files)
│   └── logs/                           # Eval execution logs
│
├── frontend/                           # React 18 SPA (Vite + TypeScript + Tailwind)
│   ├── src/
│   │   ├── pages/                      # LandingPage.tsx, ChatPage.tsx
│   │   ├── components/                 # Sidebar, ChatMessage, ChatInput, ReasoningTrace, AuthModal, etc.
│   │   ├── hooks/                      # useAuthStatus.ts, useAnonId.ts
│   │   ├── lib/                        # api.ts (WS/fetch types), config.ts
│   │   ├── main.tsx                    # Entry point
│   │   ├── App.tsx                     # Routes
│   │   └── index.css                   # Tailwind + utility classes
│   ├── public/logos/                   # 25 company SVG logos (AAPL, NVDA, MSFT, ...)
│   ├── vite.config.ts                  # Dev proxy to :8000
│   ├── tailwind.config.js, tsconfig.json, package.json
│   └── index.html                      # SPA shell
│
├── assets/                             # Static assets
│   ├── architecture-overview.svg, langgraph-pipeline.svg, rag-pipeline.svg  # Mermaid diagrams
│   ├── logos/                          # 25 company SVG logos (symlink from frontend/public/logos)
│   ├── stack_logos/                    # 14 tech stack logos (PNG + SVG): DeepSeek, Cerebras, OpenAI, Supabase, etc.
│   ├── website-ss/                     # 7 production screenshots (landing, auth, chat, citations, etc.)
│   └── traces/                         # LangSmith trace visualization PNGs (web, finalize-early, retry)
│
├── tests/                              # Test suite
│   ├── api/                            # REST endpoint tests
│   ├── db/                             # DB tests (Supabase, legacy Railway tests)
│   └── tracing/                        # LangSmith end-to-end test (test_langsmith_trace.py, traces/)
│
├── docs/                               # Documentation
│   ├── ARCHITECTURE.md                 # System design, diagrams, component map
│   ├── DIRECTORY_STRUCTURE.md          # This file
│   ├── RAG_MODEL_PIPELINE.md           # Detailed RAG: models, prompts, search, chunking
│   ├── EVALUATION_RESULTS.md           # Complete eval history (0.546 → 0.784)
│   ├── evaluation_summary.md           # Blog-style eval writeup
│   ├── DATA_AUDIT_SEC_TRANSCRIPTS.md   # Coverage heatmap (33 tickers)
│   ├── DATA_INGESTION.md               # Ingestion workflow
│   ├── HOW_TO_RUN.md                   # Setup + deployment
│   ├── websocket_protocol.md, backend.md, frontend.md # Reference docs
│   └── REFERENCE_REPOS_ANALYSIS.md  # Historical reference
│
├── logs/                               # .gitkeep (runtime logs)
├── config.py                           # Pydantic Settings
├── requirements.txt                    # Python dependencies
├── nixpacks.toml                       # Railway build config
├── .env.example, .env, .gitignore
├── CLAUDE.md                           # Claude Code instructions
├── Procfile                            # Railway entrypoint
└── railway.toml                        # Railway health check
```

---

## Key Relationships & Data Flow

### App Initialization (FastAPI Startup)

```
app/__init__.py
  │ creates FastAPI instance
  ├─ mounts /logos → assets/logos/ (company SVGs)
  ├─ mounts /stack_logos → assets/stack_logos/
  ├─ registers middleware (CORS, logging)
  ├─ registers routers (health, chat, sessions, ws)
  └─ production catch-all → serves frontend/dist/index.html

app/lifespan.py (startup event)
  ├─ create asyncpg pool (2–10 connections to Supabase)
  ├─ agent/rag/database_manager.py:set_pool(pool)
  ├─ agent/graph/graph.py:build_graph() → compile LangGraph singleton
  └─ background tasks:
       ├─ warm all-MiniLM-L6-v2 embedding model
       ├─ warm ms-marco-TinyBERT-L-2-v2 cross-encoder
       └─ load all chunk text from DB → build BM25 index in memory
```

### Request Flow (WebSocket Query)

```
Browser → WebSocket /ws
  └─ app/websocket/routes.py
       └─ app/websocket/handler.py
            ├─ parse {type:"query", query, web_search, session_id}
            ├─ load conversation history from DB
            ├─ emit {type:"status"} updates via _status_callback
            └─ agent/graph/graph.py:run(ResearchState)
                 │
                 ├─ plan_search (nodes.py:node_analyze_question)
                 │   → LLM extracts tickers, intent, sub-questions, query_mode
                 │   → streams sub-questions as tokens to browser
                 │
                 ├─ retrieve_context (nodes.py:node_execute_search)
                 │   → agent/rag/search_engine.py:hybrid_search()
                 │       ├─ semantic cache check (cosine ≥ 0.92)
                 │       ├─ embed query: all-MiniLM-L6-v2
                 │       ├─ pgvector ANN → agent/rag/database_manager.py
                 │       ├─ BM25 keyword search (in-memory index)
                 │       ├─ RRF fusion (k=60) + dedup
                 │       ├─ cross-encoder rerank (TinyBERT)
                 │       ├─ table boost injection (top-4 table chunks)
                 │       └─ optional Tavily web search
                 │
                 ├─ generate_answer (nodes.py:node_generate_response)
                 │   → agent/rag/response_generator.py
                 │       ├─ format_chunks() — round-robin by ticker
                 │       ├─ build context window (6000 chars budget)
                 │       ├─ call agent/llm/factory.py:create()
                 │       └─ stream tokens via _token_callback → browser
                 │
                 ├─ evaluate_quality (nodes.py:node_evaluate_response)
                 │   → heuristic check (fast, no LLM)
                 │   → LLM judge (GPT-4o) if borderline 0.50–0.75
                 │   → track best_score across iterations
                 │
                 ├─ [if score < 0.65 and iter < 2]
                 │   rewrite_query → retrieve_context (retry loop)
                 │
                 └─ finalize (nodes.py:node_finalize)
                     → format final_answer with best citations

handler.py (post-graph)
  ├─ save session + messages to Supabase
  └─ post LangSmith trace (token counts + USD cost)

Browser receives: {type:"final", answer, confidence, citations}
```

### Data Ingestion Pipeline

```
db/setup_db.py
  └─ Apply db/schema.sql (CREATE TABLE + pgvector + IVFFlat indexes)

db/ingestion/ingest_sec.py
  ├─ Download 10-K filings from SEC EDGAR API
  ├─ 33 companies, FY2023–FY2025
  ├─ Chunk: 1400-char sliding window, 200-char overlap
  ├─ Detect tables: regex → chunk_type = "table"
  ├─ Embed: all-MiniLM-L6-v2 → vector(384)
  └─ INSERT → ten_k_chunks (Supabase)

db/ingestion/ingest_stockanalysis.py
  ├─ Scrape full earnings call transcripts from StockAnalysis.com
  ├─ 27 companies, Q1 2023–Q4 2026
  ├─ Same chunking + embedding pipeline
  └─ INSERT → transcript_chunks (Supabase)

db/generate_data_audit.py
  └─ Query live DB → write docs/DATA_AUDIT_SUPABASE_INGESTION_2026.md
```

### Evaluation Workflow

```
evals/qa_eval/generate_ground_truth.py --input question_vN.txt --full
  └─ For each question:
       ├─ Extract tickers via TICKER_MAP
       ├─ Query DB (pgvector + BM25, top-K chunks, no web)
       └─ GPT-4o → synthesize ground truth + 5 key facts
            → write back to question_vN.txt

evals/qa_eval/run_eval.py --full --input question_vN.txt
  └─ For each question:
       ├─ Run full LangGraph pipeline (same as production)
       ├─ Compute M1 (factual), M2 (RAGAS faithful), M3 (retrieval recall)
       ├─ Compute M4 (RAGAS context precision), M6 (routing), M7 (judge)
       └─ Write results/<timestamp>/ (per-Q JSON + _summary.json + _analysis.md)
```

---

## Notable File Changes Since Initial Commit

| Change | Commit | Details |
|--------|--------|---------|
| DB migrated to Supabase | `2bc596c` | `db/schema.sql`, `db/setup_db.py`, `db/setup_pgvector_supabase.py`, migration script added |
| Ingestion scripts moved | `2bc596c` | `scripts/ingestion/` → `db/ingestion/`; `data/tickers.txt` → `db/ingestion/tickers.txt` |
| Architecture SVG diagrams | `2bc596c` | `assets/architecture-overview.svg`, `assets/langgraph-pipeline.svg`, `assets/rag-pipeline.svg` |
| Company logos added | `2bc596c` + `1c59258` | `assets/logos/*.svg`, `frontend/public/logos/*.svg` |
| Stack logos added | `1c59258` | `assets/stack_logos/` (PNG + SVG for 14 tech tools) |
| Auth (Clerk) wired | `2bc596c` + `1c59258` | `app/auth/clerk.py`, `frontend/src/components/AuthModal.tsx`, `ProtectedRoute.tsx`, `useAnonId.ts` |
| Logo serving fixed | `64f0090` | FastAPI mounts `/logos` + `/stack_logos`; `frontend/dist/` removed from git |
| nixpacks.toml added | `2bc596c` + `9b7adde` | Railway nixpacks build config for Python 3.12 + Node.js |
| Website screenshots | `a811cb7` | `assets/website-ss/` (7 production screenshots) |
| Logo download scripts | `1c59258` | `scripts/logos/` (4 download utilities) |
| Supabase test files | `2bc596c` | `tests/db/test_supabase.py`, `tests/db/test_railway.py` |
| `docs/DATA_INGESTION.md` | `2bc596c` | New ingestion step-by-step guide |
| `db/generate_data_audit.py` | `2bc596c` | Auto-generate data audit from live Supabase DB |

---

## Component Isolation Summary

| Component | Role | Depends On |
|-----------|------|-----------|
| `app/` | HTTP + WebSocket server | `agent/`, `config.py` |
| `agent/graph/` | LangGraph orchestration | `agent/llm/`, `agent/rag/` |
| `agent/llm/` | LLM provider abstraction | DeepSeek / Cerebras / OpenAI APIs |
| `agent/rag/` | Hybrid search + context building | Supabase DB, sentence-transformers |
| `frontend/` | React SPA | REST + WebSocket from `app/` |
| `db/ingestion/` | One-time data pipeline | SEC EDGAR, StockAnalysis.com, Supabase |
| `evals/qa_eval/` | Quality measurement | Full LangGraph pipeline + GPT-4o |
| `scripts/logos/` | Logo download utilities | Logo CDNs (run once to populate `assets/`) |
| `assets/` | Static assets | Served by FastAPI in production |
