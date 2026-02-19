"""
Neo4j Vector Repository - 벡터 검색

책임:
- Vector Index 관리
- 노드 유사도 검색
- 임베딩 저장/업데이트
"""

import logging
from typing import Any

from src.domain.exceptions import QueryExecutionError
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.neo4j_types import NodeResult
from src.repositories.neo4j_validators import validate_labels

logger = logging.getLogger(__name__)


class Neo4jVectorRepository:
    """벡터 검색 전담 레포지토리"""

    def __init__(self, client: Neo4jClient):
        self._client = client

    async def vector_search_nodes(
        self,
        embedding: list[float],
        index_name: str,
        labels: list[str] | None = None,
        limit: int = 10,
        threshold: float | None = None,
    ) -> list[tuple[Any, float]]:
        """Vector Index를 사용한 노드 유사도 검색"""
        try:
            results = await self._client.vector_search(
                index_name=index_name,
                embedding=embedding,
                limit=limit,
                threshold=threshold,
            )

            if labels:
                validated_labels = set(validate_labels(labels))
                results = [
                    r
                    for r in results
                    if validated_labels.intersection(set(r.get("labels", [])))
                ]

            return [
                (
                    NodeResult(
                        id=r["id"],
                        labels=r["labels"],
                        properties=r["properties"],
                    ),
                    r["score"],
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Vector search failed on index '{index_name}': {e}")
            raise QueryExecutionError(
                f"Vector search failed: {e}", query=f"vector_search({index_name})"
            ) from e

    async def ensure_vector_index(
        self,
        index_name: str,
        label: str,
        property_name: str,
        dimensions: int = 1536,
    ) -> bool:
        """Vector Index가 존재하는지 확인하고 없으면 생성"""
        return await self._client.create_vector_index(
            index_name=index_name,
            label=label,
            property_name=property_name,
            dimensions=dimensions,
        )

    async def upsert_node_embedding(
        self,
        node_id: str,
        property_name: str,
        embedding: list[float],
    ) -> bool:
        """노드에 임베딩 저장/업데이트"""
        return await self._client.upsert_embedding(
            node_id=node_id,
            property_name=property_name,
            embedding=embedding,
        )

    async def batch_upsert_node_embeddings(
        self,
        updates: list[dict[str, Any]],
        property_name: str,
    ) -> int:
        """여러 노드에 임베딩 일괄 저장"""
        return await self._client.batch_upsert_embeddings(
            updates=updates,
            property_name=property_name,
        )
