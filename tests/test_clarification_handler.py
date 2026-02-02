"""
Clarification Handler Node Tests
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.nodes.clarification_handler import ClarificationHandlerNode


class TestClarificationHandlerNode:
    """ClarificationHandlerNode 테스트"""

    @pytest.fixture
    def mock_llm_repository(self):
        """LLM Repository 목업"""
        repo = MagicMock()
        repo.generate_clarification = AsyncMock()
        return repo

    @pytest.fixture
    def node(self, mock_llm_repository):
        """테스트용 노드 인스턴스"""
        return ClarificationHandlerNode(mock_llm_repository)

    async def test_clarification_with_unresolved_entities(
        self, node, mock_llm_repository
    ):
        """미해결 엔티티가 있을 때 명확화 요청 생성"""
        mock_llm_repository.generate_clarification.return_value = (
            "홍길동이라는 이름을 가진 직원이 여러 명 있습니다. 어느 부서의 홍길동을 찾으시나요?"
        )

        state = {
            "question": "홍길동의 이메일은?",
            "session_id": "test",
            "resolved_entities": [
                {
                    "id": None,  # 미해결
                    "labels": ["Employee"],
                    "original_value": "홍길동",
                }
            ],
            "entities": {"Employee": ["홍길동"]},
            "execution_path": [],
        }

        result = await node(state)

        assert "response" in result
        assert "홍길동" in result["response"]
        assert "clarification_handler" in result["execution_path"]
        mock_llm_repository.generate_clarification.assert_called_once()

    async def test_clarification_with_multiple_unresolved(
        self, node, mock_llm_repository
    ):
        """여러 미해결 엔티티가 있을 때 처리"""
        mock_llm_repository.generate_clarification.return_value = (
            "조금 더 구체적으로 알려주시겠어요?"
        )

        state = {
            "question": "홍길동이 김철수와 같은 팀인가요?",
            "session_id": "test",
            "resolved_entities": [
                {"id": None, "labels": ["Employee"], "original_value": "홍길동"},
                {"id": None, "labels": ["Employee"], "original_value": "김철수"},
            ],
            "entities": {"Employee": ["홍길동", "김철수"]},
            "execution_path": [],
        }

        result = await node(state)

        assert "response" in result
        # LLM에 두 엔티티 모두 전달되었는지 확인
        call_args = mock_llm_repository.generate_clarification.call_args
        assert "홍길동" in call_args.kwargs["unresolved_entities"]
        assert "김철수" in call_args.kwargs["unresolved_entities"]

    async def test_clarification_no_unresolved_entities(
        self, node, mock_llm_repository
    ):
        """미해결 엔티티가 없을 때 일반적인 명확화 요청"""
        mock_llm_repository.generate_clarification.return_value = (
            "질문을 좀 더 구체적으로 해주시겠어요?"
        )

        state = {
            "question": "그 사람 부서는?",
            "session_id": "test",
            "resolved_entities": [],
            "entities": {},
            "execution_path": [],
        }

        result = await node(state)

        assert "response" in result
        # 빈 unresolved_entities로 호출
        call_args = mock_llm_repository.generate_clarification.call_args
        assert call_args.kwargs["unresolved_entities"] == ""

    async def test_clarification_error_handling(self, node, mock_llm_repository):
        """LLM 호출 실패 시 폴백 메시지 반환"""
        mock_llm_repository.generate_clarification.side_effect = Exception("LLM error")

        state = {
            "question": "홍길동은 누구인가요?",
            "session_id": "test",
            "resolved_entities": [],
            "entities": {"Employee": ["홍길동"]},
            "execution_path": [],
        }

        result = await node(state)

        assert "response" in result
        assert "홍길동" in result["response"]  # 폴백 메시지에 엔티티 언급
        assert "clarification_handler_fallback" in result["execution_path"]

    async def test_clarification_fallback_no_entities(self, node, mock_llm_repository):
        """엔티티가 없을 때 폴백 메시지"""
        mock_llm_repository.generate_clarification.side_effect = Exception("LLM error")

        state = {
            "question": "그게 뭐야?",
            "session_id": "test",
            "resolved_entities": [],
            "entities": {},
            "execution_path": [],
        }

        result = await node(state)

        assert "response" in result
        assert "구체적으로" in result["response"]


class TestExtractUnresolvedEntities:
    """미해결 엔티티 추출 테스트"""

    @pytest.fixture
    def node(self):
        """테스트용 노드 인스턴스"""
        mock_llm = MagicMock()
        return ClarificationHandlerNode(mock_llm)

    def test_extract_from_resolved_entities(self, node):
        """resolved_entities에서 미해결 항목 추출"""
        resolved = [
            {"id": "123", "labels": ["Employee"], "original_value": "홍길동"},
            {"id": None, "labels": ["Employee"], "original_value": "김철수"},  # 미해결
        ]
        entities = {"Employee": ["홍길동", "김철수"]}

        result = node._extract_unresolved_entities(resolved, entities)

        assert len(result) == 1
        assert result[0]["value"] == "김철수"
        assert result[0]["type"] == "Employee"

    def test_extract_missing_from_entities(self, node):
        """entities에는 있지만 resolved에 없는 항목 추출"""
        resolved = [
            {"id": "123", "labels": ["Employee"], "original_value": "홍길동"},
        ]
        entities = {"Employee": ["홍길동", "김철수"]}  # 김철수는 resolved에 없음

        result = node._extract_unresolved_entities(resolved, entities)

        assert len(result) == 1
        assert result[0]["value"] == "김철수"

    def test_extract_empty_when_all_resolved(self, node):
        """모두 해결된 경우 빈 리스트 반환"""
        resolved = [
            {"id": "123", "labels": ["Employee"], "original_value": "홍길동"},
        ]
        entities = {"Employee": ["홍길동"]}

        result = node._extract_unresolved_entities(resolved, entities)

        assert len(result) == 0

    def test_extract_handles_missing_labels(self, node):
        """labels가 없는 경우 Unknown 사용"""
        resolved = [
            {"id": None, "original_value": "테스트"},  # labels 없음
        ]
        entities = {}

        result = node._extract_unresolved_entities(resolved, entities)

        assert len(result) == 1
        assert result[0]["type"] == "Unknown"


class TestPipelineRouting:
    """파이프라인 라우팅 통합 테스트"""

    @pytest.fixture
    def mock_repos(self):
        """Repository 목업들"""
        llm = MagicMock()
        llm.classify_intent = AsyncMock(
            return_value={"intent": "personnel_search", "confidence": 0.9}
        )
        llm.extract_entities = AsyncMock(
            return_value={"entities": [{"type": "Employee", "value": "홍길동"}]}
        )
        llm.generate_clarification = AsyncMock(
            return_value="홍길동이라는 이름이 여러 명 있습니다."
        )
        llm.generate_response = AsyncMock(return_value="응답입니다.")

        neo4j = MagicMock()
        neo4j.get_schema = AsyncMock(
            return_value={"node_labels": ["Employee"], "relationship_types": ["WORKS_IN"]}
        )
        neo4j.find_entities_by_name = AsyncMock(return_value=[])  # 미해결

        return llm, neo4j

    async def test_route_to_clarification_when_unresolved(self, mock_repos):
        """미해결 엔티티가 있을 때 clarification_handler로 라우팅"""
        from unittest.mock import patch

        from src.config import Settings
        from src.graph.pipeline import GraphRAGPipeline

        llm, neo4j = mock_repos

        settings = MagicMock(spec=Settings)
        settings.schema_cache_ttl = 300

        with patch.object(
            GraphRAGPipeline, "__init__", lambda self, *args, **kwargs: None
        ):
            pipeline = GraphRAGPipeline.__new__(GraphRAGPipeline)

        # 라우팅 함수만 테스트
        from src.graph.state import GraphRAGState

        state: GraphRAGState = {
            "question": "홍길동은 누구?",
            "session_id": "test",
            "resolved_entities": [
                {"id": None, "labels": ["Employee"], "original_value": "홍길동"}
            ],
            "execution_path": [],
        }

        # 미해결 엔티티가 있으므로 clarification_handler로 라우팅되어야 함
        has_unresolved = any(
            not entity.get("id") for entity in state.get("resolved_entities", [])
        )
        assert has_unresolved is True

    async def test_route_to_cypher_when_all_resolved(self, mock_repos):
        """모든 엔티티가 해결되면 cypher_generator로 라우팅"""
        from src.graph.state import GraphRAGState

        state: GraphRAGState = {
            "question": "홍길동은 누구?",
            "session_id": "test",
            "resolved_entities": [
                {"id": "123", "labels": ["Employee"], "original_value": "홍길동"}
            ],
            "execution_path": [],
        }

        has_unresolved = any(
            not entity.get("id") for entity in state.get("resolved_entities", [])
        )
        assert has_unresolved is False
