"""WebSocket connection manager — tracks active connections by session."""
import logging
from typing import Dict
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self._connections[session_id] = ws
        logger.info(f"[ws] connected session={session_id} total={len(self._connections)}")

    def disconnect(self, session_id: str):
        self._connections.pop(session_id, None)
        logger.info(f"[ws] disconnected session={session_id}")

    async def send(self, session_id: str, data: dict):
        ws = self._connections.get(session_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.warning(f"[ws] send failed session={session_id}: {e}")
                self.disconnect(session_id)

    async def broadcast(self, data: dict):
        for sid, ws in list(self._connections.items()):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(sid)


manager = ConnectionManager()
