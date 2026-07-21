"""
LLMTaskService 단위 테스트 (use-case 계층)

게이트웨이 경계 계약 검증: 각 task가 올바른 primitive/티어로 호출하는지.

실행 방법:
    pytest tests/application/test_llm_task_service.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.llm import LLMTaskService
from src.infrastructure.llm import AzureOpenAIGateway, ModelTier


@pytest.fixture
def mock_gateway():
    gateway = MagicMock(spec=AzureOpenAIGateway)
    gateway.generate = AsyncMock(return_value="text response")
    gateway.generate_json = AsyncMock(return_value={})
    gateway.generate_with_fallback = AsyncMock(return_value="fallback text")
    gateway.generate_json_with_fallback = AsyncMock(return_value={})
    return gateway


@pytest.fixture
def service(mock_gateway):
    return LLMTaskService(mock_gateway)


class TestIntentEntityExtraction:
    """classify_intent_and_extract_entities 계약"""

    @pytest.mark.asyncio
    async def test_calls_generate_json_with_light_model(
        self, service, mock_gateway
    ) -> None:
        """LIGHT 모델로 generate_json 1회 호출"""
        mock_gateway.generate_json.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [],
        }

        result = await service.classify_intent_and_extract_entities(
            question="테스트 질문",
            available_intents=["personnel_search"],
            entity_types=["Employee"],
        )

        mock_gateway.generate_json.assert_called_once()
        call_kwargs = mock_gateway.generate_json.call_args.kwargs
        assert call_kwargs["model_tier"] == ModelTier.LIGHT
        assert result["intent"] == "personnel_search"


class TestGenerateCypher:
    """generate_cypher 계약"""

    @pytest.mark.asyncio
    async def test_uses_json_fallback(self, service, mock_gateway) -> None:
        """HEAVY→LIGHT fallback primitive 사용"""
        mock_gateway.generate_json_with_fallback.return_value = {
            "cypher": "MATCH (p:Employee {name: $name}) RETURN p",
            "parameters": {"name": "홍길동"},
        }

        result = await service.generate_cypher(
            question="홍길동 찾아줘",
            schema={"node_labels": ["Employee"], "relationship_types": []},
            entities=[{"type": "Employee", "value": "홍길동", "normalized": "홍길동"}],
        )

        mock_gateway.generate_json_with_fallback.assert_called_once()
        assert "MATCH" in result["cypher"]

    @pytest.mark.asyncio
    async def test_intent_included_in_prompt(self, service, mock_gateway) -> None:
        """intent가 user 프롬프트에 포함됨"""
        mock_gateway.generate_json_with_fallback.return_value = {"cypher": ""}

        await service.generate_cypher(
            question="질문",
            schema={},
            entities=[],
            intent="personnel_search",
        )

        call_kwargs = mock_gateway.generate_json_with_fallback.call_args.kwargs
        assert "personnel_search" in call_kwargs["user_prompt"]


class TestGenerateResponse:
    """generate_response / generate_response_stream 계약"""

    @pytest.mark.asyncio
    async def test_uses_text_fallback(self, service, mock_gateway) -> None:
        """HEAVY→LIGHT fallback primitive 사용"""
        mock_gateway.generate_with_fallback.return_value = "홍길동을 찾았습니다."

        result = await service.generate_response(
            question="홍길동 찾아줘",
            query_results=[{"name": "홍길동"}],
            cypher_query="MATCH (p) RETURN p",
        )

        mock_gateway.generate_with_fallback.assert_called_once()
        assert result == "홍길동을 찾았습니다."

    @pytest.mark.asyncio
    async def test_stream_delegates_to_gateway_heavy(
        self, service, mock_gateway
    ) -> None:
        """스트리밍은 gateway.generate_stream(HEAVY)에 위임"""

        async def mock_stream(**kwargs):
            yield "Hello"
            yield " World"

        mock_gateway.generate_stream = mock_stream

        chunks = []
        async for chunk in service.generate_response_stream(
            question="테스트",
            query_results=[],
            cypher_query="",
        ):
            chunks.append(chunk)

        assert chunks == ["Hello", " World"]

    @pytest.mark.asyncio
    async def test_stream_and_response_share_prompt_build(
        self, service, mock_gateway
    ) -> None:
        """stream/non-stream이 동일한 프롬프트를 조립 (중복 제거 검증)"""
        captured: dict[str, str] = {}

        async def mock_stream(**kwargs):
            captured["system"] = kwargs["system_prompt"]
            captured["user"] = kwargs["user_prompt"]
            yield "x"

        mock_gateway.generate_stream = mock_stream

        question = "테스트 질문"
        results = [{"name": "홍길동"}]

        async for _ in service.generate_response_stream(
            question=question, query_results=results, cypher_query=""
        ):
            pass

        await service.generate_response(
            question=question, query_results=results, cypher_query=""
        )

        call_kwargs = mock_gateway.generate_with_fallback.call_args.kwargs
        assert call_kwargs["system_prompt"] == captured["system"]
        assert call_kwargs["user_prompt"] == captured["user"]


class TestClarification:
    """generate_clarification 계약"""

    @pytest.mark.asyncio
    async def test_uses_light_tier(self, service, mock_gateway) -> None:
        """LIGHT 티어 generate 사용"""
        await service.generate_clarification(
            question="누구?",
            unresolved_entities="홍길동",
        )

        mock_gateway.generate.assert_called_once()
        call_kwargs = mock_gateway.generate.call_args.kwargs
        assert call_kwargs["model_tier"] == ModelTier.LIGHT


class TestDecomposeQuery:
    """decompose_query 계약"""

    @pytest.mark.asyncio
    async def test_uses_light_tier_json(self, service, mock_gateway) -> None:
        """LIGHT 티어 generate_json 사용"""
        mock_gateway.generate_json.return_value = {
            "is_multi_hop": False,
            "hop_count": 1,
            "hops": [],
        }

        result = await service.decompose_query(question="테스트")

        mock_gateway.generate_json.assert_called_once()
        call_kwargs = mock_gateway.generate_json.call_args.kwargs
        assert call_kwargs["model_tier"] == ModelTier.LIGHT
        assert result["is_multi_hop"] is False
