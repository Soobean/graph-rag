"""
GraphEditService 단위 테스트

화이트리스트 검증, 중복 확인, 삭제 보호 등 비즈니스 로직을 검증합니다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.exceptions import EntityNotFoundError, ValidationError
from src.repositories.neo4j_repository import Neo4jRepository, NodeResult
from src.services.graph_edit_service import (
    GraphEditConflictError,
    GraphEditService,
)


@pytest.fixture
def mock_repo():
    """Mock Neo4jRepository"""
    repo = MagicMock(spec=Neo4jRepository)
    repo.check_duplicate_node = AsyncMock(return_value=False)
    repo.create_node_generic = AsyncMock(return_value={
        "id": "4:abc:0",
        "labels": ["Employee"],
        "properties": {"name": "홍길동", "created_by": "anonymous_admin"},
    })
    repo.find_entity_by_id = AsyncMock(return_value=NodeResult(
        id="4:abc:0",
        labels=["Employee"],
        properties={"name": "홍길동"},
    ))
    repo.update_node_properties = AsyncMock(return_value={
        "id": "4:abc:0",
        "labels": ["Employee"],
        "properties": {"name": "홍길동", "updated_by": "anonymous_admin"},
    })
    repo.delete_node_atomic = AsyncMock(return_value={
        "deleted": True, "rel_count": 0, "not_found": False,
    })
    # 기존 메서드도 유지 (다른 테스트에서 사용 가능)
    repo.get_node_relationship_count = AsyncMock(return_value=0)
    repo.delete_node_generic = AsyncMock(return_value=True)
    repo.create_relationship_generic = AsyncMock(return_value={
        "id": "5:abc:0",
        "type": "HAS_SKILL",
        "source_id": "4:abc:0",
        "target_id": "4:abc:1",
        "properties": {"created_by": "anonymous_admin"},
        "source_labels": ["Employee"],
        "target_labels": ["Skill"],
    })
    repo.find_relationship_by_id = AsyncMock(return_value={
        "id": "5:abc:0",
        "type": "HAS_SKILL",
        "source_id": "4:abc:0",
        "target_id": "4:abc:1",
        "properties": {},
    })
    repo.delete_relationship_generic = AsyncMock(return_value=True)
    repo.search_nodes = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_repo):
    """GraphEditService 인스턴스"""
    return GraphEditService(mock_repo)


# =============================================================================
# 노드 생성
# =============================================================================


class TestCreateNode:
    async def test_create_node_success(self, service, mock_repo):
        result = await service.create_node("Employee", {"name": "홍길동"})
        assert result["id"] == "4:abc:0"
        assert result["labels"] == ["Employee"]
        mock_repo.check_duplicate_node.assert_awaited_once_with("Employee", "홍길동")
        mock_repo.create_node_generic.assert_awaited_once()

    async def test_create_node_invalid_label(self, service):
        with pytest.raises(ValidationError, match="not allowed"):
            await service.create_node("InvalidLabel", {"name": "test"})

    async def test_create_node_missing_name(self, service):
        with pytest.raises(ValidationError, match="required"):
            await service.create_node("Employee", {"department": "개발팀"})

    async def test_create_node_empty_name(self, service):
        with pytest.raises(ValidationError, match="required"):
            await service.create_node("Employee", {"name": "  "})

    async def test_create_node_duplicate_early_check(self, service, mock_repo):
        """서비스 레이어 중복 확인 (빠른 UX 피드백)"""
        mock_repo.check_duplicate_node.return_value = True
        with pytest.raises(GraphEditConflictError, match="already exists"):
            await service.create_node("Employee", {"name": "홍길동"})

    async def test_create_node_duplicate_atomic(self, service, mock_repo):
        """repository가 None 반환 시 (atomic 중복 감지) 에러"""
        mock_repo.check_duplicate_node.return_value = False
        mock_repo.create_node_generic.return_value = None
        with pytest.raises(GraphEditConflictError, match="already exists"):
            await service.create_node("Employee", {"name": "홍길동"})

    async def test_create_node_strips_name(self, service, mock_repo):
        await service.create_node("Skill", {"name": "  Python  "})
        call_args = mock_repo.create_node_generic.call_args
        assert call_args[0][1]["name"] == "Python"


# =============================================================================
# 노드 조회/검색
# =============================================================================


class TestGetNode:
    async def test_get_node_success(self, service):
        result = await service.get_node("4:abc:0")
        assert result["id"] == "4:abc:0"
        assert result["labels"] == ["Employee"]

    async def test_get_node_not_found(self, service, mock_repo):
        mock_repo.find_entity_by_id.side_effect = EntityNotFoundError("Node", "invalid")
        with pytest.raises(EntityNotFoundError):
            await service.get_node("invalid")


class TestSearchNodes:
    async def test_search_nodes_success(self, service, mock_repo):
        mock_repo.search_nodes.return_value = [
            {"id": "4:abc:0", "labels": ["Employee"], "properties": {"name": "홍길동"}}
        ]
        result = await service.search_nodes(label="Employee", search="홍")
        assert len(result) == 1
        mock_repo.search_nodes.assert_awaited_once_with(label="Employee", search="홍", limit=50)

    async def test_search_nodes_invalid_label(self, service):
        with pytest.raises(ValidationError, match="not allowed"):
            await service.search_nodes(label="InvalidLabel")

    async def test_search_nodes_no_filter(self, service, mock_repo):
        await service.search_nodes()
        mock_repo.search_nodes.assert_awaited_once_with(label=None, search=None, limit=50)


# =============================================================================
# 노드 수정
# =============================================================================


class TestUpdateNode:
    async def test_update_node_success(self, service, mock_repo):
        result = await service.update_node("4:abc:0", {"department": "개발팀"})
        assert result["id"] == "4:abc:0"
        mock_repo.update_node_properties.assert_awaited_once()

    async def test_update_node_not_found(self, service, mock_repo):
        mock_repo.find_entity_by_id.side_effect = EntityNotFoundError("Node", "invalid")
        with pytest.raises(EntityNotFoundError):
            await service.update_node("invalid", {"name": "test"})

    async def test_update_node_name_duplicate(self, service, mock_repo):
        mock_repo.check_duplicate_node.return_value = True
        with pytest.raises(GraphEditConflictError, match="already exists"):
            await service.update_node("4:abc:0", {"name": "김철수"})

    async def test_update_node_same_name_no_duplicate_check(self, service, mock_repo):
        """현재 이름과 동일하면 중복 확인 안 함"""
        await service.update_node("4:abc:0", {"name": "홍길동"})
        mock_repo.check_duplicate_node.assert_not_awaited()

    async def test_update_node_null_removes_property(self, service, mock_repo):
        await service.update_node("4:abc:0", {"department": None})
        call_args = mock_repo.update_node_properties.call_args
        remove_keys = call_args[0][2]
        assert "department" in remove_keys

    async def test_update_node_cannot_remove_required(self, service):
        with pytest.raises(ValidationError, match="required properties"):
            await service.update_node("4:abc:0", {"name": None})

    async def test_update_node_empty_name(self, service):
        with pytest.raises(ValidationError, match="empty"):
            await service.update_node("4:abc:0", {"name": "  "})

    async def test_update_node_ignores_protected_properties(self, service, mock_repo):
        """시스템 메타데이터(created_by 등)는 사용자가 수정 불가"""
        await service.update_node("4:abc:0", {
            "department": "개발팀",
            "created_by": "hacker",
            "created_at": None,
            "updated_at": None,
        })
        call_args = mock_repo.update_node_properties.call_args
        update_props = call_args[0][1]
        remove_keys = call_args[0][2]
        # created_by 덮어쓰기 시도는 무시됨
        assert "created_by" not in update_props or update_props.get("created_by") != "hacker"
        # created_at/updated_at null 삭제 시도도 무시됨
        assert remove_keys is None or "created_at" not in remove_keys
        assert remove_keys is None or "updated_at" not in remove_keys
        # 일반 속성은 정상 처리
        assert update_props["department"] == "개발팀"


# =============================================================================
# 노드 삭제
# =============================================================================


class TestDeleteNode:
    async def test_delete_node_success(self, service, mock_repo):
        await service.delete_node("4:abc:0")
        mock_repo.delete_node_atomic.assert_awaited_once_with("4:abc:0", force=False)

    async def test_delete_node_not_found(self, service, mock_repo):
        mock_repo.delete_node_atomic.return_value = {
            "deleted": False, "rel_count": 0, "not_found": True,
        }
        with pytest.raises(EntityNotFoundError):
            await service.delete_node("invalid")

    async def test_delete_node_has_relationships(self, service, mock_repo):
        mock_repo.delete_node_atomic.return_value = {
            "deleted": False, "rel_count": 3, "not_found": False,
        }
        with pytest.raises(GraphEditConflictError, match="3 relationship"):
            await service.delete_node("4:abc:0")

    async def test_delete_node_force(self, service, mock_repo):
        await service.delete_node("4:abc:0", force=True)
        mock_repo.delete_node_atomic.assert_awaited_once_with("4:abc:0", force=True)


# =============================================================================
# 엣지 생성
# =============================================================================


class TestCreateEdge:
    async def test_create_edge_success(self, service, mock_repo):
        mock_repo.find_entity_by_id.side_effect = [
            NodeResult(id="4:abc:0", labels=["Employee"], properties={"name": "홍길동"}),
            NodeResult(id="4:abc:1", labels=["Skill"], properties={"name": "Python"}),
        ]
        result = await service.create_edge("4:abc:0", "4:abc:1", "HAS_SKILL")
        assert result["type"] == "HAS_SKILL"
        mock_repo.create_relationship_generic.assert_awaited_once()

    async def test_create_edge_invalid_type(self, service):
        with pytest.raises(ValidationError, match="not allowed"):
            await service.create_edge("4:abc:0", "4:abc:1", "INVALID_REL")

    async def test_create_edge_source_not_found(self, service, mock_repo):
        mock_repo.find_entity_by_id.side_effect = EntityNotFoundError("Node", "invalid")
        with pytest.raises(EntityNotFoundError):
            await service.create_edge("invalid", "4:abc:1", "HAS_SKILL")

    async def test_create_edge_invalid_label_combo(self, service, mock_repo):
        """Skill -> Employee 방향으로 HAS_SKILL은 불가"""
        mock_repo.find_entity_by_id.side_effect = [
            NodeResult(id="4:abc:0", labels=["Skill"], properties={"name": "Python"}),
            NodeResult(id="4:abc:1", labels=["Employee"], properties={"name": "홍길동"}),
        ]
        with pytest.raises(ValidationError, match="Invalid label combination"):
            await service.create_edge("4:abc:0", "4:abc:1", "HAS_SKILL")

    async def test_create_edge_with_properties(self, service, mock_repo):
        mock_repo.find_entity_by_id.side_effect = [
            NodeResult(id="4:abc:0", labels=["Employee"], properties={"name": "홍길동"}),
            NodeResult(id="4:abc:1", labels=["Skill"], properties={"name": "Python"}),
        ]
        await service.create_edge("4:abc:0", "4:abc:1", "HAS_SKILL", {"level": "expert"})
        call_args = mock_repo.create_relationship_generic.call_args
        props = call_args[0][3]
        assert props["level"] == "expert"
        assert props["created_by"] == "anonymous_admin"


# =============================================================================
# 엣지 삭제
# =============================================================================


class TestDeleteEdge:
    async def test_delete_edge_success(self, service, mock_repo):
        await service.delete_edge("5:abc:0")
        mock_repo.delete_relationship_generic.assert_awaited_once_with("5:abc:0")

    async def test_delete_edge_not_found(self, service, mock_repo):
        mock_repo.delete_relationship_generic.return_value = False
        with pytest.raises(EntityNotFoundError):
            await service.delete_edge("invalid")


# =============================================================================
# 스키마 정보
# =============================================================================


class TestSchemaInfo:
    async def test_get_schema_info(self, service):
        result = await service.get_schema_info()
        assert "Employee" in result["allowed_labels"]
        assert "Skill" in result["allowed_labels"]
        assert "HAS_SKILL" in result["valid_relationships"]
        assert result["valid_relationships"]["HAS_SKILL"] == [
            {"source": "Employee", "target": "Skill"}
        ]
        assert result["required_properties"]["Employee"] == ["name"]
        # Concept 전용 관계는 제외됨
        assert "SAME_AS" not in result["valid_relationships"]
        assert "IS_A" not in result["valid_relationships"]


# =============================================================================
# 삭제 영향 분석
# =============================================================================


class TestDeletionImpact:
    async def test_skill_with_concept_bridge(self, service, mock_repo):
        """Skill 삭제 시 Concept 브릿지 끊어짐 감지"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Skill"], properties={"name": "Python"},
        )
        mock_repo.get_node_relationships_detailed = AsyncMock(return_value=[
            {
                "id": "5:abc:0", "type": "HAS_SKILL", "direction": "incoming",
                "connected_node_id": "4:abc:1", "connected_node_labels": ["Employee"],
                "connected_node_name": "홍길동",
            },
        ])
        mock_repo.find_concept_bridge = AsyncMock(return_value={
            "concept_name": "Python", "hierarchy": ["Python", "Programming Language"],
        })
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_deletion_impact("4:abc:0")

        assert result["node_name"] == "Python"
        assert result["relationship_count"] == 1
        assert result["concept_bridge"]["will_break"] is True
        assert result["concept_bridge"]["current_concept"] == "Python"
        assert "브릿지가 끊어집니다" in result["summary"]

    async def test_employee_no_concept_bridge(self, service, mock_repo):
        """Employee 노드는 concept_bridge가 None"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Employee"], properties={"name": "홍길동"},
        )
        mock_repo.get_node_relationships_detailed = AsyncMock(return_value=[])
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_deletion_impact("4:abc:0")

        assert result["concept_bridge"] is None
        assert result["relationship_count"] == 0

    async def test_node_not_found(self, service, mock_repo):
        """존재하지 않는 노드 → EntityNotFoundError"""
        mock_repo.find_entity_by_id.side_effect = EntityNotFoundError("Node", "invalid")

        with pytest.raises(EntityNotFoundError):
            await service.analyze_deletion_impact("invalid")

    async def test_no_relationships(self, service, mock_repo):
        """관계 없는 노드는 안전한 삭제"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Skill"], properties={"name": "Rust"},
        )
        mock_repo.get_node_relationships_detailed = AsyncMock(return_value=[])
        mock_repo.find_concept_bridge = AsyncMock(return_value=None)
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_deletion_impact("4:abc:0")

        assert result["relationship_count"] == 0
        assert "안전하게 삭제" in result["summary"]
        assert result["concept_bridge"]["will_break"] is False

    async def test_skill_no_concept_match(self, service, mock_repo):
        """Concept 매칭 없는 Skill → 브릿지 끊어지지 않음"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Skill"], properties={"name": "CustomTool"},
        )
        mock_repo.get_node_relationships_detailed = AsyncMock(return_value=[])
        mock_repo.find_concept_bridge = AsyncMock(return_value=None)
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_deletion_impact("4:abc:0")

        assert result["concept_bridge"]["will_break"] is False
        assert result["concept_bridge"]["current_concept"] is None

    async def test_downstream_cache_and_gds(self, service, mock_repo):
        """캐시/GDS 경고 생성 확인"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Skill"], properties={"name": "Python"},
        )
        mock_repo.get_node_relationships_detailed = AsyncMock(return_value=[])
        mock_repo.find_concept_bridge = AsyncMock(return_value=None)
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=5)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=10)

        result = await service.analyze_deletion_impact("4:abc:0")

        systems = [e["system"] for e in result["downstream_effects"]]
        assert "cache" in systems
        assert "gds" in systems


# =============================================================================
# 이름 변경 영향 분석
# =============================================================================


class TestRenameImpact:
    async def test_skill_bridge_breaks(self, service, mock_repo):
        """Skill 이름 변경 → 브릿지 끊어짐"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Skill"], properties={"name": "Python"},
        )
        mock_repo.check_duplicate_node = AsyncMock(return_value=False)
        mock_repo.find_concept_bridge = AsyncMock(side_effect=[
            {"concept_name": "Python", "hierarchy": ["Python", "PL"]},
            None,
        ])
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_rename_impact("4:abc:0", "PythonLang")

        assert result["concept_bridge"]["will_break"] is True
        assert result["concept_bridge"]["current_concept"] == "Python"
        assert result["concept_bridge"]["new_concept"] is None
        assert "브릿지가 끊어집니다" in result["summary"]

    async def test_skill_bridge_preserved(self, service, mock_repo):
        """이름 변경 후에도 Concept 매칭 유지"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Skill"], properties={"name": "Python"},
        )
        mock_repo.check_duplicate_node = AsyncMock(return_value=False)
        mock_repo.find_concept_bridge = AsyncMock(side_effect=[
            {"concept_name": "Python", "hierarchy": ["Python", "PL"]},
            {"concept_name": "Python", "hierarchy": ["Python", "PL"]},
        ])
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_rename_impact("4:abc:0", "python")

        assert result["concept_bridge"]["will_break"] is False
        assert "유지됩니다" in result["summary"]

    async def test_duplicate_detected(self, service, mock_repo):
        """중복 이름 감지"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Skill"], properties={"name": "Python"},
        )
        mock_repo.check_duplicate_node = AsyncMock(return_value=True)
        mock_repo.find_concept_bridge = AsyncMock(return_value=None)
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_rename_impact("4:abc:0", "Java")

        assert result["has_duplicate"] is True
        assert "중복" in result["summary"]

    async def test_empty_name(self, service):
        """빈 이름 → ValidationError"""
        with pytest.raises(ValidationError, match="empty"):
            await service.analyze_rename_impact("4:abc:0", "  ")

    async def test_same_name_case_only(self, service, mock_repo):
        """대소문자만 다르면 중복 확인 스킵"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Skill"], properties={"name": "Python"},
        )
        mock_repo.find_concept_bridge = AsyncMock(side_effect=[
            {"concept_name": "Python", "hierarchy": ["Python", "PL"]},
            {"concept_name": "Python", "hierarchy": ["Python", "PL"]},
        ])
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_rename_impact("4:abc:0", "python")

        assert result["has_duplicate"] is False
        # check_duplicate_node은 호출되지 않아야 함
        mock_repo.check_duplicate_node.assert_not_awaited()

    async def test_non_skill_node(self, service, mock_repo):
        """비-Skill 노드는 concept_bridge가 None"""
        mock_repo.find_entity_by_id.return_value = NodeResult(
            id="4:abc:0", labels=["Employee"], properties={"name": "홍길동"},
        )
        mock_repo.check_duplicate_node = AsyncMock(return_value=False)
        mock_repo.check_cached_queries_exist = AsyncMock(return_value=0)
        mock_repo.check_similar_relationships_exist = AsyncMock(return_value=0)

        result = await service.analyze_rename_impact("4:abc:0", "김철수")

        assert result["concept_bridge"] is None
