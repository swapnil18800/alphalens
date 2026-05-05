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
):
    """
    WebSocket endpoint for real-time chat.
    Connect: ws://localhost:8000/ws?session_id=<uuid>&token=<clerk_jwt>
    The token is optional; without it the connection is anonymous.
    """
    user_id = "anonymous"
    if not settings.AUTH_DISABLED and token:
        try:
            from app.auth.clerk import _verify_clerk_token
            user = await _verify_clerk_token(token)
            user_id = user.get("id", "anonymous")
            logger.debug(f"[ws] authenticated user: {user_id}")
        except Exception as e:
            logger.debug(f"[ws] token verification failed, using anonymous: {e}")
    await handle_connection(ws, session_id, user_id=user_id)
