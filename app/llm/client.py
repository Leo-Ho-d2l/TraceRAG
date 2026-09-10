from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.observability.tracing import span


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    raw_message: dict[str, Any] = field(default_factory=dict)


class BaseChatClient:
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        raise NotImplementedError


class OpenAICompatibleChatClient(BaseChatClient):
    def __init__(self) -> None:
        self.endpoint = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        self.client = httpx.AsyncClient(timeout=settings.llm_timeout_seconds)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        body: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": settings.llm_temperature if temperature is None else temperature,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        with span("llm.chat", model=settings.llm_model, tools=bool(tools)):
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
                retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
                reraise=True,
            ):
                with attempt:
                    response = await self.client.post(self.endpoint, headers=headers, json=body)
                    response.raise_for_status()
                    payload = response.json()

        message = payload["choices"][0]["message"]
        tool_calls: list[ToolCall] = []
        for item in message.get("tool_calls") or []:
            raw_arguments = item.get("function", {}).get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCall(
                    id=item.get("id", f"call_{len(tool_calls)}"),
                    name=item.get("function", {}).get("name", ""),
                    arguments=arguments or {},
                )
            )
        return ChatResult(
            content=message.get("content"),
            tool_calls=tool_calls,
            usage=payload.get("usage") or {},
            raw_message=message,
        )


class MockChatClient(BaseChatClient):
    """Predictable smoke-test client. It is not intended for benchmark claims."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        system = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
        user = next((str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), "")
        if "[ROUTER]" in system:
            route = "research" if re.search(r"\b(compare|difference|across|why|trade[- ]?off|versus|vs\.?|multiple)\b", user, re.I) else "retrieve"
            if re.match(r"^(hi|hello|hey|thanks|thank you)[!. ]*$", user.strip(), re.I):
                route = "direct"
            return ChatResult(content=json.dumps({"route": route}))

        if tools:
            tool_messages = [m for m in messages if m.get("role") == "tool"]
            if not tool_messages:
                call = ToolCall(id="mock_search_1", name="search_documents", arguments={"query": user, "top_k": 6})
                raw = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                        }
                    ],
                }
                return ChatResult(content=None, tool_calls=[call], raw_message=raw)
            source_labels = re.findall(r"\[(S\d+)\]", str(tool_messages[-1].get("content", "")))
            label = source_labels[0] if source_labels else "S1"
            content = f"The retrieved knowledge base contains relevant evidence for this request [{label}]."
            return ChatResult(content=content, raw_message={"role": "assistant", "content": content})

        if "[GROUNDED_ANSWER]" in system:
            labels = re.findall(r"\[(S\d+)\]", "\n".join(str(m.get("content", "")) for m in messages))
            label = labels[0] if labels else "S1"
            return ChatResult(content=f"The retrieved evidence supports the response [{label}].")

        return ChatResult(content="TraceRAG is running in mock LLM mode. Configure an OpenAI-compatible endpoint for semantic answers.")


@lru_cache(maxsize=1)
def get_chat_client() -> BaseChatClient:
    if settings.llm_backend == "mock":
        return MockChatClient()
    return OpenAICompatibleChatClient()
