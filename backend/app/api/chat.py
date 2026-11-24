"""Streaming chat endpoint (Server-Sent Events).

Event types sent to the client, in order:
  start       {conversation_id, user_message_id, title, created}
  meta        {language, language_name} / {intent, query_type}
  step        {agent, label, status: running|done|error, summary?, data?, ms?, usage?}
  sources     {sources: [...]}
  token       {text}
  validation  {validation: {grounded, score, issues}}
  error       {message}
  done        {message_id, status, usage, latency_ms}
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import anyio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.agents.graph import AgentState, run_agents
from app.agents.llm import LLMError
from app.api.conversations import get_owned_conversation
from app.api.deps import CurrentUser, DbDep, ServicesDep
from app.db import Conversation, Document, Message
from app.schemas import ChatRequest
from app.services import Services

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _title_from(message: str, limit: int = 60) -> str:
    text = " ".join(message.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]) + "…"


async def _history(session: DbDep, conversation_id: str, before_id: str, turns: int) -> list[dict[str, str]]:
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.id != before_id, Message.content != "")
        .order_by(Message.created_at.desc())
        .limit(turns * 2)
    )
    return [{"role": m.role, "content": m.content[:4000]} for m in reversed(list(rows))]


@router.post("/chat")
async def chat(body: ChatRequest, user: CurrentUser, session: DbDep, services: ServicesDep) -> StreamingResponse:
    settings = services.settings
    created = body.conversation_id is None
    if body.conversation_id:
        conv = await get_owned_conversation(session, user.id, body.conversation_id)
    else:
        conv = Conversation(user_id=user.id, title=_title_from(body.message))
        session.add(conv)

    user_msg = Message(conversation=conv, role="user", content=body.message)
    session.add(user_msg)
    conv.updated_at = datetime.now(UTC)
    await session.commit()

    history = await _history(session, conv.id, user_msg.id, settings.history_turns)
    doc_query = select(Document.language).where(Document.user_id == user.id, Document.status == "ready")
    if body.document_ids:
        doc_query = doc_query.where(Document.id.in_(body.document_ids))
    languages = [lang for lang in await session.scalars(doc_query)]

    state: AgentState = {
        "question": body.message,
        "history": history,
        "user_id": user.id,
        "document_ids": body.document_ids or None,
        "corpus_languages": sorted({lang for lang in languages if lang}),
        "has_documents": bool(languages),
    }
    conversation_id, user_message_id, title = conv.id, user_msg.id, conv.title

    async def stream():
        started = time.perf_counter()
        answer_parts: list[str] = []
        trace: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        validation: dict[str, Any] | None = None
        meta: dict[str, Any] = {}
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        outcome = {"status": "complete", "message_id": None}

        yield _sse(
            "start",
            {
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "title": title,
                "created": created,
            },
        )
        try:
            if not settings.llm_configured:
                raise LLMError("No LLM is configured on the server. Set LLM_API_KEY in the backend .env file.")
            async for event in run_agents(services.graph, state):
                kind = event.get("type")
                if kind == "final":
                    continue
                if kind == "token":
                    answer_parts.append(event["text"])
                elif kind == "step" and event.get("status") in ("done", "error"):
                    trace.append({k: v for k, v in event.items() if k != "type"})
                    for key in usage:
                        usage[key] += (event.get("usage") or {}).get(key, 0)
                elif kind == "sources":
                    sources = event["sources"]
                elif kind == "validation":
                    validation = event["validation"]
                elif kind == "meta":
                    meta.update({k: v for k, v in event.items() if k != "type"})
                yield _sse(kind, {k: v for k, v in event.items() if k != "type"})
        except asyncio.CancelledError:
            outcome["status"] = "stopped"  # client disconnected / pressed stop
            raise
        except LLMError as exc:
            outcome["status"] = "error"
            yield _sse("error", {"message": str(exc)})
        except Exception:
            logger.exception("Chat pipeline failed")
            outcome["status"] = "error"
            yield _sse("error", {"message": "Something went wrong while answering. Please try again."})
        finally:
            with anyio.CancelScope(shield=True):
                outcome["message_id"] = await _save_assistant_message(
                    services,
                    conversation_id,
                    content="".join(answer_parts).strip(),
                    status=outcome["status"],
                    meta=meta,
                    sources=sources,
                    trace=trace,
                    validation=validation,
                    usage={**usage, "latency_ms": int((time.perf_counter() - started) * 1000)},
                )

        yield _sse(
            "done",
            {
                "message_id": outcome["message_id"],
                "status": outcome["status"],
                "usage": usage,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            },
        )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _save_assistant_message(
    services: Services,
    conversation_id: str,
    *,
    content: str,
    status: str,
    meta: dict[str, Any],
    sources: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    validation: dict[str, Any] | None,
    usage: dict[str, Any],
) -> str | None:
    try:
        async with services.sessionmaker() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is None:  # conversation deleted while answering
                return None
            msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                status=status,
                language=meta.get("language"),
                query_type=meta.get("query_type"),
                sources=sources or None,
                trace=trace or None,
                validation=validation,
                usage=usage,
            )
            session.add(msg)
            conv.updated_at = datetime.now(UTC)
            await session.commit()
            return msg.id
    except Exception:  # noqa: BLE001 - never let persistence errors break the stream
        logger.exception("Failed to save assistant message")
        return None
