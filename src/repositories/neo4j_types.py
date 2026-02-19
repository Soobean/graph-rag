"""
Neo4j Repository 공유 데이터 타입

모든 서브 레포지토리에서 공통으로 사용하는 결과 타입.
순환 import를 방지하기 위해 독립 모듈로 분리.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class NodeResult:
    """노드 검색 결과"""

    id: str
    labels: list[str]
    properties: dict[str, Any]


@dataclass(slots=True)
class RelationshipResult:
    """관계 검색 결과"""

    id: str
    type: str
    start_node_id: str
    end_node_id: str
    properties: dict[str, Any]
