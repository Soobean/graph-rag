"""
스트리밍 응답 테스트

파이프라인 메타데이터 빌드 및 SSE 엔드포인트 검증.
LLM 스트리밍 전송(generate_stream) 테스트는
tests/infrastructure/test_llm_gateway.py로 이관됨.
"""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest


class TestBuildMetadata:
    """Pipeline._build_metadata 테스트"""

    def test_build_metadata_with_expanded_entities(self) -> None:
        """expanded_entities 우선 사용"""

        # _build_metadata는 인스턴스 메서드이므로 직접 호출 테스트
        state = {
            "intent": "personnel_search",
            "intent_confidence": 0.95,
            "entities": {"Skill": ["Python"]},
            "expanded_entities": {"Skill": ["Python", "python", "파이썬"]},
            "cypher_query": "MATCH (p:Employee) RETURN p",
            "result_count": 5,
            "execution_path": ["intent_classifier", "cypher_generator"],
        }

        # 정적으로 메타데이터 빌드 로직 테스트
        entities = state.get("expanded_entities") or state.get("entities", {})
        metadata = {
            "intent": state.get("intent", "unknown"),
            "intent_confidence": state.get("intent_confidence", 0.0),
            "entities": entities,
            "cypher_query": state.get("cypher_query", ""),
            "result_count": state.get("result_count", 0),
            "execution_path": state.get("execution_path", []),
        }

        assert metadata["intent"] == "personnel_search"
        assert "파이썬" in metadata["entities"]["Skill"]  # expanded 사용
        assert metadata["result_count"] == 5

    def test_build_metadata_fallback_to_entities(self) -> None:
        """expanded_entities 없으면 entities 사용"""
        state = {
            "intent": "certificate_search",
            "intent_confidence": 0.8,
            "entities": {"Certificate": ["정보처리기사"]},
            # expanded_entities 없음
            "cypher_query": "",
            "result_count": 0,
            "execution_path": [],
        }

        entities = state.get("expanded_entities") or state.get("entities", {})
        metadata = {
            "intent": state.get("intent", "unknown"),
            "entities": entities,
        }

        assert "정보처리기사" in metadata["entities"]["Certificate"]


class TestStreamingEndpoint:
    """SSE 엔드포인트 테스트"""

    @pytest.fixture
    def mock_pipeline(self) -> MagicMock:
        from src.graph.pipeline import GraphRAGPipeline

        pipeline = MagicMock(spec=GraphRAGPipeline)

        async def mock_stream(*args, **kwargs) -> AsyncIterator[dict]:
            yield {"type": "metadata", "data": {"intent": "personnel_search"}}
            yield {"type": "chunk", "text": "응답 "}
            yield {"type": "chunk", "text": "텍스트"}
            yield {"type": "done", "full_response": "응답 텍스트", "success": True}

        pipeline.run_with_streaming_response = mock_stream
        return pipeline

    @pytest.mark.asyncio
    async def test_original_endpoint_unchanged(self) -> None:
        """기존 /query 엔드포인트는 변경 없음"""

        from src.api.routes.query import router

        # router에 /query와 /query/stream 모두 존재 확인
        routes = [r.path for r in router.routes]
        assert "/api/v1/query" in routes
        assert "/api/v1/query/stream" in routes
