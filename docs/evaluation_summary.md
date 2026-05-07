# How We Built a Self-Evaluating AI Financial Research Assistant — and What the Numbers Taught Us

> *A technical deep-dive into building, breaking, and improving a RAG system for equity research over 6+ evaluation sessions.*

---

When I started building AlphaLens, I had a naive assumption shared by most people new to RAG systems: *build good retrieval, pick a smart LLM, and the answers will be good.*

Six evaluation sessions and 70+ questions later, I can tell you that assumption is wrong in every interesting way.

This post chronicles the real story of building an agentic financial research assistant — from the ugly 0.546 baseline to a production-stable 0.784 combined score — with specific technical lessons that apply to any RAG system you're building.

---

## What We Built

[AlphaLens](https://alphalens-production-15e1.up.railway.app) answers financial questions about public companies by:

1. Extracting intent, tickers, and query mode from the question
2. Retrieving relevant chunks from SEC 10-K filings (32,009 chunks, 33 companies) and earnings transcripts (17,836 chunks, 27 companies)
3. Generating a grounded, cited answer using DeepSeek V3
4. **Self-evaluating its own confidence** and retrying if quality is low

The pipeline is a [LangGraph](https://github.com/langchain-ai/langgraph) state machine:

```
User Question → plan_search → retrieve_context → generate_answer
                                    ↑                    ↓
                             rewrite_query ←── evaluate_quality
                                                    (≥0.65?) → finalize
```

For retrieval, we use a hybrid pipeline: `pgvector` semantic search + `BM25` keyword search → `RRF` rank fusion → `cross-encoder reranking`. For generation, DeepSeek V3 is primary (no daily quota, 35x cheaper than GPT-4o), with Cerebras Qwen-3-235B and OpenAI GPT-4.1-mini as fallbacks.

---

## The Evaluation Framework

Before the story: the measurement system.

We built an 8-metric evaluation harness that runs the full pipeline on question sets with pre-generated ground truth:

| Metric | What It Measures | Requires LLM? |
|--------|----------------|---|
| M1 | % of key facts found in answer (fuzzy match) | No |
| M2 | RAGAS faithfulness — answer grounded in retrieved context | Yes (GPT-4o) |
| M3 | % of key facts found in top-K retrieved chunks | No |
| M4 | RAGAS context precision — chunks are relevant | Yes (GPT-4o) |
| M6 | Routing accuracy — does observed mode match expected? | No |
| M7 | GPT-4o judge: pass / partial / fail | Yes (GPT-4o) |

**Score = mean(M1, M2, M3, M4, M6, M7)**

We also tracked hallucination control (a special M1-derived metric) and latency separately.

### Distributed Tracing with LangSmith

To verify the pipeline's execution paths in production, we instrumented it with LangSmith:

<div align="center">
<table>
<tr>
<td align="center" width="300"><a href="../../assets/traces/langsmith-web.png"><img src="../../assets/traces/langsmith-web.png" width="280" alt="Web Search Path"/></a><br/><sub><b>Web Search Path</b><br/>Tavily routing</sub></td>
<td align="center" width="300"><a href="../../assets/traces/langsmith-finalise-early.png"><img src="../../assets/traces/langsmith-finalise-early.png" width="280" alt="Out-of-Scope Path"/></a><br/><sub><b>Out-of-Scope Path</b><br/>Early finalization</sub></td>
<td align="center" width="300"><a href="../../assets/traces/langsmith-retry.png"><img src="../../assets/traces/langsmith-retry.png" width="280" alt="Retry Loop"/></a><br/><sub><b>Retry Loop Path</b><br/>Query rewrite on low eval</sub></td>
</tr>
</table>
</div>

> Run: `LANGCHAIN_TRACING_V2=true python tests/tracing/test_langsmith_trace.py` to generate live traces.

The `evals/qa_eval/` folder structure:

```
evals/qa_eval/
├── run_eval.py              # Computes M1-M8 for each question
├── generate_ground_truth.py # GPT-4o synthesizes GT from DB chunks
├── question_vN.txt          # Question sets with categories + GT
├── results/<timestamp>/     # Per-question JSON + summary
└── docs/                    # Improvement summaries (this post's source)
```

---

## Session 1: The Baseline (0.546)

The first full eval was on 24 questions across 10 categories. The results were humbling:

```
specific_financial_metrics:   0.00
hybrid_queries:               0.00
single_company_deep_dives:    0.55
cross_company_comparisons:    0.75
hallucination_control:        1.00
```

Two root causes dominated.

### Root Cause 1: The LLM Was Blind to Its Own Context

This was the most frustrating failure mode. The retrieved chunks contained the answer. The LLM said "data not available." Example:

> **Query:** "What was Google's operating cash flow in FY2025?"  
> **Context chunk 7:** "Operating cash flow was $164.7 billion for the year ended December 31, 2025"  
> **LLM:** "I don't have data for FY2025. The most recent I have is $101.7B for FY2023."

The LLM's parametric memory was overriding its retrieval context. A single added rule to `RESPONSE_PROMPT` fixed this: *"Scan ALL provided chunks before declaring data unavailable."*

### Root Cause 2: Financial Tables Were Being Thrown Away

Our retrieval pipeline used a cross-encoder (`ms-marco-TinyBERT-L-2-v2`) to rerank the top-20 hybrid results. This model was trained on prose-matching — and sparse financial tables like:

```
| Compute & Networking | 130,141 | 47,479 |
| Graphics             |  15,925 | 15,891 |
```

...scored lower than MD&A prose. The revenue tables were being dropped from context before the LLM saw them.

**Fix:** After cross-encoder reranking, inject the top-4 table-type chunks back from the RRF pool. The tables exist in the pool — they just get deprioritized. We bypass the reranker for this specific chunk type.

```python
# After CE rerank, inject table chunks from the pool
if boost_tables:
    table_candidates = [c for c in rrf_pool if c["chunk_type"] == "table"][:4]
    final_chunks = final_chunks[:-len(table_candidates)] + table_candidates
```

Simple. Effective. The `specific_financial_metrics` category went from 0.00 to 0.65+ in the next run.

---

## Sessions 2–3: The Measurement Was Wrong (0.685 → 0.740)

After the initial fixes, we moved to a calibrated 20-question set (v2). Baseline: 0.685. Then a strange thing happened — the score *dropped* to 0.585 after we applied more fixes.

The instinct was: "we broke something." The reality: **the evaluation system itself was broken.**

### Bug 1: Empty Ground Truth Inflated the Baseline

`generate_ground_truth.py` auto-generates ground truth by querying the DB and calling GPT-4o. When it retrieved poor chunks, it wrote: "Data not available." This became the ground truth.

When the pipeline later retrieved *good* chunks and gave a *correct* answer, the judge scored it **FAIL** — because the correct answer didn't match the wrong ground truth.

Fixing ground truth for 8–10 questions gave +0.082 on v3 scores **with zero pipeline changes.** This is the single most important lesson:

> **Fix your grading rubric before tuning your pipeline.**

### Bug 2: Cerebras Quota Exhaustion

Sequential 20-question eval runs exhaust Cerebras Qwen-3-235B's daily request quota by question 5-8. Everything then falls back to GPT-4o-mini, which hallucinates aggressively on financial data.

The same retrieval pipeline, same context, same prompt — but different answers because the LLM is different. Score swings of ±0.40 on individual questions across iterations.

**Fix:** DeepSeek V3 as primary. No daily quota. 35× cheaper than GPT-4o. When we switched, v3 score went from 0.720 to 0.802 in a single iteration.

### Bug 3: GPT-4o-mini as Judge

The judge model (`_select_judge_model`) was using GPT-4o-mini for questions with M1 ≥ 0.80 or M1 = 0.00. GPT-4o-mini gave inconsistent verdicts — the same correct answer with M1=M2=M3=1.00 would sometimes score FAIL.

**Fix:** Always use GPT-4o for all judge calls. Non-negotiable. +0.035 average in one change.

---

## The Combined Score (0.784) and the GT Calibration Lesson

After 6 iterations on v2 and 4 iterations on v3, combined v2+v3 score: **0.784** (40 questions).

The remaining 4 failures all had M1=1.00. The pipeline was correct. The evaluation standard was wrong. Our estimated GT-corrected score: **0.857**.

This is the most counterintuitive finding: for RAG systems, the evaluation system needs as much engineering as the pipeline itself.

---

## Session 4: Getting Routing to 100%

We moved to v4 (30 harder questions). The routing accuracy (M6) was 0.67 — the model sometimes confused `web_only` with `rag_only` or even `out_of_scope`.

Root cause: the original routing prompt used keyword heuristics. "If the question contains 'stock price' → web_only." This fails for edge cases.

**The fix:** A 3-step logical decision tree, not keyword matching:

```
STEP 1: Could a 10-K filed months ago contain this?
        If NO → web_only

STEP 2: Needs BOTH filing data AND recent external data?
        → hybrid

STEP 3: Everything else historical?
        → rag_only
```

M6 routing accuracy: **0.67 → 1.00** across all 70 questions. Perfect routing has been stable since.

We also discovered a subtle bug: "real-time market data" was listed under `out_of_scope` in the analysis prompt, causing NVDA stock price queries to be refused. Moved it to `web_only` where it belongs.

---

## Plan C: When "More Fixes" Made Things Worse

This is the session that taught me the most.

We applied 6 fixes simultaneously:
- Year-aware filtering (±1 window for offset fiscal years)
- Per-ticker retrieval decomposition for cross-company queries  
- Dynamic top_k scaling (more chunks for multi-year/multi-ticker queries)
- Strict-RAG numeric validator
- Hybrid dual-citation enforcement
- Metadata labels in chunk headers

Result: **v2 dropped from 0.755 → 0.670. v3 dropped from 0.810 → 0.708.**

The regression had one dominant cause:

> **The `strict_rag_block` prompt — designed to prevent hallucination — was injected into the response prompt for ALL `rag_only` queries.**

This caused the LLM to refuse to compute derived metrics. Example:

> **Query:** "What's LRCX's operating margin?"  
> **Context:** Both operating income and revenue were present in retrieved chunks.  
> **LLM:** "Operating margin data is not available in the retrieved context."

The LLM wouldn't compute `operating_income / revenue` because the `STRICT MODE` block said "only cite data explicitly in context." Both inputs were there. The derived metric wasn't. The LLM chose refusal.

**Fix:** Gate `strict_rag_block` on explicit user intent only:

```python
_STRICT_Q_RE = re.compile(
    r"\b(do not use general knowledge|only from retrieved)\b",
    re.IGNORECASE,
)
# Inject strict block ONLY when _question_wants_strict(question) returns True
```

**Lesson:** Overly aggressive faithfulness enforcement can be worse than no enforcement. The RESPONSE_PROMPT's chunk-grounding rules already handle the common case.

---

## Plan D: Recovery and the Minimum-Risk Approach

After Plan C, the goal was simple: restore v2/v3 scores without introducing new risks.

Key realization: the v2/v3 regression was measured *before* the mid-session `strict_rag_block` fix. Re-running against the current codebase showed full recovery.

**Plan D results:**
- v2: 0.755 → **0.774** (above pre-Plan-C baseline)
- v3: 0.810 → **0.797** (within noise of baseline)

Additional improvements in Plan D:
- **Round-robin interleaving** in `_format_chunks` for cross-company queries — prevents dominant-ticker crowdout
- **Removed numeric validator** — it was net-negative (false positives > true catches)
- **max_tokens 1200 → 700** — ~40% token cost reduction, no quality loss

---

## The v4 Reality Check (0.550)

The v4 honest score of 0.550 (after RAGAS was fixed and GT truncation corrected) looks worse than v2+v3's 0.784. This is expected and does not represent a pipeline regression.

Three reasons v4 is lower:

1. **Harder questions:** Cross-company data center rankings, multi-year trend aggregation, fiscal year offset math
2. **Less calibration:** v4 has had ~1 calibration pass vs 6+ for v2+v3
3. **Honest RAGAS:** M2 faithfulness was broken (0.00 for all) in the original 0.633 run. With RAGAS working, hallucinations are caught properly.

The same pipeline that achieves 0.773 on calibrated v2+v3 questions achieves 0.550 on harder, less-calibrated v4 questions. This is what we'd expect from a honest, multi-difficulty evaluation.

---

## Key Technical Lessons

### 1. Fix evaluation before fixing the pipeline

Ground truth calibration gave +0.082 on v3 with zero pipeline changes. If your judge says "wrong" and M1=M3=1.00, the judge is wrong.

### 2. LLM choice is the biggest variable

Switching DeepSeek V3 as primary gave +0.082 in one shot — more than 6 iterations of prompt tuning. A stable primary LLM with no quota exhaustion is critical for consistent evals.

### 3. Table chunks require special treatment

Cross-encoders trained on prose don't rank sparse financial tables well. Post-rerank injection is the pragmatic fix. A proper solution would be a domain-specific reranker fine-tuned on financial documents.

### 4. Strict mode must be user-intent gated

Overly aggressive "only cite from context" instructions prevent legitimate derived metrics (margins from revenue + operating income). Gate strict behavior on explicit user request.

### 5. GPT-4o-mini as judge is a reliability failure

The evaluation system needs a reliable judge more than the pipeline needs a smart LLM. gpt-4o-mini gave inconsistent verdicts on identical answers with M1=M2=M3=1.00. Always use gpt-4o for judgment.

### 6. Never run two evals simultaneously

Semantic cache hits from one run can contaminate retrieval quality in a concurrent run. The `deep_retrieval` regression in Session 6 was almost entirely from parallel eval interference.

---

## What's Working Well

At production-ready baseline (v2+v3 combined, 0.773):

| Capability | Score | Notes |
|-----------|-------|-------|
| Routing accuracy (M6) | **1.00** | Perfect across 70 questions |
| Hallucination control | **1.00** | Never fabricates for private companies |
| Web search integration | **0.90+** | Tavily with HTML cleaning |
| Earnings transcript Q&A | **0.75–0.85** | Strong on CEO/CFO commentary |
| Single-company SEC analysis | **0.80–0.95** | Segment revenue, risk factors, margins |

## What Still Needs Work

| Gap | Impact | Fix Required |
|-----|--------|-------------|
| Revenue vs operating income | strict_rag_only fails | Retrieval-layer chunk_type preference |
| Cross-company context imbalance | Multi-ticker comparisons weak | True interleaved format_chunks |
| Fiscal year offset precision | NVDA year=2024 = FY2025 data | ±1 applied, but gaps remain |

---

## Conclusion

Building a production-quality RAG system for financial research taught us three things that textbooks don't emphasize:

**The evaluation system is half the work.** Getting ground truth right, using a consistent judge model, and avoiding eval harness bugs (GT truncation, RAGAS logger, judge rate limits) matters as much as the pipeline itself.

**LLM choice cascades through everything.** DeepSeek V3 as a quota-free, cost-efficient primary completely changed our eval dynamics. A $35 saving per million tokens is irrelevant; the absence of rate-limit fallback to a weaker model is not.

**Enforce faithfulness carefully.** The strictest RAG systems — the ones that never hallucinate — are often the ones that refuse to answer questions they could answer from context. The right balance is: grounding rules in the prompt, not validator-enforced refusals.

AlphaLens is live at [alphalens-production-15e1.up.railway.app](https://alphalens-production-15e1.up.railway.app). The evaluation harness, question sets, and all improvement summaries are in the `evals/qa_eval/` directory — feel free to fork, run your own questions, and break things in new and interesting ways.

---

*Built with LangGraph · DeepSeek V3 · pgvector · BM25 · Sentence Transformers · FastAPI · React*  
*Full evaluation history: [docs/EVALUATION_RESULTS.md](EVALUATION_RESULTS.md)*
