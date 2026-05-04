# AlphaLens Demo Question Guide — Top 15

**Last updated:** 2026-05-02 (Sessions 4 & 5)  
**Based on:** question_v4.txt full eval, 30 questions, `.venv` Python

---

## Quick Reference: Top 15 Questions

| # | Category | Question | Reliability | Mode |
|---|----------|----------|-------------|------|
| 1 | hallucination | SpaceX private company | ★★★ | rag_only |
| 2 | hallucination | Stripe private company | ★★★ | rag_only |
| 3 | hallucination | OpenAI private company | ★★★ | rag_only |
| 4 | earnings | Netflix subscriber growth | ★★★ | rag_only |
| 5 | web_trigger | NVIDIA stock price | ★★★ | web_only |
| 6 | web_trigger | Semiconductor M&A 2025-26 | ★★★ | web_only |
| 7 | context_aggregation | AWS revenue trace FY22-24 | ★★★ | rag_only |
| 8 | hybrid | Microsoft Azure + Copilot | ★★★ | hybrid |
| 9 | deep_retrieval | Broadcom FY2024 segments | ★★★ | rag_only |
| 10 | deep_retrieval | Microsoft 3 segments | ★★ | rag_only |
| 11 | context_aggregation | Microsoft FY23-24 themes | ★★ | rag_only |
| 12 | earnings | Meta AI infrastructure | ★★ | rag_only |
| 13 | web_trigger | AI regulatory 2026 | ★★ | web_only |
| 14 | cross_company | AMD vs Intel data center | ★★ | rag_only |
| 15 | edge_cases | Broad query (impossible) | ★★★ | rag_only |

★★★ = Consistent PASS/near-PASS across eval runs  
★★ = Reliable PARTIAL — strong answer, some gaps acceptable in demo context

---

## Tier 1 — Reliable PASS (always use in demos)

### 1. SpaceX — Hallucination Guard
> **"What does SpaceX's FY2024 10-K report as its total revenue and operating margin?"**

Demonstrates: The system refuses to fabricate data for private companies. Politely explains SpaceX doesn't file with the SEC.  
Score: 1.00 (3/3 across all runs)  
Mode: `rag_only`

---

### 2. Stripe — Hallucination Guard
> **"What specific revenue figures and profit margins did Stripe report in its FY2024 annual report?"**

Same pattern for Stripe. Shows the system knows the limits of its database.  
Score: 1.00  
Mode: `rag_only`

---

### 3. OpenAI — Hallucination Guard
> **"What did OpenAI report as its total revenue and net income in its FY2024 annual filing?"**

Same pattern for OpenAI. Three consecutive private-company refusals in a demo are impressive.  
Score: 1.00  
Mode: `rag_only`

---

### 4. Netflix — Earnings Transcript Retrieval
> **"What did Netflix management say about subscriber growth and content strategy in FY2024 earnings calls?"**

Demonstrates: Dual-source retrieval (10-K + earnings transcripts). System synthesizes subscriber milestone (~300M), paid sharing crackdown, ad-tier growth, live events strategy.  
Score: 1.00  
Mode: `rag_only`

---

### 5. NVIDIA Stock Price — Web-Only Routing
> **"What is NVIDIA's current stock price and how did it perform in its most recent quarterly earnings report?"**  
**⚠️ Requires: web search toggle ON + `TAVILY_API_KEY` set**

Demonstrates: Correct `web_only` routing for real-time data (not SEC filings). System retrieves Q4 FY2026 results ($68.1B revenue, $1.62 EPS), cites news sources.  
Score: 0.90  
Mode: `web_only` (auto-routed)

---

### 6. Semiconductor M&A — Web Search
> **"What recent mergers, acquisitions, or major partnerships have been announced in the semiconductor industry in 2025-2026?"**  
**⚠️ Requires: web search toggle ON**

Demonstrates: Web-only mode for current events, structured M&A summary with deal names and approximate values.  
Score: 0.90  
Mode: `web_only`

---

### 7. AWS Revenue Trace — Multi-Year Aggregation
> **"Trace Amazon Web Services revenue growth and operating margin from FY2022 to FY2024 based on annual reports."**

Demonstrates: Cross-year synthesis from multiple filings. Expected: FY2022 $80.1B → FY2023 $90.8B → FY2024 $107.6B; operating margins recovering to 37%.  
Score: 1.00  
Mode: `rag_only`

---

### 8. Microsoft Azure + Copilot — Hybrid Routing
> **"What does Microsoft's most recent 10-K say about Azure growth and cloud strategy, and what recent 2026 Copilot or AI product announcements have been made?"**  
**⚠️ Requires: web search toggle ON for best results**

Demonstrates: Hybrid routing — cites both [SEC-MSFT] chunks and [NEWS] sources. Azure ~34% growth from 10-K, Copilot news from web.  
Score: 0.90  
Mode: `hybrid`

---

### 9. Broadcom VMware Segments — Deep Retrieval
> **"What were Broadcom's FY2024 revenue segments after completing the VMware acquisition?"**

Demonstrates: Accurate segment data retrieval, M&A context. Semiconductor Solutions 58% + Infrastructure Software 42%; total $51.6B; VMware explained.  
Score: 0.70 (consistent PARTIAL — clean, structured answer)  
Mode: `rag_only`

---

## Tier 2 — Reliable PARTIAL (good demo, expected depth)

### 10. Microsoft Three Segments — Deep Retrieval
> **"Break down Microsoft's revenue by its three reportable segments (most recent 10-K available) and describe each segment."**

Demonstrates: Segment-level financial retrieval. Productivity & Business Processes / Intelligent Cloud / More Personal Computing with revenue and descriptions.  
Score: 0.70  
Mode: `rag_only`  
Note: May give FY2024 or FY2025 figures depending on DB; both are acceptable.

---

### 11. Microsoft Strategic Themes — Cross-Year Synthesis
> **"What strategic themes are consistent across Microsoft's FY2023 and FY2024 annual reports regarding cloud and AI?"**

Demonstrates: Longitudinal narrative synthesis. Azure growth, Copilot branding, OpenAI partnership, responsible AI governance appear across both filings.  
Score: 0.70  
Mode: `rag_only`

---

### 12. Meta AI Infrastructure — Earnings Grounding
> **"What did Meta's management discuss about AI infrastructure investment and spending plans in FY2024 earnings calls?"**

Demonstrates: Honest handling of partial transcript coverage. System either retrieves transcript content (Llama, ad AI, Reality Labs) or states "FY2024 transcript data limited in retrieved documents" and falls back to 10-K context.  
Score: 0.60 (judge accepts partial with 10-K fallback)  
Mode: `rag_only`

---

### 13. AI Regulatory Developments — Web Only
> **"What are the latest AI regulatory developments in the US and EU that could affect major technology companies in 2026?"**  
**⚠️ Requires: web search toggle ON**

Demonstrates: Live web research capability. EU AI Act milestones, US executive orders, impact on NVDA/MSFT/META/GOOGL.  
Score: 0.60 (PARTIAL — current event detail varies by retrieval date)  
Mode: `web_only`

---

### 14. AMD vs Intel — Cross-Company Comparison
> **"Compare AMD and Intel's FY2024 data center segment revenue, growth rates, and strategic positioning in AI."**

Demonstrates: Multi-ticker retrieval and competitive comparison. AMD DC ~$12.6B (+122%), Intel DCAI ~$12.8B (declining), MI300X vs Gaudi narrative.  
Score: 0.60  
Mode: `rag_only`  
Note: Latency ~24s for multi-ticker retrieval.

---

### 15. Broad Query — Graceful Handling
> **"Tell me everything about every technology company that has ever existed, their complete financial history, all their products, strategies, and future plans."**

Demonstrates: Graceful handling of impossible scope. System acknowledges it's too broad, offers to narrow, lists available companies in DB (~27). Does not crash or hallucinate.  
Score: 1.00  
Mode: `rag_only`

---

## Questions to AVOID in Demos

These questions have consistent failures across eval runs. Do not use them.

| Question | Why It Fails |
|----------|-------------|
| Alphabet/Google FY2024 three segments | LLM reports operating income (~$121B) instead of revenue (~$326B) — structurally wrong metric |
| Amazon FY2024 total revenues + drivers | Same revenue vs operating income confusion |
| NVIDIA competitive advantages and moats | Retrieval failure — "moats" is investor jargon, not 10-K language; zero chunks retrieved |
| Cisco vs Palo Alto Networks security revenue | Consistent judge fail — mixed-up security revenue figures for one company |
| "nvda fy25 rev???" (informal terse query) | Sometimes routes as out-of-scope; use full-sentence version instead |
| NVIDIA business segments FY2025 | LLM hallucination on segment figures (M2 faithfulness low) |

---

## Question Framing Rules

### DO
- **Anchor to a specific filing year:** "According to [company]'s FY2024 10-K..."
- **Name the metric explicitly:** "...their revenue (not operating income)..." if you need precision
- **Scope to one company or two named companies** for comparison
- **State trajectory explicitly:** "How has X evolved from FY2022 to FY2024..."
- **Mark web questions:** Tell the user to enable web search for real-time topics

### DON'T
- ❌ Use informal abbreviations in queries ("nvda fy25 rev???") — the analysis model can misclassify these
- ❌ Ask about "performance" without specifying whether you mean revenue or operating income
- ❌ Ask for "the latest" without enabling web search
- ❌ Ask to compare more than 2 companies in one question (multi-ticker retrieval degrades)
- ❌ Ask questions whose answer requires sub-segment granularity (e.g., App Store commissions only) — 10-Ks don't report at that level

---

## Specificity Sweet Spot

```
TOO VAGUE                    SWEET SPOT                    TOO SPECIFIC
──────────────────────────────────────────────────────────────────────────
"Tell me about NVIDIA"  →   "What was NVIDIA's FY2025     "What was NVIDIA's H100
                             Data Center revenue and        revenue per unit in Q3
                             growth rate?"                  FY2025 excluding China?"
```

10-K filings disclose at the **segment** level (annual), not the SKU/region/quarter level. Stay in the segment and annual range.

---

## Known Ambiguities and Pitfalls

### Revenue ≠ Operating Income
The DB contains both metrics in table chunks. Without explicit disambiguation, the LLM may report either one. For revenue questions, always say "revenue" or "net sales" in the question — never just "performance."

### Fiscal Year Calendar Mismatch
| Company | FY End | FY2024 = Calendar |
|---------|--------|------------------|
| NVIDIA | January | Feb 2023 – Jan 2024 |
| Apple | September | Oct 2023 – Sep 2024 |
| Microsoft | June | Jul 2023 – Jun 2024 |
| Amazon, Meta, Alphabet | December | Jan – Dec 2024 |

Anchor with explicit fiscal year to avoid year confusion. "NVIDIA's most recent filing" may refer to FY2026 (ended Jan 2026) while you might mean the calendar year 2024 results.

### "Most Recent" Is Database-Dependent
The pipeline returns data from the most recent filing in the DB — which may or may not match the real-world most recent. If both FY2024 and FY2025 are ingested, you'll get FY2025. If only FY2024, you'll get FY2024. Anchor with an explicit year for reproducible demo answers.

### Web Search Requires Full Stack
For web_trigger and hybrid questions to work:
1. Web search toggle **ON** in UI
2. `TAVILY_API_KEY` in `.env`
3. Server running from `.venv` (not system Python)

Without all three, the system answers from 10-K data only (potentially saying "no web data available").

### Transcript Coverage is Sparse
Earnings transcript data = ~5 chunks per company. For transcript-dependent questions, reliable companies are: **Netflix**, **Meta**, **Amazon**. Avoid transcript questions for: NVIDIA, Salesforce, Tesla, Cisco (sparse or absent).
