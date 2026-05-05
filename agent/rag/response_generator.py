"""
Generates a grounded answer from retrieved context chunks.
Formats citations, builds prompt, calls LLM.
"""
import logging
import re
from typing import List, Dict, Any, Tuple, Optional

from agent.llm.factory import LLMFactory
from .prompts import RESPONSE_SYSTEM, RESPONSE_PROMPT

logger = logging.getLogger(__name__)


def _is_table_chunk(c: Dict) -> bool:
    """Detect pipe-delimited table chunks (may lack explicit chunk_type field)."""
    if c.get("chunk_type") == "table":
        return True
    text = c.get("chunk_text", "")
    return text.count("|") > 15


def _format_chunks(chunks: List[Dict], max_chars: int = 4000) -> str:
    if not chunks:
        return "No relevant context found."

    # For cross-company chunks (≥2 distinct tickers), interleave round-robin by ticker
    # so one ticker's high-CE scores don't crowd out others before the max_chars budget runs out.
    tickers_present = [c.get("ticker", "") for c in chunks if c.get("ticker")]
    if len(set(tickers_present)) >= 2:
        from collections import defaultdict
        ticker_groups: Dict[str, List] = defaultdict(list)
        for c in sorted(chunks, key=lambda c: -(c.get("score") or 0)):
            ticker_groups[c.get("ticker", "")].append(c)
        sorted_chunks = []
        max_len = max(len(v) for v in ticker_groups.values())
        for i in range(max_len):
            for k in sorted(ticker_groups.keys()):
                if i < len(ticker_groups[k]):
                    sorted_chunks.append(ticker_groups[k][i])
    else:
        sorted_chunks = sorted(chunks, key=lambda c: -(c.get("score") or 0))

    parts = []
    total = 0
    for c in sorted_chunks:
        ticker  = c.get("ticker", "")
        text    = c.get("chunk_text", "")
        year    = c.get("year") or c.get("filing_year", "")
        quarter = c.get("quarter", "")
        company = c.get("company_name") or ""

        # Surface year + company in label so the LLM disambiguates when chunks
        # from different years of the same ticker are interleaved (Plan C Fix 6).
        if c.get("source") == "transcript":
            label = f"[TC-{ticker}-Q{quarter}-FY{year}]"
            if company:
                label = label[:-1] + f" | {company}]"
        elif c.get("source") == "news":
            url   = c.get("url", "")
            label = f"[NEWS: {c.get('title', '')} | {url}]"
        else:
            label = f"[SEC-{ticker}-{year}]"
            if company:
                label = label[:-1] + f" | {company} | filing_year={year}]"

        per_chunk = 1000
        excerpt = f"{label} {text[:per_chunk]}"
        if total + len(excerpt) > max_chars:
            break
        parts.append(excerpt)
        total += len(excerpt)
    return "\n\n".join(parts)



def _build_citations(chunks: List[Dict]) -> List[Dict]:
    seen: set = set()
    citations = []
    for c in chunks:
        source = c.get("source", "")
        if source == "news":
            # News chunks: deduplicate by URL; show title+URL instead of raw text
            key = ("news", c.get("url", ""))
        else:
            key = (c.get("ticker"), source, c.get("year"), c.get("quarter"), c.get("section"))
        if key in seen:
            continue
        seen.add(key)
        entry: Dict = {
            "ticker":      c.get("ticker", ""),
            "source":      source,
            "year":        c.get("year"),
            "filing_year": c.get("filing_year") or c.get("year"),
            "quarter":     c.get("quarter"),
            "section":     c.get("section", ""),
            "similarity":  round(c.get("similarity", 0), 3),
        }
        if source == "news":
            entry["title"] = c.get("title", "")
            entry["url"]   = c.get("url", "")
            # Short clean excerpt for UI preview (no HTML noise after search_engine cleaning)
            text = (c.get("chunk_text") or "")
            entry["chunk_text"] = text[:300]
        else:
            entry["chunk_text"] = (c.get("chunk_text") or "")[:800]
        citations.append(entry)
    return citations


async def generate(
    question: str,
    sec_chunks: List[Dict],
    transcript_chunks: List[Dict],
    news_results: List[Dict],
    conversation_history: List[Dict],
    iteration: int = 0,
    token_callback=None,
    query_mode: str = "rag_only",
) -> Tuple[str, List[Dict]]:
    """
    Generate a grounded answer with optional token streaming.
    Returns (answer_text, citations_list).
    token_callback: async callable(token: str) called for each streamed token.
    query_mode: controls context budget split for hybrid queries.
    """
    llm = LLMFactory.create()

    history_text = ""
    if conversation_history:
        recent = conversation_history[-4:]
        history_text = "\n".join(f"{m['role'].upper()}: {m['content'][:200]}" for m in recent)

    # For hybrid queries split the 6000-char budget: 60% local, 40% web
    # to prevent local chunks from crowding out web results or vice versa.
    if query_mode == "hybrid" and news_results:
        local_budget = 3600
        web_budget   = 2400
    elif query_mode == "web_only":
        local_budget = 0
        web_budget   = 6000
    else:
        local_budget = 6000
        web_budget   = 800

    # Heavy strict-RAG block only fires when the user's question explicitly asks for
    # grounding discipline ("only use", "do not use general knowledge", "from the 10-K only",
    # etc.). For ordinary rag_only questions the general RESPONSE_PROMPT rules already
    # enforce chunk-grounding without over-refusing calculable figures.
    _STRICT_Q_RE = re.compile(
        r"\b(do not use general knowledge|don't use general knowledge|only from retrieved|only use retrieved)\b",
        re.IGNORECASE,
    )
    _question_wants_strict = bool(_STRICT_Q_RE.search(question))
    strict_rag_block = (
        "STRICT MODE: Answer only from the local SEC filings and earnings transcripts above. "
        "Do not use general knowledge or training data. If a specific number, segment, or "
        "fact is not visibly present in a chunk, you MUST say 'not found in the provided context'. "
        "It is BETTER to say data is unavailable than to recall it from memory.\n\n"
        if (query_mode == "rag_only" and _question_wants_strict) else ""
    )
    hybrid_block = (
        "HYBRID MODE: This answer must integrate BOTH historical filing data AND recent news. "
        "Cite at least one [SEC-...] or [TC-...] marker AND at least one [NEWS] marker. "
        "If web context is empty, state 'no recent news available'. If filings are empty, "
        "state 'no filing context available'.\n\n"
        if query_mode == "hybrid" else ""
    )

    prompt = RESPONSE_PROMPT.format(
        question=question,
        sec_context=_format_chunks(sec_chunks, max_chars=local_budget),
        transcript_context=_format_chunks(transcript_chunks, max_chars=local_budget),
        news_context=_format_chunks(news_results, max_chars=web_budget),
        history=history_text or "No prior conversation.",
        strict_rag_block=strict_rag_block,
        hybrid_block=hybrid_block,
    )

    try:
        if token_callback is not None:
            # Stream tokens to callback
            tokens: list[str] = []
            async for token in llm.astream(prompt, system=RESPONSE_SYSTEM, max_tokens=700):
                tokens.append(token)
                try:
                    await token_callback(token)
                except Exception:
                    pass
            answer = "".join(tokens)
        else:
            answer = await llm.acomplete(prompt, system=RESPONSE_SYSTEM, max_tokens=700)
    except Exception as e:
        logger.error(f"[response_generator] LLM call failed: {e}")
        answer = "I encountered an error generating a response. Please try again."

    all_chunks = sec_chunks + transcript_chunks + news_results
    citations = _build_citations(all_chunks)

    return answer, citations
