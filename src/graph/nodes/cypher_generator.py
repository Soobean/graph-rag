"""
Cypher Generator Node

사용자 질문과 엔티티 정보를 바탕으로 Cypher 쿼리를 생성합니다.
캐시 히트 시에는 생성을 스킵합니다. (캐시 저장은 GraphExecutor에서 실행 성공 후 수행)

모델 선택 정책:
- HEAVY 우선, 실패 시 LIGHT로 fallback (AzureOpenAIGateway.generate_json_with_fallback)
- 이전의 정적 휴리스틱 기반 LIGHT 분기는 false negative가 잦아 제거됨
  (시나리오: entity 1개라 'SIMPLE'로 분류됐지만 실제 쿼리는 복잡한 조건 다수)
- 미래에 모델 비용/지연 분리가 다시 필요해지면, 휴리스틱이 아닌 실측 메트릭
  (Eval 점수, 응답 시간)에 근거해 재도입
"""

from typing import Any

from src.application.llm import LLMTaskService
from src.auth.access_policy import AccessPolicy
from src.config import Settings
from src.domain.cypher import corrections
from src.domain.exceptions import LLMContentFilterError
from src.domain.types import CypherGeneratorUpdate, GraphSchema
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.neo4j_repository import Neo4jRepository


class CypherGeneratorNode(BaseNode[CypherGeneratorUpdate]):
    """Cypher 쿼리 생성 노드. HEAVY 모델 우선, LIGHT로 fallback."""

    def __init__(
        self,
        llm_tasks: LLMTaskService,
        neo4j_repository: Neo4jRepository,
        settings: Settings | None = None,
    ):
        super().__init__()
        self._llm = llm_tasks
        self._neo4j = neo4j_repository
        # settings는 현재 사용되지 않지만, Phase 4 (Query 컨텍스트 마이그레이션) 시
        # temperature/max_tokens override 등으로 재사용 가능성 있어 시그니처 유지.
        # 호출자(pipeline.py)는 이미 settings=settings로 전달 중.
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

    # ------------------------------------------------------------------
    # Cypher 교정 규칙은 src/domain/cypher/corrections.py로 이전됨.
    # 아래 위임 메서드들은 과도기용 — 다음 커밋에서 apply_corrections() 직접
    # 호출로 교체 후 제거된다.
    # ------------------------------------------------------------------

    def _correct_parameters(
        self,
        parameters: dict[str, Any],
        entities: dict[str, list[str]],
    ) -> dict[str, Any]:
        """파라미터 값 보정 (도메인 모델 위임)"""
        return corrections.correct_parameters(parameters, entities)

    def _fix_not_in_syntax(self, cypher: str) -> str:
        """SQL식 NOT IN 문법 교정 (도메인 모델 위임)"""
        return corrections.fix_not_in_syntax(cypher)

    def _fix_in_clause_to_tolower(self, cypher: str) -> str:
        """IN 절 case-insensitive 변환 (도메인 모델 위임)"""
        return corrections.fix_in_clause_to_tolower(cypher)

    def _fix_aggregation_type_a_return(self, cypher: str) -> str:
        """집계 후 TYPE A RETURN 안티패턴 교정 (도메인 모델 위임)"""
        return corrections.fix_aggregation_type_a_return(cypher)

    def _coerce_tolower_params(
        self,
        cypher: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """toLower 파라미터 타입 강제 (도메인 모델 위임)"""
        return corrections.coerce_tolower_params(cypher, parameters)

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
        # LLMTaskService.generate_cypher는 list[dict]를 기대함.
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

            # LLM을 통한 Cypher 생성 (HEAVY 우선 + LIGHT fallback)
            intent = state.get("intent", "unknown")
            result = await self._llm.generate_cypher(
                question=question,
                schema=dict(schema),  # TypedDict를 dict로 변환
                entities=formatted_entities,
                query_plan=dict(query_plan)
                if query_plan
                else None,  # Multi-hop 쿼리 계획 전달
                intent=intent,
            )

            cypher = result.get("cypher", "")
            parameters = result.get("parameters", {})

            # Cypher 문법 보정 (SQL-style NOT IN → Cypher NOT ... IN)
            cypher = self._fix_not_in_syntax(cypher)

            # IN 절 case-insensitive 보정 (s.name IN $list → ANY ... toLower)
            cypher = self._fix_in_clause_to_tolower(cypher)

            # 집계 후 TYPE A 반환 안티패턴 보정
            cypher = self._fix_aggregation_type_a_return(cypher)

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

        except LLMContentFilterError as e:
            # Content Filter는 raw 메시지 노출 금지 — 친화적 메시지만 전달
            self._logger.warning(
                f"Cypher generation blocked by content filter: "
                f"param={e.param}, categories={e.categories}"
            )
            return CypherGeneratorUpdate(
                cypher_query="",
                cypher_parameters={},
                error=e.message,
                execution_path=[f"{self.name}_content_filter"],
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
                label
                for label in schema.get("node_labels", [])
                if label in allowed_labels
            ],
            relationship_types=[
                rel
                for rel in schema.get("relationship_types", [])
                if rel in allowed_rels
            ],
            nodes=[
                node
                for node in schema.get("nodes", [])
                if node.get("label") in allowed_labels
            ],
            relationships=[
                rel
                for rel in schema.get("relationships", [])
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
