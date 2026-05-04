"""OpenAI LLM client — fallback inference."""
import os
from typing import Optional
from .base import BaseLLMClient

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
EVAL_MODEL = "gpt-4o-mini"   # cheaper model for evaluation/analysis tasks


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None, model: str = OPENAI_MODEL):
        import openai
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        self._sync = openai.OpenAI(api_key=key)
        self._async = openai.AsyncOpenAI(api_key=key)
        self.model = model

    async def acomplete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await self._async.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        if resp.usage:
            from .token_tracker import tracker
            tracker.record(self.model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""

    async def astream(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = await self._async.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                from .token_tracker import tracker
                tracker.record(self.model, chunk.usage.prompt_tokens, chunk.usage.completion_tokens)
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
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        if resp.usage:
            from .token_tracker import tracker
            tracker.record(self.model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""
