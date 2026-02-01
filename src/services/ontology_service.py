"""
OntologyService - 온톨로지 제안 관리 비즈니스 로직

Admin API의 비즈니스 로직을 담당합니다.
- 제안 CRUD
- 승인/거절 처리
- 일괄 작업
- 통계
- 온톨로지 적용 (Phase 4)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

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
    ValidationError,
)
from src.repositories.neo4j_repository import Neo4jRepository
from src.utils.ontology_utils import safe_refresh_ontology_cache

if TYPE_CHECKING:
    from src.domain.ontology.registry import OntologyRegistry

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """일괄 작업 결과"""

    success_count: int
    failed_count: int
    failed_ids: list[str]
    errors: list[dict[str, str]]


class OntologyService:
    """
    온톨로지 제안 관리 서비스

    Neo4jRepository를 통해 OntologyProposal을 관리하며,
    비즈니스 규칙(상태 전이, 버전 검증 등)을 적용합니다.
    """

    def __init__(
        self,
        neo4j_repository: Neo4jRepository,
        ontology_registry: OntologyRegistry | None = None,
    ):
        self._neo4j = neo4j_repository
        self._registry = ontology_registry

    # ============================================
    # 조회
    # ============================================

    async def get_proposal(self, proposal_id: str) -> OntologyProposal:
        """
        ID로 제안 조회

        Args:
            proposal_id: 제안 ID

        Returns:
            OntologyProposal

        Raises:
            ProposalNotFoundError: 제안을 찾을 수 없을 때
        """
        proposal = await self._neo4j.get_proposal_by_id(proposal_id)

        if proposal is None:
            raise ProposalNotFoundError(proposal_id)

        return proposal

    async def list_proposals(
        self,
        status: str | None = None,
        proposal_type: str | None = None,
        source: str | None = None,
        category: str | None = None,
        term_search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[OntologyProposal], int]:
        """
        제안 목록 조회 (필터링 + 페이지네이션)

        Args:
            status: 상태 필터 (pending, approved, rejected, auto_approved, all)
            proposal_type: 유형 필터 (NEW_CONCEPT, NEW_SYNONYM, NEW_RELATION, all)
            source: 출처 필터 (chat, background, admin, all)
            category: 카테고리 필터
            term_search: 용어 검색어
            sort_by: 정렬 필드
            sort_order: 정렬 방향
            page: 페이지 번호 (1부터 시작)
            page_size: 페이지 크기

        Returns:
            (제안 목록, 전체 개수) 튜플
        """
        # "all" 값은 None으로 변환
        if status == "all":
            status = None
        if proposal_type == "all":
            proposal_type = None
        if source == "all":
            source = None

        offset = (page - 1) * page_size

        return await self._neo4j.get_proposals_paginated(
            status=status,
            proposal_type=proposal_type,
            source=source,
            category=category,
            term_search=term_search,
            sort_by=sort_by,
            sort_order=sort_order,
            offset=offset,
            limit=page_size,
        )

    async def get_stats(self) -> dict[str, Any]:
        """
        온톨로지 통계 조회

        Returns:
            통계 딕셔너리
        """
        return await self._neo4j.get_ontology_stats()

    # ============================================
    # 생성/수정
    # ============================================

    async def create_proposal(
        self,
        term: str,
        category: str,
        proposal_type: str,
        suggested_parent: str | None = None,
        suggested_canonical: str | None = None,
        relation_type: str | None = None,
        note: str | None = None,
    ) -> OntologyProposal:
        """
        제안 수동 생성

        Args:
            term: 용어
            category: 카테고리
            proposal_type: 제안 유형
            suggested_parent: 부모 개념
            suggested_canonical: 정규 형태
            relation_type: 관계 유형 (IS_A, SAME_AS, REQUIRES, PART_OF)
            note: 메모 (suggested_action으로 저장)

        Returns:
            생성된 OntologyProposal
        """
        proposal = OntologyProposal(
            proposal_type=ProposalType(proposal_type),
            term=term,
            category=category,
            suggested_action=note or f"Manual proposal: {proposal_type} for '{term}'",
            suggested_parent=suggested_parent,
            suggested_canonical=suggested_canonical,
            suggested_relation_type=relation_type,
            frequency=1,
            confidence=1.0,  # 수동 생성은 높은 신뢰도
            status=ProposalStatus.PENDING,
            source=ProposalSource.ADMIN,  # Admin API에서 생성
        )

        return await self._neo4j.create_proposal(proposal)

    async def update_proposal(
        self,
        proposal_id: str,
        expected_version: int,
        updates: dict[str, Any],
    ) -> OntologyProposal:
        """
        제안 수정

        Args:
            proposal_id: 제안 ID
            expected_version: 예상 버전 (Optimistic Locking)
            updates: 업데이트할 필드

        Returns:
            업데이트된 OntologyProposal

        Raises:
            ProposalNotFoundError: 제안을 찾을 수 없을 때
            ConflictError: 버전 불일치 시
        """
        # 현재 버전 확인
        current_version = await self._neo4j.get_proposal_current_version(proposal_id)

        if current_version is None:
            raise ProposalNotFoundError(proposal_id)

        if current_version != expected_version:
            raise ConflictError(
                f"Version mismatch: expected {expected_version}, current {current_version}",
                expected_version=expected_version,
                current_version=current_version,
            )

        # 빈 값은 필터링
        filtered_updates = {k: v for k, v in updates.items() if v is not None}

        result = await self._neo4j.update_proposal_with_version(
            proposal_id=proposal_id,
            expected_version=expected_version,
            updates=filtered_updates,
        )

        if result is None:
            # 동시에 다른 요청이 업데이트했을 수 있음
            raise ConflictError(
                "Concurrent modification detected",
                expected_version=expected_version,
                current_version=None,
            )

        return result

    # ============================================
    # 승인/거절
    # ============================================

    async def approve_proposal(
        self,
        proposal_id: str,
        expected_version: int,
        reviewer: str | None = None,
        canonical: str | None = None,
        parent: str | None = None,
        note: str | None = None,
    ) -> OntologyProposal:
        """
        제안 승인

        Args:
            proposal_id: 제안 ID
            expected_version: 예상 버전
            reviewer: 검토자 ID
            canonical: 확정할 정규 형태
            parent: 확정할 부모 개념
            note: 승인 메모

        Returns:
            승인된 OntologyProposal

        Raises:
            ProposalNotFoundError: 제안을 찾을 수 없을 때
            InvalidStateError: pending 상태가 아닐 때
            ConflictError: 버전 불일치 시
        """
        proposal = await self.get_proposal(proposal_id)

        # 상태 검증
        if proposal.status != ProposalStatus.PENDING:
            raise InvalidStateError(
                f"Cannot approve proposal with status '{proposal.status.value}'",
                current_state=proposal.status.value,
            )

        # 버전 검증
        if proposal.version != expected_version:
            raise ConflictError(
                f"Version mismatch: expected {expected_version}, current {proposal.version}",
                expected_version=expected_version,
                current_version=proposal.version,
            )

        # 업데이트 준비
        updates: dict[str, Any] = {
            "status": ProposalStatus.APPROVED.value,
            "reviewed_at": datetime.now(UTC).isoformat(),
            "reviewed_by": reviewer or "admin",
        }

        if canonical:
            updates["suggested_canonical"] = canonical
        if parent:
            updates["suggested_parent"] = parent
        if note:
            current_action = proposal.suggested_action or ""
            updates["suggested_action"] = f"{current_action}\n[Approved] {note}".strip()

        result = await self._neo4j.update_proposal_with_version(
            proposal_id=proposal_id,
            expected_version=expected_version,
            updates=updates,
        )

        if result is None:
            raise ConflictError(
                "Concurrent modification detected",
                expected_version=expected_version,
                current_version=None,
            )

        logger.info(f"Proposal {proposal_id} approved by {reviewer or 'admin'}")

        # Phase 4: 승인 후 온톨로지 적용 시도
        try:
            applied = await self.apply_proposal_to_ontology(result)
            if applied:
                await self._neo4j.update_proposal_applied_at(proposal_id)
                # 응답에 applied_at 반영
                result.applied_at = datetime.now(UTC)
                logger.info(f"Proposal {proposal_id} applied to ontology successfully")

                # 런타임 캐시 새로고침 (즉시 쿼리 반영)
                await safe_refresh_ontology_cache(self._registry, "approve")
        except Exception as e:
            # 적용 실패해도 승인 상태는 유지
            logger.error(f"Failed to apply proposal {proposal_id} to ontology: {e}")

        return result

    async def reject_proposal(
        self,
        proposal_id: str,
        expected_version: int,
        reviewer: str | None = None,
        reason: str = "",
    ) -> OntologyProposal:
        """
        제안 거절

        Args:
            proposal_id: 제안 ID
            expected_version: 예상 버전
            reviewer: 검토자 ID
            reason: 거절 사유

        Returns:
            거절된 OntologyProposal

        Raises:
            ProposalNotFoundError: 제안을 찾을 수 없을 때
            InvalidStateError: pending 상태가 아닐 때
            ConflictError: 버전 불일치 시
        """
        proposal = await self.get_proposal(proposal_id)

        # 상태 검증
        if proposal.status != ProposalStatus.PENDING:
            raise InvalidStateError(
                f"Cannot reject proposal with status '{proposal.status.value}'",
                current_state=proposal.status.value,
            )

        # 버전 검증
        if proposal.version != expected_version:
            raise ConflictError(
                f"Version mismatch: expected {expected_version}, current {proposal.version}",
                expected_version=expected_version,
                current_version=proposal.version,
            )

        updates: dict[str, Any] = {
            "status": ProposalStatus.REJECTED.value,
            "reviewed_at": datetime.now(UTC).isoformat(),
            "reviewed_by": reviewer or "admin",
            "rejection_reason": reason,
        }

        result = await self._neo4j.update_proposal_with_version(
            proposal_id=proposal_id,
            expected_version=expected_version,
            updates=updates,
        )

        if result is None:
            raise ConflictError(
                "Concurrent modification detected",
                expected_version=expected_version,
                current_version=None,
            )

        logger.info(
            f"Proposal {proposal_id} rejected by {reviewer or 'admin'}: {reason}"
        )
        return result

    # ============================================
    # 일괄 작업
    # ============================================

    async def batch_approve(
        self,
        proposal_ids: list[str],
        reviewer: str | None = None,
        note: str | None = None,
    ) -> BatchResult:
        """
        일괄 승인

        Args:
            proposal_ids: 승인할 제안 ID 목록
            reviewer: 검토자 ID
            note: 승인 메모

        Returns:
            BatchResult
        """
        success_count, failed_ids = await self._neo4j.batch_update_proposal_status(
            proposal_ids=proposal_ids,
            new_status=ProposalStatus.APPROVED.value,
            reviewed_by=reviewer or "admin",
            rejection_reason=None,
        )

        errors = [
            {"id": pid, "message": "Not in pending state or not found"}
            for pid in failed_ids
        ]

        logger.info(f"Batch approve: {success_count} success, {len(failed_ids)} failed")

        # 배치 승인 후 캐시 새로고침 (1회만)
        if success_count > 0:
            await safe_refresh_ontology_cache(self._registry, "batch-approve")

        return BatchResult(
            success_count=success_count,
            failed_count=len(failed_ids),
            failed_ids=failed_ids,
            errors=errors,
        )

    async def batch_reject(
        self,
        proposal_ids: list[str],
        reviewer: str | None = None,
        reason: str = "",
    ) -> BatchResult:
        """
        일괄 거절

        Args:
            proposal_ids: 거절할 제안 ID 목록
            reviewer: 검토자 ID
            reason: 거절 사유

        Returns:
            BatchResult
        """
        success_count, failed_ids = await self._neo4j.batch_update_proposal_status(
            proposal_ids=proposal_ids,
            new_status=ProposalStatus.REJECTED.value,
            reviewed_by=reviewer or "admin",
            rejection_reason=reason,
        )

        errors = [
            {"id": pid, "message": "Not in pending state or not found"}
            for pid in failed_ids
        ]

        logger.info(f"Batch reject: {success_count} success, {len(failed_ids)} failed")

        return BatchResult(
            success_count=success_count,
            failed_count=len(failed_ids),
            failed_ids=failed_ids,
            errors=errors,
        )

    # ============================================
    # 온톨로지 적용 (Phase 4)
    # ============================================

    async def apply_proposal_to_ontology(
        self,
        proposal: OntologyProposal,
    ) -> bool:
        """
        승인된 제안을 실제 온톨로지에 적용

        제안 유형에 따라 적절한 적용 로직을 실행합니다:
        - NEW_CONCEPT: 새 Concept 노드 + IS_A 관계
        - NEW_SYNONYM: alias Concept 노드 + SAME_AS 관계
        - NEW_RELATION: 관계 유형에 따른 관계 생성

        Args:
            proposal: 적용할 OntologyProposal (APPROVED 또는 AUTO_APPROVED 상태)

        Returns:
            True if applied successfully, False otherwise

        Raises:
            InvalidStateError: 승인되지 않은 제안인 경우
            ValidationError: 필수 정보가 누락된 경우
        """
        if proposal.status not in [
            ProposalStatus.APPROVED,
            ProposalStatus.AUTO_APPROVED,
        ]:
            raise InvalidStateError(
                f"Only approved proposals can be applied (current: {proposal.status.value})",
                current_state=proposal.status.value,
            )

        match proposal.proposal_type:
            case ProposalType.NEW_CONCEPT:
                return await self._apply_new_concept(proposal)
            case ProposalType.NEW_SYNONYM:
                return await self._apply_new_synonym(proposal)
            case ProposalType.NEW_RELATION:
                return await self._apply_new_relation(proposal)
            case _:
                logger.warning(f"Unknown proposal type: {proposal.proposal_type}")
                return False

    async def _apply_new_concept(self, proposal: OntologyProposal) -> bool:
        """
        새 개념 추가 + 부모와 IS_A 관계 생성

        Args:
            proposal: NEW_CONCEPT 타입의 OntologyProposal

        Returns:
            성공 여부
        """
        # 1. Concept 노드 생성
        await self._neo4j.create_or_get_concept(
            name=proposal.term,
            concept_type=proposal.category,
            is_canonical=True,
            description=proposal.suggested_action,
            source=f"proposal:{proposal.id}",
        )

        # 2. 부모가 지정되어 있으면 IS_A 관계 생성
        if proposal.suggested_parent:
            # 부모 개념이 존재하는지 확인하고 없으면 생성
            parent_exists = await self._neo4j.concept_exists(proposal.suggested_parent)
            if not parent_exists:
                # 부모 개념도 자동 생성 (description 포함)
                await self._neo4j.create_or_get_concept(
                    name=proposal.suggested_parent,
                    concept_type=proposal.category,
                    is_canonical=True,
                    description=f"Auto-created parent for '{proposal.term}'",
                    source=f"auto_parent_of:{proposal.id}",
                )

            relation_created = await self._neo4j.create_is_a_relation(
                child_name=proposal.term,
                parent_name=proposal.suggested_parent,
                proposal_id=proposal.id,
            )
            if not relation_created:
                logger.warning(
                    "Failed to create IS_A relation: "
                    f"'{proposal.term}' -> '{proposal.suggested_parent}'"
                )
                return False

        logger.info(
            f"Applied NEW_CONCEPT: '{proposal.term}'"
            f"{' -> ' + proposal.suggested_parent if proposal.suggested_parent else ''}"
        )
        return True

    async def _apply_new_synonym(self, proposal: OntologyProposal) -> bool:
        """
        동의어 추가 + SAME_AS 관계 생성

        Args:
            proposal: NEW_SYNONYM 타입의 OntologyProposal

        Returns:
            성공 여부

        Raises:
            ValidationError: suggested_canonical이 없는 경우
        """
        if not proposal.suggested_canonical:
            raise ValidationError(
                "NEW_SYNONYM proposal requires suggested_canonical",
                field="suggested_canonical",
            )

        # 1. canonical 개념이 존재하는지 확인
        canonical_exists = await self._neo4j.concept_exists(
            proposal.suggested_canonical
        )
        if not canonical_exists:
            # canonical이 없으면 먼저 생성 (description 포함)
            await self._neo4j.create_or_get_concept(
                name=proposal.suggested_canonical,
                concept_type=proposal.category,
                is_canonical=True,
                description=f"Auto-created canonical for '{proposal.term}'",
                source=f"auto_canonical_for:{proposal.id}",
            )

        # 2. alias Concept 노드 생성 (is_canonical=False)
        await self._neo4j.create_or_get_concept(
            name=proposal.term,
            concept_type=proposal.category,
            is_canonical=False,
            description=f"Alias for {proposal.suggested_canonical}",
            source=f"proposal:{proposal.id}",
        )

        # 3. SAME_AS 관계 생성
        relation_created = await self._neo4j.create_same_as_relation(
            alias_name=proposal.term,
            canonical_name=proposal.suggested_canonical,
            proposal_id=proposal.id,
        )

        if not relation_created:
            logger.warning(
                "Failed to create SAME_AS relation: "
                f"'{proposal.term}' -> '{proposal.suggested_canonical}'"
            )
            return False

        logger.info(
            f"Applied NEW_SYNONYM: '{proposal.term}' -> '{proposal.suggested_canonical}'"
        )
        return True

    async def _apply_new_relation(self, proposal: OntologyProposal) -> bool:
        """
        관계 추가 (IS_A, REQUIRES, PART_OF)

        Args:
            proposal: NEW_RELATION 타입의 OntologyProposal

        Returns:
            성공 여부

        Raises:
            ValidationError: 관계 대상이 지정되지 않은 경우
        """
        relation_type = proposal.suggested_relation_type or "IS_A"

        # 관계의 source/target 결정
        # NEW_RELATION의 경우:
        # - suggested_parent가 있으면: term -> suggested_parent (IS_A, PART_OF)
        # - suggested_canonical이 있으면: term -> suggested_canonical (SAME_AS)
        target = proposal.suggested_parent or proposal.suggested_canonical

        if not target:
            raise ValidationError(
                "NEW_RELATION proposal requires suggested_parent or suggested_canonical",
                field="suggested_parent",
            )

        # 양쪽 노드가 존재하는지 확인하고 없으면 생성
        source_exists = await self._neo4j.concept_exists(proposal.term)
        if not source_exists:
            await self._neo4j.create_or_get_concept(
                name=proposal.term,
                concept_type=proposal.category,
                is_canonical=True,
                description=f"Auto-created for {relation_type} relation to '{target}'",
                source=f"auto_source_for:{proposal.id}",
            )

        target_exists = await self._neo4j.concept_exists(target)
        if not target_exists:
            await self._neo4j.create_or_get_concept(
                name=target,
                concept_type=proposal.category,
                is_canonical=True,
                description=f"Auto-created as {relation_type} target from '{proposal.term}'",
                source=f"auto_target_for:{proposal.id}",
            )

        # 관계 유형에 따라 생성
        match relation_type:
            case "IS_A":
                result = await self._neo4j.create_is_a_relation(
                    child_name=proposal.term,
                    parent_name=target,
                    proposal_id=proposal.id,
                )
            case "SAME_AS":
                result = await self._neo4j.create_same_as_relation(
                    alias_name=proposal.term,
                    canonical_name=target,
                    proposal_id=proposal.id,
                )
            case "REQUIRES":
                result = await self._neo4j.create_requires_relation(
                    entity_name=proposal.term,
                    skill_name=target,
                    proposal_id=proposal.id,
                )
            case "PART_OF":
                result = await self._neo4j.create_part_of_relation(
                    part_name=proposal.term,
                    whole_name=target,
                    proposal_id=proposal.id,
                )
            case _:
                logger.warning(f"Unknown relation type: {relation_type}")
                return False

        logger.info(
            f"Applied NEW_RELATION: '{proposal.term}' -[{relation_type}]-> '{target}'"
        )
        return result
