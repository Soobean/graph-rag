"""
Schema Fetcher Node

Neo4j 스키마 정보를 조회합니다.
EntityExtractor와 병렬 실행되어 성능을 최적화합니다.
"""

import logging

from src.domain.types import SchemaFetcherUpdate
from src.graph.state import GraphRAGState
from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)


class SchemaFetcherNode:
    """스키마 조회 노드"""

    def __init__(self, neo4j_repository: Neo4jRepository):
        self._neo4j = neo4j_repository

    async def __call__(self, state: GraphRAGState) -> SchemaFetcherUpdate:
        """
        Neo4j 스키마 정보 조회

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        logger.info("Fetching Neo4j schema...")

        try:
            schema = await self._neo4j.get_schema()

            logger.info(
                f"Schema fetched: {len(schema.get('node_labels', []))} labels, "
                f"{len(schema.get('relationship_types', []))} relationship types"
            )

            return {
                "schema": schema,
                "execution_path": ["schema_fetcher"],
            }

        except Exception as e:
            logger.error(f"Schema fetch failed: {e}")
            return {
                "schema": {},
                "error": f"Schema fetch failed: {e}",
                "execution_path": ["schema_fetcher_error"],
            }
