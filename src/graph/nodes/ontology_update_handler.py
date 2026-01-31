"""
Ontology Update Handler - 사용자 주도 온톨로지 업데이트 처리

사용자가 채팅으로 직접 요청한 온톨로지 변경을 처리합니다.
기존 OntologyService를 재사용하여 제안 생성 및 즉시 적용.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage

from src.domain.adaptive.models import (
    OntologyProposal,
    ProposalStatus,
    ProposalType,
)
from src.domain.types import OntologyUpdateHandlerUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository, ModelTier
from src.utils.prompt_manager import PromptManager

if TYPE_CHECKING:
    from src.repositories.neo4j_repository import Neo4jRepository
    from src.services.ontology_service import OntologyService

logger = logging.getLogger(__name__)

# 카테고리 정규화 (단수 → 복수)
CATEGORY_MAPPING = {
    "skill": "skills",
    "person": "persons",
    "department": "departments",
    "project": "projects",
    "certificate": "certificates",
}


class OntologyUpdateHandlerNode(BaseNode[OntologyUpdateHandlerUpdate]):
    """사용자 주도 온톨로지 업데이트 처리 노드"""

    def __init__(
        self,
        llm_repository: LLMRepository,
        neo4j_repository: Neo4jRepository,
        ontology_service: OntologyService,
    ):
        super().__init__()
        self._llm = llm_repository
        self._neo4j = neo4j_repository
        self._ontology_service = ontology_service
        self._prompt_manager = PromptManager()

    @property
    def name(self) -> str:
        return "ontology_update_handler"

    @property
    def input_keys(self) -> list[str]:
        return ["question"]

    async def _process(self, state: GraphRAGState) -> OntologyUpdateHandlerUpdate:
        """사용자 온톨로지 업데이트 요청 처리"""
        question = state.get("question", "")
        self._logger.info(f"Processing ontology update request: {question[:50]}...")

        # 1. LLM으로 요청 파싱
        parsed = await self._parse_update_request(question)

        if not parsed:
            return self._error_response(
                "온톨로지 업데이트 요청을 이해하지 못했습니다. "
                "예시: 'LangGraph를 스킬로 추가해줘'",
                "parse_failed",
            )

        if parsed.get("confidence", 0.0) < 0.7:
            return self._error_response(
                f"요청이 불명확합니다. '{parsed.get('term', '?')}'에 대해 더 명확하게 설명해주세요.",
                "low_confidence",
            )

        # 2. OntologyProposal 생성
        try:
            proposal = self._create_proposal(parsed, question)
            saved = await self._neo4j.save_ontology_proposal(proposal)
        except Exception as e:
            self._logger.error(f"Failed to create proposal: {e}")
            return self._error_response(
                "온톨로지 제안 생성 중 오류가 발생했습니다.", "proposal_error", str(e)
            )

        # 3. 즉시 승인 및 적용
        try:
            approved = await self._ontology_service.approve_proposal(
                proposal_id=saved.id,
                expected_version=saved.version,
                reviewer="chat_user",
            )
            applied = approved.applied_at is not None
        except Exception as e:
            self._logger.error(f"Failed to approve proposal: {e}")
            msg = f"'{saved.term}' 제안이 생성되었지만 자동 적용에 실패했습니다."
            return OntologyUpdateHandlerUpdate(
                response=msg,
                proposal_id=saved.id,
                applied=False,
                error=str(e),
                execution_path=[f"{self.name}_approve_error"],
                messages=[AIMessage(content=msg)],
            )

        # 4. 응답 생성
        response = self._generate_response(parsed, approved, applied)
        self._logger.info(f"Ontology update completed: {parsed.get('action')} '{parsed.get('term')}'")

        return OntologyUpdateHandlerUpdate(
            response=response,
            proposal_id=approved.id,
            applied=applied,
            execution_path=[self.name],
            messages=[AIMessage(content=response)],
        )

    def _error_response(
        self, message: str, suffix: str, error: str | None = None
    ) -> OntologyUpdateHandlerUpdate:
        """에러 응답 생성 헬퍼"""
        return OntologyUpdateHandlerUpdate(
            response=message,
            applied=False,
            error=error,
            execution_path=[f"{self.name}_{suffix}"],
            messages=[AIMessage(content=message)],
        )

    async def _parse_update_request(self, question: str) -> dict[str, Any] | None:
        """LLM으로 사용자 요청 파싱"""
        try:
            prompt = self._prompt_manager.load_prompt("ontology_update_parser")
            result = await self._llm.generate_json(
                system_prompt=prompt["system"],
                user_prompt=prompt["user"].format(question=question),
                model_tier=ModelTier.LIGHT,
            )
            return result if result and result.get("action") else None
        except Exception as e:
            self._logger.error(f"Failed to parse update request: {e}")
            return None

    def _create_proposal(self, parsed: dict[str, Any], question: str) -> OntologyProposal:
        """파싱 결과로 OntologyProposal 생성"""
        action = parsed.get("action", "").lower()
        term = parsed.get("term", "").strip()
        raw_category = parsed.get("category", "Skill").lower()
        category = CATEGORY_MAPPING.get(raw_category, raw_category)

        # action에 따른 ProposalType 및 관련 필드 결정
        suggested_canonical: str | None = None
        suggested_parent: str | None = None
        suggested_relation_type: str | None = None

        if action == "add_synonym":
            proposal_type = ProposalType.NEW_SYNONYM
            suggested_canonical = parsed.get("canonical") or parsed.get("target_term")
            suggested_relation_type = "SAME_AS"
        elif action == "add_relation":
            proposal_type = ProposalType.NEW_RELATION
            suggested_relation_type = parsed.get("relation_type", "IS_A").upper()
            if suggested_relation_type == "SAME_AS":
                suggested_canonical = parsed.get("target_term")
            else:
                suggested_parent = parsed.get("target_term")
        else:  # add_concept
            proposal_type = ProposalType.NEW_CONCEPT
            suggested_parent = parsed.get("parent")
            if suggested_parent:
                suggested_relation_type = "IS_A"

        return OntologyProposal(
            proposal_type=proposal_type,
            term=term,
            category=category,
            suggested_action=parsed.get("reasoning", "User-driven update"),
            suggested_parent=suggested_parent,
            suggested_canonical=suggested_canonical,
            suggested_relation_type=suggested_relation_type,
            evidence_questions=[question],
            frequency=1,
            confidence=parsed.get("confidence", 0.8),
            status=ProposalStatus.PENDING,
        )

    def _generate_response(
        self, parsed: dict[str, Any], proposal: OntologyProposal, applied: bool
    ) -> str:
        """사용자 응답 메시지 생성"""
        action = parsed.get("action", "")
        term = proposal.term

        if not applied:
            return f"'{term}'에 대한 온톨로지 제안이 생성되었습니다. 관리자 승인 후 적용됩니다."

        if action == "add_synonym":
            canonical = proposal.suggested_canonical or "?"
            return f"'{term}'을(를) '{canonical}'의 동의어로 등록했습니다."

        if action == "add_relation":
            target = proposal.suggested_parent or proposal.suggested_canonical or "?"
            rel_type = proposal.suggested_relation_type or "관계"
            return f"'{term}'과(와) '{target}' 사이에 {rel_type} 관계를 추가했습니다."

        # add_concept
        if proposal.suggested_parent:
            return f"'{term}'을(를) {proposal.category}에 추가했습니다 (상위: {proposal.suggested_parent})."
        return f"'{term}'을(를) {proposal.category}에 추가했습니다."
