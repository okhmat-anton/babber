"""
Anthropic (Claude) LLM provider.

Uses the official anthropic Python SDK for Messages API.
"""
import asyncio
import logging
import anthropic
from typing import AsyncIterator
from app.llm.base import LLMProvider, Message, GenerationParams, LLMResponse, ModelInfo

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]  # seconds between retries


# Well-known Anthropic models
ANTHROPIC_MODELS = [
    {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4", "context": 200000},
    {"id": "claude-opus-4-6", "name": "Claude Opus 4", "context": 200000},
    {"id": "claude-3-7-sonnet-latest", "name": "Claude 3.7 Sonnet", "context": 200000},
    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet v2", "context": 200000},
    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "context": 200000},
    {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "context": 200000},
    {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku", "context": 200000},
]


class AnthropicProvider:
    """Provider for Anthropic Claude models via the official SDK."""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = anthropic.Anthropic(api_key=api_key, base_url=self.base_url)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key, base_url=self.base_url)

    def _prepare_messages(self, messages: list[Message]) -> tuple[str | None, list[dict]]:
        """Split system messages from user/assistant messages.

        Anthropic requires:
        - system as a top-level param (not in messages array)
        - messages must alternate user/assistant, starting with user
        """
        system_parts = []
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                api_messages.append({"role": m.role, "content": m.content})

        system_text = "\n\n".join(system_parts) if system_parts else None

        # Merge consecutive same-role messages (Anthropic requires alternation)
        merged = []
        for msg in api_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n\n" + msg["content"]
            else:
                merged.append(dict(msg))

        # Ensure first message is user role
        if not merged or merged[0]["role"] != "user":
            merged.insert(0, {"role": "user", "content": "Hello"})

        return system_text, merged

    async def chat(self, model: str, messages: list[Message], params: GenerationParams) -> LLMResponse:
        system_text, api_messages = self._prepare_messages(messages)

        kwargs = {
            "model": model,
            "messages": api_messages,
            "max_tokens": params.max_tokens or 4096,
        }
        if system_text:
            kwargs["system"] = system_text
        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        if params.stop:
            kwargs["stop_sequences"] = params.stop

        # Retry on transient errors (overloaded, rate limit, server errors)
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                # Use streaming internally to avoid Anthropic 10-minute timeout
                async with self._async_client.messages.stream(**kwargs) as stream:
                    response = await stream.get_final_message()

                content = ""
                for block in response.content:
                    if block.type == "text":
                        content += block.text

                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens

                return LLMResponse(
                    content=content,
                    model=response.model,
                    total_tokens=input_tokens + output_tokens,
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                )
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                last_error = e
                is_retryable = isinstance(e, anthropic.APIConnectionError) or (
                    hasattr(e, 'status_code') and e.status_code in (429, 500, 502, 503, 529)
                )
                if is_retryable and attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    logger.warning("Anthropic chat error (attempt %d/%d), retrying in %ds: %s", attempt + 1, MAX_RETRIES, delay, e)
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_error

    async def stream(self, model: str, messages: list[Message], params: GenerationParams) -> AsyncIterator[str]:
        system_text, api_messages = self._prepare_messages(messages)

        stream_kwargs = {
            "model": model,
            "messages": api_messages,
            "max_tokens": params.max_tokens or 4096,
            "system": system_text or anthropic.NOT_GIVEN,
            "temperature": params.temperature if params.temperature is not None else anthropic.NOT_GIVEN,
            "stop_sequences": params.stop if params.stop else anthropic.NOT_GIVEN,
        }

        # Retry on transient errors (overloaded, rate limit, server errors)
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with self._async_client.messages.stream(**stream_kwargs) as stream:
                    async for text in stream.text_stream:
                        yield text
                return  # Success - exit retry loop
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                last_error = e
                is_retryable = isinstance(e, anthropic.APIConnectionError) or (
                    hasattr(e, 'status_code') and e.status_code in (429, 500, 502, 503, 529)
                )
                if is_retryable and attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    logger.warning("Anthropic stream error (attempt %d/%d), retrying in %ds: %s", attempt + 1, MAX_RETRIES, delay, e)
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_error

    async def list_models(self) -> list[ModelInfo]:
        """Return well-known Anthropic models."""
        return [ModelInfo(name=m["id"]) for m in ANTHROPIC_MODELS]

    async def check_connection(self) -> bool:
        """Test connection by sending a minimal request."""
        try:
            response = await self._async_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True
        except Exception:
            return False

    async def embeddings(self, text: str, model: str = "") -> list[float]:
        """Anthropic doesn't support embeddings natively."""
        raise NotImplementedError("Anthropic does not provide an embeddings API")
