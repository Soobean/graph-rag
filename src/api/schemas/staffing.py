"""
Project Staffing 스키마 정의

비용 기반 프로젝트 인력 배치 시나리오:
1. 프로젝트 후보자 탐색 (예산 내)
2. 스태핑 플랜 + 예상 비용
3. 예산 대비 인건비 분석
"""

from pydantic import BaseModel, Field

# =============================================================================
# 공통 모델
# =============================================================================


class ProjectListItem(BaseModel):
    """프로젝트 목록 아이템 (드롭다운용)"""

    name: str = Field(..., description="프로젝트 이름")
    status: str | None = Field(default=None, description="프로젝트 상태")
    budget_million: float | None = Field(default=None, description="예산 (백만원)")
    required_headcount: int | None = Field(default=None, description="필요 인원")


class ProjectListResponse(BaseModel):
    """프로젝트 목록 응답"""

    projects: list[ProjectListItem] = Field(
        default_factory=list, description="프로젝트 목록"
    )


class SkillCategory(BaseModel):
    """스킬 카테고리 정보"""

    name: str = Field(..., description="카테고리명")
    color: str = Field(default="#6B7280", description="UI 표시용 색상")
    skills: list[str] = Field(default_factory=list, description="소속 스킬 목록")


class SkillCategoryListResponse(BaseModel):
    """스킬 카테고리 목록 응답"""

    categories: list[SkillCategory] = Field(
        default_factory=list,
        description="카테고리 목록",
    )


# =============================================================================
# Scenario 1: 프로젝트 후보자 탐색
# =============================================================================


class FindCandidatesRequest(BaseModel):
    """후보자 탐색 요청"""

    project_name: str = Field(
        ...,
        description="프로젝트 이름",
        examples=["ETL파이프라인 구축", "챗봇 리뉴얼"],
    )
    skill_name: str | None = Field(
        default=None,
        description="특정 스킬로 필터링 (없으면 전체 REQUIRES 스킬)",
    )
    min_proficiency: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="최소 숙련도 필터 (1~5)",
    )


class ProjectParticipation(BaseModel):
    """후보자의 프로젝트 참여 정보"""

    project_name: str = Field(..., description="프로젝트명")
    status: str | None = Field(default=None, description="프로젝트 상태 (진행중/계획)")
    progress_pct: float | None = Field(
        default=None, description="진행률 % (actual/allocated)"
    )
    contribution_pct: float | None = Field(default=None, description="투입 비율 %")


class CandidateInfo(BaseModel):
    """적격 후보자 정보"""

    employee_name: str = Field(..., description="직원 이름")
    department: str | None = Field(default=None, description="소속 부서")
    proficiency: int = Field(..., description="해당 스킬 숙련도 (1~5)")
    effective_rate: float = Field(..., description="유효 단가 (원/시간)")
    availability: str | None = Field(default=None, description="가용 상태")
    current_projects: int = Field(default=0, description="현재 참여 프로젝트 수")
    max_projects: int = Field(default=5, description="최대 참여 가능 프로젝트 수")
    effective_workload: float = Field(
        default=0.0,
        description="가중 워크로드 (프로젝트 상태·진행률·투입비율 반영)",
    )
    years_used: int = Field(default=0, description="해당 스킬 사용 연수")
    match_score: int = Field(default=0, ge=0, le=100, description="매칭 점수 (0~100)")
    proficiency_gap: int = Field(
        default=0, description="숙련도 갭 (양수=초과, 0=충족, 음수=미달)"
    )
    cost_efficiency: float | None = Field(
        default=None, description="비용 효율 (max_rate/effective_rate×100)"
    )
    capacity_remaining: float = Field(
        default=0.0, description="잔여 가용 여력 (max_projects - workload - 1)"
    )
    match_reasons: list[str] = Field(default_factory=list, description="추천 사유 목록")
    project_participations: list[ProjectParticipation] = Field(
        default_factory=list, description="현재 프로젝트 참여 내역"
    )
    availability_label: str = Field(
        default="가능", description="투입 가능 여부 (가능/애매/빠듯)"
    )


class SkillCandidates(BaseModel):
    """스킬별 후보자 목록"""

    skill_name: str = Field(..., description="필요 스킬")
    required_proficiency: int | None = Field(default=None, description="요구 숙련도")
    max_hourly_rate: float | None = Field(default=None, description="최대 시급 (원)")
    required_headcount: int | None = Field(default=None, description="필요 인원")
    importance: str | None = Field(default=None, description="중요도")
    candidates: list[CandidateInfo] = Field(
        default_factory=list, description="적격 후보자 목록 (단가순)"
    )


class FindCandidatesResponse(BaseModel):
    """후보자 탐색 결과"""

    project_name: str = Field(..., description="프로젝트 이름")
    project_budget: float | None = Field(
        default=None, description="프로젝트 예산 (백만원)"
    )
    estimated_hours: float | None = Field(
        default=None, description="예상 총 공수 (시간)"
    )
    required_headcount: int | None = Field(default=None, description="필요 총 인원")
    skill_candidates: list[SkillCandidates] = Field(
        default_factory=list, description="스킬별 후보자 목록"
    )
    total_skills: int = Field(default=0, description="필요 스킬 수")
    total_candidates: int = Field(default=0, description="전체 고유 후보자 수")


# =============================================================================
# Scenario 2: 스태핑 플랜 + 예상 비용
# =============================================================================


class StaffingPlanRequest(BaseModel):
    """스태핑 플랜 요청"""

    project_name: str = Field(
        ...,
        description="프로젝트 이름",
        examples=["ETL파이프라인 구축"],
    )
    top_n_per_skill: int = Field(
        default=3,
        ge=1,
        le=10,
        description="스킬당 추천 인원 수",
    )


class RecommendedCandidate(BaseModel):
    """추천 후보자 (스태핑 플랜용)"""

    employee_name: str = Field(..., description="직원 이름")
    department: str | None = Field(default=None, description="소속 부서")
    proficiency: int = Field(..., description="숙련도")
    effective_rate: float = Field(..., description="유효 단가")
    availability: str | None = Field(default=None, description="가용 상태")
    match_score: int = Field(default=0, description="매칭 점수 (0~100)")
    match_reasons: list[str] = Field(default_factory=list, description="추천 사유 요약")


class SkillStaffingPlan(BaseModel):
    """스킬별 스태핑 플랜"""

    skill_name: str = Field(..., description="필요 스킬")
    importance: str | None = Field(default=None, description="중요도")
    required_headcount: int | None = Field(default=None, description="필요 인원")
    recommended_candidates: list[RecommendedCandidate] = Field(
        default_factory=list, description="추천 후보자"
    )
    estimated_cost_per_hour: float = Field(
        default=0.0, description="추천 인원 기준 시간당 예상 비용"
    )


class StaffingPlanResponse(BaseModel):
    """스태핑 플랜 결과"""

    project_name: str = Field(..., description="프로젝트 이름")
    project_budget: float | None = Field(
        default=None, description="프로젝트 예산 (백만원)"
    )
    estimated_hours: float | None = Field(
        default=None, description="예상 총 공수 (시간)"
    )
    skill_plans: list[SkillStaffingPlan] = Field(
        default_factory=list, description="스킬별 스태핑 플랜"
    )
    total_estimated_labor_cost: float = Field(
        default=0.0, description="총 예상 인건비 (원)"
    )
    budget_utilization_percent: float | None = Field(
        default=None, description="예산 대비 인건비 비율 (%)"
    )


# =============================================================================
# Scenario 3: 예산 대비 인건비 분석
# =============================================================================


class BudgetAnalysisRequest(BaseModel):
    """예산 분석 요청"""

    project_name: str = Field(
        ...,
        description="프로젝트 이름",
        examples=["챗봇 리뉴얼"],
    )


class TeamMemberCost(BaseModel):
    """팀원별 비용 내역"""

    employee_name: str = Field(..., description="직원 이름")
    role: str | None = Field(default=None, description="프로젝트 내 역할")
    agreed_rate: float = Field(default=0.0, description="합의 단가 (원/시간)")
    allocated_hours: float = Field(default=0.0, description="배정 공수 (시간)")
    actual_hours: float = Field(default=0.0, description="실제 공수 (시간)")
    planned_cost: float = Field(default=0.0, description="계획 비용 (원)")
    actual_cost: float = Field(default=0.0, description="실제 비용 (원)")


class BudgetAnalysisResponse(BaseModel):
    """예산 분석 결과"""

    project_name: str = Field(..., description="프로젝트 이름")
    project_budget: float | None = Field(
        default=None, description="프로젝트 예산 (백만원)"
    )
    budget_allocated: float | None = Field(default=None, description="배정 예산 (원)")
    budget_spent: float | None = Field(default=None, description="집행 예산 (원)")
    team_breakdown: list[TeamMemberCost] = Field(
        default_factory=list, description="팀원별 비용 내역"
    )
    total_planned_cost: float = Field(default=0.0, description="총 계획 인건비 (원)")
    total_actual_cost: float = Field(default=0.0, description="총 실제 인건비 (원)")
    variance: float = Field(default=0.0, description="차이 (실제 - 계획, 양수=초과)")
    variance_percent: float | None = Field(default=None, description="차이 비율 (%)")
