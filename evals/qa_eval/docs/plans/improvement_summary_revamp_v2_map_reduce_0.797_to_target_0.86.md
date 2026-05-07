# AlphaLens v2 RAG Revamp — Improvement Summary
**Phase: Full Map-Reduce Pipeline Redesign**
**Baseline: 0.797 overall (v5 question set)**
**Target: ≥ 0.86 overall, earnings_grounding ≥ 0.75, cross_company_reasoning ≥ 0.78**

---

## Root Cause Diagnosis

All weak categories shared one root cause: **every retrieved chunk funneled into a single LLM call with one context budget, one routing decision, and a single ≤700-token answer**. This caused:

| Category | v5 Score | Failure Mode |
|---|---|---|
| earnings_grounding | 0.50 | Sparse transcript chunks → fabrication in single mega-context |
| cross_company_reasoning | 0.60 | Multiple tickers' chunks collide in one budget; first ticker dominates |
| context_aggregation | 0.70 | Multi-source synthesis diluted across single pass |
| hybrid_routing | 0.70 | Hallucination when web mis-routed into RAG-only path |

---

## Architecture Change: v1 → v2

### v1 (old)
```
analyze → retrieve_context (one big search) → generate (one LLM call, all chunks)
       → evaluate → [retry via rewrite_query] → finalize
```

### v2 (new, behind RAG_V2=true)
```
plan_research (Cartesian decomposition)
    ↓
fan_out_retrieval (parallel per-subq, transcript→10K fallback)
    ↓
per_subq_synth (parallel, strict-by-default, no_info honest)
    ↓
gap_filler (conditional: Tavily extract on failing sub-qs)
    ↓
aggregate (DeepSeek, clean mini-answers → final answer, max_tokens=2000)
    ↓
validate (structured JSON: score, missing_dimensions, refusal_appropriate)
    ↓
finalize | gap_filler retry (max 1 iter, only missing sub-qs)
```

---

## Changes Made

### Day 1 Morning — Prompt & Budget Changes

**`agent/rag/prompts.py`** — 4 new prompt pairs added:
- `DECOMPOSITION_PROMPT`: Cartesian sub-question decomposition with `axes={entities, metrics, time_refs, intents}`, `filing_year_lookup`, `preferred_source`, `needs_web`
- `SUB_SYNTHESIS_PROMPT`: Strict-by-default grounding; returns `{sub_answer, citations, no_info, confidence, missing_aspects}`
- `AGGREGATOR_PROMPT`: Combines sub-answers; markdown tables; honest no_info pass-through; `max_tokens=2000`
- `VALIDATOR_PROMPT`: Structured JSON judge `{score, missing_dimensions, refusal_appropriate, citation_coverage, needs_web_fallback}`

**`agent/llm/base.py`** — `temperature: float = 0.0` parameter added to all abstract methods.

**`agent/llm/{cerebras,deepseek,openai}_client.py`** — `temperature=0.0` plumbed through all call sites. DeepSeek gets 429 exponential backoff (1s→2s→4s→8s).

**`agent/llm/concurrency.py`** (new) — Per-provider asyncio semaphores: `CEREBRAS=4, DEEPSEEK=6, OPENAI=4`. Configurable via env vars.

**`agent/llm/factory.py`** — `create_fast()` returns Cerebras (for fast decomposition JSON). Temperature propagated.

**`agent/rag/response_generator.py`**:
- Removed 1000-char per-chunk clip (chunks now pass at full ingest size: 1400 prose, 4000 tables)
- `max_tokens` bumped 700 → 1800
- Context budgets: rag_only 6k→12k, hybrid 3.6k→9k, web 2.4k→4k

**`agent/rag/search_engine.py`**:
- Tavily `search_depth="advanced"`, limit 5→6
- `_clean_web_text` cap raised 3000→5000 chars
- New `tavily_extract(urls, max_chars_per_url=8000)` for gap_filler verbose extraction

### Day 1 Afternoon — Graph Rewiring

**`agent/graph/state.py`** — Added v2 fields:
```python
axes: Optional[Dict[str, Any]]
v2_sub_questions: List[Dict[str, Any]]
sub_answers: List[Dict[str, Any]]
time_refs: List[Dict[str, Any]]
validator_report: Optional[Dict[str, Any]]
```
Initialized to safe defaults in `graph.py:run()`.

**`agent/rag/sub_synthesizer.py`** (new, ~50 lines):
- Per-sub-q synthesis; strict no_info by default
- `temperature=0, max_tokens=400`

**`agent/rag/aggregator.py`** (new, ~80 lines):
- Aggregates sub-answers into final answer with token streaming
- `temperature=0, max_tokens=2000`

**`agent/graph/nodes.py`** — 6 new v2 nodes + 2 routing helpers:
- `node_plan_research`: Cerebras decomposition → axes + v2_sub_questions
- `node_fan_out_retrieval`: Parallel per-subq retrieval; transcript→10K fallback; always-parallel web
- `node_per_subq_synth`: Parallel sub-synthesis; emits `subq_complete` events
- `node_gap_filler`: Tavily extract on failing sub-qs; conditional
- `node_aggregate`: DeepSeek aggregation with token streaming
- `node_validate`: Structured JSON validator; score threshold 0.70
- `route_after_plan`: Out-of-scope → finalize_early; else → fan_out_retrieval
- `route_after_validate`: score < 0.70 AND missing_dims → gap_filler retry; else → finalize

**`agent/graph/graph.py`** — v2 graph wired behind `RAG_V2=true` env flag. v1 preserved intact for rollback. `run()` initializes all v2 state fields.

### Day 2 Morning — Frontend Trace

**`app/websocket/handler.py`** — `status_callback` detects v2 step names and emits them as typed events (e.g. `{type: "plan_complete", axes: ..., sub_questions: [...]}`) instead of generic `{type: "status"}`.

**`frontend/src/lib/api.ts`** — `data?: Record<string, unknown>` added to `ReasoningStep`. 9 new v2 WS event interfaces (`WsPlanComplete`, `WsSubqStart`, etc.). `WsEvent` union extended.

**`frontend/src/pages/ChatPage.tsx`** — v2 structured events stored as `ReasoningStep` entries with `data` payload.

**`frontend/src/components/ReasoningTrace.tsx`** — Extended to auto-detect v2 pipeline (presence of `plan_complete` step) and render v2 UI:
- **Research plan card**: entity chips (indigo), metric chips (violet), time-ref chips (sky), intent chips
- **Sub-question grid**: mini-cards with live status (pending → retrieving → synthesizing → done/no_info/gap_filled), confidence, chunk count
- **Aggregating** loader while final answer is being assembled
- **Validation summary**: score badge, missing dimensions, refusal_appropriate flag
- Falls back to v1 trace for non-v2 queries

### Eval Sets

**`evals/qa_eval/question_v6_smoke.txt`** — 5 questions (S1-S5): single_simple, cross_company_simple, strict_refusal, hybrid_web, multi_part. ~45s smoke run.

**`evals/qa_eval/question_v6.txt`** — 15 questions (E01-E15) across 9 categories: year_scoped, cross_company_quant, multi_year_trend, transcript_grounding, strict_rag_hard, hybrid_dual, multi_hop_ratio, gap_fill_trigger, private_company_gap.

---

## Expected Impact per Category

| Category | v5 Score | Expected v2 | Mechanism |
|---|---|---|---|
| earnings_grounding | 0.50 | ≥ 0.75 | Per-subq synthesis → honest `no_info` instead of fabrication; transcript→10K fallback |
| cross_company_reasoning | 0.60 | ≥ 0.78 | Cartesian per-ticker sub-qs; each entity gets its own retrieval + synthesis budget |
| context_aggregation | 0.70 | ≥ 0.85 | Aggregator works from clean mini-answers, not raw chunks in one budget |
| hybrid_routing | 0.70 | ≥ 0.85 | Always-parallel web when `needs_web=True`; gap_filler for still-missing sub-qs |
| hallucination_control | ≥ 1.00 | ≥ 1.00 | Strict-by-default sub-synthesis; validator's refusal_appropriate flag |
| strict_rag, deep_retrieval | ~0.85 | no regression | No changes to reranker or BM25; per-subq isolation improves, not hurts |

---

## What Was Deliberately NOT Done

- Re-ingestion of SEC tables as JSON (deferred — DB check needed first)
- Embedding model upgrade (cross-encoder covers retrieval; not the bottleneck)
- Reranker score filter (reorder-only kept; per-subq isolation replaces filtering)
- Hard cap on sub-questions (Cartesian decomposition produces correct count naturally)
- Heuristic shortcuts anywhere (all routing is LLM-driven)
- Separate judge LLM pass (validator IS the judge)
- Regex temporal parsing (LLM-resolved `filing_year_lookup` in decomposition)

---

## Activation

```bash
# Enable v2 pipeline
export RAG_V2=true
python -m uvicorn app:app --reload --port 8000

# Run smoke test
python evals/qa_eval/run_eval.py --questions evals/qa_eval/question_v6_smoke.txt

# Run full v6 eval
python evals/qa_eval/run_eval.py --questions evals/qa_eval/question_v6.txt

# Rollback to v1 (no env var needed)
unset RAG_V2
python -m uvicorn app:app --reload --port 8000
```

---

## Finance-Agent Cross-Pollination

Patterns ported from the `finance-agent` reference repo:
1. **Per-source orchestration** → per-sub-question isolation (taken further with Cartesian decomposition)
2. **Transcript→10K fallback** when transcript chunks empty → directly attacks `earnings_grounding=0.50`
3. **Temporal resolution** via `time_refs` with `filing_year_lookup` → year_scoped category fix
4. **Streaming events from every stage** → new v2 WS event types

Patterns NOT ported (finance-agent does these worse):
- Hardcoded magic numbers, regex temporal parsing, no cross-encoder rerank, monolithic LLM, shallow evaluation
