"""
LLM Repository 단위 테스트 (task 계층 — 포맷팅/고수준 메서드)

전송 계층(generate/generate_json/fallback/스트리밍/에러분류) 테스트는
tests/infrastructure/test_llm_gateway.py로 이관됨.

실행 방법:
    pytest tests/test_llm_repository.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.llm_repository import LLMRepository


class TestHighLevelMethods:
    """고수준 메서드 테스트 (generate_cypher, generate_response 등)"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.azure_openai_endpoint = "https://test.openai.azure.com"
        settings.azure_openai_api_key = "test-key"
        settings.azure_openai_api_version = "2024-10-21"
        settings.light_model_deployment = "gpt-4o-mini"
        settings.heavy_model_deployment = "gpt-4o"
        settings.llm_temperature = 0.0
        settings.llm_max_tokens = 2000
        return settings

    @pytest.mark.asyncio
    async def test_generate_cypher(self, mock_settings):
        """Cypher 쿼리 생성"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"cypher": "MATCH (p:Employee {name: $name}) RETURN p", '
            '"parameters": {"name": "홍길동"}, '
            '"explanation": "Finding person by name"}'
        )

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._gateway._client = mock_client

        result = await repo.generate_cypher(
            question="홍길동 찾아줘",
            schema={"node_labels": ["Employee"], "relationship_types": []},
            entities=[{"type": "Employee", "value": "홍길동", "normalized": "홍길동"}],
        )

        assert "cypher" in result
        assert "parameters" in result
        # HEAVY 모델 사용 확인
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_generate_response(self, mock_settings):
        """응답 생성"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "홍길동은 ABC 회사에서 근무합니다."

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._gateway._client = mock_client

        result = await repo.generate_response(
            question="홍길동이 어디서 일해?",
            query_results=[{"name": "홍길동", "company": "ABC"}],
            cypher_query="MATCH (p:Employee)-[:WORKS_AT]->(c:Company) RETURN p, c",
        )

        assert "홍길동" in result
        assert "ABC" in result

