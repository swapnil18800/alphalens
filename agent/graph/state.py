"""
ResearchState — the single TypedDict that flows through every LangGraph node.
Every node receives this state and returns a dict of keys it updates.
"""
from typing import TypedDict, Optional, List, Dict, Any


class ResearchState(TypedDict):
    # ── Input ──────────────────────────────────────────────
    question: str
    user_id: str
    session_id: str
    conversation_history: List[Dict[str, Any]]

    # ── Analysis (Node 1: analyze_question) ───────────────
    tickers: List[str]               # extracted tickers e.g. ["NVDA", "AMD"]
    years: List[int]                 # explicit years extracted from query (e.g. [2024]); empty if none
    sub_questions: List[str]         # decomposed sub-questions shown as "thinking"
    intent: str                      # e.g. "risk_factors", "revenue", "comparison"
    query_mode: str                  # "rag_only" | "web_only" | "hybrid"
    include_news: bool               # derived from query_mode; kept for backward compat
    is_out_of_scope: bool
    iteration_count: int

    # ── Query rewriter (retry path only) ──────────────────
    rewritten_query: Optional[str]   # broadened/reworded query for retry retrieval

    # ── Search results (Nodes 2–3) ────────────────────────
    sec_chunks: List[Dict[str, Any]]
    transcript_chunks: List[Dict[str, Any]]
    news_results: List[Dict[str, Any]]
    cache_hit: bool                  # True if semantic cache returned a result

    # ── Generation (Node 4) ───────────────────────────────
    draft_answer: Optional[str]
    citations: List[Dict[str, Any]]

    # ── Evaluation (Node 5) ───────────────────────────────
    eval_score: float                # 0.0 – 1.0 faithfulness score
    eval_reason: Optional[str]
    best_score: float                # highest eval_score seen across all iterations
    best_answer: Optional[str]       # draft_answer that achieved best_score
    best_citations: List[Dict[str, Any]]

    # ── Output (Node 6) ────────────────────────────────────
    final_answer: Optional[str]
    confidence: float                # same as best_score, exposed to frontend

    # ── Internal ───────────────────────────────────────────
    _status_callback: Optional[Any]  # async callable(step, message) for WS status updates
    _token_callback: Optional[Any]   # async callable(token: str) for streaming tokens
    _web_search: bool                # user-requested web search toggle
    error: Optional[str]
