# AlphaLens Eval Workflow Guide — Complete Commands

## Phase 1: Data Ingestion (Run First — Required)

### 1.1 SEC 10-K Ingestion
**Purpose**: Populate `ten_k_chunks` table with SEC filing data (financial statements, risk factors, segments)

**Logs saved to**: `scripts/ingestion/logs/sec_YYYYMMDD_HHMMSS.log`

```bash
# From project root
python scripts/ingestion/ingest_sec.py --all --years 3 --replace
```

**What it does:**
- Downloads 3 years of 10-K filings (FY2023, FY2024, FY2025, FY2026) for all 27 tickers + ADBE
- Chunks documents into 1400-char segments with 200-char overlap
- Detects sections (Item 1A Risk Factors, Item 7 MD&A, etc.) via regex
- Generates embeddings (384-dim, all-MiniLM-L6-v2) and stores in PostgreSQL `ten_k_chunks` table
- `--replace` deletes old chunks for each ticker before re-ingesting
- **Time**: ~2-3 hours for all 28 tickers (each ticker: ~3-5 min)

### 1.2 yfinance Earnings Transcripts Ingestion
**Purpose**: Populate `transcript_chunks` table with quarterly earnings call summaries

**Logs saved to**: `scripts/ingestion/logs/transcript_YYYYMMDD_HHMMSS.log`

```bash
# From project root
python scripts/ingestion/ingest_yfinance.py --lookback-quarters 12
```

**What it does:**
- Fetches last 12 quarters (~3 years) of earnings summaries for all 28 tickers
- Each quarter = 1 chunk with revenue, margins, key metrics, earnings date
- Generates embeddings (same model) and stores in `transcript_chunks` table
- Skips quarters already in DB (idempotent)
- **Note**: To filter 2023-2025 only, manually delete 2026 Q1 rows post-ingestion or modify script to filter by date
- **Time**: ~20-30 min (most tickers already cached)

**Database check after ingestion:**
```sql
-- Verify data was ingested
SELECT COUNT(*) as ten_k_count FROM ten_k_chunks;  -- Should be ~35K+
SELECT COUNT(*) as transcript_count FROM transcript_chunks;  -- Should be ~150-200
SELECT DISTINCT ticker FROM ten_k_chunks ORDER BY ticker;  -- List all 28 tickers
```

---

## Phase 2: Ground Truth Generation (Run After Ingestion Complete)

**CRITICAL**: Must run AFTER Phase 1 completes. Ground truth queries the DB for chunks.

**Logs saved to**: `evals/qa_eval/logs/gt_generation_YYYYMMDD_HHMMSS.log`

### 2.1 Create Questions File
Create `question_vN.txt` (JSON) with structure:
```json
{
  "category_name": {
    "web_search": true/false,
    "expected_behavior": "...",
    "questions": ["Q1...", "Q2..."],
    "ground_truth_map": {}  // Empty initially
  }
}
```

### 2.2 Run Ground Truth Generation
```bash
# From project root
python evals/qa_eval/generate_ground_truth.py --input question_v2.txt --full

# Or from evals/qa_eval directory
cd evals/qa_eval
python generate_ground_truth.py --input question_v2.txt --full
```

**What it does (Ground Truth Creation Process):**

1. **Question Analysis** (No LLM):
   - Extracts tickers from question text using `TICKER_MAP` (hardcoded dictionary in script)
   - Maps "qualcomm" → "QCOM", "lam research" → "LRCX", etc.
   - If ticker not found, returns empty key_facts

2. **Chunk Retrieval** (DB Query, No LLM):
   - For detected tickers, queries `ten_k_chunks` + `transcript_chunks` via pgvector
   - Uses semantic search (embedding similarity) + BM25 hybrid retrieval
   - Retrieves top-K chunks (default ~3-5) relevant to question meaning
   - **No web search** — uses only internal DB

3. **Ground Truth Synthesis** (Uses GPT-4o LLM):
   - Passes question + retrieved chunks to GPT-4o
   - Prompt: "Synthesize a reference answer and 5 key verifiable facts from these chunks"
   - **My inference (Claude)**: NOT used. Pure GPT-4o inference
   - Returns: `ground_truth` (1-2 sentence summary) + `key_facts` (list of extractable claims)

4. **Special Cases**:
   - `hallucination_control` category → Auto-sets `ground_truth="NOT_IN_DATABASE"`, `key_facts=[]`
   - `edge_cases` category → Auto-sets `ground_truth="BROAD_QUERY_HANDLED"`, `key_facts=["EDGE_CASE"]`
   - `web_trigger` category → Auto-sets `ground_truth="WEB_SEARCH_TRIGGERED"`, `key_facts=[]`

5. **Output**:
   - Populates `ground_truth_map` in-place in `question_vN.txt`
   - No web search used (only DB chunks)
   - **File grows** from 5KB → 20-30KB after GT generation

**Options:**
- `--full`: Process all questions
- `--smoke`: Process first 3 questions only
- `--category CAT1 CAT2`: Process specific categories
- `--force`: Regenerate GT even if already present

**TICKER_MAP to update** (in `generate_ground_truth.py`):
```python
TICKER_MAP = {
    "nvidia": "NVDA", "amd": "AMD", "intel": "INTC",
    "qualcomm": "QCOM", "lam research": "LRCX", "applied materials": "AMAT",
    "salesforce": "CRM", "servicenow": "NOW", "palo alto": "PANW",
    "adobe": "ADBE", "broadcom": "AVGO", "micron": "MU",
    "texas instruments": "TXN", "uber": "UBER",
    # ... add missing tickers here
}
```

---

## Phase 3: Evaluation (Run After Ground Truth Complete)

### 3.1 Smoke Test (First 3 Questions)
**Purpose**: Sanity check before full eval (detects crashes, embedding issues)

**Logs saved to**: `evals/qa_eval/logs/smoke_eval_YYYYMMDD_HHMMSS.log`

```bash
# From project root
python evals/qa_eval/run_eval.py --smoke --input question_v2.txt

# Or from evals/qa_eval directory
cd evals/qa_eval
python run_eval.py --smoke --input question_v2.txt
```

**Expected output**: 3 result JSONs in `results/<timestamp>/`, each with M1-M7 scores
**Time**: ~5-10 min (depends on LLM latency)

### 3.2 Full Eval (All 20 Questions)
**Purpose**: Compute baseline score across all categories

**Logs saved to**: `evals/qa_eval/logs/eval_YYYYMMDD_HHMMSS.log`

```bash
# From project root
python evals/qa_eval/run_eval.py --full --input question_v2.txt

# Or from evals/qa_eval directory
cd evals/qa_eval
python run_eval.py --full --input question_v2.txt
```

**Output**:
- `results/<timestamp>/01_category_question.json` through `20_...`
- `results/<timestamp>/_summary.json` (aggregated scores)
- `results/<timestamp>/_analysis.md` (category breakdown, top/bottom questions)
- **Time**: ~20-30 min for 20 questions

**Log file naming**:
- When `--smoke` flag is used: filename starts with `smoke_eval_`
- When `--full` or `--category` flags are used: filename starts with `eval_`
- Both include timestamp: `eval_20260501_143000.log`

**Metrics Generated** (M1-M7):
- **M1 (Factual correctness)**: % of key_facts found in answer (no LLM, fuzzy match)
- **M2 (Faithfulness)**: RAGAS — answer claims grounded in retrieved context (GPT-4o)
- **M3 (Retrieval recall)**: % of key_facts found in top-K chunks (no LLM)
- **M4 (Context precision)**: RAGAS — retrieved chunks are relevant (GPT-4o)
- **M6 (Routing accuracy)**: web_search flag alignment with query_mode
- **M7 (Judge score)**: LLM judge verdict (pass/partial/fail), always uses gpt-4o

**Average = mean(M1, M2, M3, M4, M6, M7)**

---

## Phase 4: Iteration (If Needed)

**Threshold to iterate**: If `average < 0.72` (below v2 demo-ready score)

**Logs saved to**: `evals/qa_eval/logs/eval_YYYYMMDD_HHMMSS.log`

```bash
# After fixes (prompt rules, GT updates), run again with --set-baseline:
cd evals/qa_eval
python run_eval.py --full --input question_v2.txt --set-baseline
```

**`--set-baseline` flag**: Writes results to `evals/baseline.json` for tracking

**Max iterations**: 1 per eval cycle (avoid overfitting to specific questions)

---

## Summary of Data Flow

```
[Ingestion Phase]
  SEC API → ingest_sec.py → chunks + embeddings → ten_k_chunks table
  yfinance API → ingest_yfinance.py → transcript chunks + embeddings → transcript_chunks table

[Ground Truth Phase]
  Question text → extract_tickers() → TICKER_MAP
    ↓
  pgvector search (DB chunks only, NO web search)
    ↓
  Retrieved chunks → GPT-4o synthesis → ground_truth + key_facts
    ↓
  question_vN.txt updated with ground_truth_map

[Eval Phase]
  question_vN.txt → run_eval.py
    ↓
  ResearchState → LangGraph pipeline:
    analyze_question → execute_search → generate_response → evaluate_response
    ↓
  M1-M7 metrics → _summary.json + _analysis.md
```

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| "Column 'year' does not exist" | Query references 'year' instead of 'filing_year' | Already fixed in DB schema |
| Ground truth "No tickers found" | Ticker not in TICKER_MAP | Add ticker: `"lrcx": "LRCX"` in generate_ground_truth.py |
| Eval crashes with "question file not found" | `--input` path is relative | Use absolute path or cd to `evals/qa_eval/` first |
| M2 score always 0 | RAGAS embedding model incompatible | Already fixed: excluded answer_relevancy, use faithfulness + context_precision only |
| LLM judge returns "fail" despite M1=1.0 | gpt-4o-mini is unreliable as judge | Use `OPENAI_MODEL=gpt-4o` (already set in commands above) |
| Cerebras daily quota exceeded | Sequential 20-question eval exhausts limit | Always use `OPENAI_MODEL=gpt-4o` env var |

---

## Full Command Checklist for Next Iteration

**Logs automatically saved to**:
- **Ingestion**: `scripts/ingestion/logs/`
- **Ground Truth**: `evals/qa_eval/logs/`
- **Evaluation**: `evals/qa_eval/logs/` (smoke → `smoke_eval_*.log`, full/category → `eval_*.log`)

```bash
# Day 1: Ingestion (2-3 hours)
cd C:\Users\HP\Desktop\ai-projects\alphalens
python scripts/ingestion/ingest_sec.py --all --years 3 --replace
python scripts/ingestion/ingest_yfinance.py --lookback-quarters 12

# Day 2: Ground Truth + Eval (2-3 hours)
cd C:\Users\HP\Desktop\ai-projects\alphalens\evals\qa_eval
python generate_ground_truth.py --input question_v2.txt --full
python run_eval.py --smoke --input question_v2.txt      # → smoke_eval_*.log
python run_eval.py --full --input question_v2.txt       # → eval_*.log

# (Optional) Iteration if baseline < 0.72
# [Apply fixes to agent/rag/prompts.py or evals/qa_eval/question_v2.txt]
python run_eval.py --full --input question_v2.txt --set-baseline  # → eval_*.log
```

Then I'll create:
1. `IMPROVEMENT_SUMMARY_V[N]_BASELINE.md` — score vs v2, category breakdown, key findings
2. `DEMO_QUESTIONS_V[N].md` (if score ≥ 0.70) — top 5 questions with reasoning traces

---

## Files Modified for Future Runs

When adding new tickers or categories, update:
1. `scripts/ingestion/ingest_sec.py` → TOP_25 list (if adding new companies)
2. `evals/qa_eval/generate_ground_truth.py` → TICKER_MAP (add phrase → ticker mappings)
3. `evals/qa_eval/run_eval.py` → Already supports `--input` flag (no changes needed)
4. `agent/rag/prompts.py` → Add prompt rules if new failure patterns emerge (not needed for GT)

---

## Key Takeaways

✅ **Ground Truth Creation**:
- My inference (Claude): NOT used
- GPT-4o inference: USED (synthesizes GT from chunks)
- Web search: NOT used (DB chunks only)
- Timing: Run ONLY after ingestion completes

✅ **Eval Execution**:
- Smoke test sanity-checks in 5 min
- Full eval produces M1-M7 scores in 20-30 min
- Judge always uses gpt-4o (set via env var)
- Iterate only if baseline < 0.72

✅ **Data Flow**:
1. Ingest → DB (SEC, yfinance)
2. Generate GT → queries DB, uses GPT-4o, populates question file
3. Run eval → LangGraph pipeline, produces scores
4. Document → summary + demo questions (my inference, no API calls)
