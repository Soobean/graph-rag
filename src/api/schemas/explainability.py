"""
Explainability API Schemas

AI 추론 과정 설명 및 그래프 시각화를 위한 스키마
- ThoughtStep: 개별 추론 단계
- ConceptExpansionTree: 개념 확장 트리
- ExplainableGraphData: 그래프 시각화 데이터
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.api.schemas.visualization import GraphEdge, GraphNode

# =============================================================================
# 추론 단계 (Thought Process)
# =============================================================================


class ThoughtStep(BaseModel):
    """파이프라인 추론 단계"""

    step_number: int = Field(..., description="단계 번호 (1부터 시작)")
    node_name: str = Field(..., description="노드 이름 (intent_classifier 등)")
    step_type: Literal[
        "classification",  # Intent 분류
        "decomposition",  # 쿼리 분해
        "extraction",  # 엔티티 추출
        "expansion",  # 개념 확장
        "resolution",  # 엔티티 해석
        "generation",  # Cypher 생성
        "execution",  # 쿼리 실행
        "response",  # 응답 생성
        "cache",  # 캐시 확인
    ] = Field(..., description="단계 유형")
    description: str = Field(..., description="단계 설명 (한국어)")
    input_summary: str | None = Field(None, description="입력 요약")
    output_summary: str | None = Field(None, description="출력 요약")
    details: dict[str, Any] = Field(default_factory=dict, description="추가 세부 정보")
    duration_ms: float | None = Field(None, description="실행 시간 (밀리초)")


class ConceptExpansionTree(BaseModel):
    """개념 확장 트리 시각화"""

    original_concept: str = Field(..., description="원본 개념")
    entity_type: str = Field(default="Skill", description="엔티티 타입")
    expansion_strategy: Literal["strict", "normal", "broad"] = Field(
        ..., description="확장 전략"
    )
    expanded_concepts: list[str] = Field(
        default_factory=list, description="확장된 개념 목록"
    )
    expansion_path: list[dict[str, str]] = Field(
        default_factory=list,
        description="확장 경로 [{from, to, relation}]",
    )


class ThoughtProcessVisualization(BaseModel):
    """추론 과정 시각화 데이터"""

    steps: list[ThoughtStep] = Field(default_factory=list, description="추론 단계 목록")
    concept_expansions: list[ConceptExpansionTree] = Field(
        default_factory=list, description="개념 확장 트리 목록"
    )
    total_duration_ms: float | None = Field(None, description="총 실행 시간")
    execution_path: list[str] = Field(default_factory=list, description="실행 경로")


# =============================================================================
# 그래프 데이터 (Interactive Graph)
# =============================================================================


class ExplainableGraphData(BaseModel):
    """설명 가능한 그래프 데이터"""

    nodes: list[GraphNode] = Field(default_factory=list, description="그래프 노드")
    edges: list[GraphEdge] = Field(default_factory=list, description="그래프 엣지")
    node_count: int = Field(0, description="노드 수")
    edge_count: int = Field(0, description="엣지 수")

    # 역할별 노드 ID 분류 (프론트엔드에서 색상 구분용)
    query_entity_ids: list[str] = Field(
        default_factory=list, description="쿼리 엔티티 노드 ID (파란색)"
    )
    expanded_entity_ids: list[str] = Field(
        default_factory=list, description="확장된 엔티티 노드 ID (초록색)"
    )
    result_entity_ids: list[str] = Field(
        default_factory=list, description="결과 엔티티 노드 ID (주황색)"
    )

    # 페이지네이션
    has_more: bool = Field(False, description="추가 데이터 존재 여부")
    cursor: str | None = Field(None, description="다음 페이지 커서")


# =============================================================================
# 통합 응답 (ExplainableResponse)
# =============================================================================


class ExplainableResponse(BaseModel):
    """설명 가능한 응답 (QueryResponse 확장용)"""

    thought_process: ThoughtProcessVisualization | None = Field(
        None, description="추론 과정 시각화"
    )
    graph_data: ExplainableGraphData | None = Field(
        None, description="그래프 시각화 데이터"
    )
