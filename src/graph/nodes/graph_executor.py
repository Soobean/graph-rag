"""
Graph Executor Node

생성된 Cypher 쿼리를 Neo4j에서 실행합니다.
"""

import logging

from src.domain.types import GraphExecutorUpdate
from src.graph.state import GraphRAGState
from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)


class GraphExecutorNode:
    """그래프 쿼리 실행 노드"""

    def __init__(self, neo4j_repository: Neo4jRepository):
        self._neo4j = neo4j_repository

    async def __call__(self, state: GraphRAGState) -> GraphExecutorUpdate:
        """
        Cypher 쿼리 실행

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        cypher_query = state.get("cypher_query", "")
        parameters = state.get("cypher_parameters", {})

        if not cypher_query:
            logger.warning("No Cypher query to execute")
            return {
                "graph_results": [],
                "result_count": 0,
                "execution_path": ["graph_executor_skipped"],
            }

        logger.info(f"Executing Cypher: {cypher_query[:100]}...")

        try:
            results = await self._neo4j.execute_cypher(
                query=cypher_query,
                parameters=parameters,
            )

            logger.info(f"Query returned {len(results)} results")

            return {
                "graph_results": results,
                "result_count": len(results),
                "execution_path": ["graph_executor"],
            }

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return {
                "graph_results": [],
                "result_count": 0,
                "error": f"Query execution failed: {str(e)}",
                "execution_path": ["graph_executor_error"],
            }
