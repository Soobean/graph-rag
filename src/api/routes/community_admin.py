"""
Community Admin API Routes

커뮤니티 배치 관리 엔드포인트
- 원클릭 커뮤니티 리프레시
- 커뮤니티 상태 조회
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemas.community_admin import (
    CommunityRefreshRequest,
    CommunityRefreshResponse,
    CommunityStatusResponse,
)
from src.dependencies import get_community_batch_service
from src.domain.exceptions import ConcurrentRefreshError
from src.services.community_batch_service import CommunityBatchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/communities", tags=["community-admin"])


@router.post("/refresh", response_model=CommunityRefreshResponse)
async def refresh_communities(
    request: CommunityRefreshRequest,
    service: Annotated[CommunityBatchService, Depends(get_community_batch_service)],
) -> CommunityRefreshResponse:
    """
    원클릭 커뮤니티 리프레시

    전체 파이프라인을 실행합니다:
    1. 기존 GDS 프로젝션 정리
    2. 스킬 유사도 프로젝션 생성
    3. 커뮤니티 탐지 (Leiden/Louvain)
    4. CommunityMeta 노드에 메타데이터 기록
    5. 프로젝션 정리 (메모리 해제)
    """
    logger.info(
        f"Community refresh request: algorithm={request.algorithm}, "
        f"gamma={request.gamma}"
    )

    try:
        result = await service.refresh(
            algorithm=request.algorithm,
            gamma=request.gamma,
            min_shared_skills=request.min_shared_skills,
        )

        return CommunityRefreshResponse(
            success=result.success,
            algorithm=result.algorithm,
            community_count=result.community_count,
            modularity=result.modularity,
            node_count=result.node_count,
            duration_seconds=result.duration_seconds,
        )

    except ConcurrentRefreshError as e:
        logger.warning(f"Community refresh rejected: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="커뮤니티 리프레시가 이미 진행 중입니다. 잠시 후 다시 시도해주세요.",
        ) from e

    except Exception as e:
        logger.error(f"Community refresh failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="커뮤니티 리프레시 중 오류가 발생했습니다.",
        ) from e


@router.get("/status", response_model=CommunityStatusResponse)
async def get_community_status(
    service: Annotated[CommunityBatchService, Depends(get_community_batch_service)],
) -> CommunityStatusResponse:
    """
    커뮤니티 상태 조회

    마지막 리프레시 시점, 커뮤니티 수, stale 여부 등을 반환합니다.
    """
    try:
        result = await service.get_status()

        return CommunityStatusResponse(
            has_communities=result.has_communities,
            refreshed_at=result.refreshed_at,
            algorithm=result.algorithm,
            community_count=result.community_count,
            modularity=result.modularity,
            assigned_node_count=result.assigned_node_count,
            is_stale=result.is_stale,
        )

    except Exception as e:
        logger.error(f"Community status check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="커뮤니티 상태 조회 중 오류가 발생했습니다.",
        ) from e
