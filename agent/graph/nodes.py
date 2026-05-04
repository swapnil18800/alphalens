"""
LangGraph nodes — one async function per stage.

Flow:
  analyze_question
    ├─ out_of_scope → finalize_early → END
    └─ ok → execute_search → generate_response → evaluate_response
                ↑                                       │
                │                              score ≥ 0.65 → finalize → END
                │                              score < 0.65 →
                └── query_rewriter ←───────────────────┘  (retry, cap 2)

Each function takes ResearchState and returns a dict of keys it updates.
"""
import asyncio
import datetime
import json
import logging
import re
import time
from typing import Dict, Any, List

from .state import ResearchState
from agent.llm.factory import LLMFactory
from agent.rag import search_engine, response_generator
from agent.rag.prompts import (
    ANALYSIS_SYSTEM, ANALYSIS_PROMPT,
    EVAL_PROMPT, REWRITE_PROMPT,
    OUT_OF_SCOPE_REPLY,
)

logger = logging.getLogger(__name__)


# ── helpers ────────────────────────────────────────────────────────────────

async def _emit(state: ResearchState, step: str, message: str, chunks=None) -> None:
    """Fire status callback if one is wired in (from WS handler)."""
    cb = state.get("_status_callback")
    if cb:
        try:
            await cb(step, message, chunks=chunks)
        except Exception:
            pass


def _history_summary(history: list, max_turns: int = 3) -> str:
    if not history:
        return "No prior conversation."
    recent = history[-(max_turns * 2):]
    return " | ".join(f"{m['role']}: {m['content'][:100]}" for m in recent)


def _heuristic_eval(answer: str, context_chunks: list) -> tuple[float, str]:
    """
    Fast heuristic evaluation — no LLM call needed for common cases.
    Returns (score, reason). Falls back to LLM eval if ambiguous.
    """
    if not answer or len(answer) < 50:
        return 0.4, "Answer too short or empty"

    word_count = len(answer.split())
    has_citation = any(
        marker in answer
        for marker in ["[SEC-", "[Q", "[TC-", "[10K-", "[N"]
    )
    has_numbers = any(c.isdigit() for c in answer)
    is_refusal = any(
        phrase in answer.lower()
        for phrase in ["not available", "cannot find", "no information", "i don't have"]
    )

    if is_refusal:
        return 0.72, "Honest refusal — no matching data"

    if word_count >= 80 and has_citation and has_numbers:
        return 0.82, "Detailed grounded answer with citations and data"
    if word_count >= 50 and (has_citation or has_numbers):
        return 0.75, "Adequate answer with partial grounding"
    if word_count >= 20 and has_numbers:
        return 0.65, "Brief answer with numeric data"

    return 0.45, "Short answer without clear grounding"


# ── helpers: dedup chunks across multiple searches ─────────────────────────

def _dedup_chunks(chunks: List[Dict]) -> List[Dict]:
    """Deduplicate by chunk id, keeping first occurrence (highest-ranked)."""
    seen: set = set()
    out: List[Dict] = []
    for c in chunks:
        cid = c.get("id") or id(c)
        if cid not in seen:
            seen.add(cid)
            out.append(c)
    return out


# ── Node 1: Analyze Question ────────────────────────────────────────────────

async def node_analyze_question(state: ResearchState) -> Dict[str, Any]:
    """
    Identifies tickers, intent, scope, sub-questions, and query routing mode.
    Out-of-scope questions (including investment advice, future periods) are routed
    directly to finalize_early. query_mode controls whether retrieval uses RAG,
    web search, or both.
    """
    await _emit(state, "analyze", "Reading your question…")
    logger.info(f"[node] analyze_question | q={state['question'][:80]}")
    t0 = time.time()

    llm = LLMFactory.create()
    prompt = ANALYSIS_PROMPT.format(
        question=state["question"],
        history_summary=_history_summary(state.get("conversation_history", [])),
    )

    try:
        raw = await llm.acomplete(prompt, system=ANALYSIS_SYSTEM, max_tokens=500)
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)
    except Exception as e:
        logger.warning(f"[node] analyze_question JSON parse error: {e}")
        parsed = {
            "tickers": [], "intent": "general", "query_mode": "rag_only",
            "out_of_scope": False, "sub_questions": [],
        }

    tickers = [t.upper() for t in parsed.get("tickers", [])]
    # Years: explicit fiscal years from the question. Empty list = no year filter at retrieval.
    raw_years = parsed.get("years", []) or []
    years: List[int] = []
    for y in raw_years:
        try:
            yi = int(y)
            if 2018 <= yi <= 2030:
                years.append(yi)
        except (TypeError, ValueError):
            continue
    years = sorted(set(years))
    sub_questions = parsed.get("sub_questions", []) or [state["question"]]
    sub_questions = sub_questions[:6]
    if not sub_questions:
        sub_questions = [state["question"]]

    intent = parsed.get("intent", "general")
    is_out_of_scope = bool(parsed.get("out_of_scope", False))

    # Determine query_mode with web_search flag override
    raw_mode = parsed.get("query_mode", "rag_only")
    if raw_mode not in ("rag_only", "web_only", "hybrid"):
        raw_mode = "rag_only"

    web_search_on = state.get("_web_search", False)
    if not web_search_on:
        if raw_mode == "web_only":
            # Question requires real-time/external data but web search is disabled.
            # Treat as out-of-scope so the system explains the limitation clearly.
            is_out_of_scope = True
            query_mode = "rag_only"
            logger.info("[node] analyze_question: web_only query with web_search OFF → out_of_scope")
        else:
            # Web toggle is OFF — force local-only regardless of LLM suggestion
            query_mode = "rag_only"
    else:
        query_mode = raw_mode

        # When web search is enabled, only override if the LLM returned out_of_scope
        # (routing error). Respect rag_only decisions for SEC-grounded questions.
        if not is_out_of_scope and query_mode == "out_of_scope":
            query_mode = "hybrid"
            logger.info("[node] analyze_question: web_search ON + out_of_scope from LLM → upgraded to hybrid")

    # Temporal guard: reject requests for future fiscal periods
    if not is_out_of_scope:
        time_period = str(parsed.get("time_period", ""))
        current_year = datetime.date.today().year
        for token in time_period.replace("FY", "").replace("Q", " ").split():
            try:
                yr = int(token[:4])
                if yr > current_year:
                    is_out_of_scope = True
                    logger.info(
                        f"[node] analyze_question: future period detected ({time_period}) → out_of_scope"
                    )
                    break
            except (ValueError, IndexError):
                pass

    # Emit analysis summary with routing decision
    ticker_str = ", ".join(tickers) if tickers else "no specific ticker"
    await _emit(
        state, "analyze",
        f"Identified: {ticker_str} · intent={intent} · mode={query_mode} · {len(sub_questions)} sub-question(s)"
    )

    if len(sub_questions) > 1:
        sq_text = " · ".join(f"({i+1}) {q[:90]}" for i, q in enumerate(sub_questions))
        await _emit(state, "decompose", f"Sub-questions: {sq_text}")

    result = {
        "tickers": tickers,
        "years": years,
        "sub_questions": sub_questions,
        "intent": intent,
        "query_mode": query_mode,
        "include_news": query_mode in ("web_only", "hybrid"),  # backward compat
        "is_out_of_scope": is_out_of_scope,
        "iteration_count": 0,
        "cache_hit": False,
        "rewritten_query": None,
    }
    logger.info(f"[node] analyze_question done in {time.time()-t0:.1f}s | {result}")
    return result


# ── Node 2: Execute Search ──────────────────────────────────────────────────

async def node_execute_search(state: ResearchState) -> Dict[str, Any]:
    """
    Source-isolated retrieval based on query_mode:
      - rag_only  → pgvector + BM25 hybrid search only (no web)
      - web_only  → Tavily web search only (no RAG)
      - hybrid    → RAG + web in parallel, merged with budget split

    Ticker filter is always applied when tickers are present — even on retry
    iterations. The query rewriter broadens the query text; it does not drop
    the company filter.
    """
    import os
    iteration     = state.get("iteration_count", 0)
    tickers       = state.get("tickers", [])
    years         = state.get("years", []) or []
    sub_questions = state.get("sub_questions", [state["question"]])
    base_query    = state.get("rewritten_query") or state["question"]
    query_mode    = state.get("query_mode", "rag_only")
    ticker_label  = ", ".join(tickers) if tickers else "all tickers"

    n_sq = len(sub_questions)

    # Detect comparative cross-company question for per-ticker query decomposition (Plan C Fix 2).
    _COMPARE_RE = re.compile(
        r"\b(compare|comparison|comparing|vs\.?|versus|between|differ|differs|difference|contrast|"
        r"contrasted|relative to|rank|ranking|ordered|side by side|side-by-side)\b",
        re.IGNORECASE,
    )
    is_cross_company = len(tickers) >= 2 and bool(_COMPARE_RE.search(state["question"]))

    # Year-filter robustness: expand each extracted year by ±1 to absorb fiscal/filing-year offsets.
    # A 10-K for "FY2024" is typically filed in 2025 (filing_year=2025).
    # For offset-fiscal-year companies (NVDA Jan, MSFT Jun, CRM Jan), transcript calendar year
    # can differ from fiscal year by up to 1 year in EITHER direction:
    #   • NVDA Q3 FY2025 call (Nov 2024) → year=2024; "FY2025" query → filter must include 2024.
    #   • AAPL FY2025 10-K (filed Nov 2025) → filing_year=2025; "FY2025" → filter includes 2025. ✓
    # Expand ±1: "FY2025" → [2024, 2025, 2026]. CE reranker restores precision within the window.
    if years:
        expanded = set()
        for y in years:
            expanded.update({y - 1, y, y + 1})
        years_for_filter: List[int] = sorted(expanded)
    else:
        years_for_filter = []

    if iteration == 0:
        chunks_per_source = min(16, max(8, 4 * n_sq))
    else:
        chunks_per_source = min(20, max(12, 5 * n_sq))

    if iteration == 0:
        mode_label = {"rag_only": "filings", "web_only": "web", "hybrid": "filings + web"}[query_mode]
        await _emit(state, "search",
                    f"Searching {mode_label} for {ticker_label} "
                    f"({n_sq} sub-question{'s' if n_sq > 1 else ''})…")
    else:
        await _emit(state, "search_retry",
                    f"Broadening search (attempt {iteration+1}) — {base_query[:100]}")

    logger.info(
        f"[node] execute_search | mode={query_mode} | tickers={tickers} "
        f"| iter={iteration} | sub_q={n_sq} | chunks_per={chunks_per_source}"
    )

    # Always filter by ticker — never drop the company filter on retry
    search_tickers = tickers

    all_sec:  List[Dict] = []
    all_tc:   List[Dict] = []
    all_news: List[Dict] = []
    cache_hit = False

    # ── web-only: skip RAG entirely ────────────────────────────────────────
    if query_mode == "web_only":
        web_query = f"{' '.join(tickers[:2])} {base_query}".strip() if tickers else base_query
        await _emit(state, "web_search", f"Searching web: {web_query[:120]}…")
        all_news = await search_engine.search_web(web_query)
        if not all_news and not os.getenv("TAVILY_API_KEY"):
            await _emit(state, "web_search", "⚠ web search unavailable (TAVILY_API_KEY not set)")

    # ── rag_only / hybrid: run hybrid retrieval ────────────────────────────
    else:
        include_web_for_hybrid = (query_mode == "hybrid")

        # Boost table chunks for intents that need precise financial statement data.
        # The cross-encoder (TinyBERT) downgrades sparse table chunks even when they
        # contain the exact figures needed; this flag bypasses that for key intents.
        intent = state.get("intent", "")
        boost_tables = intent == "revenue" and len(search_tickers) <= 2

        async def _search_one(query: str, force_rag_only: bool = False,
                              tickers_override: List[str] = None,
                              years_override: List[int] = None):
            nonlocal cache_hit
            try:
                effective_mode = "rag_only" if force_rag_only else query_mode
                effective_tickers = tickers_override if tickers_override is not None else search_tickers
                effective_years = years_override if years_override is not None else years_for_filter
                results, hit = await search_engine.run_parallel_search(
                    question=query,
                    tickers=effective_tickers,
                    query_mode=effective_mode,
                    chunks_per_source=chunks_per_source,
                    boost_tables=boost_tables,
                    years=effective_years or None,
                )
                if hit:
                    cache_hit = True
                return results
            except Exception as e:
                logger.error(f"[node] execute_search sub-query failed: {e}")
                return {"sec": [], "transcripts": [], "news": []}

        if query_mode == "hybrid":
            hybrid_web_q = f"{' '.join(tickers[:2])} {base_query}".strip() if tickers else base_query
            await _emit(state, "web_search", f"Searching web: {hybrid_web_q[:120]}…")

        # Per-ticker decomposition for cross-company comparisons (Plan C Fix 2).
        # Run one ticker-scoped retrieval per company in parallel and merge.
        if is_cross_company and query_mode != "hybrid":
            await _emit(state, "decompose",
                        f"Cross-company: running per-ticker retrievals for {ticker_label}")
            per_ticker_results = await asyncio.gather(
                *[
                    _search_one(
                        f"{t} {base_query}",
                        force_rag_only=True,
                        tickers_override=[t],
                    )
                    for t in tickers
                ],
                return_exceptions=True,
            )
            # Cap per-ticker contribution to ensure balanced context representation.
            # Without this, the _format_chunks budget may be consumed entirely by the
            # first ticker (highest CE scores), leaving no context for others.
            per_ticker_cap = max(4, chunks_per_source // len(tickers))
            for res in per_ticker_results:
                if isinstance(res, Exception):
                    continue
                # Sort by CE score desc within each ticker, keep top N
                sec_r = sorted(res.get("sec", []), key=lambda c: -(c.get("score") or 0))
                tc_r  = sorted(res.get("transcripts", []), key=lambda c: -(c.get("score") or 0))
                all_sec.extend(sec_r[:per_ticker_cap])
                all_tc.extend(tc_r[:per_ticker_cap])
            all_sec = _dedup_chunks(all_sec)
            all_tc  = _dedup_chunks(all_tc)
        elif n_sq == 1:
            res = await _search_one(base_query)
            all_sec  = res["sec"]
            all_tc   = res["transcripts"]
            all_news = res.get("news", [])
        else:
            # Multi-sub-question: do ONE web search for the base query, RAG-only per sub-question.
            # Avoids n_sq parallel Tavily calls which causes rate-limiting and hangs.
            if query_mode == "hybrid":
                web_task = search_engine.search_web(hybrid_web_q)
                rag_tasks = [_search_one(q, force_rag_only=True) for q in [base_query] + sub_questions[1:]]
                gathered = await asyncio.gather(web_task, *rag_tasks, return_exceptions=True)
                web_result, *rag_results = gathered
                if not isinstance(web_result, Exception):
                    all_news = web_result if isinstance(web_result, list) else []
                rag_results_list = rag_results
            else:
                queries = [base_query] + sub_questions[1:]
                rag_results_list = await asyncio.gather(
                    *[_search_one(q) for q in queries], return_exceptions=True
                )

            for res in rag_results_list:
                if isinstance(res, Exception):
                    continue
                all_sec.extend(res.get("sec", []))
                all_tc.extend(res.get("transcripts", []))
                if query_mode != "hybrid":  # hybrid news already collected above
                    all_news.extend(res.get("news", []))

            all_sec  = _dedup_chunks(all_sec)
            all_tc   = _dedup_chunks(all_tc)
            all_news = _dedup_chunks(all_news)

    sec_count  = len(all_sec)
    tc_count   = len(all_tc)
    news_count = len(all_news)

    if cache_hit:
        await _emit(state, "search", "Cache hit — serving prior answer")
    else:
        parts = []
        if sec_count:   parts.append(f"{sec_count} 10-K")
        if tc_count:    parts.append(f"{tc_count} transcript")
        if news_count:  parts.append(f"{news_count} web")
        if query_mode in ("web_only", "hybrid") and news_count == 0 and not os.getenv("TAVILY_API_KEY"):
            parts.append("⚠ web search unavailable (TAVILY_API_KEY not set)")

        chunk_previews = [
            {
                "ticker":  c.get("ticker", ""),
                "source":  c.get("source", "10k"),
                "year":    c.get("filing_year") or c.get("year", ""),
                "section": c.get("section", ""),
                "text":    (c.get("chunk_text") or "")[:300],
            }
            for c in (all_sec + all_tc + all_news)[:10]
        ]
        await _emit(
            state, "search",
            f"Retrieved {', '.join(parts) or 'no results'} passages",
            chunks=chunk_previews,
        )

    return {
        "sec_chunks":        all_sec,
        "transcript_chunks": all_tc,
        "news_results":      all_news,
        "cache_hit":         cache_hit,
    }


# ── Node 3: Generate Response ───────────────────────────────────────────────

async def node_generate_response(state: ResearchState) -> Dict[str, Any]:
    """Builds grounded answer from retrieved context with citation markers."""
    sec_n  = len(state.get("sec_chunks", []))
    tc_n   = len(state.get("transcript_chunks", []))
    total_chunks = sec_n + tc_n
    tickers = state.get("tickers", [])
    ticker_str = "/".join(tickers) if tickers else "company"

    await _emit(
        state, "generate",
        f"Synthesizing answer from {total_chunks} source passages ({ticker_str})…"
    )
    logger.info(f"[node] generate_response | chunks={total_chunks} | iter={state.get('iteration_count',0)}")

    try:
        answer, citations = await response_generator.generate(
            question=state["question"],
            sec_chunks=state.get("sec_chunks", []),
            transcript_chunks=state.get("transcript_chunks", []),
            news_results=state.get("news_results", []),
            conversation_history=state.get("conversation_history", []),
            iteration=state.get("iteration_count", 0),
            token_callback=state.get("_token_callback"),
            query_mode=state.get("query_mode", "rag_only"),
        )
    except Exception as e:
        logger.error(f"[node] generate_response failed: {e}")
        answer = "I encountered an error generating a response. Please try again."
        citations = []

    return {"draft_answer": answer, "citations": citations}


# ── Node 4: Evaluate Response ───────────────────────────────────────────────

async def node_evaluate_response(state: ResearchState) -> Dict[str, Any]:
    """
    Fast heuristic eval first; falls back to LLM-as-judge only when borderline.
    Score < 0.65 AND iteration < 2 → retry via query_rewriter.
    """
    await _emit(state, "evaluate", "Checking answer quality…")
    logger.info(f"[node] evaluate_response | iter={state.get('iteration_count', 0)}")

    all_chunks = state.get("sec_chunks", []) + state.get("transcript_chunks", [])

    h_score, h_reason = _heuristic_eval(state.get("draft_answer", ""), all_chunks)

    score, reason = h_score, h_reason
    if 0.50 <= h_score < 0.75 and state.get("iteration_count", 0) == 0:
        context_excerpt = "\n---\n".join(
            c.get("chunk_text", "")[:500] for c in all_chunks[:6]
        )
        llm = LLMFactory.create_eval_llm()
        prompt = EVAL_PROMPT.format(
            question=state["question"],
            answer=(state.get("draft_answer") or "")[:600],
            context=context_excerpt[:1500],
        )
        try:
            raw = await llm.acomplete(prompt, max_tokens=64)
            clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(clean)
            score  = float(parsed.get("score", h_score))
            reason = parsed.get("reason", h_reason)
        except Exception as e:
            logger.debug(f"[node] evaluate_response LLM fallback failed ({e}) — using heuristic")

    new_iter = state.get("iteration_count", 0) + 1

    await _emit(
        state, "evaluate",
        f"Quality score: {score:.0%} — {'good, finalizing' if score >= 0.65 else 'retrying with refined query'}"
    )

    prev_best = state.get("best_score", 0.0)
    if score >= prev_best:
        best_score     = score
        best_answer    = state.get("draft_answer", "")
        best_citations = state.get("citations", [])
    else:
        best_score     = prev_best
        best_answer    = state.get("best_answer", state.get("draft_answer", ""))
        best_citations = state.get("best_citations", state.get("citations", []))

    logger.info(f"[node] evaluate_response score={score:.2f} reason={reason}")
    return {
        "eval_score":      score,
        "eval_reason":     reason,
        "iteration_count": new_iter,
        "best_score":      best_score,
        "best_answer":     best_answer,
        "best_citations":  best_citations,
    }


# ── Node 4b: Query Rewriter (retry path only) ──────────────────────────────

async def node_query_rewriter(state: ResearchState) -> Dict[str, Any]:
    """
    Rewrites the original question with different keywords before retry search.
    Only reached when eval_score < 0.65 and iteration_count < 2.
    """
    await _emit(state, "rewrite", "Refining query for better retrieval…")
    logger.info(f"[node] query_rewriter | original={state['question'][:60]}")

    llm = LLMFactory.create()
    prompt = REWRITE_PROMPT.format(
        question=state["question"],
        reason=state.get("eval_reason", "low faithfulness score"),
    )

    rewritten = state["question"]
    try:
        raw = await llm.acomplete(prompt, max_tokens=150)
        rewritten = raw.strip().strip('"').strip("'")
        logger.info(f"[node] query_rewriter → {rewritten[:80]}")
    except Exception as e:
        logger.warning(f"[node] query_rewriter failed: {e}")

    # Emit the actual rewritten query so users can see it in the trace
    await _emit(state, "rewrite", f"Rewritten query: {rewritten[:120]}")

    return {"rewritten_query": rewritten}


# ── Node 5a: Finalize ───────────────────────────────────────────────────────

async def node_finalize(state: ResearchState) -> Dict[str, Any]:
    """Packages the best answer seen across all iterations as the final output."""
    best = state.get("best_answer") or state.get("draft_answer", "No answer could be generated.")
    best_cites = state.get("best_citations") or state.get("citations", [])
    confidence = state.get("best_score") or state.get("eval_score", 0.5)
    await _emit(state, "finalize", f"Answer ready · confidence {confidence:.0%}")
    logger.info(f"[node] finalize | best_score={confidence:.2f}")

    # Populate semantic cache for production use.
    # Guard: skip if this response was already a cache hit, confidence too low, or cache disabled.
    from config import settings
    if not state.get("cache_hit") and confidence >= 0.65 and not settings.CACHE_DISABLED:
        question = state.get("question", "")
        if question:
            asyncio.create_task(search_engine.store_in_cache(question, best))
            logger.debug("[node] finalize | queued cache write")

    return {"final_answer": best, "citations": best_cites, "confidence": confidence}


# ── Node 5b: Finalize Early (out-of-scope / error) ─────────────────────────

async def node_finalize_early(state: ResearchState) -> Dict[str, Any]:
    """Used for out-of-scope questions or unrecoverable errors."""
    answer = state.get("error") or OUT_OF_SCOPE_REPLY
    await _emit(state, "finalize", "Done")
    logger.info(f"[node] finalize_early | reason={'error' if state.get('error') else 'out_of_scope'}")
    return {"final_answer": answer, "confidence": 1.0, "eval_score": 1.0}
