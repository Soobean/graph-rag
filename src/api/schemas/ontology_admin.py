"""
Ontology Admin API 스키마

OntologyProposal 관리를 위한 Request/Response 모델을 정의합니다.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ============================================
# Pagination
# ============================================


class PaginationMeta(BaseModel):
    """페이지네이션 메타데이터"""

    total: int = Field(..., description="전체 레코드 수")
    page: int = Field(..., description="현재 페이지 (1부터 시작)")
    page_size: int = Field(..., description="페이지당 레코드 수")
    total_pages: int = Field(..., description="전체 페이지 수")
    has_next: bool = Field(..., description="다음 페이지 존재 여부")
    has_prev: bool = Field(..., description="이전 페이지 존재 여부")


# ============================================
# Request Models
# ============================================


class ProposalCreateRequest(BaseModel):
    """제안 수동 생성 요청"""

    term: str = Field(..., min_length=1, max_length=100, description="용어")
    category: str = Field(..., min_length=1, max_length=50, description="카테고리")
    proposal_type: Literal["NEW_CONCEPT", "NEW_SYNONYM", "NEW_RELATION"] = Field(
        ..., description="제안 유형"
    )
    suggested_parent: str | None = Field(
        default=None, max_length=100, description="제안된 부모 개념 (NEW_CONCEPT용)"
    )
    suggested_canonical: str | None = Field(
        default=None, max_length=100, description="제안된 정규 형태 (NEW_SYNONYM용)"
    )
    relation_type: Literal["IS_A", "SAME_AS", "REQUIRES", "PART_OF"] | None = Field(
        default=None, description="관계 유형 (NEW_RELATION용)"
    )
    note: str | None = Field(
        default=None, max_length=500, description="메모 (suggested_action으로 저장)"
    )


class ProposalUpdateRequest(BaseModel):
    """제안 수정 요청"""

    expected_version: int = Field(..., ge=1, description="예상 버전 (Optimistic Locking)")
    suggested_parent: str | None = Field(
        default=None, max_length=100, description="수정할 부모 개념"
    )
    suggested_canonical: str | None = Field(
        default=None, max_length=100, description="수정할 정규 형태"
    )
    category: str | None = Field(
        default=None, max_length=50, description="수정할 카테고리"
    )


class ProposalApproveRequest(BaseModel):
    """제안 승인 요청"""

    expected_version: int = Field(..., ge=1, description="예상 버전 (Optimistic Locking)")
    canonical: str | None = Field(
        default=None, max_length=100, description="승인 시 확정할 정규 형태"
    )
    parent: str | None = Field(
        default=None, max_length=100, description="승인 시 확정할 부모 개념"
    )
    note: str | None = Field(default=None, max_length=500, description="승인 메모")


class ProposalRejectRequest(BaseModel):
    """제안 거절 요청"""

    expected_version: int = Field(..., ge=1, description="예상 버전 (Optimistic Locking)")
    reason: str = Field(
        ..., min_length=1, max_length=500, description="거절 사유 (필수)"
    )


class BatchApproveRequest(BaseModel):
    """일괄 승인 요청"""

    proposal_ids: list[str] = Field(
        ..., min_length=1, max_length=100, description="승인할 제안 ID 목록"
    )
    note: str | None = Field(default=None, max_length=500, description="승인 메모")


class BatchRejectRequest(BaseModel):
    """일괄 거절 요청"""

    proposal_ids: list[str] = Field(
        ..., min_length=1, max_length=100, description="거절할 제안 ID 목록"
    )
    reason: str = Field(..., min_length=1, max_length=500, description="거절 사유 (필수)")


# ============================================
# Response Models
# ============================================


class ProposalResponse(BaseModel):
    """제안 응답 (목록용)"""

    id: str = Field(..., description="제안 ID (UUID)")
    version: int = Field(..., description="버전 번호")
    proposal_type: str = Field(..., description="제안 유형")
    term: str = Field(..., description="용어")
    category: str = Field(..., description="카테고리")
    suggested_action: str = Field(..., description="제안된 액션 설명")
    suggested_parent: str | None = Field(default=None, description="제안된 부모 개념")
    suggested_canonical: str | None = Field(default=None, description="제안된 정규 형태")
    suggested_relation_type: str | None = Field(
        default=None, description="제안된 관계 유형 (IS_A, SAME_AS, REQUIRES, PART_OF)"
    )
    frequency: int = Field(..., description="등장 빈도")
    confidence: float = Field(..., description="신뢰도 (0.0 ~ 1.0)")
    status: str = Field(..., description="현재 상태")
    source: str = Field(..., description="제안 출처 (chat, background, admin)")
    evidence_questions: list[str] = Field(
        default_factory=list, description="증거 질문 목록 (최근 5건)"
    )
    created_at: datetime = Field(..., description="생성 시각")
    reviewed_at: datetime | None = Field(default=None, description="검토 완료 시각")
    reviewed_by: str | None = Field(default=None, description="검토자 ID")
    applied_at: datetime | None = Field(default=None, description="온톨로지 적용 시각")


class ProposalDetailResponse(ProposalResponse):
    """제안 상세 응답"""

    all_evidence_questions: list[str] = Field(
        default_factory=list, description="전체 증거 질문 목록"
    )
    rejection_reason: str | None = Field(default=None, description="거절 사유")


class ProposalListResponse(BaseModel):
    """제안 목록 응답"""

    items: list[ProposalResponse] = Field(..., description="제안 목록")
    pagination: PaginationMeta = Field(..., description="페이지네이션 정보")


class BatchOperationResponse(BaseModel):
    """일괄 작업 응답"""

    success_count: int = Field(..., description="성공한 작업 수")
    failed_count: int = Field(..., description="실패한 작업 수")
    failed_ids: list[str] = Field(default_factory=list, description="실패한 제안 ID 목록")
    errors: list[dict[str, str]] = Field(
        default_factory=list, description="에러 상세 (id, message)"
    )


class UnresolvedTermStats(BaseModel):
    """미해결 용어 통계"""

    term: str = Field(..., description="용어")
    category: str = Field(..., description="카테고리")
    frequency: int = Field(..., description="등장 빈도")
    confidence: float = Field(..., description="신뢰도")


class OntologyStatsResponse(BaseModel):
    """온톨로지 통계 응답"""

    total_proposals: int = Field(..., description="전체 제안 수")
    pending_count: int = Field(..., description="대기 중인 제안 수")
    approved_count: int = Field(..., description="승인된 제안 수")
    auto_approved_count: int = Field(..., description="자동 승인된 제안 수")
    rejected_count: int = Field(..., description="거절된 제안 수")
    category_distribution: dict[str, int] = Field(
        default_factory=dict, description="카테고리별 분포"
    )
    top_unresolved_terms: list[UnresolvedTermStats] = Field(
        default_factory=list, description="빈도 높은 미해결 용어 TOP 10"
    )
