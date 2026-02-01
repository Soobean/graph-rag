"""
OntologyUpdateHandler 단위 테스트

사용자 주도 온톨로지 업데이트 처리 로직 테스트
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.adaptive.models import (
    OntologyProposal,
    ProposalStatus,
    ProposalType,
)
from src.graph.nodes.ontology_update_handler import OntologyUpdateHandlerNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.ontology_service import OntologyService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_llm():
    """Mock LLM Repository"""
    llm = MagicMock(spec=LLMRepository)
    llm.generate_json = AsyncMock(
        return_value={
            "action": "add_concept",
            "term": "LangGraph",
            "category": "Skill",
            "canonical": None,
            "relation_type": None,
            "target_term": None,
            "parent": "Framework",
            "confidence": 0.95,
            "reasoning": "LangGraph는 AI 프레임워크입니다",
        }
    )
    return llm


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j Repository"""
    neo4j = MagicMock(spec=Neo4jRepository)

    def create_saved_proposal(proposal: OntologyProposal) -> OntologyProposal:
        # ID와 기본값 설정
        return proposal

    neo4j.save_ontology_proposal = AsyncMock(side_effect=create_saved_proposal)
    return neo4j


@pytest.fixture
def mock_ontology_service():
    """Mock Ontology Service"""
    service = MagicMock(spec=OntologyService)

    async def mock_approve(
        proposal_id: str,
        expected_version: int,
        reviewer: str | None = None,
        canonical: str | None = None,
        parent: str | None = None,
        note: str | None = None,
    ) -> OntologyProposal:
        return OntologyProposal(
            id=proposal_id,
            proposal_type=ProposalType.NEW_CONCEPT,
            term="LangGraph",
            category="skills",
            suggested_action="test",
            status=ProposalStatus.APPROVED,
            applied_at=datetime.now(UTC),
        )

    service.approve_proposal = AsyncMock(side_effect=mock_approve)
    return service


@pytest.fixture
def handler(mock_llm, mock_neo4j, mock_ontology_service):
    """기본 OntologyUpdateHandler 인스턴스"""
    return OntologyUpdateHandlerNode(
        llm_repository=mock_llm,
        neo4j_repository=mock_neo4j,
        ontology_service=mock_ontology_service,
    )


@pytest.fixture
def sample_state() -> GraphRAGState:
    """샘플 파이프라인 상태"""
    return GraphRAGState(
        question="LangGraph를 스킬로 추가해줘",
        session_id="test-session",
        messages=[],
        execution_path=[],
    )


# =============================================================================
# 기본 동작 테스트
# =============================================================================


class TestOntologyUpdateHandlerBasic:
    """기본 동작 테스트"""

    @pytest.mark.asyncio
    async def test_process_add_concept_success(
        self, handler, mock_neo4j, mock_ontology_service, sample_state
    ):
        """새 개념 추가 요청 처리 성공"""
        result = await handler._process(sample_state)

        assert result["applied"] is True
        assert result["proposal_id"] is not None
        assert "LangGraph" in result["response"]
        assert "ontology_update_handler" in result["execution_path"]

        # Neo4j 저장 호출 확인
        mock_neo4j.save_ontology_proposal.assert_called_once()

        # OntologyService 승인 호출 확인
        mock_ontology_service.approve_proposal.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_returns_messages(self, handler, sample_state):
        """응답에 AIMessage가 포함됨"""
        result = await handler._process(sample_state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == result["response"]

    @pytest.mark.asyncio
    async def test_node_properties(self, handler):
        """노드 속성 확인"""
        assert handler.name == "ontology_update_handler"
        assert "question" in handler.input_keys


# =============================================================================
# 요청 파싱 테스트
# =============================================================================


class TestRequestParsing:
    """사용자 요청 파싱 테스트"""

    @pytest.mark.asyncio
    async def test_parse_add_synonym_request(
        self, handler, mock_llm, mock_neo4j, mock_ontology_service
    ):
        """동의어 추가 요청 파싱"""
        mock_llm.generate_json = AsyncMock(
            return_value={
                "action": "add_synonym",
                "term": "ReactJS",
                "category": "Skill",
                "canonical": "React",
                "relation_type": "SAME_AS",
                "target_term": "React",
                "parent": None,
                "confidence": 0.92,
                "reasoning": "ReactJS는 React의 다른 이름입니다",
            }
        )

        # 승인 결과에 applied_at 설정
        mock_ontology_service.approve_proposal = AsyncMock(
            return_value=OntologyProposal(
                proposal_type=ProposalType.NEW_SYNONYM,
                term="ReactJS",
                category="skills",
                suggested_action="test",
                suggested_canonical="React",
                status=ProposalStatus.APPROVED,
                applied_at=datetime.now(UTC),
            )
        )

        state = GraphRAGState(
            question="ReactJS와 React는 같은 거야",
            session_id="test",
            messages=[],
            execution_path=[],
        )

        result = await handler._process(state)

        assert result["applied"] is True
        assert "동의어" in result["response"]

    @pytest.mark.asyncio
    async def test_parse_add_relation_request(
        self, handler, mock_llm, mock_neo4j, mock_ontology_service
    ):
        """관계 추가 요청 파싱"""
        mock_llm.generate_json = AsyncMock(
            return_value={
                "action": "add_relation",
                "term": "FastAPI",
                "category": "Skill",
                "canonical": None,
                "relation_type": "REQUIRES",
                "target_term": "Python",
                "parent": None,
                "confidence": 0.95,  # >= 0.9 for auto-approve
                "reasoning": "FastAPI는 Python이 필요합니다",
            }
        )

        mock_ontology_service.approve_proposal = AsyncMock(
            return_value=OntologyProposal(
                proposal_type=ProposalType.NEW_RELATION,
                term="FastAPI",
                category="skills",
                suggested_action="test",
                suggested_parent="Python",
                suggested_relation_type="REQUIRES",
                status=ProposalStatus.APPROVED,
                applied_at=datetime.now(UTC),
            )
        )

        state = GraphRAGState(
            question="FastAPI는 Python이 필요해",
            session_id="test",
            messages=[],
            execution_path=[],
        )

        result = await handler._process(state)

        assert result["applied"] is True
        assert "REQUIRES" in result["response"]

    @pytest.mark.asyncio
    async def test_parse_failure_returns_help_message(
        self, handler, mock_llm
    ):
        """파싱 실패 시 도움말 메시지 반환"""
        mock_llm.generate_json = AsyncMock(return_value=None)

        state = GraphRAGState(
            question="이해할 수 없는 요청",
            session_id="test",
            messages=[],
            execution_path=[],
        )

        result = await handler._process(state)

        assert result["applied"] is False
        assert "예시" in result["response"]
        assert "parse_failed" in result["execution_path"][0]


# =============================================================================
# 신뢰도 검증 테스트
# =============================================================================


class TestConfidenceValidation:
    """신뢰도 검증 테스트"""

    @pytest.mark.asyncio
    async def test_low_confidence_returns_clarification(
        self, handler, mock_llm
    ):
        """낮은 신뢰도 시 명확화 요청"""
        mock_llm.generate_json = AsyncMock(
            return_value={
                "action": "add_concept",
                "term": "??",
                "category": "Skill",
                "confidence": 0.5,  # 낮은 신뢰도
                "reasoning": "요청이 불명확합니다",
            }
        )

        state = GraphRAGState(
            question="모호한 요청",
            session_id="test",
            messages=[],
            execution_path=[],
        )

        result = await handler._process(state)

        assert result["applied"] is False
        assert "불명확" in result["response"]
        assert "low_confidence" in result["execution_path"][0]


# =============================================================================
# 에러 처리 테스트
# =============================================================================


class TestErrorHandling:
    """에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_neo4j_save_error_handling(
        self, handler, mock_llm, mock_neo4j
    ):
        """Neo4j 저장 실패 시 에러 처리"""
        mock_neo4j.save_ontology_proposal = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        state = GraphRAGState(
            question="LangGraph를 스킬로 추가해줘",
            session_id="test",
            messages=[],
            execution_path=[],
        )

        result = await handler._process(state)

        assert result["applied"] is False
        assert result["error"] is not None
        assert "proposal_error" in result["execution_path"][0]

    @pytest.mark.asyncio
    async def test_approve_error_handling(
        self, handler, mock_neo4j, mock_ontology_service
    ):
        """승인 실패 시 에러 처리 (제안은 생성됨)"""
        mock_ontology_service.approve_proposal = AsyncMock(
            side_effect=Exception("Approval failed")
        )

        state = GraphRAGState(
            question="LangGraph를 스킬로 추가해줘",
            session_id="test",
            messages=[],
            execution_path=[],
        )

        result = await handler._process(state)

        assert result["applied"] is False
        assert result["proposal_id"] is not None  # 제안은 생성됨
        assert "실패" in result["response"]  # 적용 실패 안내
        assert "approve_error" in result["execution_path"][0]

    @pytest.mark.asyncio
    async def test_empty_question_handling(self, handler, mock_llm):
        """빈 question 처리"""
        mock_llm.generate_json = AsyncMock(return_value=None)

        state = GraphRAGState(
            question="",
            session_id="test",
            messages=[],
            execution_path=[],
        )

        result = await handler._process(state)

        assert result["applied"] is False
        assert "예시" in result["response"]

    @pytest.mark.asyncio
    async def test_llm_exception_handling(self, handler, mock_llm):
        """LLM 예외 발생 시 처리"""
        mock_llm.generate_json = AsyncMock(
            side_effect=Exception("LLM API timeout")
        )

        state = GraphRAGState(
            question="LangGraph를 스킬로 추가해줘",
            session_id="test",
            messages=[],
            execution_path=[],
        )

        result = await handler._process(state)

        assert result["applied"] is False
        assert "예시" in result["response"]  # 파싱 실패 시 도움말 표시
        assert "parse_failed" in result["execution_path"][0]


# =============================================================================
# 카테고리/관계 매핑 테스트
# =============================================================================


class TestCategoryMapping:
    """카테고리 매핑 테스트"""

    def test_category_mapping(self):
        """카테고리 정규화 확인 (모듈 레벨 상수)"""
        from src.graph.nodes.ontology_update_handler import CATEGORY_MAPPING

        assert CATEGORY_MAPPING["skill"] == "skills"
        assert CATEGORY_MAPPING["department"] == "departments"
        assert CATEGORY_MAPPING["person"] == "persons"
        assert CATEGORY_MAPPING["project"] == "projects"
        assert CATEGORY_MAPPING["certificate"] == "certificates"

    def test_relation_type_uses_upper(self, handler):
        """관계 타입은 .upper()로 정규화됨을 확인"""
        # RELATION_TYPE_MAPPING 제거됨 - LLM이 반환한 값을 .upper()로 처리
        parsed = {
            "action": "add_relation",
            "term": "FastAPI",
            "category": "skill",
            "relation_type": "requires",  # 소문자
            "target_term": "Python",
            "confidence": 0.9,
        }
        proposal = handler._create_proposal(parsed, "FastAPI는 Python 필요")
        assert proposal.suggested_relation_type == "REQUIRES"  # 대문자로 변환됨


# =============================================================================
# 응답 생성 테스트
# =============================================================================


class TestResponseGeneration:
    """응답 메시지 생성 테스트"""

    def test_generate_add_concept_response(self, handler):
        """새 개념 추가 응답 생성"""
        parsed = {"action": "add_concept"}
        proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="LangGraph",
            category="skills",
            suggested_action="test",
            suggested_parent="Framework",
        )

        response = handler._generate_response(parsed, proposal, applied=True)

        assert "LangGraph" in response
        assert "skills" in response
        assert "Framework" in response

    def test_generate_add_synonym_response(self, handler):
        """동의어 추가 응답 생성"""
        parsed = {"action": "add_synonym"}
        proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="ReactJS",
            category="skills",
            suggested_action="test",
            suggested_canonical="React",
        )

        response = handler._generate_response(parsed, proposal, applied=True)

        assert "ReactJS" in response
        assert "React" in response
        assert "동의어" in response

    def test_generate_pending_response(self, handler):
        """미승인 제안 응답 생성"""
        parsed = {"action": "add_concept"}
        proposal = OntologyProposal(
            id="test-id-123",
            proposal_type=ProposalType.NEW_CONCEPT,
            term="NewTech",
            category="skills",
            suggested_action="test",
        )

        response = handler._generate_response(parsed, proposal, applied=False)

        assert "NewTech" in response
        # ID는 메시지에서 제거됨 (단순화)
        assert "관리자" in response


# =============================================================================
# Proposal 생성 테스트
# =============================================================================


class TestProposalCreation:
    """Proposal 생성 로직 테스트"""

    def test_create_add_concept_proposal(self, handler):
        """add_concept Proposal 생성"""
        parsed = {
            "action": "add_concept",
            "term": "LangGraph",
            "category": "Skill",
            "parent": "Framework",
            "confidence": 0.9,
            "reasoning": "새 프레임워크",
        }

        proposal = handler._create_proposal(parsed, "테스트 질문")

        assert proposal.term == "LangGraph"
        assert proposal.category == "skills"  # 정규화됨
        assert proposal.proposal_type == ProposalType.NEW_CONCEPT
        assert proposal.suggested_parent == "Framework"
        assert proposal.confidence == 0.9

    def test_create_add_synonym_proposal(self, handler):
        """add_synonym Proposal 생성"""
        parsed = {
            "action": "add_synonym",
            "term": "ReactJS",
            "category": "Skill",
            "canonical": "React",
            "confidence": 0.85,
            "reasoning": "동의어",
        }

        proposal = handler._create_proposal(parsed, "테스트 질문")

        assert proposal.term == "ReactJS"
        assert proposal.proposal_type == ProposalType.NEW_SYNONYM
        assert proposal.suggested_canonical == "React"
        assert proposal.suggested_relation_type == "SAME_AS"

    def test_create_add_relation_proposal(self, handler):
        """add_relation Proposal 생성"""
        parsed = {
            "action": "add_relation",
            "term": "FastAPI",
            "category": "Skill",
            "relation_type": "REQUIRES",
            "target_term": "Python",
            "confidence": 0.88,
            "reasoning": "의존 관계",
        }

        proposal = handler._create_proposal(parsed, "테스트 질문")

        assert proposal.term == "FastAPI"
        assert proposal.proposal_type == ProposalType.NEW_RELATION
        assert proposal.suggested_parent == "Python"
        assert proposal.suggested_relation_type == "REQUIRES"

    def test_confidence_default_value(self, handler):
        """신뢰도 값이 없으면 기본값 0.8 사용"""
        parsed = {
            "action": "add_concept",
            "term": "Test",
            "category": "Skill",
            # confidence 없음
            "reasoning": "test",
        }

        proposal = handler._create_proposal(parsed, "테스트")
        assert proposal.confidence == 0.8  # 기본값
