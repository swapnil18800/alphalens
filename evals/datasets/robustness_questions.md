# AlphaLens Robustness Test Questions

A curated set of questions to evaluate chatbot quality across multiple dimensions.
Run these manually against the live app and log the results.

---

## 1. Single-Company Deep Dives (10-K Grounding)

| # | Question | Expected behavior |
|---|----------|-------------------|
| 1 | What were NVIDIA's primary revenue segments in FY2026 and how much did each contribute? | Detailed breakdown with numbers, 10-K citation |
| 2 | What risk factors did Apple list in their most recent 10-K related to supply chain? | Multiple risk factors with section citation |
| 3 | How did Microsoft describe its cloud revenue growth in FY2025? | Specific figures and forward-looking statements |
| 4 | What is Tesla's stated strategy for expanding manufacturing capacity in their 10-K? | Strategic discussion with citations |
| 5 | What does Snowflake's FY2026 10-K say about competition in the data cloud market? | Competitive landscape section |

---

## 2. Earnings Transcript Analysis

| # | Question | Expected behavior |
|---|----------|-------------------|
| 6 | What did IBM's management say about AI consulting demand in their earnings call? | Transcript citation, executive quotes |
| 7 | How did Netflix's CFO describe subscriber growth trends in their latest earnings? | Specific transcript passages |
| 8 | What guidance did Cisco's management give for FY2026 revenue in their earnings call? | Forward guidance with numbers |
| 9 | What did Meta's CEO say about capital expenditure plans for AI infrastructure? | Capex discussion with citations |
| 10 | Did AMD mention any specific partnership or customer wins in their recent earnings call? | Named partnerships/customers from transcript |

---

## 3. Cross-Document Multi-Company Comparisons

| # | Question | Expected behavior |
|---|----------|-------------------|
| 11 | Compare NVIDIA and AMD's revenue growth rates from FY2024 to FY2026 | Table with both companies' numbers |
| 12 | How do Snowflake and Databricks differ in their approach to data platform monetization? | Side-by-side comparison from 10-Ks |
| 13 | Compare Apple and Microsoft's R&D spending as a percentage of revenue over the last two years | Numeric comparison with citations from both |
| 14 | What are the key differences in risk factors between Meta and Alphabet in their most recent 10-Ks? | Cross-document synthesis |
| 15 | Which company between Netflix and Disney had higher content spending in FY2025? | Comparison with dollar figures |

---

## 4. Trend Analysis (Cross-Year)

| # | Question | Expected behavior |
|---|----------|-------------------|
| 16 | How has NVIDIA's gross margin changed from FY2023 to FY2026? | Year-over-year table |
| 17 | Track Tesla's operating income from FY2022 to FY2025 | Multi-year trend with data |
| 18 | How did Meta's advertising revenue growth rate change between FY2024 and FY2025? | YoY comparison with percentages |
| 19 | Show Amazon's AWS segment revenue growth across the last three fiscal years | AWS-specific data trend |
| 20 | How did Salesforce's subscription revenue as a share of total revenue evolve from FY2024 to FY2026? | Trend analysis |

---

## 5. Specific Financial Metrics

| # | Question | Expected behavior |
|---|----------|-------------------|
| 21 | What was Google's operating cash flow in FY2025? | Specific dollar figure from 10-K |
| 22 | How much free cash flow did Apple generate in FY2025? | FCF figure with citation |
| 23 | What were Cisco's total deferred revenue figures at the end of FY2025? | Balance sheet metric |
| 24 | What is the total goodwill on Microsoft's balance sheet as of their latest 10-K? | Specific accounting figure |
| 25 | What was IBM's debt-to-equity ratio mentioned in their FY2025 10-K? | Financial ratio |

---

## 6. Out-of-Scope / Rejection Tests

| # | Question | Expected behavior |
|---|----------|-------------------|
| 26 | What is the current stock price of NVDA? | Politely declines — not real-time data |
| 27 | Should I buy Tesla stock right now? | Declines investment advice, disclaims |
| 28 | Who won the 2024 US presidential election? | Out of scope, declines gracefully |
| 29 | Write me a Python script to scrape SEC filings | Out of scope, redirects to relevant capability |
| 30 | What is Warren Buffett's net worth today? | Declines real-time personal finance data |

---

## 7. Limited Capability / Honest Uncertainty

| # | Question | Expected behavior |
|---|----------|-------------------|
| 31 | What are Stripe's revenue figures for FY2025? | Explains Stripe is private, not in DB |
| 32 | Compare SpaceX's margins against Boeing | SpaceX is private — explains data gap |
| 33 | What did NVIDIA say in their most recent quarterly earnings (Q3 FY2027)? | Honest about data cutoff |
| 34 | What is the sentiment score for NVDA among institutional investors this week? | Not in scope — no sentiment data |
| 35 | What did the Fed say about interest rates last week? | Out of scope unless web search enabled |

---

## 8. RAG-Only Queries (database grounding only, no web search)

Queries that should be satisfied by documented companies in the database.
Expected behavior: Pure retrieval from 10-K and earnings transcripts.

| # | Question | Ticker | Expected behavior |
|---|----------|--------|-------------------|
| 36 | What were NVIDIA's primary revenue segments in FY2026? | NVDA | 10-K citation with detailed breakdown |
| 37 | How did Apple describe supply chain risks in their latest 10-K? | AAPL | Risk factors section with quotes |
| 38 | What cloud growth did Microsoft report in FY2025? | MSFT | Cloud revenue figures from 10-K |
| 39 | What did Alphabet management say about AI investments in earnings? | GOOGL | Earnings transcript quotes |
| 40 | How much did Amazon invest in AWS infrastructure per the latest 10-K? | AMZN | Capital expenditure details |

## 9. Web-Only Queries (out-of-database companies or real-time data)

Queries that should trigger web search fallback (no 10-K/transcript match).
Expected behavior: Tavily news results, graceful handling of missing data.

| # | Question | Company | Expected behavior |
|---|----------|---------|-------------------|
| 41 | What is Stripe's latest funding or valuation news? | Stripe (private) | Web search triggered, news results |
| 42 | What did analysts say about SpaceX's latest achievements? | SpaceX (private) | News search only, acknowledges data gap |
| 43 | What are recent analyst predictions for Tesla's stock price? | TSLA (public, no transcript data) | News results for recent commentary |
| 44 | What are the latest developments in the AI chip competition? | General | News search for recent trends |
| 45 | What did Bloomberg report about cloud infrastructure investment? | General | News search results |

## 10. Hybrid Queries (both RAG and web search)

Queries mixing in-scope and out-of-scope elements.
Expected behavior: RAG results + web search augmentation for recent/external perspective.

| # | Question | In-DB | Out-of-scope | Expected behavior |
|---|----------|-------|-----------------|-------------------|
| 46 | Compare NVIDIA's disclosed capex with recent analyst expectations | NVDA | Recent analyst reports | 10-K data + news synthesis |
| 47 | What are Apple's announced AI initiatives beyond their latest 10-K? | AAPL | Recent announcements | 10-K grounding + web news |
| 48 | How does Microsoft's cloud strategy from their latest 10-K align with recent market trends? | MSFT | Current market analysis | 10-K context + web search |
| 49 | What private companies are competing with AWS based on recent news? | AMZN (AWS from 10-K) | Private competitors | AWS data + news on competitors |
| 50 | Which of the documented companies had the most recent acquisition and what did they acquire? | Multi-company | Recent M&A news | 10-K base + web for latest deals |

## 11. Web Search Capability (with include_news=true)

Queries explicitly requesting recent/live information.
Expected behavior: Tavily news results cited alongside RAG where relevant.

| # | Question | Expected behavior |
|---|----------|-------------------|
| 51 | What did analysts say about NVDA earnings last month? | News results + 10-K context if relevant |
| 52 | Are there any recent news articles about Apple's AI strategy? | Fetches Tavily results with URLs |
| 53 | What are the latest analyst price targets for Microsoft? | Web search for recent analyst coverage |
| 54 | Has there been any recent news about Snowflake's acquisition plans? | Live news results with citations |
| 55 | What is the current analyst consensus rating for Meta stock? | Web search for consensus data |

---

## 9. Complex Multi-Part Questions

| # | Question | Expected behavior |
|---|----------|-------------------|
| 41 | Compare NVIDIA, AMD, and Intel's data center revenue, gross margins, and capex guidance — use a table | 3-company table with multiple metrics |
| 42 | For NVDA, what are (a) the top 3 risk factors, (b) the revenue breakdown, and (c) the management's key priorities? | Structured multi-part answer |
| 43 | Which of the 27 companies in your database had the highest revenue growth rate in their most recent fiscal year? | Cross-corpus ranking |
| 44 | Summarize the AI-related disclosures from both the 10-K and earnings call for IBM | Cross-document synthesis for one company |
| 45 | What are the common themes in risk disclosures across big tech companies (Apple, Google, Meta, Microsoft)? | Thematic synthesis across 4 companies |

---

## 10. Edge Cases and Stress Tests

| # | Question | Expected behavior |
|---|----------|-------------------|
| 46 | Tell me everything you know about NVDA | Summarizes available data without hallucinating |
| 47 | aslkdjf lksdjf lksdjflsdf | Gracefully handles nonsense input |
| 48 | What is 2 + 2? | Responds helpfully but redirects to financial capability |
| 49 | Repeat the last answer verbatim | Handles conversation context correctly |
| 50 | What companies do you have data for? | Lists all 27 companies accurately |
