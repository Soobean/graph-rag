"""
Query API 엔드포인트 테스트 (health, schema)

TestClient + dependency_overrides로 서비스를 모킹하여
HTTP 상태 코드, 응답 형식을 검증합니다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.query import router
from src.config import Settings, get_settings
from src.dependencies import get_neo4j_client
from src.infrastructure.neo4j_client import Neo4jClient


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4jClient"""
    client = MagicMock(spec=Neo4jClient)
    client.health_check = AsyncMock(
        return_value={
            "connected": True,
            "server_info": {"version": "5.15.0", "edition": "community"},
        }
    )
    client.get_schema_info = AsyncMock(
        return_value={
            "node_labels": ["Employee", "Skill", "Project"],
            "relationship_types": ["HAS_SKILL", "WORKS_ON"],
            "indexes": [],
            "constraints": [],
        }
    )
    return client


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    settings = MagicMock(spec=Settings)
    settings.app_version = "1.0.0-test"
    return settings


@pytest.fixture
def app(mock_neo4j_client, mock_settings):
    """테스트용 FastAPI 앱"""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_neo4j_client] = lambda: mock_neo4j_client
    app.dependency_overrides[get_settings] = lambda: mock_settings
    return app


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return TestClient(app)


# =============================================================================
# GET /health
# =============================================================================


class TestHealthAPI:
    def test_health_healthy(self, client):
        """Neo4j 연결 성공 시 healthy 상태"""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["neo4j_connected"] is True
        assert data["version"] == "1.0.0-test"

    def test_health_degraded(self, client, mock_neo4j_client):
        """Neo4j 연결 실패 시 degraded 상태"""
        mock_neo4j_client.health_check = AsyncMock(
            return_value={
                "connected": False,
            }
        )
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["neo4j_connected"] is False


# =============================================================================
# GET /schema
# =============================================================================


class TestSchemaAPI:
    def test_schema_200(self, client):
        """스키마 조회 성공"""
        resp = client.get("/api/v1/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "Employee" in data["node_labels"]
        assert "HAS_SKILL" in data["relationship_types"]
