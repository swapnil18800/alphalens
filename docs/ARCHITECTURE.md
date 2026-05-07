# AlphaLens — System Architecture

> **See also:** [RAG_MODEL_PIPELINE.md](RAG_MODEL_PIPELINE.md) for a deep dive into every model, prompt, and search heuristic in the RAG pipeline. [DIRECTORY_STRUCTURE.md](DIRECTORY_STRUCTURE.md) for the full file tree.

---

## System Overview

AlphaLens is a full-stack agentic RAG (Retrieval-Augmented Generation) system for equity research. Users ask financial questions via a WebSocket connection; a LangGraph state machine retrieves context from SEC 10-K filings and earnings transcripts, generates a grounded, cited answer, self-evaluates its own confidence, and automatically retries with a rewritten query if quality falls below threshold.

**Key capabilities:**
- **Agentic self-correction** — confidence scoring + automatic query rewriting + retry (max 2 iterations)
- **Hybrid semantic + keyword search** — pgvector cosine ANN + BM25 Okapi → RRF fusion → cross-encoder rerank
- **Multi-provider LLM routing** — DeepSeek V3 (primary) → Cerebras Qwen-3-235B (secondary) → GPT-4.1-mini (fallback)
- **Real-time WebSocket streaming** — token-by-token response + live reasoning trace
- **Production database** — Supabase PostgreSQL with pgvector extension
- **Clerk auth** — wired, disabled by default (`AUTH_DISABLED=true`)
- **LangSmith tracing** — optional distributed tracing with token cost reporting

---

## High-Level Architecture

![Architecture Overview](../assets/architecture.png)


---

## WebSocket Data Flow During Chat

The following diagram shows the complete lifecycle of a single user query through the system — from WebSocket message receipt to the final streamed answer.

```mermaid
sequenceDiagram
    participant B as Browser (React)
    participant WS as WS Handler (handler.py)
    participant G as LangGraph (graph.py)
    participant N as Nodes (nodes.py)
    participant SE as SearchEngine
    participant DB as Supabase DB
    participant LLM as LLM (DeepSeek/etc.)
    participant LS as LangSmith

    B->>WS: {type:"query", query:"...", web_search:false, session_id:"uuid"}
    WS->>WS: Load conversation history from DB
    WS-->>B: {type:"status", step:"plan_search", message:"Analyzing question..."}

    WS->>G: graph.run(ResearchState)

    G->>N: node_analyze_question (plan_search)
    Note over N: Extract tickers, classify intent,<br/>decompose sub-questions,<br/>check out-of-scope
    N-->>B: {type:"token"} × N  (streaming sub-questions)
    N-->>B: {type:"status", step:"retrieve_context"}

    G->>N: node_execute_search (retrieve_context)
    N->>SE: hybrid_search(query, tickers, year)
    SE->>DB: pgvector cosine ANN (top-20 × 2 tables)
    SE->>SE: BM25 keyword search (top-20 × 2 tables)
    Note over SE: RRF rank fusion (k=60)<br/>Cross-encoder rerank<br/>Table boost injection
    SE-->>N: sec_chunks[], transcript_chunks[]

    N-->>B: {type:"status", step:"generate_answer"}

    G->>N: node_generate_response (generate_answer)
    N->>LLM: stream(context + prompt)
    loop Token streaming
        LLM-->>N: token chunk
        N-->>B: {type:"token", content:"..."}
    end
    N-->>B: {type:"status", step:"evaluate_quality"}

    G->>N: node_evaluate_response (evaluate_quality)
    Note over N: Heuristic check first<br/>LLM judge if borderline (0.50-0.75)
    
    alt score >= 0.65 OR iterations >= 2
        G->>N: node_finalize (finalize)
    else score < 0.65 AND iterations < 2
        N-->>B: {type:"status", step:"rewrite_query"}
        G->>N: node_query_rewriter (rewrite_query)
        Note over N: Broaden query, expand synonyms
        G->>N: node_execute_search (retry)
        G->>N: node_generate_response (retry)
        G->>N: node_evaluate_response (retry)
        G->>N: node_finalize (best score wins)
    end

    N-->>B: {type:"final", answer:"...", confidence:0.85, citations:[...]}

    WS->>DB: Save session + messages
    WS->>LS: Post LangSmith trace + token cost
```

---

## Component Architecture

### 1. FastAPI Application Layer (`app/`)

**Entry Point: `app/__init__.py`**
- Creates FastAPI instance with lifespan handlers
- Registers middleware (CORS, request logging)
- Mounts static file routes: `/logos` (company SVGs) and `/stack_logos` (tech stack logos)
- In production: serves React SPA from `frontend/dist` (catch-all route)

```mermaid
flowchart LR
    INIT[app/__init__.py]
    LIFE[lifespan.py]
    MW[middleware.py]
    ROUTES[routes.py]

    INIT --> LIFE
    INIT --> MW
    INIT --> ROUTES

    subgraph Startup
        LIFE --> POOL["asyncpg pool — 2-10 connections"]
        LIFE --> INJECT["inject pool into database_manager"]
        LIFE --> COMPILE["compile LangGraph singleton"]
        LIFE --> WARM["warm ML models + BM25 index"]
    end

    ROUTES --> R_HEALTH["GET /health"]
    ROUTES --> R_CHAT["POST /chat"]
    ROUTES --> R_SESS["/sessions CRUD"]
    ROUTES --> R_WS["WebSocket /ws"]
```

**Startup Sequence:**
```
on_startup:
  1. Create asyncpg connection pool (2–10 connections)
  2. Inject pool into agent/rag/database_manager.py via set_pool()
  3. Pre-compile LangGraph research_graph singleton (build_graph())
  4. Background task: warm sentence-transformer embedding model
  5. Background task: warm cross-encoder reranker model
  6. Background task: load all chunks from DB → build BM25 index in memory

on_shutdown:
  1. Close asyncpg pool gracefully
```

**WebSocket Handler (`app/websocket/handler.py`)**

The central WS coordinator. Manages per-connection lifecycle:
- Receives `{type: "query", query, web_search, session_id}` from browser
- Emits `{type: "status"}` updates at each graph node boundary
- Streams `{type: "token"}` from LLM via `_token_callback`
- Saves `session` + `messages` to DB on completion
- Submits LangSmith run metadata (token counts, cost) on completion

**Authentication (`app/auth/clerk.py`)**
- Implements Clerk JWT verification (JWKS-based)
- **Default:** `AUTH_DISABLED=true` — returns anonymous user with `anon_id` from browser localStorage
- **To enable:** Set `AUTH_DISABLED=false` + configure `CLERK_SECRET_KEY` + `CLERK_PUBLISHABLE_KEY`
- When enabled: JWT decoded, user payload extracted, sessions scoped per user

**REST Endpoints**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness probe (Railway/Supabase healthcheck) |
| `/chat` | POST | One-off non-streaming query |
| `/sessions` | GET / POST | List/create chat sessions |
| `/sessions/{id}` | GET / PUT / DELETE | Manage individual session |
| `/sessions/{id}/messages` | GET | Retrieve conversation history |
| `/ws` | WebSocket | Primary streaming chat interface |

---

### 2. LangGraph Orchestration (`agent/graph/`)

The LangGraph state machine is the core orchestration layer. All inter-node communication happens through `ResearchState` — a TypedDict that flows through every node.

```mermaid
flowchart TD
    START([User Query]) --> PS

    PS[plan_search]

    PS -->|out_of_scope| FE[finalize_early]
    PS --> RC

    RC[retrieve_context]

    RC --> GA

    GA[generate_answer]

    GA --> EQ

    EQ[evaluate_quality]

    EQ -->|"score >= 0.65 or iter >= 2"| FIN
    EQ -->|"score < 0.65 and iter < 2"| RQ

    RQ[rewrite_query]

    RQ --> RC

    FIN[finalize]

    FIN --> END([Final Answer + Citations])
    FE --> END
```

**`ResearchState` TypedDict (`state.py`)**

Every field is initialized in `graph.py:run()` before graph execution begins:

| Field | Type | Role |
|-------|------|------|
| `question` | `str` | User's original query |
| `tickers` | `List[str]` | Extracted stock tickers (`["NVDA", "AMD"]`) |
| `sub_questions` | `List[str]` | Analysis decomposition (shown as "thinking" trace) |
| `intent` | `str` | Classification: `"risk_factors"`, `"valuation"`, `"comparison"`, etc. |
| `query_mode` | `str` | `"rag_only"` \| `"web_only"` \| `"hybrid"` \| `"out_of_scope"` |
| `is_out_of_scope` | `bool` | True → route to `finalize_early` |
| `year` | `Optional[int]` | Extracted fiscal year for DB filtering |
| `sec_chunks` | `List[Dict]` | Retrieved 10-K segments with metadata |
| `transcript_chunks` | `List[Dict]` | Retrieved earnings call segments |
| `news_results` | `List[Dict]` | Tavily web search results |
| `draft_answer` | `str` | Raw LLM output |
| `citations` | `List[Dict]` | `{ticker, source, year, quarter, similarity}` |
| `eval_score` | `float` | Confidence 0–1 |
| `eval_reason` | `str` | Explanation of confidence |
| `best_score` | `float` | Best eval score across all iterations |
| `best_answer` | `str` | Answer corresponding to best score |
| `best_citations` | `List[Dict]` | Citations for best answer |
| `final_answer` | `str` | Polished response sent to user |
| `confidence` | `float` | `= best_score`, exposed to frontend |
| `iteration_count` | `int` | Retry counter (0, 1, or 2) |
| `_token_callback` | `Callable` | Async function to emit tokens → WebSocket |
| `_status_callback` | `Callable` | Async function to emit status → WebSocket |
| `web_search` | `bool` | Whether to invoke Tavily |
| `conversation_history` | `List[Dict]` | Prior turns for multi-turn context |
| `error` | `Optional[str]` | Error message if node fails |

**Node Definitions (`nodes.py`)**

| Node | LLM | Key Operations |
|------|-----|----------------|
| `node_analyze_question` | DeepSeek V3 → Cerebras → GPT-4.1-mini | Extract tickers, classify intent, decompose sub-questions, routing decision |
| `node_execute_search` | — (no LLM) | Semantic cache → embed → pgvector + BM25 → RRF → rerank → table boost |
| `node_generate_response` | DeepSeek V3 → Cerebras → GPT-4.1-mini | Build context, stream LLM tokens, build citations |
| `node_evaluate_response` | GPT-4o (consistent judge) | Heuristic check + LLM judge if borderline (0.50–0.75) |
| `node_query_rewriter` | DeepSeek V3 → Cerebras → GPT-4.1-mini | Rewrite/broaden query for retry |
| `node_finalize` | — | Format final answer using best score from any iteration |
| `node_finalize_early` | — | Graceful refusal for out-of-scope queries |

**Routing Logic (`edges.py`)**
```python
def route_after_analysis(state) -> str:
    return "finalize_early" if state["is_out_of_scope"] else "retrieve_context"

def route_after_evaluation(state) -> str:
    if state["eval_score"] >= 0.65 or state["iteration_count"] >= 2:
        return "finalize"
    return "rewrite_query"
```

---

### 3. RAG Pipeline (`agent/rag/`)

```mermaid
flowchart LR
    Q[User Query] --> CACHE{Semantic Cache — cosine 0.92}
    CACHE -->|HIT| CACHED[Cached Answer]
    CACHE -->|MISS| EMBED[Embed — all-MiniLM-L6-v2]

    EMBED --> PAR{Parallel Search}

    PAR --> PGV[pgvector — cosine ANN top-20]
    PAR --> BM25[BM25 Okapi — keyword top-20]
    PAR --> WEB[Tavily — web search]

    PGV --> RRF[RRF Fusion k=60]
    BM25 --> RRF

    RRF --> CE[Cross-Encoder — TinyBERT rerank]
    CE --> BOOST[Table Boost — inject top-4]
    BOOST --> CTX[Context Window — 6000 chars]
    WEB --> CTX

    CTX --> GEN[Response Generator — DeepSeek V3]
    GEN --> ANS[Grounded Answer + Citations]
```

**`search_engine.py`** — Hybrid retrieval coordinator:
- Reads pre-built BM25 index from memory (warmed at startup)
- Queries pgvector via `database_manager.py` (asyncpg)
- Runs RRF merge with `k=60` to dampen rank inflation
- Invokes cross-encoder reranking via sentence-transformers
- Injects top-4 table-type chunks post-rerank (bypasses TinyBERT table downranking)
- Applies year filter `±1` expansion for NVDA-style offset fiscal years

**`database_manager.py`** — asyncpg wrapper:
- Pool injected at startup via `set_pool()`
- `search_chunks(query_embedding, ticker, year, table, top_k)` → pgvector cosine ANN
- `get_semantic_cache_entry(query_embedding)` → cache lookup
- `insert_semantic_cache(query, answer, embedding)` → cache write

**`response_generator.py`** — Context + LLM call:
- Builds context: `format_chunks()` with round-robin interleaving for cross-company queries
- Context budget: 6000 chars total (60% SEC, 40% transcript for hybrid; all SEC for rag_only)
- Calls `LLMFactory.create()` and streams tokens via `state._token_callback`
- Deduplicates citations (SEC by key tuple, web by URL)

**`prompts.py`** — Single source of truth for all prompts:
- `ANALYSIS_SYSTEM_PROMPT` — intent extraction, ticker detection, routing
- `RESPONSE_SYSTEM_PROMPT` — grounded answer generation with citation rules
- `EVAL_PROMPT` — LLM-as-judge verdict (pass/partial/fail)
- `REWRITE_PROMPT` — query broadening for retry
- `OUT_OF_SCOPE_REPLY` — graceful refusal template

---

### 4. LLM Abstraction Layer (`agent/llm/`)

```mermaid
flowchart TB
    FAC[LLMFactory.create]

    FAC -->|"1st: DEEPSEEK_API_KEY set"| DS[DeepSeek V3 — deepseek-chat, no daily quota]

    FAC -->|"2nd: CEREBRAS_API_KEY set"| CB[Cerebras Qwen-3-235B — fast inference, daily quota]

    FAC -->|"3rd: Fallback"| OA[OpenAI GPT-4.1-mini — fallback, gpt-4o for eval]

    TT[token_tracker.py — per-call tokens + cost, posts to LangSmith]

    DS --> TT
    CB --> TT
    OA --> TT

    BASE[BaseLLMClient — astream, acomplete]
    DS -.->|implements| BASE
    CB -.->|implements| BASE
    OA -.->|implements| BASE
```

**Provider Selection Logic:**
```
LLM_PROVIDER=auto (default):
  1. DEEPSEEK_API_KEY present? → DeepSeekClient (fast, cheap, quota-free)
  2. CEREBRAS_API_KEY present? → CerebrasClient (fast, but daily quota)
     - On 429 CerebrasRateLimitError → fall through to OpenAI
  3. OPENAI_API_KEY → OpenAIClient (GPT-4.1-mini for generation)

Eval LLM (always GPT-4o):
  - factory.create_eval_llm() always returns GPT-4o for consistent judging
  - Non-negotiable: gpt-4o-mini gave inconsistent verdicts on identical answers
```

**Token Tracking (`token_tracker.py`)**

| Model | Input ($/1M) | Output ($/1M) |
|-------|-------------|--------------|
| DeepSeek V3 | $0.14 | $0.28 |
| GPT-4.1-mini | $0.40 | $1.60 |
| GPT-4o | $2.50 | $10.00 |
| Cerebras Qwen-3-235B | ~$0.60 | ~$0.60 |

Typical total query cost: **~$0.002–$0.008** (DeepSeek V3 primary).

---

### 5. Frontend (`frontend/`)

**Stack:** React 18 + TypeScript + Vite + Tailwind CSS + framer-motion + Clerk

```mermaid
flowchart TB
    subgraph Pages
        LP[LandingPage.tsx]
        CP[ChatPage.tsx]
    end

    subgraph Components
        SB[Sidebar.tsx]
        CM[ChatMessage.tsx]
        CI[ChatInput.tsx]
        RT[ReasoningTrace.tsx]
        AM[AboutModal.tsx]
        AUTH[AuthModal.tsx]
    end

    subgraph Hooks
        UA[useAuthStatus.ts]
        ANON[useAnonId.ts]
    end

    subgraph Lib
        API[api.ts]
        CFG[config.ts]
    end

    LP --> CP
    CP --> SB
    CP --> CM
    CP --> CI
    CP --> RT
    CP --> AM
    CP --> AUTH
    CP --> API
    CP --> CFG
    CP --> UA
    CP --> ANON
```

**WebSocket Protocol (Client → Server):**
```jsonc
// Client sends:
{
  "type": "query",
  "query": "What are NVIDIA's key risk factors?",
  "web_search": false,
  "session_id": "uuid-or-null"
}

// Server streams:
{"type": "status", "step": "plan_search", "message": "Analyzing question..."}
{"type": "status", "step": "retrieve_context", "message": "Searching SEC filings..."}
{"type": "token", "content": "NVIDIA"}
{"type": "token", "content": " faces several significant risks..."}
// ... (hundreds of token messages)
{"type": "final", "answer": "...", "confidence": 0.85, "citations": [
  {"ticker": "NVDA", "source": "10-K", "year": 2025, "similarity": 0.91}
]}
```

**Anonymous Session Flow:**
- `useAnonId.ts` generates a UUID and stores it in `localStorage` as `anon_id`
- All sessions are scoped by `anon_id` when `AUTH_DISABLED=true`
- Session history persists across page reloads via the same `anon_id`
- When Clerk auth is enabled: sessions scope to authenticated user instead

---

### 6. Data Stores (Supabase PostgreSQL + pgvector)

> **Database host:** Supabase (migrated from Railway PostgreSQL, commit `2bc596c`)

```mermaid
erDiagram
    ten_k_chunks {
        uuid id PK
        varchar ticker
        int year
        varchar section
        text text
        varchar chunk_type
        vector_384 embedding
        timestamp created_at
    }

    transcript_chunks {
        uuid id PK
        varchar ticker
        int year
        varchar quarter
        text text
        varchar chunk_type
        vector_384 embedding
        timestamp created_at
    }

    semantic_cache {
        uuid id PK
        text query
        vector_384 query_embedding
        text answer
        float score
        timestamp created_at
    }

    sessions {
        uuid id PK
        varchar user_id
        varchar anon_id
        varchar title
        timestamp created_at
        timestamp updated_at
    }

    messages {
        uuid id PK
        uuid session_id FK
        varchar role
        text content
        jsonb metadata
        timestamp created_at
    }

    eval_logs {
        uuid id PK
        uuid session_id FK
        text query
        float eval_score
        text reason
        timestamp created_at
    }

    sessions ||--o{ messages : contains
    sessions ||--o{ eval_logs : tracks
```

**pgvector Indexes:**
- `ten_k_chunks.embedding` — IVFFlat, cosine metric (lists=100)
- `transcript_chunks.embedding` — IVFFlat, cosine metric
- `semantic_cache.query_embedding` — IVFFlat, cosine metric

**BM25 Index (in-memory):**
- Built at startup from all `ten_k_chunks` + `transcript_chunks` text
- `BM25Okapi` from `rank_bm25` library, k1=1.5, b=0.75
- Never persisted to disk; always rebuilt from DB on startup (~30s for 50k chunks)

---

## Data Ingestion Pipeline (`db/ingestion/`)

```mermaid
flowchart TD
    SCHEMA[1. db/setup_db.py — apply schema + pgvector + IVFFlat indexes]

    SEC[2. ingest_sec.py — SEC EDGAR API, 10-K filings, 33 companies, ten_k_chunks]

    SA[3. ingest_stockanalysis.py — earnings transcripts, 27 companies, transcript_chunks]

    AUDIT[4. generate_data_audit.py — query DB stats, write audit markdown]

    SCHEMA --> SEC --> SA --> AUDIT

    style SEC fill:#dbeafe,color:#111111
    style SA fill:#dcfce7,color:#111111
    style AUDIT fill:#fef3c7,color:#111111
```

**Chunking Strategy:**
- 1400-character sliding window, 200-character overlap
- Table detection: regex pattern → `chunk_type = "table"` (not prose)
- Table chunks get injected post-rerank (bypass TinyBERT downranking)
- All chunks embedded at ingest time → stored as `vector(384)` in pgvector

---

## Evaluation Suite (`evals/qa_eval/`)

```mermaid
flowchart LR
    QF[question_vN.txt]

    GT[generate_ground_truth.py — GPT-4o synthesize GT]

    RUN[run_eval.py — compute M1-M8 metrics]

    RESULTS[results/timestamp/ — JSON + analysis.md]

    DOCS[evals/qa_eval/docs/ — improvement summaries]

    QF --> GT --> QF
    QF --> RUN --> RESULTS --> DOCS
```

**M1–M8 Metric Summary:**

| Metric | Definition | LLM? | Weight |
|--------|-----------|------|--------|
| **M1** | Factual correctness — key facts in answer (fuzzy match) | No | 1/6 |
| **M2** | RAGAS faithfulness — answer grounded in retrieved context | GPT-4o | 1/6 |
| **M3** | Retrieval recall — key facts in top-K chunks | No | 1/6 |
| **M4** | RAGAS context precision — chunks are relevant | GPT-4o | 1/6 |
| **M6** | Routing accuracy — query_mode vs expected | No | 1/6 |
| **M7** | LLM judge verdict (pass=1.0 / partial=0.5 / fail=0.0) | GPT-4o | 1/6 |
| **Score** | `mean(M1, M2, M3, M4, M6, M7)` | — | — |

**Score history:** 0.546 (baseline) → 0.784 (v2+v3 combined) → 0.773 (Session 6 final).

---

## Observability & Tracing

### LangSmith (Optional)

Enable by setting `LANGCHAIN_TRACING_V2=true` in `.env`.

```mermaid
flowchart LR
    WS[WebSocket Handler] -->|RunCollectorCallbackHandler| GRAPH[LangGraph Execution]
    GRAPH -->|node spans| LS[LangSmith Dashboard]
    GRAPH -->|token counts + cost| LS

    LS --> SPANS[Trace Spans — plan, retrieve, generate, evaluate, finalize]
    LS --> COST[Metadata — tokens, cost USD, model, eval_score]
```

Tavily web search is decorated with `@traceable` for LangSmith span capture.

### Application Logging

- Format: `[tag] message` (e.g., `[search] Embedding query...`, `[node] plan_search complete`)
- Log level: `LOG_LEVEL` env (default: `INFO`)
- Tags: `[ws]`, `[graph]`, `[search]`, `[llm]`, `[node]`, `[rag]`

---

## Configuration Reference

All env vars are defined in `config.py` (pydantic-settings):

```bash
# Database (Supabase)
DATABASE_URL=postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres

# LLM Providers
DEEPSEEK_API_KEY=sk-...       # Primary — no daily quota
CEREBRAS_API_KEY=csk-...      # Secondary — fast but has daily limit
OPENAI_API_KEY=sk-...         # Fallback + eval judge (GPT-4o)
LLM_PROVIDER=auto             # auto | deepseek | cerebras | openai

# Web Search
TAVILY_API_KEY=tvly-...       # Optional; enables web_search mode

# Auth (Clerk)
AUTH_DISABLED=true            # true = anonymous sessions (default for local dev)
CLERK_SECRET_KEY=sk_...       # Required when AUTH_DISABLED=false
CLERK_PUBLISHABLE_KEY=pk_...  # Required when AUTH_DISABLED=false

# Observability (LangSmith)
LANGCHAIN_TRACING_V2=false    # Set to true to enable tracing
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=alphalens

# Feature Flags
CACHE_DISABLED=false          # Set true during evals to prevent cache interference

# Server
ENVIRONMENT=development       # development | production
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5175,https://alphalens-production-15e1.up.railway.app
```

---

## Deployment

### Railway (Production)

```bash
# 1. Build frontend
cd frontend && npm run build && cd ..

# 2. Procfile (Railway uses this)
web: uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1

# 3. FastAPI serves React SPA from frontend/dist in production
#    Logos and stack_logos served from static mounts
```

- **App hosting:** Railway (via Procfile + `railway.toml`)
- **Database:** Supabase PostgreSQL + pgvector
- **Frontend build:** Railway builds via nixpacks.toml (`npm run build` pre-deploy)
- **Health check:** `GET /health` (configured in `railway.toml`)
- **Env vars:** Set in Railway dashboard

### Local Development

```bash
# Terminal 1: Backend (from project root, .venv activated)
python -m uvicorn app:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev   # → http://localhost:5175
# Vite proxies /api, /ws, /sessions, /health to localhost:8000
```

---

## Cross-Component Summary

```mermaid
flowchart LR
    APP[app/ — FastAPI]
    AGENT[agent/graph/ — LangGraph]
    RAG[agent/rag/ — Search + Generation]
    LLM[agent/llm/ — LLM Abstraction]
    DB[(Supabase PostgreSQL)]
    FE[frontend/ — React SPA]
    EVAL[evals/qa_eval/ — Eval Harness]
    INGEST[db/ingestion/ — Data Pipeline]

    FE -->|WS + REST| APP
    APP --> AGENT
    AGENT --> RAG
    RAG --> LLM
    RAG --> DB
    LLM -->|DeepSeek / Cerebras / OpenAI| EXT((External APIs))
    INGEST --> DB
    EVAL -->|runs full pipeline| AGENT
    EVAL -->|GPT-4o judge| LLM

    style APP fill:#dbeafe,color:#111111
    style AGENT fill:#dcfce7,color:#111111
    style RAG fill:#fef3c7,color:#111111
    style LLM fill:#fce7f3,color:#111111
    style DB fill:#f3f4f6,color:#111111
    style FE fill:#ede9fe,color:#111111
```

| Component | Role | Depends On |
|-----------|------|-----------|
| `app/` | HTTP + WebSocket server | `agent/`, `config.py` |
| `agent/graph/` | LangGraph orchestration | `agent/llm/`, `agent/rag/` |
| `agent/llm/` | LLM provider abstraction | DeepSeek, Cerebras, OpenAI APIs |
| `agent/rag/` | Hybrid search + context generation | Supabase DB, sentence-transformers |
| `frontend/` | React SPA | REST + WebSocket from `app/` |
| `db/ingestion/` | Data pipeline | SEC EDGAR, StockAnalysis.com, Supabase |
| `evals/qa_eval/` | Quality measurement | Full LangGraph pipeline, GPT-4o |
