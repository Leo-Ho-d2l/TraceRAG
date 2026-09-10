from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_session

DBSession = Annotated[AsyncSession, Depends(get_session)]
Auth = Annotated[None, Depends(require_api_key)]
