"""
Ontology API 엔드포인트 테스트

온톨로지 스키마/스타일 조회 API 테스트
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.ontology import router


@pytest.fixture
def mock_loader():
    """Mock OntologyLoader"""
    loader = MagicMock()
    loader.load_schema.return_value = {
        "_meta": {"version": "1.0"},
        "relations": {"IS_A": {"description": "상위 개념", "transitive": True}},
        "concepts": {"SkillCategory": [], "PositionLevel": None},
        "expansion_rules": {},
    }
    loader.get_style_for_concept.return_value = {
        "color": "#3B82F6",
        "icon": "code",
    }
    return loader


@pytest.fixture
def app(mock_loader):
    """테스트용 FastAPI 앱"""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return TestClient(app)


# =============================================================================
# GET /ontology/schema
# =============================================================================


class TestOntologySchemaAPI:
    def test_schema_200(self, client, mock_loader):
        """온톨로지 스키마 조회 성공"""
        with patch(
            "src.api.routes.ontology.get_ontology_loader", return_value=mock_loader
        ):
            resp = client.get("/api/v1/ontology/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "_meta" in data
        assert "relations" in data

    def test_schema_500_error(self, client):
        """로더 실패 시 500"""
        with patch(
            "src.api.routes.ontology.get_ontology_loader",
            side_effect=RuntimeError("loader init failed"),
        ):
            resp = client.get("/api/v1/ontology/schema")
        assert resp.status_code == 500


# =============================================================================
# GET /ontology/concept/{category}/{name}/style
# =============================================================================


class TestConceptStyleAPI:
    def test_style_found(self, client, mock_loader):
        """스타일이 존재하는 개념"""
        with patch(
            "src.api.routes.ontology.get_ontology_loader", return_value=mock_loader
        ):
            resp = client.get("/api/v1/ontology/concept/skills/Python/style")
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] == "#3B82F6"
        assert data["icon"] == "code"

    def test_style_fallback_default(self, client, mock_loader):
        """스타일이 없는 개념 → 기본 스타일 반환"""
        mock_loader.get_style_for_concept.return_value = None
        with patch(
            "src.api.routes.ontology.get_ontology_loader", return_value=mock_loader
        ):
            resp = client.get("/api/v1/ontology/concept/skills/UnknownSkill/style")
        assert resp.status_code == 200
        data = resp.json()
        assert data["color"] == "#94A3B8"
        assert data["icon"] == "circle"
