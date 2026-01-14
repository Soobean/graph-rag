"""
Query Cache Repository - 질문-Cypher 캐싱 관리

책임:
- 질문과 생성된 Cypher 쿼리를 Vector Index로 캐싱
- 유사 질문 검색으로 Cypher 생성 스킵 (성능 최적화)
- 캐시 TTL 관리 및 무효화
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.config import Settings
from src.domain.exceptions import QueryExecutionError
from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# Vector Index 설정
QUERY_CACHE_INDEX_NAME = "query_cache_embedding"
QUERY_CACHE_LABEL = "CachedQuery"
QUERY_CACHE_EMBEDDING_PROPERTY = "embedding"


@dataclass
class CachedQuery:
    """캐시된 질문-Cypher 쌍"""

    id: str
    question: str
    cypher_query: str
    cypher_parameters: dict[str, Any]
    created_at: datetime
    hit_count: int
    score: float  # 유사도 점수

    @classmethod
    def from_neo4j(cls, data: dict[str, Any], score: float = 1.0) -> "CachedQuery":
        """Neo4j 노드 데이터에서 생성"""
        props = data.get("properties", data)

        # cypher_parameters는 JSON 문자열로 저장됨
        params_str = props.get("cypher_parameters", "{}")
        try:
            params = json.loads(params_str) if isinstance(params_str, str) else params_str
        except json.JSONDecodeError as e:
            logger.warning(
                f"Failed to parse cached cypher_parameters: {e}. "
                f"Data (truncated): {str(params_str)[:100]}"
            )
            params = {}

        # created_at 처리
        created_at = props.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif created_at is None:
            created_at = datetime.now(UTC)

        return cls(
            id=data.get("id", ""),
            question=props.get("question", ""),
            cypher_query=props.get("cypher_query", ""),
            cypher_parameters=params,
            created_at=created_at,
            hit_count=props.get("hit_count", 0),
            score=score,
        )


class QueryCacheRepository:
    """
    질문-Cypher 캐싱 Repository

    Neo4j Vector Index를 활용하여 유사 질문에 대한 Cypher 쿼리를 캐싱합니다.

    사용 예시:
        repo = QueryCacheRepository(neo4j_client, settings)
        await repo.ensure_index()

        # 캐시 조회
        cached = await repo.find_similar_query(embedding, threshold=0.9)
        if cached:
            return cached.cypher_query, cached.cypher_parameters

        # 캐시 저장
        await repo.cache_query(question, embedding, cypher, params)
    """

    def __init__(self, client: Neo4jClient, settings: Settings):
        self._client = client
        self._settings = settings
        self._index_ensured = False

        logger.info(
            f"QueryCacheRepository initialized: "
            f"threshold={settings.vector_similarity_threshold}, "
            f"ttl={settings.query_cache_ttl_hours}h"
        )

    async def ensure_index(self) -> bool:
        """
        Vector Index 존재 확인 및 생성

        Returns:
            성공 여부
        """
        if self._index_ensured:
            return True

        try:
            result = await self._client.create_vector_index(
                index_name=QUERY_CACHE_INDEX_NAME,
                label=QUERY_CACHE_LABEL,
                property_name=QUERY_CACHE_EMBEDDING_PROPERTY,
                dimensions=self._settings.embedding_dimensions,
            )
            self._index_ensured = result
            return result
        except Exception as e:
            logger.error(f"Failed to ensure query cache index: {e}")
            return False

    async def cache_query(
        self,
        question: str,
        embedding: list[float],
        cypher_query: str,
        cypher_parameters: dict[str, Any] | None = None,
    ) -> str | None:
        """
        질문과 Cypher 쿼리를 캐시에 저장

        Args:
            question: 원본 질문
            embedding: 질문 임베딩 벡터
            cypher_query: 생성된 Cypher 쿼리
            cypher_parameters: Cypher 쿼리 파라미터

        Returns:
            생성된 노드의 elementId (실패 시 None)
        """
        await self.ensure_index()

        params_json = json.dumps(cypher_parameters or {}, ensure_ascii=False)
        now = datetime.now(UTC).isoformat()

        query = f"""
        CREATE (c:{QUERY_CACHE_LABEL} {{
            question: $question,
            {QUERY_CACHE_EMBEDDING_PROPERTY}: $embedding,
            cypher_query: $cypher_query,
            cypher_parameters: $cypher_parameters,
            created_at: datetime($created_at),
            hit_count: 0
        }})
        RETURN elementId(c) as id
        """

        try:
            result = await self._client.execute_write(
                query,
                {
                    "question": question,
                    "embedding": embedding,
                    "cypher_query": cypher_query,
                    "cypher_parameters": params_json,
                    "created_at": now,
                },
            )
            if result:
                node_id = result[0]["id"]
                logger.info(f"Cached query: '{question[:50]}...' -> {node_id}")
                return node_id
            return None
        except Exception as e:
            logger.error(f"Failed to cache query: {e}")
            return None

    async def find_similar_query(
        self,
        embedding: list[float],
        threshold: float | None = None,
    ) -> CachedQuery | None:
        """
        유사 질문 검색

        Args:
            embedding: 검색할 질문의 임베딩 벡터
            threshold: 최소 유사도 점수 (None이면 설정값 사용)

        Returns:
            가장 유사한 캐시된 쿼리 (없으면 None)
        """
        await self.ensure_index()

        min_score = threshold or self._settings.vector_similarity_threshold

        try:
            results = await self._client.vector_search(
                index_name=QUERY_CACHE_INDEX_NAME,
                embedding=embedding,
                limit=1,
                threshold=min_score,
            )

            if not results:
                logger.debug(f"No similar query found (threshold={min_score})")
                return None

            # TTL 체크
            result = results[0]
            cached = CachedQuery.from_neo4j(result, score=result["score"])

            ttl_hours = self._settings.query_cache_ttl_hours
            expiry_time = cached.created_at + timedelta(hours=ttl_hours)

            if datetime.now(UTC) > expiry_time:
                logger.debug(f"Cache expired for query: {cached.question[:50]}...")
                # 만료된 캐시 삭제
                await self._delete_cache(cached.id)
                return None

            # hit_count 증가
            await self._increment_hit_count(cached.id)

            logger.info(
                f"Cache HIT: '{cached.question[:50]}...' (score={cached.score:.3f})"
            )
            return cached

        except Exception as e:
            logger.error(f"Failed to find similar query: {e}")
            return None

    async def _increment_hit_count(self, node_id: str) -> None:
        """캐시 히트 카운트 증가"""
        query = """
        MATCH (c)
        WHERE elementId(c) = $node_id
        SET c.hit_count = c.hit_count + 1
        """
        try:
            await self._client.execute_write(query, {"node_id": node_id})
        except Exception as e:
            logger.warning(f"Failed to increment hit count: {e}")

    async def _delete_cache(self, node_id: str) -> None:
        """캐시 삭제"""
        query = """
        MATCH (c)
        WHERE elementId(c) = $node_id
        DELETE c
        """
        try:
            await self._client.execute_write(query, {"node_id": node_id})
            logger.debug(f"Deleted expired cache: {node_id}")
        except Exception as e:
            logger.warning(f"Failed to delete cache: {e}")

    async def invalidate_cache(
        self,
        older_than: datetime | None = None,
    ) -> int:
        """
        캐시 무효화 (만료된 항목 삭제)

        Args:
            older_than: 이 시간보다 오래된 캐시 삭제 (None이면 TTL 기준)

        Returns:
            삭제된 캐시 수
        """
        if older_than is None:
            ttl_hours = self._settings.query_cache_ttl_hours
            older_than = datetime.now(UTC) - timedelta(hours=ttl_hours)

        query = f"""
        MATCH (c:{QUERY_CACHE_LABEL})
        WHERE c.created_at < datetime($older_than)
        WITH c, elementId(c) as id
        DELETE c
        RETURN count(*) as deleted_count
        """

        try:
            result = await self._client.execute_write(
                query, {"older_than": older_than.isoformat()}
            )
            count = result[0]["deleted_count"] if result else 0
            logger.info(f"Invalidated {count} expired cache entries")
            return count
        except Exception as e:
            logger.error(f"Failed to invalidate cache: {e}")
            raise QueryExecutionError(f"Cache invalidation failed: {e}") from e

    async def clear_all_cache(self) -> int:
        """
        모든 캐시 삭제

        Returns:
            삭제된 캐시 수
        """
        query = f"""
        MATCH (c:{QUERY_CACHE_LABEL})
        WITH c, count(*) as total
        DELETE c
        RETURN total as deleted_count
        """

        try:
            result = await self._client.execute_write(query)
            count = result[0]["deleted_count"] if result else 0
            logger.info(f"Cleared all {count} cache entries")
            return count
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            raise QueryExecutionError(f"Cache clear failed: {e}") from e

    async def get_cache_stats(self) -> dict[str, Any]:
        """
        캐시 통계 조회

        Returns:
            캐시 통계 정보
        """
        query = f"""
        MATCH (c:{QUERY_CACHE_LABEL})
        RETURN
            count(c) as total_count,
            sum(c.hit_count) as total_hits,
            avg(c.hit_count) as avg_hits,
            min(c.created_at) as oldest,
            max(c.created_at) as newest
        """

        try:
            result = await self._client.execute_query(query)
            if not result:
                return {
                    "total_count": 0,
                    "total_hits": 0,
                    "avg_hits": 0,
                    "oldest": None,
                    "newest": None,
                }

            stats = result[0]
            return {
                "total_count": stats.get("total_count", 0),
                "total_hits": stats.get("total_hits", 0),
                "avg_hits": round(stats.get("avg_hits", 0) or 0, 2),
                "oldest": stats.get("oldest"),
                "newest": stats.get("newest"),
                "ttl_hours": self._settings.query_cache_ttl_hours,
                "similarity_threshold": self._settings.vector_similarity_threshold,
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}
