"""
LangSmith end-to-end trace test for AlphaLens.

Lifecycle:
  1. Start the backend subprocess (LANGCHAIN_TRACING_V2=true)
  2. Wait for /health (DB + LangGraph ready)
  3. Wait for "BM25 hybrid search index ready" in subprocess output (full readiness)
  4. Fire 4 WS queries covering the three execution paths:
       - RAG-only          → success path, verbose financial answer
       - Web search        → web_only / hybrid path
       - Out-of-scope      → finalize_early path (short-circuits at plan_search)
       - Retry-likely      → evaluate_quality → rewrite_query → retrieve_context
  5. Save all WS events + summary to traces/{timestamp}_{label}_trace.json
  6. Terminate backend

Run:
    python tests/tracing/test_langsmith_trace.py
"""

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import websockets

# ─── config ───────────────────────────────────────────────────────────────────
BACKEND_PORT    = 8765
BACKEND_URL     = f"http://localhost:{BACKEND_PORT}"
WS_URL          = f"ws://localhost:{BACKEND_PORT}/ws"
HEALTH_TIMEOUT  = 30    # seconds to wait for /health
BM25_TIMEOUT    = 90    # seconds to wait for BM25 index after /health
QUERY_TIMEOUT   = 180   # seconds per query

TRACES_DIR = Path(__file__).parent / "traces"
TRACES_DIR.mkdir(exist_ok=True)

# ─── queries: 4 distinct execution paths ──────────────────────────────────────
QUERIES = [
    # Path 1: RAG answer — multi-metric Apple question, gets rich context with 20+ citations
    {
        "label":      "rag_apple",
        "web_search": False,
        "question": (
            "What was Apple's total net revenue, gross margin, and net income for fiscal year 2024? "
            "How did each metric compare to fiscal year 2023, and what segments drove the changes? "
            "Include specific dollar figures and year-over-year percentages."
        ),
        "expect": "RAG path — Apple financials in 10-K; may retry once if initial decomposition retrieves sparse context",
    },
    # Path 2: web search — web_search=True forces web_only routing via Tavily (or graceful no-results)
    {
        "label":      "web_search",
        "web_search": True,
        "question": (
            "What did NVIDIA CEO Jensen Huang say about the Blackwell GPU architecture "
            "and AI infrastructure demand in the most recent earnings call? "
            "Include specific customer names, revenue guidance, and shipment timelines he mentioned."
        ),
        "expect": "web_only path — routes to Tavily web search; answer from transcripts if Tavily unavailable",
    },
    # Path 3: out-of-scope → finalize_early (short-circuits at plan_search, no retrieval at all)
    {
        "label":      "out_of_scope",
        "web_search": False,
        "question": "What is the best recipe for chocolate lava cake with step-by-step instructions?",
        "expect": "finalize_early — plan_search marks is_out_of_scope=True, skips search entirely",
    },
    # Path 4: retry — broad multi-year, multi-segment NVDA question scores low on first pass
    {
        "label":      "retry_rag",
        "web_search": False,
        "question": (
            "Provide a detailed breakdown of NVIDIA's revenue by every segment for both FY2024 "
            "and FY2025, including year-over-year growth percentages for each segment, "
            "gross margin per segment, and specific management commentary from earnings calls "
            "about what drove the growth or decline in each segment."
        ),
        "expect": "retry_then_finalize — multi-dim first pass scores < 0.65, rewrite_query fires and improves retrieval",
    },
]


# ─── subprocess output capture ────────────────────────────────────────────────

class LogCapture:
    """Read subprocess stderr/stdout in a background thread, store lines."""

    def __init__(self, stream):
        self._lines: list[str] = []
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._reader, args=(stream,), daemon=True)
        self._thread.start()

    def _reader(self, stream):
        try:
            for raw in stream:
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    line = str(raw)
                self._lines.append(line)
                self._q.put(line)
        except Exception:
            pass

    def wait_for(self, substring: str, timeout: float) -> bool:
        """Block until a line containing `substring` is seen or timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                line = self._q.get(timeout=remaining)
                if substring in line:
                    return True
            except queue.Empty:
                pass
        return False

    def all_lines(self) -> list[str]:
        return list(self._lines)


# ─── helpers ──────────────────────────────────────────────────────────────────

def save_trace(label: str, events: list, summary: dict, log_lines: list[str]) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = TRACES_DIR / f"{ts}_{label}_trace.json"
    path.write_text(
        json.dumps({
            "label":      label,
            "timestamp":  datetime.now().isoformat(),
            "summary":    summary,
            "events":     events,
            "backend_log_excerpt": [l for l in log_lines if label.split("_")[0][:3] in l.lower()
                                    or "node" in l.lower() or "score" in l.lower()][-40:],
        }, indent=2),
        encoding="utf-8",
    )
    print(f"  [saved] {path.name}")
    return path


async def wait_for_health(timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                r = await client.get(f"{BACKEND_URL}/health", timeout=2)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(1)
    return False


async def run_query(label: str, question: str, web_search: bool,
                    log_capture: LogCapture) -> dict:
    session_id = str(uuid.uuid4())
    events: list[dict] = []
    summary: dict = {
        "label":      label,
        "question":   question,
        "web_search": web_search,
        "session_id": session_id,
    }

    print(f"\n[{label}] Connecting ...")
    async with websockets.connect(WS_URL, open_timeout=10) as ws:
        payload = {
            "type":       "query",
            "question":   question,
            "session_id": session_id,
            "web_search": web_search,
        }
        await ws.send(json.dumps(payload))
        print(f"  Q: {question[:90]}...")

        try:
            async with asyncio.timeout(QUERY_TIMEOUT):
                async for raw in ws:
                    msg = json.loads(raw)
                    events.append(msg)

                    t = msg.get("type")
                    if t == "status":
                        step = msg.get("step", "")
                        text = msg.get("message", "")
                        print(f"  [{step}] {text[:100]}")
                    elif t == "answer":
                        summary.update({
                            "answer_preview":  msg.get("answer", "")[:300],
                            "answer_length":   len(msg.get("answer", "")),
                            "citations":       len(msg.get("citations", [])),
                            "confidence":      msg.get("confidence"),
                        })
                        print(f"  [answer] confidence={summary['confidence']:.0%}  "
                              f"citations={summary['citations']}  "
                              f"chars={summary['answer_length']}")
                        break
                    elif t == "error":
                        summary["error"] = msg.get("detail", "unknown error")
                        print(f"  [error] {summary['error']}")
                        break
        except asyncio.TimeoutError:
            summary["error"] = f"query_timeout ({QUERY_TIMEOUT}s)"
            print(f"  [timeout] query exceeded {QUERY_TIMEOUT}s")

    # infer execution path from status messages
    status_steps = [e.get("step") for e in events if e.get("type") == "status"]
    statuses     = [e.get("message", "") for e in events if e.get("type") == "status"]
    retried      = any("retrying" in m.lower() or "rewritten" in m.lower() for m in statuses)
    finalized_early = not any(e.get("step") == "search" for e in events
                               if e.get("type") == "status")

    summary["execution_path"] = (
        "finalize_early"  if finalized_early else
        "retry_then_finalize" if retried else
        "direct_finalize"
    )
    summary["steps_seen"]  = [s for s in status_steps if s]
    summary["retry_fired"] = retried

    path = save_trace(label, events, summary, log_capture.all_lines())
    return {"label": label, "trace_file": str(path), **summary}


# ─── main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 65)
    print("AlphaLens - LangSmith end-to-end trace test  (4 queries)")
    print("=" * 65)

    # ── 1. start backend ──────────────────────────────────────────────────────
    env = {**os.environ, "LANGCHAIN_TRACING_V2": "true",
           "PYTHONUNBUFFERED": "1"}
    cmd = [sys.executable, "-m", "uvicorn", "app:app",
           "--port", str(BACKEND_PORT), "--log-level", "info"]
    root = Path(__file__).parent.parent.parent
    print(f"\nStarting backend on port {BACKEND_PORT} ...")
    proc = subprocess.Popen(
        cmd, env=env, cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    log_capture = LogCapture(proc.stdout)

    try:
        # ── 2. wait for /health (DB + LangGraph ready) ────────────────────────
        print("Waiting for /health ...")
        if not await wait_for_health(HEALTH_TIMEOUT):
            print(f"ERROR: backend did not respond within {HEALTH_TIMEOUT}s")
            proc.terminate(); sys.exit(1)
        print("/health OK")

        # ── 3. wait for BM25 index (full ML readiness) ────────────────────────
        print("Waiting for BM25 index (full readiness) ...")
        bm25_ready = await asyncio.get_event_loop().run_in_executor(
            None,
            log_capture.wait_for,
            "BM25 hybrid search index ready",
            BM25_TIMEOUT,
        )
        if bm25_ready:
            print("BM25 index ready. Backend fully up.\n")
        else:
            print(f"WARNING: BM25 not confirmed within {BM25_TIMEOUT}s — proceeding anyway.\n")

        # ── 4. run all queries ────────────────────────────────────────────────
        results = []
        for q in QUERIES:
            r = await run_query(q["label"], q["question"], q["web_search"], log_capture)
            results.append(r)

    finally:
        # ── 5. shut down backend ──────────────────────────────────────────────
        print("\nStopping backend ...")
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Backend stopped.")

    # ── 6. summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("Results:")
    all_ok = True
    for r in results:
        ok = "error" not in r
        if not ok:
            all_ok = False
        status = "OK  " if ok else "FAIL"
        conf   = f"{r.get('confidence', 0):.0%}" if r.get("confidence") is not None else "n/a"
        path   = f"{r.get('execution_path', '?'):<22}"
        print(f"  [{status}] {r['label']:<18}  {path}  conf={conf:>4}  "
              f"citations={r.get('citations', 0)}  "
              f"file={Path(r['trace_file']).name}")

    print("=" * 65)
    print(f"Traces saved to: {TRACES_DIR}")
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
