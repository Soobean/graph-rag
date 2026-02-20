"""
Explainability Service

AI 추론 과정 및 그래프 시각화 데이터 생성 로직을 담당하는 서비스
"""

from typing import Any

from src.api.schemas.explainability import (
    ConceptExpansionTree,
    ExplainableGraphData,
    ThoughtProcessVisualization,
    ThoughtStep,
)
from src.api.schemas.visualization import GraphEdge, GraphNode
from src.api.utils.graph_utils import get_node_style, sanitize_props
from src.domain.types import FullState, PipelineMetadata

# ============================================
# 상수 정의
# ============================================

# 역할(role) → depth 기본 매핑
# 프론트엔드에서 depth 기반 레이아웃 계산 시 사용
ROLE_TO_DEFAULT_DEPTH: dict[str, int] = {
    "start": 0,  # 쿼리 엔티티 (검색 시작점)
    "intermediate": 1,  # 확장된 개념 (온톨로지 기반)
    "end": 2,  # 결과 엔티티 (검색 결과)
}

# 노드 이름 → 단계 유형 매핑
NODE_TO_STEP_TYPE: dict[str, str] = {
    "intent_classifier": "classification",
    "query_decomposer": "decomposition",
    "cache_checker": "cache",
    "entity_extractor": "extraction",
    "concept_expander": "expansion",
    "entity_resolver": "resolution",
    "cypher_generator": "generation",
    "graph_executor": "execution",
    "response_generator": "response",
    "clarification_handler": "response",
}

# 노드 이름 → 한국어 설명
NODE_DESCRIPTIONS: dict[str, str] = {
    "intent_classifier": "질문 의도 분류",
    "query_decomposer": "Multi-hop 쿼리 분해",
    "cache_checker": "쿼리 캐시 확인",
    "entity_extractor": "엔티티 추출",
    "concept_expander": "개념 확장 (온톨로지)",
    "entity_resolver": "엔티티 매칭 (Neo4j)",
    "cypher_generator": "Cypher 쿼리 생성",
    "graph_executor": "그래프 쿼리 실행",
    "response_generator": "응답 생성",
    "clarification_handler": "명확화 요청",
}


class ExplainabilityService:
    """Explainability 관련 로직을 처리하는 서비스"""

    def build_thought_process(
        self,
        metadata: PipelineMetadata,
        full_state: FullState | None,
    ) -> ThoughtProcessVisualization:
        """메타데이터에서 추론 과정 시각화 데이터 구축"""
        execution_path = metadata.get("execution_path", [])
        steps: list[ThoughtStep] = []

        for i, node_name in enumerate(execution_path):
            # 노드 이름 정리 (_error, _cached 접미사 제거)
            clean_name = node_name.replace("_error", "").replace("_cached", "")

            step = ThoughtStep(
                step_number=i + 1,
                node_name=node_name,
                step_type=NODE_TO_STEP_TYPE.get(clean_name, "execution"),
                description=NODE_DESCRIPTIONS.get(clean_name, node_name),
            )

            # 노드별 세부 정보 추가
            if clean_name == "intent_classifier":
                intent = metadata.get("intent", "unknown")
                confidence = metadata.get("intent_confidence", 0.0)
                step.output_summary = f"Intent: {intent} ({confidence:.0%})"
                step.details = {"intent": intent, "confidence": confidence}

            elif clean_name == "query_decomposer":
                query_plan = metadata.get("query_plan") or {}
                is_multi_hop = query_plan.get("is_multi_hop", False)
                hop_count = query_plan.get("hop_count", 1)
                hops = query_plan.get("hops", [])
                explanation = query_plan.get("explanation", "")

                if is_multi_hop and hop_count > 1:
                    step.output_summary = f"Multi-hop 쿼리: {hop_count}단계"
                else:
                    step.output_summary = "Single-hop 쿼리"

                step.details = {
                    "is_multi_hop": is_multi_hop,
                    "hop_count": hop_count,
                    "hops": hops,
                    "explanation": explanation,
                }

            elif clean_name == "entity_extractor":
                entities = metadata.get("entities", {})
                total = sum(len(v) for v in entities.values())
                step.output_summary = f"추출된 엔티티: {total}개"
                step.details = {"entities": entities}

            elif clean_name == "concept_expander" and full_state:
                original = full_state.get("original_entities", {})
                expanded = full_state.get("expanded_entities", {})
                expanded_by_original = full_state.get(
                    "expanded_entities_by_original", {}
                )
                strategy = full_state.get("expansion_strategy", "normal")
                count = full_state.get("expansion_count", 0)
                step.output_summary = f"확장 전략: {strategy}, +{count}개 개념 추가"
                step.details = {
                    "original_entities": original,
                    "expanded_entities": expanded,
                    "expanded_entities_by_original": expanded_by_original,
                    "expansion_strategy": strategy,
                    "expansion_count": count,
                }

            elif clean_name == "graph_executor":
                step.output_summary = f"결과: {metadata.get('result_count', 0)}건"

            elif clean_name == "cypher_generator":
                cypher = metadata.get("cypher_query", "")
                if cypher:
                    step.output_summary = f"Cypher 쿼리 생성 완료 ({len(cypher)}자)"

            steps.append(step)

        # 개념 확장 트리 구축
        concept_expansions: list[ConceptExpansionTree] = []
        if full_state:
            original = full_state.get("original_entities", {})
            expanded = full_state.get("expanded_entities", {})
            expanded_by_original = full_state.get("expanded_entities_by_original", {})
            strategy = full_state.get("expansion_strategy") or "normal"

            if expanded_by_original:
                for entity_type, original_map in expanded_by_original.items():
                    for orig, exp_values in original_map.items():
                        expanded_only = [v for v in exp_values if v != orig]
                        if expanded_only:
                            expansion_path = [
                                {
                                    "from": orig,
                                    "to": v,
                                    "relation": "synonym/subconcept",
                                }
                                for v in expanded_only
                            ]
                            concept_expansions.append(
                                ConceptExpansionTree(
                                    original_concept=orig,
                                    entity_type=entity_type,
                                    expansion_strategy=strategy,
                                    expanded_concepts=expanded_only,
                                    expansion_path=expansion_path,
                                )
                            )
            else:
                for entity_type, orig_values in original.items():
                    exp_values = expanded.get(entity_type, [])
                    for orig in orig_values:
                        # 확장된 개념만 추출 (원본 제외)
                        expanded_only = [v for v in exp_values if v != orig]
                        if expanded_only:
                            expansion_path = [
                                {
                                    "from": orig,
                                    "to": v,
                                    "relation": "synonym/subconcept",
                                }
                                for v in expanded_only
                            ]
                            concept_expansions.append(
                                ConceptExpansionTree(
                                    original_concept=orig,
                                    entity_type=entity_type,
                                    expansion_strategy=strategy,
                                    expanded_concepts=expanded_only,
                                    expansion_path=expansion_path,
                                )
                            )

        return ThoughtProcessVisualization(
            steps=steps,
            concept_expansions=concept_expansions,
            execution_path=execution_path,
        )

    def _assign_depth_values(self, nodes_map: dict[str, GraphNode]) -> None:
        """
        노드들에 depth 값 할당 (in-place 수정)

        x, y 좌표 계산은 프론트엔드에서 담당하며,
        백엔드는 depth 메타데이터만 제공합니다.

        Args:
            nodes_map: 노드 ID → GraphNode 맵 (depth가 할당됨)
        """
        for node in nodes_map.values():
            # depth가 설정되지 않은 경우 role 기반으로 기본값 할당
            if node.depth == 0 and node.role != "start":
                node.depth = ROLE_TO_DEFAULT_DEPTH.get(node.role or "end", 2)

    def build_graph_data(
        self,
        full_state: FullState,
        resolved_entities: list[dict[str, Any]],
        limit: int = 200,
    ) -> ExplainableGraphData:
        """graph_results에서 시각화 가능한 그래프 데이터 구축 (노드 + 엣지)"""
        graph_results = full_state.get("graph_results", [])
        original_entities = full_state.get("original_entities", {})
        expanded_entities = full_state.get("expanded_entities", {})

        nodes_map: dict[str, GraphNode] = {}
        edges_map: dict[str, GraphEdge] = {}

        query_entity_ids: list[str] = []
        expanded_entity_ids: list[str] = []
        result_entity_ids: list[str] = []

        # 원본/확장 엔티티 이름 집합 (역할 판별용)
        original_names: set[str] = set()
        for values in original_entities.values():
            original_names.update(values)

        expanded_names: set[str] = set()
        for values in expanded_entities.values():
            expanded_names.update(values)
        expanded_names -= original_names  # 순수 확장된 것만

        def add_node(
            node_id: str,
            labels: list[str],
            name: str,
            props: dict[str, Any],
        ) -> None:
            """노드 추가 헬퍼 (depth는 role 기반, x/y는 프론트엔드에서 계산)"""
            if not node_id or node_id in nodes_map:
                return

            label = labels[0] if labels else "Node"

            # 역할 판별 (depth는 프론트엔드에서 BFS로 계산)
            # query_entity_ids: 오직 original_names에 매칭되는 노드만 (쿼리 시작점)
            if name in original_names:
                role = "start"
                depth = 0  # 힌트용, 실제 레이아웃은 프론트엔드 BFS
                query_entity_ids.append(node_id)
            elif name in expanded_names:
                role = "intermediate"
                depth = 1
                expanded_entity_ids.append(node_id)
            else:
                # Person, Skill 등 모든 결과 노드
                role = "end"
                depth = 2
                result_entity_ids.append(node_id)

            nodes_map[node_id] = GraphNode(
                id=node_id,
                label=label,
                name=name or "Unknown",
                properties=sanitize_props(props),
                group=label,
                role=role,
                depth=depth,
                style=get_node_style(label),
            )

        def add_edge(
            edge_id: str,
            rel_type: str,
            source_id: str,
            target_id: str,
            props: dict[str, Any] | None = None,
        ) -> None:
            """엣지 추가 헬퍼"""
            if not edge_id or edge_id in edges_map:
                return
            if not source_id or not target_id:
                return

            edges_map[edge_id] = GraphEdge(
                id=edge_id,
                source=source_id,
                target=target_id,
                label=rel_type,
                properties=sanitize_props(props) if props else {},
            )

        # graph_results에서 노드/엣지 추출
        for row in graph_results[:limit]:
            for _key, value in row.items():
                if not isinstance(value, dict):
                    continue

                # 노드 형식 감지 (labels 속성이 있는 경우)
                if "labels" in value and isinstance(value.get("labels"), list):
                    fallback_id = f"node_{len(nodes_map)}"
                    elem_id = value.get("elementId", fallback_id)
                    node_id = str(value.get("id", elem_id))
                    labels = value.get("labels", [])
                    props = value.get("properties", {})
                    name = props.get("name", "") if isinstance(props, dict) else ""
                    node_props = props if isinstance(props, dict) else {}
                    add_node(node_id, labels, name, node_props)

                # 관계(Relationship) 형식 감지
                # Neo4j: {type: "HAS_SKILL", startNodeId/start, endNodeId/end}
                elif "type" in value and ("startNodeId" in value or "start" in value):
                    rel_type = value.get("type", "RELATED")
                    fallback_edge = f"edge_{len(edges_map)}"
                    edge_id = str(
                        value.get("id", value.get("elementId", fallback_edge))
                    )
                    source = str(value.get("startNodeId", value.get("start", "")))
                    target = str(value.get("endNodeId", value.get("end", "")))
                    props = value.get("properties", {})
                    add_edge(edge_id, rel_type, source, target, props)

            # 리스트 형식의 관계 처리 (path 쿼리 결과)
            for _key, value in row.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and "type" in item:
                            rel_type = item.get("type", "RELATED")
                            fallback_edge = f"edge_{len(edges_map)}"
                            elem_id = item.get("elementId", fallback_edge)
                            edge_id = str(item.get("id", elem_id))
                            source = str(item.get("startNodeId", item.get("start", "")))
                            target = str(item.get("endNodeId", item.get("end", "")))
                            props = item.get("properties", {})
                            add_edge(edge_id, rel_type, source, target, props)

        for entity in resolved_entities:
            node_id = str(entity.get("id", ""))
            labels = entity.get("labels", [])
            name = entity.get("name", entity.get("original_value", ""))
            add_node(node_id, labels, name, entity.get("properties", {}))

        has_more = len(graph_results) > limit

        # depth 값 할당 (x, y 좌표는 프론트엔드에서 계산)
        self._assign_depth_values(nodes_map)

        # 유효한 엣지만 필터링 (source와 target이 모두 nodes_map에 존재하는 경우)
        valid_edges = [
            edge
            for edge in edges_map.values()
            if edge.source in nodes_map and edge.target in nodes_map
        ]

        return ExplainableGraphData(
            nodes=list(nodes_map.values())[:limit],
            edges=valid_edges,
            node_count=min(len(nodes_map), limit),
            edge_count=len(valid_edges),
            query_entity_ids=query_entity_ids,
            expanded_entity_ids=expanded_entity_ids,
            result_entity_ids=result_entity_ids,
            has_more=has_more,
        )
