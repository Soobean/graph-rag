"""
Neo4j Schema Repository - 스키마 캐싱 + 메타데이터

책임:
- 그래프 스키마 조회 (TTL 기반 캐싱)
- 노드 레이블/관계 타입/속성 목록
"""

import asyncio
import logging
import time
from typing import Any

from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class Neo4jSchemaRepository:
    """스키마 캐싱 전담 레포지토리"""

    SCHEMA_CACHE_TTL_SECONDS = 300

    def __init__(self, client: Neo4jClient):
        self._client = client
        self._schema_cache: dict[str, Any] | None = None
        self._schema_cache_time: float = 0.0
        self._schema_fetch_lock = asyncio.Lock()

    async def get_schema(self, force_refresh: bool = False) -> dict[str, Any]:
        """그래프 스키마 정보 조회 (TTL 기반 캐싱, 동시성 안전)"""
        current_time = time.time()
        cache_expired = (
            current_time - self._schema_cache_time
        ) > self.SCHEMA_CACHE_TTL_SECONDS

        if force_refresh or self._schema_cache is None or cache_expired:
            async with self._schema_fetch_lock:
                if (
                    force_refresh
                    or self._schema_cache is None
                    or (time.time() - self._schema_cache_time)
                    > self.SCHEMA_CACHE_TTL_SECONDS
                ):
                    logger.debug(
                        "Fetching schema from database (cache miss or expired)"
                    )
                    self._schema_cache = await self._client.get_schema_info()
                    self._schema_cache_time = time.time()
                else:
                    logger.debug("Using cached schema (updated by another task)")
        else:
            logger.debug("Using cached schema")

        return self._schema_cache

    def invalidate_schema_cache(self) -> None:
        """스키마 캐시 무효화"""
        self._schema_cache = None
        self._schema_cache_time = 0.0
        logger.debug("Schema cache invalidated")

    async def get_node_labels(self) -> list[str]:
        """노드 레이블 목록 조회"""
        schema = await self.get_schema()
        return schema.get("node_labels", [])

    async def get_relationship_types(self) -> list[str]:
        """관계 타입 목록 조회"""
        schema = await self.get_schema()
        return schema.get("relationship_types", [])

    async def get_node_properties(self, label: str) -> list[str]:
        """특정 레이블의 노드 속성 목록 조회"""
        query = """
        MATCH (n)
        WHERE $label IN labels(n)
        UNWIND keys(n) as key
        RETURN DISTINCT key
        LIMIT 100
        """

        results = await self._client.execute_query(query, {"label": label})
        return [r["key"] for r in results]
