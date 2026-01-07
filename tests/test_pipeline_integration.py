"""
Pipeline Integration Tests

파이프라인 전체 흐름을 검증하는 통합 테스트

실행 방법:
    pytest tests/test_pipeline_integration.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.config import Settings
from src.graph.pipeline import GraphRAGPipeline
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository


class TestPipelineRouting:
    """파이프라인 라우팅 로직 테스트"""

    @pytest.fixture
    def mock_settings(self):
        """Mock Settings"""
        settings = MagicMock(spec=Settings)
        settings.vector_search_enabled = False  # Vector cache 비활성화
        return settings

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM Repository"""
        llm = MagicMock(spec=LLMRepository)
        llm.classify_intent = AsyncMock()
        llm.extract_entities = AsyncMock()
        llm.generate_cypher = AsyncMock()
        llm.generate_response = AsyncMock()
        return llm

    @pytest.fixture
    def mock_neo4j(self):
        """Mock Neo4j Repository"""
        neo4j = MagicMock(spec=Neo4jRepository)
        neo4j.find_entities_by_name = AsyncMock(return_value=[])
        neo4j.get_schema = AsyncMock(return_value={
            "node_labels": ["Person"],
            "relationship_types": ["WORKS_AT"],
        })
        neo4j.execute_cypher = AsyncMock(return_value=[])
        return neo4j

    @pytest.fixture
    def pipeline(self, mock_settings, mock_neo4j, mock_llm):
        """테스트용 파이프라인"""
        return GraphRAGPipeline(mock_settings, mock_neo4j, mock_llm)

    @pytest.mark.asyncio
    async def test_unknown_intent_skips_to_response(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """Unknown intent 시 entity 추출 스킵"""
        mock_llm.classify_intent.return_value = {
            "intent": "unknown",
            "confidence": 0.0,
        }

        result = await pipeline.run("알 수 없는 질문")

        assert result["success"] is True
        path = result["metadata"]["execution_path"]
        assert "intent_classifier" in path
        assert "entity_extractor" not in path
        assert "response_generator_empty" in path

        # Entity extractor가 호출되지 않았는지 확인
        mock_llm.extract_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_cypher_error_skips_executor(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """Cypher 생성 에러 시 executor 스킵"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {"entities": []}
        mock_llm.generate_cypher.side_effect = Exception("Cypher Error")
        mock_llm.generate_response.return_value = "오류가 발생했습니다."

        result = await pipeline.run("에러 유발 질문")

        path = result["metadata"]["execution_path"]
        assert "cypher_generator_error" in path
        assert "graph_executor" not in path
        assert "response_generator_error_handler" in path

    @pytest.mark.asyncio
    async def test_normal_flow_all_nodes(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """정상 흐름 시 모든 노드 실행 (병렬 실행 포함)"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Person", "value": "홍길동"}]
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (p:Person {name: $name}) RETURN p",
            "parameters": {"name": "홍길동"},
        }
        mock_neo4j.execute_cypher.return_value = [
            {"p": {"name": "홍길동", "department": "개발팀"}}
        ]
        mock_llm.generate_response.return_value = "홍길동은 개발팀에서 근무합니다."

        result = await pipeline.run("홍길동의 부서는?")

        assert result["success"] is True
        path = result["metadata"]["execution_path"]

        # 병렬 실행 노드 포함
        expected_nodes = [
            "intent_classifier",
            "entity_extractor",
            "schema_fetcher",  # 병렬 실행
            "entity_resolver",
            "cypher_generator",
            "graph_executor",
            "response_generator",
        ]
        for node in expected_nodes:
            assert node in path, f"{node} not in path: {path}"

    @pytest.mark.asyncio
    async def test_parallel_execution(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """entity_extractor와 schema_fetcher 병렬 실행 확인"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {"entities": []}
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = []
        mock_llm.generate_response.return_value = "결과 없음"

        result = await pipeline.run("테스트 질문")

        path = result["metadata"]["execution_path"]

        # 병렬 실행된 노드들이 모두 경로에 포함되어야 함
        assert "entity_extractor" in path
        assert "schema_fetcher" in path

        # schema가 state에 저장되었는지 확인 (CypherGenerator에서 사용)
        # mock_neo4j.get_schema가 호출되었는지 확인
        mock_neo4j.get_schema.assert_called()


class TestPipelineMetadata:
    """파이프라인 메타데이터 테스트"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        settings.vector_search_enabled = False  # Vector cache 비활성화
        return settings

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock(spec=LLMRepository)
        llm.classify_intent = AsyncMock()
        llm.extract_entities = AsyncMock()
        llm.generate_cypher = AsyncMock()
        llm.generate_response = AsyncMock()
        return llm

    @pytest.fixture
    def mock_neo4j(self):
        neo4j = MagicMock(spec=Neo4jRepository)
        neo4j.find_entities_by_name = AsyncMock(return_value=[])
        neo4j.get_schema = AsyncMock(return_value={
            "node_labels": ["Person"],
            "relationship_types": ["WORKS_AT"],
        })
        neo4j.execute_cypher = AsyncMock(return_value=[])
        return neo4j

    @pytest.fixture
    def pipeline(self, mock_settings, mock_neo4j, mock_llm):
        return GraphRAGPipeline(mock_settings, mock_neo4j, mock_llm)

    @pytest.mark.asyncio
    async def test_metadata_includes_intent(self, pipeline, mock_llm, mock_neo4j):
        """메타데이터에 intent 정보 포함"""
        mock_llm.classify_intent.return_value = {
            "intent": "org_analysis",  # 유효한 IntentType 사용
            "confidence": 0.85,
        }
        mock_llm.extract_entities.return_value = {"entities": []}
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (o:Organization) RETURN o",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = []
        mock_llm.generate_response.return_value = "조직 정보를 찾지 못했습니다."

        result = await pipeline.run("개발팀 정보 알려줘")

        assert result["metadata"]["intent"] == "org_analysis"
        assert result["metadata"]["intent_confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_metadata_includes_entities(self, pipeline, mock_llm, mock_neo4j):
        """메타데이터에 엔티티 정보 포함"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {
            "entities": [
                {"type": "Person", "value": "김철수"},
                {"type": "Department", "value": "인사팀"},
            ]
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (p:Person)-[:BELONGS_TO]->(d:Department) RETURN p, d",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = []
        mock_llm.generate_response.return_value = "결과 없음"

        result = await pipeline.run("김철수가 인사팀 소속인가요?")

        entities = result["metadata"]["entities"]
        assert len(entities) == 2

    @pytest.mark.asyncio
    async def test_metadata_includes_cypher(self, pipeline, mock_llm, mock_neo4j):
        """메타데이터에 Cypher 쿼리 포함"""
        expected_cypher = "MATCH (p:Person {name: $name}) RETURN p"

        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {"entities": []}
        mock_llm.generate_cypher.return_value = {
            "cypher": expected_cypher,
            "parameters": {"name": "테스트"},
        }
        mock_neo4j.execute_cypher.return_value = []
        mock_llm.generate_response.return_value = "결과 없음"

        result = await pipeline.run("테스트 검색")

        assert result["metadata"]["cypher_query"] == expected_cypher
        assert result["metadata"]["cypher_parameters"] == {"name": "테스트"}


class TestPipelineErrorHandling:
    """파이프라인 에러 처리 테스트"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        settings.vector_search_enabled = False  # Vector cache 비활성화
        return settings

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock(spec=LLMRepository)
        llm.classify_intent = AsyncMock()
        llm.extract_entities = AsyncMock()
        llm.generate_cypher = AsyncMock()
        llm.generate_response = AsyncMock()
        return llm

    @pytest.fixture
    def mock_neo4j(self):
        neo4j = MagicMock(spec=Neo4jRepository)
        neo4j.find_entities_by_name = AsyncMock(return_value=[])
        neo4j.get_schema = AsyncMock(return_value={
            "node_labels": ["Person"],
            "relationship_types": ["WORKS_AT"],
        })
        neo4j.execute_cypher = AsyncMock(return_value=[])
        return neo4j

    @pytest.fixture
    def pipeline(self, mock_settings, mock_neo4j, mock_llm):
        return GraphRAGPipeline(mock_settings, mock_neo4j, mock_llm)

    @pytest.mark.asyncio
    async def test_intent_classifier_error(self, pipeline, mock_llm):
        """Intent classifier 에러 시 graceful 처리 (fallback to unknown)"""
        mock_llm.classify_intent.side_effect = Exception("LLM 연결 실패")

        result = await pipeline.run("테스트 질문")

        # IntentClassifier는 에러 시 unknown으로 fallback하므로 파이프라인은 계속 진행
        # 최종 응답은 success=True지만 intent가 unknown임
        assert result["metadata"]["intent"] == "unknown"
        path = result["metadata"]["execution_path"]
        assert "intent_classifier_error" in path or "intent_classifier" in path

    @pytest.mark.asyncio
    async def test_entity_extractor_error(self, pipeline, mock_llm, mock_neo4j):
        """Entity extractor 에러 시 graceful 처리"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.side_effect = Exception("Entity 추출 실패")

        result = await pipeline.run("테스트 질문")

        # 에러가 발생해도 파이프라인이 중단되지 않음
        assert result["success"] is False or result["metadata"].get("error")

    @pytest.mark.asyncio
    async def test_graph_executor_error(self, pipeline, mock_llm, mock_neo4j):
        """Graph executor 에러 시 graceful 처리"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {"entities": []}
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.side_effect = Exception("DB 연결 실패")
        mock_llm.generate_response.return_value = "DB 오류가 발생했습니다."

        result = await pipeline.run("테스트 질문")

        path = result["metadata"]["execution_path"]
        assert "graph_executor_error" in path
        assert "response_generator_error_handler" in path


class TestPipelineStreaming:
    """파이프라인 스트리밍 모드 테스트"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        settings.vector_search_enabled = False  # Vector cache 비활성화
        return settings

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock(spec=LLMRepository)
        llm.classify_intent = AsyncMock()
        llm.extract_entities = AsyncMock()
        llm.generate_cypher = AsyncMock()
        llm.generate_response = AsyncMock()
        return llm

    @pytest.fixture
    def mock_neo4j(self):
        neo4j = MagicMock(spec=Neo4jRepository)
        neo4j.find_entities_by_name = AsyncMock(return_value=[])
        neo4j.get_schema = AsyncMock(return_value={
            "node_labels": ["Person"],
            "relationship_types": ["WORKS_AT"],
        })
        neo4j.execute_cypher = AsyncMock(return_value=[])
        return neo4j

    @pytest.fixture
    def pipeline(self, mock_settings, mock_neo4j, mock_llm):
        return GraphRAGPipeline(mock_settings, mock_neo4j, mock_llm)

    @pytest.mark.asyncio
    async def test_streaming_yields_events(self, pipeline, mock_llm, mock_neo4j):
        """스트리밍 모드에서 각 노드 이벤트 yield"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {"entities": []}
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = [{"n": "test"}]
        mock_llm.generate_response.return_value = "테스트 응답"

        events = []
        async for event in pipeline.run_with_streaming("테스트 질문"):
            events.append(event)

        # 최소한 몇 개의 이벤트가 발생해야 함
        assert len(events) > 0

        # 각 이벤트에 node와 output이 있어야 함
        for event in events:
            assert "node" in event
            assert "output" in event


class TestPipelineEmptyResults:
    """빈 결과 처리 테스트"""

    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        settings.vector_search_enabled = False  # Vector cache 비활성화
        return settings

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock(spec=LLMRepository)
        llm.classify_intent = AsyncMock()
        llm.extract_entities = AsyncMock()
        llm.generate_cypher = AsyncMock()
        llm.generate_response = AsyncMock()
        return llm

    @pytest.fixture
    def mock_neo4j(self):
        neo4j = MagicMock(spec=Neo4jRepository)
        neo4j.find_entities_by_name = AsyncMock(return_value=[])
        neo4j.get_schema = AsyncMock(return_value={
            "node_labels": ["Person"],
            "relationship_types": ["WORKS_AT"],
        })
        neo4j.execute_cypher = AsyncMock(return_value=[])
        return neo4j

    @pytest.fixture
    def pipeline(self, mock_settings, mock_neo4j, mock_llm):
        return GraphRAGPipeline(mock_settings, mock_neo4j, mock_llm)

    @pytest.mark.asyncio
    async def test_empty_query_results(self, pipeline, mock_llm, mock_neo4j):
        """쿼리 결과가 비어있는 경우"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Person", "value": "존재하지않는사람"}]
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (p:Person {name: $name}) RETURN p",
            "parameters": {"name": "존재하지않는사람"},
        }
        mock_neo4j.execute_cypher.return_value = []  # 빈 결과
        mock_llm.generate_response.return_value = "해당 인물을 찾을 수 없습니다."

        result = await pipeline.run("존재하지않는사람 찾아줘")

        assert result["success"] is True
        assert result["metadata"]["result_count"] == 0
        # response_generator 또는 response_generator_empty가 포함되어야 함
        path = result["metadata"]["execution_path"]
        assert any("response_generator" in node for node in path)

    @pytest.mark.asyncio
    async def test_no_entities_extracted(self, pipeline, mock_llm, mock_neo4j):
        """엔티티가 추출되지 않은 경우"""
        mock_llm.classify_intent.return_value = {
            "intent": "relationship_search",  # 유효한 IntentType 사용
            "confidence": 0.7,
        }
        mock_llm.extract_entities.return_value = {"entities": []}  # 빈 엔티티
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n LIMIT 10",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = [{"n": "data"}]
        mock_llm.generate_response.return_value = "검색 결과입니다."

        result = await pipeline.run("모든 데이터 보여줘")

        assert result["success"] is True
        # 엔티티가 없어도 파이프라인은 계속 진행
        assert "cypher_generator" in result["metadata"]["execution_path"]
