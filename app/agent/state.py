from __future__ import annotations

from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    mode: Literal["auto", "retrieve", "research"]
    route: Literal["direct", "retrieve", "research"]
    top_k: int
    history: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    answer: str
    step: int
    tool_trace: list[dict[str, Any]]
