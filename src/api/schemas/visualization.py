"""
Visualization API Schemas

그래프 시각화 API의 요청/응답 스키마
"""

from typing import Any

from pydantic import BaseModel, Field


class NodeStyle(BaseModel):
    """노드 스타일"""

    color: str
    icon: str
    size: float = 1.0


class GraphNode(BaseModel):
    """그래프 노드"""

    id: str = Field(..., description="노드 고유 ID")
    label: str = Field(..., description="노드 라벨 (Employee, Skill, etc.)")
    name: str = Field(..., description="노드 이름")
    properties: dict[str, Any] = Field(default_factory=dict, description="추가 속성")
    group: str | None = Field(default=None, description="시각화 그룹 (색상 구분용)")
    role: str | None = Field(
        default=None,
        description="노드 역할 (start: 시작점, end: 결과, intermediate: 중간)",
    )
    depth: int = Field(
        default=0,
        description="홉 깊이 (0=쿼리 엔티티, 1=첫번째 홉, ..., max=결과)",
    )
    style: NodeStyle | None = Field(
        default=None, description="노드 스타일 (Palantir-style)"
    )
    x: float = Field(default=0.0, description="초기 X 좌표")
    y: float = Field(default=0.0, description="초기 Y 좌표")


class GraphEdge(BaseModel):
    """그래프 엣지"""

    id: str = Field(..., description="엣지 고유 ID")
    source: str = Field(..., description="시작 노드 ID")
    target: str = Field(..., description="끝 노드 ID")
    label: str = Field(..., description="관계 타입")
    properties: dict = Field(default_factory=dict, description="추가 속성")


class SubgraphResponse(BaseModel):
    """서브그래프 응답"""

    success: bool = True
    center_node_id: str = Field(..., description="중심 노드 ID")
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    node_count: int = Field(default=0)
    edge_count: int = Field(default=0)


class SubgraphRequest(BaseModel):
    """서브그래프 요청"""

    node_id: str | None = Field(default=None, description="중심 노드 ID")
    node_name: str | None = Field(default=None, description="중심 노드 이름")
    node_label: str | None = Field(default=None, description="노드 라벨 필터")
    depth: int = Field(default=1, ge=1, le=3, description="탐색 깊이 (1-3)")
    limit: int = Field(default=50, ge=1, le=200, description="최대 노드 수")


class CommunityGraphRequest(BaseModel):
    """커뮤니티 그래프 요청"""

    community_id: int = Field(..., description="커뮤니티 ID")
    include_skills: bool = Field(default=True, description="스킬 노드 포함 여부")
    limit: int = Field(default=100, ge=1, le=500, description="최대 노드 수")


class QueryResultVisualizationRequest(BaseModel):
    """쿼리 결과 시각화 요청"""

    cypher_query: str = Field(..., description="실행할 Cypher 쿼리")
    parameters: dict = Field(default_factory=dict, description="쿼리 파라미터")


class SchemaVisualizationResponse(BaseModel):
    """스키마 시각화 응답"""

    success: bool = True
    nodes: list[GraphNode] = Field(default_factory=list, description="노드 타입들")
    edges: list[GraphEdge] = Field(default_factory=list, description="관계 타입들")


class QueryStep(BaseModel):
    """쿼리 실행 단계"""

    step: int = Field(..., description="단계 번호")
    description: str = Field(..., description="단계 설명")
    node_label: str | None = Field(default=None, description="대상 노드 타입")
    relationship: str | None = Field(default=None, description="관계 타입")
    result_count: int = Field(default=0, description="결과 수")
    sample_results: list[str] = Field(
        default_factory=list, description="샘플 결과 (이름)"
    )


class QueryPathVisualizationRequest(BaseModel):
    """쿼리 경로 시각화 요청"""

    question: str = Field(..., description="자연어 질문")


class QueryPathVisualizationResponse(BaseModel):
    """쿼리 경로 시각화 응답"""

    success: bool = True
    question: str = Field(..., description="원본 질문")
    intent: str | None = Field(default=None, description="분류된 의도")
    is_multi_hop: bool = Field(default=False, description="Multi-hop 쿼리 여부")

    # 쿼리 분해 정보
    query_plan: list[QueryStep] = Field(
        default_factory=list, description="쿼리 실행 계획"
    )

    # 시각화 데이터
    nodes: list[GraphNode] = Field(default_factory=list, description="그래프 노드")
    edges: list[GraphEdge] = Field(default_factory=list, description="그래프 엣지")

    # 실행 정보
    cypher_query: str | None = Field(default=None, description="생성된 Cypher 쿼리")
    execution_path: list[str] = Field(default_factory=list, description="실행 경로")
    final_answer: str | None = Field(default=None, description="최종 응답")
