from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RetrievalCache:
    def __init__(self) -> None:
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        await self.redis.aclose()

    async def corpus_version(self) -> int:
        try:
            raw = await self.redis.get("tracerag:corpus_version")
            return int(raw or 0)
        except Exception:
            logger.warning("Redis unavailable; retrieval cache disabled", exc_info=True)
            return 0

    async def bump_corpus_version(self) -> None:
        try:
            await self.redis.incr("tracerag:corpus_version")
        except Exception:
            logger.warning("Could not bump corpus version", exc_info=True)

    async def get(self, query: str, payload: dict[str, Any]) -> list[dict[str, Any]] | None:
        try:
            version = await self.corpus_version()
            key = self._key(version, query, payload)
            raw = await self.redis.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            logger.warning("Retrieval cache get failed", exc_info=True)
            return None

    async def set(self, query: str, payload: dict[str, Any], value: list[dict[str, Any]]) -> None:
        try:
            version = await self.corpus_version()
            key = self._key(version, query, payload)
            await self.redis.setex(
                key,
                settings.retrieval_cache_ttl_seconds,
                json.dumps(value, ensure_ascii=False),
            )
        except Exception:
            logger.warning("Retrieval cache set failed", exc_info=True)

    @staticmethod
    def _key(version: int, query: str, payload: dict[str, Any]) -> str:
        normalized = json.dumps({"q": query, **payload}, sort_keys=True, default=str)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"tracerag:retrieval:v{version}:{digest}"
