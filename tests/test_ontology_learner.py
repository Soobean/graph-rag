"""
OntologyLearner 단위 테스트

미해결 엔티티 분석 및 온톨로지 제안 생성 로직 테스트
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import AdaptiveOntologySettings
from src.domain.adaptive.models import (
    OntologyProposal,
    ProposalStatus,
    ProposalType,
)
from src.domain.types import UnresolvedEntity
from src.graph.nodes.ontology_learner import OntologyLearner
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def default_settings():
    """기본 Adaptive Ontology 설정 (활성화)"""
    return AdaptiveOntologySettings(
        enabled=True,
        auto_approve_enabled=True,
        auto_approve_confidence=0.95,
        auto_approve_min_frequency=5,
        auto_approve_types=["NEW_SYNONYM"],
        auto_approve_daily_limit=20,
        min_term_length=2,
        max_term_length=100,
    )


@pytest.fixture
def disabled_settings():
    """비활성화된 설정"""
    return AdaptiveOntologySettings(enabled=False)


@pytest.fixture
def mock_llm():
    """Mock LLM Repository"""
    llm = MagicMock(spec=LLMRepository)
    llm.generate_json = AsyncMock(return_value={
        "type": "NEW_CONCEPT",
        "action": "skills 카테고리에 새 개념으로 추가",
        "canonical": None,
        "parent": "Programming",
        "confidence": 0.85,
        "reasoning": "LangGraph는 새로운 프레임워크입니다",
    })
    return llm


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j Repository"""
    neo4j = MagicMock(spec=Neo4jRepository)
    neo4j.find_ontology_proposal = AsyncMock(return_value=None)
    neo4j.save_ontology_proposal = AsyncMock(side_effect=lambda p: p)
    neo4j.update_proposal_frequency = AsyncMock(return_value=True)
    neo4j.update_proposal_status = AsyncMock(return_value=True)
    neo4j.count_today_auto_approved = AsyncMock(return_value=0)
    neo4j.try_auto_approve_with_limit = AsyncMock(return_value=True)
    return neo4j


@pytest.fixture
def mock_ontology():
    """Mock Ontology Loader"""
    ontology = MagicMock()
    ontology.load_schema = MagicMock(return_value={
        "concepts": {
            "SkillCategory": [
                {
                    "name": "Programming",
                    "skills": ["Python", "Java", "Go"],
                    "subcategories": [
                        {"name": "Backend", "skills": ["Django", "FastAPI"]},
                    ],
                }
            ]
        }
    })
    ontology.load_synonyms = MagicMock(return_value={
        "skills": {
            "Python": {
                "canonical": "Python",
                "aliases": ["파이썬", "Python3"],
            }
        }
    })
    return ontology


@pytest.fixture
def learner(default_settings, mock_llm, mock_neo4j, mock_ontology):
    """기본 OntologyLearner 인스턴스"""
    return OntologyLearner(
        settings=default_settings,
        llm_repository=mock_llm,
        neo4j_repository=mock_neo4j,
        ontology_loader=mock_ontology,
    )


@pytest.fixture
def sample_unresolved():
    """샘플 미해결 엔티티"""
    return [
        UnresolvedEntity(
            term="LangGraph",
            category="skills",
            question="LangGraph를 사용하는 개발자는?",
            timestamp=datetime.now(UTC).isoformat(),
        ),
    ]


# =============================================================================
# 기본 동작 테스트
# =============================================================================


class TestOntologyLearnerBasic:
    """기본 동작 테스트"""

    @pytest.mark.asyncio
    async def test_process_unresolved_creates_proposal(
        self, learner, mock_neo4j, sample_unresolved
    ):
        """미해결 엔티티 처리 시 제안이 생성됨"""
        result = await learner.process_unresolved(sample_unresolved)

        assert len(result) == 1
        proposal = result[0]
        assert proposal.term == "LangGraph"
        assert proposal.category == "skills"
        assert proposal.proposal_type == ProposalType.NEW_CONCEPT

        # Neo4j 저장 호출 확인
        mock_neo4j.save_ontology_proposal.assert_called_once()

    @pytest.mark.asyncio
    async def test_disabled_when_settings_off(
        self, disabled_settings, mock_llm, mock_neo4j, sample_unresolved
    ):
        """비활성화 시 아무것도 처리하지 않음"""
        learner = OntologyLearner(
            settings=disabled_settings,
            llm_repository=mock_llm,
            neo4j_repository=mock_neo4j,
        )

        result = await learner.process_unresolved(sample_unresolved)

        assert result == []
        mock_llm.generate_json.assert_not_called()
        mock_neo4j.save_ontology_proposal.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_unresolved_returns_empty(self, learner):
        """빈 리스트 입력 시 빈 결과 반환"""
        result = await learner.process_unresolved([])
        assert result == []


# =============================================================================
# 용어 검증 테스트
# =============================================================================


class TestTermValidation:
    """용어 유효성 검증 테스트"""

    def test_validate_term_valid(self, learner):
        """유효한 용어 검증"""
        assert learner.validate_term("Python") is True
        assert learner.validate_term("FastAPI") is True
        assert learner.validate_term("한글용어") is True
        assert learner.validate_term("LangGraph 2.0") is True

    def test_validate_term_too_short(self, learner):
        """너무 짧은 용어 거부"""
        assert learner.validate_term("A") is False
        assert learner.validate_term("") is False
        assert learner.validate_term("  ") is False

    def test_validate_term_only_numbers(self, learner):
        """순수 숫자만 있는 경우 거부"""
        assert learner.validate_term("12345") is False
        assert learner.validate_term("2024") is False

    def test_validate_term_only_special_chars(self, learner):
        """특수문자만 있는 경우 거부"""
        assert learner.validate_term("@#$%") is False
        assert learner.validate_term("---") is False

    @pytest.mark.asyncio
    async def test_invalid_terms_filtered(
        self, learner, mock_llm, mock_neo4j
    ):
        """유효하지 않은 용어는 처리되지 않음"""
        invalid_unresolved = [
            UnresolvedEntity(
                term="",
                category="skills",
                question="test",
                timestamp=datetime.now(UTC).isoformat(),
            ),
            UnresolvedEntity(
                term="123",
                category="skills",
                question="test",
                timestamp=datetime.now(UTC).isoformat(),
            ),
        ]

        result = await learner.process_unresolved(invalid_unresolved)

        assert result == []
        mock_llm.generate_json.assert_not_called()


# =============================================================================
# 기존 제안 업데이트 테스트
# =============================================================================


class TestExistingProposalUpdate:
    """기존 제안 빈도 업데이트 테스트"""

    @pytest.mark.asyncio
    async def test_increments_frequency_for_existing(
        self, learner, mock_neo4j, sample_unresolved
    ):
        """기존 제안이 있으면 빈도 증가"""
        existing_proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="LangGraph",
            category="skills",
            suggested_action="새 개념 추가",
            frequency=3,
            confidence=0.8,
        )
        mock_neo4j.find_ontology_proposal = AsyncMock(return_value=existing_proposal)

        result = await learner.process_unresolved(sample_unresolved)

        assert len(result) == 1
        # 빈도 업데이트 호출 확인
        mock_neo4j.update_proposal_frequency.assert_called_once()
        # 새 제안 저장은 호출되지 않음
        mock_neo4j.save_ontology_proposal.assert_not_called()


# =============================================================================
# 자동 승인 테스트
# =============================================================================


class TestAutoApproval:
    """자동 승인 조건 테스트"""

    @pytest.mark.asyncio
    async def test_auto_approve_when_conditions_met(
        self, default_settings, mock_llm, mock_neo4j, mock_ontology
    ):
        """자동 승인 조건 충족 시 승인됨"""
        # NEW_SYNONYM 타입으로 LLM 응답 설정
        mock_llm.generate_json = AsyncMock(return_value={
            "type": "NEW_SYNONYM",
            "action": "Python의 동의어로 추가",
            "canonical": "Python",
            "parent": None,
            "confidence": 0.98,  # 높은 신뢰도
        })

        # 이미 4번 등장한 기존 제안 (frequency=4)
        existing_proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="파이선",
            category="skills",
            suggested_action="Python의 동의어로 추가",
            suggested_canonical="Python",
            frequency=4,  # 다음 호출로 5가 됨
            confidence=0.98,
        )
        mock_neo4j.find_ontology_proposal = AsyncMock(return_value=existing_proposal)

        learner = OntologyLearner(
            settings=default_settings,
            llm_repository=mock_llm,
            neo4j_repository=mock_neo4j,
            ontology_loader=mock_ontology,
        )

        unresolved = [
            UnresolvedEntity(
                term="파이선",
                category="skills",
                question="파이선 개발자 찾아줘",
                timestamp=datetime.now(UTC).isoformat(),
            ),
        ]

        await learner.process_unresolved(unresolved)

        # 원자적 자동 승인 호출 확인
        mock_neo4j.try_auto_approve_with_limit.assert_called()

    @pytest.mark.asyncio
    async def test_no_auto_approve_for_new_concept(
        self, default_settings, mock_llm, mock_neo4j, mock_ontology, sample_unresolved
    ):
        """NEW_CONCEPT은 자동 승인되지 않음 (allowed_types에 없음)"""
        # NEW_CONCEPT 타입으로 LLM 응답
        mock_llm.generate_json = AsyncMock(return_value={
            "type": "NEW_CONCEPT",
            "action": "새 개념 추가",
            "canonical": None,
            "parent": "Programming",
            "confidence": 0.99,  # 매우 높은 신뢰도
        })

        learner = OntologyLearner(
            settings=default_settings,
            llm_repository=mock_llm,
            neo4j_repository=mock_neo4j,
            ontology_loader=mock_ontology,
        )

        result = await learner.process_unresolved(sample_unresolved)

        assert len(result) == 1
        # NEW_CONCEPT이므로 자동 승인 상태 업데이트가 호출되지 않음
        # (저장은 호출되지만 status 업데이트는 안됨)
        assert result[0].status == ProposalStatus.PENDING

    @pytest.mark.asyncio
    async def test_daily_limit_prevents_auto_approve(
        self, default_settings, mock_llm, mock_neo4j, mock_ontology
    ):
        """일일 한도 초과 시 자동 승인 안됨 (원자적 처리)"""
        # 원자적 자동 승인이 한도 초과로 실패하도록 설정
        mock_neo4j.try_auto_approve_with_limit = AsyncMock(return_value=False)

        mock_llm.generate_json = AsyncMock(return_value={
            "type": "NEW_SYNONYM",
            "action": "동의어 추가",
            "canonical": "Python",
            "confidence": 0.99,
        })

        existing_proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="파이선",
            category="skills",
            suggested_action="동의어 추가",
            frequency=5,
            confidence=0.99,
        )
        mock_neo4j.find_ontology_proposal = AsyncMock(return_value=existing_proposal)

        learner = OntologyLearner(
            settings=default_settings,
            llm_repository=mock_llm,
            neo4j_repository=mock_neo4j,
            ontology_loader=mock_ontology,
        )

        unresolved = [
            UnresolvedEntity(
                term="파이선",
                category="skills",
                question="test",
                timestamp=datetime.now(UTC).isoformat(),
            ),
        ]

        result = await learner.process_unresolved(unresolved)

        # 원자적 자동 승인이 호출되었지만 실패
        mock_neo4j.try_auto_approve_with_limit.assert_called()
        # 제안은 생성되었지만 상태는 PENDING 유지
        assert result[0].status == ProposalStatus.PENDING


# =============================================================================
# LLM 분석 테스트
# =============================================================================


class TestLLMAnalysis:
    """LLM 분석 관련 테스트"""

    @pytest.mark.asyncio
    async def test_handles_llm_timeout(
        self, default_settings, mock_llm, mock_neo4j, sample_unresolved
    ):
        """LLM 타임아웃 시 graceful 처리"""
        import asyncio

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(10)  # 타임아웃보다 긴 응답
            return {}

        mock_llm.generate_json = slow_response

        # 짧은 타임아웃 설정 (최소 1초)
        settings = AdaptiveOntologySettings(
            enabled=True,
            analysis_timeout_seconds=1.0,
        )

        learner = OntologyLearner(
            settings=settings,
            llm_repository=mock_llm,
            neo4j_repository=mock_neo4j,
        )

        result = await learner.process_unresolved(sample_unresolved)

        # 타임아웃으로 빈 결과
        assert result == []

    @pytest.mark.asyncio
    async def test_handles_invalid_llm_response(
        self, default_settings, mock_llm, mock_neo4j, sample_unresolved
    ):
        """잘못된 LLM 응답 처리"""
        mock_llm.generate_json = AsyncMock(return_value={
            "type": "INVALID_TYPE",  # 잘못된 타입
            "action": "test",
        })

        learner = OntologyLearner(
            settings=default_settings,
            llm_repository=mock_llm,
            neo4j_repository=mock_neo4j,
        )

        result = await learner.process_unresolved(sample_unresolved)

        # 잘못된 응답으로 제안이 생성되지 않음
        assert result == []


# =============================================================================
# OntologyProposal 모델 테스트
# =============================================================================


class TestOntologyProposalModel:
    """OntologyProposal 모델 단위 테스트"""

    def test_add_evidence(self):
        """증거 추가 및 빈도 증가"""
        proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="test",
            category="skills",
            suggested_action="test action",
            frequency=1,
        )

        proposal.add_evidence("첫 번째 질문")
        assert proposal.frequency == 2
        assert "첫 번째 질문" in proposal.evidence_questions

        proposal.add_evidence("두 번째 질문")
        assert proposal.frequency == 3
        assert len(proposal.evidence_questions) == 2

        # 중복 질문은 추가되지 않지만 빈도는 증가
        proposal.add_evidence("첫 번째 질문")
        assert proposal.frequency == 4
        assert len(proposal.evidence_questions) == 2

    def test_approve_manual(self):
        """수동 승인"""
        proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="test",
            category="skills",
            suggested_action="test",
        )

        proposal.approve(reviewer="admin@example.com")

        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.reviewed_by == "admin@example.com"
        assert proposal.reviewed_at is not None

    def test_approve_auto(self):
        """자동 승인"""
        proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="test",
            category="skills",
            suggested_action="test",
        )

        proposal.approve(auto=True)

        assert proposal.status == ProposalStatus.AUTO_APPROVED
        assert proposal.reviewed_by == "system"

    def test_reject(self):
        """거부"""
        proposal = OntologyProposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="test",
            category="skills",
            suggested_action="test",
        )

        proposal.reject(reviewer="admin@example.com")

        assert proposal.status == ProposalStatus.REJECTED
        assert proposal.reviewed_by == "admin@example.com"

    def test_can_auto_approve_conditions(self):
        """자동 승인 조건 확인"""
        # 조건 충족
        proposal1 = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="test",
            category="skills",
            suggested_action="test",
            frequency=5,
            confidence=0.96,
        )
        assert proposal1.can_auto_approve() is True

        # 신뢰도 부족
        proposal2 = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="test",
            category="skills",
            suggested_action="test",
            frequency=5,
            confidence=0.90,
        )
        assert proposal2.can_auto_approve() is False

        # 빈도 부족
        proposal3 = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="test",
            category="skills",
            suggested_action="test",
            frequency=3,
            confidence=0.99,
        )
        assert proposal3.can_auto_approve() is False

        # 타입 불허
        proposal4 = OntologyProposal(
            proposal_type=ProposalType.NEW_CONCEPT,
            term="test",
            category="skills",
            suggested_action="test",
            frequency=5,
            confidence=0.99,
        )
        assert proposal4.can_auto_approve() is False

    def test_to_dict_and_from_dict(self):
        """딕셔너리 변환 테스트"""
        original = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="파이썬",
            category="skills",
            suggested_action="Python의 동의어로 추가",
            suggested_canonical="Python",
            evidence_questions=["파이썬 개발자 찾아줘"],
            frequency=3,
            confidence=0.95,
        )

        data = original.to_dict()
        restored = OntologyProposal.from_dict(data)

        assert restored.term == original.term
        assert restored.category == original.category
        assert restored.proposal_type == original.proposal_type
        assert restored.suggested_canonical == original.suggested_canonical
        assert restored.frequency == original.frequency
        assert restored.confidence == original.confidence


# =============================================================================
# 설정 검증 테스트
# =============================================================================


class TestAdaptiveOntologySettingsValidation:
    """AdaptiveOntologySettings 검증 테스트"""

    def test_valid_auto_approve_types(self):
        """유효한 auto_approve_types 설정"""
        settings = AdaptiveOntologySettings(
            auto_approve_types=["NEW_CONCEPT", "NEW_SYNONYM"]
        )
        assert settings.auto_approve_types == ["NEW_CONCEPT", "NEW_SYNONYM"]

    def test_invalid_auto_approve_types_raises(self):
        """잘못된 auto_approve_types는 에러 발생"""
        with pytest.raises(ValueError, match="Invalid proposal types"):
            AdaptiveOntologySettings(
                auto_approve_types=["INVALID_TYPE"]
            )

    def test_invalid_term_length_range_raises(self):
        """min_term_length > max_term_length이면 에러 발생"""
        with pytest.raises(ValueError, match="min_term_length.*cannot be greater"):
            AdaptiveOntologySettings(
                min_term_length=50,
                max_term_length=10,
            )

    def test_valid_term_length_range(self):
        """유효한 term length 범위"""
        settings = AdaptiveOntologySettings(
            min_term_length=2,
            max_term_length=100,
        )
        assert settings.min_term_length == 2
        assert settings.max_term_length == 100

    def test_confidence_range_validation(self):
        """confidence 범위 검증 (0.0 ~ 1.0)"""
        # 유효한 값
        settings = AdaptiveOntologySettings(auto_approve_confidence=0.85)
        assert settings.auto_approve_confidence == 0.85

        # 범위 초과 - Pydantic Field 검증
        with pytest.raises(ValueError):
            AdaptiveOntologySettings(auto_approve_confidence=1.5)

        with pytest.raises(ValueError):
            AdaptiveOntologySettings(auto_approve_confidence=-0.1)
