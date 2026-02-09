"""
Graph Edit API 엔드포인트 테스트

FastAPI TestClient + dependency_overrides로 서비스를 모킹하여
HTTP 상태 코드, 요청/응답 형식을 검증합니다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.graph_edit import router
from src.dependencies import get_graph_edit_service
from src.domain.exceptions import EntityNotFoundError, ValidationError
from src.services.graph_edit_service import (
    GraphEditConflictError,
    GraphEditService,
)


@pytest.fixture
def mock_service():
    """Mock GraphEditService"""
    service = MagicMock(spec=GraphEditService)
    service.create_node = AsyncMock(return_value={
        "id": "4:abc:0",
        "labels": ["Employee"],
        "properties": {"name": "홍길동"},
    })
    service.get_node = AsyncMock(return_value={
        "id": "4:abc:0",
        "labels": ["Employee"],
        "properties": {"name": "홍길동"},
    })
    service.search_nodes = AsyncMock(return_value=[
        {"id": "4:abc:0", "labels": ["Employee"], "properties": {"name": "홍길동"}},
    ])
    service.update_node = AsyncMock(return_value={
        "id": "4:abc:0",
        "labels": ["Employee"],
        "properties": {"name": "김철수"},
    })
    service.delete_node = AsyncMock()
    service.create_edge = AsyncMock(return_value={
        "id": "5:abc:0",
        "type": "HAS_SKILL",
        "source_id": "4:abc:0",
        "target_id": "4:abc:1",
        "properties": {},
    })
    service.get_edge = AsyncMock(return_value={
        "id": "5:abc:0",
        "type": "HAS_SKILL",
        "source_id": "4:abc:0",
        "target_id": "4:abc:1",
        "properties": {},
    })
    service.delete_edge = AsyncMock()
    service.get_schema_info = AsyncMock(return_value={
        "allowed_labels": ["Employee", "Skill"],
        "required_properties": {"Employee": ["name"], "Skill": ["name"]},
        "valid_relationships": {
            "HAS_SKILL": [{"source": "Employee", "target": "Skill"}],
        },
    })
    return service


@pytest.fixture
def app(mock_service):
    """테스트용 FastAPI 앱"""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_graph_edit_service] = lambda: mock_service
    return app


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return TestClient(app)


# =============================================================================
# 노드 CRUD 엔드포인트
# =============================================================================


class TestCreateNodeAPI:
    def test_create_node_201(self, client):
        resp = client.post("/api/v1/graph/nodes", json={
            "label": "Employee",
            "properties": {"name": "홍길동"},
        })
        assert resp.status_code == 201
        assert resp.json()["id"] == "4:abc:0"

    def test_create_node_400_validation(self, client, mock_service):
        mock_service.create_node.side_effect = ValidationError("not allowed", field="label")
        resp = client.post("/api/v1/graph/nodes", json={
            "label": "Invalid",
            "properties": {"name": "test"},
        })
        assert resp.status_code == 400

    def test_create_node_409_duplicate(self, client, mock_service):
        mock_service.create_node.side_effect = GraphEditConflictError("already exists")
        resp = client.post("/api/v1/graph/nodes", json={
            "label": "Employee",
            "properties": {"name": "홍길동"},
        })
        assert resp.status_code == 409


class TestSearchNodesAPI:
    def test_search_nodes_200(self, client):
        resp = client.get("/api/v1/graph/nodes", params={"label": "Employee"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert len(data["nodes"]) == 1

    def test_search_nodes_with_search(self, client, mock_service):
        resp = client.get("/api/v1/graph/nodes", params={"search": "홍"})
        assert resp.status_code == 200
        mock_service.search_nodes.assert_awaited_once()


class TestGetNodeAPI:
    def test_get_node_200(self, client):
        resp = client.get("/api/v1/graph/nodes/4:abc:0")
        assert resp.status_code == 200
        assert resp.json()["id"] == "4:abc:0"

    def test_get_node_404(self, client, mock_service):
        mock_service.get_node.side_effect = EntityNotFoundError("Node", "invalid")
        resp = client.get("/api/v1/graph/nodes/invalid")
        assert resp.status_code == 404


class TestUpdateNodeAPI:
    def test_update_node_200(self, client):
        resp = client.patch("/api/v1/graph/nodes/4:abc:0", json={
            "properties": {"name": "김철수"},
        })
        assert resp.status_code == 200
        assert resp.json()["properties"]["name"] == "김철수"

    def test_update_node_404(self, client, mock_service):
        mock_service.update_node.side_effect = EntityNotFoundError("Node", "invalid")
        resp = client.patch("/api/v1/graph/nodes/invalid", json={
            "properties": {"name": "test"},
        })
        assert resp.status_code == 404

    def test_update_node_409_duplicate(self, client, mock_service):
        mock_service.update_node.side_effect = GraphEditConflictError("already exists")
        resp = client.patch("/api/v1/graph/nodes/4:abc:0", json={
            "properties": {"name": "duplicate"},
        })
        assert resp.status_code == 409


class TestDeleteNodeAPI:
    def test_delete_node_204(self, client):
        resp = client.delete("/api/v1/graph/nodes/4:abc:0")
        assert resp.status_code == 204

    def test_delete_node_404(self, client, mock_service):
        mock_service.delete_node.side_effect = EntityNotFoundError("Node", "invalid")
        resp = client.delete("/api/v1/graph/nodes/invalid")
        assert resp.status_code == 404

    def test_delete_node_409_has_relationships(self, client, mock_service):
        mock_service.delete_node.side_effect = GraphEditConflictError("has relationships")
        resp = client.delete("/api/v1/graph/nodes/4:abc:0")
        assert resp.status_code == 409

    def test_delete_node_force(self, client, mock_service):
        resp = client.delete("/api/v1/graph/nodes/4:abc:0", params={"force": True})
        assert resp.status_code == 204
        mock_service.delete_node.assert_awaited_once_with("4:abc:0", force=True)


# =============================================================================
# 엣지 CRUD 엔드포인트
# =============================================================================


class TestCreateEdgeAPI:
    def test_create_edge_201(self, client):
        resp = client.post("/api/v1/graph/edges", json={
            "source_id": "4:abc:0",
            "target_id": "4:abc:1",
            "relationship_type": "HAS_SKILL",
        })
        assert resp.status_code == 201
        assert resp.json()["type"] == "HAS_SKILL"

    def test_create_edge_400_invalid_type(self, client, mock_service):
        mock_service.create_edge.side_effect = ValidationError("not allowed", field="relationship_type")
        resp = client.post("/api/v1/graph/edges", json={
            "source_id": "4:abc:0",
            "target_id": "4:abc:1",
            "relationship_type": "INVALID",
        })
        assert resp.status_code == 400

    def test_create_edge_404_node_not_found(self, client, mock_service):
        mock_service.create_edge.side_effect = EntityNotFoundError("Node", "invalid")
        resp = client.post("/api/v1/graph/edges", json={
            "source_id": "invalid",
            "target_id": "4:abc:1",
            "relationship_type": "HAS_SKILL",
        })
        assert resp.status_code == 404


class TestGetEdgeAPI:
    def test_get_edge_200(self, client):
        resp = client.get("/api/v1/graph/edges/5:abc:0")
        assert resp.status_code == 200
        assert resp.json()["type"] == "HAS_SKILL"

    def test_get_edge_404(self, client, mock_service):
        mock_service.get_edge.side_effect = EntityNotFoundError("Edge", "invalid")
        resp = client.get("/api/v1/graph/edges/invalid")
        assert resp.status_code == 404


class TestDeleteEdgeAPI:
    def test_delete_edge_204(self, client):
        resp = client.delete("/api/v1/graph/edges/5:abc:0")
        assert resp.status_code == 204

    def test_delete_edge_404(self, client, mock_service):
        mock_service.delete_edge.side_effect = EntityNotFoundError("Edge", "invalid")
        resp = client.delete("/api/v1/graph/edges/invalid")
        assert resp.status_code == 404


# =============================================================================
# 스키마 정보
# =============================================================================


class TestSchemaLabelsAPI:
    def test_get_schema_200(self, client):
        resp = client.get("/api/v1/graph/schema/labels")
        assert resp.status_code == 200
        data = resp.json()
        assert "Employee" in data["allowed_labels"]
        assert "HAS_SKILL" in data["valid_relationships"]
