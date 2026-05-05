"""WebSocket route definition."""
import logging
from fastapi import APIRouter, WebSocket, Query
from typing import Optional
from .handler import handle_connection
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    session_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    anon_id: Optional[str] = Query(None),
):
    """
    Connect: ws://host/ws?session_id=<uuid>&token=<clerk_jwt>&anon_id=<anon_uuid>
    - token: Clerk JWT for authenticated users
    - anon_id: sessionStorage UUID for anonymous users (scopes their sessions)
    """
    user_id = "anonymous"
    user_payload: dict | None = None
    if not settings.AUTH_DISABLED and token:
        try:
            from app.auth.clerk import _verify_clerk_token
            user_payload = await _verify_clerk_token(token)
            user_id = user_payload.get("id", "anonymous")
        except Exception as e:
            logger.debug(f"[ws] token verify failed, using anon: {e}")

    # Scope anonymous users to their sessionStorage ID
    if user_id == "anonymous" and anon_id and anon_id.startswith("anon_"):
        user_id = anon_id[:64]

    # Upsert authenticated users into Supabase users table on each connection
    if user_payload and user_id != "anonymous" and not user_id.startswith("anon_"):
        try:
            from app.utils.database import get_pool
            from .handler import _upsert_user
            await _upsert_user(get_pool(), user_payload)
        except Exception as e:
            logger.debug(f"[ws] user upsert failed: {e}")

    await handle_connection(ws, session_id, user_id=user_id)
