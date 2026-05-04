"""Abstract base for all LLM clients."""
from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator


class BaseLLMClient(ABC):
    @abstractmethod
    async def acomplete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        """Async completion — returns the response string."""
        ...

    @abstractmethod
    def complete(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> str:
        """Sync completion — returns the response string."""
        ...

    async def astream(self, prompt: str, system: Optional[str] = None, max_tokens: int = 2048) -> AsyncIterator[str]:
        """Async streaming — yields tokens. Default: complete then yield all at once."""
        result = await self.acomplete(prompt, system=system, max_tokens=max_tokens)
        yield result
