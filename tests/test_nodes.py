from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.nodes.intent_classifier import IntentClassifierNode
from src.graph.nodes.entity_extractor import EntityExtractorNode
from src.graph.nodes.entity_resolver import EntityResolverNode
from src.graph.nodes.cypher_generator import CypherGeneratorNode
from src.graph.nodes.graph_executor import GraphExecutorNode
from src.graph.nodes.response_generator import ResponseGeneratorNode
from src.graph.state import GraphRAGState
from src.repositories.neo4j_repository import Neo4jRepository


class TestIntentClassifierNode:
    """IntentClassifierNode 테스트"""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM Repository"""
        llm = MagicMock()
        llm.classify_intent = AsyncMock()
        return llm

    @pytest.fixture
    def node(self, mock_llm):
        """IntentClassifierNode 인스턴스"""
        return IntentClassifierNode(mock_llm)

    @pytest.fixture
    def base_state(self) -> GraphRAGState:
        """기본 상태"""
        return GraphRAGState(
            question="홍길동이 근무하는 부서는?",
            session_id="test-session",
        )

    @pytest.mark.asyncio
    async def test_classify_personnel_search(self, node, mock_llm, base_state):
        """인력 검색 의도 분류"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.95,
        }

        result = await node(base_state)

        assert result["intent"] == "personnel_search"
        assert result["intent_confidence"] == 0.95
        assert "intent_classifier" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_classify_relationship_search(self, node, mock_llm, base_state):
        """관계 탐색 의도 분류"""
        mock_llm.classify_intent.return_value = {
            "intent": "relationship_search",
            "confidence": 0.85,
        }

        result = await node(base_state)

        assert result["intent"] == "relationship_search"

    @pytest.mark.asyncio
    async def test_classify_unknown_intent(self, node, mock_llm, base_state):
        """알 수 없는 의도 분류"""
        mock_llm.classify_intent.return_value = {
            "intent": "unknown",
            "confidence": 0.3,
        }

        result = await node(base_state)

        assert result["intent"] == "unknown"
        assert result["intent_confidence"] == 0.3

    @pytest.mark.asyncio
    async def test_classify_invalid_intent_fallback(self, node, mock_llm, base_state):
        """유효하지 않은 의도 → unknown 폴백"""
        mock_llm.classify_intent.return_value = {
            "intent": "invalid_intent_type",
            "confidence": 0.9,
        }

        result = await node(base_state)

        assert result["intent"] == "unknown"

    @pytest.mark.asyncio
    async def test_classify_error_handling(self, node, mock_llm, base_state):
        """에러 처리"""
        mock_llm.classify_intent.side_effect = Exception("LLM Error")

        result = await node(base_state)

        assert result["intent"] == "unknown"
        assert result["intent_confidence"] == 0.0
        assert "error" in result
        assert "intent_classifier_error" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_classify_missing_fields(self, node, mock_llm, base_state):
        """응답에 필드 누락 시 기본값"""
        mock_llm.classify_intent.return_value = {}

        result = await node(base_state)

        assert result["intent"] == "unknown"
        assert result["intent_confidence"] == 0.0


class TestEntityExtractorNode:
    """EntityExtractorNode 테스트"""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM Repository"""
        llm = MagicMock()
        llm.extract_entities = AsyncMock()
        return llm

    @pytest.fixture
    def node(self, mock_llm):
        """EntityExtractorNode 인스턴스"""
        return EntityExtractorNode(mock_llm)

    @pytest.fixture
    def base_state(self) -> GraphRAGState:
        """기본 상태"""
        return GraphRAGState(
            question="홍길동이 ABC 회사에서 Python 프로젝트를 진행중이야",
            session_id="test-session",
        )

    @pytest.mark.asyncio
    async def test_extract_single_entity(self, node, mock_llm, base_state):
        """단일 엔티티 추출"""
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Person", "value": "홍길동", "normalized": "홍길동"}]
        }

        result = await node(base_state)

        assert "entities" in result
        assert "Person" in result["entities"]
        assert "홍길동" in result["entities"]["Person"]
        assert "entity_extractor" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_extract_multiple_entities(self, node, mock_llm, base_state):
        """다중 엔티티 추출"""
        mock_llm.extract_entities.return_value = {
            "entities": [
                {"type": "Person", "value": "홍길동", "normalized": "홍길동"},
                {"type": "Organization", "value": "ABC 회사", "normalized": "ABC"},
                {"type": "Skill", "value": "Python", "normalized": "Python"},
            ]
        }

        result = await node(base_state)

        assert len(result["entities"]) == 3
        assert "Person" in result["entities"]
        assert "Organization" in result["entities"]
        assert "Skill" in result["entities"]

    @pytest.mark.asyncio
    async def test_extract_same_type_multiple(self, node, mock_llm, base_state):
        """같은 타입 다중 엔티티"""
        mock_llm.extract_entities.return_value = {
            "entities": [
                {"type": "Person", "value": "홍길동", "normalized": "홍길동"},
                {"type": "Person", "value": "김철수", "normalized": "김철수"},
            ]
        }

        result = await node(base_state)

        assert len(result["entities"]["Person"]) == 2
        assert "홍길동" in result["entities"]["Person"]
        assert "김철수" in result["entities"]["Person"]

    @pytest.mark.asyncio
    async def test_extract_no_entities(self, node, mock_llm, base_state):
        """엔티티 없음"""
        mock_llm.extract_entities.return_value = {"entities": []}

        result = await node(base_state)

        assert result["entities"] == {}

    @pytest.mark.asyncio
    async def test_extract_use_normalized_value(self, node, mock_llm, base_state):
        """normalized 값 우선 사용"""
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Person", "value": "홍 길동", "normalized": "홍길동"}]
        }

        result = await node(base_state)

        # normalized 값이 사용되어야 함
        assert "홍길동" in result["entities"]["Person"]

    @pytest.mark.asyncio
    async def test_extract_fallback_to_value(self, node, mock_llm, base_state):
        """normalized 없으면 value 사용"""
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Person", "value": "홍길동"}]
        }

        result = await node(base_state)

        assert "홍길동" in result["entities"]["Person"]

    @pytest.mark.asyncio
    async def test_extract_error_handling(self, node, mock_llm, base_state):
        """에러 처리"""
        mock_llm.extract_entities.side_effect = Exception("LLM Error")

        result = await node(base_state)

        assert result["entities"] == {}
        assert "error" in result
        assert "entity_extractor_error" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_custom_entity_types(self, mock_llm, base_state):
        """커스텀 엔티티 타입"""
        custom_types = ["CustomType1", "CustomType2"]
        node = EntityExtractorNode(mock_llm, entity_types=custom_types)

        mock_llm.extract_entities.return_value = {"entities": []}

        await node(base_state)

        # extract_entities가 커스텀 타입으로 호출되었는지 확인
        call_kwargs = mock_llm.extract_entities.call_args.kwargs
        assert call_kwargs["entity_types"] == custom_types

    def test_default_entity_types(self, mock_llm):
        """기본 엔티티 타입 확인"""
        node = EntityExtractorNode(mock_llm)

        assert "Person" in node._entity_types
        assert "Organization" in node._entity_types
        assert "Skill" in node._entity_types


class TestEntityResolverNode:
    """EntityResolverNode 테스트"""

    @pytest.fixture
    def mock_neo4j(self):
        """Mock Neo4j Repository"""
        neo4j = MagicMock(spec=Neo4jRepository)
        neo4j.find_entities_by_name = AsyncMock()
        return neo4j

    @pytest.fixture
    def node(self, mock_neo4j):
        """EntityResolverNode 인스턴스"""
        return EntityResolverNode(mock_neo4j)

    @pytest.mark.asyncio
    async def test_resolve_success(self, node, mock_neo4j):
        """엔티티 리졸브 성공"""
        mock_match = MagicMock()
        mock_match.id = 123
        mock_match.labels = ["Person"]
        mock_match.properties = {"name": "홍길동", "dept": "IT"}
        mock_neo4j.find_entities_by_name.return_value = [mock_match]

        state: GraphRAGState = {
            "entities": {"Person": ["홍길동"]},
            "execution_path": [],
        }

        result = await node(state)

        assert "resolved_entities" in result
        assert len(result["resolved_entities"]) == 1

        resolved = result["resolved_entities"][0]
        assert resolved["id"] == 123
        assert resolved["labels"] == ["Person"]
        assert resolved["name"] == "홍길동"
        assert resolved["original_value"] == "홍길동"
        assert resolved["match_score"] == 1.0
        assert resolved["properties"] == {"name": "홍길동", "dept": "IT"}

        assert "entity_resolver" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, node, mock_neo4j):
        """엔티티 못 찾음"""
        mock_neo4j.find_entities_by_name.return_value = []

        state: GraphRAGState = {
            "entities": {"Person": ["없는사람"]},
            "execution_path": [],
        }

        result = await node(state)

        # 찾지 못한 경우 리스트에 포함되지 않음
        assert "resolved_entities" in result
        assert len(result["resolved_entities"]) == 0
        assert "entity_resolver" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_resolve_skipped(self, node, mock_neo4j):
        """엔티티 없으면 스킵"""
        state = GraphRAGState(question="질문", entities={})
        result = await node(state)

        assert result["resolved_entities"] == []
        assert "entity_resolver_skipped" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_resolve_error(self, node, mock_neo4j):
        """리졸브 에러"""
        mock_neo4j.find_entities_by_name.side_effect = Exception("DB Error")

        state: GraphRAGState = {
            "entities": {"Person": ["에러유발"]},
            "execution_path": [],
        }

        result = await node(state)

        assert "resolved_entities" in result
        assert len(result["resolved_entities"]) == 0
        assert "entity_resolver" in result["execution_path"]


class TestCypherGeneratorNode:
    """CypherGeneratorNode 테스트"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.generate_cypher = AsyncMock()
        return llm

    @pytest.fixture
    def mock_neo4j(self):
        neo4j = MagicMock()
        neo4j.get_schema = AsyncMock(return_value={"node_labels": ["Person"]})
        return neo4j

    @pytest.fixture
    def node(self, mock_llm, mock_neo4j):
        return CypherGeneratorNode(mock_llm, mock_neo4j)

    @pytest.fixture
    def base_state(self) -> GraphRAGState:
        return GraphRAGState(
            question="홍길동 찾기",
            entities={"Person": ["홍길동"]},
        )

    @pytest.mark.asyncio
    async def test_generate_success(self, node, mock_llm, base_state):
        """Cypher 생성 성공"""
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }

        result = await node(base_state)

        assert result["cypher_query"] == "MATCH (n) RETURN n"
        assert "cypher_generator" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_generate_error(self, node, mock_llm, base_state):
        """Cypher 생성 실패"""
        mock_llm.generate_cypher.side_effect = Exception("LLM Fail")

        result = await node(base_state)

        assert result["cypher_query"] == ""
        assert "cypher_generator_error" in result["execution_path"]


class TestGraphExecutorNode:
    """GraphExecutorNode 테스트"""

    @pytest.fixture
    def mock_neo4j(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return neo4j

    @pytest.fixture
    def node(self, mock_neo4j):
        return GraphExecutorNode(mock_neo4j)

    @pytest.mark.asyncio
    async def test_execute_success(self, node, mock_neo4j):
        state = GraphRAGState(
            cypher_query="MATCH (n) RETURN n",
            cypher_parameters={},
        )
        mock_neo4j.execute_cypher.return_value = [{"n": "data"}]

        result = await node(state)

        assert len(result["graph_results"]) == 1
        assert result["result_count"] == 1
        assert "graph_executor" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_execute_no_query(self, node):
        state = GraphRAGState(cypher_query="")
        result = await node(state)
        assert result["result_count"] == 0
        assert "graph_executor_skipped" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_execute_error(self, node, mock_neo4j):
        state = GraphRAGState(cypher_query="BAD QUERY")
        mock_neo4j.execute_cypher.side_effect = Exception("DB Fail")

        result = await node(state)
        assert "error" in result
        assert "graph_executor_error" in result["execution_path"]


class TestResponseGeneratorNode:
    """ResponseGeneratorNode 테스트"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.generate_response = AsyncMock()
        return llm

    @pytest.fixture
    def node(self, mock_llm):
        return ResponseGeneratorNode(mock_llm)

    @pytest.mark.asyncio
    async def test_generate_response_success(self, node, mock_llm):
        state = GraphRAGState(
            question="q",
            graph_results=[{"name": "test"}],
        )
        mock_llm.generate_response.return_value = "This is a response."

        result = await node(state)
        assert result["response"] == "This is a response."
        assert "response_generator" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_generate_response_empty_results(self, node):
        state = GraphRAGState(question="q", graph_results=[])
        result = await node(state)
        assert "죄송합니다" in result["response"]
        assert "response_generator_empty" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_generate_response_error_in_state(self, node):
        state = GraphRAGState(question="q", error="Previous failure")
        result = await node(state)
        assert "오류가 발생" in result["response"]
        assert "response_generator_error_handler" in result["execution_path"]


class TestGraphRAGState:
    """GraphRAGState 테스트"""

    def test_minimal_state(self):
        """최소 상태 생성"""
        state = GraphRAGState(question="테스트 질문")
        assert state["question"] == "테스트 질문"

    def test_full_state(self):
        """전체 상태 생성"""
        state = GraphRAGState(
            question="홍길동 찾아줘",
            session_id="session-123",
            intent="personnel_search",
            intent_confidence=0.95,
            entities={"Person": ["홍길동"]},
            resolved_entities=[
                {
                    "id": 1,
                    "name": "홍길동",
                    "labels": ["Person"],
                    "properties": {},
                    "match_score": 1,
                    "original_value": "홍길동",
                }
            ],
            schema={"node_labels": ["Person"]},
            cypher_query="MATCH (p:Person) RETURN p",
            cypher_parameters={},
            graph_results=[{"name": "홍길동"}],
            result_count=1,
            response="홍길동을 찾았습니다.",
            error=None,
            execution_path=["intent_classifier", "entity_extractor"],
        )

        assert state["intent"] == "personnel_search"
        assert len(state["execution_path"]) == 2

    def test_execution_path_reducer(self):
        """execution_path Reducer 동작 확인"""
        # execution_path는 Annotated[list[str], operator.add] 타입이므로
        # LangGraph에서 자동으로 리스트 병합됨
        state = GraphRAGState(execution_path=["step1"])
        # 새로운 상태 업데이트 시 리스트가 합쳐짐 (LangGraph 동작)
        assert state["execution_path"] == ["step1"]
