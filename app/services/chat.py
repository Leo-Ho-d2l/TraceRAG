from __future__ import annotations

import re
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import TraceRAGGraph
from app.core.config import settings
from app.db.models import ChatMessage, ChatRole, ChatThread
from app.schemas.chat import ChatResponse, CitationOut, ToolTraceOut


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def answer(
        self,
        question: str,
        thread_id: uuid.UUID | None,
        mode: str,
        top_k: int,
    ) -> ChatResponse:
        started = time.perf_counter()
        thread = await self._get_or_create_thread(thread_id, question)
        history = await self._history(thread.id)

        graph = TraceRAGGraph(self.session)
        state = await graph.graph.ainvoke(
            {
                "question": question,
                "mode": mode,
                "top_k": top_k,
                "history": history,
                "messages": [],
                "pending_tool_calls": [],
                "evidence": [],
                "tool_trace": [],
                "step": 0,
            }
        )
        answer = state.get("answer", "")
        citations = self._resolve_citations(answer, state.get("evidence") or [])

        self.session.add(ChatMessage(thread_id=thread.id, role=ChatRole.user, content=question, citations=[]))
        self.session.add(
            ChatMessage(
                thread_id=thread.id,
                role=ChatRole.assistant,
                content=answer,
                citations=[c.model_dump(mode="json") for c in citations],
            )
        )
        await self.session.commit()

        return ChatResponse(
            thread_id=thread.id,
            route=state.get("route", "retrieve"),
            answer=answer,
            citations=citations,
            tool_trace=[ToolTraceOut(**item) for item in state.get("tool_trace") or []],
            total_steps=int(state.get("step", 0)),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def _get_or_create_thread(self, thread_id: uuid.UUID | None, question: str) -> ChatThread:
        if thread_id:
            thread = await self.session.get(ChatThread, thread_id)
            if thread is not None:
                return thread
        thread = ChatThread(id=uuid.uuid4(), title=question[:120])
        self.session.add(thread)
        await self.session.flush()
        return thread

    async def _history(self, thread_id: uuid.UUID) -> list[dict[str, Any]]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(settings.chat_history_messages)
        )
        rows = list((await self.session.scalars(stmt)).all())
        rows.reverse()
        history: list[dict[str, Any]] = []
        for item in rows:
            content = item.content
            if item.role == ChatRole.assistant:
                # Prior source labels are local to an earlier turn; remove them so
                # [S1] in the next turn can only refer to current evidence.
                content = re.sub(r"\[S\d+\]", "", content)
            history.append({"role": item.role.value, "content": content})
        return history

    @staticmethod
    def _resolve_citations(answer: str, evidence: list[dict[str, Any]]) -> list[CitationOut]:
        labels = []
        for label in re.findall(r"\[(S\d+)\]", answer):
            if label not in labels:
                labels.append(label)
        by_label = {item["label"]: item for item in evidence}
        citations: list[CitationOut] = []
        for label in labels:
            item = by_label.get(label)
            if not item:
                continue
            excerpt = item["content"].replace("\n", " ").strip()
            if len(excerpt) > 420:
                excerpt = excerpt[:417] + "..."
            citations.append(
                CitationOut(
                    label=label,
                    chunk_id=uuid.UUID(item["chunk_id"]),
                    document_id=uuid.UUID(item["document_id"]),
                    filename=item["filename"],
                    section_title=item.get("section_title"),
                    page_number=item.get("page_number"),
                    excerpt=excerpt,
                )
            )
        return citations
