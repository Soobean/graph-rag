"""
Query API Explainability 테스트

/api/v1/query 엔드포인트의 Explainability 기능 테스트

실행 방법:
    pytest tests/test_query_api_explainability.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from src.api.routes.query import router
from src.api.schemas.query import QueryResponse
from src.config import Settings
from src.graph import GraphRAGPipeline


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    settings = MagicMock(spec=Settings)
    settings.vector_search_enabled = False
    settings.app_version = "0.1.0-test"
    return settings


@pytest.fixture
def mock_pipeline():
    """Mock GraphRAGPipeline"""
    pipeline = MagicMock(spec=GraphRAGPipeline)
    pipeline.run = AsyncMock()
    return pipeline


@pytest.fixture
def app(mock_pipeline, mock_settings):
    """테스트용 FastAPI 앱"""
    test_app = FastAPI()
    test_app.include_router(router)

    # 의존성 오버라이드
    from src.dependencies import get_graph_pipeline

    test_app.dependency_overrides[get_graph_pipeline] = lambda: mock_pipeline

    return test_app


@pytest.fixture
def client(app):
    """동기 테스트 클라이언트"""
    return TestClient(app)


@pytest.fixture
async def async_client(app):
    """비동기 테스트 클라이언트"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


class TestQueryEndpointBasic:
    """Query 엔드포인트 기본 테스트"""

    def test_query_without_explanation(self, client, mock_pipeline):
        """explanation 없이 쿼리"""
        mock_pipeline.run.return_value = {
            "success": True,
            "question": "테스트 질문",
            "response": "테스트 응답",
            "metadata": {
                "intent": "personnel_search",
                "intent_confidence": 0.9,
                "entities": {},
                "resolved_entities": [],
                "cypher_query": "",
                "cypher_parameters": {},
                "result_count": 0,
                "execution_path": ["intent_classifier"],
            },
            "error": None,
        }

        response = client.post(
            "/api/v1/query",
            json={"question": "테스트 질문"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["explanation"] is None

        # return_full_state=False로 호출됨
        mock_pipeline.run.assert_called_once()
        call_kwargs = mock_pipeline.run.call_args.kwargs
        assert call_kwargs.get("return_full_state", False) is False


class TestQueryEndpointWithExplanation:
    """Query 엔드포인트 Explanation 테스트"""

    def test_query_with_include_explanation(self, client, mock_pipeline):
        """include_explanation=True 요청"""
        mock_pipeline.run.return_value = {
            "success": True,
            "question": "Python 개발자 찾아줘",
            "response": "홍길동을 찾았습니다.",
            "metadata": {
                "intent": "personnel_search",
                "intent_confidence": 0.92,
                "entities": {"Skill": ["Python"]},
                "resolved_entities": [],
                "cypher_query": "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill) RETURN e",
                "cypher_parameters": {},
                "result_count": 1,
                "execution_path": [
                    "intent_classifier",
                    "entity_extractor",
                    "concept_expander",
                    "entity_resolver",
                    "cypher_generator",
                    "graph_executor",
                    "response_generator",
                ],
                "_full_state": {
                    "original_entities": {"Skill": ["Python"]},
                    "expanded_entities": {"Skill": ["Python", "Django"]},
                    "expansion_strategy": "normal",
                    "expansion_count": 1,
                    "graph_results": [],
                },
            },
            "error": None,
        }

        response = client.post(
            "/api/v1/query",
            json={
                "question": "Python 개발자 찾아줘",
                "include_explanation": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # explanation 필드 확인
        assert data["explanation"] is not None
        assert data["explanation"]["thought_process"] is not None

        # 스텝 확인
        steps = data["explanation"]["thought_process"]["steps"]
        assert len(steps) > 0

        # intent_classifier 스텝 찾기
        intent_step = next(
            (s for s in steps if s["node_name"] == "intent_classifier"),
            None,
        )
        assert intent_step is not None
        assert "92%" in intent_step["output_summary"]

        # concept_expander 스텝 찾기
        expander_step = next(
            (s for s in steps if s["node_name"] == "concept_expander"),
            None,
        )
        assert expander_step is not None
        assert "normal" in expander_step["output_summary"]

    def test_query_with_include_graph(self, client, mock_pipeline):
        """include_graph=True 요청"""
        mock_pipeline.run.return_value = {
            "success": True,
            "question": "Python 개발자",
            "response": "찾았습니다",
            "metadata": {
                "intent": "personnel_search",
                "intent_confidence": 0.9,
                "entities": {"Skill": ["Python"]},
                "resolved_entities": [
                    {
                        "id": 1,
                        "labels": ["Skill"],
                        "name": "Python",
                        "properties": {},
                    }
                ],
                "cypher_query": "MATCH (e) RETURN e",
                "cypher_parameters": {},
                "result_count": 2,
                "execution_path": ["intent_classifier", "response_generator"],
                "_full_state": {
                    "original_entities": {"Skill": ["Python"]},
                    "expanded_entities": {"Skill": ["Python"]},
                    "expansion_strategy": "normal",
                    "expansion_count": 0,
                    "graph_results": [
                        {
                            "e": {
                                "id": 100,
                                "labels": ["Employee"],
                                "properties": {"name": "홍길동"},
                            }
                        },
                    ],
                },
            },
            "error": None,
        }

        response = client.post(
            "/api/v1/query",
            json={
                "question": "Python 개발자",
                "include_graph": True,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # graph_data 확인
        assert data["explanation"] is not None
        assert data["explanation"]["graph_data"] is not None

        graph = data["explanation"]["graph_data"]
        assert "nodes" in graph
        assert "edges" in graph
        assert "query_entity_ids" in graph
        assert "result_entity_ids" in graph

    def test_query_with_both_explanation_and_graph(self, client, mock_pipeline):
        """include_explanation=True, include_graph=True 요청"""
        mock_pipeline.run.return_value = {
            "success": True,
            "question": "테스트",
            "response": "응답",
            "metadata": {
                "intent": "personnel_search",
                "intent_confidence": 0.9,
                "entities": {},
                "resolved_entities": [],
                "cypher_query": "",
                "cypher_parameters": {},
                "result_count": 0,
                "execution_path": ["intent_classifier"],
                "_full_state": {
                    "original_entities": {},
                    "expanded_entities": {},
                    "expansion_strategy": "normal",
                    "expansion_count": 0,
                    "graph_results": [],
                },
            },
            "error": None,
        }

        response = client.post(
            "/api/v1/query",
            json={
                "question": "테스트",
                "include_explanation": True,
                "include_graph": True,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # 둘 다 포함 확인
        assert data["explanation"]["thought_process"] is not None
        assert data["explanation"]["graph_data"] is not None


class TestQueryEndpointGraphLimit:
    """Query 엔드포인트 graph_limit 테스트"""

    def test_graph_limit_passed_to_service(self, client, mock_pipeline):
        """graph_limit이 서비스에 전달됨"""
        mock_pipeline.run.return_value = {
            "success": True,
            "question": "테스트",
            "response": "응답",
            "metadata": {
                "intent": "personnel_search",
                "intent_confidence": 0.9,
                "entities": {},
                "resolved_entities": [],
                "cypher_query": "",
                "cypher_parameters": {},
                "result_count": 0,
                "execution_path": [],
                "_full_state": {
                    "original_entities": {},
                    "expanded_entities": {},
                    "expansion_strategy": "normal",
                    "expansion_count": 0,
                    "graph_results": [],
                },
            },
            "error": None,
        }

        response = client.post(
            "/api/v1/query",
            json={
                "question": "테스트",
                "include_graph": True,
                "graph_limit": 100,
            },
        )

        assert response.status_code == 200


class TestQueryEndpointValidation:
    """Query 엔드포인트 검증 테스트"""

    def test_graph_limit_min_validation(self, client):
        """graph_limit 최소값 검증"""
        response = client.post(
            "/api/v1/query",
            json={
                "question": "테스트",
                "graph_limit": 0,
            },
        )

        assert response.status_code == 422  # Validation Error

    def test_graph_limit_max_validation(self, client):
        """graph_limit 최대값 검증"""
        response = client.post(
            "/api/v1/query",
            json={
                "question": "테스트",
                "graph_limit": 201,
            },
        )

        assert response.status_code == 422  # Validation Error


class TestQueryEndpointBackwardCompatibility:
    """Query 엔드포인트 하위 호환성 테스트"""

    def test_old_request_format_still_works(self, client, mock_pipeline):
        """기존 요청 형식이 여전히 동작"""
        mock_pipeline.run.return_value = {
            "success": True,
            "question": "홍길동 찾아줘",
            "response": "홍길동을 찾았습니다.",
            "metadata": {
                "intent": "personnel_search",
                "intent_confidence": 0.9,
                "entities": {},
                "resolved_entities": [],
                "cypher_query": "",
                "cypher_parameters": {},
                "result_count": 1,
                "execution_path": [],
            },
            "error": None,
        }

        # 기존 형식 (explanation 옵션 없음)
        response = client.post(
            "/api/v1/query",
            json={"question": "홍길동 찾아줘"},
        )

        assert response.status_code == 200
        data = response.json()

        # 기존 필드들 확인
        assert "success" in data
        assert "question" in data
        assert "response" in data
        assert "metadata" in data

        # explanation은 None
        assert data["explanation"] is None


class TestQueryEndpointConceptExpansions:
    """Query 엔드포인트 개념 확장 테스트"""

    def test_concept_expansions_in_thought_process(self, client, mock_pipeline):
        """thought_process에 개념 확장 트리 포함"""
        mock_pipeline.run.return_value = {
            "success": True,
            "question": "파이썬 개발자",
            "response": "찾았습니다",
            "metadata": {
                "intent": "personnel_search",
                "intent_confidence": 0.9,
                "entities": {"Skill": ["파이썬"]},
                "resolved_entities": [],
                "cypher_query": "",
                "cypher_parameters": {},
                "result_count": 0,
                "execution_path": ["concept_expander"],
                "_full_state": {
                    "original_entities": {"Skill": ["파이썬"]},
                    "expanded_entities": {"Skill": ["파이썬", "Python", "Django", "FastAPI"]},
                    "expansion_strategy": "normal",
                    "expansion_count": 3,
                    "graph_results": [],
                },
            },
            "error": None,
        }

        response = client.post(
            "/api/v1/query",
            json={
                "question": "파이썬 개발자",
                "include_explanation": True,
            },
        )

        assert response.status_code == 200
        data = response.json()

        thought_process = data["explanation"]["thought_process"]
        concept_expansions = thought_process["concept_expansions"]

        # 개념 확장 트리가 있어야 함
        assert len(concept_expansions) > 0

        expansion = concept_expansions[0]
        assert expansion["original_concept"] == "파이썬"
        assert "Python" in expansion["expanded_concepts"]
        assert expansion["expansion_strategy"] == "normal"


class TestAsyncQueryEndpoint:
    """비동기 Query 엔드포인트 테스트"""

    @pytest.mark.asyncio
    async def test_async_query_with_explanation(self, async_client, mock_pipeline):
        """비동기 클라이언트로 explanation 요청"""
        mock_pipeline.run.return_value = {
            "success": True,
            "question": "테스트",
            "response": "응답",
            "metadata": {
                "intent": "test",
                "intent_confidence": 0.8,
                "entities": {},
                "resolved_entities": [],
                "cypher_query": "",
                "cypher_parameters": {},
                "result_count": 0,
                "execution_path": ["intent_classifier"],
                "_full_state": {
                    "original_entities": {},
                    "expanded_entities": {},
                    "expansion_strategy": "normal",
                    "expansion_count": 0,
                    "graph_results": [],
                },
            },
            "error": None,
        }

        response = await async_client.post(
            "/api/v1/query",
            json={
                "question": "테스트",
                "include_explanation": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["explanation"] is not None
