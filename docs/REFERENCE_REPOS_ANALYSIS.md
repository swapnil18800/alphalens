# Reference Repository Analysis

Architecture and key patterns from the three reference repositories, and what AlphaLens
borrows from each.

---

## 1. GiovanniPasq/agentic-rag-for-dummies

### Directory Structure
```
project/
├── app.py                 # Gradio entry point
├── config.py              # All tunable settings
├── core/                  # RAG orchestration
├── db/                    # Vector DB + parent chunk storage
├── rag_agent/             # LangGraph workflow
└── ui/                    # Gradio interface
notebooks/
assets/
```

### Tech Stack
- **LLM**: Ollama / OpenAI / Anthropic / Gemini (swappable in config.py one line)
- **Vector DB**: Qdrant (local or cloud)
- **Embeddings**: HuggingFace `all-mpnet-base-v2` (768-dim dense) + FastEmbedSparse (BM25)
- **Sparse search**: Qdrant's built-in BM25 tokenizer via `RetrievalMode.HYBRID`
- **UI**: Gradio

### LangGraph Topology

**Agent subgraph** (one per sub-question):
```
START → orchestrator → tools (search_child_chunks / retrieve_parent_chunks)
  → should_compress_context → [compress OR continue]
  → fallback_response | collect_answer → END
```

**Main graph**:
```
START
  → summarize_history
  → rewrite_query ──→ request_clarification (interrupt_before, loop back if ambiguous)
                  └──→ agent (spawns parallel subgraphs via LangGraph Send API)
                           → aggregate_answers → END
```

### Key Architectural Patterns

| Pattern | Description |
|---|---|
| **Hierarchical indexing** | Parent chunks (large, header-based) + child chunks (500-token). Search on small; return large. |
| **Multi-agent map-reduce** | Complex queries decomposed into sub-questions; each runs a parallel subgraph via `Send` API |
| **BM25 + dense hybrid** | Qdrant stores both vectors; `RetrievalMode.HYBRID` fuses them internally |
| **Token budget management** | `estimate_context_tokens()` drives compression decisions dynamically |
| **Accumulator reducer with reset** | `accumulate_or_reset()` — allows clean state resets between phases |
| **Human-in-the-loop** | `interrupt_before=["request_clarification"]` pauses graph for user input |
| **Parent deduplication** | Tracks retrieved parent IDs in `retrieval_keys: Set[str]` to avoid duplicate fetches |

### What AlphaLens Borrows
- **Sub-question decomposition** in `analyze_question` node (added to `ANALYSIS_PROMPT`)
- **Query rewriter node** on retry path (borrowed from `rewrite_query` concept)
- **BM25 hybrid search** (adapted: `rank_bm25` in-memory instead of Qdrant's built-in)
- **Conversation history summary** injected per LLM call

### What Was Skipped / Adapted
- Qdrant → PostgreSQL pgvector (already in use, persistent, simpler)
- Gradio UI → React frontend (already built)
- Hierarchical parent/child chunking → single-level chunks (sufficient for 10-K/yfinance data)
- Human-in-the-loop clarification → not needed for financial Q&A (question scope is clear)

---

## 2. wassim249/fastapi-langgraph-agent-production-ready-template

### Directory Structure
```
app/
├── api/v1/           # HTTP route handlers
├── core/
│   ├── langgraph/    # Agent graph + tool definitions
│   ├── prompts/      # System prompt templates
│   ├── cache.py      # Valkey/Redis + in-memory fallback
│   ├── config.py     # Settings (env-backed)
│   ├── middleware.py # Metrics, logging, request-ID injection
│   └── limiter.py    # Rate limiting (slowapi)
├── models/           # SQLModel ORM definitions
├── schemas/          # Pydantic validation schemas
└── services/         # LLM, database, memory services
alembic/             # DB migrations
evals/               # LLM eval framework
prometheus/          # Metrics config
grafana/dashboards/  # Visualization
```

### Tech Stack
- **Core**: FastAPI + LangGraph (stateful, checkpointed)
- **DB**: PostgreSQL + Alembic + pgvector
- **Memory**: mem0 with semantic caching layer
- **Cache**: Valkey/Redis + in-memory fallback
- **Auth**: JWT + session tracking
- **Observability**: Langfuse + Prometheus + Grafana
- **Rate limiting**: slowapi

### Key Architectural Patterns

| Pattern | Description |
|---|---|
| **FastAPI lifespan** | `@asynccontextmanager` — graph, DB pool, embedding model all initialized once at startup |
| **Request context propagation** | user_id / session_id / request_id injected into every log line via middleware |
| **pgvector semantic cache** | `SELECT response WHERE cosine_sim >= 0.92` — skips full pipeline on near-duplicate queries |
| **Circular model fallback** | Exponential backoff across LLM providers, total timeout budget |
| **Alembic migrations** | Versioned schema changes; no manual SQL needed |
| **Observability first** | Every LLM call traced in Langfuse; metrics to Prometheus; dashboards in Grafana |
| **mem0 memory tiering** | Semantic + episodic memory backed by pgvector + Redis |

### What AlphaLens Borrows
- **FastAPI lifespan pattern** → `app/lifespan.py` (DB pool + BM25 corpus built once at startup)
- **pgvector semantic cache** → `semantic_cache` table + `_check_semantic_cache()` in `search_engine.py`
- **LangSmith env-var tracing** → just set `LANGCHAIN_TRACING_V2=true` in `.env`, zero code changes
- **Test directory structure** → `tests/api/` and `tests/unit/`
- **`db/migrations/` placeholder** → ready for Alembic if needed later

### What Was Skipped / Adapted
- mem0 → LangFuse (already integrated, simpler)
- Prometheus/Grafana → LangFuse (sufficient for current scale)
- Alembic → plain `db/schema.sql` (simpler, avoids migration overhead at this stage)
- Valkey/Redis → not needed at single-worker Railway scale

---

## 3. kamathhrishi/finance-agent (base repo)

### Directory Structure
```
finance_agent/
├── agent/
│   ├── llm/               # Unified LLM client (Cerebras primary, OpenAI fallback)
│   ├── rag/
│   │   ├── rag_agent.py               # Main pipeline orchestrator
│   │   ├── sec_filings_service_smart_parallel.py
│   │   ├── earnings_transcript_service.py
│   │   ├── question_analyzer.py       # Semantic routing
│   │   ├── search_engine.py           # Hybrid: pgvector + TF-IDF
│   │   ├── response_generator.py
│   │   ├── search_planner.py          # Search strategy planner
│   │   └── data_ingestion/
│   └── screener/          # DuckDB financial screener
├── app/                   # FastAPI routers + schemas
├── frontend/              # React + TypeScript + Tailwind
├── db/
└── docs/
```

### Tech Stack
- **LLM**: Cerebras Qwen-3-235B (primary, fast) → OpenAI gpt-4o-mini (fallback)
- **Search**: pgvector cosine + TF-IDF, cross-encoder reranking
- **Screener**: DuckDB (fast in-process analytics)
- **Auth**: Clerk
- **Observability**: Logfire (optional)
- **Benchmark**: 91% on FinanceBench (112 10-K questions)

### Key Architectural Patterns

| Pattern | Description |
|---|---|
| **Semantic data-source routing** | `question_analyzer` extracts intent → routes to transcripts vs 10-K vs news vs hybrid |
| **Planning-driven retrieval** | Agent generates explicit reasoning ("I need to find...") before searching |
| **Parallel per-ticker subagents** | Multi-ticker queries spawn concurrent LangGraph subgraphs, unified in one answer |
| **Iterative improvement loop** | Generate → evaluate quality (configurable 70-95%) → re-query with better terms |
| **TF-IDF + pgvector hybrid** | Keyword + semantic fusion; cross-encoder reranks top-20 → top-k |
| **yfinance as transcript substitute** | Quarterly financial summaries replace paid API Ninjas transcripts (free, no key) |

### What AlphaLens Borrows
- **Cerebras → OpenAI LLM routing** (entire `agent/llm/` layer kept identical)
- **Frontend** (React + TypeScript + Tailwind — kept close to finance-agent)
- **FastAPI routers** (app/routers/ structure kept close to finance-agent)
- **yfinance ingestion** (`scripts/ingestion/ingest_yfinance.py` ported directly from `ingest_yfinance_to_transcripts.py`)
- **EDGAR 10-K ingestion** (`scripts/ingestion/ingest_sec.py`)
- **Test suite** (`tests/api/test_apis.py` adapted from `test_apis.py`)
- **DuckDB screener** (`agent/screener/`)
- **Cross-encoder reranking** (added to `search_engine.py`)

### What Was Changed / Extended
- Monolithic RAG agent → LangGraph 6-node graph (cleaner state management)
- TF-IDF → `rank_bm25` (pure Python BM25, no sklearn dependency)
- Added semantic cache (`semantic_cache` table + cache lookup)
- Added query rewriter node on retry path
- Added sub_questions in analysis node (from agentic-rag-for-dummies)
- Added eval_logs table (RAGAS per-query scores persisted)
- Production directory structure (`scripts/ingestion/`, `tests/api/`, `data/`)

---

## Summary: What AlphaLens Synthesizes

```
finance-agent (base)              → FastAPI routers, React frontend, Cerebras+OpenAI
                                    LLM routing, yfinance/EDGAR ingestion, cross-encoder,
                                    DuckDB screener, Railway deployment

agentic-rag-for-dummies           → Sub-question decomposition, query rewriter node,
                                    BM25 hybrid search, conversation history injection,
                                    retry-loop concept

fastapi-langgraph-production      → FastAPI lifespan pattern, semantic cache (pgvector),
                                    LangSmith tracing, test directory structure,
                                    BM25 corpus pre-built at startup
```

### AlphaLens differentiators over all three repos
- **Free data pipeline**: yfinance (quarterly) + SEC EDGAR (10-K) — no paid APIs
- **Semantic cache**: ~200ms hit vs ~10s full pipeline
- **RAGAS eval_logs**: every query's faithfulness score persisted in DB
- **BM25+pgvector+rerank in one engine**: combined into `search_engine.py`
- **Production directory layout**: `scripts/ingestion/`, `tests/api/`, `data/`, `logs/`, `evals/`
