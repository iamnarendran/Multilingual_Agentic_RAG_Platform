"""The agent pipeline, built as a LangGraph state machine.

    language ─► router ─┬─ chitchat ───────────────────────────────► generator ─► END
                        └─ documents ─► planner ─► retriever ─► grader ─┬─► generator ─┬─► validator ─► END
                                           ▲                            │              └─► END (no sources)
                                           └──── retry (nothing relevant found) ◄──┘

Every node reports progress through LangGraph's custom stream ("step" events), so the UI can
show the agents working live. The generator streams answer tokens the same way.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.agents import prompts
from app.agents.llm import LLMError, Usage, parse_json_object
from app.rag.language import detect_language, language_name
from app.rag.sparse import encode_query
from app.services import Services

logger = logging.getLogger(__name__)

RRF_K = 60


class AgentState(TypedDict, total=False):
    # inputs
    question: str
    history: list[dict[str, str]]
    user_id: str
    document_ids: list[str] | None
    corpus_languages: list[str]
    has_documents: bool
    # language + router
    language: str
    language_name: str
    intent: str
    query_type: str
    standalone_question: str
    # planner / retriever / grader
    search_queries: list[str]
    previous_queries: list[str]
    attempts: int
    candidates: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    feedback: str
    retry: bool
    # outputs
    answer: str
    validation: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Step reporting helper
# ---------------------------------------------------------------------------


@dataclass
class StepReport:
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)


def _emit(event: dict[str, Any]) -> None:
    get_stream_writer()(event)


@asynccontextmanager
async def _step(agent: str, label: str) -> AsyncIterator[StepReport]:
    report = StepReport()
    started = time.perf_counter()
    _emit({"type": "step", "agent": agent, "label": label, "status": "running"})
    try:
        yield report
    except Exception as exc:
        _emit(
            {
                "type": "step",
                "agent": agent,
                "label": label,
                "status": "error",
                "summary": str(exc),
                "ms": int((time.perf_counter() - started) * 1000),
            }
        )
        raise
    _emit(
        {
            "type": "step",
            "agent": agent,
            "label": label,
            "status": "done",
            "summary": report.summary,
            "data": report.data,
            "ms": int((time.perf_counter() - started) * 1000),
            "usage": report.usage.to_dict(),
        }
    )


def _public_source(src: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "index": index,
        "document_id": src["document_id"],
        "filename": src["filename"],
        "page": src.get("page"),
        "page_end": src.get("page_end"),
        "text": src["text"],
        "score": src.get("score"),
        "language": src.get("language"),
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_graph(services: Services):
    settings = services.settings
    llm = services.llm

    async def language_node(state: AgentState) -> AgentState:
        async with _step("language", "Detecting language") as step:
            detected = detect_language(state["question"])
            step.summary = f"{detected.name} ({detected.script} script)"
            step.data = {"code": detected.code, "confidence": detected.confidence}
        _emit({"type": "meta", "language": detected.code, "language_name": detected.name})
        return {"language": detected.code, "language_name": detected.name}

    async def router_node(state: AgentState) -> AgentState:
        async with _step("router", "Understanding the question") as step:
            history = prompts.format_history(state.get("history", []))
            intent, query_type, standalone = "documents", "SIMPLE_QA", state["question"]
            try:
                text, usage = await llm.complete(
                    [
                        {"role": "system", "content": prompts.ROUTER_SYSTEM},
                        {
                            "role": "user",
                            "content": f"Conversation so far:\n{history}\n\nLatest message: {state['question']}",
                        },
                    ],
                    model=settings.model_for("router"),
                    temperature=0.0,
                    max_tokens=700,
                    json_mode=True,
                    purpose="router",
                )
                step.usage.add(usage)
                parsed = parse_json_object(text)
                intent = "chitchat" if parsed.get("intent") == "chitchat" else "documents"
                qt = str(parsed.get("query_type", "")).upper()
                query_type = qt if qt in prompts.QUERY_TYPES else "SIMPLE_QA"
                standalone = str(parsed.get("standalone_question") or "").strip() or state["question"]
            except ValueError as exc:  # unparsable reply: keep safe defaults (LLMError propagates)
                logger.info("Router reply unparsable (%s); using defaults", exc)
            step.summary = (
                "Small talk, no search needed" if intent == "chitchat" else prompts.QUERY_TYPE_LABELS[query_type]
            )
            step.data = {
                "intent": intent,
                "query_type": query_type,
                "standalone_question": standalone,
                "rewritten": standalone.strip() != state["question"].strip(),
            }
        _emit({"type": "meta", "intent": intent, "query_type": query_type})
        return {"intent": intent, "query_type": query_type, "standalone_question": standalone, "attempts": 0}

    async def planner_node(state: AgentState) -> AgentState:
        attempt = state.get("attempts", 0) + 1
        label = "Planning searches" if attempt == 1 else "Re-planning searches"
        async with _step("planner", label) as step:
            question = state["standalone_question"]
            corpus = ", ".join(language_name(c) for c in state.get("corpus_languages", [])) or "unknown"
            n = 3 if state.get("query_type") in ("SIMPLE_QA", "EXTRACTION") else 4
            user = f"Question ({state['language_name']}): {question}\nQuery type: {state['query_type']}"
            if attempt > 1:
                user += (
                    f"\n\nA previous search with these queries found nothing relevant: {state.get('previous_queries', [])}."
                    f"\nGrader feedback: {state.get('feedback') or 'none'}"
                    "\nUse different wording: synonyms, broader terms, or translations."
                )
            queries: list[str] = []
            try:
                text, usage = await llm.complete(
                    [
                        {
                            "role": "system",
                            "content": prompts.PLANNER_SYSTEM.format(
                                n=n, corpus_languages=corpus, language_name=state["language_name"]
                            ),
                        },
                        {"role": "user", "content": user},
                    ],
                    model=settings.model_for("planner"),
                    temperature=0.4 if attempt > 1 else 0.2,
                    max_tokens=700,
                    json_mode=True,
                    purpose="planner",
                )
                step.usage.add(usage)
                raw = parse_json_object(text).get("queries", [])
                queries = [q.strip() for q in raw if isinstance(q, str) and q.strip()]
            except ValueError as exc:
                logger.info("Planner reply unparsable (%s); falling back to the question", exc)
            if attempt == 1 and question not in queries:
                queries.insert(0, question)  # always search the question itself first
            queries = list(dict.fromkeys(queries))[: n + 1] or [question]
            step.summary = f"{len(queries)} search queries"
            step.data = {"queries": queries, "attempt": attempt}
        return {
            "search_queries": queries,
            "previous_queries": state.get("previous_queries", []) + queries,
            "attempts": attempt,
        }

    async def retriever_node(state: AgentState) -> AgentState:
        async with _step("retriever", "Searching your documents") as step:
            if not state.get("has_documents"):
                step.summary = "No documents uploaded yet"
                return {"candidates": []}
            queries = state["search_queries"]
            dense_vectors = await services.embedder.embed_queries(queries)
            results = await asyncio.gather(
                *[
                    services.vector_store.hybrid_search(
                        user_id=state["user_id"],
                        dense=dense,
                        sparse=encode_query(q),
                        limit=settings.retrieval_candidates_per_query,
                        document_ids=state.get("document_ids"),
                    )
                    for q, dense in zip(queries, dense_vectors, strict=True)
                ]
            )
            # Reciprocal Rank Fusion across all queries
            fused: dict[str, float] = defaultdict(float)
            hits_by_id = {}
            for hits in results:
                for rank, hit in enumerate(hits, start=1):
                    fused[hit.id] += 1.0 / (RRF_K + rank)
                    hits_by_id.setdefault(hit.id, hit)
            ranked = sorted(hits_by_id.values(), key=lambda h: fused[h.id], reverse=True)
            candidates = [{**h.to_dict(), "score": round(fused[h.id], 5)} for h in ranked[: settings.grader_candidates]]
            files = sorted({c["filename"] for c in candidates})
            step.summary = f"{len(candidates)} passages from {len(files)} document{'s' if len(files) != 1 else ''}"
            step.data = {"queries": len(queries), "unique_hits": len(hits_by_id), "files": files}
        return {"candidates": candidates}

    async def grader_node(state: AgentState) -> AgentState:
        async with _step("grader", "Checking relevance") as step:
            candidates = state.get("candidates", [])
            can_retry = state.get("has_documents", False) and state.get("attempts", 1) < settings.max_retrieval_attempts
            if not candidates:
                step.summary = "Nothing found, trying again" if can_retry else "Nothing relevant found"
                return {"sources": [], "retry": can_retry, "feedback": "no passages matched"}

            relevant_idx: list[int] = []
            feedback = ""
            try:
                text, usage = await llm.complete(
                    [
                        {"role": "system", "content": prompts.GRADER_SYSTEM},
                        {
                            "role": "user",
                            "content": f"Question: {state['standalone_question']}\n\nPassages:\n{prompts.format_sources(candidates, max_chars=700)}",
                        },
                    ],
                    model=settings.model_for("grader"),
                    temperature=0.0,
                    max_tokens=700,
                    json_mode=True,
                    purpose="grader",
                )
                step.usage.add(usage)
                parsed = parse_json_object(text)
                for value in parsed.get("relevant", []):
                    try:
                        i = int(value)
                    except (TypeError, ValueError):
                        continue
                    if 1 <= i <= len(candidates) and i not in relevant_idx:
                        relevant_idx.append(i)
                feedback = str(parsed.get("feedback") or "")
                sources = [candidates[i - 1] for i in relevant_idx][: settings.top_k_sources]
            except ValueError:
                # Grader unusable: fall back to the top retrieval results rather than failing
                sources = candidates[: settings.top_k_sources]
                feedback = "grader unavailable"

            retry = not sources and can_retry
            if sources:
                step.summary = f"{len(sources)} of {len(candidates)} passages are relevant"
            else:
                step.summary = "None relevant, re-planning" if retry else "None of the passages answer this"
            step.data = {"relevant": relevant_idx, "kept": len(sources), "feedback": feedback}
        return {"sources": sources, "retry": retry, "feedback": feedback}

    async def generator_node(state: AgentState) -> AgentState:
        sources = state.get("sources", [])
        public = [_public_source(s, i) for i, s in enumerate(sources, start=1)]
        if public:
            _emit({"type": "sources", "sources": public})
        async with _step("generator", "Writing the answer") as step:
            lang = state.get("language_name", "English")
            if state.get("intent") == "chitchat":
                system = prompts.GENERATOR_CHITCHAT_SYSTEM.format(language_name=lang)
            elif sources:
                system = prompts.GENERATOR_RAG_SYSTEM.format(
                    language_name=lang,
                    query_type=state.get("query_type", "SIMPLE_QA"),
                    sources=prompts.format_sources(sources),
                )
            else:
                situation = (
                    "The user has not uploaded any documents yet."
                    if not state.get("has_documents")
                    else "A search of the user's documents found nothing relevant to this question."
                )
                system = prompts.GENERATOR_NO_SOURCES_SYSTEM.format(situation=situation, language_name=lang)

            messages = [{"role": "system", "content": system}]
            messages += [{"role": m["role"], "content": m["content"]} for m in state.get("history", [])]
            messages.append({"role": "user", "content": state["question"]})

            parts: list[str] = []
            async for token in llm.stream(
                messages,
                model=settings.model_for("generator"),
                temperature=0.3,
                max_tokens=2500,
                purpose="generator",
                usage=step.usage,
            ):
                parts.append(token)
                _emit({"type": "token", "text": token})
            answer = "".join(parts).strip()
            step.summary = f"{len(answer.split())} words" + (f", {len(sources)} sources" if sources else "")
        return {"answer": answer}

    async def validator_node(state: AgentState) -> AgentState:
        async with _step("validator", "Verifying against sources") as step:
            validation: dict[str, Any]
            try:
                text, usage = await llm.complete(
                    [
                        {"role": "system", "content": prompts.VALIDATOR_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"Question: {state['question']}\n\nAnswer:\n{state['answer']}\n\n"
                                f"Sources:\n{prompts.format_sources(state['sources'], max_chars=1200)}"
                            ),
                        },
                    ],
                    model=settings.model_for("validator"),
                    temperature=0.0,
                    max_tokens=800,
                    json_mode=True,
                    purpose="validator",
                )
                step.usage.add(usage)
                parsed = parse_json_object(text)
                score = parsed.get("score")
                score = max(0.0, min(1.0, float(score))) if isinstance(score, (int, float)) else None
                issues = [str(i) for i in parsed.get("issues", []) if str(i).strip()][:5]
                grounded = bool(parsed.get("grounded", not issues))
                validation = {"grounded": grounded, "score": score, "issues": issues}
                step.summary = "All claims supported" if grounded and not issues else f"{len(issues)} possible issue(s)"
            except (LLMError, ValueError) as exc:
                # Never block the answer on the validator, but don't pretend it passed either.
                validation = {"grounded": None, "score": None, "issues": [], "error": str(exc)}
                step.summary = "Could not verify"
            step.data = validation
        _emit({"type": "validation", "validation": validation})
        return {"validation": validation}

    def after_router(state: AgentState) -> str:
        return "generator" if state.get("intent") == "chitchat" else "planner"

    def after_grader(state: AgentState) -> str:
        return "planner" if state.get("retry") else "generator"

    def after_generator(state: AgentState) -> str:
        if settings.validation_enabled and state.get("sources") and state.get("answer"):
            return "validator"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("language", language_node)
    graph.add_node("router", router_node)
    graph.add_node("planner", planner_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("grader", grader_node)
    graph.add_node("generator", generator_node)
    graph.add_node("validator", validator_node)

    graph.add_edge(START, "language")
    graph.add_edge("language", "router")
    graph.add_conditional_edges("router", after_router, {"planner": "planner", "generator": "generator"})
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "grader")
    graph.add_conditional_edges("grader", after_grader, {"planner": "planner", "generator": "generator"})
    graph.add_conditional_edges("generator", after_generator, {"validator": "validator", END: END})
    graph.add_edge("validator", END)
    return graph.compile()


async def run_agents(graph, state: AgentState) -> AsyncIterator[dict[str, Any]]:
    """Run the graph, yielding UI events; the last event is {"type": "final", "state": ...}."""
    final: dict[str, Any] = dict(state)
    async for mode, payload in graph.astream(state, stream_mode=["custom", "values"]):
        if mode == "custom":
            yield payload
        else:
            final = payload
    yield {"type": "final", "state": final}
