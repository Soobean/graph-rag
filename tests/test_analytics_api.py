"""
Analytics API 엔드포인트 테스트

GDS 분석 (프로젝션, 커뮤니티, 유사 직원, 팀 추천) +
Project Staffing (프로젝트 목록, 후보자, 플랜, 예산 분석) 테스트
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.analytics import router
from src.dependencies import get_gds_service, get_staffing_service
from src.services.gds_service import CommunityResult, GDSService, TeamRecommendation


@pytest.fixture
def mock_gds():
    """Mock GDSService"""
    service = MagicMock(spec=GDSService)
    service.SKILL_PROJECTION = "skill-similarity"
    service.create_skill_similarity_projection = AsyncMock(
        return_value={
            "name": "skill-similarity",
            "node_count": 100,
            "relationship_count": 500,
        }
    )
    service.get_projection_info = AsyncMock(
        return_value=(
            True,
            {
                "nodeCount": 100,
                "relationshipCount": 500,
            },
        )
    )
    service.drop_projection = AsyncMock(return_value=True)
    service.cleanup_all_projections = AsyncMock(return_value=3)
    service.detect_communities = AsyncMock(
        return_value=CommunityResult(
            algorithm="leiden",
            node_count=100,
            community_count=5,
            modularity=0.72,
            communities=[
                {
                    "community_id": 0,
                    "member_count": 20,
                    "sample_members": ["홍길동", "김철수"],
                },
                {"community_id": 1, "member_count": 15, "sample_members": ["박지우"]},
            ],
        )
    )
    service.find_similar_employees = AsyncMock(
        return_value=[
            {
                "name": "김철수",
                "job_type": "개발자",
                "similarity": 0.85,
                "shared_skills": 5,
                "community_id": 0,
            },
        ]
    )
    service.recommend_team = AsyncMock(
        return_value=TeamRecommendation(
            members=[
                {
                    "name": "홍길동",
                    "job_type": "개발자",
                    "communityId": 0,
                    "matchedSkills": ["Python"],
                    "skillCount": 5,
                },
            ],
            skill_coverage=0.8,
            covered_skills=["Python"],
            missing_skills=["React"],
            community_diversity=1,
            total_score=0.85,
        )
    )
    return service


@pytest.fixture
def mock_staffing():
    """Mock ProjectStaffingService"""
    service = MagicMock()
    service.list_projects = AsyncMock(
        return_value=[
            {
                "name": "ETL파이프라인 구축",
                "status": "진행중",
                "budget_million": 50.0,
                "required_headcount": 5,
            },
        ]
    )
    service.find_candidates = AsyncMock(
        return_value={
            "project_name": "ETL파이프라인 구축",
            "project_budget": 50.0,
            "estimated_hours": None,
            "required_headcount": 5,
            "skill_candidates": [],
            "total_skills": 3,
            "total_candidates": 10,
        }
    )
    service.generate_staffing_plan = AsyncMock(
        return_value={
            "project_name": "ETL파이프라인 구축",
            "project_budget": 50.0,
            "estimated_hours": None,
            "skill_plans": [],
            "total_estimated_labor_cost": 1000000,
            "budget_utilization_percent": 20.0,
        }
    )
    service.analyze_budget = AsyncMock(
        return_value={
            "project_name": "챗봇 리뉴얼",
            "project_budget": 30.0,
            "budget_allocated": None,
            "budget_spent": None,
            "team_breakdown": [],
            "total_planned_cost": 500000,
            "total_actual_cost": 450000,
            "variance": -50000,
            "variance_percent": -10.0,
        }
    )
    service.get_categories = AsyncMock(
        return_value=[
            {"name": "Programming", "color": "#3B82F6", "skills": ["Python", "Java"]},
        ]
    )
    return service


@pytest.fixture
def app(mock_gds, mock_staffing):
    """테스트용 FastAPI 앱"""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_gds_service] = lambda: mock_gds
    app.dependency_overrides[get_staffing_service] = lambda: mock_staffing
    return app


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return TestClient(app)


# =============================================================================
# 프로젝션 관리
# =============================================================================


class TestCreateProjectionAPI:
    def test_create_success(self, client):
        """프로젝션 생성 성공"""
        resp = client.post("/api/v1/analytics/projection/create")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["node_count"] == 100

    def test_create_error_500(self, client, mock_gds):
        """프로젝션 생성 실패 → 500"""
        mock_gds.create_skill_similarity_projection = AsyncMock(
            side_effect=RuntimeError("GDS error")
        )
        resp = client.post("/api/v1/analytics/projection/create")
        assert resp.status_code == 500


class TestProjectionStatusAPI:
    def test_status_exists(self, client):
        """프로젝션 존재"""
        resp = client.get("/api/v1/analytics/projection/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["node_count"] == 100

    def test_status_not_exists(self, client, mock_gds):
        """프로젝션 미존재"""
        mock_gds.get_projection_info = AsyncMock(return_value=(False, {}))
        resp = client.get("/api/v1/analytics/projection/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False


class TestDeleteProjectionAPI:
    def test_delete_dropped(self, client):
        """프로젝션 삭제 성공"""
        resp = client.delete("/api/v1/analytics/projection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["dropped"] is True

    def test_delete_not_found(self, client, mock_gds):
        """삭제할 프로젝션 없음"""
        mock_gds.drop_projection = AsyncMock(return_value=False)
        resp = client.delete("/api/v1/analytics/projection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dropped"] is False


class TestCleanupProjectionsAPI:
    def test_cleanup_success(self, client):
        """전체 정리 성공"""
        resp = client.delete("/api/v1/analytics/projection/cleanup-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["dropped_count"] == 3


# =============================================================================
# 커뮤니티 탐지
# =============================================================================


class TestCommunityDetectAPI:
    def test_detect_success(self, client):
        """커뮤니티 탐지 성공"""
        resp = client.post(
            "/api/v1/analytics/communities/detect",
            json={
                "algorithm": "leiden",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["community_count"] == 5

    def test_detect_error_500(self, client, mock_gds):
        """커뮤니티 탐지 실패 → 500"""
        mock_gds.detect_communities = AsyncMock(side_effect=RuntimeError("GDS error"))
        resp = client.post("/api/v1/analytics/communities/detect", json={})
        assert resp.status_code == 500


# =============================================================================
# 유사 직원 탐색
# =============================================================================


class TestSimilarEmployeesAPI:
    def test_similar_success(self, client):
        """유사 직원 탐색 성공"""
        resp = client.post(
            "/api/v1/analytics/employees/similar",
            json={
                "employee_name": "홍길동",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["base_employee"] == "홍길동"

    def test_similar_no_projection_400(self, client, mock_gds):
        """프로젝션 없음 → 400"""
        mock_gds.get_projection_info = AsyncMock(return_value=(False, {}))
        resp = client.post(
            "/api/v1/analytics/employees/similar",
            json={
                "employee_name": "홍길동",
            },
        )
        assert resp.status_code == 400


# =============================================================================
# 팀 추천
# =============================================================================


class TestTeamRecommendAPI:
    def test_recommend_success(self, client):
        """팀 추천 성공"""
        resp = client.post(
            "/api/v1/analytics/team/recommend",
            json={
                "required_skills": ["Python", "React"],
                "team_size": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["skill_coverage"] == 0.8

    def test_recommend_error_500(self, client, mock_gds):
        """팀 추천 실패 → 500"""
        mock_gds.recommend_team = AsyncMock(side_effect=RuntimeError("GDS error"))
        resp = client.post(
            "/api/v1/analytics/team/recommend",
            json={
                "required_skills": ["Python"],
            },
        )
        assert resp.status_code == 500


# =============================================================================
# Project Staffing
# =============================================================================


class TestStaffingProjectsAPI:
    def test_list_projects(self, client):
        """프로젝트 목록 조회"""
        resp = client.get("/api/v1/analytics/staffing/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "ETL파이프라인 구축"


class TestFindCandidatesAPI:
    def test_find_candidates_success(self, client):
        """후보자 탐색 성공"""
        resp = client.post(
            "/api/v1/analytics/staffing/find-candidates",
            json={
                "project_name": "ETL파이프라인 구축",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_name"] == "ETL파이프라인 구축"

    def test_find_candidates_validation_400(self, client, mock_staffing):
        """유효성 검증 실패 → 400"""
        mock_staffing.find_candidates = AsyncMock(
            side_effect=ValueError("프로젝트를 찾을 수 없습니다")
        )
        resp = client.post(
            "/api/v1/analytics/staffing/find-candidates",
            json={
                "project_name": "없는프로젝트",
            },
        )
        assert resp.status_code == 400


class TestStaffingPlanAPI:
    def test_plan_success(self, client):
        """스태핑 플랜 생성 성공"""
        resp = client.post(
            "/api/v1/analytics/staffing/plan",
            json={
                "project_name": "ETL파이프라인 구축",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_name"] == "ETL파이프라인 구축"

    def test_plan_validation_400(self, client, mock_staffing):
        """유효성 검증 실패 → 400"""
        mock_staffing.generate_staffing_plan = AsyncMock(
            side_effect=ValueError("프로젝트를 찾을 수 없습니다")
        )
        resp = client.post(
            "/api/v1/analytics/staffing/plan",
            json={
                "project_name": "없는프로젝트",
            },
        )
        assert resp.status_code == 400


class TestBudgetAnalysisAPI:
    def test_budget_analysis_success(self, client):
        """예산 분석 성공"""
        resp = client.post(
            "/api/v1/analytics/staffing/budget-analysis",
            json={
                "project_name": "챗봇 리뉴얼",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_name"] == "챗봇 리뉴얼"

    def test_budget_analysis_validation_400(self, client, mock_staffing):
        """유효성 검증 실패 → 400"""
        mock_staffing.analyze_budget = AsyncMock(
            side_effect=ValueError("프로젝트를 찾을 수 없습니다")
        )
        resp = client.post(
            "/api/v1/analytics/staffing/budget-analysis",
            json={
                "project_name": "없는프로젝트",
            },
        )
        assert resp.status_code == 400


class TestStaffingCategoriesAPI:
    def test_categories_success(self, client):
        """카테고리 목록 조회"""
        resp = client.get("/api/v1/analytics/staffing/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["categories"]) == 1
        assert data["categories"][0]["name"] == "Programming"
