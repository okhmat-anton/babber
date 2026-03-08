import asyncio
import logging
import httpx
from typing import AsyncIterator
from app.llm.base import LLMProvider, Message, GenerationParams, LLMResponse, ModelInfo
import json

logger = logging.getLogger(__name__)

# Global semaphore: Ollama processes requests sequentially, so sending
# multiple concurrent requests only builds a queue.  A semaphore of 1
# serialises our calls, prevents cascading timeouts (where Ollama is
# still processing a previous timed-out request) and keeps the behaviour
# predictable.  The value can be increased when running Ollama with
# OLLAMA_NUM_PARALLEL > 1.
_ollama_semaphore = asyncio.Semaphore(1)


class OllamaProvider:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    async def chat(self, model: str, messages: list[Message], params: GenerationParams) -> LLMResponse:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": params.temperature,
                "top_p": params.top_p,
                "top_k": params.top_k,
                "num_ctx": params.num_ctx,
                "repeat_penalty": params.repeat_penalty,
                "num_predict": params.num_predict,
                "num_thread": params.num_thread,
                "num_gpu": params.num_gpu,
            },
        }
        if params.stop:
            payload["options"]["stop"] = params.stop

        async with _ollama_semaphore:
            logger.debug(f"Ollama chat: model={model}, messages={len(messages)}")
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            model=model,
            total_tokens=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    async def stream(self, model: str, messages: list[Message], params: GenerationParams) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {
                "temperature": params.temperature,
                "top_p": params.top_p,
                "top_k": params.top_k,
                "num_ctx": params.num_ctx,
                "repeat_penalty": params.repeat_penalty,
                "num_predict": params.num_predict,
                "num_thread": params.num_thread,
                "num_gpu": params.num_gpu,
            },
        }
        if params.stop:
            payload["options"]["stop"] = params.stop

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()

        return [
            ModelInfo(
                name=m["name"],
                size=m.get("size", 0),
                modified_at=m.get("modified_at", ""),
            )
            for m in data.get("models", [])
        ]

    async def check_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def embeddings(self, text: str, model: str = "nomic-embed-text") -> list[float]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json().get("embedding", [])
