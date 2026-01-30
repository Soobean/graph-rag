"""
OntologyService 단위 테스트

온톨로지 제안 관리 비즈니스 로직 테스트
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.adaptive.models import (
    OntologyProposal,
    ProposalStatus,
    ProposalType,
)
from src.domain.exceptions import (
    ConflictError,
    InvalidStateError,
    ProposalNotFoundError,
)
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.ontology_service import OntologyService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j Repository"""
    neo4j = MagicMock(spec=Neo4jRepository)
    neo4j.get_proposal_by_id = AsyncMock(return_value=None)
    neo4j.get_proposals_paginated = AsyncMock(return_value=([], 0))
    neo4j.get_ontology_stats = AsyncMock(return_value={
        "total_proposals": 0,
        "pending_count": 0,
        "approved_count": 0,
        "auto_approved_count": 0,
        "rejected_count": 0,
        "category_distribution": {},
        "top_unresolved_terms": [],
    })
    neo4j.create_proposal = AsyncMock()
    neo4j.update_proposal_with_version = AsyncMock(return_value=None)
    neo4j.get_proposal_current_version = AsyncMock(return_value=None)
    neo4j.batch_update_proposal_status = AsyncMock(return_value=(0, []))
    return neo4j


@pytest.fixture
def service(mock_neo4j):
    """OntologyService 인스턴스"""
    return OntologyService(neo4j_repository=mock_neo4j)


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
        evidence_questions=["LangGraph를 사용하는 개발자는?"],
    )


# =============================================================================
# 조회 테스트
# =============================================================================


class TestGetProposal:
    """get_proposal 테스트"""

    @pytest.mark.asyncio
    async def test_get_proposal_success(self, service, mock_neo4j, sample_proposal):
        """제안 조회 성공"""
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=sample_proposal)

        result = await service.get_proposal("test-proposal-id")

        assert result.id == "test-proposal-id"
        assert result.term == "LangGraph"
        mock_neo4j.get_proposal_by_id.assert_called_once_with("test-proposal-id")

    @pytest.mark.asyncio
    async def test_get_proposal_not_found(self, service, mock_neo4j):
        """존재하지 않는 제안 조회 시 예외"""
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=None)

        with pytest.raises(ProposalNotFoundError) as exc_info:
            await service.get_proposal("nonexistent-id")

        assert "nonexistent-id" in str(exc_info.value.message)


class TestListProposals:
    """list_proposals 테스트"""

    @pytest.mark.asyncio
    async def test_list_proposals_with_filters(self, service, mock_neo4j, sample_proposal):
        """필터와 함께 목록 조회"""
        mock_neo4j.get_proposals_paginated = AsyncMock(
            return_value=([sample_proposal], 1)
        )

        proposals, total = await service.list_proposals(
            status="pending",
            proposal_type="NEW_CONCEPT",
            category="skills",
            page=1,
            page_size=50,
        )

        assert len(proposals) == 1
        assert total == 1
        mock_neo4j.get_proposals_paginated.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_proposals_all_status(self, service, mock_neo4j):
        """'all' 상태는 None으로 변환됨"""
        mock_neo4j.get_proposals_paginated = AsyncMock(return_value=([], 0))

        await service.list_proposals(status="all", proposal_type="all")

        call_args = mock_neo4j.get_proposals_paginated.call_args
        assert call_args.kwargs["status"] is None
        assert call_args.kwargs["proposal_type"] is None


# =============================================================================
# 생성 테스트
# =============================================================================


class TestCreateProposal:
    """create_proposal 테스트"""

    @pytest.mark.asyncio
    async def test_create_proposal_success(self, service, mock_neo4j):
        """제안 생성 성공"""
        created_proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="NewFramework",
            category="skills",
            suggested_action="Manual proposal: NEW_CONCEPT for 'NewFramework'",
        )
        mock_neo4j.create_proposal = AsyncMock(return_value=created_proposal)

        result = await service.create_proposal(
            term="NewFramework",
            category="skills",
            proposal_type="NEW_CONCEPT",
            suggested_parent="Framework",
        )

        assert result.term == "NewFramework"
        mock_neo4j.create_proposal.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_proposal_with_note(self, service, mock_neo4j):
        """메모와 함께 제안 생성"""
        created_proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="파이선",
            category="skills",
            suggested_action="Python의 오타 수정용 동의어",
        )
        mock_neo4j.create_proposal = AsyncMock(return_value=created_proposal)

        await service.create_proposal(
            term="파이선",
            category="skills",
            proposal_type="NEW_SYNONYM",
            suggested_canonical="Python",
            note="Python의 오타 수정용 동의어",
        )

        call_args = mock_neo4j.create_proposal.call_args
        proposal_arg = call_args.args[0]
        assert "Python의 오타 수정용 동의어" in proposal_arg.suggested_action


# =============================================================================
# 수정 테스트
# =============================================================================


class TestUpdateProposal:
    """update_proposal 테스트"""

    @pytest.mark.asyncio
    async def test_update_proposal_success(self, service, mock_neo4j, sample_proposal):
        """제안 수정 성공"""
        mock_neo4j.get_proposal_current_version = AsyncMock(return_value=1)
        updated_proposal = OntologyProposal(
            id=sample_proposal.id,
            version=2,
            proposal_type=sample_proposal.proposal_type,
            term=sample_proposal.term,
            category="frameworks",  # 변경됨
            suggested_action=sample_proposal.suggested_action,
        )
        mock_neo4j.update_proposal_with_version = AsyncMock(return_value=updated_proposal)

        result = await service.update_proposal(
            proposal_id="test-proposal-id",
            expected_version=1,
            updates={"category": "frameworks"},
        )

        assert result.category == "frameworks"
        assert result.version == 2

    @pytest.mark.asyncio
    async def test_update_proposal_not_found(self, service, mock_neo4j):
        """존재하지 않는 제안 수정 시 예외"""
        mock_neo4j.get_proposal_current_version = AsyncMock(return_value=None)

        with pytest.raises(ProposalNotFoundError):
            await service.update_proposal(
                proposal_id="nonexistent-id",
                expected_version=1,
                updates={"category": "test"},
            )

    @pytest.mark.asyncio
    async def test_update_proposal_version_conflict(self, service, mock_neo4j):
        """버전 불일치 시 ConflictError"""
        mock_neo4j.get_proposal_current_version = AsyncMock(return_value=2)

        with pytest.raises(ConflictError) as exc_info:
            await service.update_proposal(
                proposal_id="test-id",
                expected_version=1,
                updates={"category": "test"},
            )

        assert exc_info.value.expected_version == 1
        assert exc_info.value.current_version == 2


# =============================================================================
# 승인 테스트
# =============================================================================


class TestApproveProposal:
    """approve_proposal 테스트"""

    @pytest.mark.asyncio
    async def test_approve_proposal_success(self, service, mock_neo4j, sample_proposal):
        """제안 승인 성공"""
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=sample_proposal)

        approved_proposal = OntologyProposal(
            id=sample_proposal.id,
            version=2,
            proposal_type=sample_proposal.proposal_type,
            term=sample_proposal.term,
            category=sample_proposal.category,
            suggested_action=sample_proposal.suggested_action,
            status=ProposalStatus.APPROVED,
        )
        mock_neo4j.update_proposal_with_version = AsyncMock(return_value=approved_proposal)

        result = await service.approve_proposal(
            proposal_id="test-proposal-id",
            expected_version=1,
            reviewer="admin@example.com",
        )

        assert result.status == ProposalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approve_already_approved_fails(self, service, mock_neo4j, sample_proposal):
        """이미 승인된 제안 재승인 시 InvalidStateError"""
        sample_proposal.status = ProposalStatus.APPROVED
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=sample_proposal)

        with pytest.raises(InvalidStateError) as exc_info:
            await service.approve_proposal(
                proposal_id="test-proposal-id",
                expected_version=1,
            )

        assert exc_info.value.current_state == "approved"

    @pytest.mark.asyncio
    async def test_approve_rejected_fails(self, service, mock_neo4j, sample_proposal):
        """거절된 제안 승인 시 InvalidStateError"""
        sample_proposal.status = ProposalStatus.REJECTED
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=sample_proposal)

        with pytest.raises(InvalidStateError):
            await service.approve_proposal(
                proposal_id="test-proposal-id",
                expected_version=1,
            )

    @pytest.mark.asyncio
    async def test_approve_with_canonical_and_parent(
        self, service, mock_neo4j, sample_proposal
    ):
        """canonical과 parent를 지정하여 승인"""
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=sample_proposal)

        approved_proposal = OntologyProposal(
            id=sample_proposal.id,
            version=2,
            proposal_type=sample_proposal.proposal_type,
            term=sample_proposal.term,
            category=sample_proposal.category,
            suggested_action=sample_proposal.suggested_action,
            suggested_canonical="Python",
            suggested_parent="Programming Languages",
            status=ProposalStatus.APPROVED,
        )
        mock_neo4j.update_proposal_with_version = AsyncMock(return_value=approved_proposal)

        await service.approve_proposal(
            proposal_id="test-proposal-id",
            expected_version=1,
            canonical="Python",
            parent="Programming Languages",
        )

        call_args = mock_neo4j.update_proposal_with_version.call_args
        updates = call_args.kwargs["updates"]
        assert updates["suggested_canonical"] == "Python"
        assert updates["suggested_parent"] == "Programming Languages"


# =============================================================================
# 거절 테스트
# =============================================================================


class TestRejectProposal:
    """reject_proposal 테스트"""

    @pytest.mark.asyncio
    async def test_reject_proposal_success(self, service, mock_neo4j, sample_proposal):
        """제안 거절 성공"""
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=sample_proposal)

        rejected_proposal = OntologyProposal(
            id=sample_proposal.id,
            version=2,
            proposal_type=sample_proposal.proposal_type,
            term=sample_proposal.term,
            category=sample_proposal.category,
            suggested_action=sample_proposal.suggested_action,
            status=ProposalStatus.REJECTED,
            rejection_reason="온톨로지 범위에 맞지 않음",
        )
        mock_neo4j.update_proposal_with_version = AsyncMock(return_value=rejected_proposal)

        result = await service.reject_proposal(
            proposal_id="test-proposal-id",
            expected_version=1,
            reviewer="admin@example.com",
            reason="온톨로지 범위에 맞지 않음",
        )

        assert result.status == ProposalStatus.REJECTED

    @pytest.mark.asyncio
    async def test_reject_already_rejected_fails(self, service, mock_neo4j, sample_proposal):
        """이미 거절된 제안 재거절 시 InvalidStateError"""
        sample_proposal.status = ProposalStatus.REJECTED
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=sample_proposal)

        with pytest.raises(InvalidStateError):
            await service.reject_proposal(
                proposal_id="test-proposal-id",
                expected_version=1,
                reason="test",
            )

    @pytest.mark.asyncio
    async def test_reject_with_reason(self, service, mock_neo4j, sample_proposal):
        """거절 사유가 저장됨"""
        mock_neo4j.get_proposal_by_id = AsyncMock(return_value=sample_proposal)
        mock_neo4j.update_proposal_with_version = AsyncMock(return_value=sample_proposal)

        await service.reject_proposal(
            proposal_id="test-proposal-id",
            expected_version=1,
            reason="이미 존재하는 개념입니다",
        )

        call_args = mock_neo4j.update_proposal_with_version.call_args
        updates = call_args.kwargs["updates"]
        assert updates["rejection_reason"] == "이미 존재하는 개념입니다"


# =============================================================================
# 일괄 작업 테스트
# =============================================================================


class TestBatchOperations:
    """일괄 승인/거절 테스트"""

    @pytest.mark.asyncio
    async def test_batch_approve_success(self, service, mock_neo4j):
        """일괄 승인 성공"""
        mock_neo4j.batch_update_proposal_status = AsyncMock(return_value=(3, []))

        result = await service.batch_approve(
            proposal_ids=["id1", "id2", "id3"],
            reviewer="admin@example.com",
        )

        assert result.success_count == 3
        assert result.failed_count == 0
        assert len(result.failed_ids) == 0

    @pytest.mark.asyncio
    async def test_batch_approve_partial_failure(self, service, mock_neo4j):
        """일괄 승인 부분 실패"""
        mock_neo4j.batch_update_proposal_status = AsyncMock(
            return_value=(2, ["id3"])
        )

        result = await service.batch_approve(
            proposal_ids=["id1", "id2", "id3"],
        )

        assert result.success_count == 2
        assert result.failed_count == 1
        assert "id3" in result.failed_ids

    @pytest.mark.asyncio
    async def test_batch_reject_with_reason(self, service, mock_neo4j):
        """일괄 거절 (사유 포함)"""
        mock_neo4j.batch_update_proposal_status = AsyncMock(return_value=(2, []))

        await service.batch_reject(
            proposal_ids=["id1", "id2"],
            reason="스팸으로 판단됨",
        )

        call_args = mock_neo4j.batch_update_proposal_status.call_args
        assert call_args.kwargs["rejection_reason"] == "스팸으로 판단됨"
        assert call_args.kwargs["new_status"] == "rejected"


# =============================================================================
# 통계 테스트
# =============================================================================


class TestGetStats:
    """get_stats 테스트"""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, service, mock_neo4j):
        """통계 조회 성공"""
        mock_neo4j.get_ontology_stats = AsyncMock(return_value={
            "total_proposals": 100,
            "pending_count": 50,
            "approved_count": 30,
            "auto_approved_count": 10,
            "rejected_count": 10,
            "category_distribution": {"skills": 80, "departments": 20},
            "top_unresolved_terms": [
                {"term": "LangGraph", "category": "skills", "frequency": 15, "confidence": 0.9},
            ],
        })

        result = await service.get_stats()

        assert result["total_proposals"] == 100
        assert result["pending_count"] == 50
        assert "skills" in result["category_distribution"]
