"""
Core WebSocket chat handler.

Protocol (JSON messages):
  Client → Server:
    { "type": "query",  "question": "...", "session_id": "...", "web_search": false }
    { "type": "cancel" }
    { "type": "ping" }
  Server → Client:
    { "type": "ack",    "session_id": "..." }
    { "type": "status", "step": "search", "message": "Searching NVDA filings…" }
    { "type": "token",  "token": "..." }           ← streaming token
    { "type": "answer", "answer": "...", "citations": [...], "confidence": 0.9, "reasoning": [...] }
    { "type": "error",  "detail": "..." }
    { "type": "cancelled" }
"""
import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from .manager import manager
from agent.graph import graph as research
from app.utils.database import get_pool

logger = logging.getLogger(__name__)

MAX_SESSIONS = 10       # base per-user limit; anonymous users share this pool


async def _load_history(session_id: str, limit: int = 10) -> list:
    try:
        pool = get_pool()
        rows = await pool.fetch(
            "SELECT role, content FROM messages "
            "WHERE session_id = $1 ORDER BY created_at DESC LIMIT $2",
            session_id, limit,
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    except Exception:
        return []


async def _generate_title(question: str) -> str:
    """Generate a concise 4-6 word session title from the first question."""
    try:
        from agent.llm.factory import LLMFactory
        llm = LLMFactory.create()
        raw = await llm.acomplete(
            f"Write a 4-6 word session title for this question. No quotes, no periods, title case only: {question[:200]}",
            max_tokens=20,
        )
        title = raw.strip().strip('"').strip("'").strip('.')[:60]
        return title or question[:60]
    except Exception:
        return question[:60]


async def _update_session_title(pool, session_id: str, question: str):
    try:
        title = await _generate_title(question)
        await pool.execute(
            "UPDATE sessions SET title = $1 WHERE id = $2",
            title, session_id,
        )
    except Exception as e:
        logger.debug(f"[ws] title update failed: {e}")


async def _enforce_session_limit(pool, db_user_id):
    """Delete oldest sessions beyond MAX_SESSIONS for this user."""
    try:
        if db_user_id is None:
            count = await pool.fetchval("SELECT COUNT(*) FROM sessions WHERE user_id IS NULL")
            if count >= MAX_SESSIONS:
                await pool.execute(
                    "DELETE FROM sessions WHERE id IN ("
                    "  SELECT id FROM sessions WHERE user_id IS NULL"
                    "  ORDER BY updated_at ASC LIMIT $1"
                    ")",
                    count - MAX_SESSIONS + 1,
                )
        else:
            count = await pool.fetchval("SELECT COUNT(*) FROM sessions WHERE user_id = $1", db_user_id)
            if count >= MAX_SESSIONS:
                await pool.execute(
                    "DELETE FROM sessions WHERE id IN ("
                    "  SELECT id FROM sessions WHERE user_id = $1"
                    "  ORDER BY updated_at ASC LIMIT $2"
                    ")",
                    db_user_id, count - MAX_SESSIONS + 1,
                )
    except Exception as e:
        logger.debug(f"[ws] session limit enforce failed: {e}")


async def _ensure_session(session_id: str, user_id: str, question: str):
    try:
        pool = get_pool()
        db_user_id = None if user_id in ("anonymous", "", None) else user_id

        existing = await pool.fetchrow("SELECT id FROM sessions WHERE id = $1", session_id)
        if existing:
            return  # session already created — don't overwrite title on subsequent turns

        await _enforce_session_limit(pool, db_user_id)

        title = question[:60].strip()
        await pool.execute(
            """INSERT INTO sessions (id, user_id, title, message_count)
               VALUES ($1, $2, $3, 0)
               ON CONFLICT (id) DO NOTHING""",
            session_id, db_user_id, title,
        )
        # Generate smart title in background while research runs
        asyncio.create_task(_update_session_title(pool, session_id, question))
    except Exception as e:
        logger.warning(f"[ws] ensure_session failed: {e}")


async def _save_turn(session_id: str, question: str, answer: str, meta: dict):
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata) VALUES ($1,'user',$2,$3)",
                session_id, question, json.dumps({}),
            )
            await conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata) VALUES ($1,'assistant',$2,$3)",
                session_id, answer, json.dumps(meta),
            )
            await conn.execute(
                "UPDATE sessions SET updated_at=NOW(), message_count=message_count+2 WHERE id=$1",
                session_id,
            )
    except Exception as e:
        logger.warning(f"[ws] save_turn failed: {e}")


async def handle_connection(ws: WebSocket, session_id: Optional[str] = None, user_id: str = "anonymous"):
    sid = session_id or str(uuid.uuid4())
    await manager.connect(sid, ws)

    _current_task: Optional[asyncio.Task] = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send(sid, {"type": "error", "detail": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "query")

            if msg_type == "ping":
                await manager.send(sid, {"type": "pong"})
                continue

            if msg_type == "cancel":
                if _current_task and not _current_task.done():
                    _current_task.cancel()
                    logger.info(f"[ws] cancelled session={sid}")
                # Always acknowledge cancel so frontend can reset UI
                await manager.send(sid, {"type": "cancelled"})
                continue

            if msg_type != "query":
                await manager.send(sid, {"type": "error", "detail": f"Unknown type: {msg_type}"})
                continue

            question = (msg.get("question") or msg.get("query") or "").strip()
            if not question:
                await manager.send(sid, {"type": "error", "detail": "question is required"})
                continue

            if _current_task and not _current_task.done():
                _current_task.cancel()

            # user_id is set at connection-time via Clerk JWT verification;
            # fall back to anonymous only if not already authenticated
            conn_user_id = msg.get("user_id") if user_id == "anonymous" else user_id
            user_id      = conn_user_id or "anonymous"
            use_session  = msg.get("session_id", sid)
            web_search  = bool(msg.get("web_search", False))

            await manager.send(sid, {"type": "ack", "session_id": use_session})

            await _ensure_session(use_session, user_id, question)
            history = await _load_history(use_session)

            reasoning_steps: list[dict] = []

            async def status_callback(step: str, message: str, chunks=None):
                entry = {"step": step, "message": message}
                if chunks:
                    entry["chunks"] = chunks
                reasoning_steps.append(entry)
                payload = {"type": "status", "step": step, "message": message}
                if chunks:
                    payload["chunks"] = chunks
                await manager.send(sid, payload)

            async def token_callback(token: str):
                await manager.send(sid, {"type": "token", "token": token})

            async def _run_research():
                return await research.run(
                    question=question,
                    user_id=user_id,
                    session_id=use_session,
                    conversation_history=history,
                    status_callback=status_callback,
                    token_callback=token_callback,
                    web_search=web_search,
                )

            try:
                _current_task = asyncio.create_task(_run_research())
                result = await _current_task

                answer     = result.get("final_answer", "")
                citations  = result.get("citations", [])
                confidence = round(result.get("confidence", 0.0), 2)

                await manager.send(sid, {
                    "type":       "answer",
                    "answer":     answer,
                    "citations":  citations,
                    "confidence": confidence,
                    "reasoning":  reasoning_steps,
                    "session_id": use_session,
                })

                await _save_turn(use_session, question, answer, {
                    "citations":  citations,
                    "confidence": confidence,
                    "reasoning":  reasoning_steps,
                })

            except asyncio.CancelledError:
                logger.info(f"[ws] research cancelled session={sid}")
            except Exception as e:
                logger.error(f"[ws] graph error: {e}", exc_info=True)
                await manager.send(sid, {
                    "type":   "error",
                    "detail": "Research agent encountered an error. Please try again.",
                })
            finally:
                _current_task = None

    except WebSocketDisconnect:
        manager.disconnect(sid)
    except Exception as e:
        logger.error(f"[ws] unexpected error session={sid}: {e}", exc_info=True)
        manager.disconnect(sid)
