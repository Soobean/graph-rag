"""
Pipeline Integration Tests

파이프라인 전체 흐름을 검증하는 통합 테스트

실행 방법:
    pytest tests/test_pipeline_integration.py -v

Note:
    공통 fixture (mock_settings, mock_llm, mock_neo4j, graph_schema, pipeline)는
    tests/conftest.py에 정의되어 있습니다.

    Latency Optimization으로 IntentEntityExtractorNode가 사용됩니다.
    (기존 IntentClassifier + EntityExtractor 통합)
"""

import pytest


class TestPipelineRouting:
    """파이프라인 라우팅 로직 테스트"""

    @pytest.mark.asyncio
    async def test_unknown_intent_skips_to_response(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """Unknown intent 시 나머지 노드 스킵"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "unknown",
            "confidence": 0.0,
            "entities": [],
        }

        result = await pipeline.run("알 수 없는 질문")

        assert result["success"] is True
        path = result["metadata"]["execution_path"]
        assert "intent_entity_extractor" in path
        assert "cypher_generator" not in path
        assert "response_generator_empty" in path

    @pytest.mark.asyncio
    async def test_cypher_error_skips_executor(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """Cypher 생성 에러 시 executor 스킵"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [],
        }
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
        """정상 흐름 시 모든 노드 실행 (순차 실행)"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [{"type": "Person", "value": "홍길동", "normalized": "홍길동"}],
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

        # 순차 실행 노드 (IntentEntityExtractor가 intent + entity 통합 처리)
        expected_nodes = [
            "intent_entity_extractor",
            "entity_resolver",
            "cypher_generator",
            "graph_executor",
            "response_generator",
        ]
        for node in expected_nodes:
            assert node in path, f"{node} not in path: {path}"


class TestPipelineMetadata:
    """파이프라인 메타데이터 테스트"""

    @pytest.mark.asyncio
    async def test_metadata_includes_intent(self, pipeline, mock_llm, mock_neo4j):
        """메타데이터에 intent 정보 포함"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "org_analysis",
            "confidence": 0.85,
            "entities": [],
        }
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
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [
                {"type": "Person", "value": "김철수", "normalized": "김철수"},
                {"type": "Department", "value": "인사팀", "normalized": "인사팀"},
            ],
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (p:Person)-[:BELONGS_TO]->(d:Department) RETURN p, d",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = []
        mock_llm.generate_response.return_value = "결과 없음"

        result = await pipeline.run("김철수가 인사팀 소속인가요?")

        entities = result["metadata"]["entities"]
        # IntentEntityExtractor는 dict[str, list[str]] 형태로 반환
        assert "Person" in entities or "Department" in entities

    @pytest.mark.asyncio
    async def test_metadata_includes_cypher(self, pipeline, mock_llm, mock_neo4j):
        """메타데이터에 Cypher 쿼리 포함"""
        expected_cypher = "MATCH (p:Person {name: $name}) RETURN p"

        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [],
        }
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

    @pytest.mark.asyncio
    async def test_intent_entity_extractor_error(self, pipeline, mock_llm):
        """IntentEntityExtractor 에러 시 graceful 처리 (fallback to unknown)"""
        mock_llm.classify_intent_and_extract_entities.side_effect = Exception(
            "LLM 연결 실패"
        )

        result = await pipeline.run("테스트 질문")

        # IntentEntityExtractor는 에러 시 unknown으로 fallback하므로 파이프라인은 계속 진행
        assert result["metadata"]["intent"] == "unknown"
        path = result["metadata"]["execution_path"]
        assert (
            "intent_entity_extractor_error" in path
            or "intent_entity_extractor" in path
        )

    @pytest.mark.asyncio
    async def test_graph_executor_error(self, pipeline, mock_llm, mock_neo4j):
        """Graph executor 에러 시 graceful 처리"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [],
        }
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

    @pytest.mark.asyncio
    async def test_streaming_yields_events(self, pipeline, mock_llm, mock_neo4j):
        """스트리밍 모드에서 각 노드 이벤트 yield"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [],
        }
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

    @pytest.mark.asyncio
    async def test_empty_query_results(self, pipeline, mock_llm, mock_neo4j):
        """쿼리 결과가 비어있는 경우"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [
                {"type": "Person", "value": "존재하지않는사람", "normalized": "존재하지않는사람"}
            ],
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
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "relationship_search",
            "confidence": 0.7,
            "entities": [],  # 빈 엔티티
        }
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


class TestOntologyUpdateRouting:
    """사용자 주도 온톨로지 업데이트 라우팅 테스트"""

    @pytest.mark.asyncio
    async def test_ontology_update_routes_to_handler(
        self, pipeline_with_ontology, mock_llm, mock_neo4j
    ):
        """ontology_update intent 시 ontology_update_handler로 라우팅"""
        # Intent를 ontology_update로 설정
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "ontology_update",
            "confidence": 0.95,
            "entities": [],
        }
        # LLM 파싱 결과 설정
        mock_llm.generate_json.return_value = {
            "action": "add_concept",
            "term": "LangGraph",
            "category": "Skill",
            "canonical": None,
            "relation_type": None,
            "target_term": None,
            "parent": "Framework",
            "confidence": 0.92,
            "reasoning": "LangGraph는 AI 프레임워크입니다",
        }

        result = await pipeline_with_ontology.run("LangGraph를 스킬로 추가해줘")

        assert result["success"] is True
        path = result["metadata"]["execution_path"]

        # ontology_update_handler로 라우팅됨
        assert "ontology_update_handler" in path
        # 기존 쿼리 파이프라인은 스킵됨
        assert "cypher_generator" not in path
        assert "graph_executor" not in path

    @pytest.mark.asyncio
    async def test_ontology_update_add_synonym(
        self, pipeline_with_ontology, mock_llm, mock_neo4j, mock_ontology_service
    ):
        """동의어 추가 요청 처리"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "ontology_update",
            "confidence": 0.92,
            "entities": [],
        }
        mock_llm.generate_json.return_value = {
            "action": "add_synonym",
            "term": "ReactJS",
            "category": "Skill",
            "canonical": "React",
            "relation_type": "SAME_AS",
            "target_term": "React",
            "parent": None,
            "confidence": 0.88,
            "reasoning": "ReactJS는 React의 다른 이름입니다",
        }

        # 승인 결과 설정
        from datetime import UTC, datetime
        from src.domain.adaptive.models import OntologyProposal, ProposalStatus, ProposalType

        mock_ontology_service.approve_proposal.return_value = OntologyProposal(
            proposal_type=ProposalType.NEW_SYNONYM,
            term="ReactJS",
            category="skills",
            suggested_action="test",
            suggested_canonical="React",
            status=ProposalStatus.APPROVED,
            applied_at=datetime.now(UTC),
        )

        result = await pipeline_with_ontology.run("ReactJS와 React는 같은 거야")

        assert result["success"] is True
        path = result["metadata"]["execution_path"]
        # ontology_update_handler 또는 ontology_update_handler_pending이 있어야 함
        assert any("ontology_update_handler" in node for node in path)
        # 응답에 관련 텍스트가 있어야 함 (동의어, 등록, 추가, 접수 등)
        response = result["response"]
        assert any(
            keyword in response for keyword in ["동의어", "등록", "추가", "접수", "적용"]
        )

    @pytest.mark.asyncio
    async def test_ontology_update_without_service_fallback(
        self, pipeline, mock_llm
    ):
        """OntologyService 없는 pipeline에서 ontology_update intent 처리"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "ontology_update",
            "confidence": 0.9,
            "entities": [],
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n LIMIT 1",
            "parameters": {},
        }
        mock_llm.generate_response.return_value = "쿼리 결과입니다."

        result = await pipeline.run("LangGraph를 스킬로 추가해줘")

        # OntologyService가 없으면 query_decomposer로 fallback (기존 쿼리 파이프라인 진행)
        path = result["metadata"]["execution_path"]
        assert "ontology_update_handler" not in path
        # query_decomposer 또는 query_decomposer_skipped가 있어야 함
        assert any("query_decomposer" in node for node in path)

    @pytest.mark.asyncio
    async def test_ontology_update_low_confidence_response(
        self, pipeline_with_ontology, mock_llm
    ):
        """낮은 신뢰도 파싱 시 명확화 요청"""
        mock_llm.classify_intent_and_extract_entities.return_value = {
            "intent": "ontology_update",
            "confidence": 0.85,
            "entities": [],
        }
        mock_llm.generate_json.return_value = {
            "action": "add_concept",
            "term": "??",
            "category": "Skill",
            "confidence": 0.4,  # 낮은 신뢰도
            "reasoning": "요청이 불명확합니다",
        }

        result = await pipeline_with_ontology.run("모호한 요청")

        assert result["success"] is True
        path = result["metadata"]["execution_path"]
        # ontology_update_handler 또는 ontology_update_handler_low_confidence가 있어야 함
        assert any("ontology_update_handler" in node for node in path)
        assert "신뢰도" in result["response"] or "명확" in result["response"]
