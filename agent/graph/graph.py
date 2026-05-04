"""
Assembles and compiles the LangGraph research agent.

Graph topology (node names match LangSmith trace spans):

  [plan_search]
       │
       ├─ out_of_scope / error ──► [finalize_early] ──► END
       │
       └─ ok ──► [retrieve_context]
                      │
                 [generate_answer]
                      │
                 [evaluate_quality]
                      │
                      ├─ score ≥ 0.65 OR iter ≥ 2 ──► [finalize] ──► END
                      │
                      └─ score < 0.65 ──► [rewrite_query] ──► [retrieve_context]  (retry)
"""
import logging
from langgraph.graph import StateGraph, END

from .state import ResearchState
from .nodes import (
    node_analyze_question,
    node_execute_search,
    node_generate_response,
    node_evaluate_response,
    node_query_rewriter,
    node_finalize,
    node_finalize_early,
)
from .edges import route_after_analysis, route_after_evaluation

logger = logging.getLogger(__name__)


def build_graph():
    g = StateGraph(ResearchState)

    # Node names are the LangSmith span labels — keep them descriptive and sequential
    g.add_node("plan_search",      node_analyze_question)
    g.add_node("retrieve_context", node_execute_search)
    g.add_node("generate_answer",  node_generate_response)
    g.add_node("evaluate_quality", node_evaluate_response)
    g.add_node("rewrite_query",    node_query_rewriter)
    g.add_node("finalize",         node_finalize)
    g.add_node("finalize_early",   node_finalize_early)

    g.set_entry_point("plan_search")

    g.add_conditional_edges(
        "plan_search",
        route_after_analysis,
        {"retrieve_context": "retrieve_context", "finalize_early": "finalize_early"},
    )

    g.add_edge("retrieve_context", "generate_answer")
    g.add_edge("generate_answer",  "evaluate_quality")

    g.add_conditional_edges(
        "evaluate_quality",
        route_after_evaluation,
        {"finalize": "finalize", "rewrite_query": "rewrite_query"},
    )

    # Retry loop: rewrite → search again
    g.add_edge("rewrite_query", "retrieve_context")

    g.add_edge("finalize",       END)
    g.add_edge("finalize_early", END)

    compiled = g.compile()
    logger.info("[graph] Research agent graph compiled successfully")
    return compiled


research_graph = build_graph()


async def run(
    question: str,
    user_id: str = "anonymous",
    session_id: str = "default",
    conversation_history: list = None,
    status_callback=None,
    token_callback=None,
    web_search: bool = False,
) -> dict:
    """
    Convenience wrapper. Returns the full final state dict.
    Callers use result["final_answer"], result["citations"], result["confidence"].
    """
    initial: ResearchState = {
        "question": question,
        "user_id": user_id,
        "session_id": session_id,
        "conversation_history": conversation_history or [],
        "tickers": [],
        "years": [],
        "sub_questions": [],
        "intent": "general",
        "query_mode": "rag_only",
        "include_news": False,
        "is_out_of_scope": False,
        "iteration_count": 0,
        "rewritten_query": None,
        "sec_chunks": [],
        "transcript_chunks": [],
        "news_results": [],
        "cache_hit": False,
        "draft_answer": None,
        "citations": [],
        "eval_score": 0.0,
        "eval_reason": None,
        "best_score": 0.0,
        "best_answer": None,
        "best_citations": [],
        "final_answer": None,
        "confidence": 0.0,
        "_status_callback": status_callback,
        "_token_callback": token_callback,
        "_web_search": web_search,
        "error": None,
    }
    import os
    run_config = {
        "run_name": question[:100],
        "metadata": {"question": question, "session_id": session_id, "user_id": user_id},
    }

    # Attach a run collector so we can post-hoc add token cost to the LangSmith run
    _ls_collector = None
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
        try:
            from langchain_core.tracers.run_collector import RunCollectorCallbackHandler
            _ls_collector = RunCollectorCallbackHandler()
            run_config["callbacks"] = [_ls_collector]
        except Exception as _e:
            logger.debug(f"[graph] run_collector unavailable: {_e}")

    result = await research_graph.ainvoke(initial, config=run_config)

    # Update LangSmith run with token cost so it shows in the UI alongside node latencies
    if _ls_collector:
        try:
            from agent.llm.token_tracker import tracker as _t
            usage = _t.snapshot()
            if _ls_collector.traced_runs:
                from langsmith import Client as _LsClient
                _ls = _LsClient()
                _ls.update_run(
                    _ls_collector.traced_runs[0].id,
                    extra={
                        "total_cost_usd":      usage.get("total_cost_usd", 0),
                        "total_tokens":        usage.get("total_tokens", 0),
                        "total_input_tokens":  usage.get("total_input_tokens", 0),
                        "total_output_tokens": usage.get("total_output_tokens", 0),
                        "token_usage":         usage,
                    },
                )
                logger.debug(
                    f"[graph] LangSmith token cost posted: "
                    f"${usage.get('total_cost_usd', 0):.5f} / {usage.get('total_tokens', 0)} tok"
                )
        except Exception as _e:
            logger.debug(f"[graph] LangSmith token update failed: {_e}")

    return result
