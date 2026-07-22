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


    @staticmethod
    def _build_error_feedback(state: GraphRAGState) -> str:
        """Self-Correction 재생성용 에러 피드백 텍스트 조립.

        이전 실행이 SyntaxError로 실패한 경우(state.cypher_error 존재)에만
        내용을 만들고, 최초 생성 시에는 빈 문자열을 반환한다
        (프롬프트 {error_feedback} placeholder가 빈 값으로 채워짐).
        """
        cypher_error = state.get("cypher_error")
        if not cypher_error:
            return ""

        failed_cypher = state.get("failed_cypher", "") or ""
        return (
            "\n⚠️ PREVIOUS ATTEMPT FAILED — FIX THE ERROR:\n"
            "The previous query failed with this Neo4j error:\n"
            f"{cypher_error}\n\n"
            "Failed query:\n"
            f"{failed_cypher}\n\n"
            "Generate a corrected query. Do NOT repeat the same mistake. "
            "Use only valid Neo4j Cypher syntax (no SQL window functions like "
            "OVER(), no map-property access inside MATCH patterns)."
        )

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
        # 주: 캐시 쿼리가 SyntaxError로 실패하면 GraphExecutor가
        # skip_generation=False로 클리어하므로 재시도 시 실제 재생성됨
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

            # Self-Correction: 이전 실행이 SyntaxError로 실패했으면 피드백 조립
            error_feedback = self._build_error_feedback(state)
            if error_feedback:
                self._logger.info(
                    f"Regenerating Cypher with error feedback "
                    f"(retry #{state.get('cypher_retry_count', 0)})"
                )

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
                error_feedback=error_feedback,
            )

            # Cypher/파라미터 교정 (도메인 규칙 일괄 적용 — 순서 불변식은
            # src/domain/cypher/corrections.py docstring 참고)
            cypher, parameters = corrections.apply_corrections(
                cypher=result.get("cypher", ""),
                parameters=result.get("parameters", {}),
                entities=raw_entities,
            )

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
                # Self-Correction: 재생성 성공 시 stale error/힌트 클리어
                # (남겨두면 route_after_cypher가 즉시 response_generator로 빠짐)
                error=None,
                cypher_error=None,
                failed_cypher=None,
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
