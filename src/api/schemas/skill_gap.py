"""
Skill Gap Analysis 스키마 정의

온톨로지 기반 스킬 갭 분석을 위한 Request/Response 모델
"""

from enum import Enum
from typing import Self

from pydantic import BaseModel, Field, model_validator

# Enums


class CoverageStatus(str, Enum):
    """스킬 커버리지 상태"""

    COVERED = "covered"  # 직접 보유자 있음
    PARTIAL = "partial"  # 유사 스킬 보유자만 있음
    GAP = "gap"  # 관련 인력 없음


class MatchType(str, Enum):
    """스킬 매칭 타입"""

    SAME_CATEGORY = "same_category"  # Java ↔ Python (같은 Backend)
    PARENT_CATEGORY = "parent"  # Backend 경험 → Python 필요
    RELATED = "related"  # 같은 상위 카테고리 (Programming)
    NONE = "none"  # 관련 없음


# Request Models


class SkillGapAnalyzeRequest(BaseModel):
    """스킬 갭 분석 요청"""

    required_skills: list[str] = Field(
        ...,
        description="필요한 스킬 목록",
        min_length=1,
        max_length=20,
        examples=[["Python", "LangGraph", "NLP", "Kubernetes"]],
    )
    team_members: list[str] | None = Field(
        default=None,
        description="분석 대상 팀원 이름 목록 (project_id 미지정 시 필수)",
        min_length=1,
        examples=[["홍길동", "김철수", "박지수"]],
    )
    project_id: str | None = Field(
        default=None,
        description="프로젝트 이름 (팀원 자동 조회용, team_members 미지정 시 필수)",
        examples=["GraphRAG 프로젝트", "AI 챗봇 개발"],
    )

    @model_validator(mode="after")
    def check_team_source(self) -> Self:
        """team_members 또는 project_id 중 하나는 필수"""
        if self.team_members is None and not self.project_id:
            raise ValueError("team_members 또는 project_id 중 하나는 필수입니다")
        return self


class SkillRecommendRequest(BaseModel):
    """갭 해소 추천 요청"""

    skill: str = Field(
        ...,
        description="부족한 스킬",
        examples=["NLP"],
    )
    exclude_members: list[str] = Field(
        default_factory=list,
        description="제외할 팀원 목록 (이미 팀에 있는 인원)",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="추천 인원 수",
    )


# Response Models - 세부 항목


class SkillMatch(BaseModel):
    """유사 스킬 매칭 정보"""

    employee_name: str = Field(..., description="직원 이름")
    possessed_skill: str = Field(..., description="보유 스킬")
    match_type: MatchType = Field(..., description="매칭 타입")
    common_ancestor: str | None = Field(
        default=None,
        description="공통 상위 개념 (Backend, LLM Framework 등)",
    )
    explanation: str = Field(..., description="매칭 설명")


class SkillCoverage(BaseModel):
    """단일 스킬 커버리지 분석 결과"""

    skill: str = Field(..., description="필요 스킬")
    category: str | None = Field(default=None, description="소속 카테고리")
    category_color: str | None = Field(
        default=None,
        description="UI 표시용 카테고리 색상",
    )
    status: CoverageStatus = Field(..., description="커버리지 상태")

    exact_matches: list[str] = Field(
        default_factory=list,
        description="직접 보유자 목록",
    )
    similar_matches: list[SkillMatch] = Field(
        default_factory=list,
        description="유사 스킬 보유자 목록",
    )

    explanation: str = Field(..., description="상태 설명")


class CategoryCoverage(BaseModel):
    """카테고리별 커버리지 요약"""

    category: str = Field(..., description="카테고리명")
    color: str = Field(default="#6B7280", description="UI 표시용 색상")
    total_skills: int = Field(..., description="필요 스킬 수")
    covered_count: int = Field(default=0, description="커버된 스킬 수")
    partial_count: int = Field(default=0, description="부분 커버 스킬 수")
    gap_count: int = Field(default=0, description="갭 스킬 수")
    coverage_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="커버리지 비율 (0.0 ~ 1.0)",
    )


class RecommendedEmployee(BaseModel):
    """추천 인력"""

    name: str = Field(..., description="직원 이름")
    department: str | None = Field(default=None, description="소속 부서")
    current_skills: list[str] = Field(
        default_factory=list,
        description="보유 스킬 목록",
    )
    match_type: MatchType = Field(..., description="매칭 타입")
    matched_skill: str = Field(..., description="매칭된 스킬")
    reason: str = Field(..., description="추천 사유")
    current_projects: int = Field(
        default=0,
        ge=0,
        description="현재 참여 중인 프로젝트 수",
    )


# =============================================================================
# Response Models - 최종 응답
# =============================================================================


class SkillGapAnalyzeResponse(BaseModel):
    """스킬 갭 분석 결과"""

    # 요약
    team_members: list[str] = Field(..., description="분석 대상 팀원")
    total_required_skills: int = Field(..., description="필요 스킬 총 개수")
    overall_status: CoverageStatus = Field(..., description="전체 상태")

    # 카테고리별 요약
    category_summary: list[CategoryCoverage] = Field(
        default_factory=list,
        description="카테고리별 커버리지 요약",
    )

    # 상세 스킬별 분석
    skill_details: list[SkillCoverage] = Field(
        default_factory=list,
        description="스킬별 상세 분석",
    )

    # 갭 목록 (빠른 접근용)
    gaps: list[str] = Field(
        default_factory=list,
        description="갭 스킬 목록",
    )

    # 추천
    recommendations: list[str] = Field(
        default_factory=list,
        description="갭 해소 추천 메시지",
    )


class SkillRecommendResponse(BaseModel):
    """갭 해소 추천 결과"""

    target_skill: str = Field(..., description="대상 스킬")
    category: str | None = Field(default=None, description="스킬 카테고리")

    # 내부 추천 (교육 대상)
    internal_candidates: list[RecommendedEmployee] = Field(
        default_factory=list,
        description="내부 교육 추천 인력",
    )

    # 외부 추천 (충원)
    external_search_query: str = Field(
        default="",
        description="외부 채용 검색 키워드",
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
