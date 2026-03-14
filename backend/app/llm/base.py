from typing import Protocol, AsyncIterator
from dataclasses import dataclass


@dataclass
class Message:
    role: str  # system, user, assistant
    content: str


@dataclass
class GenerationParams:
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 32768
    num_ctx: int = 32768
    repeat_penalty: float = 1.1
    num_predict: int = -1
    stop: list[str] | None = None
    num_thread: int = 8
    num_gpu: int = 1


@dataclass
class LLMResponse:
    content: str
    model: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ModelInfo:
    name: str
    size: int = 0
    modified_at: str = ""


class LLMProvider(Protocol):
    async def chat(self, model: str, messages: list[Message], params: GenerationParams) -> LLMResponse: ...
    async def stream(self, model: str, messages: list[Message], params: GenerationParams) -> AsyncIterator[str]: ...
    async def list_models(self) -> list[ModelInfo]: ...
    async def check_connection(self) -> bool: ...
    async def embeddings(self, text: str, model: str) -> list[float]: ...
