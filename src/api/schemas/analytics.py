"""
Analytics API Schemas

GDS 분석 API 요청/응답 스키마 정의
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# ============================================
# 커뮤니티 탐지
# ============================================


class CommunityDetectRequest(BaseModel):
    """커뮤니티 탐지 요청"""

    algorithm: Literal["leiden", "louvain"] = Field(
        default="leiden",
        description="사용할 알고리즘 (leiden 권장)",
    )
    gamma: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Resolution 파라미터 (높을수록 작은 커뮤니티)",
    )
    min_shared_skills: int = Field(
        default=2,
        ge=1,
        le=10,
        description="유사도 계산 시 최소 공유 스킬 수",
    )


class CommunityInfo(BaseModel):
    """커뮤니티 정보"""

    community_id: int = Field(description="커뮤니티 ID")
    member_count: int = Field(description="멤버 수")
    sample_members: list[str] = Field(description="샘플 멤버 (최대 5명)")


class CommunityDetectResponse(BaseModel):
    """커뮤니티 탐지 응답"""

    success: bool = Field(description="성공 여부")
    algorithm: str = Field(description="사용된 알고리즘")
    community_count: int = Field(description="탐지된 커뮤니티 수")
    modularity: float = Field(description="모듈성 점수 (0~1, 높을수록 좋음)")
    communities: list[CommunityInfo] = Field(description="커뮤니티 목록")


# ============================================
# 유사 직원 탐색
# ============================================


class SimilarEmployeeRequest(BaseModel):
    """유사 직원 조회 요청"""

    employee_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="기준 직원 이름",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="반환할 최대 결과 수",
    )


class SimilarEmployee(BaseModel):
    """유사 직원 정보"""

    name: str = Field(description="직원 이름")
    job_type: str | None = Field(description="직무 유형")
    similarity: float = Field(description="유사도 (0~1)")
    shared_skills: int = Field(description="공유 스킬 수")
    community_id: int | None = Field(default=None, description="소속 커뮤니티")


class SimilarEmployeeResponse(BaseModel):
    """유사 직원 조회 응답"""

    success: bool = Field(description="성공 여부")
    base_employee: str = Field(description="기준 직원")
    similar_employees: list[SimilarEmployee] = Field(description="유사 직원 목록")


# ============================================
# 팀 추천
# ============================================


class TeamRecommendRequest(BaseModel):
    """팀 추천 요청"""

    required_skills: list[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="필요한 스킬 목록",
        examples=[["Python", "Kubernetes", "React"]],
    )
    team_size: int = Field(
        default=5,
        ge=2,
        le=20,
        description="추천 팀 규모",
    )
    diversity_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="커뮤니티 다양성 가중치 (0: 무시, 1: 최우선)",
    )


class TeamMember(BaseModel):
    """팀 멤버 정보"""

    name: str = Field(description="직원 이름")
    job_type: str | None = Field(description="직무 유형")
    community_id: int | None = Field(default=None, description="소속 커뮤니티")
    matched_skills: list[str] = Field(description="매칭된 스킬")
    skill_count: int = Field(description="총 보유 스킬 수")


class TeamRecommendResponse(BaseModel):
    """팀 추천 응답"""

    success: bool = Field(description="성공 여부")
    required_skills: list[str] = Field(description="요청된 스킬")
    members: list[TeamMember] = Field(description="추천 팀원")
    skill_coverage: float = Field(description="스킬 커버리지 (0~1)")
    covered_skills: list[str] = Field(description="커버된 스킬 목록")
    missing_skills: list[str] = Field(description="미커버 스킬 목록")
    community_diversity: int = Field(description="팀 내 커뮤니티 다양성")


# ============================================
# 프로젝션 상태
# ============================================


class ProjectionStatusResponse(BaseModel):
    """프로젝션 상태 응답"""

    exists: bool = Field(description="프로젝션 존재 여부")
    name: str = Field(description="프로젝션 이름")
    node_count: int | None = Field(default=None, description="노드 수")
    relationship_count: int | None = Field(default=None, description="관계 수")
    details: dict[str, Any] | None = Field(default=None, description="상세 정보")
