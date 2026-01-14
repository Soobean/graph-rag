"""
Analytics API Routes

GDS 기반 분석 API 엔드포인트
- 커뮤니티 탐지
- 유사 직원 탐색
- 팀 추천
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemas.analytics import (
    CommunityDetectRequest,
    CommunityDetectResponse,
    CommunityInfo,
    ProjectionStatusResponse,
    SimilarEmployee,
    SimilarEmployeeRequest,
    SimilarEmployeeResponse,
    TeamMember,
    TeamRecommendRequest,
    TeamRecommendResponse,
)
from src.dependencies import get_gds_service
from src.services.gds_service import GDSService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


# ============================================
# 프로젝션 관리
# ============================================


@router.post("/projection/create", response_model=ProjectionStatusResponse)
async def create_projection(
    gds: Annotated[GDSService, Depends(get_gds_service)],
    min_shared_skills: int = 2,
) -> ProjectionStatusResponse:
    """
    스킬 유사도 그래프 프로젝션 생성

    직원 간 스킬 유사도를 계산하여 인메모리 그래프를 생성합니다.
    커뮤니티 탐지, 유사 직원 탐색, 팀 추천 기능의 전제 조건입니다.
    """
    try:
        result = await gds.create_skill_similarity_projection(
            min_shared_skills=min_shared_skills,
        )

        return ProjectionStatusResponse(
            exists=True,
            name=result["name"],
            node_count=result["node_count"],
            relationship_count=result["relationship_count"],
        )

    except Exception as e:
        logger.error(f"Failed to create projection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"프로젝션 생성 실패: {e}",
        ) from e


@router.get("/projection/status", response_model=ProjectionStatusResponse)
async def projection_status(
    gds: Annotated[GDSService, Depends(get_gds_service)],
) -> ProjectionStatusResponse:
    """
    현재 프로젝션 상태 조회
    """
    try:
        exists, details = await gds.get_projection_info()

        if exists:
            return ProjectionStatusResponse(
                exists=True,
                name=gds.SKILL_PROJECTION,
                node_count=details.get("nodeCount"),
                relationship_count=details.get("relationshipCount"),
                details=details,
            )
        else:
            return ProjectionStatusResponse(
                exists=False,
                name=gds.SKILL_PROJECTION,
            )

    except Exception as e:
        logger.error(f"Failed to get projection status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"프로젝션 상태 조회 실패: {e}",
        ) from e


@router.delete("/projection", response_model=dict)
async def delete_projection(
    gds: Annotated[GDSService, Depends(get_gds_service)],
) -> dict:
    """
    프로젝션 삭제

    메모리 해제를 위해 사용합니다.
    """
    try:
        dropped = await gds.drop_projection()
        return {
            "success": True,
            "dropped": dropped,
            "message": "프로젝션이 삭제되었습니다." if dropped else "삭제할 프로젝션이 없습니다.",
        }

    except Exception as e:
        logger.error(f"Failed to drop projection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"프로젝션 삭제 실패: {e}",
        ) from e


# ============================================
# 커뮤니티 탐지
# ============================================


@router.post("/communities/detect", response_model=CommunityDetectResponse)
async def detect_communities(
    request: CommunityDetectRequest,
    gds: Annotated[GDSService, Depends(get_gds_service)],
) -> CommunityDetectResponse:
    """
    커뮤니티 탐지 실행

    Leiden 또는 Louvain 알고리즘을 사용하여 직원들의 스킬 기반 커뮤니티를 탐지합니다.
    프로젝션이 없으면 자동으로 생성합니다.
    """
    logger.info(f"Community detection request: algorithm={request.algorithm}")

    try:
        # 프로젝션 확인 및 생성
        exists, _ = await gds.get_projection_info()
        if not exists:
            logger.info("Projection not found, creating...")
            await gds.create_skill_similarity_projection(
                min_shared_skills=request.min_shared_skills,
            )

        # 커뮤니티 탐지
        result = await gds.detect_communities(
            algorithm=request.algorithm,
            gamma=request.gamma,
        )

        # 응답 변환
        communities = [
            CommunityInfo(
                community_id=c["community_id"],
                member_count=c["member_count"],
                sample_members=c["sample_members"][:5],
            )
            for c in result.communities
        ]

        return CommunityDetectResponse(
            success=True,
            algorithm=result.algorithm,
            community_count=result.community_count,
            modularity=result.modularity,
            communities=communities,
        )

    except Exception as e:
        logger.error(f"Community detection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"커뮤니티 탐지 실패: {e}",
        ) from e


# ============================================
# 유사 직원 탐색
# ============================================


@router.post("/employees/similar", response_model=SimilarEmployeeResponse)
async def find_similar_employees(
    request: SimilarEmployeeRequest,
    gds: Annotated[GDSService, Depends(get_gds_service)],
) -> SimilarEmployeeResponse:
    """
    유사 직원 탐색

    특정 직원과 스킬 유사도가 높은 직원들을 찾습니다.
    """
    logger.info(f"Similar employees request: {request.employee_name}")

    try:
        # 프로젝션 확인
        exists, _ = await gds.get_projection_info()
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="프로젝션이 없습니다. /projection/create를 먼저 호출하세요.",
            )

        # 유사 직원 탐색
        similar = await gds.find_similar_employees(
            employee_name=request.employee_name,
            top_k=request.top_k,
        )

        # 응답 변환
        employees = [
            SimilarEmployee(
                name=emp["name"],
                job_type=emp.get("job_type"),
                similarity=emp["similarity"],
                shared_skills=emp["shared_skills"],
                community_id=emp.get("community_id"),
            )
            for emp in similar
        ]

        return SimilarEmployeeResponse(
            success=True,
            base_employee=request.employee_name,
            similar_employees=employees,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Similar employee search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"유사 직원 탐색 실패: {e}",
        ) from e


# ============================================
# 팀 추천
# ============================================


@router.post("/team/recommend", response_model=TeamRecommendResponse)
async def recommend_team(
    request: TeamRecommendRequest,
    gds: Annotated[GDSService, Depends(get_gds_service)],
) -> TeamRecommendResponse:
    """
    최적 팀 구성 추천

    필요한 스킬 셋을 커버하면서 커뮤니티 다양성을 고려한 최적의 팀을 추천합니다.

    **알고리즘:**
    1. 필요 스킬을 가진 후보자 검색
    2. 그리디 방식으로 스킬 커버리지 최적화
    3. 커뮤니티 다양성 고려 (사일로 방지)
    """
    logger.info(f"Team recommendation request: skills={request.required_skills}")

    try:
        # 프로젝션 확인
        exists, _ = await gds.get_projection_info()
        if not exists:
            # 자동 생성
            logger.info("Projection not found, creating...")
            await gds.create_skill_similarity_projection()

        # 팀 추천
        result = await gds.recommend_team(
            required_skills=request.required_skills,
            team_size=request.team_size,
            diversity_weight=request.diversity_weight,
        )

        # 응답 변환
        members = [
            TeamMember(
                name=m["name"],
                job_type=m.get("job_type"),
                community_id=m.get("communityId"),
                matched_skills=m.get("matchedSkills", []),
                skill_count=m.get("skillCount", 0),
            )
            for m in result.members
        ]

        return TeamRecommendResponse(
            success=True,
            required_skills=request.required_skills,
            members=members,
            skill_coverage=result.skill_coverage,
            covered_skills=result.covered_skills,
            missing_skills=result.missing_skills,
            community_diversity=result.community_diversity,
        )

    except Exception as e:
        logger.error(f"Team recommendation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"팀 추천 실패: {e}",
        ) from e
