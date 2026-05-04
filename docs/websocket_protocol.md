# WebSocket Protocol

## Connection

```
ws://localhost:8000/ws[?session_id=UUID]
```

If `session_id` is omitted, server generates one. Connection persists for the session lifetime.

## Client → Server Messages

| Type | Fields | Description |
|------|--------|-------------|
| `query` | `question`, `session_id?`, `user_id?`, `web_search?` | Start research |
| `cancel` | — | Cancel current research task |
| `ping` | — | Keep-alive |

## Server → Client Messages

| Type | Fields | Description |
|------|--------|-------------|
| `ack` | `session_id` | Query accepted, session confirmed |
| `status` | `step`, `message`, `chunks?` | Progress update from graph nodes |
| `token` | `token` | Streaming token from LLM response |
| `answer` | `answer`, `citations`, `confidence`, `reasoning`, `session_id` | Final result |
| `error` | `detail` | Error message |
| `cancelled` | — | Confirms cancellation |
| `pong` | — | Ping response |

## Message flow for a query

```
Client: {"type": "query", "question": "What was NVDA revenue?"}
Server: {"type": "ack", "session_id": "uuid-here"}
Server: {"type": "status", "step": "analyze", "message": "Reading your question…"}
Server: {"type": "status", "step": "search", "message": "Searching SEC filings…", "chunks": [...]}
Server: {"type": "status", "step": "generate", "message": "Synthesizing answer…"}
Server: {"type": "token", "token": "NVIDIA"}
Server: {"type": "token", "token": "'s revenue"}
...
Server: {"type": "status", "step": "evaluate", "message": "Quality score: 82%…"}
Server: {"type": "status", "step": "finalize", "message": "Answer ready…"}
Server: {"type": "answer", "answer": "...", "citations": [...], "confidence": 0.82, "reasoning": [...]}
```

## Status step values

`analyze` → `decompose` (if multi-sub-question) → `search` → `generate` → `evaluate` → `finalize`

On retry: `rewrite` → `search_retry` → `generate` → `evaluate` → `finalize`

## Cancellation

Client sends `{"type": "cancel"}`. Server cancels the asyncio task and sends `{"type": "cancelled"}`.
Frontend waits for `cancelled` ACK before clearing UI state.

## Session management

- Sessions auto-created on first query (`_ensure_session` in handler.py)
- Title generated async via LLM after session creation
- Max 10 sessions per anonymous user pool; oldest deleted on overflow
- Messages saved after each complete turn (user + assistant)

## Files involved

- Backend: `app/websocket/handler.py` (protocol), `app/websocket/manager.py` (connection pool), `app/websocket/routes.py` (route)
- Frontend: `frontend/src/pages/ChatPage.tsx` (WS lifecycle), `frontend/src/lib/api.ts` (message types), `frontend/src/lib/config.ts` (URL)
