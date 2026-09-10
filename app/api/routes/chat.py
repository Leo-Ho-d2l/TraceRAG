import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import Auth, DBSession
from app.db.models import ChatMessage, ChatThread
from app.schemas.chat import ChatRequest, ChatResponse, MessageOut
from app.services.chat import ChatService

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, session: DBSession, _auth: Auth) -> ChatResponse:
    return await ChatService(session).answer(
        question=request.question,
        thread_id=request.thread_id,
        mode=request.mode,
        top_k=request.top_k,
    )


@router.get("/threads/{thread_id}/messages", response_model=list[MessageOut])
async def get_thread_messages(thread_id: uuid.UUID, session: DBSession, _auth: Auth) -> list[MessageOut]:
    thread = await session.get(ChatThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    stmt = select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.created_at)
    rows = list((await session.scalars(stmt)).all())
    return [
        MessageOut(id=row.id, role=row.role.value, content=row.content, created_at=row.created_at)
        for row in rows
    ]
