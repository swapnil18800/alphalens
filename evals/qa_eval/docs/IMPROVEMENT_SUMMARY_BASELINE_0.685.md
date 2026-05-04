# AlphaLens RAG Eval — Baseline Iteration
## Establishing Baseline: 0.685 (35% pass rate) → Target 0.72+ (60%+ pass)

**Date**: May 1, 2026  
**Eval run**: `20260501T100112Z` — 20 questions, 10 categories, `question_v2.txt`  
**Status**: Baseline written to `evals/baseline.json`

---

## Baseline Scores

| Metric | Value |
|--------|-------|
| **Overall avg score** | **0.685** |
| Pass (M7 ≥ 0.85) | 7 / 20 (35%) |
| Partial | 11 / 20 |
| Fail | 2 / 20 |
| Confidence calibration RMSE | 0.282 |
| Demo-ready threshold gap | −0.035 avg, −25pp pass rate |

### Per-Category

| Category | Avg | Pass | M1 | M2 | M3 | M6 | Dominant Failure |
|----------|-----|------|----|----|----|----|-----------------|
| strict_rag_only | 0.950 | 2/2 | 1.0 | 0.778 | 1.0 | 1.0 | none |
| hallucination_control | 1.000 | 2/2 | 1.0 | 0.500 | 1.0 | 1.0 | — |
| edge_cases | 1.000 | 2/2 | 1.0 | 0.000 | 1.0 | 1.0 | — |
| adaptive_response | 0.750 | 1/2 | 1.0 | 0.606 | 1.0 | 1.0 | none |
| context_aggregation | 0.650 | 0/2 | 1.0 | 0.714 | 1.0 | 1.0 | none |
| cross_company_reasoning | 0.600 | 0/2 | 1.0 | 0.651 | 1.0 | 1.0 | none |
| hybrid_routing | 0.600 | 0/2 | 1.0 | 0.449 | 1.0 | 1.0 | hallucination |
| deep_retrieval | 0.600 | 0/2 | 0.70 | 0.916 | 1.0 | 1.0 | reasoning_failure |
| web_trigger | 0.400 | 0/2 | 1.0 | 0.000 | 1.0 | 1.0 | hallucination |
| **earnings_grounding** | **0.300** | 0/2 | 1.0 | 0.916 | 1.0 | 1.0 | none |

---

## Critical Finding: Ground Truth Is Missing for 17/20 Questions

Only 3 of 20 questions had ground truth generated (`generate_ground_truth.py` was only run in smoke mode). This means:

- **M1 (factual correctness) = 1.0 trivially** for all questions with `key_facts: []` — any answer passes
- **M3 (retrieval recall) = 1.0 trivially** for the same reason
- The baseline 0.685 reflects judge scores (M7) + RAGAS faithfulness (M2), **not** factual accuracy

**Impact**: The baseline overstates system quality. The true score will be lower once ground truth is populated and M1 becomes meaningful. However, this also means the first iteration improvement will partially come from measurement accuracy, not just model quality.

**Required before re-evaluation**: Run `python evals/qa_eval/generate_ground_truth.py --full`

---

## Root Cause Analysis

### Issue #1: Web Answer Scored as Hallucination (RAGAS Artifact)
**Category**: `web_trigger`  
**Score**: 0.400 avg — but the pipeline actually worked correctly

**What happened** (Q13 — "Latest AI chip developments in 2026"):
- Pipeline correctly routed to `web_only` mode, fetched 8 Tavily results
- Answer was well-structured with specific facts (AMD "Advancing AI 2026" event, Broadcom/Anthropic TPU, $120B ASIC market projection)
- **M2 (faithfulness) = 0.0**: RAGAS receives only sec/transcript chunks as `contexts`, not news chunks → faithfulness fails because the answer cites news sources RAGAS can't see
- **M7 (judge) = 0.20**: Judge (gpt-4o-mini) incorrectly wrote "fails to trigger a web search" despite `query_mode=web_only` and `news_count=8` being clearly present in the answer

**Root Causes**:
1. `_run_ragas_batch()` passes `sec_chunks + transcript_chunks` as context, but for web queries the relevant context is `news_chunks` — they never reach RAGAS
2. Judge (gpt-4o-mini) hallucinated a retrieval failure on a question that was answered correctly

**Fix**: 
1. In `_run_ragas_batch()`: for web_only queries, pass `news_chunks` (not SEC chunks) as context
2. Extend tiered judge to always use `gpt-4o` for `web_trigger` category (not just borderline M1)

**Expected gain**: web_trigger 0.40 → 0.75+ (+0.35 category, +~0.035 overall)

---

### Issue #2: Earnings Transcript Retrieval Missing CFO-Level Content
**Category**: `earnings_grounding`  
**Score**: 0.300 avg

**What happened** (Q6 — "What did Netflix's CFO say about subscriber growth in FY2025"):
- Pipeline returned: `"The provided context does not include specific statements from Netflix's CFO. Information unavailable."`
- Context had 15 SEC chunks and 5 transcript chunks, but **none contained CFO subscriber statements**
- Key data finding: Netflix's FY2025 10-K explicitly states: *"we discontinued the reporting of membership numbers, including average paying memberships... focusing instead on revenue and operating margin"*
- The CFO genuinely had nothing to say about subscriber growth because Netflix stopped reporting it — but the system said "unavailable" without explaining this context
- Ground truth was empty for this question → M1=1.0 trivially, judge = 0.0 (correctly caught "unavailable" response)

**Root Causes**:
1. Transcript chunks retrieved for NFLX don't contain the CFO subscriber growth discussion because Netflix stopped reporting subscribers in FY2025
2. The LLM fell back to "data unavailable" rather than explaining the business context (why the data doesn't exist)
3. Ground truth for `earnings_grounding` was never generated — the question assumes data exists when it may not

**Fix**:
1. Generate ground truth for `earnings_grounding` with `generate_ground_truth.py --category earnings_grounding`
2. Add to `RESPONSE_SYSTEM` prompt: "If a metric was discontinued by the company, explicitly state this with context (e.g., 'Netflix discontinued subscriber reporting in FY2025 and now focuses on revenue and operating margin as primary metrics')"
3. For Q6 specifically: accept that this question exposes a real data limitation; update it in the next question set

**Expected gain**: earnings_grounding 0.30 → 0.55+ (+0.25 category, +~0.025 overall)

---

### Issue #3: RAGAS M2=0.0 for Correct Refusals (Measurement Artifact)
**Categories**: `edge_cases`, `hallucination_control`

**What happened**: Both categories score M2=0.0 (RAGAS faithfulness) but both passed with M7=1.0. These are structurally correct answers that RAGAS can't evaluate:
- Edge cases: `final_answer` exists but `contexts = []` → RAGAS has nothing to verify against → faithfulness = 0
- Hallucination control: SpaceX/Stripe answers are refusals; context chunks are from unrelated companies (RAGAS retrieved other chunks to fill the pool)
- The `failure_type = "hallucination"` classification fires whenever M2 < 0.4, which triggers for all these correctly-handled cases

**Fix**: Skip RAGAS (set M2=None) for questions with `key_facts` containing only special tokens (`NOT_IN_DATABASE`, `INVALID_INPUT`, `BROAD_QUERY_HANDLED`, `WEB_SEARCH_TRIGGERED`). In `classify_failure()`, use M2 only when it's not None.

**Expected gain**: Cleans up spurious "hallucination" labels; no score change but more accurate failure attribution

---

### Issue #4: Deep Retrieval Missing Segment-Level Facts (Partial)
**Category**: `deep_retrieval`, score 0.600

**What happened** (Q3 — "NVIDIA FY2026 revenue segments"):
- M1=0.40 (reasoning_failure) — ground truth had key_facts that the answer partially missed
- The table boost was active but the FY2026 Note 16 segment table still not appearing in top-8 context
- Answer cited $130.1B total NVDA revenue but missed individual segment breakdown ($130.1B Compute & Networking, $9.1B Graphics)

**Fix**: This is the known Limitation #2 from the prior session. The immediate fix is intent-specific retrieval — for `deep_retrieval` + `revenue` intent, pre-fetch the top-3 "Note X" section chunks (segment tables live in the notes section of 10-Ks). This can be implemented as a section filter on pgvector: `WHERE section ILIKE 'note%'`.

**Expected gain**: deep_retrieval 0.60 → 0.75+ (+0.15 category, +~0.015 overall)

---

## Failure Type Distribution

| Failure Type | Count | Notes |
|-------------|-------|-------|
| none | 13 (65%) | Majority — no dominant failure mode |
| hallucination (M2 < 0.4) | 6 (30%) | Mostly RAGAS artifacts for web/edge/hallu categories |
| reasoning_failure | 1 (5%) | NVDA segment retrieval gap |
| routing_failure | 0 | M6=1.0 across all 20 questions — routing works |
| retrieval_failure | 0 | M3=1.0 trivially (empty key_facts) |

**Key insight**: M6=1.0 for all questions — routing is working. M3=1.0 trivially — retrieval can't be measured until ground truth is populated.

---

## Top 5 Demo-Worthy Questions

These questions show consistent pass verdicts and would impress a technical interviewer:

### 1. strict_rag_only — Apple Revenue Segments (M7=1.00)
"What were Apple's revenue segments in its FY2025 10-K?"
- Returns a clean markdown table with all 5 geographic segments + exact dollar figures
- Shows precise SEC data retrieval, not generic knowledge
- Reliable: passed consistently across smoke and full runs
- **Demo appeal**: Table format is visually striking; proves the system reads and cites actual filings

### 2. strict_rag_only — Google Business Segments (M7=0.90)
"What did Google report about its business segments in its FY2025 filings?"
- Structured multi-section answer: Google Services vs Google Cloud breakdown
- Cites actual FY2025 figures with revenue growth percentages
- **Demo appeal**: Multi-ticker multi-segment reasoning from real filings

### 3. adaptive_response — NVIDIA Overview (M7=0.90)
"What does NVIDIA do as of FY2026?"
- Full-stack description: data center AI infra, HPC, automotive, gaming
- Grounds in FY2026 context — not just general knowledge
- **Demo appeal**: Shows the system can answer both deep-dive and overview questions

### 4. hallucination_control — SpaceX Refusal (M7=1.00)
"What are SpaceX's revenue numbers for FY2025?"
- Short, crisp: "Data not available for SpaceX's revenue numbers for FY2025."
- No hallucinated figures — unlike GPT-4o raw which fabricates EBITDA estimates
- **Demo appeal**: Trust + safety demonstration — proves grounding is working

### 5. edge_cases — Gibberish Handling (M7=1.00)
"asldkjaslkdj"
- Redirects gracefully: "That question seems outside my scope. Try asking about a specific company's financials..."
- **Demo appeal**: Shows system robustness — good for live demo where audience might ask edge questions

---

## Proposed Next Iteration Fixes (Priority Order)

| Priority | Fix | Files | Expected Gain |
|----------|-----|-------|--------------|
| 1 | Generate ground truth for all 20 questions | `generate_ground_truth.py --full` | Enables accurate M1/M3 measurement |
| 2 | Pass news chunks to RAGAS for web_only queries | `run_eval.py:_run_ragas_batch()` | web_trigger M2: 0.0 → ~0.7 |
| 3 | Always use gpt-4o judge for web_trigger category | `run_eval.py:_select_judge_model()` | web_trigger M7: 0.2 → 0.7+ |
| 4 | Skip RAGAS for special-token-only key_facts | `run_eval.py:_run_ragas_batch()` | Remove spurious hallucination flags |
| 5 | Add discontinued-metric explanation to RESPONSE_SYSTEM | `agent/rag/prompts.py` | earnings_grounding: 0.30 → 0.50+ |
| 6 | Note-section pre-fetch for deep retrieval | `agent/graph/nodes.py` + `search_engine.py` | deep_retrieval: 0.60 → 0.75+ |

**Expected score after top 3 fixes**: 0.685 + 0.035 (web_trigger) + 0.025 (earnings) + 0.01 (calibration) ≈ **0.755**, pass rate ~55-60%

---

## Stopping Criteria Check

| Tier | Target | Current | Status |
|------|--------|---------|--------|
| Demo-ready | avg ≥ 0.72, pass ≥ 60% | 0.685, 35% | Not yet |
| Good | avg ≥ 0.78, pass ≥ 70% | — | Not yet |
| Iteration cap | 5 iterations | Iteration 1 | OK |

**Next step**: Confirm direction above, then run `generate_ground_truth.py --full` → apply fixes 2–5 → re-run `run_eval.py --full`

---

*Generated May 1, 2026 · AlphaLens Eval Harness · Baseline 0.685*
