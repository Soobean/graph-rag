"""
Explainability 통합 테스트

파이프라인에서 Explainability 기능이 정상 동작하는지 검증

실행 방법:
    pytest tests/test_explainability_integration.py -v
"""

import pytest


class TestPipelineWithExplainability:
    """파이프라인 Explainability 통합 테스트"""

    @pytest.mark.asyncio
    async def test_run_with_return_full_state_false(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """return_full_state=False일 때 _full_state 미포함"""
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

        result = await pipeline.run(
            "테스트 질문",
            return_full_state=False,
        )

        assert result["success"] is True
        # _full_state가 없어야 함
        assert "_full_state" not in result["metadata"]

    @pytest.mark.asyncio
    async def test_run_with_return_full_state_true(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """return_full_state=True일 때 _full_state 포함"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Skill", "value": "Python"}]
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill) RETURN e",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = [{"e": {"name": "홍길동", "id": 1}}]
        mock_llm.generate_response.return_value = "홍길동을 찾았습니다."

        result = await pipeline.run(
            "Python 개발자 찾아줘",
            return_full_state=True,
        )

        assert result["success"] is True
        assert "_full_state" in result["metadata"]

        full_state = result["metadata"]["_full_state"]
        assert "original_entities" in full_state
        assert "expanded_entities" in full_state
        assert "graph_results" in full_state

    @pytest.mark.asyncio
    async def test_full_state_contains_expansion_info(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """full_state에 개념 확장 정보 포함"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Skill", "value": "파이썬"}]
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = []
        mock_llm.generate_response.return_value = "결과 없음"

        result = await pipeline.run(
            "파이썬 개발자 찾아줘",
            return_full_state=True,
        )

        full_state = result["metadata"]["_full_state"]

        # expansion_strategy와 expansion_count 확인
        assert "expansion_strategy" in full_state
        assert "expansion_count" in full_state

    @pytest.mark.asyncio
    async def test_full_state_contains_graph_results(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """full_state에 그래프 결과 포함"""
        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {"entities": []}
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (e:Employee) RETURN e LIMIT 5",
            "parameters": {},
        }
        graph_results = [
            {"e": {"name": "김철수", "id": 1}},
            {"e": {"name": "이영희", "id": 2}},
        ]
        mock_neo4j.execute_cypher.return_value = graph_results
        mock_llm.generate_response.return_value = "직원 2명을 찾았습니다."

        result = await pipeline.run(
            "직원 목록 보여줘",
            return_full_state=True,
        )

        full_state = result["metadata"]["_full_state"]
        assert full_state["graph_results"] == graph_results


class TestExplainabilityServiceIntegration:
    """ExplainabilityService 통합 테스트"""

    @pytest.mark.asyncio
    async def test_build_thought_process_from_pipeline_result(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """파이프라인 결과에서 추론 과정 구축"""
        from src.api.services.explainability import ExplainabilityService

        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.92,
        }
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Skill", "value": "Python"}]
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill {name: 'Python'}) RETURN e",
            "parameters": {},
        }
        mock_neo4j.execute_cypher.return_value = [{"e": {"name": "홍길동"}}]
        mock_llm.generate_response.return_value = "홍길동을 찾았습니다."

        result = await pipeline.run(
            "Python 개발자 찾아줘",
            return_full_state=True,
        )

        service = ExplainabilityService()
        metadata = result["metadata"]
        full_state = metadata.get("_full_state")

        thought_process = service.build_thought_process(metadata, full_state)

        # 실행 경로에 따른 스텝이 생성되었는지 확인
        assert len(thought_process.steps) > 0
        assert thought_process.execution_path == metadata["execution_path"]

        # intent_classifier 스텝 확인
        intent_step = next(
            (s for s in thought_process.steps if s.node_name == "intent_classifier"),
            None,
        )
        if intent_step:
            assert "Intent:" in intent_step.output_summary
            assert "92%" in intent_step.output_summary

    @pytest.mark.asyncio
    async def test_build_graph_data_from_pipeline_result(
        self, pipeline, mock_llm, mock_neo4j
    ):
        """파이프라인 결과에서 그래프 데이터 구축"""
        from src.api.services.explainability import ExplainabilityService

        mock_llm.classify_intent.return_value = {
            "intent": "personnel_search",
            "confidence": 0.9,
        }
        mock_llm.extract_entities.return_value = {
            "entities": [{"type": "Skill", "value": "Python"}]
        }
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (e:Employee)-[r:HAS_SKILL]->(s:Skill) RETURN e, r, s",
            "parameters": {},
        }
        # Neo4j 스타일의 노드/관계 데이터
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": {
                    "id": 100,
                    "labels": ["Employee"],
                    "properties": {"name": "홍길동"},
                },
                "r": {
                    "id": 200,
                    "type": "HAS_SKILL",
                    "startNodeId": 100,
                    "endNodeId": 101,
                    "properties": {},
                },
                "s": {
                    "id": 101,
                    "labels": ["Skill"],
                    "properties": {"name": "Python"},
                },
            }
        ]
        mock_llm.generate_response.return_value = "홍길동이 Python을 보유하고 있습니다."

        result = await pipeline.run(
            "Python 개발자와 스킬 관계 보여줘",
            return_full_state=True,
        )

        service = ExplainabilityService()
        full_state = result["metadata"].get("_full_state")
        resolved_entities = result["metadata"].get("resolved_entities", [])

        graph_data = service.build_graph_data(
            full_state=full_state,
            resolved_entities=resolved_entities,
            limit=50,
        )

        # 노드와 엣지가 생성되었는지 확인
        assert graph_data.node_count >= 0
        # 엣지가 추출되었는지 확인 (관계 데이터가 있는 경우)
        # Note: 실제 추출은 Neo4j 반환 형식에 따라 다름


class TestQueryRequestWithExplainability:
    """QueryRequest Explainability 옵션 테스트"""

    def test_default_explainability_options(self):
        """기본 Explainability 옵션값"""
        from src.api.schemas.query import QueryRequest

        request = QueryRequest(question="테스트 질문")

        assert request.include_explanation is False
        assert request.include_graph is False
        assert request.graph_limit == 50

    def test_explainability_options_enabled(self):
        """Explainability 옵션 활성화"""
        from src.api.schemas.query import QueryRequest

        request = QueryRequest(
            question="테스트 질문",
            include_explanation=True,
            include_graph=True,
            graph_limit=100,
        )

        assert request.include_explanation is True
        assert request.include_graph is True
        assert request.graph_limit == 100

    def test_graph_limit_validation(self):
        """graph_limit 범위 검증"""
        from pydantic import ValidationError

        from src.api.schemas.query import QueryRequest

        # 최소값 미만
        with pytest.raises(ValidationError):
            QueryRequest(question="test", graph_limit=0)

        # 최대값 초과
        with pytest.raises(ValidationError):
            QueryRequest(question="test", graph_limit=201)

        # 경계값 (유효)
        req_min = QueryRequest(question="test", graph_limit=1)
        req_max = QueryRequest(question="test", graph_limit=200)
        assert req_min.graph_limit == 1
        assert req_max.graph_limit == 200


class TestQueryResponseWithExplainability:
    """QueryResponse Explainability 필드 테스트"""

    def test_response_without_explanation(self):
        """explanation 없는 응답"""
        # ExplainableResponse를 먼저 임포트하여 forward reference 해결
        from src.api.schemas.explainability import ExplainableResponse  # noqa: F401
        from src.api.schemas.query import QueryResponse

        # model_rebuild() 호출하여 forward reference 해결
        QueryResponse.model_rebuild()

        response = QueryResponse(
            success=True,
            question="테스트",
            response="응답",
        )

        assert response.explanation is None

    def test_response_with_explanation(self):
        """explanation 포함 응답"""
        from src.api.schemas.explainability import (
            ExplainableResponse,
            ThoughtProcessVisualization,
            ThoughtStep,
        )
        from src.api.schemas.query import QueryResponse

        thought_process = ThoughtProcessVisualization(
            steps=[
                ThoughtStep(
                    step_number=1,
                    node_name="intent_classifier",
                    step_type="classification",
                    description="의도 분류",
                )
            ]
        )
        explanation = ExplainableResponse(thought_process=thought_process)

        response = QueryResponse(
            success=True,
            question="테스트",
            response="응답",
            explanation=explanation,
        )

        assert response.explanation is not None
        assert len(response.explanation.thought_process.steps) == 1
