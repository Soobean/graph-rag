"""
LLM 프롬프트용 포맷터 (순수 함수)

Neo4j 결과/스키마/엔티티를 LLM 프롬프트에 삽입할 문자열로 변환한다.

주의: format_results()는 (subject, relation, object) 페어 보존이 핵심 —
라벨별 그룹화로 되돌리면 응답 LLM이 가짜 페어를 생성하는 중대 버그가 재발한다.
(2026-05-21 수정 이력 참고)
"""

from typing import Any


def format_chat_history_for_prompt(chat_history: str) -> str:
    """
    프롬프트용 chat_history 포맷팅

    빈 문자열이나 공백만 있는 경우 기본 메시지로 대체합니다.

    Args:
        chat_history: format_chat_history()의 반환값

    Returns:
        프롬프트에 삽입할 chat_history 문자열
    """
    return chat_history.strip() or "(No previous conversation)"


def format_schema(schema: dict[str, Any]) -> str:
    """스키마를 문자열로 포맷팅 (속성 정보 + enum 값 포함)"""
    lines = []

    # 노드 스키마 (속성 정보가 있으면 포함)
    nodes = schema.get("nodes")
    if nodes:
        lines.append("Nodes:")
        for node in nodes:
            label = node.get("label", "Unknown")
            props = node.get("properties", [])
            if props:
                prop_parts = []
                for p in props:
                    name = p.get("name", "")
                    if not name:
                        continue
                    sample = p.get("sample_values")
                    if sample:
                        prop_parts.append(f"{name}[{', '.join(sample)}]")
                    else:
                        prop_parts.append(name)
                lines.append(f"  {label} ({', '.join(prop_parts)})")
            else:
                lines.append(f"  {label}")
    else:
        labels = schema.get("node_labels", [])
        if labels:
            lines.append(f"Node Labels: {', '.join(labels)}")

    # 관계 스키마 (속성 정보가 있으면 포함)
    rels = schema.get("relationships")
    if rels:
        lines.append("Relationships:")
        for rel in rels:
            rel_type = rel.get("type", "Unknown")
            props = rel.get("properties", [])
            if props:
                prop_parts = []
                for p in props:
                    name = p.get("name", "")
                    if not name:
                        continue
                    sample = p.get("sample_values")
                    if sample:
                        prop_parts.append(f"{name}[{', '.join(sample)}]")
                    else:
                        prop_parts.append(name)
                lines.append(f"  {rel_type} ({', '.join(prop_parts)})")
            else:
                lines.append(f"  {rel_type}")
    else:
        rel_types = schema.get("relationship_types", [])
        if rel_types:
            lines.append(f"Relationship Types: {', '.join(rel_types)}")

    return "\n".join(lines) if lines else "Schema information not available"


def format_entities(entities: list[dict[str, Any]]) -> str:
    """엔티티 리스트를 문자열로 포맷팅"""
    if not entities:
        return "No entities extracted"

    lines = []
    for entity in entities:
        lines.append(
            f"- {entity.get('type', 'Unknown')}: {entity.get('value', '')} "
            f"(normalized: {entity.get('normalized', '')})"
        )
    return "\n".join(lines)


def format_query_plan(query_plan: dict[str, Any] | None) -> str:
    """Multi-hop 쿼리 계획을 문자열로 포맷팅"""
    if not query_plan:
        return "No query plan (single-hop query)"

    if not query_plan.get("is_multi_hop"):
        return "Single-hop query"

    lines = [
        f"Multi-hop Query Plan ({query_plan.get('hop_count', 0)} hops):",
        f"Goal: {query_plan.get('final_return', 'unknown')}",
    ]

    hops = query_plan.get("hops", [])
    for hop in hops:
        step = hop.get("step", "?")
        desc = hop.get("description", "")
        rel = hop.get("relationship", "")
        direction = hop.get("direction", "")
        filter_cond = hop.get("filter_condition", "")

        hop_line = f"  Step {step}: {desc}"
        if rel:
            hop_line += f" [{rel}, {direction}]"
        if filter_cond:
            hop_line += f" WHERE {filter_cond}"
        lines.append(hop_line)

    return "\n".join(lines)


def format_results(results: list[dict[str, Any]]) -> str:
    """
    쿼리 결과를 문자열로 포맷팅.

    핵심 원칙: 각 row의 (노드, 관계, 노드) 페어 정보를 보존한다.
    이전 구현은 노드를 라벨별로 그룹화하여 어떤 노드가 어떤 노드와 관계되는지 잃었음.
    """
    if not results:
        return "No results found"

    MAX_PAIR_ROWS = 60  # row 단위로 직접 보여줄 최대 개수
    MAX_PROP_DISPLAY = 6  # 한 노드의 표시 속성 수
    SKIP_PROPS = {"embedding", "vector", "id"}

    def _is_node(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and "labels" in value
            and isinstance(value.get("labels"), list)
        )

    def _is_rel(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and "type" in value
            and ("startNodeId" in value or "start" in value)
        )

    def _fmt_node(value: dict[str, Any]) -> str:
        """노드를 '이름:라벨(주요속성)' 형태로 직렬화"""
        labels = value.get("labels", [])
        label = labels[0] if labels else "Node"
        props = value.get("properties", {}) or {}
        name = props.get("name", "?")
        prop_strs = []
        for k, v in props.items():
            if k in SKIP_PROPS or k == "name" or v is None:
                continue
            prop_strs.append(f"{k}={v}")
        extras = ", ".join(prop_strs[:MAX_PROP_DISPLAY])
        return f"{name}:{label}" + (f"({extras})" if extras else "")

    def _fmt_rel(value: dict[str, Any]) -> str:
        """관계를 '-[TYPE props]->' 형태로 직렬화"""
        rel_type = value.get("type", "RELATED")
        props = value.get("properties", {}) or {}
        prop_strs = [
            f"{k}={v}"
            for k, v in props.items()
            if k not in SKIP_PROPS and v is not None
        ]
        extras = " ".join(prop_strs[:4])
        return f"-[{rel_type}{(' ' + extras) if extras else ''}]->"

    # 라벨/관계 통계 수집 + row별 표현 생성
    node_count_by_label: dict[str, int] = {}
    seen_node_ids: set[str] = set()
    rel_counts: dict[str, int] = {}
    formatted_rows: list[str] = []
    scalar_rows: list[dict[str, Any]] = []

    for row in results:
        has_struct = False
        parts: list[str] = []
        for key, value in row.items():
            if _is_node(value):
                has_struct = True
                # id가 빈 문자열인 경우에도 elementId로 fallback
                node_id = value.get("id") or value.get("elementId") or ""
                if node_id and node_id not in seen_node_ids:
                    seen_node_ids.add(node_id)
                    labels = value.get("labels", [])
                    if labels:
                        node_count_by_label[labels[0]] = (
                            node_count_by_label.get(labels[0], 0) + 1
                        )
                parts.append(f"{key}={_fmt_node(value)}")
            elif _is_rel(value):
                has_struct = True
                rel_type = value.get("type", "RELATED")
                rel_counts[rel_type] = rel_counts.get(rel_type, 0) + 1
                parts.append(f"{key}{_fmt_rel(value)}")
            elif value is not None:
                parts.append(f"{key}={value}")

        if has_struct:
            formatted_rows.append(" | ".join(parts))
        else:
            scalar_rows.append(row)

    lines: list[str] = []

    # 1) 헤더: 전체 통계 (LLM에게 데이터 규모 안내)
    if formatted_rows:
        stats_parts = []
        if node_count_by_label:
            stats_parts.append(
                "노드: "
                + ", ".join(
                    f"{lbl}={cnt}" for lbl, cnt in node_count_by_label.items()
                )
            )
        if rel_counts:
            stats_parts.append(
                "관계: " + ", ".join(f"{r}={c}" for r, c in rel_counts.items())
            )
        lines.append(
            f"총 {len(results)}행 ({'; '.join(stats_parts) if stats_parts else ''})"
        )
        lines.append("")
        lines.append("--- 각 행 (subject | relation | object) ---")

        # 2) row 단위 페어 데이터 (페어 정보 보존)
        for i, row_str in enumerate(formatted_rows[:MAX_PAIR_ROWS], 1):
            lines.append(f"{i}. {row_str}")
        if len(formatted_rows) > MAX_PAIR_ROWS:
            lines.append(
                f"... 외 {len(formatted_rows) - MAX_PAIR_ROWS}개 행 (LLM은 위 샘플로 답변)"
            )

    # 3) 스칼라/집계 결과 (그대로 표시)
    if scalar_rows:
        if lines:
            lines.append("")
        lines.append(f"집계 결과 ({len(scalar_rows)}행):")
        for i, row in enumerate(scalar_rows[:30], 1):
            parts = [f"{k}={v}" for k, v in row.items() if v is not None]
            lines.append(f"  {i}. {', '.join(parts)}")
        if len(scalar_rows) > 30:
            lines.append(f"  ... 외 {len(scalar_rows) - 30}개")

    if not lines:
        return "No results found"

    return "\n".join(lines)
