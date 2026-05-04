"""
AlphaLens unified evaluation harness — question_v2.txt edition.

Combines all metrics in one pass:
  M1  Factual correctness   — % of key_facts found in answer (fuzzy, no LLM)
  M2  Faithfulness          — RAGAS: answer claims grounded in context
  M3  Retrieval recall      — % of key_facts found in retrieved chunks (no LLM)
  M4  Context precision     — RAGAS: fraction of retrieved chunks that are relevant
  M5  Answer relevancy      — RAGAS: excluded (embeddings incompatibility in ragas 0.4.x)
  M6  Routing accuracy      — web_search flag vs actual query_mode (no LLM)
  M7  Judge score           — tiered GPT-4o-mini / GPT-4o, returns verdict + likely_broke
  M8  Latency + calibration — pipeline_s + RMSE(confidence, judge_score)

Ground truth is loaded from question_v2.txt's ground_truth_map field.
Run generate_ground_truth.py first if ground_truth_map is missing.

Usage:
    python evals/qa_eval/run_eval.py --smoke             # first 3 questions
    python evals/qa_eval/run_eval.py --full              # all 20 questions
    python evals/qa_eval/run_eval.py --category deep_retrieval earnings_grounding
    python evals/qa_eval/run_eval.py --set-baseline      # write evals/baseline.json after run
    python evals/qa_eval/run_eval.py --full --set-baseline

Output:
    evals/qa_eval/results/<timestamp>/NN_category_question.json   (per-question)
    evals/qa_eval/results/<timestamp>/_summary.json               (aggregated)
    evals/qa_eval/results/<timestamp>/_analysis.md                (iteration log)
"""
import argparse
import asyncio
import json
import logging
import math
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from dotenv import load_dotenv
load_dotenv()

from agent.llm.token_tracker import tracker as _llm_tracker

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

# Logging setup deferred until after argparse (see main() below)

QUESTIONS_FILE = Path(__file__).parent / "question_v2.txt"
EVALS_DIR      = Path(__file__).parent / "results"
BASELINE_PATH  = Path(__file__).parent.parent / "baseline.json"


# ---------------------------------------------------------------------------
# Metric helpers (M1, M3, M6) — no LLM, instant
# ---------------------------------------------------------------------------

def _safe_float(val) -> float:
    try:
        f = float(val)
        return 0.0 if math.isnan(f) else round(f, 3)
    except Exception:
        return 0.0


def _matches_fact(fact: str, text: str) -> bool:
    """
    Fuzzy fact matching:
      - Numeric values: must match within ±5% AND same magnitude unit if present
      - Text: majority of meaningful key terms appear in text
    """
    text_lower = text.lower()

    # Extract numbers from fact (e.g. "$130.5B", "25%", "4,000")
    num_matches = re.findall(r'\$?([\d,]+\.?\d*)\s*([BMK%]?)', fact)
    if num_matches:
        for raw, unit in num_matches:
            try:
                val = float(raw.replace(",", ""))
                if val == 0:
                    continue
                # Find candidate numbers in text
                text_nums = re.findall(r'\$?([\d,]+\.?\d*)\s*([BMK%]?)', text)
                for t_raw, t_unit in text_nums:
                    try:
                        t_val = float(t_raw.replace(",", ""))
                        if unit == t_unit and abs(val - t_val) / max(abs(val), 1) <= 0.05:
                            return True
                    except Exception:
                        continue
            except Exception:
                continue

    # Text key-term matching
    stop = {"from", "their", "with", "that", "this", "have", "been", "were", "the",
            "and", "for", "its", "was", "are", "per", "into", "than", "will"}
    terms = [w for w in re.sub(r"[^a-z0-9 ]", " ", fact.lower()).split()
             if len(w) > 3 and w not in stop]
    if not terms:
        return fact.lower() in text_lower
    hits = sum(1 for t in terms if t in text_lower)
    return hits >= max(1, len(terms) * 0.6)


_REFUSAL_PHRASES = [
    "not available", "not in", "not covered", "private company",
    "unable to find", "don't have", "do not have", "no data",
    "not found", "cannot find", "not public", "not in our database",
    "outside of my", "not in the database", "outside my scope",
    "outside my coverage", "focus on us equity", "cannot provide",
    "not covered in", "i focus on",
]

_SPECIAL_TOKENS = {"NOT_IN_DATABASE", "INVALID_INPUT", "BROAD_QUERY_HANDLED", "WEB_SEARCH_TRIGGERED"}


def fact_check(key_facts: list, answer: str, pipeline: dict) -> float:
    """M1: factual correctness. Returns 0–1."""
    if not key_facts:
        return 1.0  # no facts defined → cannot fail
    answer_lower = (answer or "").lower()
    hits = 0
    for fact in key_facts:
        if fact == "NOT_IN_DATABASE":
            if any(p in answer_lower for p in _REFUSAL_PHRASES):
                hits += 1
        elif fact == "INVALID_INPUT":
            if len(answer.strip()) >= 10:  # any coherent response passes
                hits += 1
        elif fact == "BROAD_QUERY_HANDLED":
            hits += 1  # any non-empty response to a broad question is acceptable
        elif fact == "WEB_SEARCH_TRIGGERED":
            if pipeline.get("query_mode") in {"hybrid", "web_only"} or pipeline.get("news_count", 0) > 0:
                hits += 1
        else:
            if _matches_fact(fact, answer):
                hits += 1
    return round(hits / len(key_facts), 3)


def retrieval_recall(key_facts: list, chunks: list) -> float:
    """M3: retrieval recall. % of key_facts present in retrieved chunk texts."""
    if not key_facts:
        return 1.0
    if not chunks:
        # Special tokens that don't require chunks pass trivially
        non_db_facts = [f for f in key_facts if f in _SPECIAL_TOKENS]
        return 1.0 if len(non_db_facts) == len(key_facts) else 0.0

    all_text = " ".join((c.get("text") or c.get("chunk_text") or "") for c in chunks)
    hits = 0
    for fact in key_facts:
        if fact in _SPECIAL_TOKENS:
            hits += 1  # special tokens don't need to be in chunks
        elif _matches_fact(fact, all_text):
            hits += 1
    return round(hits / len(key_facts), 3)


def routing_check(web_search_flag: bool, query_mode: str) -> int:
    """M6: routing accuracy. 1 = correct, 0 = wrong."""
    if web_search_flag:
        return 1 if query_mode in {"hybrid", "web_only"} else 0
    return 1 if query_mode == "rag_only" else 0


def classify_failure(m1: float, m2: float, m3: float, m6: int) -> str:
    """Rule-based failure type classification."""
    if m6 == 0:
        return "routing_failure"
    if m3 < 0.4:
        return "retrieval_failure"
    if m2 < 0.4:
        return "hallucination"
    if m1 < 0.5:
        return "reasoning_failure"
    return "none"


# ---------------------------------------------------------------------------
# LangSmith trace block
# ---------------------------------------------------------------------------

def make_langsmith_block(session_id: str, iteration_count: int, finalized_early: bool) -> dict:
    project = os.getenv("LANGSMITH_PROJECT", "alphalens")
    filter_expr = f'eq(metadata_key, "session_id") and eq(metadata_value, "{session_id}")'
    search_url = (
        f"https://smith.langchain.com/projects/p/{project}/runs"
        f"?filter={urllib.parse.quote(filter_expr)}"
    )
    nodes = ["plan_search", "retrieve_context", "generate_answer", "evaluate_quality"]
    if finalized_early:
        nodes.append("finalize_early")
    else:
        if iteration_count > 0:
            nodes.append("rewrite_query")
        nodes.append("finalize")

    return {
        "session_id": session_id,
        "project": project,
        "trace_search_url": search_url,
        "node_spans": nodes,
        "had_retry": iteration_count > 0,
    }


# ---------------------------------------------------------------------------
# RAGAS batch evaluation (M2, M4)
# ---------------------------------------------------------------------------

def _run_ragas_batch(inputs: list[dict]) -> list[dict]:
    """
    Sync RAGAS evaluation on a batch of inputs.
    Each input: {question, answer, contexts: [str], ground_truth}
    Returns per-question {faithfulness, context_precision, context_recall, answer_relevancy}.

    Metric strategy:
      faithfulness        — LLM-only (always available)
      context_precision   — LLM-only (always available)
      context_recall      — LLM-only (added; checks ground_truth coverage in context)
      answer_relevancy    — embeddings-based; uses local all-MiniLM-L6-v2 via
                            ragas HuggingfaceEmbeddings to avoid OpenAI embedding costs
                            (falls back gracefully if ragas version doesn't support it)
    """
    import warnings
    empty = {"faithfulness": 0.0, "context_precision": 0.0,
             "context_recall": 0.0, "answer_relevancy": 0.0}

    try:
        from ragas import evaluate
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from ragas.metrics import faithfulness, context_precision
        from datasets import Dataset
    except ImportError:
        logger.warning("RAGAS not installed — M2/M4 will be 0.0")
        return [empty.copy() for _ in inputs]

    # Configure shared RAGAS LLM (higher max_tokens prevents statement truncation)
    try:
        from langchain_openai import ChatOpenAI
        from ragas.llms import LangchainLLMWrapper
        ragas_llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini", max_tokens=4096))
        faithfulness.llm = ragas_llm
        context_precision.llm = ragas_llm
    except Exception:
        pass

    # Try to add context_recall (LLM-only — no embeddings required)
    _has_cr = False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from ragas.metrics import context_recall as _context_recall
        _context_recall.llm = ragas_llm  # type: ignore[possibly-undefined]
        _has_cr = True
        logger.info("[ragas] context_recall metric available")
    except Exception as _e:
        logger.debug(f"[ragas] context_recall unavailable: {_e}")

    # Try to add answer_relevancy using local all-MiniLM-L6-v2 (avoids OpenAI embedding cost)
    _has_ar = False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from ragas.metrics import answer_relevancy as _answer_relevancy
        # Prefer ragas's own HuggingfaceEmbeddings (uses sentence_transformers already installed)
        try:
            from ragas.embeddings import HuggingfaceEmbeddings as _RagasHFEmb
            _local_emb = _RagasHFEmb(model_name="all-MiniLM-L6-v2")
            _answer_relevancy.embeddings = _local_emb
        except Exception:
            # Fallback: try langchain_community HuggingFaceEmbeddings
            from langchain_community.embeddings import HuggingFaceEmbeddings as _LcHFEmb
            from ragas.embeddings import LangchainEmbeddingsWrapper as _LEW
            _answer_relevancy.embeddings = _LEW(_LcHFEmb(model_name="all-MiniLM-L6-v2"))
        _answer_relevancy.llm = ragas_llm  # type: ignore[possibly-undefined]
        _has_ar = True
        logger.info("[ragas] answer_relevancy metric available (local embeddings)")
    except Exception as _e:
        logger.debug(f"[ragas] answer_relevancy unavailable: {_e}")

    active_metrics = [faithfulness, context_precision]
    if _has_cr:
        active_metrics.append(_context_recall)   # type: ignore[possibly-undefined]
    if _has_ar:
        active_metrics.append(_answer_relevancy)  # type: ignore[possibly-undefined]
    logger.info(f"[ragas] running {len(active_metrics)} metrics: "
                f"{[m.name for m in active_metrics]}")

    # Ensure non-empty contexts
    clean_inputs = []
    for inp in inputs:
        contexts = inp.get("contexts") or ["[No documents retrieved]"]
        clean_inputs.append({
            **inp,
            "contexts": [str(c) for c in contexts if c][:6] or ["[No documents retrieved]"],
        })

    ds = Dataset.from_dict({
        "question":     [r["question"]     for r in clean_inputs],
        "answer":       [r["answer"]       for r in clean_inputs],
        "contexts":     [r["contexts"]     for r in clean_inputs],
        "ground_truth": [r["ground_truth"] for r in clean_inputs],
    })

    try:
        scores = evaluate(
            ds,
            metrics=active_metrics,
            column_map={
                "user_input":         "question",
                "response":           "answer",
                "retrieved_contexts": "contexts",
                "reference":          "ground_truth",
            },
            raise_exceptions=False,
        )
        df = scores.to_pandas()

        results = []
        for i in range(len(clean_inputs)):
            row = {"faithfulness": 0.0, "context_precision": 0.0,
                   "context_recall": 0.0, "answer_relevancy": 0.0}
            for metric_name in ("faithfulness", "context_precision",
                                "context_recall", "answer_relevancy"):
                col = df.get(metric_name)
                if col is not None:
                    row[metric_name] = _safe_float(col.iloc[i])
            results.append(row)
        return results

    except Exception as e:
        logger.warning(f"RAGAS batch failed: {e}")
        return [empty.copy() for _ in inputs]


# ---------------------------------------------------------------------------
# Judge (M7) — tiered model selection
# ---------------------------------------------------------------------------

def _select_judge_model(m1_score: float, category: str) -> str:
    """Always use GPT-4o — gpt-4o-mini gives inconsistent false-fail verdicts."""
    return "gpt-4o"


JUDGE_SYSTEM = """\
You are an expert evaluator for an AI equity-research assistant backed by SEC 10-K filings and earnings transcripts.
Evaluate the system response against the expected behavior and reference ground truth.

Scoring rubric:
- pass   (0.8–1.0): Response clearly meets expected behavior; key facts are correct
- partial (0.4–0.79): Some aspects correct, some missing or inaccurate
- fail   (0.0–0.39): Response fails to meet expected behavior; significant errors

Category-specific guidance:
- edge_cases: A response that gracefully redirects the user (e.g., "That seems outside my scope, try asking about...") IS valid graceful handling. Do NOT fail a response simply because it redirects rather than labeling the input as gibberish.
- web_trigger: Check pipeline signals — if query_mode is "web_only" or "hybrid" and citations reference news sources, the system DID trigger web search. Score on answer quality, not on whether you perceive web search to have occurred.
- hallucination_control: A correct refusal ("I cannot provide data for this company") must score pass(1.0) even if brief. Any attempt to fabricate numbers must score fail(0.0).
- deep_retrieval: If the ground truth itself states that the requested information is not present in the available excerpts/context, then a system response saying "data not available" or "not in the provided context" is CORRECT behavior and must score pass(1.0). Only penalize retrieval failures when the ground truth confirms the data IS available in the database but the system failed to find it.

Return ONLY valid JSON (no markdown, no extra text):
{
  "verdict": "pass" | "partial" | "fail",
  "score": <float 0.0-1.0>,
  "reasoning": "brief explanation citing answer, ground truth, and expected behavior",
  "likely_broke": "routing | retrieval | generation | nothing | uncertain"
}
"""

JUDGE_USER = """\
CATEGORY: {category}
EXPECTED BEHAVIOR: {expected_behavior}
GROUND TRUTH (reference): {ground_truth}
FACTUAL CORRECTNESS (M1={m1:.3f}): fraction of key facts found in the answer

QUESTION: {question}

SYSTEM RESPONSE:
{answer}

TOP CONTEXT CHUNKS (preview):
{context_preview}

PIPELINE SIGNALS:
- confidence: {confidence}  eval_score: {eval_score}
- sec_chunks: {sec_n}  transcript_chunks: {txn_n}
- query_mode: {query_mode}  cache_hit: {cache_hit}  iterations: {iterations}
- citations: {citations_n}
"""


async def _llm_judge(
    openai_client,
    question: str,
    category: str,
    expected_behavior: str,
    answer: str,
    context_chunks: list,
    ground_truth: str,
    m1_score: float,
    pipeline: dict,
) -> dict:
    """M7: judge evaluation with tiered model selection."""
    model = _select_judge_model(m1_score, category)
    ctx_preview = "\n".join(
        f"  [{i+1}] {(c.get('text') or c.get('chunk_text') or '')[:180]}"
        for i, c in enumerate(context_chunks[:3])
    )

    user_msg = JUDGE_USER.format(
        category=category,
        expected_behavior=expected_behavior,
        ground_truth=(ground_truth or "N/A")[:1500],
        m1=m1_score,
        question=question,
        answer=(answer or "")[:1200],
        context_preview=ctx_preview or "  [none]",
        confidence=pipeline.get("confidence", 0.0),
        eval_score=pipeline.get("eval_score", 0.0),
        sec_n=pipeline.get("sec_chunks_count", 0),
        txn_n=pipeline.get("transcript_chunks_count", 0),
        query_mode=pipeline.get("query_mode", "unknown"),
        cache_hit=pipeline.get("cache_hit", False),
        iterations=pipeline.get("iteration_count", 0),
        citations_n=pipeline.get("citations_count", 0),
    )

    for attempt in range(5):
        try:
            resp = await asyncio.to_thread(
                openai_client.chat.completions.create,
                model=model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=400,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            parsed = json.loads(raw)
            parsed["judge_model"] = model
            return parsed
        except Exception as e:
            is_rate_limit = "429" in str(e) or "rate_limit" in str(e).lower() or "tokens per min" in str(e).lower()
            logger.warning(f"Judge call failed ({model}): {e}")
            if is_rate_limit and attempt < 4:
                await asyncio.sleep(5 * (attempt + 1))  # 5s, 10s, 15s, 20s backoff
                continue
            return {
                "verdict": "fail", "score": 0.0,
                "reasoning": f"Judge error: {e}",
                "likely_broke": "uncertain",
                "judge_model": model,
            }


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_question(research, question: str, web_search: bool, session_id: str) -> dict:
    """Run one question through the pipeline. Returns state fields + timing + token usage."""
    _llm_tracker.reset()
    t0 = time.monotonic()
    try:
        state = await research.run(
            question=question,
            user_id="eval-harness",
            session_id=session_id,
            web_search=web_search,
        )
        elapsed = round(time.monotonic() - t0, 2)
        error = state.get("error")
    except Exception as e:
        elapsed = round(time.monotonic() - t0, 2)
        return {"error": str(e), "elapsed_s": elapsed, "final_answer": "",
                "citations": [], "context_chunks": [], "query_mode": "unknown",
                "token_usage": _llm_tracker.snapshot()}

    sec_chunks        = state.get("sec_chunks") or []
    transcript_chunks = state.get("transcript_chunks") or []
    news_results      = state.get("news_results") or []
    citations         = state.get("best_citations") or state.get("citations") or []

    def _summarise(chunks: list, web: bool = False) -> list:
        out = []
        for c in chunks[:15]:
            item: dict = {
                "ticker":  c.get("ticker") or c.get("company"),
                "source":  c.get("source_type") or c.get("source"),
                "section": (c.get("section") or ""),
                "score":   round(float(c.get("score") or c.get("similarity") or 0.0), 3),
                "text":    (c.get("chunk_text") or c.get("text") or ""),
            }
            if web:
                item["url"]   = c.get("url", "")
                item["title"] = c.get("title", "")
            out.append(item)
        return out

    citation_sources = [
        {"ticker": c.get("ticker"), "source": c.get("source"),
         "year": c.get("year"), "section": (c.get("section") or "")[:60]}
        for c in citations[:8]
    ]

    return {
        "error":                   error,
        "elapsed_s":               elapsed,
        "final_answer":            state.get("best_answer") or state.get("final_answer") or "",
        "citations":               citation_sources,
        "citations_count":         len(citations),
        "context_chunks":          _summarise(sec_chunks + transcript_chunks),
        "context_chunks_count":    len(sec_chunks) + len(transcript_chunks),
        "sec_chunks_count":        len(sec_chunks),
        "transcript_chunks_count": len(transcript_chunks),
        "news_chunks":             _summarise(news_results, web=True),
        "news_count":              len(news_results),
        "tickers_extracted":       state.get("tickers") or [],
        "is_out_of_scope":         state.get("is_out_of_scope", False),
        "query_mode":              state.get("query_mode", "rag_only"),
        "confidence":              round(float(state.get("confidence") or 0.0), 3),
        "eval_score":              round(float(state.get("best_score") or state.get("eval_score") or 0.0), 3),
        "cache_hit":               state.get("cache_hit", False),
        "iteration_count":         state.get("iteration_count", 0),
        "intent":                  state.get("intent", ""),
        "sub_questions":           state.get("sub_questions") or [],
        "rewritten_query":         state.get("rewritten_query"),
        "token_usage":             _llm_tracker.snapshot(),
    }


# ---------------------------------------------------------------------------
# Demo quality scorer
# ---------------------------------------------------------------------------

_HIGH_DEPTH_CATS = {"deep_retrieval", "cross_company_reasoning", "earnings_grounding", "context_aggregation"}


def _demo_score(record: dict) -> float:
    """Score 0–4 for recruiter demo appeal. Only passing answers qualify."""
    judgment = record.get("judgment", {})
    pipeline = record.get("pipeline", {})

    if judgment.get("verdict") != "pass":
        return 0.0

    score = 0.0

    if record.get("category") in _HIGH_DEPTH_CATS:
        score += 1.5
    elif record.get("category") in {"adaptive_response", "strict_rag_only"}:
        score += 0.5

    if pipeline.get("citations_count", 0) >= 2:
        score += 0.5
    if pipeline.get("confidence", 0.0) >= 0.7:
        score += 0.5

    answer_len = len(pipeline.get("final_answer", ""))
    if answer_len >= 400:
        score += 1.0
    elif answer_len >= 200:
        score += 0.5

    if judgment.get("score", 0.0) >= 0.90:
        score += 0.5

    return score


# ---------------------------------------------------------------------------
# Analysis markdown writer
# ---------------------------------------------------------------------------

def _write_analysis_md(
    results: list,
    summary: dict,
    baseline: Optional[dict],
    out_dir: Path,
    timestamp: str,
) -> Path:
    """Write _analysis.md iteration log with metrics, demo questions, and next steps."""
    overall = summary["meta"]
    cat_stats = summary["category_summary"]

    # Failure type distribution
    failure_counts: dict[str, int] = {}
    for r in results:
        ft = r.get("failure_type", "unknown")
        failure_counts[ft] = failure_counts.get(ft, 0) + 1

    # Top 5 demo-worthy questions
    demo_scored = sorted(results, key=_demo_score, reverse=True)[:5]

    # Baseline delta
    baseline_note = ""
    if baseline:
        prev = baseline.get("overall_avg_score", 0.0)
        curr = overall["overall_avg_score"]
        delta = round(curr - prev, 3)
        sign = "+" if delta >= 0 else ""
        baseline_note = f" (Δ {sign}{delta} vs baseline {prev:.3f})"

    # Cost / latency aggregates
    total_usage = overall.get("token_usage", {})
    total_cost  = total_usage.get("total_cost_usd", 0.0)
    total_tok   = total_usage.get("total_tokens", 0)
    total_inp   = total_usage.get("total_input_tokens", 0)
    total_out   = total_usage.get("total_output_tokens", 0)
    latencies   = [r["timing"]["pipeline_s"] for r in results if r.get("timing", {}).get("pipeline_s")]
    avg_lat     = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    total_lat   = round(sum(latencies), 1)

    qfile_name = overall.get("questions_file", "question_v2.txt")
    lines = [
        f"# AlphaLens Eval — Iteration Log",
        f"**Timestamp**: {timestamp}  ",
        f"**Questions**: {qfile_name} ({overall['total_questions']} questions, "
        f"{'smoke' if overall['mode'] == 'smoke' else 'full'} mode)",
        "",
        "---",
        "",
        "## Score Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Overall avg score | **{overall['overall_avg_score']:.3f}**{baseline_note} |",
        f"| Pass | {overall['pass_count']} ({100*overall['pass_count']//max(overall['total_questions'],1)}%) |",
        f"| Partial | {overall['partial_count']} |",
        f"| Fail | {overall['fail_count']} |",
        f"| Confidence calibration RMSE | {overall.get('calibration_rmse', 'N/A')} |",
        f"| Total pipeline time | {total_lat}s (avg {avg_lat}s/Q) |",
        f"| Total LLM tokens | {total_tok:,} ({total_inp:,} in / {total_out:,} out) |",
        f"| **Total cost** | **${total_cost:.4f}** (DeepSeek V3) |",
        "",
        "### Per-Category Scores",
        "",
        f"| Category | n | Pass | Partial | Fail | Avg Score | Avg M1 | Avg M2 | Avg M3 | Avg M6 | Dominant Failure |",
        f"|----------|---|------|---------|------|-----------|--------|--------|--------|--------|-----------------|",
    ]

    for cat, s in cat_stats.items():
        delta_str = ""
        if baseline and "categories" in baseline and cat in baseline["categories"]:
            prev_cat = baseline["categories"][cat].get("avg_score", 0.0)
            d = round(s["avg_score"] - prev_cat, 3)
            delta_str = f" ({'+' if d >= 0 else ''}{d})"
        lines.append(
            f"| {cat} | {s['n']} | {s['pass']} | {s['partial']} | {s['fail']} "
            f"| {s['avg_score']:.3f}{delta_str} "
            f"| {s.get('avg_m1', 'N/A')} | {s.get('avg_m2', 'N/A')} "
            f"| {s.get('avg_m3', 'N/A')} | {s.get('avg_m6', 'N/A')} "
            f"| {s.get('dominant_failure', '-')} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Failure Type Distribution",
        "",
    ]
    for ft, count in sorted(failure_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count // max(len(results), 1)
        lines.append(f"- **{ft}**: {count} questions ({pct}%)")

    # ── Per-question latency + cost table ─────────────────────────────────────
    lines += [
        "",
        "---",
        "",
        "## Per-Question Latency & Cost",
        "",
        "| # | Category | Verdict | M7 | Latency(s) | Tokens | Cost($) | Mode |",
        "|---|----------|---------|-----|-----------|--------|---------|------|",
    ]
    for idx_r, r in enumerate(results, 1):
        timing  = r.get("timing", {})
        tu      = timing.get("token_usage", {})
        lat     = timing.get("pipeline_s", 0.0) or 0.0
        tok     = tu.get("total_tokens", 0)
        cost_q  = tu.get("total_cost_usd", 0.0)
        verdict = r.get("judgment", {}).get("verdict", "?")
        m7      = r["metrics"]["m7_judge_score"]
        mode    = r["pipeline"].get("query_mode", "?")
        lines.append(
            f"| {idx_r} | {r['category']} | {verdict} | {m7:.2f} "
            f"| {lat:.1f} | {tok:,} | ${cost_q:.4f} | {mode} |"
        )

    # Per-category latency + cost aggregates
    cat_lat: dict[str, list] = {}
    cat_cost: dict[str, float] = {}
    for r in results:
        cat = r["category"]
        tu = r.get("timing", {}).get("token_usage", {})
        cat_lat.setdefault(cat, []).append(r.get("timing", {}).get("pipeline_s", 0.0) or 0.0)
        cat_cost[cat] = cat_cost.get(cat, 0.0) + tu.get("total_cost_usd", 0.0)

    lines += [
        "",
        "### Category Latency & Cost",
        "",
        "| Category | n | Avg Latency(s) | Total Cost($) |",
        "|----------|---|---------------|--------------|",
    ]
    for cat in cat_stats:
        lats = cat_lat.get(cat, [0])
        avg_l = round(sum(lats) / max(len(lats), 1), 1)
        lines.append(f"| {cat} | {len(lats)} | {avg_l} | ${cat_cost.get(cat, 0.0):.4f} |")

    lines += [
        "",
        f"**Total cost: ${total_cost:.4f}** | **Total time: {total_lat}s** | **Avg: {avg_lat}s/Q**",
        "",
        "---",
        "",
        "## Top 5 Demo-Worthy Questions",
        "",
        "Questions that passed with high confidence, structured answers, and recruiter appeal.",
        "",
    ]

    for i, r in enumerate(demo_scored, 1):
        pipeline = r.get("pipeline", {})
        judgment = r.get("judgment", {})
        demo_s = _demo_score(r)
        tu_r   = r.get("timing", {}).get("token_usage", {})
        lines += [
            f"### {i}. [{r.get('category')}] Demo Score: {demo_s:.1f}/4.0",
            f"**Question**: {r.get('question')}",
            f"**Verdict**: {judgment.get('verdict')} ({judgment.get('score', 0):.2f})  ",
            f"**Citations**: {pipeline.get('citations_count', 0)}  "
            f"**Confidence**: {pipeline.get('confidence', 0):.3f}  "
            f"**Answer length**: {len(pipeline.get('final_answer', ''))} chars  "
            f"**Latency**: {r.get('timing',{}).get('pipeline_s',0):.1f}s  "
            f"**Cost**: ${tu_r.get('total_cost_usd',0):.4f}",
            f"**Why demo-worthy**: "
            + ("Deep retrieval + structured financial answer with citations. " if r.get("category") in _HIGH_DEPTH_CATS else "")
            + ("Cross-company comparison with data — visually impressive. " if r.get("category") == "cross_company_reasoning" else "")
            + ("Earnings transcript grounding with management quotes. " if r.get("category") == "earnings_grounding" else "")
            + f"Judge score {judgment.get('score', 0):.2f} with reasoning: {judgment.get('reasoning', '')[:120]}",
            f"**Answer preview**: {pipeline.get('final_answer', '')[:200]}…",
            "",
        ]

    lines += [
        "---",
        "",
        "## Remaining Issues",
        "",
    ]

    # Auto-generate remaining issues from failure distribution
    dominant = max(failure_counts, key=failure_counts.get) if failure_counts else "none"
    issue_map = {
        "routing_failure":   "Routing failures dominate — audit ANALYSIS_PROMPT query_mode logic and web_search flag handling.",
        "retrieval_failure": "Retrieval failures dominate — check BM25 weights, pgvector pool size, and table boosting.",
        "hallucination":     "Hallucination failures dominate — tighten RESPONSE_PROMPT grounding rules and context budget.",
        "reasoning_failure": "Reasoning failures dominate — improve sub-question decomposition and answer structure prompts.",
        "none":              "No dominant failure type — all categories performing well.",
    }
    lines.append(f"- **Primary issue**: {issue_map.get(dominant, 'Mixed failures — investigate per-category.')}")

    failing_cats = [cat for cat, s in cat_stats.items() if s["avg_score"] < 0.5]
    if failing_cats:
        lines.append(f"- **Failing categories** (avg < 0.5): {', '.join(failing_cats)}")

    lines += [
        "",
        "---",
        "",
        f"*Generated {timestamp} · AlphaLens Eval Harness*",
    ]

    out_path = out_dir / "_analysis.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

class _TeeWriter:
    """Mirrors every write to two streams — used to tee stdout/stderr into eval.log."""
    def __init__(self, primary, secondary):
        self._primary   = primary
        self._secondary = secondary

    def write(self, text):
        self._primary.write(text)
        try:
            self._secondary.write(text)
        except Exception:
            pass

    def flush(self):
        self._primary.flush()
        try:
            self._secondary.flush()
        except Exception:
            pass

    def fileno(self):
        return self._primary.fileno()

    @property
    def encoding(self):
        return getattr(self._primary, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self._primary, "errors", "replace")


async def main(
    smoke: bool = False,
    categories_filter: Optional[list[str]] = None,
    set_baseline: bool = False,
    questions_files: Optional[list[Path]] = None,
) -> None:
    # Create output dir first — log file goes there for easy correlation with results
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode_suffix = "_smoke" if smoke else "_fulleval"
    out_dir = EVALS_DIR / f"{timestamp}{mode_suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Tee stdout + stderr → eval.log so the complete terminal output is captured
    log_file = out_dir / "eval.log"
    _log_fh = open(log_file, "w", encoding="utf-8", buffering=1)
    sys.stdout = _TeeWriter(sys.__stdout__, _log_fh)
    sys.stderr = _TeeWriter(sys.__stderr__, _log_fh)

    # Also route logger calls (WARNING/INFO from libraries) to the same file
    global logger
    stream_handler = logging.StreamHandler(_log_fh)
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    logging.getLogger().addHandler(stream_handler)  # root logger → catches all libraries
    logger.setLevel(logging.INFO)
    logger.info(f"Output dir: {out_dir}")

    from app.utils.database import create_pool
    from agent.graph import graph as research
    import openai

    openai_client = openai.OpenAI()

    print("Initialising DB pool…")
    await create_pool()

    print("Building BM25 index…")
    from agent.rag.search_engine import build_bm25_corpus
    await build_bm25_corpus()
    print("BM25 ready.\n")

    # Load question file(s) — supports multiple files for combined evaluation.
    # When >1 file is given, categories are prefixed with a short version tag
    # (e.g. "v2_hybrid_routing", "v3_hybrid_routing") to avoid collisions.
    qfiles = questions_files if questions_files else [QUESTIONS_FILE]
    for qf in qfiles:
        if not qf.exists():
            raise FileNotFoundError(f"Questions file not found: {qf}")
    multi = len(qfiles) > 1

    def _version_prefix(qfile: Path) -> str:
        m = re.search(r'(v\d+)', qfile.stem)
        return f"{m.group(1)}_" if m else f"{qfile.stem[:3]}_"

    data: dict = {}
    for qf in qfiles:
        prefix = _version_prefix(qf) if multi else ""
        file_data = json.loads(qf.read_text(encoding="utf-8"))
        for cat, meta in file_data.items():
            data[f"{prefix}{cat}"] = meta

    # Build task list
    tasks: list[tuple] = []  # (category, expected_behavior, question, web_search, gt_entry)
    for category, meta in data.items():
        if categories_filter and category not in categories_filter:
            continue
        expected = meta.get("expected_behavior", "")
        web_search = meta.get("web_search", False)
        gt_map = meta.get("ground_truth_map", {})
        for q in meta.get("questions", []):
            gt_entry = gt_map.get(q, {})
            tasks.append((category, expected, q, web_search, gt_entry))

    if smoke:
        # Pick 4 representative questions covering all routing modes:
        #   1. rag_only (SEC/transcript only)         → strict_rag_only or deep_retrieval
        #   2. hybrid (RAG + web)                     → hybrid_routing
        #   3. web_only within scope (real-time data) → web_trigger
        #   4. out-of-scope / hallucination refusal   → hallucination_control
        _smoke_pref = ["strict_rag_only", "hybrid_routing", "web_trigger", "hallucination_control"]
        smoke_tasks: list[tuple] = []
        for pref in _smoke_pref:
            for t in tasks:
                if pref in t[0] and not any(pref in st[0] for st in smoke_tasks):
                    smoke_tasks.append(t)
                    break
        # Fallback: fill to 4 from the front if any preferred category is missing
        seen_q = {t[2] for t in smoke_tasks}
        for t in tasks:
            if t[2] not in seen_q and len(smoke_tasks) < 4:
                smoke_tasks.append(t)
                seen_q.add(t[2])
        tasks = smoke_tasks[:4]
        mode_labels = [t[0] for t in tasks]
        print(f"SMOKE MODE — {len(tasks)} questions covering: {', '.join(mode_labels)}\n")
    else:
        print(f"Running {len(tasks)} questions across {len({t[0] for t in tasks})} categories\n")

    # ── Phase 1: Pipeline runs ────────────────────────────────────────────────
    print("=" * 60)
    print("Phase 1: Pipeline")
    print("=" * 60)

    pipeline_results: list[dict] = []
    session_ids: list[str] = []

    for idx, (category, expected_behavior, question, web_search, gt_entry) in enumerate(tasks, 1):
        session_id = f"eval-{timestamp}-{idx:02d}"
        session_ids.append(session_id)
        q_short = question[:70]
        print(f"[{idx}/{len(tasks)}] [{category}] {q_short}{'…' if len(question) > 70 else ''}")

        t0 = time.monotonic()
        result = await run_question(research, question, web_search=web_search, session_id=session_id)
        tu = result.get("token_usage", {})
        print(f"   pipeline={result['elapsed_s']}s  chunks={result['context_chunks_count']}  "
              f"mode={result['query_mode']}  iter={result['iteration_count']}  "
              f"tokens={tu.get('total_tokens',0)}  cost=${tu.get('total_cost_usd',0):.4f}")

        pipeline_results.append(result)

        # Progressive save — includes full answer + chunks so it's useful even if eval stalls
        q_slug = question[:50].replace(" ", "_").replace("/", "_").replace("?", "").replace("!", "")
        partial_path = out_dir / f"{idx:02d}_{category}_{q_slug}.json"
        partial_path.write_text(json.dumps({
            "status": "pipeline_complete",
            "category": category, "question": question,
            "timing": {"pipeline_s": result["elapsed_s"], "token_usage": tu},
            "pipeline": {k: result.get(k) for k in (
                "final_answer", "query_mode", "context_chunks_count", "sec_chunks_count",
                "transcript_chunks_count", "news_count", "citations_count",
                "confidence", "eval_score", "iteration_count", "intent",
                "tickers_extracted", "is_out_of_scope", "cache_hit",
                "rewritten_query", "sub_questions", "error",
            )} | {
                "context_chunks": result.get("context_chunks", []),
                "news_chunks":    result.get("news_chunks", []),
                "citations":      result.get("citations", []),
            },
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Phase 2: RAGAS batch (M2, M4) ────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Phase 2: RAGAS metrics (M2 faithfulness, M4 context_precision)")
    print("=" * 60)

    _SPECIAL_TOKENS = {"NOT_IN_DATABASE", "INVALID_INPUT", "BROAD_QUERY_HANDLED", "WEB_SEARCH_TRIGGERED"}

    ragas_inputs = []
    ragas_skip_flags = []  # True when RAGAS should be skipped (special-token-only questions)
    for i, (pipeline, (category, _, question, _, gt_entry)) in enumerate(zip(pipeline_results, tasks)):
        key_facts = gt_entry.get("key_facts", [])
        # Skip RAGAS when key_facts are all special tokens — contexts will be empty/irrelevant
        # and faithfulness would score 0.0 for correct refusals, skewing failure classification
        is_special_only = bool(key_facts) and all(kf in _SPECIAL_TOKENS for kf in key_facts)
        ragas_skip_flags.append(is_special_only)

        if is_special_only:
            ragas_inputs.append({"question": question, "answer": "", "contexts": ["[skipped]"], "ground_truth": ""})
            continue

        query_mode = pipeline.get("query_mode", "rag_only")
        if query_mode == "web_only":
            # For web-only answers use news chunks as contexts; SEC chunks are empty/irrelevant
            news_chunks = pipeline.get("news_chunks", [])
            contexts = [(c.get("text") or c.get("chunk_text") or "") for c in news_chunks]
        else:
            all_chunks = pipeline.get("context_chunks", [])
            contexts = [(c.get("text") or c.get("chunk_text") or "") for c in all_chunks]

        ground_truth = gt_entry.get("ground_truth", "")
        ragas_inputs.append({
            "question":     question,
            "answer":       pipeline.get("final_answer", ""),
            "contexts":     contexts,
            "ground_truth": ground_truth,
        })

    print(f"Running RAGAS on {len(ragas_inputs)} questions… (calls OpenAI)")
    ragas_scores_raw = await asyncio.to_thread(_run_ragas_batch, ragas_inputs)
    # Replace scores with None for skipped (special-token) questions
    ragas_scores = [
        {"faithfulness": None, "context_precision": None,
         "context_recall": None, "answer_relevancy": None} if skip else scores
        for skip, scores in zip(ragas_skip_flags, ragas_scores_raw)
    ]
    print("RAGAS done.\n")

    # ── Phase 3: Judge calls (M7) — parallel ─────────────────────────────────
    print("=" * 60)
    print("Phase 3: Judge evaluation (M7, tiered model)")
    print("=" * 60)

    # Compute M1 first (needed for judge model selection)
    m1_scores = []
    for pipeline, (_, _, question, web_search, gt_entry) in zip(pipeline_results, tasks):
        key_facts = gt_entry.get("key_facts", [])
        m1 = fact_check(key_facts, pipeline.get("final_answer", ""), pipeline)
        m1_scores.append(m1)

    judge_sem = asyncio.Semaphore(8)  # cap concurrent judge calls to stay under GPT-4o TPM

    async def _judge_with_sem(**kwargs):
        async with judge_sem:
            return await _llm_judge(**kwargs)

    judge_coros = []
    for i, (pipeline, (category, expected_behavior, question, _, gt_entry)) in enumerate(
            zip(pipeline_results, tasks)):
        judge_coros.append(_judge_with_sem(
            openai_client=openai_client,
            question=question,
            category=category,
            expected_behavior=expected_behavior,
            answer=pipeline.get("final_answer", ""),
            context_chunks=pipeline.get("context_chunks", []),
            ground_truth=gt_entry.get("ground_truth", ""),
            m1_score=m1_scores[i],
            pipeline=pipeline,
        ))

    judgments = await asyncio.gather(*judge_coros)
    print("Judge done.\n")

    # ── Phase 4: Assemble records ─────────────────────────────────────────────
    results: list[dict] = []
    cat_summary: dict[str, list] = {}  # category → list of per-question metric dicts

    for i, (pipeline, ragas, judgment, m1, session_id,
            (category, expected_behavior, question, web_search, gt_entry)) in enumerate(
            zip(pipeline_results, ragas_scores, judgments, m1_scores, session_ids, tasks)):

        key_facts = gt_entry.get("key_facts", [])
        ground_truth = gt_entry.get("ground_truth", "")

        # Metrics — M2/M4 may be None for special-token-only questions (skipped RAGAS)
        m2_raw = ragas.get("faithfulness")       # None or float
        m4_raw = ragas.get("context_precision")
        m5_raw = ragas.get("answer_relevancy")   # supplementary; not in avg
        mcr_raw = ragas.get("context_recall")    # supplementary; not in avg
        m2  = m2_raw  if m2_raw  is not None else 1.0  # skipped → no hallucination penalty
        m4  = m4_raw  if m4_raw  is not None else 0.0
        m5  = m5_raw  if m5_raw  is not None else None  # None = not computed this run
        mcr = mcr_raw if mcr_raw is not None else None
        m3  = retrieval_recall(key_facts, pipeline.get("context_chunks", []))
        m6  = routing_check(web_search, pipeline.get("query_mode", "rag_only"))
        m7  = judgment.get("score", 0.0)
        # Use raw M2 (None = skipped) in failure classification to avoid spurious hallucination flags
        failure_type = classify_failure(m1, m2_raw if m2_raw is not None else 1.0, m3, m6)

        verdict = judgment.get("verdict", "fail")
        icon = "[PASS]" if verdict == "pass" else ("[PART]" if verdict == "partial" else "[FAIL]")
        model_tag = judgment.get("judge_model", "?")
        m5_str  = f" M5(AR)={m5:.2f}" if m5 is not None else ""
        mcr_str = f" MCR={mcr:.2f}"   if mcr is not None else ""
        print(f"[{i+1}/{len(tasks)}] {icon} {verdict} ({m7:.2f}) | "
              f"M1={m1:.2f} M2={m2:.2f} M3={m3:.2f} M6={m6}{m5_str}{mcr_str} | "
              f"failure={failure_type} | judge={model_tag}")

        record = {
            "category":         category,
            "expected_behavior": expected_behavior,
            "question":         question,
            "ground_truth":     ground_truth,
            "key_facts":        key_facts,
            "failure_type":     failure_type,
            "langsmith":        make_langsmith_block(session_id, pipeline.get("iteration_count", 0),
                                                     pipeline.get("is_out_of_scope", False)),
            "metrics": {
                "m1_factual_correctness":  m1,
                "m2_faithfulness":         m2,
                "m3_retrieval_recall":     m3,
                "m4_context_precision":    m4,
                "m5_answer_relevancy":     m5,   # supplementary — not in score average
                "m5_context_recall":       mcr,  # supplementary — not in score average
                "m6_routing_accuracy":     m6,
                "m7_judge_score":          m7,
            },
            "timing": {
                "pipeline_s":  pipeline.get("elapsed_s"),
                "token_usage": pipeline.get("token_usage", {}),
            },
            "pipeline": {
                "final_answer":            pipeline.get("final_answer"),
                "citations":               pipeline.get("citations"),
                "citations_count":         pipeline.get("citations_count"),
                "context_chunks":          pipeline.get("context_chunks"),
                "context_chunks_count":    pipeline.get("context_chunks_count"),
                "sec_chunks_count":        pipeline.get("sec_chunks_count"),
                "transcript_chunks_count": pipeline.get("transcript_chunks_count"),
                "news_chunks":             pipeline.get("news_chunks"),
                "news_count":              pipeline.get("news_count"),
                "tickers_extracted":       pipeline.get("tickers_extracted"),
                "is_out_of_scope":         pipeline.get("is_out_of_scope"),
                "query_mode":              pipeline.get("query_mode"),
                "confidence":              pipeline.get("confidence"),
                "eval_score":              pipeline.get("eval_score"),
                "cache_hit":               pipeline.get("cache_hit"),
                "iteration_count":         pipeline.get("iteration_count"),
                "rewritten_query":         pipeline.get("rewritten_query"),
                "intent":                  pipeline.get("intent"),
                "sub_questions":           pipeline.get("sub_questions"),
                "error":                   pipeline.get("error"),
            },
            "judgment": judgment,
        }
        results.append(record)
        cat_summary.setdefault(category, []).append({
            "verdict": verdict, "score": m7,
            "m1": m1, "m2": m2, "m3": m3, "m6": m6,
            "failure_type": failure_type,
        })

    # ── Save per-question JSONs ────────────────────────────────────────────────
    for idx, record in enumerate(results, 1):
        q_slug = record["question"][:50].replace(" ", "_").replace("/", "_").replace("?", "")
        out_path = out_dir / f"{idx:02d}_{record['category']}_{q_slug}.json"
        out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Aggregate ─────────────────────────────────────────────────────────────
    all_judge_scores = [r["metrics"]["m7_judge_score"] for r in results]
    overall_avg = round(sum(all_judge_scores) / len(all_judge_scores), 3) if all_judge_scores else 0.0

    # Aggregate token/cost across all questions
    def _sum_usage(results: list) -> dict:
        inp  = sum(r["timing"].get("token_usage", {}).get("total_input_tokens",  0) for r in results)
        out  = sum(r["timing"].get("token_usage", {}).get("total_output_tokens", 0) for r in results)
        cost = round(sum(r["timing"].get("token_usage", {}).get("total_cost_usd", 0.0) for r in results), 5)
        return {"total_input_tokens": inp, "total_output_tokens": out,
                "total_tokens": inp + out, "total_cost_usd": cost}

    total_token_usage = _sum_usage(results)

    # Confidence calibration RMSE
    pairs = [(r["pipeline"]["confidence"] or 0.0, r["metrics"]["m7_judge_score"]) for r in results]
    calib_rmse = round(math.sqrt(sum((c - s) ** 2 for c, s in pairs) / max(len(pairs), 1)), 3)

    from collections import Counter
    cat_stats: dict[str, dict] = {}
    for cat, entries in cat_summary.items():
        cat_scores   = [e["score"] for e in entries]
        failure_mode = Counter(e["failure_type"] for e in entries).most_common(1)[0][0]
        cat_stats[cat] = {
            "n":               len(entries),
            "pass":            sum(1 for e in entries if e["verdict"] == "pass"),
            "partial":         sum(1 for e in entries if e["verdict"] == "partial"),
            "fail":            sum(1 for e in entries if e["verdict"] == "fail"),
            "avg_score":       round(sum(cat_scores) / len(cat_scores), 3),
            "avg_m1":          round(sum(e["m1"] for e in entries) / len(entries), 3),
            "avg_m2":          round(sum(e["m2"] for e in entries) / len(entries), 3),
            "avg_m3":          round(sum(e["m3"] for e in entries) / len(entries), 3),
            "avg_m6":          round(sum(e["m6"] for e in entries) / len(entries), 3),
            "dominant_failure": failure_mode,
        }

    # Baseline delta
    baseline: Optional[dict] = None
    if BASELINE_PATH.exists():
        try:
            baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    baseline_delta = None
    if baseline:
        baseline_delta = round(overall_avg - baseline.get("overall_avg_score", 0.0), 3)

    summary_output = {
        "meta": {
            "timestamp":         timestamp,
            "mode":              "smoke" if smoke else "full",
            "questions_file":    " + ".join(qf.name for qf in qfiles),
            "total_questions":   len(results),
            "overall_avg_score": overall_avg,
            "calibration_rmse":  calib_rmse,
            "pass_count":        sum(1 for r in results if r["judgment"]["verdict"] == "pass"),
            "partial_count":     sum(1 for r in results if r["judgment"]["verdict"] == "partial"),
            "fail_count":        sum(1 for r in results if r["judgment"]["verdict"] == "fail"),
            "baseline_delta":    baseline_delta,
            "token_usage":       total_token_usage,
            "substrate": {
                "llm_provider":  os.getenv("LLM_PROVIDER", "auto"),
                "deepseek_key":  bool(os.getenv("DEEPSEEK_API_KEY")),
                "cerebras_key":  bool(os.getenv("CEREBRAS_API_KEY")),
                "openai_key":    bool(os.getenv("OPENAI_API_KEY")),
                "fmp_key":       bool(os.getenv("FMP_API_KEY")),
                "tavily_key":    bool(os.getenv("TAVILY_API_KEY")),
            },
        },
        "category_summary": cat_stats,
    }

    summary_path = out_dir / "_summary.json"
    summary_path.write_text(json.dumps(summary_output, indent=2, ensure_ascii=False), encoding="utf-8")

    # Analysis markdown
    analysis_path = _write_analysis_md(results, summary_output, baseline, out_dir, timestamp)

    # Optionally set baseline
    if set_baseline:
        baseline_data = {
            "timestamp":         timestamp,
            "overall_avg_score": overall_avg,
            "categories": {
                cat: {"avg_score": s["avg_score"], "pass_rate": round(s["pass"] / max(s["n"], 1), 3)}
                for cat, s in cat_stats.items()
            },
        }
        BASELINE_PATH.write_text(json.dumps(baseline_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nBaseline written → {BASELINE_PATH}")

    # ── Final report ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Results → {out_dir}")
    print(f"Summary → {summary_path.name}")
    print(f"Analysis → {analysis_path.name}")
    print(f"{'='*60}")
    print(f"Overall avg score: {overall_avg:.3f}"
          + (f"  (Δ {'+' if (baseline_delta or 0) >= 0 else ''}{baseline_delta} vs baseline)" if baseline_delta is not None else ""))
    print(f"Pass: {summary_output['meta']['pass_count']}  "
          f"Partial: {summary_output['meta']['partial_count']}  "
          f"Fail: {summary_output['meta']['fail_count']}")
    print(f"Calibration RMSE: {calib_rmse}")
    print(f"\n{'Category':<35} {'n':>3} {'pass':>5} {'avg':>6} {'M1':>6} {'M2':>6} {'M3':>6} {'M6':>5} {'dom_fail'}")
    print("-" * 85)
    for cat, s in cat_stats.items():
        print(f"{cat:<35} {s['n']:>3} {s['pass']:>5} {s['avg_score']:>6.3f} "
              f"{s['avg_m1']:>6.3f} {s['avg_m2']:>6.3f} {s['avg_m3']:>6.3f} "
              f"{s['avg_m6']:>5.2f} {s['dominant_failure']}")

    # Prompt for next iteration
    print(f"\n{'='*60}")
    demo_thresh = 0.72
    if overall_avg >= demo_thresh:
        print(f"Score {overall_avg:.3f} >= {demo_thresh} — DEMO-READY threshold reached.")
    else:
        gap = round(demo_thresh - overall_avg, 3)
        print(f"Score {overall_avg:.3f} is {gap} below demo-ready threshold ({demo_thresh}).")
    print(f"\nReview {analysis_path} for top demo questions and next steps.")
    print("Continue to next iteration? Check _analysis.md then re-run with fixes applied.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AlphaLens unified eval harness (question_v2.txt)")
    parser.add_argument("--smoke", action="store_true", help="Run first 3 questions only")
    parser.add_argument("--full", action="store_true", help="Run all questions")
    parser.add_argument("--category", nargs="+", metavar="CAT", help="Run specific categories")
    parser.add_argument("--input", nargs="+", type=Path, default=None,
                        help="Path(s) to question file(s). Multiple files are merged with version-prefixed categories.")
    parser.add_argument("--set-baseline", action="store_true",
                        help=f"Write results to {BASELINE_PATH.name} as new baseline")
    args = parser.parse_args()

    if not args.smoke and not args.full and not args.category:
        parser.error("Specify --smoke, --full, or --category")

    # Windows Python 3.14: ProactorEventLoop has asyncio executor teardown issues with
    # RAGAS concurrent I/O. SelectorEventLoop is stable for this workload.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(
        smoke=args.smoke,
        categories_filter=args.category,
        set_baseline=args.set_baseline,
        questions_files=args.input,
    ))
