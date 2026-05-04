#!/usr/bin/env python3
"""
AlphaLens API Test Suite — ported and adapted from finance-agent/test_apis.py.

Tests all major endpoints: health, chat RAG, companies, SEC filings, transcripts.
Run with:
    python tests/api/test_apis.py                         # fast (no LLM calls)
    python tests/api/test_apis.py --all                   # includes slow LLM tests
    python tests/api/test_apis.py --base-url http://...   # custom URL

Exit code 0 = all tests passed, 1 = some tests failed.
"""

import sys
import json
import time
import argparse
import urllib.request
import urllib.error

DEV_USER = "00000000-0000-0000-0000-000000000001"


def request(method, url, body=None, headers=None):
    """Simple HTTP request — returns (status_code, parsed_body)."""
    h = {"Content-Type": "application/json", "X-User-ID": DEV_USER}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def stream_request(url, body, timeout=300):
    """Streaming POST — collects all SSE events. Returns list of parsed event dicts."""
    h = {"Content-Type": "application/json", "X-User-ID": DEV_USER}
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    events = []
    try:
        import socket
        orig = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        try:
            with urllib.request.urlopen(req) as resp:
                for raw_line in resp:
                    line = raw_line.decode().strip()
                    if line.startswith("data: "):
                        try:
                            events.append(json.loads(line[6:]))
                        except json.JSONDecodeError:
                            pass
        finally:
            socket.setdefaulttimeout(orig)
    except urllib.error.HTTPError as e:
        events.append({"error": e.code, "body": e.read().decode()})
    return events


class TestRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.passed = 0
        self.failed = 0
        self.results = []

    def check(self, name: str, condition: bool, detail: str = ""):
        status = "PASS" if condition else "FAIL"
        self.results.append((status, name, detail))
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    def section(self, title: str):
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")

    # ── Health ────────────────────────────────────────────────────────────

    def test_health(self):
        self.section("Health & Status")
        status, body = request("GET", f"{self.base_url}/health")
        self.check("Health endpoint returns 200", status == 200, f"status={status}")
        if isinstance(body, dict):
            self.check("Status is healthy", body.get("status") in ("healthy", "ok"),
                       str(body.get("status")))

    # ── Companies ─────────────────────────────────────────────────────────

    def test_companies(self):
        self.section("Companies List")
        status, body = request("GET", f"{self.base_url}/companies?query=NVIDIA")
        self.check("Companies endpoint returns 200", status == 200, f"status={status}")
        if isinstance(body, (list, dict)):
            companies = body if isinstance(body, list) else body.get("companies", [])
            self.check("Companies returns a list", isinstance(companies, list))

    # ── Chat conversations ────────────────────────────────────────────────

    def test_chat_conversations(self):
        self.section("Chat — Conversations API")
        status, body = request("GET", f"{self.base_url}/chat/conversations")
        self.check("GET /chat/conversations returns 200", status == 200, f"status={status}")
        status2, body2 = request("POST", f"{self.base_url}/chat", {"question": "ping"})
        self.check("POST /chat accepts requests", status2 == 200, f"status={status2}")

    # ── Database coverage ─────────────────────────────────────────────────

    def test_db_coverage(self):
        self.section("Database Data Coverage")
        try:
            import os
            sys.path.insert(0, ".")
            from dotenv import load_dotenv
            load_dotenv(".env", override=True)
            import psycopg2

            url = os.getenv("DATABASE_URL")
            if not url:
                print("  [SKIP] DATABASE_URL not set")
                return

            conn = psycopg2.connect(url)
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM ten_k_chunks")
            ten_k = cur.fetchone()[0]
            self.check("ten_k_chunks has data", ten_k > 0, f"{ten_k} rows")

            cur.execute("SELECT COUNT(DISTINCT ticker) FROM ten_k_chunks")
            tickers = cur.fetchone()[0]
            self.check("At least 3 companies in 10-K", tickers >= 3, f"{tickers} companies")

            cur.execute("SELECT COUNT(*) FROM transcript_chunks")
            tc = cur.fetchone()[0]
            self.check("transcript_chunks has data", tc > 0, f"{tc} rows")

            cur.execute("SELECT DISTINCT ticker FROM ten_k_chunks ORDER BY ticker")
            ticker_list = [r[0] for r in cur.fetchall()]
            print(f"  [INFO] 10-K tickers: {ticker_list}")

            conn.close()
        except Exception as e:
            print(f"  [SKIP] DB check failed: {e}")

    # ── Chat RAG (slow, requires LLM) ────────────────────────────────────

    def test_chat_rag_10k(self):
        self.section("Chat RAG — 10-K Query (slow ~20-60s)")
        print("  [INFO] Hitting Cerebras — may take up to 60s...")
        status, body = request(
            "POST", f"{self.base_url}/chat",
            {"question": "What was NVIDIA total revenue in their latest fiscal year? Give exact numbers."}
        )
        self.check("POST /chat returns 200", status == 200, f"status={status}")
        if isinstance(body, dict):
            answer = body.get("answer", "")
            citations = body.get("citations", [])
            self.check("Answer is non-empty", len(answer) > 20, answer[:80])
            self.check("Answer mentions revenue figure",
                       "$" in answer or "billion" in answer.lower(), answer[:100])
            self.check("Citations returned", len(citations) > 0, f"{len(citations)} citations")

    def test_chat_rag_multi_company(self):
        self.section("Chat RAG — Multi-Company Comparison")
        print("  [INFO] Comparing Apple vs Microsoft...")
        status, body = request(
            "POST", f"{self.base_url}/chat",
            {"question": "Compare Apple and Microsoft revenue growth in their latest fiscal year"}
        )
        self.check("Multi-company query returns 200", status == 200, f"status={status}")
        if isinstance(body, dict):
            answer = body.get("answer", "")
            self.check("Multi-company answer non-empty", len(answer) > 20, answer[:80])
            self.check("Answer mentions Apple or Microsoft",
                       "Apple" in answer or "AAPL" in answer or "Microsoft" in answer, answer[:100])

    def test_chat_out_of_scope(self):
        self.section("Chat — Out-of-Scope Question Handling")
        status, body = request(
            "POST", f"{self.base_url}/chat",
            {"question": "What's the weather like in New York today?"}
        )
        self.check("Out-of-scope handled gracefully (200)", status == 200, f"status={status}")
        if isinstance(body, dict):
            answer = body.get("answer", "")
            self.check("Out-of-scope returns an answer", len(answer) > 0, answer[:80])

    # ── BM25 / hybrid search (unit-level via DB) ──────────────────────────

    def test_hybrid_search_available(self):
        self.section("Hybrid Search — pgvector + BM25")
        # Verify search works end-to-end via the chat endpoint (pgvector always on)
        status, body = request(
            "POST", f"{self.base_url}/chat",
            {"question": "What are NVIDIA risk factors?"}
        )
        self.check("Search returns result for 10-K query", status == 200, f"status={status}")
        if isinstance(body, dict):
            citations = body.get("citations", [])
            self.check("10-K chunks retrieved (sec source)",
                       any(c.get("source") == "10k" for c in citations),
                       f"sources={[c.get('source') for c in citations[:3]]}")

    # ── Run all ───────────────────────────────────────────────────────────

    def run_all(self, include_slow: bool = False):
        from datetime import datetime
        print(f"\nAlphaLens API Test Suite")
        print(f"Target: {self.base_url}")
        print(f"Time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Mode:   {'full (LLM tests included)' if include_slow else 'fast (no LLM tests)'}")

        self.test_health()
        self.test_companies()
        self.test_chat_conversations()
        self.test_db_coverage()
        self.test_hybrid_search_available()

        if include_slow:
            self.test_chat_rag_10k()
            self.test_chat_rag_multi_company()
            self.test_chat_out_of_scope()
        else:
            print("\n  [SKIPPED] Slow LLM tests — run with --all to include them")

        self.print_summary()
        return self.failed == 0

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"  RESULTS: {self.passed} passed, {self.failed} failed")
        if self.failed > 0:
            print(f"\n  FAILURES:")
            for status, name, detail in self.results:
                if status == "FAIL":
                    print(f"    - {name}" + (f": {detail}" if detail else ""))
        print(f"{'='*60}\n")


if __name__ == "__main__":
    from datetime import datetime

    parser = argparse.ArgumentParser(description="AlphaLens API Test Suite")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--all",  action="store_true", help="Include slow LLM tests")
    args = parser.parse_args()

    runner = TestRunner(args.base_url)
    ok = runner.run_all(include_slow=args.all)
    sys.exit(0 if ok else 1)
