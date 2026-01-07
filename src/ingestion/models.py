"""
KG 추출 데이터 모델 정의 (Data Models with Lineage)

LLM 입출력 및 데이터 처리를 위한 Pydantic 모델을 정의합니다.
데이터의 출처(Lineage)와 신뢰도(Confidence)를 포함합니다.
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from src.ingestion.schema import NodeType, RelationType

# UUID5 네임스페이스 (프로젝트 고유)
ENTITY_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _normalize(value: Any) -> str:
    """값을 정규화하여 일관된 문자열로 변환"""
    return str(value).strip().lower()


def generate_entity_id(
    label: str,
    properties: dict[str, Any],
) -> str:
    """
    UUID5 기반 결정적 엔티티 ID 생성

    Natural Key 우선순위:
    1. 강한 식별자 (id, email, code 등) - 단독 사용 가능
    2. 약한 식별자 (name) - 다른 속성과 조합하여 사용

    Note:
        - source_metadata는 ID 생성에 포함하지 않음
        - 대소문자 정규화 적용 (iPhone == iphone == IPHONE)
        - 같은 엔티티가 여러 소스에서 등장해도 동일한 UUID 보장

    Args:
        label: 노드 타입 (Employee, Project 등)
        properties: 노드 속성

    Returns:
        결정적 UUID5 문자열
    """
    # 강한 식별자: 단독으로 엔티티를 구분할 수 있는 필드
    strong_identifiers = [
        "id", "employee_id", "project_id", "department_id",
        "position_id", "skill_id", "certificate_id",
        "email", "code",
    ]

    # 약한 식별자: 동명이인 등 충돌 가능성이 있는 필드
    weak_identifiers = ["name"]

    key_parts = [label]

    # 1. 강한 식별자 검색
    for field in strong_identifiers:
        if field in properties and properties[field] is not None:
            value = _normalize(properties[field])
            if value:
                key_parts.append(value)
                # 결정적 문자열 생성 및 UUID5 반환
                return str(uuid.uuid5(ENTITY_NAMESPACE, "|".join(key_parts)))

    # 2. 약한 식별자가 있으면 모든 속성과 조합
    for field in weak_identifiers:
        if field in properties and properties[field] is not None:
            value = _normalize(properties[field])
            if value:
                # 약한 식별자 + 다른 모든 속성 조합
                sorted_props = sorted(
                    (k, _normalize(v))
                    for k, v in properties.items()
                    if v is not None and _normalize(v)
                )
                key_parts.extend([f"{k}:{v}" for k, v in sorted_props])
                return str(uuid.uuid5(ENTITY_NAMESPACE, "|".join(key_parts)))

    # 3. 식별자가 전혀 없으면 모든 속성 조합
    sorted_props = sorted(
        (k, _normalize(v))
        for k, v in properties.items()
        if v is not None and _normalize(v)
    )
    key_parts.extend([f"{k}:{v}" for k, v in sorted_props])

    return str(uuid.uuid5(ENTITY_NAMESPACE, "|".join(key_parts)))


class Document(BaseModel):
    """
    표준 입력 포맷 (Adapter Pattern의 공통 인터페이스)
    모든 데이터 소스(CSV, JSON, PDF 등)는 이 형태로 변환되어 LLM에 주입됨
    """

    page_content: str
    metadata: dict[str, Any]  # {"source": "file.csv", "row": 1, ...}


class Node(BaseModel):
    """추출된 노드 정보"""

    id: str = Field(..., description="Unique Identifier (UUID5 generated from natural keys)")
    label: NodeType
    properties: dict[str, Any] = Field(default_factory=dict)

    # Lineage Tracking
    source_metadata: dict[str, Any] = Field(
        default_factory=dict, description="데이터 출처 정보 (파일명, 행 번호 등)"
    )


class Edge(BaseModel):
    """추출된 관계 정보"""

    source_id: str
    target_id: str
    type: RelationType
    properties: dict[str, Any] = Field(default_factory=dict)

    # Label 정보 (Neo4j 인덱스 활용을 위한 최적화)
    source_label: NodeType | None = Field(
        default=None, description="Source 노드의 Label (쿼리 최적화용)"
    )
    target_label: NodeType | None = Field(
        default=None, description="Target 노드의 Label (쿼리 최적화용)"
    )

    # Quality Control
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="LLM의 추출 확신도 (0.0 ~ 1.0)"
    )

    # Lineage Tracking
    source_metadata: dict[str, Any] = Field(
        default_factory=dict, description="데이터 출처 정보"
    )


class ExtractedGraph(BaseModel):
    """LLM 추출 결과의 컨테이너"""

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
