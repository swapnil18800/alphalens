# AlphaLens — Session 4 Fixes (Complete Summary)

**Date:** 2026-05-02  
**Baseline entering session:** 0.633 (question_v4.txt, 30 questions)  
**Web/Hybrid subset result (6 q):** 0.733  
**Target:** 0.72+ (demo-ready)

---

## All Fixes Applied This Session

### 1. ANALYSIS_PROMPT — Definitional Routing (prompts.py)

**Problem:** LLM was routing real-time questions (stock price, live earnings) as `rag_only` instead of `web_only`. Heuristic keyword rules ("if it includes 'stock price'") were unreliable.

**Fix:** Rewrote routing section as a **3-step decision tree** with definitional logic:
- STEP 1: "Could a 10-K filed months ago contain this answer? If NO → `web_only`" — logical deduction, not heuristic
- STEP 2: Question explicitly asks for BOTH filing data AND recent external data → `hybrid`
- STEP 3: All other historical questions → `rag_only`

**Also fixed:** `out_of_scope` section previously listed "real-time market data: stock prices" as out-of-scope, which caused the LLM to mark NVDA stock price questions as out-of-scope instead of `web_only`. Removed that entry; added explicit note that real-time data routes as `web_only`, not out-of-scope.

**Impact:** web_trigger questions now correctly route as `web_only` (was failing as `hybrid` or `out_of_scope`). Confirmed in targeted 6-question eval.

---

### 2. nodes.py — Web Search Override (principled, not hardcoded)

**Problem (v1, rejected):** First version hardcoded keywords ("stock price", "NVDA") in nodes.py to override routing. User explicitly rejected: "NEVER overfit to specific thing by hardcoding."

**Fix (v2):** General principle:
```python
# When user explicitly enables web search, respect that intent.
# If LLM still chose rag_only (routing error), upgrade to hybrid minimum.
if not is_out_of_scope and query_mode == "rag_only":
    query_mode = "hybrid"
```
This is direction-setting, not keyword-matching. No company names or specific phrases hardcoded.

---

### 3. nodes.py — Hybrid Multi-Sub-Question: One Web Search

**Problem:** For hybrid questions with n sub-questions, the pipeline made n simultaneous Tavily API calls (one per sub-question via `asyncio.gather`). This caused:
- Eval hangs (n concurrent blocking executor calls)
- n × credit consumption
- Redundant duplicate news results needing dedup

**Fix:** Do **one** `search_web()` call for the base query in parallel with n RAG-only sub-question calls:
```python
web_task = search_engine.search_web(hybrid_web_q)
rag_tasks = [_search_one(q, force_rag_only=True) for q in sub_questions]
gathered = await asyncio.gather(web_task, *rag_tasks, return_exceptions=True)
```

**Latency:** Same or better. One Tavily call (not n) still runs in parallel with all RAG calls.

---

### 4. search_engine.py — Tavily Timeout (8s)

**Problem:** `_search_news` had no timeout. A hung Tavily call froze the entire asyncio event loop (the executor call ran indefinitely).

**Fix:** `asyncio.wait_for(..., timeout=8)` wraps the executor call. Timeout → graceful `[]` return, pipeline continues immediately. 8s is enough for Tavily (typical 2-5s response). In hybrid parallel mode, this caps the max web-wait overhead to 8s.

**Does it block anything?** No. `asyncio.wait_for` cancels only that coroutine. The rest of the pipeline (RAG, generation) is unaffected.

---

### 5. search_engine.py — Richer Tavily Chunks (raw_content)

**Problem:** Tavily's `content` field returns short 200-500 char snippets. The 2500-char truncation in `search_web` does nothing if Tavily only sends 200 chars to begin with.

**Fix:** Added `include_raw_content=True` to Tavily search call. This returns the full scraped page content in `raw_content` field (can be 2000-10000 chars). Logic:
```python
raw = item.get("raw_content", "").strip()
snippet = item.get("content", "").strip()
text = raw if len(raw) > len(snippet) else snippet  # prefer richer source
```
**Credit cost:** No extra credits. `include_raw_content=True` is a free flag (same 1 credit per basic search).

---

### 6. search_engine.py — LangSmith Web Search Span (@traceable)

**Problem:** Web search happened inside `retrieve_context` LangGraph node as a plain async function. LangSmith had no visibility — you could see news chunks in state but no `web_search` node in the trace.

**Fix:** Added `@traceable(name="web_search", run_type="tool")` decorator to `search_web()`. LangSmith now shows a named `web_search` tool span under `retrieve_context` in the trace timeline. Graceful fallback if `langsmith` not installed.

---

### 7. RESPONSE_PROMPT — Number Grounding Rules (prompts.py)

**Problem:** LLM was filling in financial figures from training knowledge rather than retrieved context. Year labels were being confused (FY2024 data labeled as FY2025).

**Fixes added to RESPONSE_PROMPT:**
- **CRITICAL NUMBER GROUNDING:** Every specific financial figure MUST be visibly present in context. If not in context, write "Exact [metric] for [company/period] not found in retrieved documents."
- **CRITICAL YEAR LABELING:** Confirm fiscal year label in context chunk matches the year stated in the answer. SEC filings contain prior-year comparatives — label them correctly.
- **Growth rate rule (generic):** When comparing growth rates, rank by YoY % growth. If any company completed a major acquisition, note inorganic vs organic distinction. (No company names hardcoded — previously had Broadcom/VMware specific reference, user rejected that.)

---

### 8. run_eval.py — eval.log: Complete Terminal Output

**Problem:** eval.log only captured `logger.info()` calls. `print()` statements (pipeline results, phase headers, RAGAS output, judge results, final summary) went only to terminal.

**Fix:** Added `_TeeWriter` class that mirrors every write to both terminal and the log file. Installed at `sys.stdout` and `sys.stderr` level, plus a root-logger `StreamHandler` pointing to the same file handle. Now every line visible in terminal is also in eval.log — identical to the reference `logs/full_eval_YYYYMMDD.log` format.

---

### 9. run_eval.py — Progressive JSON: Full Pipeline Data

**Problem:** Phase 1 partial save only stored 6 scalar fields. If eval got stuck before Phase 4, the JSON was useless — no chunk text, no citations, no mode details.

**Fix:** Progressive save now includes:
- All scalar pipeline fields (mode, counts, confidence, intent, tickers, etc.)
- `context_chunks` with full text
- `news_chunks` with full text and URL
- `citations` list
Phase 4 still overwrites with the complete record including metric scores.

---

### 10. run_eval.py — RAGAS: 4 Metrics

**Problem:** RAGAS only ran 2 metrics (faithfulness + context_precision). Missing `context_recall` and `answer_relevancy`.

**Fix:**
- `context_recall`: LLM-only, uses same gpt-4o-mini. Added with graceful fallback.
- `answer_relevancy`: embeddings-based. Uses local `all-MiniLM-L6-v2` via `LangchainEmbeddingsWrapper`. No OpenAI embedding cost.
- Both are **supplementary** — not included in the score average (M1/M3 already cover the same ground). Logged as `m5_answer_relevancy` and `m5_context_recall` in per-question JSON.

---

### 11. run_eval.py — Smoke Mode: 4 Routing Types

**Problem:** Smoke mode just took the first 4 questions — no guarantee of routing coverage.

**Fix:** Smart selection: 1 question from each of `strict_rag_only`, `hybrid_routing`, `web_trigger`, `hallucination_control`. If a preferred category is missing, fills from front of task list. Guarantees all routing modes are exercised in every smoke run.

---

### 12. graph.py — LangSmith Token Cost

**Problem:** Token cost was only logged to LangFuse (if configured). LangSmith showed no cost data per run.

**Fix:** Added `RunCollectorCallbackHandler` to capture root run_id post-`ainvoke`, then `Client().update_run()` with `total_cost_usd`, `total_tokens`, `total_input_tokens`, `total_output_tokens`. LangSmith now shows token cost in run metadata. Node latency is automatic via LangGraph integration.

---

### 13. ChatPage.tsx — Web Toggle Stale Closure

**Problem:** `sendMessage` (stable callback with `deps=[]`) captured stale `dispatchQuery` which had old `webSearch` value. Web toggle appeared to work in UI but the WS message always sent `web_search: false`.

**Fix:** Added `webSearchRef` that mirrors `webSearch` state:
```tsx
const webSearchRef = useRef<boolean>(false)
useEffect(() => { webSearchRef.current = webSearch }, [webSearch])
```
`dispatchQuery` reads `webSearchRef.current` instead of stale `webSearch`. Same pattern already used for `sessionIdRef`.

---

## Tavily Credit Status

- **Usage:** 174/1000 credits (~17%)
- **Full 30-question eval cost:** ~10-15 Tavily calls (3 web_trigger + 3 hybrid_routing × 1 call each)
- **No rate limiting observed** in any run. Previous hang was caused by n_sq parallel calls without timeout, not rate limiting.
- **Recommendation:** With 826 credits remaining, comfortably run 5-10 full evals.

---

## Routing Verification (6-question targeted test, 2026-05-02)

| Category | Mode Observed | M6 | Score |
|----------|--------------|-----|-------|
| hybrid_routing (×3) | `hybrid` | 1 | 0.60–0.70 |
| web_trigger (×3) | `web_only` | 1 | 0.60–0.90 |
| **Overall** | | **1.00** | **0.733** |

web_trigger was FAIL (0.00) in smoke before this session → now 2 × PASS (0.90) + 1 × PARTIAL (0.60).

---

## Ready for Full Eval

```bash
python evals/qa_eval/run_eval.py --full --input evals/qa_eval/question_v4.txt
```

Expected score improvement drivers vs 0.633 baseline:
- Q19 web_trigger routing fix: was FAIL → now PASS/PARTIAL (+~0.033 per question fixed)
- 3 web_trigger questions: all now correctly routed web_only
- 3 hybrid_routing questions: correctly routed hybrid with richer news chunks
- GT calibrations from session 3 still in place (~+0.10 from corrected ground truth)
