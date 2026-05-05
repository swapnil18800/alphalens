"""
Session management — persists conversation threads per user.

GET    /sessions           → list sessions (anonymous-safe)
POST   /sessions           → create new session
GET    /sessions/{id}      → get session + messages
DELETE /sessions/{id}      → delete session
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from app.auth.clerk import get_optional_user
from agent.rag import database_manager as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Chat"


def _resolve_user_id(user: dict | None, anon_id: str | None) -> str | None:
    """Return the DB user_id to use for session queries.
    Authenticated users → their Clerk ID.
    Anonymous users → the anon_ prefix ID from sessionStorage (if valid), else None.
    """
    uid = (user or {}).get("id", "")
    if uid and uid not in ("anonymous", ""):
        return uid
    if anon_id and anon_id.startswith("anon_"):
        return anon_id[:64]
    return None


@router.get("")
async def list_sessions(
    user: Optional[dict] = Depends(get_optional_user),
    x_anon_id: Optional[str] = Header(None),
):
    db_uid = _resolve_user_id(user, x_anon_id)
    if db_uid is None:
        return {"sessions": []}
    rows = await db.fetch(
        "SELECT id, title, created_at, updated_at, message_count "
        "FROM sessions WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 50",
        db_uid,
    )
    return {"sessions": [dict(r) for r in rows]}


@router.post("")
async def create_session(
    req: CreateSessionRequest,
    user: Optional[dict] = Depends(get_optional_user),
    x_anon_id: Optional[str] = Header(None),
):
    sid = str(uuid.uuid4())
    db_uid = _resolve_user_id(user, x_anon_id)
    await db.execute(
        "INSERT INTO sessions (id, user_id, title) VALUES ($1, $2, $3)",
        sid, db_uid, req.title,
    )
    return {"id": sid, "title": req.title}


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    user: Optional[dict] = Depends(get_optional_user),
    x_anon_id: Optional[str] = Header(None),
):
    db_uid = _resolve_user_id(user, x_anon_id)
    if db_uid:
        session = await db.fetch(
            "SELECT id, title, created_at FROM sessions WHERE id = $1 AND user_id = $2",
            session_id, db_uid,
        )
    else:
        session = await db.fetch(
            "SELECT id, title, created_at FROM sessions WHERE id = $1",
            session_id,
        )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await db.fetch(
        "SELECT role, content, metadata, created_at FROM messages "
        "WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    return {"session": dict(session[0]), "messages": [dict(m) for m in messages]}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: Optional[dict] = Depends(get_optional_user),
    x_anon_id: Optional[str] = Header(None),
):
    db_uid = _resolve_user_id(user, x_anon_id)
    if db_uid:
        result = await db.execute(
            "DELETE FROM sessions WHERE id = $1 AND user_id = $2",
            session_id, db_uid,
        )
    else:
        result = await db.execute("DELETE FROM sessions WHERE id = $1", session_id)
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
