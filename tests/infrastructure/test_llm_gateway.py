"""
AzureOpenAIGateway 단위 테스트 (전송 계층)

실행 방법:
    pytest tests/infrastructure/test_llm_gateway.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.exceptions import (
    LLMConnectionError,
    LLMContentFilterError,
    LLMRateLimitError,
    LLMResponseError,
)
from src.infrastructure.llm import (
    AzureOpenAIGateway,
    ModelTier,
    classify_api_status_error,
)


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


class TestGatewayInit:
    """AzureOpenAIGateway 초기화 테스트"""

    def test_initialization(self):
        """초기화 테스트"""
        mock_settings = MagicMock()
        mock_settings.light_model_deployment = "gpt-4o-mini"
        mock_settings.heavy_model_deployment = "gpt-4o"

        repo = AzureOpenAIGateway(mock_settings)

        assert repo._settings == mock_settings
        assert repo._client is None

    def test_get_deployment_light(self):
        """LIGHT 티어 배포명 반환"""
        mock_settings = MagicMock()
        mock_settings.light_model_deployment = "gpt-4o-mini"
        mock_settings.heavy_model_deployment = "gpt-4o"

        repo = AzureOpenAIGateway(mock_settings)
        assert repo._get_deployment(ModelTier.LIGHT) == "gpt-4o-mini"

    def test_get_deployment_heavy(self):
        """HEAVY 티어 배포명 반환"""
        mock_settings = MagicMock()
        mock_settings.light_model_deployment = "gpt-4o-mini"
        mock_settings.heavy_model_deployment = "gpt-4o"

        repo = AzureOpenAIGateway(mock_settings)
        assert repo._get_deployment(ModelTier.HEAVY) == "gpt-4o"



class TestClassifyAPIStatusError:
    """_classify_api_status_error 헬퍼 테스트 (Phase 0 — Content Filter 분리)"""

    def _make_error(
        self,
        status_code: int,
        message: str,
        body: dict | None = None,
    ):
        """APIStatusError 모킹 (openai SDK의 실제 클래스 시그니처가 까다로워서 mock 사용)"""
        err = MagicMock()
        err.status_code = status_code
        err.message = message
        err.body = body
        return err

    def test_content_filter_400_returns_content_filter_error(self):
        """status=400 + 'content_filter' 메시지 → LLMContentFilterError"""
        e = self._make_error(
            status_code=400,
            message="The response was filtered due to content_filter",
        )
        mapped = classify_api_status_error(e)
        assert isinstance(mapped, LLMContentFilterError)

    def test_content_filter_extracts_categories_from_body(self):
        """Azure 응답 body에서 categories/param 정확히 추출"""
        body = {
            "error": {
                "param": "prompt",
                "code": "content_filter",
                "innererror": {
                    "code": "ResponsibleAIPolicyViolation",
                    "content_filter_result": {
                        "self_harm": {"filtered": True, "severity": "medium"},
                        "hate": {"filtered": False, "severity": "safe"},
                    },
                },
            }
        }
        e = self._make_error(400, "content_filter triggered", body=body)
        mapped = classify_api_status_error(e)

        assert isinstance(mapped, LLMContentFilterError)
        assert mapped.param == "prompt"
        # filtered=True인 카테고리만 수집
        assert mapped.categories == {"self_harm": "medium"}

    def test_content_filter_handles_missing_body(self):
        """body가 None이어도 죽지 않음"""
        e = self._make_error(400, "content_filter", body=None)
        mapped = classify_api_status_error(e)
        assert isinstance(mapped, LLMContentFilterError)
        assert mapped.categories == {}
        assert mapped.param is None

    def test_non_content_filter_400_returns_response_error(self):
        """status=400이지만 content_filter 아니면 일반 LLMResponseError"""
        e = self._make_error(400, "Invalid request: missing field")
        mapped = classify_api_status_error(e)
        assert isinstance(mapped, LLMResponseError)
        assert not isinstance(mapped, LLMContentFilterError)

    def test_500_returns_response_error(self):
        """5xx 에러는 LLMResponseError"""
        e = self._make_error(500, "Internal server error")
        mapped = classify_api_status_error(e)
        assert isinstance(mapped, LLMResponseError)

    def test_raw_message_not_exposed(self):
        """raw Azure 메시지는 사용자 노출되지 않음 (status code만)"""
        secret_msg = "Internal Azure trace: pod-xxx 디버그 정보 leaked"
        e = self._make_error(503, secret_msg)
        mapped = classify_api_status_error(e)
        assert isinstance(mapped, LLMResponseError)
        assert secret_msg not in mapped.message
        assert "503" in mapped.message  # status code는 노출 OK


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
        repo = AzureOpenAIGateway(mock_settings)

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
        repo = AzureOpenAIGateway(mock_settings)

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
        repo = AzureOpenAIGateway(mock_settings)

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
        repo = AzureOpenAIGateway(mock_settings)

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
        repo = AzureOpenAIGateway(mock_settings)

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
        repo = AzureOpenAIGateway(mock_settings)

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
        repo = AzureOpenAIGateway(mock_settings)

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

        repo = AzureOpenAIGateway(mock_settings)

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

        repo = AzureOpenAIGateway(mock_settings)

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

        repo = AzureOpenAIGateway(mock_settings)

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
        repo = AzureOpenAIGateway(mock_settings)

        mock_client = AsyncMock()
        repo._client = mock_client

        await repo.close()

        mock_client.close.assert_called_once()
        assert repo._client is None

    @pytest.mark.asyncio
    async def test_close_uninitialized_client(self, mock_settings):
        """초기화되지 않은 클라이언트 종료"""
        repo = AzureOpenAIGateway(mock_settings)

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
        repo = AzureOpenAIGateway(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Success response"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.generate_with_fallback(
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

        repo = AzureOpenAIGateway(mock_settings)

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

        result = await repo.generate_with_fallback(
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

        repo = AzureOpenAIGateway(mock_settings)

        connection_error = APIConnectionError(request=MagicMock())

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=connection_error)
        repo._client = mock_client

        with pytest.raises(LLMResponseError) as exc_info:
            await repo.generate_with_fallback(
                system_prompt="Test",
                user_prompt="Test",
            )

        assert "All model tiers failed" in str(exc_info.value)
        # 두 번 호출되어야 함 (HEAVY 실패 + LIGHT 실패)
        assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_json_fallback_success_on_first_try(self, mock_settings):
        """JSON 생성 HEAVY 티어 성공 시 fallback 불필요"""
        repo = AzureOpenAIGateway(mock_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"key": "value"}'

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.generate_json_with_fallback(
            system_prompt="Test",
            user_prompt="Test",
        )

        assert result == {"key": "value"}
        assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_json_fallback_to_light(self, mock_settings):
        """JSON 생성 HEAVY 실패 시 LIGHT로 fallback"""
        repo = AzureOpenAIGateway(mock_settings)

        # HEAVY에서 LLMResponseError 발생 시 fallback
        heavy_error = LLMResponseError("HEAVY failed")
        light_response = MagicMock()
        light_response.choices = [MagicMock()]
        light_response.choices[0].message.content = '{"fallback": true}'

        # generate_json을 직접 mock
        call_count = 0

        async def mock_generate_json(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("model_tier") == ModelTier.HEAVY:
                raise heavy_error
            return {"fallback": True}

        repo.generate_json = mock_generate_json

        result = await repo.generate_json_with_fallback(
            system_prompt="Test",
            user_prompt="Test",
        )

        assert result == {"fallback": True}
        assert call_count == 2  # HEAVY 실패 + LIGHT 성공


class TestGatewayStreaming:
    """generate_stream 전송 primitive 테스트"""

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
    async def test_stream_yields_chunks(self, mock_settings):
        """스트리밍이 청크 단위로 yield"""
        gateway = AzureOpenAIGateway(mock_settings)

        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=" World"))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="!"))]),
        ]

        async def mock_async_iter():
            for chunk in mock_chunks:
                yield chunk

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_async_iter()
        )
        gateway._client = mock_client

        chunks = []
        async for chunk in gateway.generate_stream(
            system_prompt="System",
            user_prompt="User",
        ):
            chunks.append(chunk)

        assert chunks == ["Hello", " World", "!"]

    @pytest.mark.asyncio
    async def test_stream_uses_heavy_model_by_default(self, mock_settings):
        """스트리밍 기본 티어는 HEAVY"""
        gateway = AzureOpenAIGateway(mock_settings)

        async def mock_async_iter():
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="test"))])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_async_iter()
        )
        gateway._client = mock_client

        async for _ in gateway.generate_stream(
            system_prompt="System",
            user_prompt="User",
        ):
            pass

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == mock_settings.heavy_model_deployment
        assert call_kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_stream_handles_empty_chunks(self, mock_settings):
        """빈 content 청크는 무시"""
        gateway = AzureOpenAIGateway(mock_settings)

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

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_async_iter()
        )
        gateway._client = mock_client

        chunks = []
        async for chunk in gateway.generate_stream(
            system_prompt="System",
            user_prompt="User",
        ):
            chunks.append(chunk)

        assert chunks == ["Hello", " World"]


class TestGPT5TemperatureRegression:
    """GPT-5 계열 배포에서 temperature 파라미터 제외 회귀 테스트

    운영 환경의 LIGHT/HEAVY가 모두 gpt-5 계열이므로,
    temperature가 포함되면 3경로(generate/generate_json/generate_stream)
    전부 400 에러로 장애가 됨. 반드시 키 자체가 빠져야 함.
    """

    @pytest.fixture
    def gpt5_settings(self):
        settings = MagicMock()
        settings.azure_openai_endpoint = "https://test.openai.azure.com"
        settings.azure_openai_api_key = "test-key"
        settings.azure_openai_api_version = "2025-04-01-preview"
        settings.light_model_deployment = "gpt-5.4"
        settings.heavy_model_deployment = "gpt-5.4"
        settings.llm_temperature = 0.0
        settings.llm_max_tokens = 2000
        return settings

    @pytest.mark.asyncio
    async def test_generate_omits_temperature_for_gpt5(self, gpt5_settings):
        """generate: gpt-5 배포에서 temperature 키 부재"""
        gateway = AzureOpenAIGateway(gpt5_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        gateway._client = mock_client

        await gateway.generate(system_prompt="s", user_prompt="u")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in call_kwargs

    @pytest.mark.asyncio
    async def test_generate_json_omits_temperature_for_gpt5(self, gpt5_settings):
        """generate_json: gpt-5 배포에서 temperature 키 부재"""
        gateway = AzureOpenAIGateway(gpt5_settings)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"ok": true}'

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        gateway._client = mock_client

        await gateway.generate_json(system_prompt="s", user_prompt="u")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in call_kwargs

    @pytest.mark.asyncio
    async def test_generate_stream_omits_temperature_for_gpt5(self, gpt5_settings):
        """generate_stream: gpt-5 배포에서 temperature 키 부재"""
        gateway = AzureOpenAIGateway(gpt5_settings)

        async def mock_async_iter():
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="ok"))])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_async_iter()
        )
        gateway._client = mock_client

        async for _ in gateway.generate_stream(system_prompt="s", user_prompt="u"):
            pass

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in call_kwargs
