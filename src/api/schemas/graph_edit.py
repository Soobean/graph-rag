"""
Graph Edit API 스키마

노드/엣지 CRUD를 위한 Request/Response 모델을 정의합니다.
"""

from typing import Any

from pydantic import BaseModel, Field

from src.services.graph_edit_service import (
    ALLOWED_LABELS,
    VALID_RELATIONSHIP_COMBINATIONS,
)

# ============================================
# Request Models
# ============================================


class CreateNodeRequest(BaseModel):
    """노드 생성 요청"""

    label: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description=f"노드 레이블. 허용: {sorted(ALLOWED_LABELS)}",
    )
    properties: dict[str, Any] = Field(
        ...,
        description="노드 속성 (name 필수)",
    )


class UpdateNodeRequest(BaseModel):
    """노드 속성 수정 요청 (null 값은 속성 삭제)"""

    properties: dict[str, Any] = Field(
        ...,
        min_length=1,
        description="수정할 속성. null 값은 해당 속성 삭제.",
    )


class CreateEdgeRequest(BaseModel):
    """엣지 생성 요청"""

    source_id: str = Field(
        ...,
        min_length=1,
        description="소스 노드 elementId",
    )
    target_id: str = Field(
        ...,
        min_length=1,
        description="타겟 노드 elementId",
    )
    relationship_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description=f"관계 타입. 허용: {sorted(VALID_RELATIONSHIP_COMBINATIONS.keys())}",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description="관계 속성 (선택)",
    )


# ============================================
# Response Models
# ============================================


class NodeResponse(BaseModel):
    """노드 응답"""

    id: str = Field(..., description="노드 elementId")
    labels: list[str] = Field(..., description="노드 레이블 리스트")
    properties: dict[str, Any] = Field(..., description="노드 속성")


class NodeListResponse(BaseModel):
    """노드 목록 응답"""

    nodes: list[NodeResponse]
    count: int = Field(..., description="반환된 노드 수")


class EdgeResponse(BaseModel):
    """엣지 응답"""

    id: str = Field(..., description="관계 elementId")
    type: str = Field(..., description="관계 타입")
    source_id: str = Field(..., description="소스 노드 elementId")
    target_id: str = Field(..., description="타겟 노드 elementId")
    properties: dict[str, Any] = Field(..., description="관계 속성")


class RelationshipCombo(BaseModel):
    """허용된 관계 소스-타겟 조합"""

    source: str
    target: str


class SchemaInfoResponse(BaseModel):
    """스키마 정보 응답 (편집 UI용)"""

    allowed_labels: list[str]
    required_properties: dict[str, list[str]]
    valid_relationships: dict[str, list[RelationshipCombo]]


# ============================================
# Impact Analysis Models
# ============================================


class AffectedRelationship(BaseModel):
    """영향받는 관계 상세"""

    id: str = Field(..., description="관계 elementId")
    type: str = Field(..., description="관계 타입 (예: HAS_SKILL)")
    direction: str = Field(..., description="방향 (outgoing / incoming)")
    connected_node_id: str = Field(..., description="연결된 노드 elementId")
    connected_node_labels: list[str] = Field(..., description="연결된 노드 레이블")
    connected_node_name: str = Field(..., description="연결된 노드 이름")


class ConceptBridgeImpact(BaseModel):
    """Skill↔Concept 브릿지 영향"""

    current_concept: str | None = Field(None, description="현재 매칭되는 Concept 이름")
    current_hierarchy: list[str] = Field(
        default_factory=list, description="현재 IS_A 계층 (조상 목록)"
    )
    will_break: bool = Field(..., description="이 작업으로 브릿지가 끊어지는지 여부")
    new_concept: str | None = Field(
        None, description="(rename only) 새 이름에 매칭되는 Concept"
    )
    new_hierarchy: list[str] = Field(
        default_factory=list, description="(rename only) 새 이름의 IS_A 계층"
    )


class DownstreamEffect(BaseModel):
    """캐시/GDS 등 downstream 영향"""

    system: str = Field(..., description="영향받는 시스템 (cache / gds)")
    description: str = Field(..., description="영향 설명")


class NodeDeletionImpactResponse(BaseModel):
    """노드 삭제 영향 미리보기 응답"""

    node_id: str
    node_labels: list[str]
    node_name: str
    affected_relationships: list[AffectedRelationship]
    relationship_count: int
    concept_bridge: ConceptBridgeImpact | None = Field(
        None, description="Skill 노드일 때만 존재"
    )
    downstream_effects: list[DownstreamEffect]
    summary: str = Field(..., description="사람이 읽을 수 있는 영향 요약")


class RenameImpactRequest(BaseModel):
    """이름 변경 영향 미리보기 요청 body"""

    new_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="변경할 새 이름",
    )


class RenameImpactResponse(BaseModel):
    """이름 변경 영향 미리보기 응답"""

    node_id: str
    node_labels: list[str]
    current_name: str
    new_name: str
    has_duplicate: bool = Field(
        ..., description="새 이름으로 동일 레이블 내 중복 존재 여부"
    )
    concept_bridge: ConceptBridgeImpact | None = Field(
        None, description="Skill 노드일 때만 존재"
    )
    downstream_effects: list[DownstreamEffect]
    summary: str = Field(..., description="사람이 읽을 수 있는 영향 요약")
