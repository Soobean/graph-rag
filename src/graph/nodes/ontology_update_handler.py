"""
Ontology Update Handler - 사용자 주도 온톨로지 업데이트 처리

사용자가 채팅으로 직접 요청한 온톨로지 변경을 처리합니다.
- 스킬 추가: "LangGraph를 스킬로 추가해줘"
- 동의어 등록: "React와 ReactJS는 같은 거야"
- 관계 추가: "FastAPI는 Python이 필요해"

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
    from src.domain.ontology.registry import OntologyRegistry
    from src.repositories.neo4j_repository import Neo4jRepository
    from src.services.ontology_service import OntologyService

logger = logging.getLogger(__name__)


class OntologyUpdateHandlerNode(BaseNode[OntologyUpdateHandlerUpdate]):
    """
    사용자 주도 온톨로지 업데이트 처리 노드

    사용자가 채팅으로 요청한 온톨로지 변경을 처리하고 즉시 적용합니다.

    처리 흐름:
    1. LLM으로 사용자 요청 파싱 (action, term, category 등)
    2. OntologyProposal 생성
    3. 즉시 승인 및 적용 (OntologyService.approve_proposal 재사용)
    4. OntologyRegistry 캐시 갱신
    5. 응답 메시지 생성
    """

    # 카테고리 매핑 (사용자 입력 -> 내부 표현)
    CATEGORY_MAPPING: dict[str, str] = {
        "skill": "skills",
        "skills": "skills",
        "스킬": "skills",
        "기술": "skills",
        "person": "persons",
        "persons": "persons",
        "사람": "persons",
        "인물": "persons",
        "department": "departments",
        "departments": "departments",
        "부서": "departments",
        "project": "projects",
        "projects": "projects",
        "프로젝트": "projects",
        "certificate": "certificates",
        "certificates": "certificates",
        "자격증": "certificates",
    }

    # 관계 타입 매핑
    RELATION_TYPE_MAPPING: dict[str, str] = {
        "is_a": "IS_A",
        "isa": "IS_A",
        "하위": "IS_A",
        "상위": "IS_A",
        "same_as": "SAME_AS",
        "동의어": "SAME_AS",
        "같은": "SAME_AS",
        "requires": "REQUIRES",
        "필요": "REQUIRES",
        "의존": "REQUIRES",
        "part_of": "PART_OF",
        "partof": "PART_OF",
        "포함": "PART_OF",
        "일부": "PART_OF",
    }

    def __init__(
        self,
        llm_repository: LLMRepository,
        neo4j_repository: Neo4jRepository,
        ontology_service: OntologyService,
        ontology_registry: OntologyRegistry | None = None,
    ):
        """
        Args:
            llm_repository: LLM API 접근 레포지토리
            neo4j_repository: Neo4j 접근 레포지토리
            ontology_service: 온톨로지 서비스 (승인/적용 로직 재사용)
            ontology_registry: 온톨로지 레지스트리 (캐시 갱신용)
        """
        super().__init__()
        self._llm = llm_repository
        self._neo4j = neo4j_repository
        self._ontology_service = ontology_service
        self._registry = ontology_registry
        self._prompt_manager = PromptManager()

    @property
    def name(self) -> str:
        return "ontology_update_handler"

    @property
    def input_keys(self) -> list[str]:
        return ["question"]

    async def _process(self, state: GraphRAGState) -> OntologyUpdateHandlerUpdate:
        """
        사용자 온톨로지 업데이트 요청 처리

        Args:
            state: 현재 파이프라인 상태

        Returns:
            OntologyUpdateHandlerUpdate: 처리 결과
        """
        question = state.get("question", "")
        self._logger.info(f"Processing ontology update request: {question[:50]}...")

        # 1. LLM으로 요청 파싱
        parsed = await self._parse_update_request(question)

        if not parsed:
            response = (
                "온톨로지 업데이트 요청을 이해하지 못했습니다. "
                "예시:\n"
                "- 'LangGraph를 스킬로 추가해줘'\n"
                "- 'React와 ReactJS는 같은 거야'\n"
                "- 'FastAPI는 Python이 필요해'"
            )
            return OntologyUpdateHandlerUpdate(
                response=response,
                applied=False,
                execution_path=[f"{self.name}_parse_failed"],
                messages=[AIMessage(content=response)],
            )

        confidence = parsed.get("confidence", 0.0)
        if confidence < 0.7:
            response = (
                f"요청을 이해하기 어렵습니다 (신뢰도: {confidence:.0%}). "
                f"'{parsed.get('term', '?')}'에 대해 더 명확하게 설명해주세요.\n"
                f"판단 근거: {parsed.get('reasoning', '알 수 없음')}"
            )
            return OntologyUpdateHandlerUpdate(
                response=response,
                applied=False,
                execution_path=[f"{self.name}_low_confidence"],
                messages=[AIMessage(content=response)],
            )

        # 2. OntologyProposal 생성
        try:
            proposal = self._create_proposal(parsed, question)
            saved = await self._neo4j.save_ontology_proposal(proposal)
        except Exception as e:
            self._logger.error(f"Failed to create proposal: {e}")
            response = f"온톨로지 제안 생성 중 오류가 발생했습니다: {e}"
            return OntologyUpdateHandlerUpdate(
                response=response,
                applied=False,
                error=str(e),
                execution_path=[f"{self.name}_proposal_error"],
                messages=[AIMessage(content=response)],
            )

        # 3. 즉시 승인 및 적용 (Admin 권한 가정)
        try:
            approved = await self._ontology_service.approve_proposal(
                proposal_id=saved.id,
                expected_version=saved.version,
                reviewer="chat_user",
                note="User-driven ontology update via chat",
            )
            applied = approved.applied_at is not None
        except Exception as e:
            self._logger.error(f"Failed to approve proposal: {e}")
            # 승인 실패해도 제안은 생성됨 (pending 상태로 유지)
            response = (
                f"'{saved.term}' 온톨로지 제안이 생성되었습니다 (ID: {saved.id}). "
                f"하지만 자동 적용에 실패했습니다: {e}\n"
                "관리자가 수동으로 승인할 수 있습니다."
            )
            return OntologyUpdateHandlerUpdate(
                response=response,
                proposal_id=saved.id,
                applied=False,
                error=str(e),
                execution_path=[f"{self.name}_approve_error"],
                messages=[AIMessage(content=response)],
            )

        # 4. 응답 생성
        response = self._generate_response(parsed, approved, applied)

        self._logger.info(
            f"Ontology update completed: {parsed.get('action')} "
            f"'{parsed.get('term')}' (applied={applied})"
        )

        return OntologyUpdateHandlerUpdate(
            response=response,
            proposal_id=approved.id,
            applied=applied,
            execution_path=[self.name],
            messages=[AIMessage(content=response)],
        )

    async def _parse_update_request(self, question: str) -> dict[str, Any] | None:
        """
        LLM으로 사용자 요청 파싱

        Args:
            question: 사용자 질문

        Returns:
            파싱된 요청 정보 또는 None
        """
        try:
            prompt = self._prompt_manager.load_prompt("ontology_update_parser")

            system_prompt = prompt["system"]
            user_prompt = prompt["user"].format(question=question)

            result = await self._llm.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_tier=ModelTier.LIGHT,
            )

            if not result or not result.get("action"):
                return None

            return result

        except Exception as e:
            self._logger.error(f"Failed to parse update request: {e}")
            return None

    def _create_proposal(
        self,
        parsed: dict[str, Any],
        question: str,
    ) -> OntologyProposal:
        """
        파싱 결과로 OntologyProposal 생성

        Args:
            parsed: LLM 파싱 결과
            question: 원본 질문

        Returns:
            OntologyProposal 인스턴스
        """
        action = str(parsed.get("action", "")).lower()
        term = str(parsed.get("term", "")).strip()
        raw_category = str(parsed.get("category", "Skill"))
        confidence = min(1.0, max(0.0, float(parsed.get("confidence", 0.8))))

        # 카테고리 정규화
        category = self.CATEGORY_MAPPING.get(
            raw_category.lower(), raw_category.lower()
        )

        # action에 따른 ProposalType 결정
        suggested_canonical: str | None = None
        suggested_parent: str | None = None
        suggested_relation_type: str | None = None

        if action == "add_synonym":
            proposal_type = ProposalType.NEW_SYNONYM
            suggested_canonical = parsed.get("canonical") or parsed.get("target_term")
            suggested_relation_type = "SAME_AS"
        elif action == "add_relation":
            proposal_type = ProposalType.NEW_RELATION
            raw_relation = parsed.get("relation_type", "IS_A")
            suggested_relation_type = self.RELATION_TYPE_MAPPING.get(
                raw_relation.lower(), raw_relation.upper()
            )
            if suggested_relation_type == "SAME_AS":
                suggested_canonical = parsed.get("target_term")
            else:
                suggested_parent = parsed.get("target_term")
        else:  # add_concept (기본)
            proposal_type = ProposalType.NEW_CONCEPT
            suggested_parent = parsed.get("parent")
            if suggested_parent:
                suggested_relation_type = "IS_A"

        reasoning = parsed.get("reasoning", "User-driven ontology update")
        suggested_action = f"[Chat Request] {reasoning}"

        return OntologyProposal(
            proposal_type=proposal_type,
            term=term,
            category=category,
            suggested_action=suggested_action,
            suggested_parent=suggested_parent,
            suggested_canonical=suggested_canonical,
            suggested_relation_type=suggested_relation_type,
            evidence_questions=[question],
            frequency=1,
            confidence=confidence,
            status=ProposalStatus.PENDING,
        )

    def _generate_response(
        self,
        parsed: dict[str, Any],
        proposal: OntologyProposal,
        applied: bool,
    ) -> str:
        """
        사용자 응답 메시지 생성

        Args:
            parsed: LLM 파싱 결과
            proposal: 생성/승인된 제안
            applied: 온톨로지 적용 여부

        Returns:
            응답 메시지
        """
        action = parsed.get("action", "")
        term = proposal.term

        if applied:
            if action == "add_synonym":
                canonical = proposal.suggested_canonical or "?"
                return (
                    f"'{term}'을(를) '{canonical}'의 동의어로 등록했습니다. "
                    f"이제 '{term}'으로 검색해도 '{canonical}' 관련 결과가 나옵니다."
                )
            elif action == "add_relation":
                target = proposal.suggested_parent or proposal.suggested_canonical or "?"
                rel_type = proposal.suggested_relation_type or "관계"
                return (
                    f"'{term}'과(와) '{target}' 사이에 {rel_type} 관계를 추가했습니다."
                )
            else:  # add_concept
                if proposal.suggested_parent:
                    return (
                        f"'{term}'을(를) {proposal.category} 카테고리에 추가했습니다 "
                        f"(상위: {proposal.suggested_parent})."
                    )
                return f"'{term}'을(를) {proposal.category} 카테고리에 추가했습니다."
        else:
            return (
                f"'{term}'에 대한 온톨로지 제안이 생성되었습니다 (ID: {proposal.id}). "
                f"관리자 승인 후 적용됩니다."
            )
