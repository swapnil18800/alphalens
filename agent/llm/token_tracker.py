"""Thread-safe token usage tracker — singleton shared across all LLM clients."""
import threading

# USD per million tokens (input / output)
_PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat":  {"input": 0.14,  "output": 0.28},
    "gpt-4.1-mini":   {"input": 0.40,  "output": 1.60},
    "gpt-4.1":        {"input": 2.00,  "output": 8.00},
    "gpt-4o":         {"input": 5.00,  "output": 15.00},
    "gpt-4o-mini":    {"input": 0.15,  "output": 0.60},
}
_DEFAULT_PRICING = {"input": 1.00, "output": 3.00}


def _usd(model: str, inp: int, out: int) -> float:
    p = _PRICING.get(model, _DEFAULT_PRICING)
    return (inp * p["input"] + out * p["output"]) / 1_000_000


class _TokenTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: list[dict] = []

    def reset(self) -> None:
        with self._lock:
            self._calls = []

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        cost = _usd(model, input_tokens, output_tokens)
        with self._lock:
            self._calls.append({
                "model":         model,
                "input_tokens":  input_tokens,
                "output_tokens": output_tokens,
                "cost_usd":      round(cost, 7),
            })

    def snapshot(self) -> dict:
        with self._lock:
            calls = list(self._calls)
        inp  = sum(c["input_tokens"]  for c in calls)
        out  = sum(c["output_tokens"] for c in calls)
        cost = round(sum(c["cost_usd"] for c in calls), 6)
        return {
            "calls":               calls,
            "total_input_tokens":  inp,
            "total_output_tokens": out,
            "total_tokens":        inp + out,
            "total_cost_usd":      cost,
        }


tracker = _TokenTracker()
