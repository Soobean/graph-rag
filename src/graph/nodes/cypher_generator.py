"""
Cypher Generator Node

사용자 질문과 엔티티 정보를 바탕으로 Cypher 쿼리를 생성합니다.
캐시 히트 시에는 생성을 스킵하고, 새로 생성 시에는 캐시에 저장합니다.

Latency Optimization:
- 단순 쿼리(single-hop, 기본 의도, 적은 엔티티)에는 LIGHT 모델 사용
- 복잡한 쿼리(multi-hop, 복잡한 의도)에는 HEAVY 모델 사용
"""

from enum import Enum
from typing import Any

from src.config import Settings
from src.domain.types import CypherGeneratorUpdate, GraphSchema
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.repositories.query_cache_repository import QueryCacheRepository


class QueryComplexity(str, Enum):
    """쿼리 복잡도 구분"""

    SIMPLE = "simple"  # LIGHT 모델 사용
    COMPLEX = "complex"  # HEAVY 모델 사용 (fallback 포함)


class CypherGeneratorNode(BaseNode[CypherGeneratorUpdate]):
    """
    Cypher 쿼리 생성 노드

    Latency Optimization:
    - 단순 쿼리 판별 기준:
      1. Single-hop 쿼리 (is_multi_hop=False)
      2. 단순 Intent (personnel_search, certificate_search)
      3. 낮은 엔티티 수 (≤ 2개)
    - 모든 조건 충족 시 LIGHT 모델 사용으로 ~400ms 절감
    """

    # 단순 Intent 목록 (LIGHT 모델로 처리 가능)
    SIMPLE_INTENTS = ["personnel_search", "certificate_search"]

    # 단순 쿼리의 최대 엔티티 수
    MAX_ENTITIES_FOR_SIMPLE = 2

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

    def _analyze_complexity(self, state: GraphRAGState) -> QueryComplexity:
        """
        쿼리 복잡도 분석

        다음 조건을 모두 만족하면 SIMPLE로 판정:
        1. Single-hop 쿼리 (is_multi_hop=False 또는 query_plan 없음)
        2. 단순 Intent (SIMPLE_INTENTS에 포함)
        3. 낮은 엔티티 수 (MAX_ENTITIES_FOR_SIMPLE 이하)

        Args:
            state: 현재 파이프라인 상태

        Returns:
            QueryComplexity: SIMPLE 또는 COMPLEX
        """
        query_plan = state.get("query_plan")
        intent = state.get("intent", "unknown")
        entities = state.get("entities", {})

        # Multi-hop 쿼리면 COMPLEX
        if query_plan and query_plan.get("is_multi_hop"):
            self._logger.debug(
                f"Complex query: multi-hop detected (hops={query_plan.get('hop_count')})"
            )
            return QueryComplexity.COMPLEX

        # 복잡한 Intent면 COMPLEX
        if intent not in self.SIMPLE_INTENTS:
            self._logger.debug(f"Complex query: complex intent ({intent})")
            return QueryComplexity.COMPLEX

        # 엔티티 수 계산
        total_entities = sum(len(v) for v in entities.values())
        if total_entities > self.MAX_ENTITIES_FOR_SIMPLE:
            self._logger.debug(
                f"Complex query: too many entities ({total_entities} > {self.MAX_ENTITIES_FOR_SIMPLE})"
            )
            return QueryComplexity.COMPLEX

        self._logger.debug(
            f"Simple query: intent={intent}, entities={total_entities}"
        )
        return QueryComplexity.SIMPLE

    def _correct_parameters(
        self,
        parameters: dict[str, Any],
        entities: dict[str, list[str]],
    ) -> dict[str, Any]:
        """
        LLM이 생성한 파라미터 값을 엔티티 값으로 보정.

        LLM이 파라미터에 접미사(프로젝트, 팀, 부서 등)를 추가하거나
        공백을 변경하는 경우, 원래 엔티티 값으로 교체합니다.

        매칭 전략 (우선순위):
        1. 정확 일치 → 그대로
        2. 파라미터가 entity를 포함 → entity 값으로 교체
        3. entity가 파라미터를 포함 → entity 값으로 교체
        4. 매칭 실패 → LLM 값 그대로 (fallback)
        """
        # 모든 엔티티 값을 flat set으로 수집
        entity_values: list[str] = []
        for values in entities.values():
            entity_values.extend(values)

        if not entity_values:
            return parameters

        corrected = {}
        for key, value in parameters.items():
            if not isinstance(value, str):
                corrected[key] = value
                continue

            # 1) 정확 일치 (대소문자 무시)
            exact = next(
                (ev for ev in entity_values if ev.lower() == value.lower()),
                None,
            )
            if exact is not None:
                corrected[key] = exact
                continue

            # 2) 파라미터가 entity를 포함 (e.g. "챗봇 리뉴얼 프로젝트" contains "챗봇 리뉴얼")
            #    가장 긴 매칭을 선택 (더 구체적인 것 우선)
            val_lower = value.lower()
            contains_matches = [
                ev for ev in entity_values if ev.lower() in val_lower
            ]
            if contains_matches:
                best = max(contains_matches, key=len)
                self._logger.info(
                    f"Parameter correction: '{value}' → '{best}' (param contains entity)"
                )
                corrected[key] = best
                continue

            # 3) entity가 파라미터를 포함 (e.g. entity "데이터레이크 개선" contains param "데이터레이크")
            reverse_matches = [
                ev for ev in entity_values if val_lower in ev.lower()
            ]
            if reverse_matches:
                best = min(reverse_matches, key=len)
                self._logger.info(
                    f"Parameter correction: '{value}' → '{best}' (entity contains param)"
                )
                corrected[key] = best
                continue

            # 4) 매칭 실패 → 원래 값 유지
            corrected[key] = value

        return corrected

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

        # Multi-hop 쿼리 계획 (QueryDecomposer에서 생성)
        query_plan = state.get("query_plan")

        self._logger.info(f"Generating Cypher for: {question[:50]}...")

        try:
            # 스키마 정보 조회 (State에 없으면 조회)
            schema: GraphSchema
            state_schema = state.get("schema")
            if state_schema:
                schema = state_schema
            else:
                schema = await self._get_schema()

            # 복잡도 분석 및 모델 선택
            use_light_model = False
            if self._settings and self._settings.cypher_light_model_enabled:
                complexity = self._analyze_complexity(state)
                use_light_model = complexity == QueryComplexity.SIMPLE
                self._logger.info(
                    f"Query complexity: {complexity.value}, use_light_model={use_light_model}"
                )

            # LLM을 통한 Cypher 생성
            result = await self._llm.generate_cypher(
                question=question,
                schema=dict(schema),  # TypedDict를 dict로 변환
                entities=formatted_entities,
                query_plan=dict(query_plan) if query_plan else None,  # Multi-hop 쿼리 계획 전달
                use_light_model=use_light_model,
            )

            cypher = result.get("cypher", "")
            parameters = result.get("parameters", {})

            # 파라미터를 엔티티 값으로 보정 (LLM 접미사 추가 방지)
            parameters = self._correct_parameters(parameters, raw_entities)

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
