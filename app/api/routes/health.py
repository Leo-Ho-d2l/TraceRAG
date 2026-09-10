from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DBSession

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: DBSession) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
