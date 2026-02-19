"""
Community Admin API 엔드포인트 테스트

커뮤니티 배치 리프레시 및 상태 조회 API 테스트
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.community_admin import router
from src.dependencies import get_community_batch_service
from src.domain.exceptions import ConcurrentRefreshError
from src.services.community_batch_service import (
    CommunityBatchService,
    CommunityRefreshResult,
    CommunityStatusResult,
)


@pytest.fixture
def mock_service():
    """Mock CommunityBatchService"""
    service = MagicMock(spec=CommunityBatchService)
    service.refresh = AsyncMock(return_value=CommunityRefreshResult(
        success=True,
        algorithm="leiden",
        community_count=5,
        modularity=0.72,
        node_count=50,
        duration_seconds=3.14,
    ))
    service.get_status = AsyncMock(return_value=CommunityStatusResult(
        has_communities=True,
        refreshed_at="2026-02-19T10:00:00+09:00",
        algorithm="leiden",
        community_count=5,
        modularity=0.72,
        assigned_node_count=50,
        is_stale=False,
    ))
    return service


@pytest.fixture
def app(mock_service):
    """테스트용 FastAPI 앱"""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_community_batch_service] = lambda: mock_service
    return app


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return TestClient(app)


# =============================================================================
# POST /communities/refresh
# =============================================================================


class TestCommunityRefreshAPI:
    def test_refresh_success(self, client):
        """커뮤니티 리프레시 성공"""
        resp = client.post("/api/v1/communities/refresh", json={
            "algorithm": "leiden",
            "gamma": 1.0,
            "min_shared_skills": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["algorithm"] == "leiden"
        assert data["community_count"] == 5
        assert data["modularity"] == 0.72

    def test_refresh_concurrent_409(self, client, mock_service):
        """동시 실행 시 409"""
        mock_service.refresh = AsyncMock(
            side_effect=ConcurrentRefreshError()
        )
        resp = client.post("/api/v1/communities/refresh", json={})
        assert resp.status_code == 409

    def test_refresh_error_500(self, client, mock_service):
        """내부 오류 시 500"""
        mock_service.refresh = AsyncMock(
            side_effect=RuntimeError("unexpected")
        )
        resp = client.post("/api/v1/communities/refresh", json={})
        assert resp.status_code == 500


# =============================================================================
# GET /communities/status
# =============================================================================


class TestCommunityStatusAPI:
    def test_status_with_communities(self, client):
        """커뮤니티가 존재할 때"""
        resp = client.get("/api/v1/communities/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_communities"] is True
        assert data["community_count"] == 5
        assert data["is_stale"] is False

    def test_status_no_communities(self, client, mock_service):
        """커뮤니티가 없을 때"""
        mock_service.get_status = AsyncMock(return_value=CommunityStatusResult(
            has_communities=False,
            refreshed_at=None,
            algorithm=None,
            community_count=0,
            modularity=None,
            assigned_node_count=0,
            is_stale=False,
        ))
        resp = client.get("/api/v1/communities/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_communities"] is False
        assert data["community_count"] == 0
