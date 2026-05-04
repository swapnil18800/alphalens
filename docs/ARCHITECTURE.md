# AlphaLens — Architecture

> **See also:** [RAG_MODEL_PIPELINE.md](RAG_MODEL_PIPELINE.md) for detailed explanation of all models used in the RAG pipeline (embeddings, search, reranking, generation, evaluation)

## System Overview

AlphaLens is a full-stack agentic RAG (Retrieval-Augmented Generation) system for equity research. It combines:

- **LangGraph state machine** for multi-step reasoning and self-correction
- **Hybrid semantic + keyword search** over SEC filings and earnings transcripts
- **Multi-provider LLM routing** (DeepSeek V3 primary → Cerebras → OpenAI fallback)
- **Self-evaluating confidence scoring** with automatic retry on low confidence
- **Real-time WebSocket streaming** of both reasoning and response tokens
- **Comprehensive offline evaluation** (M1-M8 metrics) for quality measurement

End-to-end flow:
```
User Question (WS)
    ↓
[plan_search] — analyze intent, extract tickers, scope check
    ↓
[retrieve_context] — hybrid search: pgvector + BM25 → RRF + cross-encoder rerank
    ↓
[generate_answer] — build context, call LLM, stream tokens
    ↓
[evaluate_quality] — confidence score 0–1
    ├─ score ≥ 0.65 OR iter ≥ 2  →  [finalize] → return answer
    └─ score < 0.65  →  [rewrite_query] → [retrieve_context] (retry)
    ↓
Final Answer + Citations (WS)
    ↓
[LangSmith trace logged]
```

---

## Component Architecture

### 1. FastAPI Application Layer (`app/`)

**Entry Point:** `app/__init__.py` 
- Creates FastAPI instance with lifespan handlers
- Registers middleware (CORS, logging)
- Mounts all routers (chat, sessions, health)
- In production: serves React SPA from `frontend/dist`

**Startup & Lifecycle (`app/lifespan.py`)**
```python
on_startup:
  1. Create asyncpg connection pool (2–10 connections)
  2. Inject pool into database_manager
  3. Pre-compile LangGraph research agent
  4. Background: warm embedding + reranker models, build BM25 index
  
on_shutdown:
  1. Close DB pool
```

**WebSocket Handler (`app/websocket/handler.py`)**
- Manages per-connection state: session_id, conversation history
- Receives messages: `{type: "query", query: "...", web_search: bool}`
- Invokes `agent/graph/graph.py:run()` with state callbacks
- Emits status updates: `{type: "status", step: "...", message: "..."}`
- Streams tokens: `{type: "token", content: "..."}`
- Saves session & messages to DB on completion
- Submits LangSmith trace on completion (if enabled)

**Authentication (`app/auth/clerk.py`)**
- Implements Clerk JWT verification for user sessions
- **Current status:** `AUTH_DISABLED=true` (default in `config.py`)
- **Why disabled:** Local dev doesn't require authentication; allows testing without Clerk setup
- **How to enable:** Set `AUTH_DISABLED=false` in `.env` + configure `CLERK_SECRET_KEY` and `CLERK_PUBLISHABLE_KEY`
- When enabled: JWT decoded via Clerk JWKS endpoint, returns user payload; when disabled: returns anonymous user

**REST Endpoints**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness probe |
| `/chat` | POST | One-off query (non-streaming) |
| `/sessions` | GET/POST | List/create sessions |
| `/sessions/{id}` | GET/PUT/DELETE | Manage session |
| `/sessions/{id}/messages` | GET | Retrieve conversation |
| `/ws` | WebSocket | Streaming chat interface (primary) |

---

### 2. LangGraph Orchestration (`agent/graph/`)

**State Definition (`state.py`)**

`ResearchState` TypedDict contains all fields flowing through the graph:

| Field | Type | Role |
|-------|------|------|
| `question` | str | User's original query |
| `tickers` | List[str] | Extracted stock tickers (e.g., ["NVDA", "AMD"]) |
| `sub_questions` | List[str] | Decomposed analysis steps (shown as "thinking") |
| `intent` | str | Classification: "risk_factors", "valuation", "comparison", etc. |
| `query_mode` | str | "rag_only" \| "web_only" \| "hybrid" |
| `is_out_of_scope` | bool | True if question unrelated to equity research |
| `sec_chunks` | List[Dict] | Retrieved 10-K segments with metadata |
| `transcript_chunks` | List[Dict] | Retrieved earnings call segments |
| `news_results` | List[Dict] | Web search results (optional) |
| `draft_answer` | str | Generated response (raw LLM output) |
| `citations` | List[Dict] | Source references: {ticker, source, year, quarter, similarity} |
| `eval_score` | float | Confidence 0–1 (heuristic + LLM-as-judge) |
| `eval_reason` | str | Explanation of confidence score |
| `final_answer` | str | Polished response sent to user |
| `confidence` | float | Same as eval_score, exposed to frontend |
| `iteration_count` | int | Retry counter (0, 1, or 2) |
| `_token_callback` | Callable | Async function to emit tokens to WebSocket |
| `_status_callback` | Callable | Async function to emit status updates |
| `error` | Optional[str] | Error message if node fails |

**Node Definitions (`nodes.py`)**

1. **`node_analyze_question`** (`plan_search`)
   - LLM: **DeepSeek V3** (primary) or **Cerebras Qwen-3-235B** / **OpenAI GPT-4.1-mini** (fallback)
   - Classify intent (risk factors? valuation? competitor analysis?)
   - Extract company tickers
   - Decompose into sub-questions (shown to user as "thinking")
   - Route: out-of-scope? → `finalize_early` : continue

2. **`node_execute_search`** (`retrieve_context`)
   - Check semantic cache (query embedding → cosine ≥ 0.92 hit?)
   - If miss: embed query with **all-MiniLM-L6-v2** (384-dim, CPU-fast)
   - Parallel search:
     - **pgvector cosine ANN** on `ten_k_chunks` (top-20)
     - **pgvector cosine ANN** on `transcript_chunks` (top-20)
     - **BM25 keyword search** on `ten_k_chunks` (top-20)
     - **BM25 keyword search** on `transcript_chunks` (top-20)
   - **Reciprocal Rank Fusion (RRF, k=60)** merges both ranks
   - **Cross-encoder reranking** (ms-marco-TinyBERT-L-2-v2) → keep top-k chunks
   - Return: `sec_chunks`, `transcript_chunks`

3. **`node_generate_response`** (`generate_answer`)
   - Build prompt from top-k chunks + conversation history
   - Call LLM via `agent/llm/factory.py` (DeepSeek → Cerebras ��� OpenAI fallback)
   - **Model:** DeepSeek **V3** (primary, fast/cheap) or Cerebras **Qwen-3-235B** / OpenAI **GPT-4.1-mini** (fallback)
   - Stream tokens via `_token_callback`
   - Extract citations from chunks
   - Return: `draft_answer`, `citations`

4. **`node_evaluate_response`** (`evaluate_quality`)
   - **Model:** OpenAI **GPT-4o** (consistent eval scoring)
   - First: heuristic check (presence of citations, length, etc.)
   - If borderline (0.50–0.75): call LLM-as-judge for confidence
   - Return: `eval_score` (0–1), `eval_reason`
   - Track best score across iterations

5. **`node_query_rewriter`** (`rewrite_query`)
   - **Model:** DeepSeek **V3** or Cerebras / OpenAI fallback
   - If eval_score < 0.65 AND iteration < 2:
     - Broaden/rephrase query (expand synonyms, relax constraints)
     - Return: `rewritten_query`
   - Else: pass through (→ finalize)

6. **`node_finalize`** (`finalize`)
   - Format final response with citations
   - Set confidence = best_score from any iteration
   - Return: `final_answer`, `confidence`

7. **`node_finalize_early`** (`finalize_early`)
   - Query out-of-scope or error occurred
   - Return graceful message: "I can't help with that question"

**Edge Logic (`edges.py`)**

- `route_after_analysis`: out_of_scope? → finalize_early : retrieve_context
- `route_after_evaluation`: (score ≥ 0.65 OR iter ≥ 2) → finalize : rewrite_query

**Graph Builder (`graph.py`)**
```python
def build_graph():
    g = StateGraph(ResearchState)
    g.add_node("plan_search",      node_analyze_question)
    g.add_node("retrieve_context", node_execute_search)
    g.add_node("generate_answer",  node_generate_response)
    g.add_node("evaluate_quality", node_evaluate_response)
    g.add_node("rewrite_query",    node_query_rewriter)
    g.add_node("finalize",         node_finalize)
    g.add_node("finalize_early",   node_finalize_early)
    
    g.set_entry_point("plan_search")
    g.add_conditional_edges("plan_search", route_after_analysis, ...)
    g.add_edge("retrieve_context", "generate_answer")
    g.add_edge("generate_answer", "evaluate_quality")
    g.add_conditional_edges("evaluate_quality", route_after_evaluation, ...)
    g.add_edge("rewrite_query", "retrieve_context")  # retry loop
    g.add_edge("finalize", END)
    g.add_edge("finalize_early", END)
    
    return g.compile()

# Singleton instance
_graph = build_graph()

async def run(state: ResearchState) -> ResearchState:
    """Execute graph, inject callbacks, log to LangSmith."""
    return await _graph.ainvoke(state)
```

---

## RAG Pipeline Architecture

### Models Used at Each Stage

| Stage | Model | Purpose | Details |
|-------|-------|---------|---------|
| **Query Embedding** | `all-MiniLM-L6-v2` | Convert query to dense vector | 384-dim, CPU-fast, ~2ms |
| **Document Embedding** | `all-MiniLM-L6-v2` | Embed all chunks at ingest time | Same as query for consistency |
| **Semantic Search (pgvector)** | pgvector IVFFlat | ANN similarity search | Cosine similarity, top-20 candidates |
| **Keyword Search** | BM25 Okapi | Full-text matching | Parallel to pgvector, top-20 candidates |
| **Rank Fusion** | RRF (k=60) | Merge semantic + keyword results | Reciprocal Rank Fusion formula |
| **Reranking** | `ms-marco-TinyBERT-L-2-v2` | Score top-20 by relevance | Cross-encoder: final ranking → top-k |
| **Generation** | DeepSeek V3 / Cerebras / OpenAI | Generate grounded answer | Priority chain via LLMFactory |

### Search Pipeline Detail

```
Query Input
    ↓
Check Semantic Cache (cosine ≥ 0.92?)
    ├─ HIT  → return cached answer
    └─ MISS → continue
    ↓
Embed Query with all-MiniLM-L6-v2
    ↓
Parallel Search:
    ├─ pgvector (cosine similarity, top-20)
    │   ├─ ten_k_chunks
    │   └─ transcript_chunks
    │
    ├─ BM25 keyword search (top-20 each)
    │   ├─ ten_k_chunks
    │   └─ transcript_chunks
    │
    └─ Web search (Tavily, if enabled, top-10)
    ↓
Reciprocal Rank Fusion (RRF, k=60)
    → merge pgvector + BM25 ranks
    → score each by 1/(k + position)
    → deduplicate
    ↓
Cross-Encoder Rerank (ms-marco-TinyBERT-L-2-v2)
    → score top-20 by relevance
    → keep top-k for context window (dynamic budget)
    ↓
Return: sec_chunks[], transcript_chunks[], citations[]
```

**Parameters:**
- **Embedding model:** `all-MiniLM-L6-v2` (384-dim, CPU, ~2ms/query)
- **Rerank model:** `cross-encoder/ms-marco-TinyBERT-L-2-v2` (ranked on CPU)
- **RRF constant:** k=60 (reciprocal rank fusion)
- **Semantic cache threshold:** cosine ≥ 0.92
- **Output budget:** dynamic (typically top-10–20 chunks, depends on context window)

### Database Manager (`agent/rag/database_manager.py`)
- Wraps asyncpg pool (injected at startup)
- `search_chunks(query_embedding, filters)` → pgvector cosine search
- `get_semantic_cache_entry(query_embedding)` → cached Q→A lookup
- `insert_semantic_cache(...)` → save cache entry
- Connection pooling: 2–10 connections (configurable via `DB_POOL_MIN`, `DB_POOL_MAX`)

### Response Generator (`agent/rag/response_generator.py`)
- Takes top-k chunks from search
- Builds context window (system + retrieved chunks + conversation history)
- Calls `agent/llm/factory.py:create()` → LLM client
- Streams tokens via `state._token_callback`
- Extracts citations: map chunk → ticker, source, quarter, year

### Prompts (`agent/rag/prompts.py`)
- All LLM prompts as Python constants (no inline prompt engineering)
- Templates include:
  - `SYSTEM_ANALYZE_INTENT` — extract tickers, classify intent
  - `SYSTEM_GENERATE_ANSWER` — generate grounded response with citations
  - `SYSTEM_EVALUATE_CONFIDENCE` — judge response quality (heuristic first)
  - `SYSTEM_QUERY_REWRITER` — broaden/rephrase query on retry
- Single source of truth: update here, not scattered across nodes

---

## LLM Abstraction (`agent/llm/`)

**Base Client (`base.py`)**
```python
class BaseLLMClient:
    async def astream(self, messages: List[Dict]) -> AsyncGenerator[str, None]
    async def acomplete(self, prompt: str) -> str
```

**DeepSeek Client (`deepseek_client.py`)**
- API: `https://api.deepseek.com` (OpenAI-compatible)
- Model: `deepseek-chat` (DeepSeek V3, 236B MoE)
- Role: **Primary** (cheapest, no daily quota)
- Cost: $0.14/$0.28 per 1M input/output tokens

**Cerebras Client (`cerebras_client.py`)**
- API: `https://api.cerebras.ai/v1/chat/completions`
- Model: `qwen-3-235b-a22b-instruct-2507`
- Role: **Secondary** (fast, but has daily request quota)
- Raises `CerebrasRateLimitError` on 429 for factory to catch

**OpenAI Client (`openai_client.py`)**
- API: OpenAI v1
- Models: 
  - `gpt-4.1-mini` — response generation fallback
  - `gpt-4o` — evaluation (consistent scoring)
- Role: Final fallback for generation; primary for eval

**Token Tracker (`token_tracker.py`)**
- Thread-safe singleton tracking per-call token usage and USD cost
- Pricing defined for all models (DeepSeek, GPT-4.1-mini, GPT-4o, Cerebras)
- Snapshot posted to LangSmith trace after each graph execution

**Factory (`factory.py`)**
```python
class LLMFactory:
    @staticmethod
    def create() -> BaseLLMClient:
        """Route by provider priority: DeepSeek → Cerebras → OpenAI."""
        if LLM_PROVIDER == "auto":
            if DEEPSEEK_API_KEY:
                return DeepSeekClient()
            if CEREBRAS_API_KEY:
                try:
                    return CerebrasClient()  # with backoff on 429
                except RateLimitError:
                    return OpenAIClient()
            return OpenAIClient()
    
    @staticmethod
    def create_eval_llm() -> BaseLLMClient:
        """Eval LLM — tries Cerebras → DeepSeek → OpenAI in auto mode."""
```

---

## Frontend (`frontend/`)

**Stack:** React 18 + TypeScript + Vite + Tailwind CSS + framer-motion

**Pages:**
- **LandingPage:** Public home, feature grid, marketing copy
- **ChatPage:** Main interface — chat history, streaming responses, citations

**WebSocket Integration (`ChatPage.tsx`)**
```typescript
useEffect(() => {
  const ws = new WebSocket(WS_URL);
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === "token") accumulateToken(msg.content);
    if (msg.type === "status") updateStatus(msg.message);
  };
  ws.send(JSON.stringify({type: "query", query, web_search}));
}, []);
```

**Message Protocol:**
```json
/* Client → Server */
{
  "type": "query",
  "query": "What are NVIDIA's risk factors?",
  "web_search": false,
  "session_id": "uuid"
}

/* Server → Client (streaming) */
{"type": "status", "step": "plan_search", "message": "Analyzing question..."}
{"type": "token", "content": "NVIDIA"}
{"type": "token", "content": " faces"}
...
{"type": "final", "answer": "...", "confidence": 0.85, "citations": [...]}
```

---

## Data Stores

### PostgreSQL (Railway)

| Table | Fields | Purpose |
|-------|--------|---------|
| `ten_k_chunks` | id, ticker, year, text, embedding (pgvector), created_at | SEC 10-K filing chunks (27+ companies) |
| `transcript_chunks` | id, ticker, quarter, year, text, embedding, created_at | Earnings call transcripts (28+ companies) |
| `semantic_cache` | id, query_embedding, answer, score, created_at | Q→A cache (cosine ≥ 0.92 hits) |
| `sessions` | id, user_id, title, created_at, updated_at | Chat sessions |
| `messages` | id, session_id, role, content, metadata, created_at | Chat history |
| `eval_logs` | id, session_id, query, eval_score, reason, created_at | Confidence score audit trail |

**Indexes:**
- `ten_k_chunks.embedding` (pgvector, IVFFlat)
- `transcript_chunks.embedding` (pgvector, IVFFlat)
- `semantic_cache.query_embedding` (pgvector, IVFFlat)
- `sessions.user_id`
- `messages.session_id`

---

## Data Ingestion Pipeline (`scripts/ingestion/`)

**1. SEC 10-K Ingestion (`ingest_sec.py`)**

```bash
# From project root
python scripts/ingestion/ingest_sec.py --start-year 2023 --end-year 2025 --replace
```

**Other useful commands:**
```bash
# Specific tickers
python scripts/ingestion/ingest_sec.py --tickers NVDA AAPL MSFT --start-year 2023 --end-year 2025 --replace

# All from data/tickers.txt
python scripts/ingestion/ingest_sec.py --all --start-year 2023 --end-year 2025 --replace
```

**What it does:**
- Downloads SEC 10-K filings (FY2023, FY2024, FY2025)
- Chunks: 1400-char segments with 200-char overlap
- Detects sections (Item 1A Risk Factors, Item 7 MD&A, etc.)
- Embeds with **all-MiniLM-L6-v2** (384-dim)
- Stores in `ten_k_chunks` table (pgvector indexed)

**Logging:** `scripts/ingestion/logs/sec_10k/sec_YYYYMMDD_HHMMSS.log`

**Time:** 2-3 hours for all 28 tickers

---

**2. yfinance Earnings Transcripts (`ingest_yfinance.py`)**

```bash
# From project root
python scripts/ingestion/ingest_yfinance.py --start-quarter "Q1 2023" --end-quarter "Q4 2025" --replace
```

**Other useful commands:**
```bash
# Specific tickers
python scripts/ingestion/ingest_yfinance.py --tickers NVDA AAPL MSFT --start-quarter "Q1 2023" --end-quarter "Q4 2025" --replace

# From custom ticker file
python scripts/ingestion/ingest_yfinance.py --ticker-file data/tickers.txt --start-quarter "Q1 2023" --end-quarter "Q4 2025" --replace
```

**What it does:**
- Fetches quarterly earnings summaries from yfinance (free, no API key)
- Each quarter = 1 chunk with revenue, margins, EPS, key metrics
- Embeds with **all-MiniLM-L6-v2** (384-dim)
- Stores in `transcript_chunks` table (pgvector indexed)

**Logging:** `scripts/ingestion/logs/yfinance_transcripts/transcript_YYYYMMDD_HHMMSS.log`

**Time:** 20-30 min

---

## Evaluation Suite (`evals/qa_eval/`)

**Comprehensive offline evaluation (8 metrics)**

### Phase 1: Ground Truth Generation
```bash
# From project root or evals/qa_eval/
python evals/qa_eval/generate_ground_truth.py --input "question_vN.txt" --full
```

**What it does:**
1. Load `question_vN.txt` (JSON with categories, questions, empty `ground_truth_map`)
2. For each question:
   - Extract tickers using hardcoded TICKER_MAP (e.g., "nvidia" → "NVDA")
   - Query DB: pgvector + BM25 hybrid search on `ten_k_chunks` + `transcript_chunks` (DB only, no web)
   - Call **GPT-4o** to synthesize ground truth + 5 key verifiable facts from chunks
3. Populate `ground_truth_map` in-place in question file

### Phase 2: Evaluation Execution
```bash
# Smoke test (first 3 questions)
python evals/qa_eval/run_eval.py --smoke --input "question_vN.txt"

# Full eval (all ~20 questions)
python evals/qa_eval/run_eval.py --full --input "question_vN.txt"
```

**Metrics Computed (M1–M8):**

| Metric | Definition | LLM Required |
|--------|-----------|--------------|
| **M1 (Factual correctness)** | % of key_facts found in answer (fuzzy match) | No |
| **M2 (Faithfulness)** | RAGAS — answer faithful to retrieved context | Yes (GPT-4o) |
| **M3 (Retrieval recall)** | % of key_facts found in top-K chunks | No |
| **M4 (Context precision)** | RAGAS — retrieved chunks are relevant | Yes (GPT-4o) |
| **M6 (Routing accuracy)** | web_search flag alignment with query_mode | No |
| **M7 (Judge score)** | LLM judge verdict (pass/partial/fail) | Yes (GPT-4o) |
| **M8 (Latency + calibration)** | Pipeline latency + confidence calibration RMSE | No |
| **Average** | mean(M1, M2, M3, M4, M6, M7) | — |

**Output:**
- `evals/qa_eval/results/<timestamp>/NN_category_question.json` — Per-question results (all metrics + reasoning)
- `evals/qa_eval/results/<timestamp>/_summary.json` — Aggregated scores (category breakdowns, average)
- `evals/qa_eval/results/<timestamp>/_analysis.md` — Iteration log (top/bottom performers, category insights)
- `evals/qa_eval/docs/IMPROVEMENT_SUMMARY_*.md` — Historical tracking (score vs baseline)
- `evals/qa_eval/docs/DEMO_QUESTIONS_*.md` — Top 5 questions with full reasoning (if score ≥ 0.70)

**Time:** ~5-10 min (smoke), ~20-30 min (full eval)

### Phase 3: Iteration (If Needed)
```bash
# After fixes to prompts.py or question file, re-run:
python evals/qa_eval/run_eval.py --full --input "question_vN.txt" --set-baseline
```

**`--set-baseline` flag:** Writes results to `evals/baseline.json` for tracking across iterations
**Threshold:** Iterate if `average < 0.72`; max 1 iteration per eval cycle

---

## Observability & Tracing

### LangSmith Integration
- Optional distributed tracing (disabled by default; enable via `LANGCHAIN_TRACING_V2=true`)
- Emits trace for each query execution:
  - Full graph flow captured as nested spans (node names are LangSmith span labels)
  - LLM calls tracked: model, tokens, cost
  - Token cost posted to LangSmith run metadata via `RunCollectorCallbackHandler`
  - View in LangSmith dashboard for debugging

### Logging (`app/utils/logging.py`)
- Format: `[module_tag] message` (e.g., `[search] Embedding query...`)
- Log level: `LOG_LEVEL` env (default: INFO)
- Tags: `[ws]`, `[graph]`, `[search]`, `[llm]`, `[node]`, `[rag]`

---

## Configuration

All env vars read in `config.py` via pydantic-settings:

```python
# Core
DATABASE_URL = postgresql://...
ENVIRONMENT = production | development
LOG_LEVEL = INFO | DEBUG | WARNING

# LLM
DEEPSEEK_API_KEY = ...
CEREBRAS_API_KEY = ...
OPENAI_API_KEY = ...
LLM_PROVIDER = auto | deepseek | cerebras | openai

# Data sources
TAVILY_API_KEY = ...  # optional web search

# Auth
AUTH_DISABLED = true | false                  # true for local dev (default)
CLERK_SECRET_KEY = ...
CLERK_PUBLISHABLE_KEY = ...

# Observability (LangSmith)
LANGCHAIN_TRACING_V2 = false | true           # Enable LangSmith
LANGSMITH_API_KEY = lsv2_...
LANGSMITH_PROJECT = alphalens

# Feature flags
CACHE_DISABLED = false  # disable semantic cache during eval

# CORS
CORS_ORIGINS = http://localhost:3000,...
```

---

## Deployment

**Production Build:**
1. Run ingestion scripts (`scripts/ingestion/`) once locally or on server
2. `npm run build` (frontend) → `frontend/dist`
3. `python -m uvicorn app:app --host 0.0.0.0 --port 8000`
4. FastAPI auto-serves SPA from `frontend/dist`

**Railway Deployment:**
- `Procfile`: `web: python -m uvicorn app:app --host 0.0.0.0 --port $PORT`
- `railway.toml`: healthcheck `/health`, restart on failure
- Env vars configured in Railway dashboard
- Database: PostgreSQL on Railway (Railway PostgreSQL add-on)

**Local Development:**
```bash
# Terminal 1: Backend
python -m uvicorn app:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev  # port 5175, proxies /api + /ws to :8000
```

