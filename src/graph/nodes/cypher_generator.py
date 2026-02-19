"""
Cypher Generator Node

사용자 질문과 엔티티 정보를 바탕으로 Cypher 쿼리를 생성합니다.
캐시 히트 시에는 생성을 스킵합니다. (캐시 저장은 GraphExecutor에서 실행 성공 후 수행)

Latency Optimization:
- 단순 쿼리(single-hop, 기본 의도, 적은 엔티티)에는 LIGHT 모델 사용
- 복잡한 쿼리(multi-hop, 복잡한 의도)에는 HEAVY 모델 사용
"""

import re
from enum import Enum
from typing import Any

from src.auth.access_policy import AccessPolicy
from src.config import Settings
from src.domain.types import CypherGeneratorUpdate, GraphSchema
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository


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
        settings: Settings | None = None,
    ):
        super().__init__()
        self._llm = llm_repository
        self._neo4j = neo4j_repository
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

        self._logger.debug(f"Simple query: intent={intent}, entities={total_entities}")
        return QueryComplexity.SIMPLE

    def _correct_single_value(
        self,
        value: str,
        entity_values: list[str],
    ) -> str:
        """
        단일 문자열 값을 엔티티 값으로 보정.

        매칭 전략 (우선순위):
        1. 정확 일치 → 그대로
        2. 파라미터가 entity를 포함 → entity 값으로 교체
        3. entity가 파라미터를 포함 → entity 값으로 교체
        4. 매칭 실패 → 원래 값 그대로 (fallback)
        """
        # 1) 정확 일치 (대소문자 무시)
        exact = next(
            (ev for ev in entity_values if ev.lower() == value.lower()),
            None,
        )
        if exact is not None:
            return exact

        # 2) 파라미터가 entity를 포함 (e.g. "챗봇 리뉴얼 프로젝트" contains "챗봇 리뉴얼")
        val_lower = value.lower()
        contains_matches = [ev for ev in entity_values if ev.lower() in val_lower]
        if contains_matches:
            best = max(contains_matches, key=len)
            self._logger.info(
                f"Parameter correction: '{value}' → '{best}' (param contains entity)"
            )
            return best

        # 3) entity가 파라미터를 포함 (e.g. entity "데이터레이크 개선" contains param "데이터레이크")
        reverse_matches = [ev for ev in entity_values if val_lower in ev.lower()]
        if reverse_matches:
            best = min(reverse_matches, key=len)
            self._logger.info(
                f"Parameter correction: '{value}' → '{best}' (entity contains param)"
            )
            return best

        # 4) 매칭 실패 → 원래 값 유지
        return value

    def _correct_parameters(
        self,
        parameters: dict[str, Any],
        entities: dict[str, list[str]],
    ) -> dict[str, Any]:
        """
        LLM이 생성한 파라미터 값을 엔티티 값으로 보정.

        LLM이 파라미터에 접미사(프로젝트, 팀, 부서 등)를 추가하거나
        공백을 변경하는 경우, 원래 엔티티 값으로 교체합니다.
        문자열과 문자열 리스트 모두 처리합니다.
        """
        # 모든 엔티티 값을 flat list로 수집
        entity_values: list[str] = []
        for values in entities.values():
            entity_values.extend(values)

        if not entity_values:
            return parameters

        corrected: dict[str, Any] = {}
        for key, value in parameters.items():
            if isinstance(value, str):
                corrected[key] = self._correct_single_value(value, entity_values)
            elif isinstance(value, list):
                # 리스트 내 문자열 요소들도 보정
                corrected[key] = [
                    self._correct_single_value(v, entity_values)
                    if isinstance(v, str)
                    else v
                    for v in value
                ]
            else:
                corrected[key] = value

        return corrected

    def _coerce_tolower_params(
        self,
        cypher: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Cypher에서 toLower()에 사용되는 파라미터가 숫자 타입이면
        문자열로 변환합니다.

        두 가지 패턴을 감지합니다:
        1. 직접: toLower($param)
        2. 간접: ANY(var IN $param WHERE ... toLower(var))
        """
        tolower_params: set[str] = set()

        # 패턴 1: toLower($paramName) — 직접 사용
        tolower_params.update(re.findall(r"toLower\(\s*\$(\w+)\s*\)", cypher))

        # 패턴 2: var IN $param ... toLower(var) — 리스트 순회 간접 사용
        for iter_var, param_name in re.findall(r"(\w+)\s+IN\s+\$(\w+)", cypher):
            if re.search(rf"toLower\(\s*{re.escape(iter_var)}\s*\)", cypher):
                tolower_params.add(param_name)

        if not tolower_params:
            return parameters

        coerced = dict(parameters)
        for param_name in tolower_params:
            if param_name in coerced:
                value = coerced[param_name]
                if isinstance(value, (int, float)):
                    self._logger.info(
                        f"Coercing toLower param '{param_name}': "
                        f"{type(value).__name__}({value}) → str('{value}')"
                    )
                    coerced[param_name] = str(value)
                elif isinstance(value, list):
                    coerced[param_name] = [
                        str(v) if isinstance(v, (int, float)) else v for v in value
                    ]
        return coerced

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

            # 접근 제어: 허용되지 않은 라벨/관계를 스키마에서 제거
            # (최적화 — LLM이 금지된 라벨로 쿼리를 생성하지 않도록 유도)
            user_context = state.get("user_context")
            if user_context and not user_context.is_admin:
                policy = user_context.get_access_policy()
                schema = self._filter_schema_for_policy(schema, policy)

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
                query_plan=dict(query_plan)
                if query_plan
                else None,  # Multi-hop 쿼리 계획 전달
                use_light_model=use_light_model,
            )

            cypher = result.get("cypher", "")
            parameters = result.get("parameters", {})

            # 파라미터를 엔티티 값으로 보정 (LLM 접미사 추가 방지)
            parameters = self._correct_parameters(parameters, raw_entities)
            parameters = self._coerce_tolower_params(cypher, parameters)

            # 기본적인 쿼리 검증
            if not cypher or not cypher.strip():
                raise ValueError("Empty Cypher query generated")

            self._logger.info(f"Generated Cypher: {cypher[:100]}...")
            self._logger.debug(f"Parameters: {parameters}")

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

    def _filter_schema_for_policy(
        self,
        schema: GraphSchema,
        policy: AccessPolicy,
    ) -> GraphSchema:
        """
        접근 정책에 따라 스키마에서 허용되지 않은 라벨/관계를 제거

        이것은 최적화이지 보안 경계가 아님 — 보안은 GraphExecutor 필터링이 보장.
        LLM이 금지된 라벨로 쿼리를 생성하지 않도록 유도하는 역할.
        """
        allowed_labels = policy.get_allowed_labels()
        allowed_rels = policy.allowed_relationships

        filtered = GraphSchema(
            node_labels=[
                label for label in schema.get("node_labels", [])
                if label in allowed_labels
            ],
            relationship_types=[
                rel for rel in schema.get("relationship_types", [])
                if rel in allowed_rels
            ],
            nodes=[
                node for node in schema.get("nodes", [])
                if node.get("label") in allowed_labels
            ],
            relationships=[
                rel for rel in schema.get("relationships", [])
                if rel.get("type") in allowed_rels
            ],
            indexes=schema.get("indexes", []),
            constraints=schema.get("constraints", []),
        )

        self._logger.debug(
            f"Schema filtered: labels {len(schema.get('node_labels', []))}→{len(filtered['node_labels'])}, "
            f"rels {len(schema.get('relationship_types', []))}→{len(filtered['relationship_types'])}"
        )

        return filtered
