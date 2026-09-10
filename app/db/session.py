from collections.abc import AsyncIterator

from pgvector.psycopg import register_vector_async
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


@event.listens_for(engine.sync_engine, "connect")
def register_pgvector(dbapi_connection, _connection_record) -> None:
    dbapi_connection.run_async(register_vector_async)


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
