"""
LLM Repository 단위 테스트

실행 방법:
    pytest tests/test_llm_repository.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.exceptions import (
    LLMConnectionError,
    LLMContentFilterError,
    LLMRateLimitError,
    LLMResponseError,
)
from src.repositories.llm_repository import (
    LLMRepository,
    ModelTier,
    _classify_api_status_error,
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
            "node_labels": ["Employee", "Company"],
            "relationship_types": ["WORKS_AT", "KNOWS"],
        }
        result = repo._format_schema(schema)

        assert "Node Labels: Employee, Company" in result
        assert "Relationship Types: WORKS_AT, KNOWS" in result

    def test_format_schema_empty(self, repo):
        """빈 스키마 포맷팅"""
        result = repo._format_schema({})
        assert result == "Schema information not available"

    def test_format_schema_partial(self, repo):
        """부분 스키마 포맷팅"""
        schema = {"node_labels": ["Employee"]}
        result = repo._format_schema(schema)

        assert "Node Labels: Employee" in result
        assert "Relationship Types" not in result

    def test_format_schema_with_properties(self, repo):
        """속성 정보 포함 스키마 포맷팅"""
        schema = {
            "node_labels": ["Employee", "Project"],
            "relationship_types": ["WORKS_ON"],
            "nodes": [
                {
                    "label": "Employee",
                    "properties": [
                        {"name": "name"},
                        {"name": "department"},
                        {"name": "years_experience"},
                    ],
                },
                {
                    "label": "Project",
                    "properties": [
                        {"name": "name"},
                        {"name": "status"},
                        {"name": "budget_million"},
                    ],
                },
            ],
            "relationships": [
                {
                    "type": "WORKS_ON",
                    "properties": [
                        {"name": "role"},
                        {"name": "allocated_hours"},
                        {"name": "actual_hours"},
                    ],
                },
            ],
        }
        result = repo._format_schema(schema)

        # nodes 필드가 있으면 속성 포함 형식 사용
        assert "Employee (name, department, years_experience)" in result
        assert "Project (name, status, budget_million)" in result
        assert "WORKS_ON (role, allocated_hours, actual_hours)" in result
        # 기존 Node Labels 형식은 사용하지 않아야 함
        assert "Node Labels:" not in result

    def test_format_schema_with_properties_fallback(self, repo):
        """nodes 필드 없으면 기존 label 형식으로 fallback"""
        schema = {
            "node_labels": ["Employee", "Project"],
            "relationship_types": ["WORKS_ON"],
        }
        result = repo._format_schema(schema)

        assert "Node Labels: Employee, Project" in result
        assert "Relationship Types: WORKS_ON" in result

    def test_format_schema_with_empty_properties(self, repo):
        """속성이 빈 노드 스키마"""
        schema = {
            "nodes": [{"label": "Employee", "properties": []}],
            "relationships": [],
        }
        result = repo._format_schema(schema)
        assert "Employee" in result

    def test_format_entities_with_data(self, repo):
        """엔티티 포맷팅"""
        entities = [
            {"type": "Employee", "value": "홍길동", "normalized": "홍길동"},
            {"type": "Company", "value": "ABC회사", "normalized": "ABC"},
        ]
        result = repo._format_entities(entities)

        assert "Employee: 홍길동" in result
        assert "Company: ABC회사" in result

    def test_format_entities_empty(self, repo):
        """빈 엔티티 포맷팅"""
        result = repo._format_entities([])
        assert result == "No entities extracted"

    def test_format_entities_missing_fields(self, repo):
        """필드 누락 엔티티 포맷팅"""
        entities = [{"type": "Employee"}]
        result = repo._format_entities(entities)
        assert "Employee:" in result
        assert "Unknown" not in result

    def test_format_results_with_data(self, repo):
        """결과 포맷팅 - row 단위 노드 표현"""
        # _format_results는 Neo4j 노드 형식(labels 속성)을 기대함
        results = [
            {"n": {"id": 1, "labels": ["Employee"], "properties": {"name": "홍길동"}}},
            {"n": {"id": 2, "labels": ["Employee"], "properties": {"name": "김철수"}}},
        ]
        result = repo._format_results(results)

        # 노드 이름 + 라벨이 row 단위로 표시
        assert "홍길동" in result
        assert "김철수" in result
        assert "Employee" in result
        # 헤더 통계에 노드 개수 표시
        assert "Employee=2" in result
        # 총 행 수 표시
        assert "총 2행" in result

    def test_format_results_empty(self, repo):
        """빈 결과 포맷팅"""
        result = repo._format_results([])
        assert result == "No results found"

    def test_format_results_truncation(self, repo):
        """결과가 row 표시 한도(60) 초과 시 자르기"""
        # MAX_PAIR_ROWS = 60 (구현 상수와 일치)
        results = [
            {
                "n": {
                    "id": i + 1,
                    "labels": ["Node"],
                    "properties": {"name": f"Node{i + 1}"},
                }
            }
            for i in range(80)
        ]
        result = repo._format_results(results)

        # 전체 행 수는 통계로 표시
        assert "총 80행" in result
        assert "Node=80" in result
        # 60행 초과분은 "외 N개 행" 안내
        assert "외 20개 행" in result

    def test_format_results_scalar(self, repo):
        """스칼라(집계) 결과 포맷팅"""
        results = [
            {
                "employee": "김철수",
                "project": "챗봇 리뉴얼",
                "allocated": 100,
                "actual": 160,
                "gap": 60,
            },
            {
                "employee": "이영희",
                "project": "데이터레이크",
                "allocated": 80,
                "actual": 120,
                "gap": 40,
            },
            {
                "employee": "박지우",
                "project": "API 플랫폼",
                "allocated": 120,
                "actual": 130,
                "gap": 10,
            },
        ]
        result = repo._format_results(results)

        assert "집계 결과 (3행)" in result
        assert "employee=김철수" in result
        assert "gap=60" in result
        assert "employee=이영희" in result
        assert "employee=박지우" in result

    def test_format_results_scalar_truncation(self, repo):
        """스칼라 결과 30개 초과 시 자르기"""
        # 새 구현은 최대 30행까지 표시
        results = [{"name": f"Person{i}", "count": i} for i in range(35)]
        result = repo._format_results(results)

        assert "집계 결과 (35행)" in result
        assert "외 5개" in result

    def test_format_results_mixed(self, repo):
        """노드 + 스칼라 혼합 결과"""
        results = [
            # 노드 결과
            {"n": {"id": 1, "labels": ["Employee"], "properties": {"name": "김철수"}}},
            # 스칼라 결과
            {"total_count": 5, "avg_hours": 120.5},
        ]
        result = repo._format_results(results)

        # 노드 row 표시
        assert "김철수" in result
        assert "Employee" in result
        # 스칼라 집계 별도 표시
        assert "집계 결과 (1행)" in result
        assert "total_count=5" in result
        assert "avg_hours=120.5" in result

    def test_format_results_scalar_null_values(self, repo):
        """스칼라 결과에서 None 값 필터링"""
        results = [
            {"name": "김철수", "value": 10, "extra": None},
        ]
        result = repo._format_results(results)

        assert "name=김철수" in result
        assert "value=10" in result
        assert "extra" not in result

    def test_format_results_preserves_pairs_across_rows(self, repo):
        """
        회귀 방지 테스트 (2026-05-21): 각 row의 (노드, 관계, 노드) 페어가 보존되는지 검증

        Cypher: MATCH (e:Employee)-[r:HAS_SKILL]->(s:Skill) RETURN e, r, s
        같은 사람이 여러 스킬을 가져도 라벨별 합치기가 아닌 row 단위로 표시되어야 한다.
        """
        results = [
            {
                "e": {
                    "id": "n1",
                    "labels": ["Employee"],
                    "properties": {"name": "안시은"},
                },
                "r": {
                    "id": "r1",
                    "type": "HAS_SKILL",
                    "startNodeId": "n1",
                    "endNodeId": "n100",
                    "properties": {"proficiency": "고급"},
                },
                "s": {
                    "id": "n100",
                    "labels": ["Skill"],
                    "properties": {"name": "Pinecone"},
                },
            },
            {
                "e": {
                    "id": "n2",
                    "labels": ["Employee"],
                    "properties": {"name": "류채원"},
                },
                "r": {
                    "id": "r2",
                    "type": "HAS_SKILL",
                    "startNodeId": "n2",
                    "endNodeId": "n101",
                    "properties": {"proficiency": "중급"},
                },
                "s": {
                    "id": "n101",
                    "labels": ["Skill"],
                    "properties": {"name": "Kubeflow"},
                },
            },
            {
                # 같은 사람(안시은)이 다른 스킬을 가진 row — 페어가 분리되어야 함
                "e": {
                    "id": "n1",
                    "labels": ["Employee"],
                    "properties": {"name": "안시은"},
                },
                "r": {
                    "id": "r3",
                    "type": "HAS_SKILL",
                    "startNodeId": "n1",
                    "endNodeId": "n102",
                    "properties": {"proficiency": "초급"},
                },
                "s": {
                    "id": "n102",
                    "labels": ["Skill"],
                    "properties": {"name": "Angular"},
                },
            },
        ]
        result = repo._format_results(results)

        # 헤더: 노드 중복 제거된 카운트 (안시은 중복은 1로 카운트)
        assert "Employee=2" in result  # 안시은, 류채원 (안시은 2번 등장하지만 1로)
        assert "Skill=3" in result
        assert "HAS_SKILL=3" in result

        # row 단위 페어 보존 검증 — 각 사실이 분리된 row로 표시되어야 함
        lines = result.split("\n")
        row_lines = [line for line in lines if line.startswith(("1.", "2.", "3."))]
        assert len(row_lines) == 3

        # 페어 정확성: 안시은-Pinecone-고급, 류채원-Kubeflow-중급, 안시은-Angular-초급
        row1 = next(line for line in row_lines if line.startswith("1."))
        assert "안시은" in row1 and "Pinecone" in row1 and "고급" in row1

        row2 = next(line for line in row_lines if line.startswith("2."))
        assert "류채원" in row2 and "Kubeflow" in row2 and "중급" in row2

        row3 = next(line for line in row_lines if line.startswith("3."))
        assert "안시은" in row3 and "Angular" in row3 and "초급" in row3

        # 페어 손실 회귀 방지: 한 row에 두 스킬이 합쳐서 들어가면 안 됨
        assert "Pinecone, Kubeflow" not in result
        assert "Pinecone, Angular" not in result

    def test_format_results_skip_props_filtered(self, repo):
        """embedding/vector/id 같은 SKIP_PROPS는 LLM 프롬프트에서 제외"""
        results = [
            {
                "n": {
                    "id": "n1",
                    "labels": ["Employee"],
                    "properties": {
                        "name": "홍길동",
                        "department": "AI팀",
                        "embedding": [0.1, 0.2, 0.3],  # 노출 금지
                        "vector": [1, 2, 3],  # 노출 금지
                    },
                }
            }
        ]
        result = repo._format_results(results)

        assert "홍길동" in result
        assert "AI팀" in result
        # 임베딩/벡터 데이터는 LLM에 전달되지 않음
        assert "embedding" not in result
        assert "0.1" not in result
        assert "vector" not in result


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
        mapped = _classify_api_status_error(e)
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
        mapped = _classify_api_status_error(e)

        assert isinstance(mapped, LLMContentFilterError)
        assert mapped.param == "prompt"
        # filtered=True인 카테고리만 수집
        assert mapped.categories == {"self_harm": "medium"}

    def test_content_filter_handles_missing_body(self):
        """body가 None이어도 죽지 않음"""
        e = self._make_error(400, "content_filter", body=None)
        mapped = _classify_api_status_error(e)
        assert isinstance(mapped, LLMContentFilterError)
        assert mapped.categories == {}
        assert mapped.param is None

    def test_non_content_filter_400_returns_response_error(self):
        """status=400이지만 content_filter 아니면 일반 LLMResponseError"""
        e = self._make_error(400, "Invalid request: missing field")
        mapped = _classify_api_status_error(e)
        assert isinstance(mapped, LLMResponseError)
        assert not isinstance(mapped, LLMContentFilterError)

    def test_500_returns_response_error(self):
        """5xx 에러는 LLMResponseError"""
        e = self._make_error(500, "Internal server error")
        mapped = _classify_api_status_error(e)
        assert isinstance(mapped, LLMResponseError)

    def test_raw_message_not_exposed(self):
        """raw Azure 메시지는 사용자 노출되지 않음 (status code만)"""
        secret_msg = "Internal Azure trace: pod-xxx 디버그 정보 leaked"
        e = self._make_error(503, secret_msg)
        mapped = _classify_api_status_error(e)
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
        mock_response.choices[
            0
        ].message.content = '{"intent": "search", "confidence": 0.9}'

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
        mock_response.choices[
            0
        ].message.content = '{"entities": [{"type": "Employee", "value": "홍길동", "normalized": "홍길동"}]}'

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        repo._client = mock_client

        result = await repo.extract_entities(
            question="홍길동이 근무하는 회사는?",
            entity_types=["Employee", "Company"],
        )

        assert len(result["entities"]) == 1
        assert result["entities"][0]["type"] == "Employee"

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
        repo._client = mock_client

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
        repo._client = mock_client

        result = await repo.generate_response(
            question="홍길동이 어디서 일해?",
            query_results=[{"name": "홍길동", "company": "ABC"}],
            cypher_query="MATCH (p:Employee)-[:WORKS_AT]->(c:Company) RETURN p, c",
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
