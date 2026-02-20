"""
GraphEditService - 그래프 편집 비즈니스 로직

관리자가 Neo4j 콘솔 없이 웹 UI에서 그래프 데이터를 편집할 수 있도록
화이트리스트 기반 검증 + CRUD 오퍼레이션을 제공합니다.
"""

import logging
from typing import Any

from src.domain.constants import ALLOWED_LABELS, VALID_RELATIONSHIP_COMBINATIONS
from src.domain.exceptions import EntityNotFoundError, GraphRAGError, ValidationError
from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)


# ============================================
# 화이트리스트 (src.domain.constants에서 import)
# ============================================

REQUIRED_PROPERTIES: dict[str, list[str]] = {
    label: ["name"] for label in ALLOWED_LABELS
}

# 시스템 메타데이터 보호 (사용자가 수정/삭제 불가)
PROTECTED_PROPERTIES = {"created_at", "created_by", "updated_at", "updated_by"}

# 검색 기본값
DEFAULT_SEARCH_LIMIT = 50

# 플레이스홀더 — Phase 3 인증 구현 시 교체
ANONYMOUS_ADMIN = "anonymous_admin"


class GraphEditConflictError(GraphRAGError):
    """그래프 편집 충돌 (중복 노드, 관계 존재 등)"""

    def __init__(self, message: str):
        super().__init__(message, code="GRAPH_EDIT_CONFLICT")


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

        # 중복 방지 2단계 전략:
        # 1) Early check — 대부분의 중복을 빠르게 감지하여 즉시 UX 피드백
        name = str(properties["name"]).strip()
        properties["name"] = name
        is_duplicate = await self._neo4j.check_duplicate_node(label, name)
        if is_duplicate:
            raise GraphEditConflictError(
                f"Node with name '{name}' already exists in label '{label}'"
            )

        # 2) Atomic create — 동시 요청 race condition 방지 (repository 레벨)
        properties["created_by"] = ANONYMOUS_ADMIN

        result = await self._neo4j.create_node_generic(label, properties)
        if result is None:
            # 두 요청이 동시에 1단계를 통과했지만 repository atomic 패턴이 차단
            raise GraphEditConflictError(
                f"Node with name '{name}' already exists in label '{label}'"
            )
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
        시스템 메타데이터(created_at 등)는 자동 무시됩니다.
        """
        existing = await self._neo4j.find_entity_by_id(node_id)

        # 시스템 메타데이터 필터링 + null 값 분리
        update_props, remove_keys = self._split_update_properties(properties)

        # 이름 변경 시 검증
        if "name" in update_props:
            await self._validate_name_update(update_props, existing)

        # 필수 속성 삭제 방지
        self._validate_remove_keys(remove_keys, existing)

        update_props["updated_by"] = ANONYMOUS_ADMIN

        result = await self._neo4j.update_node_properties(
            node_id, update_props, remove_keys or None
        )
        logger.info(f"Node updated: {node_id}")
        return result

    @staticmethod
    def _split_update_properties(
        properties: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        """속성을 업데이트/삭제로 분리하고 시스템 메타데이터를 필터링"""
        update_props: dict[str, Any] = {}
        remove_keys: list[str] = []
        for key, value in properties.items():
            if key in PROTECTED_PROPERTIES:
                continue
            if value is None:
                remove_keys.append(key)
            else:
                update_props[key] = value
        return update_props, remove_keys

    async def _validate_name_update(
        self,
        update_props: dict[str, Any],
        existing: Any,
    ) -> None:
        """이름 변경 시 빈 값 및 중복 검증"""
        new_name = str(update_props["name"]).strip()
        if not new_name:
            raise ValidationError("name cannot be empty", field="name")
        update_props["name"] = new_name

        current_name = existing.properties.get("name", "")
        if new_name.lower() != str(current_name).lower():
            label = existing.labels[0] if existing.labels else ""
            if label:
                is_duplicate = await self._neo4j.check_duplicate_node(label, new_name)
                if is_duplicate:
                    raise GraphEditConflictError(
                        f"Node with name '{new_name}' already exists in label '{label}'"
                    )

    @staticmethod
    def _validate_remove_keys(remove_keys: list[str], existing: Any) -> None:
        """필수 속성 삭제 방지"""
        if not remove_keys:
            return
        label = existing.labels[0] if existing.labels else ""
        required = REQUIRED_PROPERTIES.get(label, [])
        blocked = [k for k in remove_keys if k in required]
        if blocked:
            raise ValidationError(
                f"Cannot remove required properties: {blocked}",
                field="properties",
            )

    async def delete_node(
        self,
        node_id: str,
        force: bool = False,
    ) -> None:
        """
        노드 삭제 (atomic — 관계 확인과 삭제를 단일 트랜잭션으로 수행)

        force=False: 관계가 있으면 409 반환
        force=True: 연결된 관계도 함께 삭제 (DETACH DELETE)
        """
        result = await self._neo4j.delete_node_atomic(node_id, force=force)

        if result["not_found"]:
            raise EntityNotFoundError("Node", node_id)

        if not result["deleted"]:
            rel_count = result["rel_count"]
            raise GraphEditConflictError(
                f"Node has {rel_count} relationship(s). "
                f"Use force=true to delete with relationships."
            )

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
        return await self._neo4j.find_relationship_by_id(edge_id)

    async def delete_edge(self, edge_id: str) -> None:
        """엣지 삭제"""
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
                rel_type: [{"source": src, "target": tgt} for src, tgt in combos]
                for rel_type, combos in VALID_RELATIONSHIP_COMBINATIONS.items()
            },
        }

    # ============================================
    # Impact Analysis (읽기 전용)
    # ============================================

    async def analyze_deletion_impact(self, node_id: str) -> dict[str, Any]:
        """
        노드 삭제 영향 분석 (dry-run)

        1. 노드 존재 확인
        2. 연결된 관계 상세 조회
        3. Skill이면 Concept 브릿지 확인
        4. 캐시/GDS downstream 경고
        5. 사람이 읽을 수 있는 요약 생성
        """
        node = await self._neo4j.find_entity_by_id(node_id)
        node_name = node.properties.get("name") or ""
        node_labels = node.labels

        relationships = await self._neo4j.get_node_relationships_detailed(node_id)

        # Skill 노드이면 Concept 브릿지 확인
        concept_bridge = None
        is_skill = "Skill" in node_labels
        if is_skill and node_name:
            bridge = await self._neo4j.find_concept_bridge(node_name)
            if bridge:
                concept_bridge = {
                    "current_concept": bridge["concept_name"],
                    "current_hierarchy": bridge.get("hierarchy", []),
                    "will_break": True,
                }
            else:
                concept_bridge = {
                    "current_concept": None,
                    "current_hierarchy": [],
                    "will_break": False,
                }

        downstream = await self._assess_downstream_effects(
            node_labels, is_deletion=True
        )

        summary = self._build_deletion_summary(
            node_name=node_name,
            node_labels=node_labels,
            rel_count=len(relationships),
            concept_bridge=concept_bridge,
        )

        return {
            "node_id": node_id,
            "node_labels": node_labels,
            "node_name": node_name,
            "affected_relationships": relationships,
            "relationship_count": len(relationships),
            "concept_bridge": concept_bridge,
            "downstream_effects": downstream,
            "summary": summary,
        }

    async def analyze_rename_impact(
        self,
        node_id: str,
        new_name: str,
    ) -> dict[str, Any]:
        """
        이름 변경 영향 분석 (dry-run)

        1. 노드 존재 확인
        2. 빈 이름 검증
        3. 중복 확인
        4. Skill이면 Concept 브릿지 변화 확인
        5. 요약 생성
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValidationError("new_name cannot be empty", field="new_name")

        node = await self._neo4j.find_entity_by_id(node_id)
        current_name = node.properties.get("name") or ""
        node_labels = node.labels

        # 중복 확인 (대소문자만 다르면 중복 아님)
        has_duplicate = False
        if new_name.lower() != current_name.lower():
            label = node_labels[0] if node_labels else ""
            if label:
                has_duplicate = await self._neo4j.check_duplicate_node(label, new_name)

        # Skill 노드이면 Concept 브릿지 변화 확인
        concept_bridge = None
        is_skill = "Skill" in node_labels
        if is_skill:
            current_bridge = await self._neo4j.find_concept_bridge(current_name)
            new_bridge = await self._neo4j.find_concept_bridge(new_name)

            will_break = current_bridge is not None and (
                new_bridge is None
                or new_bridge["concept_name"].lower()
                != current_bridge["concept_name"].lower()
            )

            concept_bridge = {
                "current_concept": (
                    current_bridge["concept_name"] if current_bridge else None
                ),
                "current_hierarchy": (
                    current_bridge.get("hierarchy", []) if current_bridge else []
                ),
                "will_break": will_break,
                "new_concept": (new_bridge["concept_name"] if new_bridge else None),
                "new_hierarchy": (
                    new_bridge.get("hierarchy", []) if new_bridge else []
                ),
            }

        downstream = await self._assess_downstream_effects(
            node_labels, is_deletion=False
        )

        summary = self._build_rename_summary(
            current_name=current_name,
            new_name=new_name,
            has_duplicate=has_duplicate,
            concept_bridge=concept_bridge,
        )

        return {
            "node_id": node_id,
            "node_labels": node_labels,
            "current_name": current_name,
            "new_name": new_name,
            "has_duplicate": has_duplicate,
            "concept_bridge": concept_bridge,
            "downstream_effects": downstream,
            "summary": summary,
        }

    async def _assess_downstream_effects(
        self,
        node_labels: list[str],
        is_deletion: bool,
    ) -> list[dict[str, str]]:
        """캐시/GDS downstream 경고 생성"""
        effects: list[dict[str, str]] = []

        cache_count = await self._neo4j.check_cached_queries_exist()
        if cache_count > 0:
            action = "삭제" if is_deletion else "이름 변경"
            effects.append(
                {
                    "system": "cache",
                    "description": (
                        f"CachedQuery {cache_count}개가 존재합니다. "
                        f"노드 {action} 후 캐시된 응답이 stale 상태가 될 수 있습니다."
                    ),
                }
            )

        is_skill_or_employee = bool({"Skill", "Employee"} & set(node_labels))
        if is_skill_or_employee:
            similar_count = await self._neo4j.check_similar_relationships_exist()
            if similar_count > 0:
                effects.append(
                    {
                        "system": "gds",
                        "description": (
                            f"SIMILAR 관계 {similar_count}개가 존재합니다. "
                            f"GDS projection이 stale 상태가 될 수 있습니다."
                        ),
                    }
                )

        return effects

    @staticmethod
    def _build_deletion_summary(
        node_name: str,
        node_labels: list[str],
        rel_count: int,
        concept_bridge: dict[str, Any] | None,
    ) -> str:
        """삭제 영향 요약 생성"""
        label_str = ", ".join(node_labels)
        parts = [f"'{node_name}' ({label_str}) 삭제 시:"]

        if rel_count > 0:
            parts.append(f"  - {rel_count}개 관계가 함께 삭제됩니다.")
        else:
            parts.append("  - 연결된 관계가 없어 안전하게 삭제 가능합니다.")

        if concept_bridge and concept_bridge.get("will_break"):
            concept = concept_bridge.get("current_concept", "")
            parts.append(f"  - ⚠ Concept '{concept}'와의 이름 브릿지가 끊어집니다.")

        return "\n".join(parts)

    @staticmethod
    def _build_rename_summary(
        current_name: str,
        new_name: str,
        has_duplicate: bool,
        concept_bridge: dict[str, Any] | None,
    ) -> str:
        """이름 변경 영향 요약 생성"""
        parts = [f"'{current_name}' → '{new_name}' 이름 변경 시:"]

        if has_duplicate:
            parts.append("  - ⛔ 동일 레이블 내 중복 이름이 존재합니다.")

        if concept_bridge:
            if concept_bridge.get("will_break"):
                old_concept = concept_bridge.get("current_concept", "")
                parts.append(
                    f"  - ⚠ Concept '{old_concept}'와의 이름 브릿지가 끊어집니다."
                )
                if concept_bridge.get("new_concept"):
                    new_concept = concept_bridge["new_concept"]
                    parts.append(
                        f"  - ✅ 새 이름은 Concept '{new_concept}'와 매칭됩니다."
                    )
                else:
                    parts.append("  - ⚠ 새 이름에 매칭되는 Concept가 없습니다.")
            elif concept_bridge.get("current_concept"):
                parts.append("  - ✅ Concept 브릿지가 유지됩니다.")
            else:
                parts.append("  - 기존 Concept 매칭이 없습니다.")

        if not has_duplicate and (
            not concept_bridge or not concept_bridge.get("will_break")
        ):
            parts.append("  - 안전하게 변경 가능합니다.")

        return "\n".join(parts)
