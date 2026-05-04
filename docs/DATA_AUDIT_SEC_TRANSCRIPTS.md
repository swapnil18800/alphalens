# Data Audit: SEC 10-K Filings & Earnings Transcripts

**Generated**: 2026-05-04 (post-ingestion, post-cleanup)  
**Source**: Live DB query + ingestion logs

---

## Summary

| Table | Chunks | Tickers | Years/Quarters |
|-------|--------|---------|----------------|
| `ten_k_chunks` | **32,009** | **33** | FY2023–FY2025 |
| `transcript_chunks` | **17,836** | **27** | Q1 2023 – Q4 2026 (varies) |

---

## SEC 10-K Coverage (`ten_k_chunks`)

33 tickers × 3 years each (~300–370 chunks/year/ticker).  
Chunks include: prose (business overview, MD&A, risk factors) + pipe-table chunks (segment revenue, margins, operating income).

### Full Coverage — Tech & Cloud (3 years each: 2023, 2024, 2025)

| Ticker | 2023 | 2024 | 2025 | Notes |
|--------|------|------|------|-------|
| AAPL | 242 | 240 | 241 | |
| ADBE | 329 | 329 | 328 | |
| AMAT | 343 | 320 | 321 | |
| AMD | 330 | 330 | 327 | |
| AMZN | 338 | 342 | 339 | |
| AVGO | 334 | 340 | 338 | |
| CRM | 331 | 327 | 335 | |
| CSCO | 370 | 370 | 370 | |
| GOOGL | 370 | 370 | 370 | |
| IBM | 198 | 208 | 212 | Smaller filing |
| INTC | 371 | 371 | 372 | |
| KLAC | 310 | 310 | 310 | |
| LRCX | 334 | 326 | 322 | |
| META | 327 | 323 | 319 | |
| MSFT | 340 | 342 | 335 | |
| MU | 320 | 319 | 322 | |
| NFLX | 258 | 290 | 316 | |
| NOW | 337 | 335 | 337 | |
| NVDA | 316 | 316 | 318 | |
| ORCL | 333 | 333 | 337 | |
| PANW | 346 | 338 | 345 | |
| PLTR | 316 | 312 | 314 | |
| PYPL | 371 | 371 | 371 | |
| QCOM | 315 | 314 | 314 | |
| SNOW | 326 | 336 | 344 | |
| TSLA | 351 | 338 | 334 | |
| TXN | 262 | 260 | 260 | |
| UBER | 369 | 356 | 348 | |

### Financial Sector (SEC only, no transcripts)

| Ticker | 2023 | 2024 | 2025 | Notes |
|--------|------|------|------|-------|
| BAC | 310 | 310 | 310 | Bank of America |
| GS | 310 | 310 | 310 | Goldman Sachs |
| JPM | 310 | 310 | 310 | JPMorgan Chase |
| V | 310 | 310 | 310 | Visa |

### Anomalies

| Ticker | 2023 | 2024 | 2025 | Issue |
|--------|------|------|------|-------|
| SMCI | 339 | — | 698 | **FY2024 missing**: SMCI delayed their FY2024 10-K filing due to accounting scandal (Hindenburg Research, 2024). When eventually filed on EDGAR, it was dated 2025. Both the FY2024 (late-filed) and FY2025 10-Ks share `filing_year=2025` in DB, giving ~2x chunks for that year. |

---

## Earnings Transcript Coverage (`transcript_chunks`)

27 tickers × 12–16 quarters each (~35–100 chunks/quarter).  
Source: StockAnalysis.com via `ingest_stockanalysis.py`. Chunks contain management commentary, CFO prepared remarks, analyst Q&A.

### Why Coverage Varies By Company

Different companies have different transcript counts because:
1. **Fiscal year calendar**: NVDA/CRM/SNOW fiscal years offset from calendar year → extra 2026 quarters available
2. **Data availability on StockAnalysis**: Some companies' oldest transcripts only go back to mid-2023
3. **Failed transcripts**: A few specific Q1-2026 transcripts had no body (earnings call not yet posted)

### Full Coverage Table (Q = quarters available)

| Ticker | 2023 | 2024 | 2025 | 2026 | Total Qs | Chunks |
|--------|------|------|------|------|----------|--------|
| AAPL | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1,Q2 | 14 | ~869 |
| ADBE | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~651 |
| AMAT | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~598 |
| AMD | Q1–Q4 | Q1–Q4 | Q1–Q4 | — | 12 | ~593 |
| AMZN | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~533 |
| AVGO | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~466 |
| CRM | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1–Q4 | 16 | ~865 |
| CSCO | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1,Q2 | 14 | ~632 |
| GOOGL | Q1–Q4 | Q1–Q4 | Q1–Q4 | — | 12 | ~537 |
| IBM | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~593 |
| INTC | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~679 |
| LRCX | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1–Q3 | 15 | ~755 |
| META | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~632 |
| MSFT | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1–Q3 | 15 | ~1,253 |
| MU | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1,Q2 | 14 | ~568 |
| NFLX | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1* | 12+1* | ~639 |
| NOW | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~672 |
| NVDA | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1–Q4 | 16 | ~689 |
| ORCL | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1–Q3 | 15 | ~490 |
| PANW | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1,Q2 | 14 | ~1,082 |
| PLTR | Q1–Q4 | Q1–Q4 | Q1–Q4 | — | 12 | ~620 |
| PYPL | Q1–Q4 | Q1–Q4 | Q1–Q4 | — | 12 | ~529 |
| QCOM | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1,Q2 | 14 | ~470 |
| SNOW | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1–Q4 | 16 | ~750 |
| TSLA | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1* | 12+1* | ~836 |
| TXN | Q1–Q4 | Q1–Q4 | Q1–Q4 | Q1 | 13 | ~391 |
| UBER | Q1–Q4 | Q1–Q4 | Q1–Q4 | — | 12 | ~427 |

> \* NFLX Q1-2026 and TSLA Q1-2026 have 1 chunk each (no transcript body available at time of ingestion — earnings call not yet posted)

### Known Gaps & Anomalies

| Company | Issue | Root Cause | Status |
|---------|-------|------------|--------|
| TSLA Q1-2026 | 1 chunk (header only) | Transcript body not available on StockAnalysis at ingestion time | Acceptable — no fix possible until published |
| NFLX Q1-2026 | 1 chunk (header only) | Same as TSLA | Acceptable |
| PYPL Q3-2024 | Was missing (timeout) | Network timeout during initial ingestion | **Fixed** — 49 chunks now present |
| PYPL Q4-2024 | Was 1 chunk (broken) | Network timeout during initial ingestion | **Fixed** — 44 chunks now present |
| KLAC | Removed | StockAnalysis only provides financial summary pages for KLAC, not full transcripts; KLAC not in DEFAULT_TICKERS | Removed from DB |
| SMCI | No transcripts | Not in transcript ingestion scope (DEFAULT_TICKERS list for transcripts excludes SMCI) | By design |

### Companies in SEC only (no transcripts)

BAC, GS, JPM, V — financial sector companies added to SEC for potential screener use. Transcripts not ingested (not in DEFAULT_TICKERS for transcript ingestion).

SMCI — in SEC but not in transcript DEFAULT_TICKERS.

---

## What the Data Contains

### SEC 10-K (`ten_k_chunks`)

**Section breakdown** (all tickers):
- `None` / unlabeled: majority (~80%) — core narrative prose (Business, MD&A, Risk Factors, Financials)
- `PART I`, `PART II`, `PART III`: labeled section headers + overviews
- `ITEM 1A.`, `ITEM 7A.`, `ITEM 8.`, `ITEM 9.` etc.: specific item sections
- Table chunks: pipe-delimited `|col|col|col|` format — revenue by segment, margins, operating income

**Typical facts retrievable:**
- Annual revenue by reporting segment (e.g., NVDA C&N vs Graphics; MSFT Productivity vs Intelligent Cloud vs MPC)
- Operating margin and net income (annual totals)
- Risk factor disclosures (competitive risks, supply chain, export controls, regulatory)
- Acquisition history (acquired companies, goodwill, deal values)
- Geographic revenue breakdown (Americas, Europe, Asia)
- R&D and CapEx investment levels
- Customer concentration disclosures

**Fiscal year → filing year mapping:**

| Ticker | FY End | Filing Year Label | Example |
|--------|--------|-------------------|---------|
| AAPL | Sep 30 | filing_year=2024 = FY ending Sep 2024 | AAPL filing_year=2024 → revenue for Oct 2023–Sep 2024 |
| NVDA | Jan 31 | filing_year=2025 = FY ending Jan 2025 | NVDA filing_year=2025 → FY2025 (calendar 2024) |
| MSFT | Jun 30 | filing_year=2025 = FY ending Jun 2025 | MSFT filing_year=2025 → FY2025 |
| AMZN | Dec 31 | filing_year=2024 = FY ending Dec 2024 | Standard calendar year |
| CRM | Jan 31 | filing_year=2025 = FY ending Jan 2025 | CRM FY2025 = calendar 2024 |
| GOOGL | Dec 31 | filing_year=2024 = FY ending Dec 2024 | Standard calendar year |

> **Important**: `filing_year` = year the 10-K was *filed*, NOT always the fiscal year ending. A 10-K filed in Feb 2025 covering FY ending Jan 2025 is labeled `filing_year=2025`.

---

### Earnings Transcripts (`transcript_chunks`)

**What's in a transcript chunk:**
- CEO/CFO prepared opening remarks (revenue guidance, strategic context)
- Segment-level quarterly revenue (more granular than 10-K annual totals)
- Analyst Q&A: competitive questions, margin guidance, product roadmap
- Product launch commentary (GPU ramps, new cloud tiers, subscriber milestones)
- Forward guidance statements (next-quarter revenue/margin outlook)

**Typical facts retrievable:**
- Quarterly revenue and margin by segment (e.g., NVDA DC Q3 FY2025 = $30.8B)
- Management's tone on competitive dynamics (defensive vs. aggressive)
- CapEx and R&D spending plans (e.g., Meta Zuckerberg CapEx commentary)
- Subscriber/user metrics (Netflix ads tier, paid sharing)
- Product ramp timelines (H200, Blackwell, new iPhone)
- Guidance for next quarter (revenue range, margin guidance)

**Quarter labeling**: `year=2025, quarter=1` means the transcript for the earnings call covering the quarter ending around Feb/Mar/Apr 2025 (depending on company fiscal year). Always cross-check with fiscal year offset.

---

## Example Chunks

### SEC Chunk — NVDA FY2025 Segment Table (`ten_k_chunks`)
```
| Segment | FY2025 Revenue | FY2024 Revenue |
|---|---|---|
| Compute & Networking | $113,627M | $47,479M |
| Graphics | $15,925M | $15,891M |
| Total | $129,552M | $63,370M |
```
*Filing year 2025 = fiscal year ending Jan 26, 2025*

### Transcript Chunk — NVDA Q3 FY2025 (`transcript_chunks`, year=2024, quarter=3)
```
Colette Kress (CFO): Data center revenue was $30.8 billion, up 17% sequentially 
and 112% year-over-year. H200 is our fastest product ramp in company history. 
CSPs represented approximately half of data center revenue. Inference drove 
more than 40% of data center revenue over the trailing four quarters.
```

### Transcript Chunk — META Q1 2026 (`transcript_chunks`, year=2026, quarter=1)
```
Mark Zuckerberg (CEO): We're seeing strong monetization from AI-powered ad 
delivery improvements. Infrastructure investment remains a priority — we 
believe that investing heavily in compute capacity now is a long-term 
strategic advantage over the next several years.
```

### Transcript Chunk — NFLX Q4 2024 (`transcript_chunks`, year=2024, quarter=4)
```
Greg Peters (COO): Q4 net adds were approximately 19 million, our largest 
quarter in several years. The ads plan represented over 55% of sign-ups 
in ads-available markets. Password sharing monetization continues to exceed 
our initial expectations.
```

---

## Questions Answerable by This Dataset

### High Confidence (>85% success rate)

| Question Type | Example | Primary Source |
|---------------|---------|----------------|
| Annual revenue by segment | "NVDA FY2025 segment breakdown?" | `ten_k_chunks` table |
| Refusal for private companies | "OpenAI 10-K revenue?" | Both (correctly refuse) |
| Quarterly KPIs from transcripts | "NVDA Q3 FY2025 data center rev?" | `transcript_chunks` |
| Risk factor disclosures | "NVDA export control risks?" | `ten_k_chunks` risk section |
| Web-trigger routing | "NVDA current stock price?" | Tavily web search |
| Hallucination control | "SpaceX FY2024 10-K revenue?" | Correctly refuses |

### Medium Confidence (55–75%)

| Question Type | Example | Limitation |
|---------------|---------|------------|
| Cross-company comparison | "NVDA vs AVGO AI revenue?" | Requires dual retrieval; RRF ranking dilutes one company |
| Multi-year trend | "AWS margin FY2022–FY2024?" | Requires stitching 3 filings; may miss years not in DB |
| FY-calendar year mapping | "MSFT FY2024 revenue?" | LLM must translate `filing_year=2024` (Jun 2024 FY) correctly |

### Low Confidence (<40%)

| Question Type | Example | Fix Needed |
|---------------|---------|------------|
| Ranking across all tickers | "Highest-margin semiconductor?" | Needs DuckDB screener aggregation |
| SMCI FY2024 specifics | "SMCI FY2024 operating income?" | FY2024 10-K not on EDGAR (delayed filing) |
| BAC/GS/JPM transcript Q&A | "What did JPM CEO say on rates?" | No transcripts ingested for financials |
| TSLA/NFLX Q1-2026 details | "Tesla Q1-2026 delivery guidance?" | Transcript body not available at ingestion time |

---

## Data Integrity Notes

1. **Deduplication**: PYPL transcripts had 177 duplicate rows (from re-ingestion over non-stockanalysis-sourced old rows). Cleaned via `MIN(id) GROUP BY ticker,year,quarter,chunk_index`.

2. **SMCI double-filing**: SMCI 2025 has ~698 chunks because EDGAR contains two separate filings tagged 2025: the delayed FY2024 10-K (filed ~Nov 2024) and the actual FY2025 10-K (filed ~Sep 2025). Both valid filings, both retrievable.

3. **KLAC transcript removal**: 5 header-only chunks were removed. KLAC earnings transcripts are not available on StockAnalysis in full-text form. KLAC 10-K data is present for all 3 years in `ten_k_chunks`.

4. **Fiscal year offsets are critical**: NVDA `filing_year=2025` covers the fiscal year ending January 26, 2025 (i.e., calendar 2024). The RESPONSE_PROMPT includes a citation year clarification rule to prevent the LLM from misattributing years.

---

*Audit prepared 2026-05-04. Run live DB queries to verify current counts.*
