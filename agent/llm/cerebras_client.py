"""Cerebras LLM client — primary inference (Qwen-3-235B, very fast).

On 429 (queue_exceeded) the SDK retries with up to 60s backoff, which stalls
the whole pipeline. We catch that and raise RateLimitError so the factory can
fall back to OpenAI immediately instead of waiting.
"""
import os
import logging
from typing import Optional
from .base import BaseLLMClient

logger = logging.getLogger(__name__)
CEREBRAS_MODEL = "qwen-3-235b-a22b-instruct-2507"


class CerebrasRateLimitError(Exception):
    """Raised when Cerebras returns 429 so the factory can fall back."""


class CerebrasClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None):
        from cerebras.cloud.sdk import Cerebras, AsyncCerebras
        key = api_key or os.getenv("CEREBRAS_API_KEY")
        if not key:
            raise ValueError("CEREBRAS_API_KEY not set")
        # max_retries=0 → do not auto-retry 429; we handle fallback ourselves
        self._sync  = Cerebras(api_key=key, max_retries=0)
        self._async = AsyncCerebras(api_key=key, max_retries=0)

    async def acomplete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = await self._async.chat.completions.create(
                model=CEREBRAS_MODEL,
                messages=messages,
                max_completion_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if "429" in str(e) or "queue_exceeded" in str(e) or "too_many_requests" in str(e):
                logger.warning("[LLM] Cerebras 429 — falling back to OpenAI")
                raise CerebrasRateLimitError(str(e)) from e
            raise

    async def astream(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            stream = await self._async.chat.completions.create(
                model=CEREBRAS_MODEL,
                messages=messages,
                max_completion_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as e:
            if "429" in str(e) or "queue_exceeded" in str(e) or "too_many_requests" in str(e):
                logger.warning("[LLM] Cerebras 429 stream — falling back")
                raise CerebrasRateLimitError(str(e)) from e
            raise

    def complete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = self._sync.chat.completions.create(
                model=CEREBRAS_MODEL,
                messages=messages,
                max_completion_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if "429" in str(e) or "queue_exceeded" in str(e) or "too_many_requests" in str(e):
                raise CerebrasRateLimitError(str(e)) from e
            raise
