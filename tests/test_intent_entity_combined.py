"""
통합 Intent + Entity 추출 테스트

2개의 LLM 호출을 1개로 통합한 노드 검증
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.nodes.intent_entity_extractor import IntentEntityExtractorNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository


@pytest.fixture
def mock_llm_repository() -> MagicMock:
    """LLM Repository 목"""
    mock = MagicMock(spec=LLMRepository)
    mock.classify_intent_and_extract_entities = AsyncMock(
        return_value={
            "intent": "personnel_search",
            "confidence": 0.95,
            "entities": [
                {"type": "Skill", "value": "Python", "normalized": "Python"},
                {"type": "Person", "value": "홍길동", "normalized": "Hong Gildong"},
            ],
        }
    )
    return mock


class TestIntentEntityExtractorNode:
    """IntentEntityExtractorNode 테스트"""

    @pytest.mark.asyncio
    async def test_combined_returns_intent_and_entities(
        self, mock_llm_repository: MagicMock
    ) -> None:
        """통합 노드가 intent와 entities를 모두 반환"""
        node = IntentEntityExtractorNode(mock_llm_repository)

        state: GraphRAGState = {
            "question": "Python 잘하는 홍길동 찾아줘",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
        }

        result = await node._process(state)

        # Intent 검증
        assert result["intent"] == "personnel_search"
        assert result["intent_confidence"] == 0.95

        # Entities 검증 (dict[str, list[str]] 형태)
        entities = result["entities"]
        assert "Skill" in entities
        assert "Python" in entities["Skill"]
        assert "Person" in entities
        assert "Hong Gildong" in entities["Person"]

        # execution_path 검증
        assert "intent_entity_extractor" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_empty_entities_with_valid_intent(
        self, mock_llm_repository: MagicMock
    ) -> None:
        """엔티티가 없어도 유효한 intent 반환"""
        mock_llm_repository.classify_intent_and_extract_entities = AsyncMock(
            return_value={
                "intent": "org_analysis",
                "confidence": 0.85,
                "entities": [],
            }
        )

        node = IntentEntityExtractorNode(mock_llm_repository)

        state: GraphRAGState = {
            "question": "회사 조직 구조 알려줘",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
        }

        result = await node._process(state)

        assert result["intent"] == "org_analysis"
        assert result["intent_confidence"] == 0.85
        assert result["entities"] == {}

    @pytest.mark.asyncio
    async def test_invalid_intent_fallback_to_unknown(
        self, mock_llm_repository: MagicMock
    ) -> None:
        """유효하지 않은 intent는 unknown으로 fallback"""
        mock_llm_repository.classify_intent_and_extract_entities = AsyncMock(
            return_value={
                "intent": "invalid_intent_type",
                "confidence": 0.7,
                "entities": [],
            }
        )

        node = IntentEntityExtractorNode(mock_llm_repository)

        state: GraphRAGState = {
            "question": "뭔가 이상한 질문",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
        }

        result = await node._process(state)

        assert result["intent"] == "unknown"

    @pytest.mark.asyncio
    async def test_llm_error_returns_safe_default(
        self, mock_llm_repository: MagicMock
    ) -> None:
        """LLM 에러 시 안전한 기본값 반환"""
        mock_llm_repository.classify_intent_and_extract_entities = AsyncMock(
            side_effect=Exception("LLM API Error")
        )

        node = IntentEntityExtractorNode(mock_llm_repository)

        state: GraphRAGState = {
            "question": "테스트 질문",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
        }

        result = await node._process(state)

        # 에러 시에도 안전한 기본값
        assert result["intent"] == "unknown"
        assert result["intent_confidence"] == 0.0
        assert result["entities"] == {}
        assert result.get("error") is not None
        assert "error" in result["execution_path"][0]

    @pytest.mark.asyncio
    async def test_uses_normalized_value_for_entities(
        self, mock_llm_repository: MagicMock
    ) -> None:
        """normalized 값이 있으면 그것을 사용"""
        mock_llm_repository.classify_intent_and_extract_entities = AsyncMock(
            return_value={
                "intent": "personnel_search",
                "confidence": 0.9,
                "entities": [
                    {"type": "Skill", "value": "파이썬", "normalized": "Python"},
                ],
            }
        )

        node = IntentEntityExtractorNode(mock_llm_repository)

        state: GraphRAGState = {
            "question": "파이썬 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
        }

        result = await node._process(state)

        # normalized 값 사용
        assert "Python" in result["entities"]["Skill"]
        assert "파이썬" not in result["entities"]["Skill"]

    @pytest.mark.asyncio
    async def test_uses_value_when_no_normalized(
        self, mock_llm_repository: MagicMock
    ) -> None:
        """normalized가 없으면 value 사용"""
        mock_llm_repository.classify_intent_and_extract_entities = AsyncMock(
            return_value={
                "intent": "personnel_search",
                "confidence": 0.9,
                "entities": [
                    {"type": "Person", "value": "홍길동"},  # normalized 없음
                ],
            }
        )

        node = IntentEntityExtractorNode(mock_llm_repository)

        state: GraphRAGState = {
            "question": "홍길동 찾아줘",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
        }

        result = await node._process(state)

        # value 사용
        assert "홍길동" in result["entities"]["Person"]


class TestIntentEntityExtractorNodeConfig:
    """IntentEntityExtractorNode 설정 테스트"""

    def test_uses_same_intents_as_intent_classifier(
        self, mock_llm_repository: MagicMock
    ) -> None:
        """IntentClassifier와 동일한 intent 목록 사용"""
        from src.graph.nodes.intent_classifier import IntentClassifierNode

        node = IntentEntityExtractorNode(mock_llm_repository)

        assert node.AVAILABLE_INTENTS == IntentClassifierNode.AVAILABLE_INTENTS

    def test_uses_same_entity_types_as_entity_extractor(
        self, mock_llm_repository: MagicMock
    ) -> None:
        """EntityExtractor와 동일한 entity types 사용"""
        from src.graph.nodes.entity_extractor import EntityExtractorNode

        node = IntentEntityExtractorNode(mock_llm_repository)

        assert node.DEFAULT_ENTITY_TYPES == EntityExtractorNode.DEFAULT_ENTITY_TYPES

    def test_custom_entity_types(self, mock_llm_repository: MagicMock) -> None:
        """커스텀 entity types 사용 가능"""
        custom_types = ["CustomType1", "CustomType2"]
        node = IntentEntityExtractorNode(mock_llm_repository, entity_types=custom_types)

        assert node._entity_types == custom_types


class TestLLMRepositoryCombinedMethod:
    """LLMRepository.classify_intent_and_extract_entities 테스트"""

    @pytest.mark.asyncio
    async def test_calls_generate_json_with_light_model(self) -> None:
        """LIGHT 모델로 generate_json 호출"""
        from src.config import Settings
        from src.repositories.llm_repository import LLMRepository, ModelTier

        settings = Settings()
        repo = LLMRepository(settings)

        # generate_json 목킹
        repo.generate_json = AsyncMock(
            return_value={
                "intent": "personnel_search",
                "confidence": 0.9,
                "entities": [],
            }
        )

        await repo.classify_intent_and_extract_entities(
            question="테스트 질문",
            available_intents=["personnel_search"],
            entity_types=["Person"],
        )

        # LIGHT 모델 사용 확인
        repo.generate_json.assert_called_once()
        call_kwargs = repo.generate_json.call_args.kwargs
        assert call_kwargs["model_tier"] == ModelTier.LIGHT
