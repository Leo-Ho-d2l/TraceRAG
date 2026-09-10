from __future__ import annotations

import json
import re
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import GROUNDED_ANSWER_SYSTEM, RESEARCH_AGENT_SYSTEM, ROUTER_SYSTEM
from app.agent.state import AgentState
from app.agent.tools import AgentTools, TOOL_SCHEMAS
from app.core.config import settings
from app.llm.client import get_chat_client
from app.observability.tracing import span
from app.agent.utils import citations_are_valid, heuristic_route


class TraceRAGGraph:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.llm = get_chat_client()
        self.tools = AgentTools(session)
        self.graph = self._build()

    def _build(self):
        builder = StateGraph(AgentState)
        builder.add_node("route", self._route)
        builder.add_node("retrieve", self._retrieve)
        builder.add_node("research_step", self._research_step)
        builder.add_node("execute_tools", self._execute_tools)
        builder.add_node("finalize", self._finalize)

        builder.add_edge(START, "route")
        builder.add_conditional_edges(
            "route",
            self._after_route,
            {"retrieve": "retrieve", "research": "research_step", "direct": "finalize"},
        )
        builder.add_edge("retrieve", "finalize")
        builder.add_conditional_edges(
            "research_step",
            self._after_research_step,
            {"tools": "execute_tools", "finalize": "finalize"},
        )
        builder.add_edge("execute_tools", "research_step")
        builder.add_edge("finalize", END)
        return builder.compile()

    async def _route(self, state: AgentState) -> dict[str, Any]:
        mode = state.get("mode", "auto")
        if mode in {"retrieve", "research"}:
            return {"route": mode}
        question = state["question"]
        messages = [
            {"role": "system", "content": ROUTER_SYSTEM},
            {"role": "user", "content": question},
        ]
        try:
            result = await self.llm.chat(messages, temperature=0.0)
            payload = _extract_json(result.content or "")
            route = payload.get("route")
            if route in {"direct", "retrieve", "research"}:
                return {"route": route}
        except Exception:
            pass
        return {"route": heuristic_route(question)}

    async def _retrieve(self, state: AgentState) -> dict[str, Any]:
        with span("agent.retrieve"):
            hits, _ = await self.tools.retriever.retrieve(
                state["question"], top_k=state.get("top_k", settings.default_top_k), rerank=True
            )
            evidence: list[dict[str, Any]] = list(state.get("evidence", []))
            self.tools._merge_evidence(evidence, hits)
            return {"evidence": evidence}

    async def _research_step(self, state: AgentState) -> dict[str, Any]:
        step = int(state.get("step", 0)) + 1
        messages = list(state.get("messages") or [])
        if not messages:
            messages = [
                {"role": "system", "content": RESEARCH_AGENT_SYSTEM},
                *state.get("history", []),
                {"role": "user", "content": state["question"]},
            ]
        if step > settings.max_agent_steps:
            return {"step": step, "pending_tool_calls": []}

        with span("agent.research_step", step=step):
            result = await self.llm.chat(
                messages, tools=TOOL_SCHEMAS, temperature=settings.llm_temperature
            )
        raw_message = result.raw_message or {"role": "assistant", "content": result.content}
        messages.append(raw_message)
        pending = [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in result.tool_calls
        ]
        update: dict[str, Any] = {
            "messages": messages,
            "pending_tool_calls": pending,
            "step": step,
        }
        if not pending and result.content:
            update["answer"] = result.content
        return update

    async def _execute_tools(self, state: AgentState) -> dict[str, Any]:
        messages = list(state.get("messages") or [])
        evidence = list(state.get("evidence") or [])
        trace = list(state.get("tool_trace") or [])
        step = int(state.get("step", 0))
        for call in state.get("pending_tool_calls") or []:
            result, evidence, event = await self.tools.execute(
                call["name"], call.get("arguments") or {}, evidence
            )
            event["step"] = step
            trace.append(event)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
        return {
            "messages": messages,
            "evidence": evidence,
            "tool_trace": trace,
            "pending_tool_calls": [],
        }

    async def _finalize(self, state: AgentState) -> dict[str, Any]:
        route = state.get("route", "retrieve")
        if route == "direct":
            messages = [
                {"role": "system", "content": "You are a concise enterprise knowledge assistant."},
                *state.get("history", []),
                {"role": "user", "content": state["question"]},
            ]
            result = await self.llm.chat(messages)
            return {"answer": result.content or ""}

        current = state.get("answer") or ""
        evidence = state.get("evidence") or []
        if current and citations_are_valid(current, evidence):
            return {"answer": current}

        evidence_text = _format_evidence(evidence)
        if not evidence_text:
            return {"answer": "I could not find sufficient evidence in the indexed knowledge base."}

        messages = [
            {"role": "system", "content": GROUNDED_ANSWER_SYSTEM},
            *state.get("history", []),
            {
                "role": "user",
                "content": f"Question:\n{state['question']}\n\nEvidence:\n{evidence_text}",
            },
        ]
        with span("agent.finalize", evidence_count=len(evidence)):
            result = await self.llm.chat(messages, temperature=settings.llm_temperature)
        return {"answer": result.content or ""}

    @staticmethod
    def _after_route(state: AgentState) -> str:
        return state.get("route", "retrieve")

    @staticmethod
    def _after_research_step(state: AgentState) -> str:
        if state.get("pending_tool_calls") and int(state.get("step", 0)) <= settings.max_agent_steps:
            return "tools"
        return "finalize"


def _format_evidence(evidence: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for item in evidence:
        location = item.get("section_title") or ""
        if item.get("page_number"):
            location = f"{location}, page {item['page_number']}".strip(", ")
        blocks.append(
            f"[{item['label']}] {item['filename']} | {location}\n{item['content']}"
        )
    return "\n\n".join(blocks)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

