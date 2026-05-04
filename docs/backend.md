# Backend

## Stack

FastAPI + asyncpg + LangGraph + pydantic-settings. Python 3.14, virtualenv at `.venv`.

## Entry point

`app/__init__.py` creates the FastAPI instance. Run with:
```bash
python -m uvicorn app:app --reload --port 8000
```

## Startup lifecycle (lifespan.py)

1. `setup_logging()` — configures from `LOG_LEVEL` env
2. `create_pool()` — asyncpg connection pool to Railway PostgreSQL
3. LangFuse client init (optional)
4. `research_graph` import — compiles LangGraph at import time
5. Background tasks: embedding model warm-up + BM25 index build

## Routing (routes.py)

| Route | Method | Handler | Purpose |
|-------|--------|---------|---------|
| `/health` | GET | `routers/health.py` | Health check + DB status |
| `/chat` | POST | `routers/chat.py` | REST alternative to WS |
| `/companies` | GET | `routers/companies.py` | List companies from DB |
| `/screener/query` | POST | `routers/screener.py` | NL→SQL screener |
| `/sessions` | GET | `routers/sessions.py` | List user sessions |
| `/sessions/{id}` | GET/DELETE | `routers/sessions.py` | Get/delete session with messages |
| `/ws` | WebSocket | `websocket/routes.py` | Primary chat interface |

## LLM factory (agent/llm/factory.py)

`LLMFactory.create()` returns the best available client:
- `LLM_PROVIDER=cerebras` → `_CerebrasWithFallback` (tries Cerebras, falls back to OpenAI on 429)
- `LLM_PROVIDER=openai` → `OpenAIClient` directly
- `LLM_PROVIDER=auto` → auto-detect from available API keys

`LLMFactory.create_eval_llm()` — prefers Cerebras for fast eval (low output tokens).

All clients implement `BaseLLMClient`: `acomplete()`, `astream()`, `complete()`.

## Config (config.py)

Uses pydantic-settings `BaseSettings` reading from `.env`. All env vars documented there.
Add new settings to `config.py` — never use raw `os.getenv()` for app config.

## Screener (agent/screener/engine.py)

Separate from the RAG pipeline. Converts natural language to SQL via LLM, executes against a local DuckDB file with company financial metrics. Used by the `/screener` page.

## Database

Two pool references exist:
- `app/utils/database.py` — pool lifecycle (`create_pool`, `close_pool`, `get_pool`)
- `agent/rag/database_manager.py` — RAG-specific queries (`search_chunks`, `list_companies`, `fetch`, `execute`)

Both share the same pool (injected at startup via `set_pool()`).
