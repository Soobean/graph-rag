"""
Cypher Generator Node

사용자 질문과 엔티티 정보를 바탕으로 Cypher 쿼리를 생성합니다.
캐시 히트 시에는 생성을 스킵하고, 새로 생성 시에는 캐시에 저장합니다.
"""

from typing import Any

from src.config import Settings
from src.domain.types import CypherGeneratorUpdate, GraphSchema
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.repositories.query_cache_repository import QueryCacheRepository


class CypherGeneratorNode(BaseNode[CypherGeneratorUpdate]):
    """Cypher 쿼리 생성 노드"""

    def __init__(
        self,
        llm_repository: LLMRepository,
        neo4j_repository: Neo4jRepository,
        cache_repository: QueryCacheRepository | None = None,
        settings: Settings | None = None,
    ):
        super().__init__()
        self._llm = llm_repository
        self._neo4j = neo4j_repository
        self._cache = cache_repository
        self._settings = settings
        self._schema_cache: GraphSchema | None = None

    @property
    def name(self) -> str:
        return "cypher_generator"

    @property
    def input_keys(self) -> list[str]:
        return ["question", "entities"]


    async def _get_schema(self) -> GraphSchema:
        """스키마 정보 조회 (캐싱)"""
        if self._schema_cache is None:
            schema_dict = await self._neo4j.get_schema()
            # dict를 GraphSchema TypedDict로 변환
            self._schema_cache = GraphSchema(
                node_labels=schema_dict.get("node_labels", []),
                relationship_types=schema_dict.get("relationship_types", []),
                nodes=schema_dict.get("nodes", []),
                relationships=schema_dict.get("relationships", []),
                indexes=schema_dict.get("indexes", []),
                constraints=schema_dict.get("constraints", []),
            )
        return self._schema_cache

    async def _process(self, state: GraphRAGState) -> CypherGeneratorUpdate:
        """
        Cypher 쿼리 생성

        캐시 히트 시에는 이미 cypher_query가 설정되어 있으므로 스킵합니다.
        새로 생성한 쿼리는 캐시에 저장합니다.

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state.get("question", "")

        # 캐시 히트 시 스킵 (이미 cypher_query가 설정됨)
        if state.get("skip_generation"):
            self._logger.info("Skipping Cypher generation (cache hit)")
            # 캐시된 값은 이미 state에 있으므로 execution_path만 추가
            return CypherGeneratorUpdate(
                execution_path=[f"{self.name}_cached"],
            )

        # entities는 dict[str, list[str]] 구조임 (e.g. {'skills': ['Python']})
        # LLMRepository.generate_cypher는 list[dict]를 기대함.
        raw_entities = state.get("entities", {})
        formatted_entities: list[dict[str, str]] = []
        for entity_type, values in raw_entities.items():
            for value in values:
                formatted_entities.append({"type": entity_type, "value": value})

        self._logger.info(f"Generating Cypher for: {question[:50]}...")

        try:
            # 스키마 정보 조회 (State에 없으면 조회)
            schema: GraphSchema
            state_schema = state.get("schema")
            if state_schema:
                schema = state_schema
            else:
                schema = await self._get_schema()

            # LLM을 통한 Cypher 생성
            result = await self._llm.generate_cypher(
                question=question,
                schema=dict(schema),  # TypedDict를 dict로 변환
                entities=formatted_entities,
            )

            cypher = result.get("cypher", "")
            parameters = result.get("parameters", {})

            # 기본적인 쿼리 검증
            if not cypher or not cypher.strip():
                raise ValueError("Empty Cypher query generated")

            self._logger.info(f"Generated Cypher: {cypher[:100]}...")
            self._logger.debug(f"Parameters: {parameters}")

            # 캐시에 저장 (비동기, 실패해도 진행)
            await self._save_to_cache(state, cypher, parameters)

            return CypherGeneratorUpdate(
                schema=schema,
                cypher_query=cypher,
                cypher_parameters=parameters,
                execution_path=[self.name],
            )

        except Exception as e:
            self._logger.error(f"Cypher generation failed: {e}")
            return CypherGeneratorUpdate(
                cypher_query="",
                cypher_parameters={},
                error=f"Cypher generation failed: {e}",
                execution_path=[f"{self.name}_error"],
            )

    async def _save_to_cache(
        self,
        state: GraphRAGState,
        cypher: str,
        parameters: dict[str, Any],
    ) -> None:
        """
        생성된 Cypher 쿼리를 캐시에 저장

        Args:
            state: 현재 파이프라인 상태
            cypher: 생성된 Cypher 쿼리
            parameters: Cypher 파라미터
        """
        if not self._cache:
            return

        if not self._settings or not self._settings.vector_search_enabled:
            return

        # 임베딩이 없으면 저장 스킵
        embedding = state.get("question_embedding")
        if not embedding:
            self._logger.debug("No question embedding available, skipping cache save")
            return

        try:
            question = state.get("question", "")
            await self._cache.cache_query(
                question=question,
                embedding=embedding,
                cypher_query=cypher,
                cypher_parameters=parameters,
            )
            self._logger.debug(f"Saved query to cache: {question[:50]}...")
        except Exception as e:
            # 캐시 저장 실패는 무시 (graceful degradation)
            self._logger.warning(f"Failed to save query to cache: {e}")
