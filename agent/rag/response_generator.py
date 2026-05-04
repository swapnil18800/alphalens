"""
Generates a grounded answer from retrieved context chunks.
Formats citations, builds prompt, calls LLM.
"""
import json
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
    # Sort by CE score descending — CE now scores full text so score is reliable
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


# ── Strict-RAG post-gen citation validator (Plan C Fix 4) ─────────────────────
# Only activated when query_mode == "rag_only". Catches DeepSeek parametric-knowledge
# bleed-through by checking that numeric figures cited in the answer actually
# appear in the retrieved context. Failing-soft: appends disclaimer, never regenerates.

# Match common financial figure formats: $123.4B, 12%, 12.3%, $0.45, 16.5 billion, 1,234,567
_NUM_RE = re.compile(
    r"""
    (?:\$\s*\d{1,4}(?:[,.]\d+)*\s*(?:[BMK]|billion|million|trillion|bn|mn)?)  # $XXX.XB / $1,234
    |
    (?:\d+(?:\.\d+)?\s*%)                                                      # 37% or 12.3%
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _normalize_num_token(tok: str) -> str:
    """Lowercase, strip currency/whitespace/units to a comparable core."""
    t = tok.lower()
    for unit in ("billion", "million", "trillion", "bn", "mn", "bn", "$", " ", ","):
        t = t.replace(unit, "")
    return t.strip()


def _validate_strict_rag(answer: str, all_chunk_text: str) -> Tuple[bool, float, List[str]]:
    """
    Returns (passed, fraction_verified, unverified_tokens).
    `passed` = True when fraction_verified >= 0.5 OR fewer than 3 numeric tokens cited
    (single-fact answers are not penalized for thin numeric coverage).

    Unit-mismatch tolerance: financial chunks commonly store numbers in thousands/millions
    while answers report in B/M shorthand. "$18.44B" ↔ "18,435,591" (thousands) is a
    legitimate match. We verify by checking whether the leading 3+ digits of the answer
    number appear as a prefix in the stripped numeric haystack.
    """
    if not answer or not all_chunk_text:
        return True, 1.0, []
    nums = list(set(_NUM_RE.findall(answer)))
    if len(nums) < 3:
        # Single-fact or two-number answers not penalized — too many false positives.
        return True, 1.0, []
    haystack = all_chunk_text.lower()
    # Strip all non-digit/non-dot characters for loose numeric search
    haystack_digits = re.sub(r"[^\d]", "", haystack)
    verified = 0
    unverified: List[str] = []
    for n in nums:
        norm = _normalize_num_token(n)
        if not norm:
            continue
        # Pass 1: direct substring match (handles "637.9 billion" in chunk text)
        digits_only = re.sub(r"[^\d.]", "", norm)
        if (norm and norm in haystack) or (digits_only and digits_only in haystack):
            verified += 1
            continue
        # Pass 2: leading-digits prefix match to tolerate unit scale differences.
        # "$18.44B" → digits_only="18.44" → leading_prefix="1844" (4+ digits).
        # If chunk has "18,435,591" → haystack_digits contains "18435591" → "1844" matches prefix.
        compact = digits_only.replace(".", "")
        if len(compact) >= 4 and haystack_digits and compact[:4] in haystack_digits:
            verified += 1
            continue
        unverified.append(n)
    if not nums:
        return True, 1.0, []
    frac = verified / len(nums)
    return (frac >= 0.5), frac, unverified


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
        r"\b(only use|solely|only cite|cite only|do not use|don't use"
        r"|from the .{0,30}10-K.{0,10}only"
        r"|from the .{0,30}filings.{0,10}only|not general knowledge|without general knowledge"
        r"|strictly from|only from retrieved|verbatim in the retrieved"
        r"|appear in the retrieved|figures that appear in)\b",
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
            async for token in llm.astream(prompt, system=RESPONSE_SYSTEM, max_tokens=1200):
                tokens.append(token)
                try:
                    await token_callback(token)
                except Exception:
                    pass
            answer = "".join(tokens)
        else:
            answer = await llm.acomplete(prompt, system=RESPONSE_SYSTEM, max_tokens=1200)
    except Exception as e:
        logger.error(f"[response_generator] LLM call failed: {e}")
        answer = "I encountered an error generating a response. Please try again."

    all_chunks = sec_chunks + transcript_chunks + news_results

    # Plan C Fix 4: post-gen validation in strict-RAG mode. Append disclaimer if
    # numeric tokens in the answer don't appear in retrieved context (catches
    # DeepSeek parametric-knowledge bleed-through). Only fires for questions that
    # explicitly ask for strict-context grounding to avoid false positives on
    # cross-company/analysis questions that are correctly computed from context.
    if query_mode == "rag_only" and _question_wants_strict:
        try:
            haystack = " ".join((c.get("chunk_text") or "") for c in (sec_chunks + transcript_chunks))
            ok, frac, unverified = _validate_strict_rag(answer, haystack)
            if not ok and unverified:
                logger.warning(
                    f"[response_generator] strict-rag validator: {frac*100:.0f}% verified; "
                    f"unverified={unverified[:5]}"
                )
                disclaimer = (
                    "\n\n> **Note:** Some figures in this answer could not be verified directly "
                    "against the retrieved filing chunks. Please cross-check primary sources before "
                    "relying on these specific numbers."
                )
                answer = answer + disclaimer
        except Exception as e:
            logger.debug(f"[response_generator] strict-rag validator skipped: {e}")

    citations = _build_citations(all_chunks)

    return answer, citations
