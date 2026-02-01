"""
Ontology Admin API 테스트

Admin API 엔드포인트 통합 테스트
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.ontology_admin import router
from src.domain.adaptive.models import (
    OntologyProposal,
    ProposalSource,
    ProposalStatus,
    ProposalType,
)
from src.domain.exceptions import (
    ConflictError,
    InvalidStateError,
    ProposalNotFoundError,
)
from src.services.ontology_service import BatchResult, OntologyService


# =============================================================================
# Test App Setup
# =============================================================================


@pytest.fixture
def mock_ontology_service():
    """Mock OntologyService"""
    service = MagicMock(spec=OntologyService)
    service.get_proposal = AsyncMock()
    service.list_proposals = AsyncMock(return_value=([], 0))
    service.create_proposal = AsyncMock()
    service.update_proposal = AsyncMock()
    service.approve_proposal = AsyncMock()
    service.reject_proposal = AsyncMock()
    service.batch_approve = AsyncMock()
    service.batch_reject = AsyncMock()
    service.get_stats = AsyncMock(return_value={
        "total_proposals": 0,
        "pending_count": 0,
        "approved_count": 0,
        "auto_approved_count": 0,
        "rejected_count": 0,
        "category_distribution": {},
        "top_unresolved_terms": [],
    })
    return service


@pytest.fixture
def app(mock_ontology_service):
    """테스트용 FastAPI 앱"""
    app = FastAPI()
    app.include_router(router)

    # 의존성 오버라이드
    def get_mock_service():
        return mock_ontology_service

    from src.dependencies import get_ontology_service
    app.dependency_overrides[get_ontology_service] = get_mock_service

    return app


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return TestClient(app)


@pytest.fixture
def sample_proposal():
    """샘플 OntologyProposal"""
    return OntologyProposal(
        id="test-proposal-id",
        version=1,
        proposal_type=ProposalType.NEW_CONCEPT,
        term="LangGraph",
        category="skills",
        suggested_action="skills 카테고리에 새 개념으로 추가",
        suggested_parent="Programming",
        frequency=3,
        confidence=0.85,
        status=ProposalStatus.PENDING,
        source=ProposalSource.BACKGROUND,
        evidence_questions=["LangGraph를 사용하는 개발자는?", "LangGraph 경험자 찾기"],
        created_at=datetime.now(UTC),
    )


# =============================================================================
# GET /proposals 테스트
# =============================================================================


class TestListProposals:
    """목록 조회 API 테스트"""

    def test_list_proposals_empty(self, client, mock_ontology_service):
        """빈 목록 조회"""
        mock_ontology_service.list_proposals = AsyncMock(return_value=([], 0))

        response = client.get("/api/v1/ontology/admin/proposals")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["pagination"]["total"] == 0

    def test_list_proposals_with_items(
        self, client, mock_ontology_service, sample_proposal
    ):
        """항목이 있는 목록 조회"""
        mock_ontology_service.list_proposals = AsyncMock(
            return_value=([sample_proposal], 1)
        )

        response = client.get("/api/v1/ontology/admin/proposals")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["term"] == "LangGraph"
        assert data["pagination"]["total"] == 1

    def test_list_proposals_with_filters(self, client, mock_ontology_service):
        """필터를 적용한 목록 조회"""
        mock_ontology_service.list_proposals = AsyncMock(return_value=([], 0))

        response = client.get(
            "/api/v1/ontology/admin/proposals",
            params={
                "status": "pending",
                "proposal_type": "NEW_CONCEPT",
                "category": "skills",
                "term_search": "Lang",
                "sort_by": "frequency",
                "sort_order": "desc",
                "page": 2,
                "page_size": 20,
            },
        )

        assert response.status_code == 200
        mock_ontology_service.list_proposals.assert_called_once_with(
            status="pending",
            proposal_type="NEW_CONCEPT",
            source="all",
            category="skills",
            term_search="Lang",
            sort_by="frequency",
            sort_order="desc",
            page=2,
            page_size=20,
        )

    def test_list_proposals_pagination_metadata(
        self, client, mock_ontology_service, sample_proposal
    ):
        """페이지네이션 메타데이터 확인"""
        mock_ontology_service.list_proposals = AsyncMock(
            return_value=([sample_proposal], 100)
        )

        response = client.get(
            "/api/v1/ontology/admin/proposals",
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] == 100
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["page_size"] == 10
        assert data["pagination"]["total_pages"] == 10
        assert data["pagination"]["has_next"] is True
        assert data["pagination"]["has_prev"] is True


# =============================================================================
# GET /proposals/{id} 테스트
# =============================================================================


class TestGetProposal:
    """상세 조회 API 테스트"""

    def test_get_proposal_success(
        self, client, mock_ontology_service, sample_proposal
    ):
        """제안 상세 조회 성공"""
        mock_ontology_service.get_proposal = AsyncMock(return_value=sample_proposal)

        response = client.get("/api/v1/ontology/admin/proposals/test-proposal-id")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-proposal-id"
        assert data["term"] == "LangGraph"
        assert "all_evidence_questions" in data

    def test_get_proposal_not_found(self, client, mock_ontology_service):
        """존재하지 않는 제안 조회"""
        mock_ontology_service.get_proposal = AsyncMock(
            side_effect=ProposalNotFoundError("nonexistent-id")
        )

        response = client.get("/api/v1/ontology/admin/proposals/nonexistent-id")

        assert response.status_code == 404


# =============================================================================
# POST /proposals 테스트
# =============================================================================


class TestCreateProposal:
    """생성 API 테스트"""

    def test_create_proposal_success(
        self, client, mock_ontology_service, sample_proposal
    ):
        """제안 생성 성공"""
        mock_ontology_service.create_proposal = AsyncMock(return_value=sample_proposal)

        response = client.post(
            "/api/v1/ontology/admin/proposals",
            json={
                "term": "LangGraph",
                "category": "skills",
                "proposal_type": "NEW_CONCEPT",
                "suggested_parent": "Programming",
                "note": "수동으로 추가",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["term"] == "LangGraph"

    def test_create_proposal_validation_error(self, client, mock_ontology_service):
        """유효하지 않은 요청"""
        response = client.post(
            "/api/v1/ontology/admin/proposals",
            json={
                "term": "",  # 빈 문자열
                "category": "skills",
                "proposal_type": "NEW_CONCEPT",
            },
        )

        assert response.status_code == 422


# =============================================================================
# PATCH /proposals/{id} 테스트
# =============================================================================


class TestUpdateProposal:
    """수정 API 테스트"""

    def test_update_proposal_success(
        self, client, mock_ontology_service, sample_proposal
    ):
        """제안 수정 성공"""
        updated = sample_proposal
        updated.category = "frameworks"
        mock_ontology_service.update_proposal = AsyncMock(return_value=updated)

        response = client.patch(
            "/api/v1/ontology/admin/proposals/test-proposal-id",
            json={
                "expected_version": 1,
                "category": "frameworks",
            },
        )

        assert response.status_code == 200

    def test_update_proposal_version_conflict(self, client, mock_ontology_service):
        """버전 충돌"""
        mock_ontology_service.update_proposal = AsyncMock(
            side_effect=ConflictError(
                "Version mismatch",
                expected_version=1,
                current_version=2,
            )
        )

        response = client.patch(
            "/api/v1/ontology/admin/proposals/test-proposal-id",
            json={
                "expected_version": 1,
                "category": "frameworks",
            },
        )

        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["code"] == "VERSION_CONFLICT"


# =============================================================================
# POST /proposals/{id}/approve 테스트
# =============================================================================


class TestApproveProposal:
    """승인 API 테스트"""

    def test_approve_proposal_success(
        self, client, mock_ontology_service, sample_proposal
    ):
        """제안 승인 성공"""
        approved = sample_proposal
        approved.status = ProposalStatus.APPROVED
        mock_ontology_service.approve_proposal = AsyncMock(return_value=approved)

        response = client.post(
            "/api/v1/ontology/admin/proposals/test-proposal-id/approve",
            json={"expected_version": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"

    def test_approve_proposal_invalid_state(self, client, mock_ontology_service):
        """이미 처리된 제안 승인 시도"""
        mock_ontology_service.approve_proposal = AsyncMock(
            side_effect=InvalidStateError(
                "Cannot approve proposal with status 'approved'",
                current_state="approved",
            )
        )

        response = client.post(
            "/api/v1/ontology/admin/proposals/test-proposal-id/approve",
            json={"expected_version": 1},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["code"] == "INVALID_STATE"

    def test_approve_with_canonical(
        self, client, mock_ontology_service, sample_proposal
    ):
        """canonical 지정하여 승인"""
        mock_ontology_service.approve_proposal = AsyncMock(return_value=sample_proposal)

        response = client.post(
            "/api/v1/ontology/admin/proposals/test-proposal-id/approve",
            json={
                "expected_version": 1,
                "canonical": "Python",
                "parent": "Languages",
            },
        )

        assert response.status_code == 200
        mock_ontology_service.approve_proposal.assert_called_once()
        call_args = mock_ontology_service.approve_proposal.call_args
        assert call_args.kwargs["canonical"] == "Python"
        assert call_args.kwargs["parent"] == "Languages"


# =============================================================================
# POST /proposals/{id}/reject 테스트
# =============================================================================


class TestRejectProposal:
    """거절 API 테스트"""

    def test_reject_proposal_success(
        self, client, mock_ontology_service, sample_proposal
    ):
        """제안 거절 성공"""
        rejected = sample_proposal
        rejected.status = ProposalStatus.REJECTED
        mock_ontology_service.reject_proposal = AsyncMock(return_value=rejected)

        response = client.post(
            "/api/v1/ontology/admin/proposals/test-proposal-id/reject",
            json={
                "expected_version": 1,
                "reason": "온톨로지 범위에 맞지 않음",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

    def test_reject_proposal_without_reason(self, client, mock_ontology_service):
        """사유 없이 거절 시 422 에러"""
        response = client.post(
            "/api/v1/ontology/admin/proposals/test-proposal-id/reject",
            json={"expected_version": 1},  # reason 누락
        )

        assert response.status_code == 422


# =============================================================================
# POST /proposals/batch-approve 테스트
# =============================================================================


class TestBatchApprove:
    """일괄 승인 API 테스트"""

    def test_batch_approve_success(self, client, mock_ontology_service):
        """일괄 승인 성공"""
        mock_ontology_service.batch_approve = AsyncMock(
            return_value=BatchResult(
                success_count=3,
                failed_count=0,
                failed_ids=[],
                errors=[],
            )
        )

        response = client.post(
            "/api/v1/ontology/admin/proposals/batch-approve",
            json={
                "proposal_ids": ["id1", "id2", "id3"],
                "note": "일괄 승인",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success_count"] == 3
        assert data["failed_count"] == 0

    def test_batch_approve_partial_failure(self, client, mock_ontology_service):
        """일괄 승인 부분 실패"""
        mock_ontology_service.batch_approve = AsyncMock(
            return_value=BatchResult(
                success_count=2,
                failed_count=1,
                failed_ids=["id3"],
                errors=[{"id": "id3", "message": "Not in pending state"}],
            )
        )

        response = client.post(
            "/api/v1/ontology/admin/proposals/batch-approve",
            json={"proposal_ids": ["id1", "id2", "id3"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success_count"] == 2
        assert data["failed_count"] == 1
        assert "id3" in data["failed_ids"]


# =============================================================================
# POST /proposals/batch-reject 테스트
# =============================================================================


class TestBatchReject:
    """일괄 거절 API 테스트"""

    def test_batch_reject_success(self, client, mock_ontology_service):
        """일괄 거절 성공"""
        mock_ontology_service.batch_reject = AsyncMock(
            return_value=BatchResult(
                success_count=2,
                failed_count=0,
                failed_ids=[],
                errors=[],
            )
        )

        response = client.post(
            "/api/v1/ontology/admin/proposals/batch-reject",
            json={
                "proposal_ids": ["id1", "id2"],
                "reason": "스팸으로 판단됨",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success_count"] == 2

    def test_batch_reject_without_reason(self, client, mock_ontology_service):
        """사유 없이 일괄 거절 시 422 에러"""
        response = client.post(
            "/api/v1/ontology/admin/proposals/batch-reject",
            json={"proposal_ids": ["id1", "id2"]},  # reason 누락
        )

        assert response.status_code == 422


# =============================================================================
# GET /stats 테스트
# =============================================================================


class TestGetStats:
    """통계 API 테스트"""

    def test_get_stats_success(self, client, mock_ontology_service):
        """통계 조회 성공"""
        mock_ontology_service.get_stats = AsyncMock(
            return_value={
                "total_proposals": 100,
                "pending_count": 50,
                "approved_count": 30,
                "auto_approved_count": 10,
                "rejected_count": 10,
                "category_distribution": {"skills": 80, "departments": 20},
                "top_unresolved_terms": [
                    {
                        "term": "LangGraph",
                        "category": "skills",
                        "frequency": 15,
                        "confidence": 0.9,
                    },
                ],
            }
        )

        response = client.get("/api/v1/ontology/admin/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_proposals"] == 100
        assert data["pending_count"] == 50
        assert "skills" in data["category_distribution"]
        assert len(data["top_unresolved_terms"]) == 1
