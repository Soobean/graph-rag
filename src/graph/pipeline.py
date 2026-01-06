"""
Graph RAG Pipeline

LangGraph를 사용한 RAG 파이프라인 정의
- 병렬 실행: entity_extractor + schema_fetcher (Send API 사용)
"""

import logging
from typing import Literal

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from src.config import Settings
from src.domain.types import PipelineMetadata, PipelineResult
from src.graph.nodes import (
    ClarificationHandlerNode,
    CypherGeneratorNode,
    EntityExtractorNode,
    EntityResolverNode,
    GraphExecutorNode,
    IntentClassifierNode,
    ResponseGeneratorNode,
    SchemaFetcherNode,
)
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)


class GraphRAGPipeline:
    """
    Graph RAG 파이프라인

    질문 → 의도분류 → 엔티티추출 → 엔티티해석 → Cypher생성 → 쿼리실행 → 응답생성

    사용 예시:
        pipeline = GraphRAGPipeline(settings, neo4j_repo, llm_repo)
        result = await pipeline.run("홍길동의 부서는 어디인가요?")
    """

    def __init__(
        self,
        settings: Settings,
        neo4j_repository: Neo4jRepository,
        llm_repository: LLMRepository,
    ):
        self._settings = settings
        self._neo4j = neo4j_repository
        self._llm = llm_repository

        # 노드 초기화
        self._intent_classifier = IntentClassifierNode(llm_repository)
        self._entity_extractor = EntityExtractorNode(llm_repository)
        self._schema_fetcher = SchemaFetcherNode(neo4j_repository)  # 병렬 실행용
        self._entity_resolver = EntityResolverNode(neo4j_repository)
        self._clarification_handler = ClarificationHandlerNode(llm_repository)
        self._cypher_generator = CypherGeneratorNode(llm_repository, neo4j_repository)
        self._graph_executor = GraphExecutorNode(neo4j_repository)
        self._response_generator = ResponseGeneratorNode(llm_repository)

        # 그래프 빌드
        self._graph = self._build_graph()

        logger.info("GraphRAGPipeline initialized (with parallel execution)")

    def _build_graph(self) -> StateGraph:
        """LangGraph 워크플로우 구성 (병렬 실행 포함)"""
        workflow = StateGraph(GraphRAGState)

        # 노드 추가
        workflow.add_node("intent_classifier", self._intent_classifier)
        workflow.add_node("entity_extractor", self._entity_extractor)
        workflow.add_node("schema_fetcher", self._schema_fetcher)  # 병렬 실행용
        workflow.add_node("entity_resolver", self._entity_resolver)
        workflow.add_node("clarification_handler", self._clarification_handler)
        workflow.add_node("cypher_generator", self._cypher_generator)
        workflow.add_node("graph_executor", self._graph_executor)
        workflow.add_node("response_generator", self._response_generator)

        # 시작점 설정
        workflow.set_entry_point("intent_classifier")

        # ---------------------------------------------------------
        # 조건부 엣지 정의 (Conditional Edges)
        # ---------------------------------------------------------

        # 1. Intent Classifier -> 병렬(Entity Extractor + Schema Fetcher) 또는 종료
        def route_after_intent(
            state: GraphRAGState,
        ) -> list[Send] | Literal["response_generator"]:
            """
            Intent에 따라 라우팅:
            - unknown: response_generator로 직접 이동
            - 유효한 intent: entity_extractor와 schema_fetcher 병렬 실행
            """
            if state.get("intent") == "unknown":
                logger.info("Intent is unknown. Skipping to response generator.")
                return "response_generator"

            # 병렬 실행: Send API 사용
            logger.info("Dispatching parallel execution: entity_extractor + schema_fetcher")
            return [
                Send("entity_extractor", state),
                Send("schema_fetcher", state),
            ]

        workflow.add_conditional_edges(
            "intent_classifier",
            route_after_intent,
            ["entity_extractor", "schema_fetcher", "response_generator"],
        )

        # 2. 병렬 노드들 -> Entity Resolver로 수렴 (Fan-in)
        workflow.add_edge("entity_extractor", "entity_resolver")
        workflow.add_edge("schema_fetcher", "entity_resolver")

        # 3. Entity Resolver -> Cypher Generator 또는 Clarification Handler
        def route_after_resolver(
            state: GraphRAGState,
        ) -> Literal["cypher_generator", "clarification_handler", "response_generator"]:
            # 에러가 있는 경우 response_generator로 직접 이동
            if state.get("error"):
                return "response_generator"

            # 미해결 엔티티가 있는 경우 명확화 요청
            resolved_entities = state.get("resolved_entities", [])
            has_unresolved = any(
                not entity.get("id") for entity in resolved_entities
            )
            if has_unresolved:
                logger.info("Unresolved entities found. Routing to clarification_handler.")
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

        return workflow.compile()

    async def run(
        self,
        question: str,
        session_id: str | None = None,
    ) -> PipelineResult:
        """
        파이프라인 실행

        Args:
            question: 사용자 질문
            session_id: 세션 ID (선택)

        Returns:
            파이프라인 실행 결과
        """
        logger.info(f"Running pipeline for: {question[:50]}...")

        initial_state: GraphRAGState = {
            "question": question,
            "session_id": session_id or "",
            "execution_path": [],
        }

        try:
            # 파이프라인 실행
            final_state = await self._graph.ainvoke(initial_state)

            metadata: PipelineMetadata = {
                "intent": final_state.get("intent", "unknown"),
                "intent_confidence": final_state.get("intent_confidence", 0.0),
                "entities": final_state.get("entities", {}),
                "resolved_entities": final_state.get("resolved_entities", []),
                "cypher_query": final_state.get("cypher_query", ""),
                "cypher_parameters": final_state.get("cypher_parameters", {}),
                "result_count": final_state.get("result_count", 0),
                "execution_path": final_state.get("execution_path", []),
                "error": final_state.get("error"),
            }

            return {
                "success": True,
                "question": question,
                "response": final_state.get("response", ""),
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
    ):
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

        initial_state: GraphRAGState = {
            "question": question,
            "session_id": session_id or "",
            "execution_path": [],
        }

        try:
            async for event in self._graph.astream(initial_state):
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
