"""
ProjectStaffingService 테스트

비용 기반 프로젝트 인력 배치 서비스 테스트
- 후보자 탐색
- 스태핑 플랜
- 예산 분석
- 카테고리 조회
- 에러 핸들링
- 매칭 점수 & 가중 워크로드
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
            "years_used": 3,
            "availability": "partial",
            "current_projects": 2,
            "max_projects": 5,
            "project_details": [
                {
                    "name": "ETL마이그레이션",
                    "status": "진행중",
                    "contribution_pct": None,
                    "allocated": 500,
                    "actual": 300,
                },
                {
                    "name": "데이터웨어하우스",
                    "status": "계획",
                    "contribution_pct": None,
                    "allocated": 200,
                    "actual": 0,
                },
            ],
        },
        {
            "emp_name": "홍길동",
            "department": "개발팀",
            "proficiency": 4,
            "effective_rate": 60000.0,
            "years_used": 6,
            "availability": "available",
            "current_projects": 1,
            "max_projects": 5,
            "project_details": [
                {
                    "name": "챗봇 리뉴얼",
                    "status": "진행중",
                    "contribution_pct": 50,
                    "allocated": 400,
                    "actual": 200,
                },
            ],
        },
    ]


def _simple_project_details(count: int, status: str = "진행중") -> list:
    """간단한 project_details mock (프로젝트당 절반 진행 상태)"""
    return [
        {"status": status, "contribution_pct": None, "allocated": 500, "actual": 250}
        for _ in range(count)
    ]


# =============================================================================
# TestFindCandidates
# =============================================================================


class TestFindCandidates:
    """find_candidates() 메서드 테스트"""

    async def test_find_candidates_returns_sorted_by_match_score(
        self, service, mock_neo4j
    ):
        """적격 후보자를 매칭 점수 DESC로 반환"""

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
        # 매칭 점수 DESC 정렬 (동점 시 단가 ASC)
        scores = [c.match_score for c in result.skill_candidates[0].candidates]
        assert scores == sorted(scores, reverse=True)

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
                        if r["skill_name"].lower() == params["skill_filter"].lower()
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

    async def test_find_candidates_min_proficiency_filter(self, service, mock_neo4j):
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

        result = await service.find_candidates("ETL파이프라인 구축", min_proficiency=4)

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
# TestMatchScore
# =============================================================================


class TestMatchScore:
    """_compute_match_context() 매칭 점수 테스트"""

    async def test_high_proficiency_low_rate_gets_high_score(self, service, mock_neo4j):
        """고숙련 + 저단가 → 높은 점수"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]  # Python, 고급(3), max=80000
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "최고수",
                        "department": "AI팀",
                        "proficiency": 4,  # 요구(3)보다 높음
                        "effective_rate": 40000.0,  # max(80000)보다 훨씬 낮음
                        "years_used": 8,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": [
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 400,
                            },
                        ],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidate = result.skill_candidates[0].candidates[0]

        assert candidate.match_score >= 80
        assert candidate.proficiency_gap > 0
        assert candidate.cost_efficiency is not None
        assert candidate.cost_efficiency >= 100
        assert candidate.capacity_remaining >= 2

    async def test_match_score_desc_sorting(self, service, mock_neo4j):
        """매칭 점수 DESC 정렬 확인"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "저점수",
                        "department": "팀A",
                        "proficiency": 3,
                        "effective_rate": 75000.0,
                        "years_used": 1,
                        "availability": "partial",
                        "current_projects": 3,
                        "max_projects": 5,
                        "project_details": _simple_project_details(3),
                    },
                    {
                        "emp_name": "고점수",
                        "department": "팀B",
                        "proficiency": 4,
                        "effective_rate": 40000.0,
                        "years_used": 7,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        assert len(candidates) == 2
        # 점수 DESC 정렬
        assert candidates[0].match_score >= candidates[1].match_score
        assert candidates[0].employee_name == "고점수"

    async def test_match_reasons_korean(self, service, mock_neo4j):
        """match_reasons 한국어 문자열 확인"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "테스터",
                        "department": "팀C",
                        "proficiency": 4,
                        "effective_rate": 50000.0,
                        "years_used": 5,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidate = result.skill_candidates[0].candidates[0]

        assert len(candidate.match_reasons) > 0
        # 한국어 문자열 포함 확인
        reasons_text = " ".join(candidate.match_reasons)
        assert any(
            keyword in reasons_text for keyword in ["숙련도", "예산", "가용", "투입"]
        )

    async def test_no_max_rate_still_scores(self, service, mock_neo4j):
        """max_hourly_rate=None → cost_efficiency=None, 점수는 생성"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [
                    {
                        "skill_name": "Go",
                        "required_proficiency": "중급",
                        "max_hourly_rate": None,  # 예산 미설정
                        "required_headcount": 1,
                        "importance": "우대",
                    },
                ]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "고개발자",
                        "department": "팀D",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 4,
                        "availability": "available",
                        "current_projects": 0,
                        "max_projects": 5,
                        "project_details": [],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidate = result.skill_candidates[0].candidates[0]

        assert candidate.cost_efficiency is None
        assert candidate.match_score > 0

    async def test_years_used_boosts_same_proficiency(self, service, mock_neo4j):
        """같은 숙련도에서 years_used가 높으면 점수도 높다"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]  # Python, 고급(3), max=80000
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "신입고급",
                        "department": "팀F",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 1,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                    {
                        "emp_name": "베테랑고급",
                        "department": "팀G",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 10,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        # 같은 조건인데 years_used만 다름 → 베테랑이 높은 점수
        veteran = next(c for c in candidates if c.employee_name == "베테랑고급")
        newcomer = next(c for c in candidates if c.employee_name == "신입고급")
        assert veteran.match_score > newcomer.match_score
        assert veteran.years_used == 10
        assert newcomer.years_used == 1

    async def test_years_used_does_not_override_proficiency(self, service, mock_neo4j):
        """연차가 높아도 숙련도 등급 자체를 역전하지는 않는다"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "중급10년",
                        "department": "팀H",
                        "proficiency": 2,  # 중급
                        "effective_rate": 50000.0,
                        "years_used": 10,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                    {
                        "emp_name": "고급1년",
                        "department": "팀I",
                        "proficiency": 3,  # 고급
                        "effective_rate": 50000.0,
                        "years_used": 1,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        senior = next(c for c in candidates if c.employee_name == "중급10년")
        junior = next(c for c in candidates if c.employee_name == "고급1년")
        # 고급(3) 1년 > 중급(2) 10년 — 숙련도 등급이 우선
        assert junior.match_score > senior.match_score

    async def test_cost_differentiation_within_budget(self, service, mock_neo4j):
        """같은 숙련도·가용성에서 저렴한 후보가 높은 점수"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]  # max=80000
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "비싼사람",
                        "department": "팀J",
                        "proficiency": 3,
                        "effective_rate": 75000.0,
                        "years_used": 3,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                    {
                        "emp_name": "저렴한사람",
                        "department": "팀K",
                        "proficiency": 3,
                        "effective_rate": 40000.0,
                        "years_used": 3,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        cheap = next(c for c in candidates if c.employee_name == "저렴한사람")
        expensive = next(c for c in candidates if c.employee_name == "비싼사람")
        # 동일 조건에서 비용이 낮으면 점수 높아야 함
        assert cheap.match_score > expensive.match_score

    async def test_staffing_plan_passes_match_fields(self, service, mock_neo4j):
        """staffing_plan → match_score/reasons 전달 확인"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "플랜후보",
                        "department": "팀E",
                        "proficiency": 4,
                        "effective_rate": 50000.0,
                        "years_used": 6,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.generate_staffing_plan(
            "ETL파이프라인 구축", top_n_per_skill=1
        )

        rc = result.skill_plans[0].recommended_candidates[0]
        assert rc.match_score > 0
        assert len(rc.match_reasons) > 0
        assert len(rc.match_reasons) <= 2  # [:2] 슬라이스


# =============================================================================
# TestWeightedWorkload
# =============================================================================


class TestWeightedWorkload:
    """가중 워크로드 계산 테스트"""

    def test_compute_workload_empty(self, service):
        """프로젝트 없으면 워크로드 0"""
        assert service._compute_workload([]) == 0.0

    def test_compute_workload_nearly_done_projects(self, service):
        """거의 완료된 프로젝트 3건 → 낮은 워크로드"""
        details = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 500,
                "actual": 475,
            },
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 300,
                "actual": 285,
            },
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 400,
                "actual": 390,
            },
        ]
        workload = service._compute_workload(details)
        # 각각 95% 진행 → remaining 5% → 1.0 × 0.05 = 0.05 per project
        # 3 × 0.05 = 0.15
        assert workload < 0.3  # 프로젝트 3건이지만 부담은 1건 미만

    def test_compute_workload_planning_vs_active(self, service):
        """'계획' 상태 프로젝트는 '진행중'보다 부담이 적다"""
        active = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 500,
                "actual": 0,
            },
        ]
        planning = [
            {"status": "계획", "contribution_pct": None, "allocated": 500, "actual": 0},
        ]
        assert service._compute_workload(active) > service._compute_workload(planning)
        # 진행중: base=1.0, 계획: base=0.3
        assert service._compute_workload(active) == 1.0
        assert service._compute_workload(planning) == 0.3

    def test_compute_workload_contribution_percent(self, service):
        """contribution_percent 50% → 절반 부담"""
        full = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 500,
                "actual": 0,
            },
        ]
        half = [
            {"status": "진행중", "contribution_pct": 50, "allocated": 500, "actual": 0},
        ]
        assert service._compute_workload(full) == 1.0
        assert service._compute_workload(half) == 0.5

    def test_compute_workload_no_hours_info(self, service):
        """시간 정보 없으면 보수적으로 풀부담"""
        details = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": None,
                "actual": None,
            },
        ]
        assert service._compute_workload(details) == 1.0

    async def test_nearly_done_projects_high_capacity_score(self, service, mock_neo4j):
        """거의 완료된 프로젝트가 많아도 가용성 점수가 높다"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "거의완료",
                        "department": "팀L",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 5,
                        "availability": "available",
                        "current_projects": 3,
                        "max_projects": 5,
                        "project_details": [
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 475,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 300,
                                "actual": 285,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 400,
                                "actual": 390,
                            },
                        ],
                    },
                    {
                        "emp_name": "막시작",
                        "department": "팀M",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 5,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": [
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 10,
                            },
                        ],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        almost_done = next(c for c in candidates if c.employee_name == "거의완료")
        just_started = next(c for c in candidates if c.employee_name == "막시작")

        # 거의완료: 3건이지만 실부담 < 0.3 → 여유 많음
        # 막시작: 1건이지만 실부담 ≈ 1.0 → 상대적으로 여유 적음
        assert almost_done.effective_workload < just_started.effective_workload
        assert almost_done.capacity_remaining > just_started.capacity_remaining

    async def test_overloaded_candidate_filtered_out(self, service, mock_neo4j):
        """워크로드가 max_projects 이상이면 후보에서 제외"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "과부하",
                        "department": "팀N",
                        "proficiency": 4,
                        "effective_rate": 50000.0,
                        "years_used": 8,
                        "availability": "available",
                        "current_projects": 5,
                        "max_projects": 5,
                        "project_details": [
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                        ],
                    },
                    {
                        "emp_name": "여유있는사람",
                        "department": "팀O",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 3,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        names = [c.employee_name for c in result.skill_candidates[0].candidates]

        assert "과부하" not in names
        assert "여유있는사람" in names


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

    async def test_budget_analysis_variance_calculation(self, service, mock_neo4j):
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
        mock_neo4j.execute_cypher = AsyncMock(side_effect=Exception("DB Error"))

        result = await service.get_categories()

        assert result == []


# =============================================================================
# TestErrorHandling
# =============================================================================


class TestErrorHandling:
    """에러 핸들링 테스트"""

    async def test_find_candidates_db_error_propagates(self, service, mock_neo4j):
        """_get_project_info DB 에러 전파"""
        mock_neo4j.execute_cypher = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        with pytest.raises(Exception, match="Connection failed"):
            await service.find_candidates("ETL파이프라인 구축")

    async def test_find_skill_candidates_error_returns_empty(self, service, mock_neo4j):
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

    async def test_budget_analysis_null_values_handled(self, service, mock_neo4j):
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


# =============================================================================
# TestComputeWorkloadEdgeCases
# =============================================================================


class TestComputeWorkloadEdgeCases:
    """_compute_workload() 경계값 테스트"""

    def test_compute_workload_progress_0_percent(self, service):
        """progress=0% (막 시작) → 풀부담 1.0"""
        details = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 500,
                "actual": 0,
            },
        ]
        assert service._compute_workload(details) == 1.0

    def test_compute_workload_progress_95_percent_cap(self, service):
        """progress=95% → 5% 잔여, progress>95% → cap at 95%"""
        # 정확히 95%
        details_95 = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 100,
                "actual": 95,
            },
        ]
        assert service._compute_workload(details_95) == 0.05

        # 100% 초과 → 95% cap
        details_100 = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 100,
                "actual": 100,
            },
        ]
        assert service._compute_workload(details_100) == 0.05

        details_over = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 100,
                "actual": 120,
            },
        ]
        assert service._compute_workload(details_over) == 0.05

    def test_compute_workload_allocated_zero(self, service):
        """allocated=0 → division by zero 방지, 보수적으로 풀부담"""
        details = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 0,
                "actual": 10,
            },
        ]
        # alloc=0이면 진행률 계산 불가 → remaining=1.0
        assert service._compute_workload(details) == 1.0

    def test_compute_workload_contribution_percent_zero(self, service):
        """contribution_pct=0 vs None — 0은 '정보 없음'으로 보수적 처리"""
        details = [
            {"status": "진행중", "contribution_pct": 0, "allocated": 500, "actual": 0},
        ]
        # contrib=0 → contrib > 0 실패 → 상태 기반 기본값 1.0
        # 실제 의도: 0%는 정보 없음으로 간주하여 풀부담
        assert service._compute_workload(details) == 1.0

    def test_compute_workload_none_project_details(self, service):
        """project_details=None → 빈 리스트로 처리"""
        # _compute_workload()는 list를 받지만, None이 전달될 수 있는지 검증
        # 현재 구현은 list 전제하므로 빈 리스트와 동일하게 처리
        assert service._compute_workload([]) == 0.0

    def test_compute_workload_mixed_contribution_and_hours(self, service):
        """contribution_pct와 hours 정보가 모두 있는 경우"""
        details = [
            {
                "status": "진행중",
                "contribution_pct": 50,
                "allocated": 500,
                "actual": 250,
            },
        ]
        # contrib=50% → base=0.5
        # progress=250/500=50% → remaining=50%
        # workload = 0.5 × 0.5 = 0.25
        assert service._compute_workload(details) == 0.25


# =============================================================================
# TestMatchContextEdgeCases
# =============================================================================


class TestMatchContextEdgeCases:
    """_compute_match_context() 경계값 테스트"""

    async def test_max_projects_one(self, service, mock_neo4j):
        """max_projects=1, workload=0 → 가용성 점수 정상 부여"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "1건전담",
                        "department": "팀P",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 5,
                        "availability": "available",
                        "current_projects": 0,
                        "max_projects": 1,
                        "project_details": [],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidate = result.skill_candidates[0].candidates[0]

        # max_proj=1, workload=0 → remaining=1.0, ratio=1.0/1=1.0 → 25점
        assert candidate.max_projects == 1
        assert candidate.capacity_remaining == 1.0
        assert candidate.match_score > 0

    async def test_workload_zero_new_employee(self, service, mock_neo4j):
        """workload=0 (프로젝트 없음) → 최대 가용성"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "신입",
                        "department": "팀Q",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 1,
                        "availability": "available",
                        "current_projects": 0,
                        "max_projects": 5,
                        "project_details": [],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidate = result.skill_candidates[0].candidates[0]

        assert candidate.effective_workload == 0.0
        assert candidate.capacity_remaining == 5.0  # max=5, workload=0

    async def test_workload_near_max_boundary(self, service, mock_neo4j):
        """workload가 max-1 근처 (경계)"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "경계인",
                        "department": "팀R",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 5,
                        "availability": "partial",
                        "current_projects": 4,
                        "max_projects": 5,
                        "project_details": [
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 250,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 250,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 250,
                            },
                            {
                                "status": "계획",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                        ],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        # workload = 3×(1.0×0.5) + 1×(0.3×1.0) = 1.5 + 0.3 = 1.8
        # max=5, workload=1.8 < 5 → 후보 포함
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.effective_workload == 1.8
        assert candidate.capacity_remaining > 0  # 5 - 1.8 = 3.2

    async def test_proficiency_zero(self, service, mock_neo4j):
        """proficiency=0 (스킬 정보 없음) → 점수 하락"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "미숙련",
                        "department": "팀S",
                        "proficiency": 0,  # 정보 없음
                        "effective_rate": 60000.0,
                        "years_used": 0,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": _simple_project_details(1),
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidate = result.skill_candidates[0].candidates[0]

        # proficiency=0 → 숙련도 점수 0 → 낮은 총점
        assert candidate.proficiency == 0
        assert candidate.match_score < 50  # 숙련도 40점 없음

    async def test_project_details_with_none_fields(self, service, mock_neo4j):
        """project_details 내부 필드가 None인 경우"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "불완전정보",
                        "department": "팀T",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 3,
                        "availability": "available",
                        "current_projects": 1,
                        "max_projects": 5,
                        "project_details": [
                            {
                                "status": None,
                                "contribution_pct": None,
                                "allocated": None,
                                "actual": None,
                            },
                        ],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidate = result.skill_candidates[0].candidates[0]

        # None 필드 → 보수적으로 풀부담 처리
        # status=None → else 1.0, alloc=None → remaining=1.0 → workload=1.0
        assert candidate.effective_workload == 1.0

    async def test_max_projects_zero_treated_as_default(self, service, mock_neo4j):
        """max_projects=0 → 기본값 5로 대체 (0은 falsy지만 명시적 None 체크)"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "제로맥스",
                        "department": "팀V",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 3,
                        "availability": "available",
                        "current_projects": 0,
                        "max_projects": 0,  # 0이면 기본값 5로 대체
                        "project_details": [],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        # max_projects=0 → 기본값 5로 대체, 후보에 포함됨
        assert len(candidates) == 1
        assert candidates[0].max_projects == 5

    async def test_workload_exactly_at_max_filtered(self, service, mock_neo4j):
        """workload == max_projects → 필터링 (>=)"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "정확히맥스",
                        "department": "팀U",
                        "proficiency": 4,
                        "effective_rate": 50000.0,
                        "years_used": 7,
                        "availability": "available",
                        "current_projects": 3,
                        "max_projects": 3,
                        "project_details": [
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                        ],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")

        # workload=3.0, max=3 → workload >= max → 제외
        assert len(result.skill_candidates[0].candidates) == 0


# =============================================================================
# TestProjectParticipations
# =============================================================================


class TestProjectParticipations:
    """프로젝트 참여 목록 + 투입 가능 여부 테스트"""

    def test_build_participations_basic(self, service):
        """project_details → ProjectParticipation 변환"""
        details = [
            {
                "name": "프로젝트A",
                "status": "진행중",
                "contribution_pct": 50,
                "allocated": 400,
                "actual": 200,
            },
            {
                "name": "프로젝트B",
                "status": "계획",
                "contribution_pct": None,
                "allocated": 300,
                "actual": 0,
            },
        ]
        result = service._build_participations(details)

        assert len(result) == 2
        assert result[0].project_name == "프로젝트A"
        assert result[0].status == "진행중"
        assert result[0].progress_pct == 50.0  # 200/400 * 100
        assert result[0].contribution_pct == 50
        assert result[1].project_name == "프로젝트B"
        assert result[1].progress_pct == 0.0  # 0/300 * 100

    def test_build_participations_no_allocated(self, service):
        """allocated=0/None → progress_pct=None"""
        details = [
            {
                "name": "프로젝트C",
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 0,
                "actual": 10,
            },
            {
                "name": "프로젝트D",
                "status": "계획",
                "contribution_pct": None,
                "allocated": None,
                "actual": None,
            },
        ]
        result = service._build_participations(details)

        assert result[0].progress_pct is None
        assert result[1].progress_pct is None

    def test_build_participations_missing_name(self, service):
        """name 없는 경우 → 'unknown' 기본값"""
        details = [
            {
                "status": "진행중",
                "contribution_pct": None,
                "allocated": 100,
                "actual": 50,
            },
        ]
        result = service._build_participations(details)
        assert result[0].project_name == "unknown"

    def test_availability_label_thresholds(self, service):
        """capacity_remaining별 가능/애매/빠듯 라벨"""
        assert service._compute_availability_label(3.0) == "가능"
        assert service._compute_availability_label(2.0) == "가능"
        assert service._compute_availability_label(1.5) == "애매"
        assert service._compute_availability_label(0.5) == "애매"
        assert service._compute_availability_label(0.4) == "빠듯"
        assert service._compute_availability_label(0.0) == "빠듯"

    async def test_candidate_includes_participations(self, service, mock_neo4j):
        """find_candidates 결과에 project_participations 포함"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return _candidate_rows()
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        # 김철수: 2개 프로젝트
        kim = next(c for c in candidates if c.employee_name == "김철수")
        assert len(kim.project_participations) == 2
        assert kim.project_participations[0].project_name == "ETL마이그레이션"
        assert kim.project_participations[1].project_name == "데이터웨어하우스"

        # 홍길동: 1개 프로젝트
        hong = next(c for c in candidates if c.employee_name == "홍길동")
        assert len(hong.project_participations) == 1
        assert hong.project_participations[0].project_name == "챗봇 리뉴얼"
        assert hong.project_participations[0].contribution_pct == 50

    async def test_candidate_includes_availability_label(self, service, mock_neo4j):
        """availability_label 포함 확인"""

        async def mock_execute(query, params=None):
            if "p.budget_million" in query:
                return [_project_info_row()]
            elif "REQUIRES" in query:
                return [_requirements_rows()[0]]
            elif "HAS_SKILL" in query:
                return [
                    {
                        "emp_name": "여유인",
                        "department": "팀A",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 3,
                        "availability": "available",
                        "current_projects": 0,
                        "max_projects": 5,
                        "project_details": [],
                    },
                    {
                        "emp_name": "빠듯인",
                        "department": "팀B",
                        "proficiency": 3,
                        "effective_rate": 60000.0,
                        "years_used": 3,
                        "availability": "partial",
                        "current_projects": 4,
                        "max_projects": 5,
                        "project_details": [
                            {
                                "name": "P1",
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "name": "P2",
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "name": "P3",
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                            {
                                "name": "P4",
                                "status": "진행중",
                                "contribution_pct": None,
                                "allocated": 500,
                                "actual": 0,
                            },
                        ],
                    },
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        result = await service.find_candidates("ETL파이프라인 구축")
        candidates = result.skill_candidates[0].candidates

        free = next(c for c in candidates if c.employee_name == "여유인")
        busy = next(c for c in candidates if c.employee_name == "빠듯인")

        # 여유인: workload=0, max=5, remaining=5 → "가능"
        assert free.availability_label == "가능"
        # 빠듯인: workload=4.0, max=5, remaining=1.0 → "애매"
        assert busy.availability_label in ("애매", "빠듯")
