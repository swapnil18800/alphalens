# NOTE: This is a lightweight standalone RAGAS runner.
# For comprehensive evaluation (M1-M8 metrics including RAGAS faithfulness
# and context precision), use evals/qa_eval/run_eval.py instead.

"""
RAGAS evaluation runner for AlphaLens.

Run once after data is ingested to generate benchmark scores.
Scores go in README.md as credibility proof.

Usage: python evals/run_ragas.py [--dataset evals/test_dataset.json] [--out evals/results.json]

Requirements: pip install ragas datasets
(ragas is heavy — not in main requirements.txt)
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


async def collect_outputs(test_cases: list) -> list:
    """Run AlphaLens on each question and collect outputs."""
    # Import here to trigger DB + model setup
    from app.utils.database import create_pool
    from agent.graph import graph as research

    await create_pool()

    results = []
    for i, case in enumerate(test_cases, 1):
        question = case["question"]
        complexity = case.get("complexity", "")
        label = f"[{complexity.upper()}] " if complexity else ""
        logger.info(f"[{i}/{len(test_cases)}] {label}{question[:70]}…")
        try:
            state = await research.run(
                question=question,
                user_id="eval",
                session_id=f"eval-{i}",
            )
            answer = state.get("final_answer", "")
            all_chunks = state.get("sec_chunks", []) + state.get("transcript_chunks", [])
            contexts = [c.get("chunk_text", "") for c in all_chunks[:6]]
            logger.info(f"  ✓ len={len(answer)} | chunks={len(all_chunks)} | score={state.get('best_score', 0):.2f}")

            results.append({
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": case.get("ground_truth", ""),
            })
        except Exception as e:
            logger.error(f"  Error: {e}")
            results.append({
                "question": question,
                "answer": f"Error: {e}",
                "contexts": [],
                "ground_truth": case.get("ground_truth", ""),
            })

    return results


def _safe_mean(vals) -> float:
    """Average a list of floats, ignoring None/NaN. Returns 0.0 if empty."""
    import math
    if not isinstance(vals, (list, tuple)):
        return round(float(vals), 3)
    valid = [float(v) for v in vals if v is not None and not math.isnan(float(v))]
    return round(sum(valid) / len(valid), 3) if valid else 0.0


def run_ragas(results: list) -> dict:
    """Run RAGAS metrics on collected results."""
    import warnings
    try:
        from ragas import evaluate
        # ragas 0.4.x: deprecated singleton instances from ragas.metrics still work
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from datasets import Dataset
    except ImportError:
        logger.error("RAGAS not installed. Run: pip install ragas datasets")
        return {}

    # ragas 0.4.x accepts old column names via column_map
    ds = Dataset.from_dict({
        "question":     [r["question"]     for r in results],
        "answer":       [r["answer"]       for r in results],
        "contexts":     [r["contexts"]     for r in results],
        "ground_truth": [r["ground_truth"] for r in results],
    })

    logger.info("Running RAGAS evaluation (calls OpenAI — ~$0.05 for 10 questions)…")
    scores = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        column_map={
            "user_input":         "question",
            "response":           "answer",
            "retrieved_contexts": "contexts",
            "reference":          "ground_truth",
        },
        raise_exceptions=False,
    )

    # In ragas 0.4.x, scores[key] returns List[float]; _repr_dict stores pre-computed means
    return {
        "faithfulness":      _safe_mean(scores._repr_dict.get("faithfulness",      scores["faithfulness"])),
        "answer_relevancy":  _safe_mean(scores._repr_dict.get("answer_relevancy",  scores["answer_relevancy"])),
        "context_precision": _safe_mean(scores._repr_dict.get("context_precision", scores["context_precision"])),
        "context_recall":    _safe_mean(scores._repr_dict.get("context_recall",    scores["context_recall"])),
        "num_questions":     len(results),
    }


async def main(dataset_path: str, out_path: str):
    test_cases = json.loads(Path(dataset_path).read_text())
    logger.info(f"Loaded {len(test_cases)} test cases from {dataset_path}")

    outputs = await collect_outputs(test_cases)
    scores = run_ragas(outputs)

    if scores:
        print("\n" + "="*55)
        print("  RAGAS EVALUATION — AlphaLens")
        print("="*55)
        for k, v in scores.items():
            print(f"  {k:<25} {v}")
        print("="*55)

        Path(out_path).write_text(json.dumps(scores, indent=2))
        logger.info(f"Results saved to {out_path}")
        logger.info("Add these numbers to your README.md!")
    else:
        logger.warning("No scores produced — check RAGAS installation and OPENAI_API_KEY.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evals/test_dataset.json")
    parser.add_argument("--out", default="evals/results.json")
    args = parser.parse_args()
    asyncio.run(main(args.dataset, args.out))
