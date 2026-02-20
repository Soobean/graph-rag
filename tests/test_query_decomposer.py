"""
QueryDecomposerNode 단위 테스트

실행: pytest tests/test_query_decomposer.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.nodes.query_decomposer import QueryDecomposerNode
from src.graph.state import GraphRAGState


class TestQueryDecomposerNode:
    """QueryDecomposerNode 테스트"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.decompose_query = AsyncMock()
        return llm

    @pytest.fixture
    def node(self, mock_llm):
        return QueryDecomposerNode(mock_llm)

    async def test_skip_non_multi_hop_intent(self, node, mock_llm):
        """personnel_search 등 single-hop intent는 분해 스킵"""
        state = GraphRAGState(
            question="홍길동의 스킬은?",
            intent="personnel_search",
        )

        result = await node(state)

        assert result["query_plan"]["is_multi_hop"] is False
        assert result["query_plan"]["hop_count"] == 1
        assert "query_decomposer_skipped" in result["execution_path"]
        mock_llm.decompose_query.assert_not_awaited()

    async def test_skip_unknown_intent(self, node, mock_llm):
        """unknown intent도 스킵"""
        state = GraphRAGState(question="아무 질문")

        result = await node(state)

        assert result["query_plan"]["is_multi_hop"] is False
        assert "query_decomposer_skipped" in result["execution_path"]
        mock_llm.decompose_query.assert_not_awaited()

    async def test_decompose_path_analysis(self, node, mock_llm):
        """path_analysis intent → LLM 분해 호출"""
        mock_llm.decompose_query.return_value = {
            "is_multi_hop": True,
            "hop_count": 3,
            "hops": [
                {"description": "Find Python experts"},
                {"description": "Find their mentors"},
                {"description": "Filter by AWS skill"},
            ],
            "final_return": "mentor",
            "explanation": "3-hop path query",
        }

        state = GraphRAGState(
            question="Python 잘하는 사람의 멘토 중 AWS 경험자는?",
            intent="path_analysis",
        )

        result = await node(state)

        assert result["query_plan"]["is_multi_hop"] is True
        assert result["query_plan"]["hop_count"] == 3
        assert len(result["query_plan"]["hops"]) == 3
        assert result["query_plan"]["final_return"] == "mentor"
        assert "query_decomposer" in result["execution_path"]

    async def test_decompose_relationship_search(self, node, mock_llm):
        """relationship_search intent → 분해 호출"""
        mock_llm.decompose_query.return_value = {
            "is_multi_hop": True,
            "hop_count": 2,
            "hops": [{"description": "hop1"}, {"description": "hop2"}],
            "final_return": "",
            "explanation": "2-hop relationship",
        }

        state = GraphRAGState(
            question="김철수와 이영희의 관계는?",
            intent="relationship_search",
        )

        result = await node(state)

        assert result["query_plan"]["is_multi_hop"] is True
        assert "query_decomposer" in result["execution_path"]
        mock_llm.decompose_query.assert_awaited_once()

    async def test_decompose_mentoring_network(self, node, mock_llm):
        """mentoring_network intent → 분해 호출"""
        mock_llm.decompose_query.return_value = {
            "is_multi_hop": False,
            "hop_count": 1,
            "hops": [],
            "final_return": "",
            "explanation": "Single hop mentoring",
        }

        state = GraphRAGState(
            question="멘토링 관계 보여줘",
            intent="mentoring_network",
        )

        result = await node(state)

        assert result["query_plan"]["is_multi_hop"] is False
        assert "query_decomposer" in result["execution_path"]

    async def test_llm_error_fallback(self, node, mock_llm):
        """LLM 실패 시 single-hop으로 폴백"""
        mock_llm.decompose_query.side_effect = RuntimeError("LLM unavailable")

        state = GraphRAGState(
            question="경로 분석 질문",
            intent="path_analysis",
        )

        result = await node(state)

        assert result["query_plan"]["is_multi_hop"] is False
        assert result["query_plan"]["hop_count"] == 1
        assert "query_decomposer_error" in result["execution_path"]
        assert "error" in result

    async def test_llm_returns_incomplete_dict(self, node, mock_llm):
        """LLM이 불완전한 dict 반환 시 기본값 사용"""
        mock_llm.decompose_query.return_value = {
            "is_multi_hop": True,
            # hop_count, hops 등 누락
        }

        state = GraphRAGState(
            question="경로 분석",
            intent="path_analysis",
        )

        result = await node(state)

        assert result["query_plan"]["is_multi_hop"] is True
        assert result["query_plan"]["hop_count"] == 1  # default
        assert result["query_plan"]["hops"] == []  # default
        assert "query_decomposer" in result["execution_path"]

    async def test_schema_passed_to_llm(self, node, mock_llm):
        """state에 schema가 있으면 LLM에 전달"""
        mock_llm.decompose_query.return_value = {
            "is_multi_hop": False,
            "hop_count": 1,
            "hops": [],
            "final_return": "",
            "explanation": "",
        }

        schema = {"node_labels": ["Employee", "Skill"]}
        state = GraphRAGState(
            question="관계 분석",
            intent="relationship_search",
            schema=schema,
        )

        await node(state)

        call_kwargs = mock_llm.decompose_query.call_args.kwargs
        assert call_kwargs["schema"] == schema
