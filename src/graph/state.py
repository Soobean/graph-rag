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

# ARCHITECTURE.md에 정의된 7가지 Intent Type + ontology_update + unknown
IntentType = Literal[
    "personnel_search",  # A. 인력 추천
    "project_matching",  # B. 프로젝트 매칭
    "relationship_search",  # C. 관계 탐색
    "org_analysis",  # D. 조직 분석
    "mentoring_network",  # E. 멘토링 네트워크
    "certificate_search",  # F. 자격증 기반 검색
    "path_analysis",  # G. 경로 기반 분석
    "ontology_update",  # H. 온톨로지 업데이트 요청 (사용자 주도)
    "global_analysis",  # I. 거시적 분석 (커뮤니티 요약 기반)
    "unknown",  # 분류 불가
]

# Intent 분류에 사용 가능한 의도 목록 (unknown 제외)
AVAILABLE_INTENTS: list[str] = [
    "personnel_search",
    "project_matching",
    "relationship_search",
    "org_analysis",
    "mentoring_network",
    "certificate_search",
    "path_analysis",
    "ontology_update",
    "global_analysis",
]

# 특정 엔티티 없이도 Cypher 생성이 가능한 집계/통계 intent
# (route_after_resolver에서 전부 unresolved여도 clarification 대신 cypher_generator로 진행)
AGGREGATE_INTENTS: set[str] = {
    "global_analysis",
    "org_analysis",
    "mentoring_network",
    "certificate_search",
}

# 기본 엔티티 타입 (Neo4j 라벨과 일치)
DEFAULT_ENTITY_TYPES: list[str] = [
    "Employee",
    "Organization",
    "Department",
    "Position",
    "Project",
    "Skill",
    "Location",
    "Date",
]


class GraphRAGState(TypedDict, total=False):
    """
    GraphRAG 시스템의 전체 상태

    ARCHITECTURE.md 3.1 참조
    """

    # 1. 입력 (Input)
    messages: Annotated[list[BaseMessage], add_messages]  # LangGraph Native History
    question: str
    session_id: str

    # 2. Query Understanding (의도 분석 및 엔티티 추출)
    intent: IntentType
    intent_confidence: float
    entities: dict[str, list[str]]  # 예: {'skills': ['Python'], 'names': ['김철수']}
    expanded_entities: dict[str, list[str]]  # 온톨로지 확장된 엔티티
    resolved_entities: list[ResolvedEntity]  # Neo4j에서 매칭된 엔티티 정보
    unresolved_entities: list[UnresolvedEntity]  # 미해결 엔티티 (Adaptive Ontology)
    query_plan: QueryPlan  # Multi-hop 쿼리 분해 계획

    # 3. Graph Retrieval (검색 단계)
    schema: GraphSchema  # 그래프 스키마 정보
    cypher_query: str
    cypher_parameters: dict[str, Any]  # Cypher 파라미터는 동적
    graph_results: list[dict[str, Any]]  # Neo4j 쿼리 결과는 동적
    result_count: int

    # 4. Context & Response (응답 생성)
    context: str
    response: str

    # 5. 메타데이터 및 에러 처리
    error: str | None

    # 실행 경로 추적 (Reducer 사용)
    # 각 노드에서 ["node_name"]을 리턴하면 기존 리스트에 append 됨
    execution_path: Annotated[list[str], operator.add]

    # 6. Vector Search / Cache 관련 필드
    question_embedding: list[float] | None  # 질문 임베딩 벡터
    cache_hit: bool  # 캐시 히트 여부
    cache_score: float  # 캐시 유사도 점수
    skip_generation: bool  # Cypher 생성 스킵 여부 (캐시 히트 시)

    # 7. 접근 제어 (Access Control)
    user_context: UserContext | None
