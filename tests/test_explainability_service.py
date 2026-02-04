"""
ExplainabilityService 단위 테스트

실행 방법:
    pytest tests/test_explainability_service.py -v
"""

import pytest

from src.api.services.explainability import (
    NODE_DESCRIPTIONS,
    NODE_TO_STEP_TYPE,
    ExplainabilityService,
)
from src.api.utils.graph_utils import NODE_STYLES, get_node_style, sanitize_props


class TestExplainabilityServiceInit:
    """ExplainabilityService 초기화 테스트"""

    def test_service_can_be_instantiated(self):
        """서비스 인스턴스 생성"""
        service = ExplainabilityService()
        assert service is not None


class TestBuildThoughtProcess:
    """build_thought_process 메서드 테스트"""

    @pytest.fixture
    def service(self):
        return ExplainabilityService()

    def test_empty_execution_path(self, service):
        """빈 실행 경로"""
        metadata = {"execution_path": []}
        result = service.build_thought_process(metadata, None)

        assert result.steps == []
        assert result.concept_expansions == []
        assert result.execution_path == []

    def test_single_step_execution_path(self, service):
        """단일 스텝 실행 경로"""
        metadata = {
            "execution_path": ["intent_classifier"],
            "intent": "personnel_search",
            "intent_confidence": 0.92,
        }
        result = service.build_thought_process(metadata, None)

        assert len(result.steps) == 1
        step = result.steps[0]
        assert step.step_number == 1
        assert step.node_name == "intent_classifier"
        assert step.step_type == "classification"
        assert "Intent: personnel_search" in step.output_summary
        assert "(92%)" in step.output_summary

    def test_multiple_steps_execution_path(self, service):
        """여러 스텝 실행 경로"""
        metadata = {
            "execution_path": [
                "intent_classifier",
                "entity_extractor",
                "concept_expander",
                "entity_resolver",
            ],
            "intent": "personnel_search",
            "intent_confidence": 0.9,
            "entities": {"Skill": ["Python", "Django"]},
        }
        result = service.build_thought_process(metadata, None)

        assert len(result.steps) == 4
        assert result.steps[0].step_number == 1
        assert result.steps[3].step_number == 4

    def test_entity_extractor_step_details(self, service):
        """엔티티 추출 스텝 세부 정보"""
        metadata = {
            "execution_path": ["entity_extractor"],
            "entities": {"Employee": ["홍길동"], "Skill": ["Python", "Java"]},
        }
        result = service.build_thought_process(metadata, None)

        step = result.steps[0]
        assert step.step_type == "extraction"
        assert "추출된 엔티티: 3개" in step.output_summary
        assert step.details["entities"] == {"Employee": ["홍길동"], "Skill": ["Python", "Java"]}

    def test_concept_expander_step_with_full_state(self, service):
        """개념 확장 스텝 (full_state 포함)"""
        metadata = {"execution_path": ["concept_expander"]}
        full_state = {
            "original_entities": {"Skill": ["Python"]},
            "expanded_entities": {"Skill": ["Python", "Django", "FastAPI"]},
            "expanded_entities_by_original": {
                "Skill": {"Python": ["Python", "Django", "FastAPI"]}
            },
            "expansion_strategy": "normal",
            "expansion_count": 2,
        }
        result = service.build_thought_process(metadata, full_state)

        step = result.steps[0]
        assert step.step_type == "expansion"
        assert "확장 전략: normal" in step.output_summary
        assert "+2개 개념 추가" in step.output_summary
        assert step.details["expansion_count"] == 2

    def test_cypher_generator_step_details(self, service):
        """Cypher 생성 스텝 세부 정보"""
        cypher_query = "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill) WHERE s.name = 'Python' RETURN e"
        metadata = {
            "execution_path": ["cypher_generator"],
            "cypher_query": cypher_query,
        }
        result = service.build_thought_process(metadata, None)

        step = result.steps[0]
        assert step.step_type == "generation"
        assert "Cypher 쿼리 생성 완료" in step.output_summary
        assert f"({len(cypher_query)}자)" in step.output_summary

    def test_graph_executor_step_details(self, service):
        """그래프 실행 스텝 세부 정보"""
        metadata = {
            "execution_path": ["graph_executor"],
            "result_count": 15,
        }
        result = service.build_thought_process(metadata, None)

        step = result.steps[0]
        assert step.step_type == "execution"
        assert "결과: 15건" in step.output_summary

    def test_error_suffix_removed_from_node_name(self, service):
        """_error 접미사 제거"""
        metadata = {
            "execution_path": ["cypher_generator_error"],
        }
        result = service.build_thought_process(metadata, None)

        step = result.steps[0]
        # 노드 이름은 그대로, step_type은 정리된 이름 기준
        assert step.node_name == "cypher_generator_error"
        assert step.step_type == "generation"

    def test_concept_expansion_tree_built(self, service):
        """개념 확장 트리 생성"""
        metadata = {"execution_path": ["concept_expander"]}
        full_state = {
            "original_entities": {"Skill": ["파이썬"]},
            "expanded_entities": {"Skill": ["파이썬", "Python", "Django"]},
            "expanded_entities_by_original": {
                "Skill": {"파이썬": ["파이썬", "Python", "Django"]}
            },
            "expansion_strategy": "normal",
            "expansion_count": 2,
        }
        result = service.build_thought_process(metadata, full_state)

        assert len(result.concept_expansions) == 1
        tree = result.concept_expansions[0]
        assert tree.original_concept == "파이썬"
        assert tree.entity_type == "Skill"
        assert tree.expansion_strategy == "normal"
        assert "Python" in tree.expanded_concepts
        assert "Django" in tree.expanded_concepts
        # 원본은 확장된 개념에서 제외
        assert "파이썬" not in tree.expanded_concepts

    def test_multiple_concept_expansions(self, service):
        """여러 개념 확장"""
        metadata = {"execution_path": ["concept_expander"]}
        full_state = {
            "original_entities": {
                "Skill": ["파이썬", "자바스크립트"],
            },
            "expanded_entities": {
                "Skill": ["파이썬", "Python", "자바스크립트", "JavaScript", "React"],
            },
            "expanded_entities_by_original": {
                "Skill": {
                    "파이썬": ["파이썬", "Python"],
                    "자바스크립트": ["자바스크립트", "JavaScript", "React"],
                }
            },
            "expansion_strategy": "broad",
            "expansion_count": 3,
        }
        result = service.build_thought_process(metadata, full_state)

        assert len(result.concept_expansions) == 2


class TestBuildGraphData:
    """build_graph_data 메서드 테스트"""

    @pytest.fixture
    def service(self):
        return ExplainabilityService()

    def test_empty_graph_results(self, service):
        """빈 그래프 결과"""
        full_state = {"graph_results": []}
        result = service.build_graph_data(full_state, [], limit=50)

        assert result.nodes == []
        assert result.edges == []
        assert result.node_count == 0
        assert result.edge_count == 0
        assert result.has_more is False

    def test_nodes_from_resolved_entities(self, service):
        """resolved_entities에서 노드 생성"""
        full_state = {
            "graph_results": [],
            "original_entities": {},
            "expanded_entities": {},
        }
        resolved_entities = [
            {
                "id": 123,
                "labels": ["Employee"],
                "name": "홍길동",
                "properties": {"department": "개발팀"},
            },
            {
                "id": 456,
                "labels": ["Skill"],
                "name": "Python",
                "properties": {},
            },
        ]
        result = service.build_graph_data(full_state, resolved_entities, limit=50)

        assert len(result.nodes) == 2
        assert result.node_count == 2

        # 노드 ID 확인
        node_ids = [n.id for n in result.nodes]
        assert "123" in node_ids
        assert "456" in node_ids

    def test_node_role_classification_query_entity(self, service):
        """노드 역할 분류 - 쿼리 엔티티 (start)"""
        full_state = {
            "graph_results": [],
            "original_entities": {"Skill": ["Python"]},
            "expanded_entities": {"Skill": ["Python"]},
        }
        resolved_entities = [
            {"id": 1, "labels": ["Skill"], "name": "Python", "properties": {}},
        ]
        result = service.build_graph_data(full_state, resolved_entities, limit=50)

        node = result.nodes[0]
        assert node.role == "start"
        assert "1" in result.query_entity_ids

    def test_node_role_classification_expanded_entity(self, service):
        """노드 역할 분류 - 확장 엔티티 (intermediate)"""
        full_state = {
            "graph_results": [],
            "original_entities": {"Skill": ["Python"]},
            "expanded_entities": {"Skill": ["Python", "Django"]},
        }
        resolved_entities = [
            {"id": 2, "labels": ["Skill"], "name": "Django", "properties": {}},
        ]
        result = service.build_graph_data(full_state, resolved_entities, limit=50)

        node = result.nodes[0]
        assert node.role == "intermediate"
        assert "2" in result.expanded_entity_ids

    def test_node_role_classification_result_entity(self, service):
        """노드 역할 분류 - 결과 엔티티 (end)"""
        full_state = {
            "graph_results": [],
            "original_entities": {"Skill": ["Python"]},
            "expanded_entities": {"Skill": ["Python"]},
        }
        resolved_entities = [
            {"id": 3, "labels": ["Employee"], "name": "홍길동", "properties": {}},
        ]
        result = service.build_graph_data(full_state, resolved_entities, limit=50)

        node = result.nodes[0]
        assert node.role == "end"
        assert "3" in result.result_entity_ids

    def test_nodes_from_graph_results(self, service):
        """graph_results에서 노드 추출"""
        full_state = {
            "graph_results": [
                {
                    "e": {
                        "id": 100,
                        "elementId": "elem100",
                        "labels": ["Employee"],
                        "properties": {"name": "김철수", "age": 30},
                    }
                }
            ],
            "original_entities": {},
            "expanded_entities": {},
        }
        result = service.build_graph_data(full_state, [], limit=50)

        assert len(result.nodes) == 1
        node = result.nodes[0]
        assert node.name == "김철수"
        assert node.label == "Employee"

    def test_edges_from_graph_results(self, service):
        """graph_results에서 엣지 추출"""
        # 엣지가 유효하려면 source와 target 노드가 모두 존재해야 함
        full_state = {
            "graph_results": [
                {
                    "n1": {
                        "id": 100,
                        "labels": ["Employee"],
                        "properties": {"name": "김철수"},
                    },
                    "n2": {
                        "id": 101,
                        "labels": ["Skill"],
                        "properties": {"name": "Python"},
                    },
                    "r": {
                        "id": 200,
                        "type": "HAS_SKILL",
                        "startNodeId": 100,
                        "endNodeId": 101,
                        "properties": {"level": "expert"},
                    },
                }
            ],
            "original_entities": {},
            "expanded_entities": {},
        }
        result = service.build_graph_data(full_state, [], limit=50)

        assert len(result.edges) == 1
        edge = result.edges[0]
        assert edge.label == "HAS_SKILL"
        assert edge.source == "100"
        assert edge.target == "101"
        assert edge.properties.get("level") == "expert"

    def test_edges_from_path_query_results(self, service):
        """path 쿼리 결과에서 엣지 추출 (리스트 형식)"""
        # 엣지가 유효하려면 source와 target 노드가 모두 존재해야 함
        # 노드는 개별 키로 제공, 관계는 리스트로 제공
        full_state = {
            "graph_results": [
                {
                    "n1": {"id": 10, "labels": ["Employee"], "properties": {"name": "A"}},
                    "n2": {"id": 20, "labels": ["Department"], "properties": {"name": "B"}},
                    "n3": {"id": 30, "labels": ["Employee"], "properties": {"name": "C"}},
                    "rels": [
                        {
                            "id": 300,
                            "type": "WORKS_IN",
                            "startNodeId": 10,
                            "endNodeId": 20,
                            "properties": {},
                        },
                        {
                            "id": 301,
                            "type": "MANAGES",
                            "start": 20,
                            "end": 30,
                            "properties": {},
                        },
                    ],
                }
            ],
            "original_entities": {},
            "expanded_entities": {},
        }
        result = service.build_graph_data(full_state, [], limit=50)

        assert len(result.edges) == 2

    def test_limit_applied_to_nodes(self, service):
        """노드 제한 적용"""
        # 5개의 그래프 결과 생성
        graph_results = []
        for i in range(5):
            graph_results.append({
                "n": {
                    "id": i,
                    "labels": ["Node"],
                    "properties": {"name": f"Node{i}"},
                }
            })

        full_state = {
            "graph_results": graph_results,
            "original_entities": {},
            "expanded_entities": {},
        }
        result = service.build_graph_data(full_state, [], limit=3)

        # limit이 graph_results 슬라이싱에 적용됨
        assert result.node_count <= 3

    def test_has_more_flag(self, service):
        """has_more 플래그 테스트"""
        # limit보다 많은 결과
        graph_results = [
            {"n": {"id": i, "labels": ["Node"], "properties": {"name": f"N{i}"}}}
            for i in range(10)
        ]
        full_state = {
            "graph_results": graph_results,
            "original_entities": {},
            "expanded_entities": {},
        }

        result = service.build_graph_data(full_state, [], limit=5)
        assert result.has_more is True

    def test_duplicate_nodes_not_added(self, service):
        """중복 노드 방지"""
        resolved_entities = [
            {"id": 1, "labels": ["Skill"], "name": "Python", "properties": {}},
        ]
        full_state = {
            "graph_results": [
                {
                    "s": {
                        "id": 1,
                        "labels": ["Skill"],
                        "properties": {"name": "Python"},
                    }
                }
            ],
            "original_entities": {},
            "expanded_entities": {},
        }
        result = service.build_graph_data(full_state, resolved_entities, limit=50)

        # 같은 ID의 노드는 한 번만 추가됨
        assert result.node_count == 1


class TestGetNodeStyle:
    """get_node_style 함수 테스트"""

    def test_employee_style(self):
        """Employee 노드 스타일"""
        style = get_node_style("Employee")
        assert style.color == "#4A90D9"
        assert style.icon == "person"
        assert style.size == 1.2

    def test_skill_style(self):
        """Skill 노드 스타일"""
        style = get_node_style("Skill")
        assert style.color == "#7CB342"
        assert style.icon == "code"

    def test_department_style(self):
        """Department 노드 스타일"""
        style = get_node_style("Department")
        assert style.color == "#FF7043"
        assert style.icon == "business"

    def test_unknown_label_uses_default(self):
        """알 수 없는 라벨은 기본 스타일"""
        style = get_node_style("UnknownLabel")
        default_style = NODE_STYLES["default"]
        assert style.color == default_style["color"]
        assert style.icon == default_style["icon"]


class TestSanitizeProps:
    """sanitize_props 함수 테스트"""

    def test_simple_props_preserved(self):
        """기본 타입 속성 유지"""
        props = {"name": "홍길동", "age": 30, "active": True, "score": 0.95}
        result = sanitize_props(props)

        assert result["name"] == "홍길동"
        assert result["age"] == 30
        assert result["active"] is True
        assert result["score"] == 0.95

    def test_embedding_field_excluded(self):
        """embedding 필드 제외"""
        props = {
            "name": "test",
            "embedding": [0.1, 0.2, 0.3],
            "name_embedding": [0.4, 0.5],
        }
        result = sanitize_props(props)

        assert "name" in result
        assert "embedding" not in result
        assert "name_embedding" not in result

    def test_datetime_converted_to_isoformat(self):
        """DateTime을 ISO format으로 변환"""
        from datetime import datetime

        dt = datetime(2024, 1, 15, 10, 30, 0)
        props = {"created_at": dt}
        result = sanitize_props(props)

        assert result["created_at"] == "2024-01-15T10:30:00"

    def test_list_with_datetime(self):
        """리스트 내 DateTime 변환"""
        from datetime import datetime

        dt1 = datetime(2024, 1, 1)
        dt2 = datetime(2024, 12, 31)
        props = {"dates": [dt1, dt2]}
        result = sanitize_props(props)

        assert result["dates"] == ["2024-01-01T00:00:00", "2024-12-31T00:00:00"]

    def test_none_value_preserved(self):
        """None 값 유지"""
        props = {"optional_field": None}
        result = sanitize_props(props)

        assert result["optional_field"] is None


class TestConstants:
    """상수 정의 테스트"""

    def test_node_to_step_type_mapping(self):
        """노드-스텝 타입 매핑 검증"""
        assert NODE_TO_STEP_TYPE["intent_classifier"] == "classification"
        assert NODE_TO_STEP_TYPE["entity_extractor"] == "extraction"
        assert NODE_TO_STEP_TYPE["concept_expander"] == "expansion"
        assert NODE_TO_STEP_TYPE["cypher_generator"] == "generation"
        assert NODE_TO_STEP_TYPE["graph_executor"] == "execution"
        assert NODE_TO_STEP_TYPE["response_generator"] == "response"

    def test_node_descriptions_korean(self):
        """노드 설명 (한국어) 검증"""
        assert "의도" in NODE_DESCRIPTIONS["intent_classifier"]
        assert "엔티티" in NODE_DESCRIPTIONS["entity_extractor"]
        assert "확장" in NODE_DESCRIPTIONS["concept_expander"]
        assert "Cypher" in NODE_DESCRIPTIONS["cypher_generator"]

    def test_node_styles_all_required_labels(self):
        """필수 노드 스타일 정의 검증"""
        required_labels = ["Employee", "Skill", "Department", "Project", "default"]
        for label in required_labels:
            assert label in NODE_STYLES
            assert "color" in NODE_STYLES[label]
            assert "icon" in NODE_STYLES[label]
            assert "size" in NODE_STYLES[label]
