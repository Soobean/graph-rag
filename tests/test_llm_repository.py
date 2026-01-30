"""
LLM Repository 단위 테스트

실행 방법:
    pytest tests/test_llm_repository.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.exceptions import LLMConnectionError, LLMRateLimitError, LLMResponseError
from src.repositories.llm_repository import LLMRepository, ModelTier


class TestModelTier:
    """ModelTier Enum 테스트"""

    def test_model_tier_values(self):
        """ModelTier 값 테스트"""
        assert ModelTier.LIGHT.value == "light"
        assert ModelTier.HEAVY.value == "heavy"

    def test_model_tier_is_string_enum(self):
        """ModelTier가 문자열 Enum인지 확인"""
        assert isinstance(ModelTier.LIGHT, str)
        assert ModelTier.LIGHT == "light"


class TestLLMRepositoryInit:
    """LLMRepository 초기화 테스트"""

    def test_initialization(self):
        """초기화 테스트"""
        mock_settings = MagicMock()
        mock_settings.light_model_deployment = "gpt-4o-mini"
        mock_settings.heavy_model_deployment = "gpt-4o"

        repo = LLMRepository(mock_settings)

        assert repo._settings == mock_settings
        assert repo._client is None

    def test_get_deployment_light(self):
        """LIGHT 티어 배포명 반환"""
        mock_settings = MagicMock()
        mock_settings.light_model_deployment = "gpt-4o-mini"
        mock_settings.heavy_model_deployment = "gpt-4o"

        repo = LLMRepository(mock_settings)
        assert repo._get_deployment(ModelTier.LIGHT) == "gpt-4o-mini"

    def test_get_deployment_heavy(self):
        """HEAVY 티어 배포명 반환"""
        mock_settings = MagicMock()
        mock_settings.light_model_deployment = "gpt-4o-mini"
        mock_settings.heavy_model_deployment = "gpt-4o"

        repo = LLMRepository(mock_settings)
        assert repo._get_deployment(ModelTier.HEAVY) == "gpt-4o"


class TestFormatHelpers:
    """포맷팅 헬퍼 메서드 테스트"""

    @pytest.fixture
    def repo(self):
        mock_settings = MagicMock()
        return LLMRepository(mock_settings)

    def test_format_schema_full(self, repo):
        """전체 스키마 포맷팅"""
        schema = {
            "node_labels": ["Person", "Company"],
            "relationship_types": ["WORKS_AT", "KNOWS"],
        }
        result = repo._format_schema(schema)

        assert "Node Labels: Person, Company" in result
        assert "Relationship Types: WORKS_AT, KNOWS" in result

    def test_format_schema_empty(self, repo):
        """빈 스키마 포맷팅"""
        result = repo._format_schema({})
        assert result == "Schema information not available"

    def test_format_schema_partial(self, repo):
        """부분 스키마 포맷팅"""
        schema = {"node_labels": ["Person"]}
        result = repo._format_schema(schema)

        assert "Node Labels: Person" in result
        assert "Relationship Types" not in result

    def test_format_entities_with_data(self, repo):
        """엔티티 포맷팅"""
        entities = [
            {"type": "Person", "value": "홍길동", "normalized": "홍길동"},
            {"type": "Company", "value": "ABC회사", "normalized": "ABC"},
        ]
        result = repo._format_entities(entities)

        assert "Person: 홍길동" in result
        assert "Company: ABC회사" in result

    def test_format_entities_empty(self, repo):
        """빈 엔티티 포맷팅"""
        result = repo._format_entities([])
        assert result == "No entities extracted"

    def test_format_entities_missing_fields(self, repo):
        """필드 누락 엔티티 포맷팅"""
        entities = [{"type": "Person"}]
        result = repo._format_entities(entities)
        assert "Person:" in result
        assert "Unknown" not in result

    def test_format_results_with_data(self, repo):
        """결과 포맷팅 - Neo4j 노드 형식 필요"""
        # _format_results는 이제 Neo4j 노드 형식(labels 속성)을 기대함
        results = [
            {"n": {"id": 1, "labels": ["Employee"], "properties": {"name": "홍길동"}}},
            {"n": {"id": 2, "labels": ["Employee"], "properties": {"name": "김철수"}}},
        ]
        result = repo._format_results(results)

        assert "홍길동" in result
        assert "김철수" in result
        assert "[Employee]" in result
        assert "2개" in result  # 총 2개의 고유 엔티티

    def test_format_results_empty(self, repo):
        """빈 결과 포맷팅"""
        result = repo._format_results([])
        assert result == "No results found"

    def test_format_results_truncation(self, repo):
        """결과 15개 초과 시 자르기"""
        # _format_results는 라벨별로 최대 15개까지 표시
        # id는 1부터 시작 (0은 falsy로 처리될 수 있음)
        results = [
            {"n": {"id": i + 1, "labels": ["Node"], "properties": {"name": f"Node{i + 1}"}}}
            for i in range(20)
        ]
        result = repo._format_results(results)

        assert "20개의 고유 엔티티" in result
        assert "[Node]" in result
        assert "외 5개" in result  # 15개 초과분 표시


class TestLLMGenerate:
    """LLM 생성 메서드 테스트"""

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

    @pytest.fixture
    def mock_response(self):
        """Mock LLM 응답"""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "Test response"
        return response

    @pytest.mark.asyncio
    async def test_generate_success(self, mock_settings, mock_response):
        """텍스트 생성 성공"""
        repo = LLMRepository(mock_settings)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.generate(
            system_prompt="You are helpful.",
            user_prompt="Hello",
        )

        assert result == "Test response"

    @pytest.mark.asyncio
    async def test_generate_empty_response(self, mock_settings):
        """빈 응답 체크"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = []

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        with pytest.raises(LLMResponseError) as exc_info:
            await repo.generate(
                system_prompt="Test",
                user_prompt="Test",
            )
        assert "No response choices" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_with_custom_params(self, mock_settings, mock_response):
        """커스텀 파라미터로 생성"""
        repo = LLMRepository(mock_settings)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        await repo.generate(
            system_prompt="Test",
            user_prompt="Test",
            model_tier=ModelTier.HEAVY,
            temperature=0.7,
            max_completion_tokens=500,
        )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_completion_tokens"] == 500


class TestLLMGenerateJSON:
    """JSON 생성 메서드 테스트"""

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
    async def test_generate_json_success(self, mock_settings):
        """JSON 생성 성공"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"key": "value"}'

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.generate_json(
            system_prompt="Return JSON",
            user_prompt="Test",
        )

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_generate_json_empty_response(self, mock_settings):
        """JSON 빈 응답 체크"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = []

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        with pytest.raises(LLMResponseError) as exc_info:
            await repo.generate_json(
                system_prompt="Test",
                user_prompt="Test",
            )
        assert "No response choices" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_json_invalid_json(self, mock_settings):
        """유효하지 않은 JSON 응답"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        with pytest.raises(LLMResponseError) as exc_info:
            await repo.generate_json(
                system_prompt="Return JSON",
                user_prompt="Test",
            )
        assert "Invalid JSON" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_json_null_content(self, mock_settings):
        """content가 None인 경우 기본값 처리"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.generate_json(
            system_prompt="Return JSON",
            user_prompt="Test",
        )
        assert result == {}


class TestLLMErrorHandling:
    """에러 핸들링 테스트"""

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
    async def test_rate_limit_error(self, mock_settings):
        """Rate Limit 에러 처리"""
        from openai import RateLimitError

        repo = LLMRepository(mock_settings)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None,
            )
        )
        repo._client = mock_client

        with pytest.raises(LLMRateLimitError):
            await repo.generate(system_prompt="Test", user_prompt="Test")

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_settings):
        """연결 에러 처리"""
        from openai import APIConnectionError

        repo = LLMRepository(mock_settings)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock())
        )
        repo._client = mock_client

        with pytest.raises(LLMConnectionError):
            await repo.generate(system_prompt="Test", user_prompt="Test")

    @pytest.mark.asyncio
    async def test_api_status_error(self, mock_settings):
        """API 상태 에러 처리"""
        from openai import APIStatusError

        repo = LLMRepository(mock_settings)

        mock_error = APIStatusError(
            message="Server error",
            response=MagicMock(status_code=500),
            body=None,
        )

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=mock_error)
        repo._client = mock_client

        with pytest.raises(LLMResponseError):
            await repo.generate(system_prompt="Test", user_prompt="Test")


class TestHighLevelMethods:
    """고수준 메서드 테스트 (classify_intent, extract_entities 등)"""

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
    async def test_classify_intent(self, mock_settings):
        """의도 분류"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"intent": "search", "confidence": 0.9}'

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.classify_intent(
            question="홍길동 찾아줘",
            available_intents=["search", "create", "update"],
        )

        assert result["intent"] == "search"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_extract_entities(self, mock_settings):
        """엔티티 추출"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"entities": [{"type": "Person", "value": "홍길동", "normalized": "홍길동"}]}'
        )

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.extract_entities(
            question="홍길동이 근무하는 회사는?",
            entity_types=["Person", "Company"],
        )

        assert len(result["entities"]) == 1
        assert result["entities"][0]["type"] == "Person"

    @pytest.mark.asyncio
    async def test_generate_cypher(self, mock_settings):
        """Cypher 쿼리 생성"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"cypher": "MATCH (p:Person {name: $name}) RETURN p", '
            '"parameters": {"name": "홍길동"}, '
            '"explanation": "Finding person by name"}'
        )

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.generate_cypher(
            question="홍길동 찾아줘",
            schema={"node_labels": ["Person"], "relationship_types": []},
            entities=[{"type": "Person", "value": "홍길동", "normalized": "홍길동"}],
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
        repo._client = mock_client

        result = await repo.generate_response(
            question="홍길동이 어디서 일해?",
            query_results=[{"name": "홍길동", "company": "ABC"}],
            cypher_query="MATCH (p:Person)-[:WORKS_AT]->(c:Company) RETURN p, c",
        )

        assert "홍길동" in result
        assert "ABC" in result


class TestClientLifecycle:
    """클라이언트 라이프사이클 테스트"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.azure_openai_endpoint = "https://test.openai.azure.com"
        settings.azure_openai_api_key = "test-key"
        settings.azure_openai_api_version = "2024-10-21"
        settings.light_model_deployment = "gpt-4o-mini"
        settings.heavy_model_deployment = "gpt-4o"
        return settings

    @pytest.mark.asyncio
    async def test_close_client(self, mock_settings):
        """클라이언트 종료"""
        repo = LLMRepository(mock_settings)

        mock_client = AsyncMock()
        repo._client = mock_client

        await repo.close()

        mock_client.close.assert_called_once()
        assert repo._client is None

    @pytest.mark.asyncio
    async def test_close_uninitialized_client(self, mock_settings):
        """초기화되지 않은 클라이언트 종료"""
        repo = LLMRepository(mock_settings)

        # 에러 없이 종료되어야 함
        await repo.close()
        assert repo._client is None


class TestFallbackMethods:
    """Fallback 메서드 테스트 (HEAVY → LIGHT → Error)"""

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
    async def test_fallback_success_on_first_try(self, mock_settings):
        """HEAVY 티어 성공 시 fallback 불필요"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Success response"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo._generate_with_fallback(
            system_prompt="Test",
            user_prompt="Test",
        )

        assert result == "Success response"
        # 한 번만 호출되어야 함 (HEAVY만 성공)
        assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_to_light_on_rate_limit(self, mock_settings):
        """HEAVY Rate Limit 시 LIGHT로 fallback"""
        from openai import RateLimitError

        repo = LLMRepository(mock_settings)

        # HEAVY 실패, LIGHT 성공
        heavy_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body=None,
        )
        light_response = MagicMock()
        light_response.choices = [MagicMock()]
        light_response.choices[0].message.content = "Fallback response"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[heavy_error, light_response]
        )
        repo._client = mock_client

        result = await repo._generate_with_fallback(
            system_prompt="Test",
            user_prompt="Test",
        )

        assert result == "Fallback response"
        # 두 번 호출되어야 함 (HEAVY 실패 + LIGHT 성공)
        assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_all_tiers_fail(self, mock_settings):
        """모든 티어 실패 시 에러 발생"""
        from openai import APIConnectionError

        repo = LLMRepository(mock_settings)

        connection_error = APIConnectionError(request=MagicMock())

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=connection_error)
        repo._client = mock_client

        with pytest.raises(LLMResponseError) as exc_info:
            await repo._generate_with_fallback(
                system_prompt="Test",
                user_prompt="Test",
            )

        assert "All model tiers failed" in str(exc_info.value)
        # 두 번 호출되어야 함 (HEAVY 실패 + LIGHT 실패)
        assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_json_fallback_success_on_first_try(self, mock_settings):
        """JSON 생성 HEAVY 티어 성공 시 fallback 불필요"""
        repo = LLMRepository(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"key": "value"}'

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo._generate_json_with_fallback(
            system_prompt="Test",
            user_prompt="Test",
        )

        assert result == {"key": "value"}
        assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_json_fallback_to_light(self, mock_settings):
        """JSON 생성 HEAVY 실패 시 LIGHT로 fallback"""
        repo = LLMRepository(mock_settings)

        # HEAVY에서 LLMResponseError 발생 시 fallback
        heavy_error = LLMResponseError("HEAVY failed")
        light_response = MagicMock()
        light_response.choices = [MagicMock()]
        light_response.choices[0].message.content = '{"fallback": true}'

        # generate_json을 직접 mock
        original_generate_json = repo.generate_json
        call_count = 0

        async def mock_generate_json(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("model_tier") == ModelTier.HEAVY:
                raise heavy_error
            return {"fallback": True}

        repo.generate_json = mock_generate_json

        result = await repo._generate_json_with_fallback(
            system_prompt="Test",
            user_prompt="Test",
        )

        assert result == {"fallback": True}
        assert call_count == 2  # HEAVY 실패 + LIGHT 성공
