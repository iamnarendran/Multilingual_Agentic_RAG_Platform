"""LLM client for any OpenAI-compatible chat API (OpenRouter by default)."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import openai
from openai import AsyncOpenAI

from app.config import Settings

logger = logging.getLogger(__name__)

Message = dict[str, str]


class LLMError(Exception):
    """A user-presentable LLM failure (bad key, unknown model, provider down, ...)."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens

    def to_dict(self) -> dict[str, int]:
        return {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        json_mode: bool = False,
        purpose: str = "",
    ) -> tuple[str, Usage]: ...

    def stream(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        purpose: str = "",
        usage: Usage | None = None,
    ) -> AsyncIterator[str]: ...


def _friendly(exc: Exception, model: str) -> LLMError:
    if isinstance(exc, openai.AuthenticationError):
        return LLMError("The LLM provider rejected the API key. Check LLM_API_KEY.")
    if isinstance(exc, openai.NotFoundError):
        return LLMError(f"Model '{model}' was not found at the LLM provider. Check the model name in your settings.")
    if isinstance(exc, openai.RateLimitError):
        return LLMError("The LLM provider is rate-limiting requests. Please wait a moment and try again.")
    if isinstance(exc, openai.APIConnectionError):
        return LLMError("Could not reach the LLM provider. Check your network or LLM_BASE_URL.")
    if isinstance(exc, openai.APIStatusError):
        return LLMError(f"LLM provider error ({exc.status_code}) for model '{model}'.")
    return LLMError(f"LLM call failed: {exc}")


class OpenAICompatibleLLM:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key or "not-configured",
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
            default_headers={"X-Title": settings.app_name},
            http_client=http_client,
        )
        self._no_json_mode: set[str] = set()

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        json_mode: bool = False,
        purpose: str = "",
    ) -> tuple[str, Usage]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode and model not in self._no_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            try:
                resp = await self._client.chat.completions.create(**kwargs)
            except openai.BadRequestError:
                if "response_format" not in kwargs:
                    raise
                # Some models don't support JSON mode; remember and retry without it.
                self._no_json_mode.add(model)
                kwargs.pop("response_format")
                resp = await self._client.chat.completions.create(**kwargs)
        except openai.OpenAIError as exc:
            logger.warning("LLM call (%s, %s) failed: %s", purpose, model, exc)
            raise _friendly(exc, model) from exc

        text = (resp.choices[0].message.content or "") if resp.choices else ""
        usage = Usage(resp.usage.prompt_tokens, resp.usage.completion_tokens) if resp.usage else Usage()
        return text, usage

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        purpose: str = "",
        usage: Usage | None = None,
    ) -> AsyncIterator[str]:
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in response:
                if chunk.usage and usage is not None:
                    usage.add(Usage(chunk.usage.prompt_tokens, chunk.usage.completion_tokens))
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
        except openai.OpenAIError as exc:
            logger.warning("LLM stream (%s, %s) failed: %s", purpose, model, exc)
            raise _friendly(exc, model) from exc


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Leniently parse a JSON object from an LLM reply (handles code fences / extra prose)."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in LLM reply")
    value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM reply is not a JSON object")
    return value
