"""
Community Admin API Schemas

커뮤니티 배치 관리 API 요청/응답 스키마 정의
"""

from typing import Literal

from pydantic import BaseModel, Field


class CommunityRefreshRequest(BaseModel):
    """커뮤니티 리프레시 요청"""

    algorithm: Literal["leiden", "louvain"] = Field(
        default="leiden",
        description="커뮤니티 탐지 알고리즘 (leiden 권장)",
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


class CommunityRefreshResponse(BaseModel):
    """커뮤니티 리프레시 응답"""

    success: bool = Field(description="성공 여부")
    algorithm: str = Field(description="사용된 알고리즘")
    community_count: int = Field(description="탐지된 커뮤니티 수")
    modularity: float = Field(description="모듈성 점수 (0~1, 높을수록 좋음)")
    node_count: int = Field(description="communityId가 부여된 노드 수")
    duration_seconds: float = Field(description="실행 시간 (초)")


class CommunityStatusResponse(BaseModel):
    """커뮤니티 상태 조회 응답"""

    has_communities: bool = Field(description="커뮤니티 존재 여부")
    refreshed_at: str | None = Field(description="마지막 리프레시 시점 (ISO format)")
    algorithm: str | None = Field(description="마지막 사용 알고리즘")
    community_count: int = Field(description="커뮤니티 수")
    modularity: float | None = Field(description="모듈성 점수")
    assigned_node_count: int = Field(description="communityId가 있는 Employee 수")
    is_stale: bool = Field(description="24시간 이상 경과 여부")
