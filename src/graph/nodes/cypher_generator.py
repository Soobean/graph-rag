"""
Cypher Generator Node

사용자 질문과 엔티티 정보를 바탕으로 Cypher 쿼리를 생성합니다.
"""

import logging

from src.domain.types import CypherGeneratorUpdate, GraphSchema
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)


class CypherGeneratorNode:
    """Cypher 쿼리 생성 노드"""

    def __init__(
        self,
        llm_repository: LLMRepository,
        neo4j_repository: Neo4jRepository,
    ):
        self._llm = llm_repository
        self._neo4j = neo4j_repository
        self._schema_cache: GraphSchema | None = None

    async def _get_schema(self) -> GraphSchema:
        """스키마 정보 조회 (캐싱)"""
        if self._schema_cache is None:
            self._schema_cache = await self._neo4j.get_schema()
        return self._schema_cache

    async def __call__(self, state: GraphRAGState) -> CypherGeneratorUpdate:
        """
        Cypher 쿼리 생성

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state["question"]
        # entities는 dict[str, list[str]] 구조임 (e.g. {'skills': ['Python']})
        # 하지만 LLMRepository.generate_cypher는 list[dict]를 기대할 수 있음. 확인 필요.
        # LLMRepository 코드를 보니 list[dict]를 받아서 _format_entities로 변환함.
        # GraphRAGState의 entities는 extraction 단계에서 구조화된 dict임.
        # 여기서는 간단히 변환해서 넘겨주거나 LLMRepository를 맞춰야 함.
        # 일단 호환성을 위해 변환 로직 추가.

        raw_entities = state.get("entities", {})
        formatted_entities = []
        for entity_type, values in raw_entities.items():
            for value in values:
                formatted_entities.append({"type": entity_type, "value": value})

        logger.info(f"Generating Cypher for: {question[:50]}...")

        try:
            # 스키마 정보 조회 (State에 없으면 조회)
            if state.get("schema"):
                schema = state["schema"]
            else:
                schema = await self._get_schema()

            # LLM을 통한 Cypher 생성
            result = await self._llm.generate_cypher(
                question=question,
                schema=schema,
                entities=formatted_entities,
            )

            cypher = result.get("cypher", "")
            parameters = result.get("parameters", {})

            # 기본적인 쿼리 검증
            if not cypher or not cypher.strip():
                raise ValueError("Empty Cypher query generated")

            logger.info(f"Generated Cypher: {cypher[:100]}...")
            logger.debug(f"Parameters: {parameters}")

            return {
                "schema": schema,
                "cypher_query": cypher,
                "cypher_parameters": parameters,
                "execution_path": ["cypher_generator"],
            }

        except Exception as e:
            logger.error(f"Cypher generation failed: {e}")
            return {
                "cypher_query": "",
                "cypher_parameters": {},
                "error": f"Cypher generation failed: {e}",
                "execution_path": ["cypher_generator_error"],
            }
