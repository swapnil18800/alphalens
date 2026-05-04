"""
Session management — persists conversation threads per user.

GET    /sessions           → list sessions (anonymous-safe)
POST   /sessions           → create new session
GET    /sessions/{id}      → get session + messages
DELETE /sessions/{id}      → delete session
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.auth.clerk import get_current_user
from agent.rag import database_manager as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Chat"


@router.get("")
async def list_sessions(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    # Anonymous / AUTH_DISABLED: sessions stored with user_id IS NULL
    if user_id in ("anonymous", "", None):
        rows = await db.fetch(
            "SELECT id, title, created_at, updated_at, message_count "
            "FROM sessions WHERE user_id IS NULL ORDER BY updated_at DESC LIMIT 50"
        )
    else:
        rows = await db.fetch(
            "SELECT id, title, created_at, updated_at, message_count "
            "FROM sessions WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 50",
            user_id,
        )
    return {"sessions": [dict(r) for r in rows]}


@router.post("")
async def create_session(req: CreateSessionRequest, user: dict = Depends(get_current_user)):
    sid = str(uuid.uuid4())
    user_id = user["id"]
    db_user_id = None if user_id in ("anonymous", "", None) else user_id
    await db.execute(
        "INSERT INTO sessions (id, user_id, title) VALUES ($1, $2, $3)",
        sid, db_user_id, req.title,
    )
    return {"id": sid, "title": req.title}


@router.get("/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    if user_id in ("anonymous", "", None):
        session = await db.fetch(
            "SELECT id, title, created_at FROM sessions WHERE id = $1 AND user_id IS NULL",
            session_id,
        )
    else:
        session = await db.fetch(
            "SELECT id, title, created_at FROM sessions WHERE id = $1 AND user_id = $2",
            session_id, user_id,
        )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await db.fetch(
        "SELECT role, content, metadata, created_at FROM messages "
        "WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    return {
        "session": dict(session[0]),
        "messages": [dict(m) for m in messages],
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    if user_id in ("anonymous", "", None):
        result = await db.execute(
            "DELETE FROM sessions WHERE id = $1 AND user_id IS NULL",
            session_id,
        )
    else:
        result = await db.execute(
            "DELETE FROM sessions WHERE id = $1 AND user_id = $2",
            session_id, user_id,
        )
    return {"deleted": result == "DELETE 1"}


async def save_message(session_id: str, role: str, content: str, metadata: dict = None):
    """Helper — called from WebSocket handler after each turn."""
    import json
    await db.execute(
        "INSERT INTO messages (session_id, role, content, metadata) VALUES ($1, $2, $3, $4)",
        session_id, role, content, json.dumps(metadata or {}),
    )
    await db.execute(
        "UPDATE sessions SET updated_at = NOW(), message_count = message_count + 1 WHERE id = $1",
        session_id,
    )
