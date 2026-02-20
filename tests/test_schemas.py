"""
API Schemas 단위 테스트

실행 방법:
    pytest tests/test_schemas.py -v
"""

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    HealthResponse,
    QueryMetadata,
    QueryRequest,
    QueryResponse,
    SchemaResponse,
)


class TestQueryRequest:
    """QueryRequest 스키마 테스트"""

    def test_valid_request(self):
        """유효한 요청"""
        request = QueryRequest(question="홍길동의 부서는?")
        assert request.question == "홍길동의 부서는?"
        assert request.session_id is None

    def test_request_with_session(self):
        """세션 ID 포함 요청"""
        request = QueryRequest(
            question="테스트 질문",
            session_id="session-123",
        )
        assert request.session_id == "session-123"

    def test_empty_question_rejected(self):
        """빈 질문 거부"""
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question="")
        assert "min_length" in str(exc_info.value) or "at least 1" in str(
            exc_info.value
        )

    def test_question_max_length(self):
        """질문 최대 길이 검증"""
        long_question = "가" * 1001
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question=long_question)
        assert "max_length" in str(exc_info.value) or "at most 1000" in str(
            exc_info.value
        )

    def test_question_at_max_length(self):
        """질문 최대 길이 경계값"""
        question = "가" * 1000
        request = QueryRequest(question=question)
        assert len(request.question) == 1000

    def test_question_required(self):
        """질문 필수 검증"""
        with pytest.raises(ValidationError):
            QueryRequest()


class TestQueryMetadata:
    """QueryMetadata 스키마 테스트"""

    def test_full_metadata(self):
        """전체 메타데이터"""
        metadata = QueryMetadata(
            intent="personnel_search",
            intent_confidence=0.95,
            entities={"Employee": ["홍길동"]},  # dict[str, list[str]] 형식
            resolved_entities=[{"id": 1, "name": "홍길동"}],
            cypher_query="MATCH (p:Employee) RETURN p",
            cypher_parameters={"name": "홍길동"},
            result_count=5,
            execution_path=["intent_classifier", "entity_extractor"],
        )
        assert metadata.intent == "personnel_search"
        assert metadata.intent_confidence == 0.95
        assert len(metadata.entities) == 1
        assert metadata.entities["Employee"] == ["홍길동"]
        assert metadata.result_count == 5

    def test_minimal_metadata(self):
        """최소 메타데이터"""
        metadata = QueryMetadata(
            intent="unknown",
            intent_confidence=0.0,
        )
        assert metadata.entities == {}
        assert metadata.resolved_entities == []
        assert metadata.cypher_query == ""
        assert metadata.result_count == 0

    def test_metadata_defaults(self):
        """기본값 테스트"""
        metadata = QueryMetadata(
            intent="test",
            intent_confidence=0.5,
        )
        assert metadata.entities == {}
        assert metadata.cypher_parameters == {}
        assert metadata.execution_path == []


class TestQueryResponse:
    """QueryResponse 스키마 테스트"""

    def test_success_response(self):
        """성공 응답"""
        response = QueryResponse(
            success=True,
            question="홍길동 찾아줘",
            response="홍길동을 찾았습니다.",
        )
        assert response.success is True
        assert response.error is None
        assert response.metadata is None

    def test_success_with_metadata(self):
        """메타데이터 포함 성공 응답"""
        metadata = QueryMetadata(
            intent="personnel_search",
            intent_confidence=0.9,
        )
        response = QueryResponse(
            success=True,
            question="홍길동 찾아줘",
            response="홍길동을 찾았습니다.",
            metadata=metadata,
        )
        assert response.metadata is not None
        assert response.metadata.intent == "personnel_search"

    def test_error_response(self):
        """에러 응답"""
        response = QueryResponse(
            success=False,
            question="잘못된 질문",
            response="",
            error="처리 중 오류가 발생했습니다.",
        )
        assert response.success is False
        assert response.error is not None

    def test_required_fields(self):
        """필수 필드 검증"""
        with pytest.raises(ValidationError):
            QueryResponse(success=True)  # question, response 누락


class TestHealthResponse:
    """HealthResponse 스키마 테스트"""

    def test_healthy_response(self):
        """정상 상태 응답"""
        response = HealthResponse(
            status="healthy",
            version="0.1.0",
            neo4j_connected=True,
            neo4j_info={"address": "localhost:7687"},
        )
        assert response.status == "healthy"
        assert response.neo4j_connected is True

    def test_degraded_response(self):
        """저하 상태 응답"""
        response = HealthResponse(
            status="degraded",
            version="0.1.0",
            neo4j_connected=False,
        )
        assert response.status == "degraded"
        assert response.neo4j_info is None

    def test_required_fields(self):
        """필수 필드 검증"""
        with pytest.raises(ValidationError):
            HealthResponse(status="healthy")  # version, neo4j_connected 누락


class TestSchemaResponse:
    """SchemaResponse 스키마 테스트"""

    def test_full_schema(self):
        """전체 스키마 응답"""
        response = SchemaResponse(
            node_labels=["Employee", "Company"],
            relationship_types=["WORKS_AT", "KNOWS"],
            indexes=[{"name": "idx1", "type": "BTREE"}],
            constraints=[{"name": "const1", "type": "UNIQUE"}],
        )
        assert len(response.node_labels) == 2
        assert len(response.relationship_types) == 2
        assert len(response.indexes) == 1
        assert len(response.constraints) == 1

    def test_empty_schema(self):
        """빈 스키마 응답"""
        response = SchemaResponse()
        assert response.node_labels == []
        assert response.relationship_types == []
        assert response.indexes == []
        assert response.constraints == []

    def test_partial_schema(self):
        """부분 스키마 응답"""
        response = SchemaResponse(node_labels=["Employee"])
        assert response.node_labels == ["Employee"]
        assert response.relationship_types == []


class TestSchemaJsonSerialization:
    """JSON 직렬화 테스트"""

    def test_query_request_to_json(self):
        """QueryRequest JSON 직렬화"""
        request = QueryRequest(question="테스트", session_id="123")
        json_data = request.model_dump()

        assert json_data["question"] == "테스트"
        assert json_data["session_id"] == "123"

    def test_query_response_to_json(self):
        """QueryResponse JSON 직렬화"""
        response = QueryResponse(
            success=True,
            question="테스트",
            response="응답",
            metadata=QueryMetadata(intent="test", intent_confidence=0.5),
        )
        json_data = response.model_dump()

        assert json_data["success"] is True
        assert json_data["metadata"]["intent"] == "test"

    def test_round_trip_serialization(self):
        """직렬화-역직렬화 왕복"""
        original = QueryResponse(
            success=True,
            question="원본 질문",
            response="원본 응답",
            metadata=QueryMetadata(
                intent="personnel_search",
                intent_confidence=0.95,
                entities={"Employee": ["홍길동"]},  # dict[str, list[str]] 형식
            ),
        )

        # 직렬화
        json_data = original.model_dump()

        # 역직렬화
        restored = QueryResponse.model_validate(json_data)

        assert restored.question == original.question
        assert restored.metadata.intent == original.metadata.intent
        assert restored.metadata.entities == original.metadata.entities
