"""DeepSeek LLM client — primary inference (DeepSeek V3, OpenAI-compatible API).

DeepSeek's API is a drop-in OpenAI-compatible endpoint; no new SDK required.
Model: deepseek-chat (maps to DeepSeek V3, 236B MoE, MIT licensed).
Cost: ~$0.14/M input tokens — ~10x cheaper than GPT-4o with comparable quality.
"""
import os
import logging
from typing import Optional
from .base import BaseLLMClient

logger = logging.getLogger(__name__)

DEEPSEEK_MODEL   = "deepseek-chat"   # DeepSeek V3
DEEPSEEK_API_URL = "https://api.deepseek.com"


class DeepSeekClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None):
        import openai
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set")
        self._sync  = openai.OpenAI(api_key=key, base_url=DEEPSEEK_API_URL)
        self._async = openai.AsyncOpenAI(api_key=key, base_url=DEEPSEEK_API_URL)

    async def acomplete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await self._async.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            max_tokens=max_tokens,
        )
        if resp.usage:
            from .token_tracker import tracker
            tracker.record(DEEPSEEK_MODEL, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""

    async def astream(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = await self._async.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                from .token_tracker import tracker
                tracker.record(DEEPSEEK_MODEL, chunk.usage.prompt_tokens, chunk.usage.completion_tokens)
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

    def complete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._sync.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            max_tokens=max_tokens,
        )
        if resp.usage:
            from .token_tracker import tracker
            tracker.record(DEEPSEEK_MODEL, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""
