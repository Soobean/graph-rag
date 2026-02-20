"""
Ontology Admin API - 온톨로지 제안 관리

OntologyProposal 관리를 위한 9개 Admin API 엔드포인트를 제공합니다.

엔드포인트:
1. GET  /proposals - 목록 조회 (필터/페이지네이션)
2. GET  /proposals/{id} - 상세 조회
3. POST /proposals - 수동 생성
4. PATCH /proposals/{id} - 수정
5. POST /proposals/{id}/approve - 승인
6. POST /proposals/{id}/reject - 거절
7. POST /proposals/batch-approve - 일괄 승인
8. POST /proposals/batch-reject - 일괄 거절
9. GET  /stats - 통계
"""

import math
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.schemas.ontology_admin import (
    BatchApproveRequest,
    BatchOperationResponse,
    BatchRejectRequest,
    OntologyStatsResponse,
    PaginationMeta,
    ProposalApproveRequest,
    ProposalCreateRequest,
    ProposalDetailResponse,
    ProposalListResponse,
    ProposalRejectRequest,
    ProposalResponse,
    ProposalUpdateRequest,
    UnresolvedTermStats,
)
from src.dependencies import get_current_reviewer_id, get_ontology_service
from src.domain.adaptive.models import OntologyProposal
from src.domain.exceptions import (
    ConflictError,
    InvalidStateError,
    ProposalNotFoundError,
)
from src.services.ontology_service import OntologyService

router = APIRouter(prefix="/api/v1/ontology/admin", tags=["ontology-admin"])


def _proposal_to_response(proposal: OntologyProposal) -> ProposalResponse:
    """OntologyProposal을 ProposalResponse로 변환"""
    # 최근 5개 질문만 포함
    recent_questions = proposal.evidence_questions[-5:]

    return ProposalResponse(
        id=proposal.id,
        version=proposal.version,
        proposal_type=proposal.proposal_type.value,
        term=proposal.term,
        category=proposal.category,
        suggested_action=proposal.suggested_action,
        suggested_parent=proposal.suggested_parent,
        suggested_canonical=proposal.suggested_canonical,
        suggested_relation_type=proposal.suggested_relation_type,
        frequency=proposal.frequency,
        confidence=proposal.confidence,
        status=proposal.status.value,
        source=proposal.source.value,
        evidence_questions=recent_questions,
        created_at=proposal.created_at,
        reviewed_at=proposal.reviewed_at,
        reviewed_by=proposal.reviewed_by,
        applied_at=proposal.applied_at,
    )


def _proposal_to_detail_response(proposal: OntologyProposal) -> ProposalDetailResponse:
    """OntologyProposal을 ProposalDetailResponse로 변환"""
    return ProposalDetailResponse(
        id=proposal.id,
        version=proposal.version,
        proposal_type=proposal.proposal_type.value,
        term=proposal.term,
        category=proposal.category,
        suggested_action=proposal.suggested_action,
        suggested_parent=proposal.suggested_parent,
        suggested_canonical=proposal.suggested_canonical,
        suggested_relation_type=proposal.suggested_relation_type,
        frequency=proposal.frequency,
        confidence=proposal.confidence,
        status=proposal.status.value,
        source=proposal.source.value,
        evidence_questions=proposal.evidence_questions[-5:],
        created_at=proposal.created_at,
        reviewed_at=proposal.reviewed_at,
        reviewed_by=proposal.reviewed_by,
        applied_at=proposal.applied_at,
        all_evidence_questions=proposal.evidence_questions,
        rejection_reason=proposal.rejection_reason,
    )


# ============================================
# 1. 목록 조회
# ============================================


@router.get("/proposals", response_model=ProposalListResponse)
async def list_proposals(
    service: Annotated[OntologyService, Depends(get_ontology_service)],
    status: Literal[
        "pending", "approved", "rejected", "auto_approved", "all"
    ] = "pending",
    proposal_type: Literal["NEW_CONCEPT", "NEW_SYNONYM", "NEW_RELATION", "all"] = "all",
    source: Literal["chat", "background", "admin", "all"] = "all",
    category: str | None = Query(default=None, max_length=50),
    term_search: str | None = Query(default=None, max_length=100),
    sort_by: Literal["created_at", "frequency", "confidence"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1, description="페이지 번호 (1부터 시작)"),
    page_size: int = Query(default=50, ge=1, le=100, description="페이지 크기"),
) -> ProposalListResponse:
    """
    온톨로지 제안 목록 조회

    - **status**: 상태 필터 (기본값: pending)
    - **proposal_type**: 유형 필터
    - **source**: 출처 필터 (chat, background, admin)
    - **category**: 카테고리 필터
    - **term_search**: 용어 검색 (부분 일치)
    - **sort_by**: 정렬 필드
    - **sort_order**: 정렬 방향
    - **page**: 페이지 번호
    - **page_size**: 페이지 크기 (최대 100)
    """
    proposals, total = await service.list_proposals(
        status=status,
        proposal_type=proposal_type,
        source=source,
        category=category,
        term_search=term_search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    # total=0이면 total_pages도 0 (빈 결과일 때 페이지가 없음이 명확)
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return ProposalListResponse(
        items=[_proposal_to_response(p) for p in proposals],
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


# ============================================
# 2. 상세 조회
# ============================================


@router.get("/proposals/{proposal_id}", response_model=ProposalDetailResponse)
async def get_proposal(
    proposal_id: str,
    service: Annotated[OntologyService, Depends(get_ontology_service)],
) -> ProposalDetailResponse:
    """
    온톨로지 제안 상세 조회

    - **proposal_id**: 제안 ID (UUID)
    """
    try:
        proposal = await service.get_proposal(proposal_id)
        return _proposal_to_detail_response(proposal)
    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e


# ============================================
# 3. 수동 생성
# ============================================


@router.post("/proposals", response_model=ProposalResponse, status_code=201)
async def create_proposal(
    request: ProposalCreateRequest,
    service: Annotated[OntologyService, Depends(get_ontology_service)],
) -> ProposalResponse:
    """
    온톨로지 제안 수동 생성

    관리자가 직접 새로운 제안을 생성합니다.
    """
    proposal = await service.create_proposal(
        term=request.term,
        category=request.category,
        proposal_type=request.proposal_type,
        suggested_parent=request.suggested_parent,
        suggested_canonical=request.suggested_canonical,
        relation_type=request.relation_type,
        note=request.note,
    )

    return _proposal_to_response(proposal)


# ============================================
# 4. 수정
# ============================================


@router.patch("/proposals/{proposal_id}", response_model=ProposalResponse)
async def update_proposal(
    proposal_id: str,
    request: ProposalUpdateRequest,
    service: Annotated[OntologyService, Depends(get_ontology_service)],
) -> ProposalResponse:
    """
    온톨로지 제안 수정

    - **expected_version**: Optimistic Locking을 위한 예상 버전 (필수)
    - 버전이 일치하지 않으면 409 Conflict 반환
    """
    try:
        updates = {}
        if request.suggested_parent is not None:
            updates["suggested_parent"] = request.suggested_parent
        if request.suggested_canonical is not None:
            updates["suggested_canonical"] = request.suggested_canonical
        if request.category is not None:
            updates["category"] = request.category

        proposal = await service.update_proposal(
            proposal_id=proposal_id,
            expected_version=request.expected_version,
            updates=updates,
        )
        return _proposal_to_response(proposal)

    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except ConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": e.message,
                "code": e.code,
                "expected_version": e.expected_version,
                "current_version": e.current_version,
            },
        ) from e


# ============================================
# 5. 승인
# ============================================


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
async def approve_proposal(
    proposal_id: str,
    request: ProposalApproveRequest,
    service: Annotated[OntologyService, Depends(get_ontology_service)],
    reviewer_id: Annotated[str, Depends(get_current_reviewer_id)],
) -> ProposalResponse:
    """
    온톨로지 제안 승인

    - **expected_version**: Optimistic Locking을 위한 예상 버전 (필수)
    - **canonical**: 승인 시 확정할 정규 형태 (선택)
    - **parent**: 승인 시 확정할 부모 개념 (선택)
    """
    try:
        proposal = await service.approve_proposal(
            proposal_id=proposal_id,
            expected_version=request.expected_version,
            reviewer=reviewer_id,
            canonical=request.canonical,
            parent=request.parent,
            note=request.note,
        )
        return _proposal_to_response(proposal)

    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except InvalidStateError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "message": e.message,
                "code": e.code,
                "current_state": e.current_state,
            },
        ) from e
    except ConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": e.message,
                "code": e.code,
                "expected_version": e.expected_version,
                "current_version": e.current_version,
            },
        ) from e


# ============================================
# 6. 거절
# ============================================


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
async def reject_proposal(
    proposal_id: str,
    request: ProposalRejectRequest,
    service: Annotated[OntologyService, Depends(get_ontology_service)],
    reviewer_id: Annotated[str, Depends(get_current_reviewer_id)],
) -> ProposalResponse:
    """
    온톨로지 제안 거절

    - **expected_version**: Optimistic Locking을 위한 예상 버전 (필수)
    - **reason**: 거절 사유 (필수)
    """
    try:
        proposal = await service.reject_proposal(
            proposal_id=proposal_id,
            expected_version=request.expected_version,
            reviewer=reviewer_id,
            reason=request.reason,
        )
        return _proposal_to_response(proposal)

    except ProposalNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message) from e
    except InvalidStateError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "message": e.message,
                "code": e.code,
                "current_state": e.current_state,
            },
        ) from e
    except ConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": e.message,
                "code": e.code,
                "expected_version": e.expected_version,
                "current_version": e.current_version,
            },
        ) from e


# ============================================
# 7. 일괄 승인
# ============================================


@router.post("/proposals/batch-approve", response_model=BatchOperationResponse)
async def batch_approve(
    request: BatchApproveRequest,
    service: Annotated[OntologyService, Depends(get_ontology_service)],
    reviewer_id: Annotated[str, Depends(get_current_reviewer_id)],
) -> BatchOperationResponse:
    """
    온톨로지 제안 일괄 승인

    - pending 상태인 제안만 승인됩니다
    - 이미 처리된 제안은 failed_ids에 포함됩니다
    """
    result = await service.batch_approve(
        proposal_ids=request.proposal_ids,
        reviewer=reviewer_id,
        note=request.note,
    )

    return BatchOperationResponse(
        success_count=result.success_count,
        failed_count=result.failed_count,
        failed_ids=result.failed_ids,
        errors=result.errors,
    )


# ============================================
# 8. 일괄 거절
# ============================================


@router.post("/proposals/batch-reject", response_model=BatchOperationResponse)
async def batch_reject(
    request: BatchRejectRequest,
    service: Annotated[OntologyService, Depends(get_ontology_service)],
    reviewer_id: Annotated[str, Depends(get_current_reviewer_id)],
) -> BatchOperationResponse:
    """
    온톨로지 제안 일괄 거절

    - pending 상태인 제안만 거절됩니다
    - **reason**: 거절 사유 (필수, 모든 제안에 동일하게 적용)
    """
    result = await service.batch_reject(
        proposal_ids=request.proposal_ids,
        reviewer=reviewer_id,
        reason=request.reason,
    )

    return BatchOperationResponse(
        success_count=result.success_count,
        failed_count=result.failed_count,
        failed_ids=result.failed_ids,
        errors=result.errors,
    )


# ============================================
# 9. 통계
# ============================================


@router.get("/stats", response_model=OntologyStatsResponse)
async def get_stats(
    service: Annotated[OntologyService, Depends(get_ontology_service)],
) -> OntologyStatsResponse:
    """
    온톨로지 통계 조회

    - 상태별 제안 수
    - 카테고리별 분포
    - 빈도 높은 미해결 용어 TOP 10
    """
    stats = await service.get_stats()

    return OntologyStatsResponse(
        total_proposals=stats["total_proposals"],
        pending_count=stats["pending_count"],
        approved_count=stats["approved_count"],
        auto_approved_count=stats["auto_approved_count"],
        rejected_count=stats["rejected_count"],
        category_distribution=stats["category_distribution"],
        top_unresolved_terms=[
            UnresolvedTermStats(
                term=t["term"],
                category=t["category"],
                frequency=t["frequency"],
                confidence=t["confidence"],
            )
            for t in stats["top_unresolved_terms"]
        ],
    )
