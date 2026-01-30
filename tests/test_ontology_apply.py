"""
온톨로지 적용 테스트 (Phase 4)

승인된 OntologyProposal을 실제 Neo4j 온톨로지에 적용하는 로직을 테스트합니다.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.adaptive.models import (
    OntologyProposal,
    ProposalStatus,
    ProposalType,
)
from src.domain.exceptions import InvalidStateError, ValidationError
from src.services.ontology_service import OntologyService


@pytest.fixture
def mock_neo4j_repo():
    """Neo4j Repository 모킹"""
    repo = MagicMock()

    # 기본 async 메서드 모킹
    repo.concept_exists = AsyncMock(return_value=False)
    repo.create_or_get_concept = AsyncMock(return_value={"name": "test", "type": "skill"})
    repo.create_same_as_relation = AsyncMock(return_value=True)
    repo.create_is_a_relation = AsyncMock(return_value=True)
    repo.create_requires_relation = AsyncMock(return_value=True)
    repo.create_part_of_relation = AsyncMock(return_value=True)
    repo.update_proposal_applied_at = AsyncMock(return_value=True)
    repo.get_proposal_by_id = AsyncMock(return_value=None)
    repo.update_proposal_with_version = AsyncMock()

    return repo


@pytest.fixture
def service(mock_neo4j_repo):
    """OntologyService 인스턴스"""
    return OntologyService(mock_neo4j_repo)


def create_proposal(
    proposal_type: ProposalType,
    status: ProposalStatus = ProposalStatus.APPROVED,
    term: str = "TestTerm",
    category: str = "skills",
    suggested_parent: str | None = None,
    suggested_canonical: str | None = None,
    suggested_relation_type: str | None = None,
) -> OntologyProposal:
    """테스트용 OntologyProposal 생성"""
    return OntologyProposal(
        id=str(uuid4()),
        proposal_type=proposal_type,
        term=term,
        category=category,
        suggested_action=f"Test action for {term}",
        suggested_parent=suggested_parent,
        suggested_canonical=suggested_canonical,
        suggested_relation_type=suggested_relation_type,
        status=status,
        frequency=1,
        confidence=0.9,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ============================================
# TestApplyNewConcept
# ============================================


class TestApplyNewConcept:
    """NEW_CONCEPT 적용 테스트"""

    @pytest.mark.asyncio
    async def test_apply_new_concept_creates_node(self, service, mock_neo4j_repo):
        """NEW_CONCEPT: Concept 노드가 생성되어야 함"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="FastAPI",
            category="skills",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True
        mock_neo4j_repo.create_or_get_concept.assert_called_once_with(
            name="FastAPI",
            concept_type="skills",
            is_canonical=True,
            description=proposal.suggested_action,
            source=f"proposal:{proposal.id}",
        )

    @pytest.mark.asyncio
    async def test_apply_new_concept_with_parent(self, service, mock_neo4j_repo):
        """NEW_CONCEPT + 부모: IS_A 관계도 생성되어야 함"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="FastAPI",
            category="skills",
            suggested_parent="Web Framework",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True

        # Concept 노드 생성 (FastAPI + Web Framework)
        assert mock_neo4j_repo.create_or_get_concept.call_count == 2

        # IS_A 관계 생성
        mock_neo4j_repo.create_is_a_relation.assert_called_once_with(
            child_name="FastAPI",
            parent_name="Web Framework",
            proposal_id=proposal.id,
        )

    @pytest.mark.asyncio
    async def test_apply_new_concept_parent_exists(self, service, mock_neo4j_repo):
        """NEW_CONCEPT + 부모 존재: 부모 노드 생성 스킵"""
        mock_neo4j_repo.concept_exists = AsyncMock(return_value=True)

        proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="FastAPI",
            category="skills",
            suggested_parent="Web Framework",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True

        # Concept 노드 생성 (FastAPI만, 부모는 이미 존재)
        assert mock_neo4j_repo.create_or_get_concept.call_count == 1


# ============================================
# TestApplyNewSynonym
# ============================================


class TestApplyNewSynonym:
    """NEW_SYNONYM 적용 테스트"""

    @pytest.mark.asyncio
    async def test_apply_new_synonym_creates_same_as(self, service, mock_neo4j_repo):
        """NEW_SYNONYM: SAME_AS 관계가 생성되어야 함"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="파이선",
            category="skills",
            suggested_canonical="Python",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True

        # alias Concept 생성
        calls = mock_neo4j_repo.create_or_get_concept.call_args_list
        alias_call = [c for c in calls if c.kwargs.get("name") == "파이선"]
        assert len(alias_call) == 1
        assert alias_call[0].kwargs["is_canonical"] is False

        # SAME_AS 관계 생성
        mock_neo4j_repo.create_same_as_relation.assert_called_once_with(
            alias_name="파이선",
            canonical_name="Python",
            proposal_id=proposal.id,
        )

    @pytest.mark.asyncio
    async def test_apply_new_synonym_canonical_not_exists(self, service, mock_neo4j_repo):
        """NEW_SYNONYM + canonical 없음: canonical도 자동 생성"""
        mock_neo4j_repo.concept_exists = AsyncMock(return_value=False)

        proposal = create_proposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="파이선",
            category="skills",
            suggested_canonical="Python",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True
        # Python (canonical) + 파이선 (alias) 두 개 생성
        assert mock_neo4j_repo.create_or_get_concept.call_count == 2

    @pytest.mark.asyncio
    async def test_apply_new_synonym_fails_without_canonical(self, service, mock_neo4j_repo):
        """NEW_SYNONYM + canonical 없음: ValidationError"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="파이선",
            category="skills",
            suggested_canonical=None,  # canonical 없음
        )

        with pytest.raises(ValidationError) as exc_info:
            await service.apply_proposal_to_ontology(proposal)

        assert "suggested_canonical" in str(exc_info.value)


# ============================================
# TestApplyNewRelation
# ============================================


class TestApplyNewRelation:
    """NEW_RELATION 적용 테스트"""

    @pytest.mark.asyncio
    async def test_apply_is_a_relation(self, service, mock_neo4j_repo):
        """NEW_RELATION + IS_A: IS_A 관계 생성"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_RELATION,
            term="Django",
            category="skills",
            suggested_parent="Web Framework",
            suggested_relation_type="IS_A",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True
        mock_neo4j_repo.create_is_a_relation.assert_called_once_with(
            child_name="Django",
            parent_name="Web Framework",
            proposal_id=proposal.id,
        )

    @pytest.mark.asyncio
    async def test_apply_requires_relation(self, service, mock_neo4j_repo):
        """NEW_RELATION + REQUIRES: REQUIRES 관계 생성"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_RELATION,
            term="Senior Engineer",
            category="roles",
            suggested_parent="Python",
            suggested_relation_type="REQUIRES",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True
        mock_neo4j_repo.create_requires_relation.assert_called_once_with(
            entity_name="Senior Engineer",
            skill_name="Python",
            proposal_id=proposal.id,
        )

    @pytest.mark.asyncio
    async def test_apply_part_of_relation(self, service, mock_neo4j_repo):
        """NEW_RELATION + PART_OF: PART_OF 관계 생성"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_RELATION,
            term="Microservices",
            category="architecture",
            suggested_parent="Architecture Patterns",
            suggested_relation_type="PART_OF",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True
        mock_neo4j_repo.create_part_of_relation.assert_called_once_with(
            part_name="Microservices",
            whole_name="Architecture Patterns",
            proposal_id=proposal.id,
        )

    @pytest.mark.asyncio
    async def test_apply_same_as_relation(self, service, mock_neo4j_repo):
        """NEW_RELATION + SAME_AS: SAME_AS 관계 생성"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_RELATION,
            term="JS",
            category="skills",
            suggested_canonical="JavaScript",
            suggested_relation_type="SAME_AS",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True
        mock_neo4j_repo.create_same_as_relation.assert_called_once_with(
            alias_name="JS",
            canonical_name="JavaScript",
            proposal_id=proposal.id,
        )

    @pytest.mark.asyncio
    async def test_apply_relation_default_is_a(self, service, mock_neo4j_repo):
        """NEW_RELATION + relation_type 없음: 기본 IS_A 적용"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_RELATION,
            term="React",
            category="skills",
            suggested_parent="Frontend Framework",
            suggested_relation_type=None,  # 기본값
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True
        mock_neo4j_repo.create_is_a_relation.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_relation_fails_without_target(self, service, mock_neo4j_repo):
        """NEW_RELATION + target 없음: ValidationError"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_RELATION,
            term="Orphan",
            category="skills",
            suggested_parent=None,
            suggested_canonical=None,
        )

        with pytest.raises(ValidationError) as exc_info:
            await service.apply_proposal_to_ontology(proposal)

        assert "suggested_parent" in str(exc_info.value)


# ============================================
# TestApproveWithApply
# ============================================


class TestApproveWithApply:
    """approve_proposal() 통합 테스트"""

    @pytest.mark.asyncio
    async def test_approve_applies_to_ontology(self, service, mock_neo4j_repo):
        """승인 시 온톨로지 적용이 호출되어야 함"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            status=ProposalStatus.PENDING,
            term="GraphQL",
            category="skills",
        )

        # 승인 전 조회 모킹
        mock_neo4j_repo.get_proposal_by_id = AsyncMock(return_value=proposal)
        mock_neo4j_repo.update_proposal_with_version = AsyncMock(
            return_value=create_proposal(
                proposal_type=ProposalType.NEW_CONCEPT,
                status=ProposalStatus.APPROVED,
                term="GraphQL",
                category="skills",
            )
        )

        result = await service.approve_proposal(
            proposal_id=proposal.id,
            expected_version=proposal.version,
            reviewer="test_admin",
        )

        assert result.status == ProposalStatus.APPROVED

        # 온톨로지 적용 메서드 호출 확인
        mock_neo4j_repo.create_or_get_concept.assert_called()
        mock_neo4j_repo.update_proposal_applied_at.assert_called_once_with(proposal.id)

    @pytest.mark.asyncio
    async def test_approve_continues_even_if_apply_fails(self, service, mock_neo4j_repo):
        """온톨로지 적용 실패해도 승인 상태는 유지"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            status=ProposalStatus.PENDING,
            term="FailTerm",
            category="skills",
        )

        mock_neo4j_repo.get_proposal_by_id = AsyncMock(return_value=proposal)

        approved_proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            status=ProposalStatus.APPROVED,
            term="FailTerm",
            category="skills",
        )
        mock_neo4j_repo.update_proposal_with_version = AsyncMock(
            return_value=approved_proposal
        )

        # 온톨로지 적용 실패 시뮬레이션
        mock_neo4j_repo.create_or_get_concept = AsyncMock(
            side_effect=Exception("DB connection failed")
        )

        result = await service.approve_proposal(
            proposal_id=proposal.id,
            expected_version=proposal.version,
            reviewer="test_admin",
        )

        # 승인은 성공
        assert result.status == ProposalStatus.APPROVED
        # applied_at은 업데이트되지 않음
        mock_neo4j_repo.update_proposal_applied_at.assert_not_called()


# ============================================
# TestInvalidState
# ============================================


class TestInvalidState:
    """유효하지 않은 상태 테스트"""

    @pytest.mark.asyncio
    async def test_apply_fails_for_pending_status(self, service, mock_neo4j_repo):
        """PENDING 상태 제안은 적용 불가"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            status=ProposalStatus.PENDING,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.apply_proposal_to_ontology(proposal)

        assert "pending" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_apply_fails_for_rejected_status(self, service, mock_neo4j_repo):
        """REJECTED 상태 제안은 적용 불가"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            status=ProposalStatus.REJECTED,
        )

        with pytest.raises(InvalidStateError) as exc_info:
            await service.apply_proposal_to_ontology(proposal)

        assert "rejected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_apply_succeeds_for_auto_approved(self, service, mock_neo4j_repo):
        """AUTO_APPROVED 상태 제안은 적용 가능"""
        proposal = create_proposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            status=ProposalStatus.AUTO_APPROVED,
            term="AutoTerm",
        )

        result = await service.apply_proposal_to_ontology(proposal)

        assert result is True
        mock_neo4j_repo.create_or_get_concept.assert_called()
