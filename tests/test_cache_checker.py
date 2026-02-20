"""
CacheCheckerNode 단위 테스트

실행: pytest tests/test_cache_checker.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.nodes.cache_checker import CacheCheckerNode
from src.graph.state import GraphRAGState


class TestCacheCheckerNode:
    """CacheCheckerNode 테스트"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
        return llm

    @pytest.fixture
    def mock_cache(self):
        cache = MagicMock()
        cache.find_similar_query = AsyncMock(return_value=None)
        return cache

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.vector_search_enabled = True
        return settings

    @pytest.fixture
    def node(self, mock_llm, mock_cache, mock_settings):
        return CacheCheckerNode(mock_llm, mock_cache, mock_settings)

    @pytest.fixture
    def base_state(self) -> GraphRAGState:
        return GraphRAGState(question="Python 잘하는 사람은?")

    async def test_cache_hit(self, node, mock_llm, mock_cache, base_state):
        """캐시 히트 시 캐싱된 Cypher 반환 + skip_generation=True"""
        cached = MagicMock()
        cached.score = 0.95
        cached.question = "Python 잘하는 사람 찾아줘"
        cached.cypher_query = "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill) RETURN e"
        cached.cypher_parameters = {"skill": "Python"}
        mock_cache.find_similar_query.return_value = cached

        result = await node(base_state)

        assert result["cache_hit"] is True
        assert result["skip_generation"] is True
        assert result["cache_score"] == 0.95
        assert result["cypher_query"] == cached.cypher_query
        assert result["cypher_parameters"] == cached.cypher_parameters
        assert result["question_embedding"] == [0.1, 0.2, 0.3]
        assert "cache_checker_hit" in result["execution_path"]

    async def test_cache_miss(self, node, mock_cache, base_state):
        """캐시 미스 시 임베딩만 반환, skip_generation=False"""
        mock_cache.find_similar_query.return_value = None

        result = await node(base_state)

        assert result["cache_hit"] is False
        assert result["skip_generation"] is False
        assert result["cache_score"] == 0.0
        assert result["question_embedding"] == [0.1, 0.2, 0.3]
        assert "cache_checker_miss" in result["execution_path"]

    async def test_vector_search_disabled(self, mock_llm, mock_cache, base_state):
        """Vector Search 비활성화 시 스킵"""
        settings = MagicMock()
        settings.vector_search_enabled = False
        node = CacheCheckerNode(mock_llm, mock_cache, settings)

        result = await node(base_state)

        assert result["cache_hit"] is False
        assert result["skip_generation"] is False
        assert result["question_embedding"] is None
        assert "cache_checker_skipped" in result["execution_path"]
        mock_llm.get_embedding.assert_not_awaited()

    async def test_embedding_error_graceful(self, node, mock_llm, base_state):
        """임베딩 생성 실패 시 graceful degradation"""
        mock_llm.get_embedding.side_effect = RuntimeError("Azure OpenAI timeout")

        result = await node(base_state)

        assert result["cache_hit"] is False
        assert result["skip_generation"] is False
        assert result["question_embedding"] is None
        assert "cache_checker_error" in result["execution_path"]
        assert "error" in result

    async def test_cache_lookup_error_graceful(self, node, mock_cache, base_state):
        """캐시 조회 실패 시 graceful degradation"""
        mock_cache.find_similar_query.side_effect = Exception("Redis connection failed")

        result = await node(base_state)

        assert result["cache_hit"] is False
        assert result["skip_generation"] is False
        assert "cache_checker_error" in result["execution_path"]
