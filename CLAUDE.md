# AlphaLens — Claude Code Instructions

## Project

Agentic AI equity research assistant. Users ask financial questions via WebSocket; a LangGraph pipeline retrieves context from SEC 10-K filings and earnings transcripts (pgvector + BM25 hybrid search), generates a grounded answer with citations, self-evaluates, and optionally retries.

## Stack

- **Backend:** FastAPI + asyncpg + LangGraph (Python 3.14, `.venv`)
- **Frontend:** React 18 + Vite + TypeScript + Tailwind + framer-motion (`frontend/`)
- **DB:** PostgreSQL on Railway (remote) with pgvector extension
- **LLM:** DeepSeek V3 (primary) + Cerebras Qwen-3-235B (secondary) + OpenAI GPT-4.1-mini (fallback)
- **Search:** all-MiniLM-L6-v2 embeddings (384-dim) + BM25Okapi + RRF fusion + cross-encoder rerank
- **Auth:** Clerk wired but bypassed (`AUTH_DISABLED=true`)
- **Observability:** LangSmith (optional, via `LANGCHAIN_TRACING_V2=true`)

## Run Commands

```bash
# Backend (from project root, activates .venv)
python -m uvicorn app:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm run dev     # port 5175

# Vite proxies /api and /ws to localhost:8000 (see vite.config.ts)
```

## Architecture (quick reference)

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full diagram and component map.

```
WebSocket /ws → handler.py → LangGraph research_graph
  analyze_question → execute_search → generate_response → evaluate_response
                         ↑                                      │
                         └── query_rewriter ←── score < 0.65 ──┘  (max 2 retries)
```

**Key files by subsystem:**

| Subsystem | Entry point | Details |
|-----------|-------------|---------|
| App factory | `app/__init__.py` | FastAPI instance, middleware, routes |
| WS handler | `app/websocket/handler.py` | Session mgmt, streaming protocol |
| Graph orchestration | `agent/graph/graph.py` | `build_graph()`, `run()` |
| Graph nodes | `agent/graph/nodes.py` | 6 async nodes (analyze, search, generate, eval, rewrite, finalize) |
| Graph state | `agent/graph/state.py` | `ResearchState` TypedDict |
| RAG search | `agent/rag/search_engine.py` | Hybrid retrieval pipeline |
| RAG prompts | `agent/rag/prompts.py` | All LLM prompts in one file |
| Response gen | `agent/rag/response_generator.py` | Builds context, calls LLM, streams tokens |
| LLM factory | `agent/llm/factory.py` | Provider priority: DeepSeek → Cerebras → OpenAI |
| Token tracker | `agent/llm/token_tracker.py` | Per-call token usage + cost tracking |
| DB manager | `agent/rag/database_manager.py` | asyncpg pool + `search_chunks()` |
| Config | `config.py` | pydantic-settings, reads `.env` |
| Frontend chat | `frontend/src/pages/ChatPage.tsx` | WS lifecycle, message state, UI |
| Frontend types | `frontend/src/lib/api.ts` | WS message types, API calls |

See [docs/DIRECTORY_STRUCTURE.md](docs/DIRECTORY_STRUCTURE.md) for full tree.

## Working Rules

### Before any change
1. Read the file(s) you're about to modify — never edit blind
2. Understand the data flow through the change point (trace from WS handler → graph → node → search/LLM)
3. Check if related state exists in `ResearchState` (state.py) before adding fields

### Code modification
- **Minimal diffs only.** Fix the bug or add the feature — don't refactor surroundings
- **Never rewrite entire files** when a targeted edit suffices
- **One concern per change.** Don't mix frontend fixes with backend logic or RAG tuning
- **Prompts live in `agent/rag/prompts.py`** — never inline LLM prompts elsewhere
- **LLM client creation goes through `LLMFactory`** — never instantiate clients directly

### Backend
- All DB access through `agent/rag/database_manager.py` (RAG) or `app/utils/database.py` (pool lifecycle)
- WebSocket protocol is documented at top of `handler.py` — any new message type must follow the same JSON shape
- `_status_callback` and `_token_callback` are threaded through state — use `await _emit()` in nodes
- Config comes from `config.py` (pydantic-settings) — add new env vars there, not ad-hoc `os.getenv`

### RAG pipeline
- Search pipeline: embed → cache check → pgvector + BM25 parallel → RRF merge → cross-encoder rerank
- Chunk budget is dynamic in `node_execute_search` — don't hardcode limits
- BM25 index is built once at startup from DB; pgvector is queried live
- Semantic cache threshold: cosine >= 0.92 (in `search_engine.py`)
- Eval uses heuristic first, LLM-as-judge only for borderline (0.50-0.75) scores on first iteration

### Frontend
- WS connection in `ChatPage.tsx` uses `useCallback([], [])` — stable, no stale closures
- `sessionIdRef` mirrors `sessionId` state to avoid stale refs inside WS handlers
- Token streaming: backend sends `{type: "token"}`, frontend accumulates in `message.content`
- After any UI change, start dev server and visually verify in browser before reporting done

### Debugging
- Backend logs use `[tag]` prefixed format (e.g., `[node]`, `[search]`, `[ws]`)
- Check `handler.py` first for WS issues — it has the full message lifecycle
- For RAG quality issues: check prompts.py, then search_engine.py chunk retrieval, then response_generator.py formatting
- For streaming issues: trace token_callback from handler.py → graph.run() → response_generator.generate() → llm.astream()

### Common failure modes to avoid
- **Hallucinating file paths or functions** — always glob/grep to verify before referencing
- **Editing state.py without updating nodes** — every ResearchState field must be initialized in `graph.py:run()`
- **Breaking WS protocol** — handler.py, ChatPage.tsx, and api.ts must stay in sync on message shapes
- **Prompt drift** — all prompts are in prompts.py; don't scatter them across files

## Environment

```
# Required in .env
DATABASE_URL=postgresql://...
CEREBRAS_API_KEY=...
OPENAI_API_KEY=...        # fallback

# Optional
TAVILY_API_KEY=...        # enables web search
LANGFUSE_SECRET_KEY=...   # enables observability
LANGFUSE_PUBLIC_KEY=...
LLM_PROVIDER=cerebras     # or openai, auto
AUTH_DISABLED=true
```

## DB Tables

| Table | Purpose |
|-------|---------|
| `ten_k_chunks` | SEC 10-K filing chunks with embeddings (27 companies) |
| `transcript_chunks` | Earnings call transcript chunks (28 companies, sparse: 5/company) |
| `sessions` | Chat sessions (id, user_id, title, timestamps) |
| `messages` | Chat messages (session_id, role, content, metadata JSON) |
| `semantic_cache` | Q→A cache with query embeddings for fast lookup |
| `eval_logs` | Evaluation score history |
| `users` | User records (unused when AUTH_DISABLED=true) |
