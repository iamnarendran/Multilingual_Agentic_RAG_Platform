"""The real OpenAI-compatible client, against an emulated OpenRouter-style HTTP API."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents.llm import LLMError, OpenAICompatibleLLM, Usage, parse_json_object
from app.config import Settings


def _client(settings: Settings, handler) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(settings, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _completion(content: str) -> dict:
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
    }


async def test_complete_uses_json_mode_and_reports_usage(settings: Settings):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json=_completion('{"intent": "documents"}'))

    text, usage = await _client(settings, handler).complete(
        [{"role": "user", "content": "hi"}], model="openai/gpt-oss-20b", json_mode=True
    )
    assert parse_json_object(text) == {"intent": "documents"}
    assert usage == Usage(12, 3)
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert seen[0]["model"] == "openai/gpt-oss-20b"


async def test_falls_back_when_model_rejects_json_mode(settings: Settings):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
        return httpx.Response(200, json=_completion('```json\n{"ok": true}\n```'))

    llm = _client(settings, handler)
    text, _ = await llm.complete([{"role": "user", "content": "x"}], model="some/model", json_mode=True)
    assert parse_json_object(text) == {"ok": True}
    await llm.complete([{"role": "user", "content": "x"}], model="some/model", json_mode=True)
    assert calls == [True, False, False]  # remembered: no JSON mode for this model


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "API key"), (404, "was not found"), (402, "LLM provider error (402)")],
)
async def test_errors_become_friendly_llm_errors(settings: Settings, status: int, message: str):
    llm = _client(settings, lambda r: httpx.Response(status, json={"error": {"message": "nope"}}))
    with pytest.raises(LLMError, match=message.replace("(", r"\(").replace(")", r"\)")):
        await llm.complete([{"role": "user", "content": "x"}], model="m")


async def test_stream_yields_tokens_and_usage(settings: Settings):
    def chunk(delta: dict | None, usage: dict | None = None) -> str:
        payload = {
            "id": "gen-2",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "m",
            "choices": [] if delta is None else [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        if usage:
            payload["usage"] = usage
        return f"data: {json.dumps(payload)}\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
        sse = (
            chunk({"role": "assistant", "content": ""})
            + chunk({"content": "नमस्ते"})
            + chunk({"content": " दुनिया"})
            + chunk(None, {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9})
            + "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})

    usage = Usage()
    tokens = [
        t async for t in _client(settings, handler).stream([{"role": "user", "content": "x"}], model="m", usage=usage)
    ]
    assert tokens == ["नमस्ते", " दुनिया"]
    assert usage == Usage(7, 2)


def test_parse_json_object_is_lenient_but_strict_about_shape():
    assert parse_json_object('Sure! {"a": 1} hope that helps') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json_object("no json here")
    with pytest.raises(ValueError):
        parse_json_object('["a list"]')
