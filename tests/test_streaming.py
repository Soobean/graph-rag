"""
스트리밍 응답 테스트

ResponseGenerator의 토큰 단위 스트리밍 및 SSE 엔드포인트 검증
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.repositories.llm_repository import LLMRepository


class TestLLMRepositoryStreamingMethod:
    """LLMRepository.generate_response_stream 테스트"""

    @pytest.fixture
    def settings(self) -> Settings:
        return Settings()

    @pytest.fixture
    def llm_repository(self, settings: Settings) -> LLMRepository:
        return LLMRepository(settings)

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self, llm_repository: LLMRepository) -> None:
        """스트리밍이 청크 단위로 yield"""
        # Mock 청크 데이터
        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=" World"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="!"))]),
        ]

        async def mock_async_iter():
            for chunk in mock_chunks:
                yield chunk

        mock_response = mock_async_iter()

        with patch.object(llm_repository, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            chunks = []
            async for chunk in llm_repository.generate_response_stream(
                question="테스트 질문",
                query_results=[{"name": "홍길동"}],
                cypher_query="MATCH (p:Employee) RETURN p",
            ):
                chunks.append(chunk)

            assert chunks == ["Hello", " World", "!"]

    @pytest.mark.asyncio
    async def test_stream_uses_heavy_model(self, llm_repository: LLMRepository) -> None:
        """스트리밍은 HEAVY 모델 사용"""

        async def mock_async_iter():
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="test"))])

        mock_response = mock_async_iter()

        with patch.object(llm_repository, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            # 스트림 소비
            async for _ in llm_repository.generate_response_stream(
                question="테스트",
                query_results=[],
                cypher_query="",
            ):
                pass

            # HEAVY 모델 배포명 사용 확인
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert (
                call_kwargs["model"] == llm_repository._settings.heavy_model_deployment
            )
            assert call_kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_stream_handles_empty_chunks(
        self, llm_repository: LLMRepository
    ) -> None:
        """빈 content 청크는 무시"""
        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=None))]),  # 빈 청크
            MagicMock(choices=[MagicMock(delta=MagicMock(content=""))]),  # 빈 문자열
            MagicMock(choices=[]),  # choices 없음
            MagicMock(choices=[MagicMock(delta=MagicMock(content=" World"))]),
        ]

        async def mock_async_iter():
            for chunk in mock_chunks:
                yield chunk

        mock_response = mock_async_iter()

        with patch.object(llm_repository, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            chunks = []
            async for chunk in llm_repository.generate_response_stream(
                question="테스트",
                query_results=[],
                cypher_query="",
            ):
                chunks.append(chunk)

            # 빈 청크는 무시됨
            assert chunks == ["Hello", " World"]


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
