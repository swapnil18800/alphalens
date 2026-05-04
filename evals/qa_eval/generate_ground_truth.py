"""
Generate ground truth for AlphaLens eval question files using DB chunks + GPT-4o.

For each question, retrieves relevant SEC/transcript chunks from the database and
synthesizes a reference answer + key verifiable facts using GPT-4o.

Special handling:
  - hallucination_control questions (private companies) → NOT_IN_DATABASE template
  - edge_cases → EDGE_CASE / BROAD_QUERY template
  - web_trigger categories → WEB_SEARCH_TRIGGERED template
  - all others → DB retrieval + GPT-4o synthesis

Ground truth is stored in-place in the question file under "ground_truth_map":
  {category: {ground_truth_map: {question_text: {ground_truth, key_facts}}}}

Reusable for any question file with the same JSON structure.

Usage:
    python evals/qa_eval/generate_ground_truth.py --smoke
    python evals/qa_eval/generate_ground_truth.py --full
    python evals/qa_eval/generate_ground_truth.py --category deep_retrieval earnings_grounding
    python evals/qa_eval/generate_ground_truth.py --force
    python evals/qa_eval/generate_ground_truth.py --input path/to/other_questions.json --full
"""
import argparse
import asyncio
import json
import logging
import re
import sys

# Force UTF-8 output on Windows so Unicode chars don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime

# Create log directory and file
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"gt_generation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to {log_file}")

DEFAULT_INPUT = Path(__file__).parent / "question_v2.txt"

# ---------------------------------------------------------------------------
# Ticker extraction
# ---------------------------------------------------------------------------

TICKER_MAP = {
    "google cloud": "GOOGL",
    "advanced micro devices": "AMD",
    "nvidia": "NVDA", "nvda": "NVDA",
    "amd": "AMD",
    "apple": "AAPL", "aapl": "AAPL",
    "microsoft": "MSFT", "msft": "MSFT", "azure": "MSFT",
    "amazon": "AMZN", "amzn": "AMZN", "aws": "AMZN",
    "alphabet": "GOOGL", "google": "GOOGL", "googl": "GOOGL",
    "meta": "META", "facebook": "META",
    "tesla": "TSLA", "tsla": "TSLA",
    "netflix": "NFLX", "nflx": "NFLX",
    "snowflake": "SNOW", "snow": "SNOW",
    "intel": "INTC", "intc": "INTC",
    "ibm": "IBM",
    "palantir": "PLTR",
    "cisco": "CSCO",
    "qualcomm": "QCOM", "qcom": "QCOM",
    "lam research": "LRCX", "lrcx": "LRCX",
    "applied materials": "AMAT", "amat": "AMAT",
    "salesforce": "CRM", "crm": "CRM",
    "servicenow": "NOW", "now": "NOW",
    "palo alto": "PANW", "panw": "PANW",
    "adobe": "ADBE", "adbe": "ADBE",
    "broadcom": "AVGO", "avgo": "AVGO",
    "micron": "MU", "micron technology": "MU",
    "texas instruments": "TXN", "txn": "TXN",
    "uber": "UBER", "ubereats": "UBER",
}

def extract_tickers(text: str) -> list[str]:
    """Extract known DB tickers from question text using TICKER_MAP."""
    lower = text.lower()
    found = []
    # Sort by phrase length descending so multi-word phrases match first
    for phrase in sorted(TICKER_MAP, key=len, reverse=True):
        ticker = TICKER_MAP[phrase]
        if phrase in lower and ticker not in found:
            found.append(ticker)
    return found[:4]  # cap at 4 tickers to keep context manageable


# ---------------------------------------------------------------------------
# Special-case ground truth templates
# ---------------------------------------------------------------------------

_NOT_IN_DB_KEYWORDS = {"spacex", "stripe"}

def _is_hallucination_question(question: str) -> bool:
    lower = question.lower()
    return any(kw in lower for kw in _NOT_IN_DB_KEYWORDS)


def _not_in_db_entry() -> dict:
    return {
        "ground_truth": (
            "This company is not covered in the AlphaLens database of SEC 10-K filings or "
            "earnings transcripts. The system should clearly acknowledge it cannot provide "
            "financial data for this company and should not fabricate any figures."
        ),
        "key_facts": ["NOT_IN_DATABASE"],
    }


def _edge_case_entry(question: str) -> dict:
    # Gibberish or very short nonsense input
    has_meaning = len(question) >= 20 and sum(c.isalpha() for c in question) >= 5
    if not has_meaning:
        return {
            "ground_truth": (
                "The system should recognize this as an invalid or nonsensical query "
                "and respond gracefully without attempting to fabricate an answer."
            ),
            "key_facts": ["INVALID_INPUT"],
        }
    # Overly broad question
    return {
        "ground_truth": (
            "The system should acknowledge the overly broad scope of this question. "
            "It may either scope its response to a subset of companies it covers or "
            "explain its coverage limitations gracefully."
        ),
        "key_facts": ["BROAD_QUERY_HANDLED"],
    }


def _web_trigger_entry() -> dict:
    return {
        "ground_truth": (
            "The system should use web search to provide recent information about this topic. "
            "The answer should contain developments beyond the static SEC filing database, "
            "citing recent news sources. The system must not rely solely on its internal documents."
        ),
        "key_facts": ["WEB_SEARCH_TRIGGERED"],
    }


# ---------------------------------------------------------------------------
# DB chunk retrieval
# ---------------------------------------------------------------------------

async def _fetch_chunks(question: str, tickers: list[str], limit_per_ticker: int = 12) -> str:
    """
    Fetch relevant DB chunks for given question + tickers.
    Returns a formatted context string for GPT-4o.
    """
    from agent.rag.search_engine import _embed
    from agent.rag import database_manager as db

    embedding = _embed(question)
    all_chunks: list[dict] = []

    for ticker in tickers:
        sec = await db.search_chunks("ten_k_chunks", embedding, ticker_filter=ticker, limit=limit_per_ticker)
        for c in sec:
            c["_label"] = f"[SEC-{ticker}]"
        all_chunks.extend(sec)

        txn = await db.search_chunks("transcript_chunks", embedding, ticker_filter=ticker, limit=limit_per_ticker // 2)
        for c in txn:
            c["_label"] = f"[TC-{ticker}]"
        all_chunks.extend(txn)

    # Deduplicate by chunk id, sort by similarity descending, cap at 20
    seen: set[str] = set()
    deduped: list[dict] = []
    for c in sorted(all_chunks, key=lambda x: x.get("similarity", 0.0), reverse=True):
        cid = str(c.get("id", ""))
        if cid not in seen:
            seen.add(cid)
            deduped.append(c)
        if len(deduped) >= 20:
            break

    if not deduped:
        return ""

    parts = []
    for c in deduped:
        label = c.get("_label", "")
        section = c.get("section") or ""
        year = c.get("year") or ""
        sim = c.get("similarity", 0.0)
        text = (c.get("chunk_text") or "")[:600]
        header = f"{label} {section} ({year}) [sim={sim:.3f}]"
        parts.append(f"{header}:\n{text}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# GPT-4o synthesis
# ---------------------------------------------------------------------------

_GT_SYSTEM = """\
You are a financial data expert with access to SEC 10-K filings and earnings call transcripts.
Given a question and relevant document excerpts, produce a precise reference answer and a list of key verifiable facts.

Rules:
- Use ONLY information from the provided document excerpts — never fabricate
- Be specific: include actual numbers, percentages, company names, and fiscal years from the excerpts
- key_facts must be short (under 15 words each) and independently verifiable
- If excerpts lack sufficient data, say so honestly in ground_truth
- Include 4–6 key_facts when possible

Return ONLY valid JSON (no markdown):
{
  "ground_truth": "2–5 sentence reference answer using only information from the excerpts",
  "key_facts": ["short verifiable fact 1", "short verifiable fact 2", ...]
}
"""

_GT_USER = """\
QUESTION: {question}

DOCUMENT EXCERPTS:
{context}

Generate the reference answer and key_facts JSON now.
"""


async def _synthesize(question: str, context: str) -> dict:
    """Call GPT-4o to synthesize ground truth from retrieved context."""
    import openai
    client = openai.AsyncOpenAI()

    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _GT_SYSTEM},
                {"role": "user", "content": _GT_USER.format(question=question, context=context[:6000])},
            ],
            temperature=0.1,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(resp.choices[0].message.content.strip())
        return {
            "ground_truth": parsed.get("ground_truth", ""),
            "key_facts": parsed.get("key_facts", []),
        }
    except Exception as e:
        logger.error(f"GPT-4o synthesis failed: {e}")
        return {"ground_truth": f"[Synthesis failed: {e}]", "key_facts": []}


# ---------------------------------------------------------------------------
# Per-question processor
# ---------------------------------------------------------------------------

async def _process_question(
    category: str,
    question: str,
    web_search: bool,
) -> dict:
    """Return {ground_truth, key_facts} for one question."""

    if _is_hallucination_question(question):
        return _not_in_db_entry()

    if category == "edge_cases":
        return _edge_case_entry(question)

    # Pure web-trigger categories with no DB data expected
    if web_search and category == "web_trigger":
        return _web_trigger_entry()

    # All other categories: fetch DB chunks and synthesize
    tickers = extract_tickers(question)
    if not tickers:
        logger.warning(f"  No tickers found for: {question[:60]}")
        return {
            "ground_truth": "No specific company data could be identified for this question.",
            "key_facts": [],
        }

    logger.info(f"  Tickers: {tickers} - fetching DB chunks...")
    context = await _fetch_chunks(question, tickers)

    if not context:
        logger.warning(f"  No DB chunks found for tickers {tickers}")
        return {
            "ground_truth": "Insufficient data found in the database for this question.",
            "key_facts": [],
        }

    logger.info("  Synthesizing with GPT-4o...")
    return await _synthesize(question, context)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def generate_all(
    input_file: Path,
    smoke: bool = False,
    categories_filter: Optional[list[str]] = None,
    force: bool = False,
) -> None:
    from app.utils.database import create_pool
    from agent.rag.search_engine import _get_embedding_model

    logger.info("Initialising DB pool…")
    await create_pool()

    logger.info("Pre-loading embedding model…")
    _get_embedding_model()

    data: dict = json.loads(input_file.read_text(encoding="utf-8"))

    # Collect work items
    tasks: list[tuple[str, str, bool, bool]] = []  # (category, question, web_search, already_has_gt)
    for category, meta in data.items():
        if categories_filter and category not in categories_filter:
            continue
        web_search = meta.get("web_search", False)
        gt_map = meta.get("ground_truth_map", {})
        for q in meta.get("questions", []):
            tasks.append((category, q, web_search, bool(gt_map.get(q))))

    if smoke:
        tasks = tasks[:3]
        print(f"SMOKE MODE — {len(tasks)} questions\n")
    else:
        print(f"Processing {len(tasks)} questions across {len({t[0] for t in tasks})} categories\n")

    updated = 0
    for i, (category, question, web_search, has_gt) in enumerate(tasks, 1):
        q_short = question[:70]
        print(f"[{i}/{len(tasks)}] [{category}] {q_short}{'…' if len(question) > 70 else ''}")

        if has_gt and not force:
            print("  ↳ already has ground_truth — skip (use --force to regenerate)\n")
            continue

        result = await _process_question(category, question, web_search)

        # Store in question file structure
        if "ground_truth_map" not in data[category]:
            data[category]["ground_truth_map"] = {}
        data[category]["ground_truth_map"][question] = result

        print(f"  [OK] ground_truth: {result['ground_truth'][:90]}...")
        print(f"  [OK] key_facts ({len(result['key_facts'])}): {result['key_facts'][:3]}\n")
        updated += 1

    # Write back in-place
    input_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=" * 60)
    print(f"Updated {updated} question(s) in {input_file.name}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ground truth for AlphaLens eval questions")
    parser.add_argument("--smoke", action="store_true", help="Process first 3 questions only")
    parser.add_argument("--full", action="store_true", help="Process all questions")
    parser.add_argument("--category", nargs="+", metavar="CAT", dest="category",
                        help="Process specific categories only")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate ground truth even if it already exists")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help=f"Path to question JSON file (default: {DEFAULT_INPUT.name})")
    args = parser.parse_args()

    if not args.smoke and not args.full and not args.category:
        parser.error("Specify --smoke, --full, or --category")

    asyncio.run(generate_all(
        input_file=args.input,
        smoke=args.smoke,
        categories_filter=args.category,
        force=args.force,
    ))
