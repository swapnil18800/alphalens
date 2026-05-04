"""WebSocket route definition."""
from fastapi import APIRouter, WebSocket, Query
from typing import Optional
from .handler import handle_connection

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    session_id: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time chat.
    Connect: ws://localhost:8000/ws?session_id=<uuid>
    """
    await handle_connection(ws, session_id)
