"""
Anthropic (Claude) LLM provider.

Uses the Anthropic Messages API: POST /v1/messages
Auth via x-api-key header + anthropic-version header.
"""
import httpx
import json
from typing import AsyncIterator
from app.llm.base import LLMProvider, Message, GenerationParams, LLMResponse, ModelInfo


# Well-known Anthropic models
ANTHROPIC_MODELS = [
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "context": 200000},
    {"id": "claude-opus-4-20250514", "name": "Claude Opus 4", "context": 200000},
    {"id": "claude-3-7-sonnet-20250219", "name": "Claude 3.7 Sonnet", "context": 200000},
    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet v2", "context": 200000},
    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "context": 200000},
    {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "context": 200000},
    {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku", "context": 200000},
]

ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicProvider:
    """Provider for Anthropic Claude models via the Messages API."""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }

    def _prepare_messages(self, messages: list[Message]) -> tuple[str | None, list[dict]]:
        """Split system message from user/assistant messages (Anthropic format)."""
        system_text = None
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_text = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})
        # Anthropic requires at least one user message
        if not api_messages:
            api_messages.append({"role": "user", "content": "Hello"})
        return system_text, api_messages

    async def chat(self, model: str, messages: list[Message], params: GenerationParams) -> LLMResponse:
        system_text, api_messages = self._prepare_messages(messages)

        payload = {
            "model": model,
            "messages": api_messages,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
        }
        if system_text:
            payload["system"] = system_text
        if params.stop:
            payload["stop_sequences"] = params.stop

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract content from response
        content_blocks = data.get("content", [])
        content = ""
        for block in content_blocks:
            if block.get("type") == "text":
                content += block.get("text", "")

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        return LLMResponse(
            content=content,
            model=data.get("model", model),
            total_tokens=input_tokens + output_tokens,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )

    async def stream(self, model: str, messages: list[Message], params: GenerationParams) -> AsyncIterator[str]:
        system_text, api_messages = self._prepare_messages(messages)

        payload = {
            "model": model,
            "messages": api_messages,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text
        if params.stop:
            payload["stop_sequences"] = params.stop

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                json=payload,
                headers=self._headers(),
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        try:
                            data = json.loads(chunk)
                            event_type = data.get("type", "")
                            if event_type == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        yield text
                        except json.JSONDecodeError:
                            continue

    async def list_models(self) -> list[ModelInfo]:
        """Return well-known Anthropic models (API doesn't provide a list endpoint)."""
        return [
            ModelInfo(name=m["id"])
            for m in ANTHROPIC_MODELS
        ]

    async def check_connection(self) -> bool:
        """Test connection by sending a minimal request."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages",
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                    headers=self._headers(),
                )
                # 200 = OK, 401 = bad key, anything else = at least reachable
                return resp.status_code == 200
        except Exception:
            return False

    async def embeddings(self, text: str, model: str = "") -> list[float]:
        """Anthropic doesn't support embeddings natively."""
        raise NotImplementedError("Anthropic does not provide an embeddings API")
