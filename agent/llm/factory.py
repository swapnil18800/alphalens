"""
LLM factory — provider priority: DeepSeek → Cerebras → OpenAI.

Set LLM_PROVIDER env var to force a specific provider:
  LLM_PROVIDER=deepseek | cerebras | openai | auto (default)
"""
import os
import logging
from typing import Optional

from .base import BaseLLMClient

logger = logging.getLogger(__name__)


_CEREBRAS_BACKOFF_DELAYS = (1.0, 2.0)  # seconds to wait before retry 1, retry 2


class _CerebrasWithFallback(BaseLLMClient):
    """Tries Cerebras with exponential backoff, falls back to OpenAI after exhausted retries."""

    def __init__(self):
        from .cerebras_client import CerebrasClient
        from .openai_client import OpenAIClient
        self._cerebras = CerebrasClient()
        self._openai   = OpenAIClient()

    async def acomplete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        import asyncio
        from .cerebras_client import CerebrasRateLimitError
        for delay in (*_CEREBRAS_BACKOFF_DELAYS, None):
            try:
                return await self._cerebras.acomplete(prompt, system=system, max_tokens=max_tokens)
            except CerebrasRateLimitError:
                if delay is None:
                    break
                logger.info(f"[LLM] Cerebras 429 — retrying in {delay}s")
                await asyncio.sleep(delay)
        return await self._openai.acomplete(prompt, system=system, max_tokens=max_tokens)

    async def astream(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048):
        import asyncio
        from .cerebras_client import CerebrasRateLimitError
        for delay in (*_CEREBRAS_BACKOFF_DELAYS, None):
            try:
                async for token in self._cerebras.astream(prompt, system=system, max_tokens=max_tokens):
                    yield token
                return
            except CerebrasRateLimitError:
                if delay is None:
                    break
                logger.info(f"[LLM] Cerebras 429 stream — retrying in {delay}s")
                await asyncio.sleep(delay)
        async for token in self._openai.astream(prompt, system=system, max_tokens=max_tokens):
            yield token

    def complete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        import time
        from .cerebras_client import CerebrasRateLimitError
        for delay in (*_CEREBRAS_BACKOFF_DELAYS, None):
            try:
                return self._cerebras.complete(prompt, system=system, max_tokens=max_tokens)
            except CerebrasRateLimitError:
                if delay is None:
                    break
                logger.info(f"[LLM] Cerebras 429 sync — retrying in {delay}s")
                time.sleep(delay)
        return self._openai.complete(prompt, system=system, max_tokens=max_tokens)


class LLMFactory:
    @staticmethod
    def create(provider: Optional[str] = None) -> BaseLLMClient:
        """
        Returns the best available LLM client.
        Priority: DeepSeek V3 → Cerebras (fast) → OpenAI fallback.
        """
        chosen = provider or os.getenv("LLM_PROVIDER", "auto")

        if chosen == "deepseek":
            from .deepseek_client import DeepSeekClient
            logger.info("[LLM] Using DeepSeek V3 (forced by LLM_PROVIDER)")
            return DeepSeekClient()

        if chosen == "openai":
            from .openai_client import OpenAIClient
            logger.info("[LLM] Using OpenAI (forced by LLM_PROVIDER)")
            return OpenAIClient()

        if chosen == "cerebras":
            if os.getenv("OPENAI_API_KEY"):
                logger.info("[LLM] Using Cerebras (Qwen-3-235B) + OpenAI fallback on 429")
                return _CerebrasWithFallback()
            from .cerebras_client import CerebrasClient
            logger.info("[LLM] Using Cerebras (Qwen-3-235B)")
            return CerebrasClient()

        # auto: DeepSeek first (no rate-limit issues), then Cerebras, then OpenAI
        if os.getenv("DEEPSEEK_API_KEY"):
            from .deepseek_client import DeepSeekClient
            logger.info("[LLM] Using DeepSeek V3 (deepseek-chat)")
            return DeepSeekClient()

        if os.getenv("CEREBRAS_API_KEY") and os.getenv("OPENAI_API_KEY"):
            logger.info("[LLM] Using Cerebras (Qwen-3-235B) + OpenAI fallback")
            return _CerebrasWithFallback()

        if os.getenv("CEREBRAS_API_KEY"):
            from .cerebras_client import CerebrasClient
            logger.info("[LLM] Using Cerebras (Qwen-3-235B)")
            return CerebrasClient()

        from .openai_client import OpenAIClient
        logger.info("[LLM] Using OpenAI (gpt-4.1-mini)")
        return OpenAIClient()

    @staticmethod
    def create_eval_llm() -> BaseLLMClient:
        """
        Evaluation LLM — needs ~64 tokens output. Respects LLM_PROVIDER; skips
        Cerebras when provider is explicitly set to something else (avoids 429 noise).
        """
        chosen = os.getenv("LLM_PROVIDER", "auto").lower()

        # Only try Cerebras if it's the chosen provider or if in auto mode
        if chosen in ("cerebras", "auto") and os.getenv("CEREBRAS_API_KEY"):
            try:
                from .cerebras_client import CerebrasClient
                return CerebrasClient()
            except Exception:
                pass

        if os.getenv("DEEPSEEK_API_KEY") and chosen in ("deepseek", "auto"):
            try:
                from .deepseek_client import DeepSeekClient
                return DeepSeekClient()
            except Exception:
                pass

        if os.getenv("OPENAI_API_KEY"):
            try:
                from .openai_client import OpenAIClient
                return OpenAIClient()
            except Exception:
                pass

        raise RuntimeError("No LLM available for evaluation")
