"""
GraphEditService - 그래프 편집 비즈니스 로직

관리자가 Neo4j 콘솔 없이 웹 UI에서 그래프 데이터를 편집할 수 있도록
화이트리스트 기반 검증 + CRUD 오퍼레이션을 제공합니다.
"""

import logging
from typing import Any

from src.domain.exceptions import EntityNotFoundError, ValidationError
from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)


# ============================================
# 화이트리스트 정의 (NEO4J_SCHEMA.md 기준)
# ============================================

ALLOWED_LABELS = {
    "Employee",
    "Skill",
    "Project",
    "Department",
    "Position",
    "Certificate",
    "Concept",
    "Office",
}

REQUIRED_PROPERTIES: dict[str, list[str]] = {
    label: ["name"] for label in ALLOWED_LABELS
}

VALID_RELATIONSHIP_COMBINATIONS: dict[str, list[tuple[str, str]]] = {
    "HAS_SKILL": [("Employee", "Skill")],
    "WORKS_ON": [("Employee", "Project")],
    "BELONGS_TO": [("Employee", "Department")],
    "HAS_POSITION": [("Employee", "Position")],
    "HAS_CERTIFICATE": [("Employee", "Certificate")],
    "REQUIRES": [("Project", "Skill")],
    "MENTORS": [("Employee", "Employee")],
    "OWNED_BY": [("Project", "Department")],
    "SAME_AS": [("Concept", "Concept")],
    "IS_A": [("Concept", "Concept")],
    "LOCATED_AT": [("Department", "Office")],
}

# 검색 기본값
DEFAULT_SEARCH_LIMIT = 50

# 플레이스홀더 — Phase 3 인증 구현 시 교체
ANONYMOUS_ADMIN = "anonymous_admin"


class GraphEditConflictError(Exception):
    """그래프 편집 충돌 (중복 노드, 관계 존재 등)"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class GraphEditService:
    """
    그래프 편집 서비스

    Neo4jRepository를 통해 노드/엣지 CRUD를 수행하며,
    화이트리스트 기반 비즈니스 검증을 적용합니다.
    """

    def __init__(self, neo4j_repository: Neo4jRepository):
        self._neo4j = neo4j_repository

    # ============================================
    # 노드 CRUD
    # ============================================

    async def create_node(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """
        노드 생성

        검증: 레이블 화이트리스트 → 필수 속성 → 이름 중복 확인
        """
        # 1. 레이블 화이트리스트 검증
        if label not in ALLOWED_LABELS:
            raise ValidationError(
                f"Label '{label}' is not allowed. "
                f"Allowed labels: {sorted(ALLOWED_LABELS)}",
                field="label",
            )

        # 2. 필수 속성 검증
        required = REQUIRED_PROPERTIES.get(label, [])
        for prop in required:
            if prop not in properties or not str(properties[prop]).strip():
                raise ValidationError(
                    f"Property '{prop}' is required for label '{label}'",
                    field=prop,
                )

        # 3. 이름 중복 확인 (toLower)
        name = str(properties["name"]).strip()
        properties["name"] = name
        is_duplicate = await self._neo4j.check_duplicate_node(label, name)
        if is_duplicate:
            raise GraphEditConflictError(
                f"Node with name '{name}' already exists in label '{label}'"
            )

        # 4. 메타데이터 추가
        properties["created_by"] = ANONYMOUS_ADMIN

        result = await self._neo4j.create_node_generic(label, properties)
        logger.info(f"Node created: {label} '{name}' by {ANONYMOUS_ADMIN}")
        return result

    async def get_node(self, node_id: str) -> dict[str, Any]:
        """노드 조회 (ID 기반)"""
        node = await self._neo4j.find_entity_by_id(node_id)
        return {
            "id": node.id,
            "labels": node.labels,
            "properties": node.properties,
        }

    async def search_nodes(
        self,
        label: str | None = None,
        search: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[dict[str, Any]]:
        """노드 검색 (레이블, 이름 필터)"""
        if label and label not in ALLOWED_LABELS:
            raise ValidationError(
                f"Label '{label}' is not allowed",
                field="label",
            )
        return await self._neo4j.search_nodes(label=label, search=search, limit=limit)

    async def update_node(
        self,
        node_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """
        노드 속성 수정

        null 값은 속성 삭제로 처리합니다.
        """
        # 1. 존재 확인
        existing = await self._neo4j.find_entity_by_id(node_id)

        # 2. null 값 분리 → REMOVE 처리
        update_props = {}
        remove_keys = []
        for key, value in properties.items():
            if value is None:
                remove_keys.append(key)
            else:
                update_props[key] = value

        # 3. 이름 변경 시 중복 확인
        if "name" in update_props:
            new_name = str(update_props["name"]).strip()
            if not new_name:
                raise ValidationError("name cannot be empty", field="name")
            update_props["name"] = new_name

            # 현재 이름과 다를 때만 중복 확인
            current_name = existing.properties.get("name", "")
            if new_name.lower() != str(current_name).lower():
                label = existing.labels[0] if existing.labels else ""
                if label:
                    is_duplicate = await self._neo4j.check_duplicate_node(label, new_name)
                    if is_duplicate:
                        raise GraphEditConflictError(
                            f"Node with name '{new_name}' already exists in label '{label}'"
                        )

        # 4. 필수 속성 삭제 방지
        if remove_keys:
            label = existing.labels[0] if existing.labels else ""
            required = REQUIRED_PROPERTIES.get(label, [])
            blocked = [k for k in remove_keys if k in required]
            if blocked:
                raise ValidationError(
                    f"Cannot remove required properties: {blocked}",
                    field="properties",
                )

        update_props["updated_by"] = ANONYMOUS_ADMIN

        result = await self._neo4j.update_node_properties(
            node_id, update_props, remove_keys or None
        )
        logger.info(f"Node updated: {node_id}")
        return result

    async def delete_node(
        self,
        node_id: str,
        force: bool = False,
    ) -> None:
        """
        노드 삭제

        force=False: 관계가 있으면 409 반환
        force=True: 연결된 관계도 함께 삭제 (DETACH DELETE)
        """
        # 1. 존재 확인
        await self._neo4j.find_entity_by_id(node_id)

        # 2. force=False면 관계 수 확인
        if not force:
            rel_count = await self._neo4j.get_node_relationship_count(node_id)
            if rel_count > 0:
                raise GraphEditConflictError(
                    f"Node has {rel_count} relationship(s). "
                    f"Use force=true to delete with relationships."
                )

        deleted = await self._neo4j.delete_node_generic(node_id, force=force)
        if not deleted:
            raise EntityNotFoundError("Node", node_id)
        logger.info(f"Node deleted: {node_id} (force={force})")

    # ============================================
    # 엣지 CRUD
    # ============================================

    async def create_edge(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        엣지 생성

        검증: 관계 타입 화이트리스트 → 소스/타겟 존재 → 레이블 조합 검증
        """
        # 1. 관계 타입 화이트리스트 검증
        if relationship_type not in VALID_RELATIONSHIP_COMBINATIONS:
            raise ValidationError(
                f"Relationship type '{relationship_type}' is not allowed. "
                f"Allowed types: {sorted(VALID_RELATIONSHIP_COMBINATIONS.keys())}",
                field="relationship_type",
            )

        # 2. 소스/타겟 노드 존재 확인 + 레이블 가져오기
        source = await self._neo4j.find_entity_by_id(source_id)
        target = await self._neo4j.find_entity_by_id(target_id)

        # 3. 레이블 조합 검증
        valid_combos = VALID_RELATIONSHIP_COMBINATIONS[relationship_type]
        source_labels = set(source.labels)
        target_labels = set(target.labels)

        combo_valid = any(
            src_label in source_labels and tgt_label in target_labels
            for src_label, tgt_label in valid_combos
        )
        if not combo_valid:
            raise ValidationError(
                f"Invalid label combination for '{relationship_type}': "
                f"{source.labels} -> {target.labels}. "
                f"Valid combinations: {valid_combos}",
                field="relationship_type",
            )

        # 4. 메타데이터 추가
        edge_props = dict(properties) if properties else {}
        edge_props["created_by"] = ANONYMOUS_ADMIN

        result = await self._neo4j.create_relationship_generic(
            source_id, target_id, relationship_type, edge_props
        )
        logger.info(
            f"Edge created: {relationship_type} "
            f"({source_id} -> {target_id}) by {ANONYMOUS_ADMIN}"
        )
        return result

    async def get_edge(self, edge_id: str) -> dict[str, Any]:
        """엣지 조회 (ID 기반)"""
        result = await self._neo4j.find_relationship_by_id(edge_id)
        if not result:
            raise EntityNotFoundError("Edge", edge_id)
        return result

    async def delete_edge(self, edge_id: str) -> None:
        """엣지 삭제"""
        # 존재 확인
        existing = await self._neo4j.find_relationship_by_id(edge_id)
        if not existing:
            raise EntityNotFoundError("Edge", edge_id)

        deleted = await self._neo4j.delete_relationship_generic(edge_id)
        if not deleted:
            raise EntityNotFoundError("Edge", edge_id)
        logger.info(f"Edge deleted: {edge_id}")

    # ============================================
    # 스키마 정보
    # ============================================

    async def get_schema_info(self) -> dict[str, Any]:
        """편집 UI용 스키마 정보 반환"""
        return {
            "allowed_labels": sorted(ALLOWED_LABELS),
            "required_properties": REQUIRED_PROPERTIES,
            "valid_relationships": {
                rel_type: [
                    {"source": src, "target": tgt}
                    for src, tgt in combos
                ]
                for rel_type, combos in VALID_RELATIONSHIP_COMBINATIONS.items()
            },
        }
