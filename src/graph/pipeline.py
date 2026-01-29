"""
Graph RAG Pipeline

LangGraph를 사용한 RAG 파이프라인 정의
- Vector Search 기반 캐싱: cache_checker 노드로 유사 질문 캐시 활용
- MemorySaver Checkpointer로 대화 기록 자동 관리
- 스키마는 초기화 시 주입 (런타임 조회 제거)
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

from src.config import Settings
from src.domain.ontology.hybrid_loader import HybridOntologyLoader
from src.domain.ontology.loader import OntologyLoader
from src.domain.types import GraphSchema, PipelineMetadata, PipelineResult
from src.graph.nodes import (
    CacheCheckerNode,
    ClarificationHandlerNode,
    ConceptExpanderNode,
    CypherGeneratorNode,
    EntityExtractorNode,
    EntityResolverNode,
    GraphExecutorNode,
    IntentClassifierNode,
    QueryDecomposerNode,
    ResponseGeneratorNode,
)
from src.graph.nodes.ontology_learner import OntologyLearner
from src.graph.state import GraphRAGState
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.repositories.query_cache_repository import QueryCacheRepository

logger = logging.getLogger(__name__)


class GraphRAGPipeline:
    """
    Graph RAG 파이프라인

    질문 → 의도분류 → 엔티티추출 → 개념확장 → 엔티티해석 → Cypher생성 → 쿼리실행 → 응답생성

    Note:
        - graph_schema는 앱 시작 시 한 번 로드하여 주입 (성능 최적화)
        - 스키마 미주입 시 CypherGenerator가 Neo4j에서 직접 조회 (fallback)
        - 스키마 변경 시 파이프라인 재생성 또는 앱 재시작 필요

    사용 예시:
        # 1. 스키마 사전 로드
        schema = await neo4j_repo.get_schema()

        # 2. 파이프라인 생성 (스키마 주입 권장)
        pipeline = GraphRAGPipeline(
            settings=settings,
            neo4j_repository=neo4j_repo,
            llm_repository=llm_repo,
            graph_schema=schema,
        )

        # 3. 실행
        result = await pipeline.run("홍길동의 부서는?", session_id="user-123")
    """

    def __init__(
        self,
        settings: Settings,
        neo4j_repository: Neo4jRepository,
        llm_repository: LLMRepository,
        neo4j_client: Neo4jClient | None = None,
        graph_schema: GraphSchema | None = None,
    ):
        self._settings = settings
        self._neo4j = neo4j_repository
        self._llm = llm_repository
        self._graph_schema = graph_schema  # 초기화 시 주입된 스키마

        # Query Cache Repository 초기화 (Vector Search 활성화 시)
        self._cache_repository: QueryCacheRepository | None = None
        if settings.vector_search_enabled and neo4j_client:
            self._cache_repository = QueryCacheRepository(neo4j_client, settings)
            logger.info("Query cache repository initialized")

        # 온톨로지 로더 초기화 (개념 확장용)
        self._ontology_loader: OntologyLoader | HybridOntologyLoader
        if settings.ontology_mode in ("neo4j", "hybrid"):
            if neo4j_client is None:
                logger.warning(
                    f"ontology_mode={settings.ontology_mode} but neo4j_client is None. "
                    "Falling back to YAML mode."
                )
                self._ontology_loader = OntologyLoader()
            else:
                self._ontology_loader = HybridOntologyLoader(
                    neo4j_client=neo4j_client, mode=settings.ontology_mode
                )
                logger.info(
                    f"HybridOntologyLoader initialized (mode={settings.ontology_mode})"
                )
        else:
            self._ontology_loader = OntologyLoader()
            logger.info("OntologyLoader initialized (YAML mode)")

        # 노드 초기화
        self._intent_classifier = IntentClassifierNode(llm_repository)
        self._query_decomposer = QueryDecomposerNode(llm_repository)
        self._entity_extractor = EntityExtractorNode(llm_repository)
        self._concept_expander = ConceptExpanderNode(self._ontology_loader)
        self._entity_resolver = EntityResolverNode(neo4j_repository)
        self._clarification_handler = ClarificationHandlerNode(llm_repository)
        self._cypher_generator = CypherGeneratorNode(
            llm_repository,
            neo4j_repository,
            cache_repository=self._cache_repository,
            settings=settings,
        )
        self._graph_executor = GraphExecutorNode(neo4j_repository)
        self._response_generator = ResponseGeneratorNode(llm_repository)

        # Cache Checker 노드 (Vector Search 활성화 시)
        self._cache_checker: CacheCheckerNode | None = None
        if settings.vector_search_enabled and self._cache_repository:
            self._cache_checker = CacheCheckerNode(
                llm_repository,
                self._cache_repository,
                settings,
            )
            logger.info("Cache checker node initialized")

        # Ontology Learner (Adaptive Ontology Phase 2)
        self._ontology_learner: OntologyLearner | None = None
        if settings.adaptive_ontology.enabled:
            self._ontology_learner = OntologyLearner(
                settings=settings.adaptive_ontology,
                llm_repository=llm_repository,
                neo4j_repository=neo4j_repository,
                ontology_loader=self._ontology_loader,
            )
            logger.info("OntologyLearner initialized (Adaptive Ontology enabled)")

        # 백그라운드 태스크 참조 저장 (GC 방지)
        self._background_tasks: set[asyncio.Task[Any]] = set()

        # MemorySaver Checkpointer (대화 기록 자동 관리)
        self._checkpointer = MemorySaver()

        # 그래프 빌드
        self._graph = self._build_graph()

        logger.info(
            "GraphRAGPipeline initialized "
            f"(vector cache: {settings.vector_search_enabled}, "
            f"schema injected: {graph_schema is not None}, checkpointer: MemorySaver)"
        )

    def _build_graph(self) -> CompiledStateGraph:
        """LangGraph 워크플로우 구성 (Vector Cache + Checkpointer)"""
        workflow = StateGraph(GraphRAGState)

        # 노드 추가 (schema_fetcher 제거됨 - 스키마는 초기화 시 주입)
        workflow.add_node("intent_classifier", self._intent_classifier)
        workflow.add_node("query_decomposer", self._query_decomposer)
        workflow.add_node("entity_extractor", self._entity_extractor)
        workflow.add_node("concept_expander", self._concept_expander)
        workflow.add_node("entity_resolver", self._entity_resolver)
        workflow.add_node("clarification_handler", self._clarification_handler)
        workflow.add_node("cypher_generator", self._cypher_generator)
        workflow.add_node("graph_executor", self._graph_executor)
        workflow.add_node("response_generator", self._response_generator)

        # Cache Checker 노드 추가 (Vector Search 활성화 시)
        if self._cache_checker:
            workflow.add_node("cache_checker", self._cache_checker)

        # 시작점 설정
        workflow.set_entry_point("intent_classifier")

        # ---------------------------------------------------------
        # 조건부 엣지 정의 (Conditional Edges)
        # ---------------------------------------------------------

        # 1. Intent Classifier -> Query Decomposer 또는 Response Generator
        def route_after_intent(
            state: GraphRAGState,
        ) -> Literal["query_decomposer", "response_generator"]:
            if state.get("intent") == "unknown":
                logger.info("Intent is unknown. Skipping to response generator.")
                return "response_generator"
            return "query_decomposer"

        workflow.add_conditional_edges(
            "intent_classifier",
            route_after_intent,
            ["query_decomposer", "response_generator"],
        )

        # 2. Query Decomposer -> Cache Checker 또는 Entity Extractor
        if self._cache_checker:
            # Vector Cache 활성화 시: query_decomposer -> cache_checker
            workflow.add_edge("query_decomposer", "cache_checker")

            # 2. Cache Checker -> 캐시 히트 시 cypher_generator, 미스 시 entity_extractor
            def route_after_cache_check(
                state: GraphRAGState,
            ) -> Literal["cypher_generator", "entity_extractor"]:
                """
                캐시 결과에 따라 라우팅:
                - cache_hit=True: cypher_generator로 이동 (캐시된 쿼리 사용)
                - cache_hit=False: entity_extractor로 이동
                """
                if state.get("skip_generation"):
                    logger.info(
                        "Cache HIT: skipping to cypher_generator (cached query)"
                    )
                    return "cypher_generator"

                logger.info("Cache MISS: proceeding to entity_extractor")
                return "entity_extractor"

            workflow.add_conditional_edges(
                "cache_checker",
                route_after_cache_check,
                ["entity_extractor", "cypher_generator"],
            )
        else:
            # Vector Cache 비활성화 시: query_decomposer -> entity_extractor
            workflow.add_edge("query_decomposer", "entity_extractor")

        # 2. Entity Extractor -> Concept Expander -> Entity Resolver (순차 실행)
        workflow.add_edge("entity_extractor", "concept_expander")
        workflow.add_edge("concept_expander", "entity_resolver")

        # 3. Entity Resolver -> Cypher Generator 또는 Clarification Handler
        def route_after_resolver(
            state: GraphRAGState,
        ) -> Literal["cypher_generator", "clarification_handler", "response_generator"]:
            # 에러가 있는 경우 response_generator로 직접 이동
            if state.get("error"):
                return "response_generator"

            # 미해결 엔티티가 있는 경우 명확화 요청
            resolved_entities = state.get("resolved_entities", [])
            has_unresolved = any(not entity.get("id") for entity in resolved_entities)
            if has_unresolved:
                logger.info(
                    "Unresolved entities found. Routing to clarification_handler."
                )
                return "clarification_handler"

            return "cypher_generator"

        workflow.add_conditional_edges(
            "entity_resolver",
            route_after_resolver,
            {
                "cypher_generator": "cypher_generator",
                "clarification_handler": "clarification_handler",
                "response_generator": "response_generator",
            },
        )

        # 4. Cypher Generator -> Graph Executor 또는 에러 처리
        def route_after_cypher(
            state: GraphRAGState,
        ) -> Literal["graph_executor", "response_generator"]:
            if state.get("error") or not state.get("cypher_query"):
                logger.warning("Cypher generation failed. Skipping execution.")
                return "response_generator"
            return "graph_executor"

        workflow.add_conditional_edges(
            "cypher_generator",
            route_after_cypher,
            {
                "graph_executor": "graph_executor",
                "response_generator": "response_generator",
            },
        )

        # 5. Graph Executor -> Response Generator
        # (ResponseGenerator 내부에서 empty results나 error를 처리하므로 바로 연결)
        workflow.add_edge("graph_executor", "response_generator")

        # 6. Clarification Handler -> END (명확화 요청 후 종료)
        workflow.add_edge("clarification_handler", END)

        # 7. Response Generator -> END
        workflow.add_edge("response_generator", END)

        # Checkpointer와 함께 컴파일 (세션별 대화 기록 자동 관리)
        return workflow.compile(checkpointer=self._checkpointer)

    async def run(
        self,
        question: str,
        session_id: str | None = None,
        return_full_state: bool = False,
    ) -> PipelineResult:
        """
        파이프라인 실행

        Args:
            question: 사용자 질문
            session_id: 세션 ID (대화 기록 유지를 위해 필요)
            return_full_state: True면 graph_results, original_entities 등 추가 데이터 포함

        Returns:
            파이프라인 실행 결과
        """
        logger.info(f"Running pipeline for: {question[:50]}...")

        # thread_id로 세션 구분 (Checkpointer가 대화 기록 자동 관리)
        thread_id = session_id or "default"
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        # 초기 상태 구성 (스키마 포함)
        initial_state: GraphRAGState = {
            "question": question,
            "session_id": session_id or "",
            "messages": [HumanMessage(content=question)],
            "execution_path": [],
        }
        if self._graph_schema:
            initial_state["schema"] = self._graph_schema

        try:
            # 파이프라인 실행
            # (AIMessage는 ResponseGenerator/ClarificationHandler 노드에서 직접 추가됨)
            final_state = await self._graph.ainvoke(initial_state, config=config)

            response_text = final_state.get("response", "")

            # expanded_entities 우선 사용 (명시적 None 체크)
            entities_for_metadata = final_state.get("expanded_entities")
            if entities_for_metadata is None:
                entities_for_metadata = final_state.get("entities", {})

            # query_plan 변환 (TypedDict -> dict)
            query_plan_raw = final_state.get("query_plan")
            query_plan_dict = dict(query_plan_raw) if query_plan_raw else None

            metadata: PipelineMetadata = {
                "intent": final_state.get("intent", "unknown"),
                "intent_confidence": final_state.get("intent_confidence", 0.0),
                "entities": entities_for_metadata,
                "resolved_entities": final_state.get("resolved_entities", []),
                "cypher_query": final_state.get("cypher_query", ""),
                "cypher_parameters": final_state.get("cypher_parameters", {}),
                "result_count": final_state.get("result_count", 0),
                "execution_path": final_state.get("execution_path", []),
                "query_plan": query_plan_dict,
                "error": final_state.get("error"),
            }

            # Explainability: full_state 추가 (요청 시에만)
            if return_full_state:
                metadata["_full_state"] = {
                    "original_entities": final_state.get("entities", {}),
                    "expanded_entities": final_state.get("expanded_entities", {}),
                    "expansion_strategy": final_state.get("expansion_strategy"),
                    "expansion_count": final_state.get("expansion_count", 0),
                    "graph_results": final_state.get("graph_results", []),
                }

            # Adaptive Ontology: 미해결 엔티티 백그라운드 학습 트리거
            unresolved_entities = final_state.get("unresolved_entities", [])
            if unresolved_entities and self._ontology_learner:
                # Task 참조를 set에 저장하여 GC 방지 (fire-and-forget 패턴)
                task = asyncio.create_task(
                    self._safe_process_unresolved(
                        unresolved_entities,
                        self._graph_schema,
                    ),
                    name="ontology_learning",
                )
                # 참조 저장 및 완료 시 자동 제거
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            return {
                "success": True,
                "question": question,
                "response": response_text,
                "metadata": metadata,
                "error": final_state.get("error"),
            }

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            return {
                "success": False,
                "question": question,
                "response": f"죄송합니다. 질문을 처리하는 중 오류가 발생했습니다: {e}",
                "metadata": {},
                "error": str(e),
            }

    async def run_with_streaming(
        self,
        question: str,
        session_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        스트리밍 모드로 파이프라인 실행

        각 노드 완료 시 중간 결과를 yield합니다.

        Args:
            question: 사용자 질문
            session_id: 세션 ID

        Yields:
            각 노드의 실행 결과
        """
        logger.info(f"Running pipeline (streaming) for: {question[:50]}...")

        # thread_id로 세션 구분 (Checkpointer가 대화 기록 자동 관리)
        thread_id = session_id or "default"
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        # 초기 상태 구성 (스키마 포함)
        initial_state: GraphRAGState = {
            "question": question,
            "session_id": session_id or "",
            "messages": [HumanMessage(content=question)],
            "execution_path": [],
        }
        if self._graph_schema:
            initial_state["schema"] = self._graph_schema

        try:
            # 파이프라인 스트리밍 실행
            # (AIMessage는 ResponseGenerator/ClarificationHandler 노드에서 직접 추가됨)
            async for event in self._graph.astream(initial_state, config=config):
                # 각 노드의 출력을 yield
                for node_name, node_output in event.items():
                    yield {
                        "node": node_name,
                        "output": node_output,
                    }

        except Exception as e:
            logger.error(f"Pipeline streaming failed: {e}")
            yield {
                "node": "error",
                "output": {"error": str(e)},
            }

    async def _safe_process_unresolved(
        self,
        unresolved: list[Any],
        schema: GraphSchema | None,
    ) -> None:
        """
        미해결 엔티티 백그라운드 학습 (안전한 래퍼)

        예외 발생 시 로그만 남기고 스킵합니다.
        메인 파이프라인 응답에 영향을 주지 않습니다.

        Args:
            unresolved: 미해결 엔티티 리스트
            schema: 현재 그래프 스키마
        """
        if not self._ontology_learner:
            return

        try:
            # GraphSchema를 dict로 안전하게 변환
            schema_dict: dict[str, Any] | None = None
            if schema:
                try:
                    schema_dict = dict(schema)
                except Exception as e:
                    logger.warning(f"Failed to convert schema to dict: {e}")

            await self._ontology_learner.process_unresolved(unresolved, schema_dict)
        except Exception as e:
            logger.warning(f"Background ontology learning failed: {e}")
