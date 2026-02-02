"""
CypherGenerator 모델 선택 테스트

단순 쿼리에 LIGHT 모델 사용, 복잡한 쿼리에 HEAVY 모델 사용 검증
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Settings
from src.graph.nodes.cypher_generator import CypherGeneratorNode, QueryComplexity
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository


@pytest.fixture
def mock_llm_repository() -> MagicMock:
    """LLM Repository 목"""
    mock = MagicMock(spec=LLMRepository)
    mock.generate_cypher = AsyncMock(
        return_value={"cypher": "MATCH (p:Employee) RETURN p", "parameters": {}}
    )
    return mock


@pytest.fixture
def mock_neo4j_repository() -> MagicMock:
    """Neo4j Repository 목"""
    mock = MagicMock(spec=Neo4jRepository)
    mock.get_schema = AsyncMock(
        return_value={
            "node_labels": ["Employee", "Skill"],
            "relationship_types": ["HAS_SKILL"],
        }
    )
    return mock


@pytest.fixture
def settings_enabled() -> Settings:
    """LIGHT 모델 활성화된 설정"""
    return Settings(cypher_light_model_enabled=True)


@pytest.fixture
def settings_disabled() -> Settings:
    """LIGHT 모델 비활성화된 설정"""
    return Settings(cypher_light_model_enabled=False)


class TestQueryComplexityAnalysis:
    """쿼리 복잡도 분석 테스트"""

    def test_simple_query_personnel_search(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """단순 personnel_search 쿼리는 SIMPLE로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람 찾아줘",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.SIMPLE

    def test_simple_query_certificate_search(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """단순 certificate_search 쿼리는 SIMPLE로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "정보처리기사 자격증 가진 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "certificate_search",
            "entities": {"certificates": ["정보처리기사"]},
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.SIMPLE

    def test_complex_query_multi_hop(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """multi-hop 쿼리는 COMPLEX로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람의 멘토",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
            "query_plan": {
                "is_multi_hop": True,
                "hop_count": 2,
                "hops": [],
            },
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.COMPLEX

    def test_complex_query_complex_intent(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """복잡한 intent (path_analysis)는 COMPLEX로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "홍길동과 김철수 사이의 관계",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "path_analysis",
            "entities": {"Employee": ["홍길동", "김철수"]},
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.COMPLEX

    def test_complex_query_too_many_entities(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """엔티티가 3개 이상이면 COMPLEX로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python, Java, Go 스킬 가진 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python", "Java", "Go"]},
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.COMPLEX


class TestCypherGeneratorModelSelection:
    """CypherGenerator 모델 선택 테스트"""

    @pytest.mark.asyncio
    async def test_simple_query_uses_light_model(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """단순 쿼리는 LIGHT 모델 사용 (use_light_model=True)"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
            "schema": {
                "node_labels": ["Employee"],
                "relationship_types": [],
            },
        }

        await node._process(state)

        # generate_cypher가 use_light_model=True로 호출되었는지 검증
        mock_llm_repository.generate_cypher.assert_called_once()
        call_kwargs = mock_llm_repository.generate_cypher.call_args.kwargs
        assert call_kwargs.get("use_light_model") is True

    @pytest.mark.asyncio
    async def test_complex_query_uses_heavy_model(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """복잡한 쿼리는 HEAVY 모델 사용 (use_light_model=False)"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람의 멘토",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "mentoring_network",
            "entities": {"skills": ["Python"]},
            "query_plan": {
                "is_multi_hop": True,
                "hop_count": 2,
            },
            "schema": {
                "node_labels": ["Employee"],
                "relationship_types": [],
            },
        }

        await node._process(state)

        # generate_cypher가 use_light_model=False로 호출되었는지 검증
        mock_llm_repository.generate_cypher.assert_called_once()
        call_kwargs = mock_llm_repository.generate_cypher.call_args.kwargs
        assert call_kwargs.get("use_light_model") is False

    @pytest.mark.asyncio
    async def test_config_disabled_uses_heavy_model(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_disabled: Settings,
    ) -> None:
        """설정 비활성화 시 항상 HEAVY 모델 사용"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_disabled,
        )

        # 단순 쿼리로 설정
        state: GraphRAGState = {
            "question": "Python 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
            "schema": {
                "node_labels": ["Employee"],
                "relationship_types": [],
            },
        }

        await node._process(state)

        # 설정이 비활성화되어 있으므로 use_light_model=False
        mock_llm_repository.generate_cypher.assert_called_once()
        call_kwargs = mock_llm_repository.generate_cypher.call_args.kwargs
        assert call_kwargs.get("use_light_model") is False

    @pytest.mark.asyncio
    async def test_no_settings_uses_heavy_model(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """Settings가 없으면 HEAVY 모델 사용"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=None,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
            "schema": {
                "node_labels": ["Employee"],
                "relationship_types": [],
            },
        }

        await node._process(state)

        # Settings가 없으므로 use_light_model=False
        mock_llm_repository.generate_cypher.assert_called_once()
        call_kwargs = mock_llm_repository.generate_cypher.call_args.kwargs
        assert call_kwargs.get("use_light_model") is False

    @pytest.mark.asyncio
    async def test_cache_hit_skips_model_selection(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """캐시 히트 시 LLM 호출 스킵"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "skip_generation": True,
            "cypher_query": "MATCH (p:Employee) RETURN p",
        }

        result = await node._process(state)

        # 캐시 히트 시 LLM 호출 없음
        mock_llm_repository.generate_cypher.assert_not_called()
        assert "cached" in result.get("execution_path", [])[0]
