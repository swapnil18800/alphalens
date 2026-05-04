"""
Conditional routing logic for the LangGraph research agent.
Each function returns a string key that maps to the next node.
"""
from .state import ResearchState

MAX_ITERATIONS = 2          # max self-correction loops before forcing finalize
RETRY_THRESHOLD = 0.65      # retry if faithfulness score below this


def route_after_analysis(state: ResearchState) -> str:
    """After analysis: skip to early finalize if out of scope, else retrieve context."""
    if state.get("error"):
        return "finalize_early"
    if state.get("is_out_of_scope"):
        return "finalize_early"
    return "retrieve_context"


def route_after_evaluation(state: ResearchState) -> str:
    """
    After evaluation:
    - Good score OR hit iteration cap → finalize
    - Low score AND still have retries → rewrite_query (then back to retrieve_context)
    """
    score = state.get("eval_score", 1.0)
    iterations = state.get("iteration_count", 0)

    if score >= RETRY_THRESHOLD or iterations >= MAX_ITERATIONS:
        return "finalize"
    return "rewrite_query"
