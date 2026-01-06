"""
Graph RAG 파이프라인 상태 정의

LangGraph의 상태 관리를 위한 TypedDict 정의
- ARCHITECTURE.md의 3.1 섹션 준수
- Annotated를 활용한 State Reducer 적용
"""

import operator
from typing import Annotated, Any, Literal, TypedDict

from src.domain.types import GraphSchema, ResolvedEntity

# ARCHITECTURE.md에 정의된 7가지 Intent Type + unknown
IntentType = Literal[
    "personnel_search",  # A. 인력 추천
    "project_matching",  # B. 프로젝트 매칭
    "relationship_search",  # C. 관계 탐색
    "org_analysis",  # D. 조직 분석
    "mentoring_network",  # E. 멘토링 네트워크
    "certificate_search",  # F. 자격증 기반 검색
    "path_analysis",  # G. 경로 기반 분석
    "unknown",  # 분류 불가
]


class GraphRAGState(TypedDict, total=False):
    """
    GraphRAG 시스템의 전체 상태

    ARCHITECTURE.md 3.1 참조
    """

    # 1. 입력 (Input)
    question: str
    session_id: str

    # 2. Query Understanding (의도 분석 및 엔티티 추출)
    intent: IntentType
    intent_confidence: float
    entities: dict[str, list[str]]  # 예: {'skills': ['Python'], 'names': ['김철수']}
    resolved_entities: list[ResolvedEntity]  # Neo4j에서 매칭된 엔티티 정보

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
