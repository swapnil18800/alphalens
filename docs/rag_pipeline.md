# RAG Pipeline

## Overview

The retrieval pipeline runs inside `node_execute_search` (agent/graph/nodes.py) and delegates to `agent/rag/search_engine.py`.

## Pipeline Stages

```
User question
     │
     ▼
1. Embed query (all-MiniLM-L6-v2, 384-dim, CPU via SentenceTransformer)
     │
     ▼
2. Semantic cache check (cosine >= 0.92 against semantic_cache table)
     │  HIT → return cached response, skip pipeline
     ▼
3. Parallel retrieval:
     ├── pgvector cosine search (ten_k_chunks + transcript_chunks)
     └── BM25 keyword search (in-memory rank_bm25 index)
     │
     ▼
4. Reciprocal Rank Fusion (RRF, k=60) — merges vector + BM25 rank lists
     │
     ▼
5. Cross-encoder rerank (ms-marco-TinyBERT-L-2-v2) — top-20 → top-k
     │
     ▼
6. Optional: Tavily news search (if include_news=true AND TAVILY_API_KEY set)
     │
     ▼
Results returned as {sec: [...], transcripts: [...], news: [...]}
```

## Multi-query fan-out

When `node_analyze_question` decomposes into multiple sub-questions:
- Each sub-question runs the full search pipeline in parallel (`asyncio.gather`)
- Results are merged and deduplicated by chunk ID (first occurrence = highest rank)
- Dynamic chunk budget: `chunks_per_source = min(16, max(8, 4 * n_sub_questions))`

## Multi-ticker handling

When multiple tickers are extracted (e.g., "Compare NVDA vs AMD"):
- pgvector runs per-ticker in parallel, results merged
- BM25 filters per-ticker, results merged
- RRF and rerank operate on the combined pool

## Key constants (search_engine.py)

| Constant | Value | Purpose |
|----------|-------|---------|
| `EMBEDDING_MODEL` | all-MiniLM-L6-v2 | 384-dim embeddings |
| `RERANK_MODEL` | cross-encoder/ms-marco-TinyBERT-L-2-v2 | Reranking |
| `RRF_K` | 60 | RRF fusion constant |
| `CACHE_THRESHOLD` | 0.92 | Cosine similarity for cache hit |

## BM25 index lifecycle

- Built once at startup in `lifespan.py` → `build_bm25_corpus()`
- Loads all rows from `ten_k_chunks` and `transcript_chunks` into memory
- Tokenized with `.lower().split()` (simple whitespace tokenization)
- Not refreshed unless app restarts

## Evaluation & retry

After generation, `node_evaluate_response` scores the answer:
1. **Heuristic eval** (fast, no LLM call): checks length, citations, numbers, refusal phrases
2. **LLM-as-judge** (only for borderline 0.50-0.75 scores on first iteration)
3. If score < 0.65 and iteration < 2: `node_query_rewriter` rewrites query → re-search

Best answer across iterations is tracked in `best_score` / `best_answer` / `best_citations`.
