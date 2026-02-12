"""
ProjectStaffingService 테스트

비용 기반 프로젝트 인력 배치 서비스 테스트
- 후보자 탐색
- 스태핑 플랜
- 예산 분석
- 카테고리 조회
- 에러 핸들링
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.neo4j_repository import Neo4jRepository
from src.services.project_staffing_service import ProjectStaffingService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j Repository"""
    neo4j = MagicMock(spec=Neo4jRepository)
    neo4j.execute_cypher = AsyncMock(return_value=[])
    return neo4j


@pytest.fixture
def service(mock_neo4j):
    """ProjectStaffingService 인스턴스"""
    return ProjectStaffingService(mock_neo4j)


# =============================================================================
# 프로젝트 정보 mock helper
# =============================================================================


def _project_info_row():
    """공통 프로젝트 정보 mock 결과"""
    return {
        "name": "ETL파이프라인 구축",
        "budget_million": 500.0,
        "estimated_hours": 2000.0,
        "required_headcount": 5,
        "budget_allocated": 300.0,
        "budget_spent": 150.0,
        "status": "진행중",
    }


def _requirements_rows():
    """공통 REQUIRES 스킬 mock 결과 (DB 실제 타입: 한글 문자열)"""
    return [
        {
            "skill_name": "Python",
            "required_proficiency": "고급",
            "max_hourly_rate": 80000.0,
            "required_headcount": 2,
            "importance": "필수",
        },
        {
            "skill_name": "Docker",
            "required_proficiency": "중급",
            "max_hourly_rate": 70000.0,
            "required_headcount": 1,
            "importance": "우대",
        },
    ]


def _candidate_rows():
    """후보자 mock 결과 (effective_rate ASC 정렬 — DB ORDER BY 시뮬레이션)"""
    return [
        {
            "emp_name": "김철수",
            "department": "데이터팀",
            "proficiency": 3,
            "effective_rate": 55000.0,
            "availability": "partial",
            "current_projects": 2,
            "max_projects": 5,
        },
        {
            "emp_name": "홍길동",
            "department": "개발팀",
            "proficiency": 4,
            "effective_rate": 60000.0,
            "availability": "available",
            "current_projects": 1,
            "max_projects": 5,
        },
    ]


# =============================================================================
# TestFindCandidates
# =============================================================================


class TestFindCandidates:
    """find_candidates() 메서드 테스트"""

    async def test_find_candidates_returns_sorted_by_rate(
        self, service, mock_neo4j
    ):
        """적격 후보자를 단가순으로 반환"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]  # Python만
            elif "HAS_SKILL" in query:
                return _candidate_rows()
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")

        assert result.project_name == "ETL파이프라인 구축"
        assert result.project_budget == 500.0
        assert result.total_skills == 1
        assert len(result.skill_candidates) == 1
        assert len(result.skill_candidates[0].candidates) == 2
        # 단가순 정렬 확인 (DB에서 정렬되어 옴)
        rates = [c.effective_rate for c in result.skill_candidates[0].candidates]
        assert rates == sorted(rates)

    async def test_find_candidates_skill_filter(self, service, mock_neo4j):
        """skill_name 필터 동작 확인"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                # skill_filter가 적용되면 해당 스킬만 반환
                if params and params.get("skill_filter"):
                    return [
                        r
                        for r in _requirements_rows()
                        if r["skill_name"].lower()
                        == params["skill_filter"].lower()
                    ]
                return _requirements_rows()
            elif "HAS_SKILL" in query:
                return _candidate_rows()
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates(
            "ETL파이프라인 구축", skill_name="Python"
        )

        assert result.total_skills == 1
        assert result.skill_candidates[0].skill_name == "Python"

    async def test_find_candidates_min_proficiency_filter(
        self, service, mock_neo4j
    ):
        """min_proficiency 필터 동작 확인"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                # min_proficiency 파라미터가 쿼리에 반영되어야 함
                assert params is not None
                if "min_proficiency" in (params or {}):
                    assert params["min_proficiency"] == 4
                return [_candidate_rows()[1]]  # proficiency=4인 홍길동만
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates(
            "ETL파이프라인 구축", min_proficiency=4
        )

        assert result.total_skills == 1
        # 결과의 후보자는 모두 proficiency >= 4
        for sc in result.skill_candidates:
            for c in sc.candidates:
                assert c.proficiency >= 4

    async def test_find_candidates_empty_candidates(self, service, mock_neo4j):
        """후보 없는 스킬도 빈 리스트로 반환"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return _requirements_rows()
            elif "HAS_SKILL" in query:
                return []  # 후보자 없음
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")

        assert result.total_skills == 2
        assert result.total_candidates == 0
        for sc in result.skill_candidates:
            assert sc.candidates == []

    async def test_find_candidates_project_not_found(self, service, mock_neo4j):
        """존재하지 않는 프로젝트 → ValueError"""
        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            await service.find_candidates("존재하지않는프로젝트")


# =============================================================================
# TestStaffingPlan
# =============================================================================


class TestStaffingPlan:
    """generate_staffing_plan() 메서드 테스트"""

    async def test_staffing_plan_cost_calculation(self, service, mock_neo4j):
        """예상 인건비 계산 정확성"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]  # Python only
            elif "HAS_SKILL" in query:
                return _candidate_rows()
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.generate_staffing_plan(
            "ETL파이프라인 구축", top_n_per_skill=2
        )

        assert result.project_name == "ETL파이프라인 구축"
        assert len(result.skill_plans) == 1
        plan = result.skill_plans[0]
        assert len(plan.recommended_candidates) == 2
        # cost_per_hour = 60000 + 55000 = 115000
        assert plan.estimated_cost_per_hour == 115000.0

    async def test_staffing_plan_top_n_limit(self, service, mock_neo4j):
        """top_n 제한 동작"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return _candidate_rows()  # 2명
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.generate_staffing_plan(
            "ETL파이프라인 구축", top_n_per_skill=1
        )

        # top_n=1이므로 추천은 1명
        assert len(result.skill_plans[0].recommended_candidates) == 1

    async def test_staffing_plan_budget_utilization(self, service, mock_neo4j):
        """예산 활용률 계산"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return _candidate_rows()
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.generate_staffing_plan("ETL파이프라인 구축")

        # budget_utilization_percent이 계산되어야 함
        if result.total_estimated_labor_cost > 0 and result.project_budget:
            assert result.budget_utilization_percent is not None
            assert result.budget_utilization_percent >= 0

    async def test_staffing_plan_project_not_found(self, service, mock_neo4j):
        """존재하지 않는 프로젝트 → ValueError"""
        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            await service.generate_staffing_plan("존재하지않는프로젝트")


# =============================================================================
# TestBudgetAnalysis
# =============================================================================


class TestBudgetAnalysis:
    """analyze_budget() 메서드 테스트"""

    async def test_budget_analysis_cost_calculation(self, service, mock_neo4j):
        """planned vs actual 비용 계산"""

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1

            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "WORKS_ON" in query:
                return [
                    {
                        "emp_name": "홍길동",
                        "role": "개발자",
                        "agreed_rate": 60000.0,
                        "allocated_hours": 100.0,
                        "actual_hours": 120.0,
                    },
                    {
                        "emp_name": "김철수",
                        "role": "리더",
                        "agreed_rate": 80000.0,
                        "allocated_hours": 80.0,
                        "actual_hours": 75.0,
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.analyze_budget("ETL파이프라인 구축")

        assert result.project_name == "ETL파이프라인 구축"
        assert len(result.team_breakdown) == 2

        # 홍길동: planned=60000*100=6000000, actual=60000*120=7200000
        hong = result.team_breakdown[0]
        assert hong.employee_name == "홍길동"
        assert hong.planned_cost == 6_000_000.0
        assert hong.actual_cost == 7_200_000.0

        # 김철수: planned=80000*80=6400000, actual=80000*75=6000000
        kim = result.team_breakdown[1]
        assert kim.planned_cost == 6_400_000.0
        assert kim.actual_cost == 6_000_000.0

        # 총계: planned=12400000, actual=13200000
        assert result.total_planned_cost == 12_400_000.0
        assert result.total_actual_cost == 13_200_000.0

    async def test_budget_analysis_variance_calculation(
        self, service, mock_neo4j
    ):
        """variance 계산 (under/over budget)"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "WORKS_ON" in query:
                return [
                    {
                        "emp_name": "홍길동",
                        "role": "개발자",
                        "agreed_rate": 50000.0,
                        "allocated_hours": 100.0,
                        "actual_hours": 150.0,  # 초과
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.analyze_budget("ETL파이프라인 구축")

        # planned=5000000, actual=7500000, variance=+2500000
        assert result.variance == 2_500_000.0
        assert result.variance_percent is not None
        assert result.variance_percent == 50.0  # (2500000/5000000)*100

    async def test_budget_analysis_empty_team(self, service, mock_neo4j):
        """팀원 없는 프로젝트 → 빈 breakdown"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "WORKS_ON" in query:
                return []  # 팀원 없음
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.analyze_budget("ETL파이프라인 구축")

        assert result.team_breakdown == []
        assert result.total_planned_cost == 0.0
        assert result.total_actual_cost == 0.0
        assert result.variance == 0.0

    async def test_budget_analysis_project_not_found(self, service, mock_neo4j):
        """존재하지 않는 프로젝트 → ValueError"""
        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            await service.analyze_budget("존재하지않는프로젝트")


# =============================================================================
# TestGetCategories
# =============================================================================


class TestGetCategories:
    """get_categories() 메서드 테스트"""

    async def test_get_categories_returns_list(self, service, mock_neo4j):
        """카테고리 목록 반환"""
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {"category": "Backend", "skills": ["Python", "Java", "Go"]},
                {"category": "Frontend", "skills": ["React", "Vue"]},
            ]
        )

        result = await service.get_categories()

        assert len(result) == 2
        assert result[0].name == "Backend"
        assert "Python" in result[0].skills
        assert result[0].color == "#10B981"  # Backend 색상

    async def test_get_categories_handles_error(self, service, mock_neo4j):
        """DB 에러 시 빈 리스트"""
        mock_neo4j.execute_cypher = AsyncMock(
            side_effect=Exception("DB Error")
        )

        result = await service.get_categories()

        assert result == []


# =============================================================================
# TestErrorHandling
# =============================================================================


class TestErrorHandling:
    """에러 핸들링 테스트"""

    async def test_find_candidates_db_error_propagates(
        self, service, mock_neo4j
    ):
        """_get_project_info DB 에러 전파"""
        mock_neo4j.execute_cypher = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        with pytest.raises(Exception, match="Connection failed"):
            await service.find_candidates("ETL파이프라인 구축")

    async def test_find_skill_candidates_error_returns_empty(
        self, service, mock_neo4j
    ):
        """_find_skill_candidates 내부 에러 시 빈 리스트"""

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                raise Exception("Query failed")
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # 스킬 후보 조회 실패해도 빈 candidates로 계속 진행
        result = await service.find_candidates("ETL파이프라인 구축")
        assert result.total_candidates == 0
        assert result.skill_candidates[0].candidates == []

    async def test_budget_analysis_null_values_handled(
        self, service, mock_neo4j
    ):
        """agreed_rate 등이 None일 때 0으로 처리"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "WORKS_ON" in query:
                return [
                    {
                        "emp_name": "홍길동",
                        "role": None,
                        "agreed_rate": None,
                        "allocated_hours": None,
                        "actual_hours": None,
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.analyze_budget("ETL파이프라인 구축")

        assert len(result.team_breakdown) == 1
        member = result.team_breakdown[0]
        assert member.planned_cost == 0.0
        assert member.actual_cost == 0.0
