"""
REST chat endpoint (alternative to WebSocket — useful for simple clients).
POST /chat  →  { question, session_id?, history? }  →  { answer, citations, confidence }
"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.auth.clerk import get_optional_user
from agent.graph import graph as research_graph

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = "default"
    history: Optional[List[Dict[str, Any]]] = []


class ChatResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]
    confidence: float
    session_id: str


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: Optional[dict] = Depends(get_optional_user)):
    user_id = (user or {}).get("id", "anonymous")
    session_id = req.session_id or "default"

    result = await research_graph.run(
        question=req.question,
        user_id=user_id,
        session_id=session_id,
        conversation_history=req.history or [],
    )

    return ChatResponse(
        answer=result.get("final_answer", ""),
        citations=result.get("citations", []),
        confidence=round(result.get("confidence", 0.0), 2),
        session_id=session_id,
    )
