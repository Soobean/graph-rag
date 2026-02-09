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
