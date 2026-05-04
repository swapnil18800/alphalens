"""
Hybrid search engine: pgvector ANN + BM25 → RRF fusion → cross-encoder rerank.

Pipeline per query:
  1. Check semantic cache (cosine ≥ 0.92) — if hit, skip pipeline
  2. Embed query with all-MiniLM-L6-v2
  3. Parallel: pgvector cosine search  +  BM25 keyword search
  4. Reciprocal Rank Fusion (RRF) to merge both rank lists
  5. Cross-encoder (ms-marco-TinyBERT-L-2-v2) to rerank top-20 → keep top-k
  6. Optionally add Tavily news results

Embedding model is isolated to _get_embedding_model() — swap by changing EMBEDDING_MODEL.
"""
import asyncio
import logging
import os
import re
from typing import List, Dict, Any, Optional, Tuple

from . import database_manager as db

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # 384-dim, fast CPU model
RERANK_MODEL    = "cross-encoder/ms-marco-TinyBERT-L-2-v2"
RRF_K           = 60                     # standard RRF constant
CACHE_THRESHOLD = 0.92                   # cosine similarity for semantic cache hit

_embedding_model = None
_rerank_model    = None

# In-memory BM25 corpus (built once at startup from DB, refreshed hourly)
_bm25_index: Dict[str, Any] = {"ten_k": None, "transcripts": None}
_bm25_corpus: Dict[str, List[Dict]] = {"ten_k": [], "transcripts": []}


# ── Model loaders ──────────────────────────────────────────────────────────

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"[search] Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def _get_rerank_model():
    global _rerank_model
    if _rerank_model is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"[search] Loading cross-encoder: {RERANK_MODEL}")
            _rerank_model = CrossEncoder(RERANK_MODEL)
        except Exception as e:
            logger.warning(f"[search] Cross-encoder unavailable ({e}) — skipping rerank")
    return _rerank_model


def _embed(text: str) -> List[float]:
    return _get_embedding_model().encode(text, normalize_embeddings=True).tolist()


# ── BM25 tokenizer ────────────────────────────────────────────────────────

def _tokenize_bm25(text: str) -> List[str]:
    """
    Improved BM25 tokenizer: regex split on word/number boundaries + minimal
    suffix normalization. Handles financial terms (5G, 10-K, gpt-4o, R&D)
    better than naive whitespace split. No new dependencies required.
    """
    tokens = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
    result = []
    for t in tokens:
        if len(t) > 4:
            if t.endswith('ing'):
                t = t[:-3]
            elif t.endswith('tion'):
                t = t[:-4]
            elif t.endswith('ness'):
                t = t[:-4]
        result.append(t)
    return result


# ── BM25 corpus management ─────────────────────────────────────────────────

async def build_bm25_corpus() -> None:
    """
    Load all chunk texts from DB into memory for BM25 ranking.
    Called once at app startup. Typically 28k+ rows — loads in ~5-10s.
    """
    try:
        from rank_bm25 import BM25Okapi
        logger.info("[search] Building BM25 corpus from DB...")

        for source, table in [("ten_k", "ten_k_chunks"), ("transcripts", "transcript_chunks")]:
            if table == "ten_k_chunks":
                select_cols = "id, ticker, chunk_text, filing_year AS year, NULL::integer AS quarter, section"
            else:
                select_cols = "id, ticker, chunk_text, year, quarter, NULL::text AS section"
            rows = await db.fetch(
                f"SELECT {select_cols} FROM {table}",
                timeout=300,  # bulk fetch of 42k rows over Railway proxy can take 2-3 min
            )
            corpus_docs = [dict(r) for r in rows]
            if not corpus_docs:
                logger.warning(f"[search] BM25 {source}: table empty, skipping")
                continue
            tokenized = [_tokenize_bm25(r["chunk_text"]) for r in corpus_docs]
            _bm25_corpus[source] = corpus_docs
            _bm25_index[source]  = BM25Okapi(tokenized)
            logger.info(f"[search] BM25 {source}: {len(corpus_docs)} docs indexed")
    except ImportError:
        logger.warning("[search] rank_bm25 not installed — BM25 disabled, using pgvector only")
    except Exception as e:
        logger.warning(f"[search] BM25 build failed ({e}) — falling back to pgvector only")


# ── Semantic cache ─────────────────────────────────────────────────────────

async def _check_semantic_cache(query_embedding: List[float]) -> Optional[str]:
    """Return cached answer if a past query is cosine-similar enough."""
    try:
        emb_str = f"[{','.join(str(v) for v in query_embedding)}]"
        row = await db.fetchval(
            """
            SELECT response FROM semantic_cache
            WHERE 1 - (query_embedding <=> $1::vector) >= $2
            ORDER BY 1 - (query_embedding <=> $1::vector) DESC
            LIMIT 1
            """,
            emb_str, CACHE_THRESHOLD,
        )
        return row
    except Exception:
        return None


async def store_in_cache(question: str, response: str) -> None:
    """Persist a Q→A pair in semantic cache for future lookups."""
    try:
        embedding = await asyncio.get_event_loop().run_in_executor(None, _embed, question)
        emb_str   = f"[{','.join(str(v) for v in embedding)}]"
        await db.execute(
            "INSERT INTO semantic_cache (question, query_embedding, response) VALUES ($1, $2::vector, $3)",
            question, emb_str, response,
        )
    except Exception as e:
        logger.debug(f"[search] Cache store failed: {e}")


# ── Individual search methods ──────────────────────────────────────────────

async def _pgvector_search(
    table: str,
    embedding: List[float],
    ticker: Optional[str],
    limit: int,
    years: Optional[List[int]] = None,
) -> List[Dict]:
    results = await db.search_chunks(table, embedding, ticker, limit, years=years)
    for i, r in enumerate(results):
        r["_rank_pgvec"] = i
    return results


async def _fetch_recent_filing_tables(
    ticker: str,
    embedding: List[float],
    limit: int = 4,
) -> List[Dict]:
    """Fetch TABLE chunks from the most recently filed 10-K for a given ticker by semantic similarity."""
    embedding_str = f"[{','.join(str(v) for v in embedding)}]"
    try:
        rows = await db.fetch(
            """
            SELECT id, ticker, chunk_text,
                   1 - (embedding <=> $1::vector) AS similarity,
                   filing_year AS year,
                   NULL::integer AS quarter,
                   section, chunk_type
            FROM ten_k_chunks
            WHERE ticker = $2
              AND chunk_type = 'table'
              AND filing_year = (
                SELECT MAX(filing_year) FROM ten_k_chunks WHERE ticker = $2
              )
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            embedding_str, ticker.upper(), limit,
        )
        results = [dict(r) for r in rows]
        for r in results:
            r["source"] = "10k"
        return results
    except Exception as e:
        logger.warning(f"[search] recent_filing_tables fetch failed for {ticker}: {e}")
        return []


def _bm25_search(
    source: str,
    query: str,
    ticker: Optional[str],
    limit: int,
    years: Optional[List[int]] = None,
) -> List[Dict]:
    index = _bm25_index.get(source)
    corpus = _bm25_corpus.get(source, [])
    if index is None or not corpus:
        return []

    tokens = _tokenize_bm25(query)
    scores = index.get_scores(tokens)

    year_set = set(years) if years else None

    def _year_match(doc: Dict) -> bool:
        if not year_set:
            return True
        # BM25 corpus aliases both filing_year and transcript year to `year` (build_bm25_corpus)
        y = doc.get("year")
        try:
            return int(y) in year_set if y is not None else False
        except (TypeError, ValueError):
            return False

    # zip with corpus docs, optionally filter by ticker AND year
    ranked = sorted(
        [(score, doc) for score, doc in zip(scores, corpus)
         if (ticker is None or doc.get("ticker", "").upper() == ticker.upper())
         and _year_match(doc)],
        key=lambda x: x[0], reverse=True,
    )[:limit]

    results = []
    for i, (score, doc) in enumerate(ranked):
        results.append({**doc, "_rank_bm25": i, "similarity": float(score)})
    return results


def _rrf_merge(
    vec_results: List[Dict],
    bm25_results: List[Dict],
    k: int = RRF_K,
) -> List[Dict]:
    """
    Reciprocal Rank Fusion: score = 1/(k+rank_vec) + 1/(k+rank_bm25).
    Deduplicates by chunk id.
    """
    scores: Dict[Any, float] = {}
    docs:   Dict[Any, Dict]  = {}

    for i, doc in enumerate(vec_results):
        cid = doc.get("id", i)
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + i + 1)
        docs[cid]   = doc

    for i, doc in enumerate(bm25_results):
        cid = doc.get("id", id(doc))
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + i + 1)
        if cid not in docs:
            docs[cid] = doc

    merged = sorted(docs.values(), key=lambda d: scores.get(d.get("id"), 0.0), reverse=True)
    return merged


def _cross_encoder_rerank(
    query: str,
    docs: List[Dict],
    top_k: int,
) -> List[Dict]:
    """Score each (query, chunk_text) pair and return top_k by CE score."""
    ce = _get_rerank_model()
    if ce is None or not docs:
        return docs[:top_k]

    try:
        pairs  = [(query, d.get("chunk_text", "")[:2000]) for d in docs]
        scores = ce.predict(pairs)
        ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        return [doc for _, doc in ranked[:top_k]]
    except Exception as e:
        logger.warning(f"[search] Cross-encoder rerank failed ({e}) — returning unranked")
        return docs[:top_k]


# ── News search ────────────────────────────────────────────────────────────

_WEB_TIMEOUT_S = 8  # 8s is enough for Tavily (typical response 2-5s); caps parallel hybrid wait

async def _search_news(query: str, limit: int = 5) -> List[Dict]:
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return []
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        resp = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: client.search(
                    query,
                    max_results=limit,
                    include_raw_content=True,  # full scraped text, not just snippet
                )
            ),
            timeout=_WEB_TIMEOUT_S,
        )
        results = []
        for item in resp.get("results", []):
            # Prefer raw_content (full page) over content (short snippet)
            raw = (item.get("raw_content") or "").strip()
            snippet = (item.get("content") or "").strip()
            text = raw if len(raw) > len(snippet) else snippet
            results.append({
                "source":     "news",
                "ticker":     "",
                "chunk_text": text,
                "title":      item.get("title", ""),
                "url":        item.get("url", ""),
                "similarity": 0.8,
            })
        return results
    except asyncio.TimeoutError:
        logger.warning(f"[search] Tavily timeout after {_WEB_TIMEOUT_S}s for query: {query[:80]}")
        return []
    except Exception as e:
        logger.warning(f"[search] Tavily error: {e}")
        return []


# ── Public API ─────────────────────────────────────────────────────────────

try:
    from langsmith import traceable as _ls_traceable
    _web_search_tracer = _ls_traceable(name="web_search", run_type="tool")
except Exception:
    def _web_search_tracer(fn):
        return fn


def _clean_web_text(raw: str, query: str = "", max_chars: int = 3000) -> str:
    """
    Strip HTML artifacts from Tavily raw_content and return the most relevant
    paragraphs up to max_chars.

    Tavily raw_content is a full scraped page: it starts with navigation menus,
    then has the article body, then footers. Naive [:2500] slices nav garbage.
    This function:
      1. Strips HTML tags and common entities
      2. Splits into paragraphs, drops short/junk lines (nav, footers)
      3. Scores each paragraph by query keyword overlap
      4. Returns top-scored paragraphs up to max_chars
    """
    import html as _html

    # 1. Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", raw)
    # Decode HTML entities (&amp; &lt; &#160; etc.)
    text = _html.unescape(text)
    # Collapse whitespace / repeated newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 2. Split into paragraphs; filter junk
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    # Keep paragraphs with at least 60 chars — filters nav items, lone labels, JS blobs
    paragraphs = [p for p in paragraphs if len(p) >= 60]

    if not paragraphs:
        return text[:max_chars]

    # 3. Keyword scoring: count query terms in each paragraph (case-insensitive)
    query_terms = set(re.findall(r'\b[a-z]{3,}\b', query.lower()))

    def _score(para: str) -> int:
        lower = para.lower()
        return sum(1 for t in query_terms if t in lower)

    scored = sorted(enumerate(paragraphs), key=lambda x: _score(x[1]), reverse=True)

    # 4. Greedily pick paragraphs by relevance score, preserving order for readability
    selected_idx = set()
    total = 0
    # Always include the top-3 by score; then fill greedily
    for idx, para in scored:
        if total + len(para) + 2 > max_chars:
            break
        selected_idx.add(idx)
        total += len(para) + 2

    # Re-emit in original document order
    result_paras = [paragraphs[i] for i in sorted(selected_idx)]
    return "\n\n".join(result_paras)[:max_chars]


@_web_search_tracer
async def search_web(query: str, limit: int = 8) -> List[Dict]:
    """Public wrapper for Tavily news/web search. Cleans and deduplicates before returning."""
    results = await _search_news(query, limit)
    cleaned = []
    seen_urls: set = set()
    for r in results:
        url = r.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        raw_text = (r.get("chunk_text") or "").strip()
        # Clean HTML noise from raw_content; pass query for keyword-guided paragraph selection
        text = _clean_web_text(raw_text, query=query, max_chars=3000)
        if not text:
            continue
        cleaned.append({**r, "chunk_text": text, "source": "news"})
    return cleaned


async def run_parallel_search(
    question: str,
    tickers: List[str],
    query_mode: str = "rag_only",
    chunks_per_source: int = 8,
    boost_tables: bool = False,
    years: Optional[List[int]] = None,
) -> Tuple[Dict[str, List[Dict]], bool]:
    """
    Full RAG retrieval pipeline with semantic cache.
    query_mode controls whether web results are also fetched:
      - "rag_only" → SEC + transcript only
      - "hybrid"   → SEC + transcript + Tavily web

    Returns (results_dict, cache_hit):
      results_dict = {"sec": [...], "transcripts": [...], "news": [...]}
      cache_hit    = True if semantic cache was used
    """
    # 1. Embed query (CPU-bound → thread pool)
    embedding = await asyncio.get_event_loop().run_in_executor(None, _embed, question)

    # 2. Semantic cache check
    cached = await _check_semantic_cache(embedding)
    if cached:
        logger.info("[search] Semantic cache HIT")
        return {"sec": [], "transcripts": [], "news": [], "_cached_response": cached}, True

    # Lift top_k cap based on query complexity (multi-ticker / multi-year synthesis)
    n_tickers = max(1, len(tickers))
    n_years = len(years) if years else 0
    cap = 12 + 4 * max(n_tickers - 1, 0) + 3 * max(n_years - 1, 0)
    top_k_rerank = min(chunks_per_source, cap)
    pool_size    = chunks_per_source * 3

    def safe(r):
        return r if isinstance(r, list) else []

    # 3. Vector retrieval — parallel per-ticker for multi-ticker queries
    if len(tickers) > 1:
        per_ticker_tasks = [
            asyncio.gather(
                _pgvector_search("ten_k_chunks",      embedding, t, pool_size, years=years),
                _pgvector_search("transcript_chunks",  embedding, t, pool_size, years=years),
                return_exceptions=True,
            )
            for t in tickers
        ]
        all_results = await asyncio.gather(*per_ticker_tasks, return_exceptions=True)
        sec_vec_r: List[Dict] = []
        tc_vec_r:  List[Dict] = []
        for r in all_results:
            if isinstance(r, Exception):
                continue
            if isinstance(r, list) and len(r) == 2:
                sec_vec_r.extend(safe(r[0]))
                tc_vec_r.extend(safe(r[1]))
    else:
        primary_ticker = tickers[0] if tickers else None
        sec_vec, tc_vec = await asyncio.gather(
            _pgvector_search("ten_k_chunks",      embedding, primary_ticker, pool_size, years=years),
            _pgvector_search("transcript_chunks",  embedding, primary_ticker, pool_size, years=years),
            return_exceptions=True,
        )
        sec_vec_r = safe(sec_vec)
        tc_vec_r  = safe(tc_vec)

    # 4. Web search for hybrid mode (runs in parallel with BM25 below via gather in caller)
    if query_mode == "hybrid":
        news_query = f"{' '.join(tickers[:2])} {question}".strip() if tickers else question
        news = await _search_news(news_query)
    else:
        news = []

    # 5. BM25 search (sync, in-memory — fast)
    if len(tickers) > 1:
        per_tk = max(1, pool_size // len(tickers))
        sec_bm25: List[Dict] = []
        tc_bm25:  List[Dict] = []
        for t in tickers:
            sec_bm25.extend(_bm25_search("ten_k",       question, t, per_tk, years=years))
            tc_bm25.extend( _bm25_search("transcripts", question, t, per_tk, years=years))
    else:
        tk = tickers[0] if tickers else None
        sec_bm25 = _bm25_search("ten_k",       question, tk, pool_size, years=years)
        tc_bm25  = _bm25_search("transcripts", question, tk, pool_size, years=years)

    # 6. RRF merge
    sec_merged = _rrf_merge(sec_vec_r, sec_bm25)
    tc_merged  = _rrf_merge(tc_vec_r,  tc_bm25)

    # 7. Cross-encoder rerank (local sources)
    sec_final = _cross_encoder_rerank(question, sec_merged, top_k=top_k_rerank)
    tc_final  = _cross_encoder_rerank(question, tc_merged,  top_k=top_k_rerank)

    # 7a. Cross-encoder rerank for news (separate pool — keep news isolated from local rerank)
    if news:
        news = _cross_encoder_rerank(question, news, top_k=min(len(news), 6))

    # 7b. Table boost: only for revenue queries with 1-2 tickers; CE now scores full text
    # so this is a narrow safety net, not a primary signal.
    if boost_tables and 1 <= len(tickers) <= 2:
        TABLE_BOOST_N = 2
        already_ids = {c.get("id") for c in sec_final}
        table_candidates = [
            c for c in sec_merged
            if c.get("chunk_type") == "table" and c.get("id") not in already_ids
        ][:TABLE_BOOST_N]
        if table_candidates:
            sec_final = sec_final[:max(0, top_k_rerank - len(table_candidates))] + table_candidates
            logger.debug(f"[search] table_boost: injected {len(table_candidates)} table chunks")

    # Tag sources
    for r in sec_final:
        r["source"] = "10k"
    for r in tc_final:
        r["source"] = "transcript"

    return {"sec": sec_final, "transcripts": tc_final, "news": safe(news)}, False
