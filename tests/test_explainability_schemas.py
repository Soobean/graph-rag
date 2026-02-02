"""
Explainability Schemas 단위 테스트

실행 방법:
    pytest tests/test_explainability_schemas.py -v
"""

import pytest
from pydantic import ValidationError

from src.api.schemas.explainability import (
    ConceptExpansionTree,
    ExplainableGraphData,
    ExplainableResponse,
    ThoughtProcessVisualization,
    ThoughtStep,
)
from src.api.schemas.visualization import GraphEdge, GraphNode, NodeStyle


class TestThoughtStep:
    """ThoughtStep 스키마 테스트"""

    def test_minimal_thought_step(self):
        """최소 필수 필드"""
        step = ThoughtStep(
            step_number=1,
            node_name="intent_classifier",
            step_type="classification",
            description="질문 의도 분류",
        )
        assert step.step_number == 1
        assert step.node_name == "intent_classifier"
        assert step.step_type == "classification"
        assert step.description == "질문 의도 분류"
        assert step.input_summary is None
        assert step.output_summary is None
        assert step.details == {}
        assert step.duration_ms is None

    def test_full_thought_step(self):
        """모든 필드 포함"""
        step = ThoughtStep(
            step_number=3,
            node_name="concept_expander",
            step_type="expansion",
            description="개념 확장 (온톨로지)",
            input_summary="Skill: Python",
            output_summary="확장 전략: normal, +2개 개념 추가",
            details={"expansion_count": 2, "strategy": "normal"},
            duration_ms=150.5,
        )
        assert step.input_summary == "Skill: Python"
        assert step.output_summary == "확장 전략: normal, +2개 개념 추가"
        assert step.details["expansion_count"] == 2
        assert step.duration_ms == 150.5

    def test_valid_step_types(self):
        """유효한 step_type 값들"""
        valid_types = [
            "classification",
            "decomposition",
            "extraction",
            "expansion",
            "resolution",
            "generation",
            "execution",
            "response",
            "cache",
        ]
        for step_type in valid_types:
            step = ThoughtStep(
                step_number=1,
                node_name="test",
                step_type=step_type,
                description="test",
            )
            assert step.step_type == step_type

    def test_invalid_step_type_rejected(self):
        """유효하지 않은 step_type 거부"""
        with pytest.raises(ValidationError) as exc_info:
            ThoughtStep(
                step_number=1,
                node_name="test",
                step_type="invalid_type",
                description="test",
            )
        assert "step_type" in str(exc_info.value)

    def test_missing_required_fields(self):
        """필수 필드 누락 검증"""
        with pytest.raises(ValidationError):
            ThoughtStep(step_number=1)  # node_name, step_type, description 누락

    def test_details_accepts_nested_dict(self):
        """details가 중첩 딕셔너리 허용"""
        step = ThoughtStep(
            step_number=1,
            node_name="test",
            step_type="extraction",
            description="test",
            details={
                "entities": {"Employee": ["홍길동"], "Skill": ["Python", "Java"]},
                "count": 3,
            },
        )
        assert step.details["entities"]["Employee"] == ["홍길동"]


class TestConceptExpansionTree:
    """ConceptExpansionTree 스키마 테스트"""

    def test_minimal_expansion_tree(self):
        """최소 필수 필드"""
        tree = ConceptExpansionTree(
            original_concept="파이썬",
            expansion_strategy="normal",
        )
        assert tree.original_concept == "파이썬"
        assert tree.entity_type == "Skill"  # 기본값
        assert tree.expansion_strategy == "normal"
        assert tree.expanded_concepts == []
        assert tree.expansion_path == []

    def test_full_expansion_tree(self):
        """모든 필드 포함"""
        tree = ConceptExpansionTree(
            original_concept="파이썬",
            entity_type="Skill",
            expansion_strategy="broad",
            expanded_concepts=["Python", "Django", "FastAPI", "Flask"],
            expansion_path=[
                {"from": "파이썬", "to": "Python", "relation": "synonym"},
                {"from": "Python", "to": "Django", "relation": "subconcept"},
            ],
        )
        assert tree.entity_type == "Skill"
        assert len(tree.expanded_concepts) == 4
        assert len(tree.expansion_path) == 2
        assert tree.expansion_path[0]["relation"] == "synonym"

    def test_valid_expansion_strategies(self):
        """유효한 expansion_strategy 값들"""
        for strategy in ["strict", "normal", "broad"]:
            tree = ConceptExpansionTree(
                original_concept="test",
                expansion_strategy=strategy,
            )
            assert tree.expansion_strategy == strategy

    def test_invalid_strategy_rejected(self):
        """유효하지 않은 strategy 거부"""
        with pytest.raises(ValidationError) as exc_info:
            ConceptExpansionTree(
                original_concept="test",
                expansion_strategy="invalid",
            )
        assert "expansion_strategy" in str(exc_info.value)


class TestThoughtProcessVisualization:
    """ThoughtProcessVisualization 스키마 테스트"""

    def test_empty_visualization(self):
        """빈 시각화 데이터"""
        viz = ThoughtProcessVisualization()
        assert viz.steps == []
        assert viz.concept_expansions == []
        assert viz.total_duration_ms is None
        assert viz.execution_path == []

    def test_full_visualization(self):
        """전체 시각화 데이터"""
        steps = [
            ThoughtStep(
                step_number=1,
                node_name="intent_classifier",
                step_type="classification",
                description="의도 분류",
            ),
            ThoughtStep(
                step_number=2,
                node_name="entity_extractor",
                step_type="extraction",
                description="엔티티 추출",
            ),
        ]
        expansions = [
            ConceptExpansionTree(
                original_concept="파이썬",
                expansion_strategy="normal",
                expanded_concepts=["Python", "Django"],
            ),
        ]

        viz = ThoughtProcessVisualization(
            steps=steps,
            concept_expansions=expansions,
            total_duration_ms=500.0,
            execution_path=["intent_classifier", "entity_extractor"],
        )

        assert len(viz.steps) == 2
        assert len(viz.concept_expansions) == 1
        assert viz.total_duration_ms == 500.0
        assert viz.execution_path == ["intent_classifier", "entity_extractor"]


class TestExplainableGraphData:
    """ExplainableGraphData 스키마 테스트"""

    def test_empty_graph_data(self):
        """빈 그래프 데이터"""
        graph = ExplainableGraphData()
        assert graph.nodes == []
        assert graph.edges == []
        assert graph.node_count == 0
        assert graph.edge_count == 0
        assert graph.query_entity_ids == []
        assert graph.expanded_entity_ids == []
        assert graph.result_entity_ids == []
        assert graph.has_more is False
        assert graph.cursor is None

    def test_graph_data_with_nodes(self):
        """노드가 있는 그래프 데이터"""
        nodes = [
            GraphNode(
                id="1",
                label="Skill",
                name="Python",
                properties={},
                group="Skill",
                role="start",
            ),
            GraphNode(
                id="2",
                label="Employee",
                name="홍길동",
                properties={"department": "개발팀"},
                group="Employee",
                role="end",
            ),
        ]

        graph = ExplainableGraphData(
            nodes=nodes,
            node_count=2,
            query_entity_ids=["1"],
            result_entity_ids=["2"],
        )

        assert len(graph.nodes) == 2
        assert graph.node_count == 2
        assert "1" in graph.query_entity_ids
        assert "2" in graph.result_entity_ids

    def test_graph_data_with_edges(self):
        """엣지가 있는 그래프 데이터"""
        edges = [
            GraphEdge(
                id="e1",
                source="2",
                target="1",
                label="HAS_SKILL",
                properties={"level": "expert"},
            ),
        ]

        graph = ExplainableGraphData(
            edges=edges,
            edge_count=1,
        )

        assert len(graph.edges) == 1
        assert graph.edge_count == 1
        edge = graph.edges[0]
        assert edge.source == "2"
        assert edge.target == "1"
        assert edge.label == "HAS_SKILL"

    def test_graph_data_pagination(self):
        """페이지네이션 테스트"""
        graph = ExplainableGraphData(
            node_count=100,
            has_more=True,
            cursor="next_page_token",
        )

        assert graph.has_more is True
        assert graph.cursor == "next_page_token"


class TestExplainableResponse:
    """ExplainableResponse 스키마 테스트"""

    def test_empty_response(self):
        """빈 응답"""
        response = ExplainableResponse()
        assert response.thought_process is None
        assert response.graph_data is None

    def test_response_with_thought_process_only(self):
        """thought_process만 포함"""
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

        response = ExplainableResponse(thought_process=thought_process)

        assert response.thought_process is not None
        assert len(response.thought_process.steps) == 1
        assert response.graph_data is None

    def test_response_with_graph_data_only(self):
        """graph_data만 포함"""
        graph_data = ExplainableGraphData(
            nodes=[
                GraphNode(id="1", label="Test", name="TestNode", properties={})
            ],
            node_count=1,
        )

        response = ExplainableResponse(graph_data=graph_data)

        assert response.thought_process is None
        assert response.graph_data is not None
        assert response.graph_data.node_count == 1

    def test_full_response(self):
        """전체 응답"""
        thought_process = ThoughtProcessVisualization(
            steps=[
                ThoughtStep(
                    step_number=1,
                    node_name="intent_classifier",
                    step_type="classification",
                    description="의도 분류",
                    output_summary="Intent: personnel_search (92%)",
                )
            ],
            execution_path=["intent_classifier"],
        )
        graph_data = ExplainableGraphData(
            nodes=[
                GraphNode(id="1", label="Skill", name="Python", properties={}),
                GraphNode(id="2", label="Employee", name="홍길동", properties={}),
            ],
            edges=[
                GraphEdge(id="e1", source="2", target="1", label="HAS_SKILL", properties={})
            ],
            node_count=2,
            edge_count=1,
            query_entity_ids=["1"],
            result_entity_ids=["2"],
        )

        response = ExplainableResponse(
            thought_process=thought_process,
            graph_data=graph_data,
        )

        assert response.thought_process is not None
        assert response.graph_data is not None
        assert len(response.thought_process.steps) == 1
        assert response.graph_data.node_count == 2
        assert response.graph_data.edge_count == 1


class TestGraphNode:
    """GraphNode 스키마 테스트"""

    def test_minimal_node(self):
        """최소 필수 필드"""
        node = GraphNode(id="1", label="Test", name="TestNode", properties={})
        assert node.id == "1"
        assert node.label == "Test"
        assert node.name == "TestNode"
        assert node.properties == {}
        assert node.group is None
        assert node.role is None
        assert node.style is None

    def test_full_node(self):
        """모든 필드 포함"""
        style = NodeStyle(color="#4A90D9", icon="person", size=1.2)
        node = GraphNode(
            id="123",
            label="Employee",
            name="홍길동",
            properties={"department": "개발팀", "years": 5},
            group="Employee",
            role="end",
            style=style,
        )

        assert node.properties["department"] == "개발팀"
        assert node.group == "Employee"
        assert node.role == "end"
        assert node.style.color == "#4A90D9"


class TestGraphEdge:
    """GraphEdge 스키마 테스트"""

    def test_minimal_edge(self):
        """최소 필수 필드"""
        edge = GraphEdge(
            id="e1",
            source="1",
            target="2",
            label="RELATED",
            properties={},
        )
        assert edge.id == "e1"
        assert edge.source == "1"
        assert edge.target == "2"
        assert edge.label == "RELATED"

    def test_edge_with_properties(self):
        """속성이 있는 엣지"""
        edge = GraphEdge(
            id="e1",
            source="100",
            target="200",
            label="HAS_SKILL",
            properties={"level": "expert", "years": 3},
        )
        assert edge.properties["level"] == "expert"
        assert edge.properties["years"] == 3


class TestJsonSerialization:
    """JSON 직렬화 테스트"""

    def test_thought_step_serialization(self):
        """ThoughtStep 직렬화"""
        step = ThoughtStep(
            step_number=1,
            node_name="intent_classifier",
            step_type="classification",
            description="의도 분류",
            output_summary="Intent: personnel_search",
        )
        json_data = step.model_dump()

        assert json_data["step_number"] == 1
        assert json_data["step_type"] == "classification"
        assert json_data["output_summary"] == "Intent: personnel_search"

    def test_explainable_response_round_trip(self):
        """ExplainableResponse 직렬화-역직렬화"""
        original = ExplainableResponse(
            thought_process=ThoughtProcessVisualization(
                steps=[
                    ThoughtStep(
                        step_number=1,
                        node_name="test",
                        step_type="extraction",
                        description="test",
                    )
                ]
            ),
            graph_data=ExplainableGraphData(
                nodes=[
                    GraphNode(id="1", label="Test", name="Node1", properties={})
                ],
                node_count=1,
            ),
        )

        # 직렬화
        json_data = original.model_dump()

        # 역직렬화
        restored = ExplainableResponse.model_validate(json_data)

        assert len(restored.thought_process.steps) == 1
        assert restored.graph_data.node_count == 1
