"""
Response Metadata Builder

파이프라인 실행 결과를 API 응답 메타데이터로 변환합니다.
그래프 데이터(노드/엣지)와 테이블 데이터(집계 결과)를 빌드합니다.
"""

from typing import Any


class ResponseMetadataBuilder:
    """파이프라인 실행 결과를 API 응답 메타데이터로 변환"""

    def build_metadata(self, state: dict[str, Any]) -> dict[str, Any]:
        """스트리밍용 메타데이터 구성 (graph_data 포함)"""
        entities = state.get("expanded_entities") or state.get("entities", {})

        metadata: dict[str, Any] = {
            "intent": state.get("intent", "unknown"),
            "intent_confidence": state.get("intent_confidence", 0.0),
            "entities": entities,
            "cypher_query": state.get("cypher_query", ""),
            "result_count": state.get("result_count", 0),
            "execution_path": state.get("execution_path", []),
        }

        graph_data = self.build_graph_data(state)
        if graph_data:
            metadata["graph_data"] = graph_data
        else:
            tabular_data = self.build_tabular_data(state)
            if tabular_data:
                metadata["tabular_data"] = tabular_data

        return metadata

    def build_graph_data(
        self, state: dict[str, Any], limit: int = 50
    ) -> dict[str, Any] | None:
        """스트리밍용 그래프 데이터 구축"""
        graph_results = state.get("graph_results", [])
        if not graph_results:
            return None

        original_entities = state.get("entities", {})
        expanded_entities = state.get("expanded_entities", {})

        # 원본/확장 엔티티 이름 집합
        original_names: set[str] = set()
        for values in original_entities.values():
            original_names.update(values)

        expanded_names: set[str] = set()
        for values in expanded_entities.values():
            expanded_names.update(values)
        expanded_names -= original_names

        nodes_map: dict[str, dict[str, Any]] = {}
        edges_list: list[dict[str, Any]] = []
        query_entity_ids: list[str] = []
        expanded_entity_ids: list[str] = []
        result_entity_ids: list[str] = []

        # 노드 스타일 기본값
        default_styles = {
            "Employee": {"color": "#4CAF50", "icon": "user", "size": 40},
            "Skill": {"color": "#2196F3", "icon": "code", "size": 35},
            "Department": {"color": "#FF9800", "icon": "building", "size": 45},
            "Project": {"color": "#9C27B0", "icon": "folder", "size": 40},
        }

        def add_node(
            node_id: str,
            labels: list[str],
            name: str,
            props: dict[str, Any],
        ) -> None:
            if not node_id or node_id in nodes_map:
                return
            label = labels[0] if labels else "Node"

            if name in original_names:
                role, depth = "start", 0
                query_entity_ids.append(node_id)
            elif name in expanded_names:
                role, depth = "intermediate", 1
                expanded_entity_ids.append(node_id)
            else:
                role, depth = "end", 2
                result_entity_ids.append(node_id)

            nodes_map[node_id] = {
                "id": node_id,
                "label": label,
                "name": name or "Unknown",
                "properties": {
                    k: v
                    for k, v in props.items()
                    if isinstance(v, (str, int, float, bool))
                },
                "group": label,
                "role": role,
                "depth": depth,
                "style": default_styles.get(
                    label, {"color": "#607D8B", "icon": "circle", "size": 30}
                ),
            }

        def add_edge(
            edge_id: str,
            rel_type: str,
            source: str,
            target: str,
            props: dict[str, Any] | None = None,
        ) -> None:
            if not edge_id or not source or not target:
                return
            edges_list.append(
                {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "label": rel_type,
                    "properties": props or {},
                }
            )

        # graph_results에서 노드/엣지 추출
        for row in graph_results[:limit]:
            for _key, value in row.items():
                if not isinstance(value, dict):
                    continue

                # 노드 감지
                if "labels" in value and isinstance(value.get("labels"), list):
                    elem_id = value.get("elementId", f"node_{len(nodes_map)}")
                    node_id = str(value.get("id", elem_id))
                    labels = value.get("labels", [])
                    props = value.get("properties", {})
                    name = props.get("name", "") if isinstance(props, dict) else ""
                    add_node(
                        node_id,
                        labels,
                        name,
                        props if isinstance(props, dict) else {},
                    )

                # 관계 감지
                elif "type" in value and ("startNodeId" in value or "start" in value):
                    rel_type = value.get("type", "RELATED")
                    edge_id = str(
                        value.get(
                            "id",
                            value.get("elementId", f"edge_{len(edges_list)}"),
                        )
                    )
                    source = str(value.get("startNodeId", value.get("start", "")))
                    target = str(value.get("endNodeId", value.get("end", "")))
                    props = value.get("properties", {})
                    add_edge(edge_id, rel_type, source, target, props)

        # 유효한 엣지만 필터링
        valid_edges = [
            e
            for e in edges_list
            if e["source"] in nodes_map and e["target"] in nodes_map
        ]

        if not nodes_map:
            return None

        return {
            "nodes": list(nodes_map.values())[:limit],
            "edges": valid_edges,
            "node_count": min(len(nodes_map), limit),
            "edge_count": len(valid_edges),
            "query_entity_ids": query_entity_ids,
            "expanded_entity_ids": expanded_entity_ids,
            "result_entity_ids": result_entity_ids,
            "has_more": len(graph_results) > limit,
        }

    def build_tabular_data(
        self, state: dict[str, Any], limit: int = 100
    ) -> dict[str, Any] | None:
        """집계 쿼리 결과를 테이블 형식으로 변환 (스칼라 값만 추출)"""
        graph_results = state.get("graph_results", [])
        if not graph_results:
            return None

        first_row = graph_results[0]
        columns = [
            k
            for k, v in first_row.items()
            if isinstance(v, (str, int, float, bool, type(None)))
        ]
        if not columns:
            return None

        rows = [{col: row.get(col) for col in columns} for row in graph_results[:limit]]
        return {
            "columns": columns,
            "rows": rows,
            "total_count": len(graph_results),
            "has_more": len(graph_results) > limit,
        }
