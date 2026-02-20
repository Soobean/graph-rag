"""
Graph RAG 파이프라인 상태 정의

LangGraph의 상태 관리를 위한 TypedDict 정의
- ARCHITECTURE.md의 3.1 섹션 준수
- Annotated를 활용한 State Reducer 적용
- Checkpointer를 통한 대화 기록 자동 관리
"""

import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from src.auth.models import UserContext
from src.domain.types import GraphSchema, QueryPlan, ResolvedEntity, UnresolvedEntity

# 하위 호환: constants.py로 이동한 심볼을 re-export
from src.graph.constants import (  # noqa: F401
    AGGREGATE_INTENTS,
    AVAILABLE_INTENTS,
    DEFAULT_ENTITY_TYPES,
    IntentType,
)


class GraphRAGState(TypedDict, total=False):
    """
    GraphRAG 시스템의 전체 상태

    ARCHITECTURE.md 3.1 참조
    """

    # ── 1. 입력 (Input) ────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]  # LangGraph Native History
    question: str
    session_id: str

    # ── 2. Query Understanding ─────────────────────────
    intent: IntentType
    intent_confidence: float
    entities: dict[str, list[str]]  # 예: {'skills': ['Python'], 'names': ['김철수']}
    expanded_entities: dict[str, list[str]]  # 온톨로지 확장된 엔티티
    resolved_entities: list[ResolvedEntity]  # Neo4j에서 매칭된 엔티티 정보
    unresolved_entities: list[UnresolvedEntity]  # 미해결 엔티티 (Adaptive Ontology)
    query_plan: QueryPlan  # Multi-hop 쿼리 분해 계획

    # ── 2a. Concept Expansion 메타데이터 ───────────────
    # ConceptExpanderNode가 반환, EntityResolver·ExplainabilityService가 참조
    expanded_entities_by_original: dict[str, dict[str, list[str]]]  # 원본별 확장 매핑
    original_entities: dict[str, list[str]]  # 확장 전 원본 엔티티
    expansion_count: int  # 확장된 개념 수
    expansion_strategy: Literal["strict", "normal", "broad"]  # 사용된 확장 전략

    # ── 3. Graph Retrieval ─────────────────────────────
    schema: GraphSchema  # 그래프 스키마 정보
    cypher_query: str
    cypher_parameters: dict[str, Any]
    graph_results: list[dict[str, Any]]
    result_count: int

    # ── 4. Response ────────────────────────────────────
    response: str

    # ── 5. 메타데이터 및 에러 처리 ─────────────────────
    error: str | None
    execution_path: Annotated[list[str], operator.add]  # 각 노드가 append

    # ── 6. Vector Search / Cache ───────────────────────
    question_embedding: list[float] | None
    cache_hit: bool
    cache_score: float
    skip_generation: bool  # 캐시 히트 시 Cypher 생성 스킵

    # ── 7. 접근 제어 (Access Control) ──────────────────
    user_context: UserContext | None
