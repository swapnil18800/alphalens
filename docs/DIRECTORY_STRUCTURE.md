# AlphaLens — Directory Structure

```
alphalens/
│
├── agent/                          # Core AI/RAG engine (LangGraph orchestration)
│   ├── __init__.py
│   │
│   ├── graph/                      # LangGraph state machine & node definitions
│   │   ├── state.py                # ResearchState TypedDict — all graph state fields
│   │   ├── nodes.py                # 7 async node functions (plan, retrieve, generate, evaluate, rewrite, finalize, finalize_early)
│   │   ├── edges.py                # Conditional routing logic (route_after_analysis, route_after_evaluation)
│   │   └── graph.py                # build_graph() → compiled singleton; run() wrapper + LangSmith tracing
│   │
│   ├── llm/                        # LLM provider abstraction layer
│   │   ├── base.py                 # BaseLLMClient abstract class (astream, acomplete)
│   │   ├── deepseek_client.py      # DeepSeek V3 API client (primary generation)
│   │   ├── cerebras_client.py      # Cerebras API client (Qwen-3-235B, secondary)
│   │   ├── openai_client.py        # OpenAI API client (GPT-4.1-mini fallback, GPT-4o eval)
│   │   ├── factory.py              # LLMFactory.create() → provider priority: DeepSeek → Cerebras → OpenAI
│   │   └── token_tracker.py        # Thread-safe singleton: per-call token usage + USD cost tracking
│   │
│   └── rag/                        # Retrieval-Augmented Generation pipeline
│       ├── database_manager.py     # pgvector ANN queries; async pool; set_pool() injection
│       ├── search_engine.py        # Hybrid search: pgvector + BM25 → RRF + cross-encoder rerank
│       ├── prompts.py              # All LLM prompts (system + user) as constants
│       └── response_generator.py   # Builds context window; calls LLM; streams + formats response
│
├── app/                            # FastAPI application layer
│   ├── __init__.py                 # App factory: FastAPI instance, middleware, route setup
│   ├── lifespan.py                 # Startup/shutdown: DB pool, graph compile, model warm-up, BM25 index
│   ├── middleware.py               # CORS, request logging
│   ├── routes.py                   # Aggregates and registers all routers
│   │
│   ├── auth/
│   │   └── clerk.py                # Clerk JWT verification (AUTH_DISABLED=true for local dev; disabled by default)
│   │
│   ├── routers/                    # REST endpoint definitions
│   │   ├── health.py               # GET /health
│   │   ├── chat.py                 # POST /chat (REST alternative to WebSocket)
│   │   └── sessions.py             # CRUD /sessions, /sessions/{id}, /sessions/{id}/messages
│   │
│   ├── utils/
│   │   ├── database.py             # asyncpg pool lifecycle (create_pool, get_pool, close_pool)
│   │   └── logging.py              # setup_logging() — log level from LOG_LEVEL env
│   │
│   └── websocket/                  # WebSocket (streaming) handler
│       ├── handler.py              # Full WS lifecycle: ping, query, history, save, session management
│       ├── manager.py              # ConnectionManager: connect/disconnect/broadcast
│       └── routes.py               # @router.websocket("/ws")
│
├── db/                             # Database schema, migrations, ingestion scripts
│   ├── schema.sql                  # All CREATE TABLE + pgvector extension + ivfflat indexes
│   ├── setup_db.py                 # Apply schema.sql to Supabase: python db/setup_db.py
│   ├── setup_pgvector_supabase.py  # Enable pgvector + create indexes (run if schema already exists)
│   ├── generate_data_audit.py      # Query DB stats and write docs/DATA_AUDIT_SUPABASE_INGESTION_2026.md
│   ├── migrations/                 # (future; schema applied on startup)
│   └── ingestion/
│       ├── ingest_sec.py           # SEC EDGAR 10-K chunks + embeddings → ten_k_chunks
│       ├── ingest_stockanalysis.py # StockAnalysis earnings transcripts → transcript_chunks
│       ├── ingest_yfinance.py      # yfinance earnings summaries → transcript_chunks
│       ├── tickers.txt             # Default ticker list for ingest_sec.py
│       └── logs/                   # Auto-created per-run logs (sec_10k/, transcripts_stockanalysis/)
│
├── scripts/                        # Utility scripts (not DB-related)
│   ├── eval/
│   │   ├── run_ragas.py            # Lightweight standalone RAGAS runner
│   │   └── __init__.py
│   ├── download_logos.py
│   └── download_logos_colorful.py
│
├── evals/                          # Evaluation harness & ground truth generation
│   └── qa_eval/
│       ├── run_eval.py             # Unified eval runner (M1-M8 metrics: factual, faithfulness, recall, precision, routing, judge, latency)
│       ├── generate_ground_truth.py # Generate ground truth from question files (ticker extraction, chunk retrieval, GPT-4o synthesis)
│       ├── question_v3.txt         # Question set v3 (20 Qs, calibrated)
│       ├── question_v4.txt         # Question set v4 (30 Qs, harder)
│       ├── question_v5.txt         # Question set v5 (11 Qs, hard-case stress test)
│       ├── results/                # Per-run results: <timestamp>/ dirs with per-question JSON + _summary.json + _analysis.md
│       ├── docs/                   # Eval documentation: IMPROVEMENT_SUMMARY_*.md, DEMO_QUESTIONS_*.md, PLAN_C_RESULTS.md
│       ├── EVAL_WORKFLOW_GUIDE.md  # Complete workflow: ingestion → GT generation → eval → iteration
│       └── logs/                   # Auto-created execution logs
│
├── frontend/                       # React 18 SPA (served from port 5175 in dev)
│   ├── index.html                  # SPA shell
│   ├── vite.config.ts              # Dev proxy to backend:8000; build config
│   ├── tailwind.config.js          # Tailwind CSS config
│   ├── tsconfig.json               # TypeScript config
│   ├── package.json                # npm dependencies
│   ├── .env                        # VITE_AUTH_DISABLED, VITE_CLERK_PUBLISHABLE_KEY
│   ├── public/
│   │   └── favicon.svg
│   │
│   └── src/
│       ├── main.tsx                # Entry: ClerkProvider + BrowserRouter
│       ├── App.tsx                 # Route definitions (/ and /chat)
│       ├── index.css               # Tailwind directives + chat UI utilities
│       │
│       ├── lib/
│       │   ├── api.ts              # Typed fetch/ws wrappers for all endpoints + WS message types
│       │   └── config.ts           # API_BASE, WS_URL, AUTH_DISABLED constants
│       │
│       ├── hooks/
│       │   └── useAuthStatus.ts    # Clerk auth status hook (for future Clerk integration)
│       │
│       ├── pages/
│       │   ├── LandingPage.tsx     # Public home; feature grid, marketing
│       │   └── ChatPage.tsx        # Main chat UI — WebSocket lifecycle, session history, streaming
│       │
│       └── components/
│           ├── Sidebar.tsx         # Navigation + session list sidebar with drag-resize
│           ├── ChatMessage.tsx     # Chat bubble — confidence badge, citations, reasoning
│           ├── ChatInput.tsx       # Auto-resize textarea with Enter-to-send + web search toggle
│           ├── ReasoningTrace.tsx  # "Thinking" display (sub-questions, analysis steps)
│           └── AboutModal.tsx      # About/help modal
│
├── data/                           # Runtime data directory
│   ├── tickers.txt                 # Company ticker list
│   └── .gitkeep
│
├── tests/                          # Test suite
│   ├── api/
│   │   └── test_apis.py            # REST endpoint tests
│   ├── unit/
│   └── integration/
│
├── docs/                           # Documentation
│   ├── ARCHITECTURE.md             # System design, data flow, component interaction
│   ├── DIRECTORY_STRUCTURE.md      # This file — repo layout & file purposes
│   ├── RAG_MODEL_PIPELINE.md       # Detailed RAG models: embeddings, search, reranking, generation, evaluation
│   ├── HOW_TO_RUN.md               # Setup, local dev, deployment guide
│   ├── DATA_AUDIT_SEC_TRANSCRIPTS.md # Data audit of SEC filings and earnings transcripts
│   ├── ResearchAgent_Reference.pdf # Reference material for research agent design
│   ├── BUILD_AND_TEST_ORDER.md     # (reference) Build phases and testing order
│   ├── STAGES.md                   # (reference) Roadmap phases
│   ├── backend.md                  # Backend subsystem reference
│   ├── frontend.md                 # Frontend subsystem reference
│   ├── rag_pipeline.md             # RAG search pipeline deep dive
│   ├── websocket_protocol.md       # WebSocket message protocol spec
│   └── REFERENCE_REPOS_ANALYSIS.md # External repo analysis for architecture decisions
│
├── logs/                           # Runtime application logs
│   └── .gitkeep
│
├── config.py                       # Pydantic Settings — all env vars in one place
├── requirements.txt                # Python dependencies (FastAPI, LangGraph, asyncpg, sentence-transformers, etc.)
├── .env.example                    # Documented env var template
├── .env                            # Local environment variables (not in git)
├── .gitignore                      # Git ignore rules
├── CLAUDE.md                       # Claude Code instructions for this project
├── Procfile                        # Railway deployment: uvicorn entrypoint
└── railway.toml                    # Railway: healthcheck + autorestart config
```

## Key Relationships & Data Flow

### App Initialization (FastAPI Startup)
1. `app/__init__.py` creates FastAPI instance, registers middleware & routes
2. `app/lifespan.py` (startup event):
   - Creates asyncpg connection pool (2–10 connections)
   - Injects into RAG layer via `agent/rag/database_manager.py:set_pool()`
   - Pre-compiles LangGraph (`agent/graph/graph.py:build_graph()`)
   - Background tasks: warm ML models + build BM25 index
3. Frontend served from `frontend/dist` (production) or proxied from port 5175 (dev)

### Request Flow (WebSocket Query)
1. Browser sends WebSocket message → `app/websocket/routes.py` → `handler.py`
2. Handler parses query, emits status updates via `_status_callback`
3. Calls `agent/graph/graph.py:run()` with state:
   - `plan_search` node → analyzes question, extracts tickers, checks scope
   - `retrieve_context` node → calls `agent/rag/search_engine.py` (hybrid search)
   - `generate_answer` node → builds context, calls LLM via `agent/llm/factory.py`
   - `evaluate_quality` node → confidence scoring; if <0.65 and iter<2, retry
   - `finalize` node → formats response + citations
4. Tokens streamed via `_token_callback` → `handler.py` → WebSocket client
5. Token usage posted to LangSmith trace (if `LANGCHAIN_TRACING_V2=true`)

### Data Ingestion Pipeline (`db/ingestion/`)

See [docs/DATA_INGESTION.md](DATA_INGESTION.md) for full guide.

```bash
python db/setup_db.py                                                    # 1. Apply schema + pgvector
python db/ingestion/ingest_sec.py --start-year 2023 --end-year 2026 --replace        # 2. SEC 10-K
python db/ingestion/ingest_stockanalysis.py --years 2023 2024 2025 2026 --replace    # 3. Transcripts
python db/generate_data_audit.py                                         # 4. Audit report
```

### Evaluation Workflow (`evals/qa_eval/`)

**Phase 1: Ground Truth Generation**
```bash
python evals/qa_eval/generate_ground_truth.py --input "question_vN.txt" --full
```
Extracts tickers, queries DB for top-K chunks, uses GPT-4o to synthesize ground truth + key facts.

**Phase 2: Evaluation Execution**
```bash
python evals/qa_eval/run_eval.py --smoke --input "question_vN.txt"   # first 3 Qs
python evals/qa_eval/run_eval.py --full --input "question_vN.txt"    # all Qs
```
Computes 8 metrics (M1–M8), outputs per-question JSON + `_summary.json` + `_analysis.md`.

### Database & Cache
- **PostgreSQL (Railway):** 
  - `ten_k_chunks` — SEC 10-K filing chunks with pgvector embeddings
  - `transcript_chunks` — earnings call transcript chunks
  - `semantic_cache` — query→answer cache (cosine similarity threshold: 0.92)
  - `sessions`, `messages` — chat history
  - `eval_logs` — confidence score history

### Authentication (Clerk)
- **Current status:** `AUTH_DISABLED=true` (default in `config.py`)
- **How to enable:** Set `AUTH_DISABLED=false` in `.env` + configure `CLERK_SECRET_KEY` and `CLERK_PUBLISHABLE_KEY`
- **Implementation:** `app/auth/clerk.py` implements JWT verification; returns anonymous user when disabled

### Component Isolation
| Component | Role | Depends On |
|-----------|------|-----------|
| `app/` | HTTP/WS server | `agent/`, `config.py` |
| `agent/graph/` | Orchestration | `agent/llm/`, `agent/rag/` |
| `agent/llm/` | LLM abstraction | DeepSeek/Cerebras/OpenAI APIs |
| `agent/rag/` | Search & generation | PostgreSQL, sentence-transformers |
| `frontend/` | User interface | REST/WS APIs from `app/` |
| `scripts/ingestion/` | Data prep | PostgreSQL, SEC EDGAR, yfinance |
| `evals/qa_eval/` | Quality measurement | LangGraph pipeline, GPT-4o eval LLM |
