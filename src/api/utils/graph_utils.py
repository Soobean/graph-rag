"""
Graph Utilities

그래프 시각화 관련 공통 유틸리티 함수 및 상수
"""

from typing import Any

from src.api.schemas.visualization import NodeStyle

# ============================================
# 노드 스타일 정의 (Palantir-style)
# ============================================

NODE_STYLES: dict[str, dict[str, str | float]] = {
    "Employee": {"color": "#4A90D9", "icon": "person", "size": 1.2},
    "Skill": {"color": "#7CB342", "icon": "code", "size": 1.0},
    "Department": {"color": "#FF7043", "icon": "business", "size": 1.3},
    "Project": {"color": "#AB47BC", "icon": "folder", "size": 1.1},
    "Position": {"color": "#26A69A", "icon": "work", "size": 1.0},
    "Certificate": {"color": "#FFA726", "icon": "verified", "size": 0.9},
    "Location": {"color": "#78909C", "icon": "place", "size": 0.9},
    "NodeType": {"color": "#9E9E9E", "icon": "category", "size": 1.0},
    "default": {"color": "#BDBDBD", "icon": "circle", "size": 1.0},
}


def get_node_style(label: str) -> NodeStyle:
    """
    노드 라벨에 따른 스타일 반환

    Args:
        label: 노드 라벨 (Employee, Skill, etc.)

    Returns:
        NodeStyle 객체
    """
    style_data = NODE_STYLES.get(label, NODE_STYLES["default"])
    return NodeStyle(
        color=str(style_data["color"]),
        icon=str(style_data["icon"]),
        size=float(style_data["size"]),
    )


def sanitize_props(props: dict[str, Any]) -> dict[str, Any]:
    """
    Neo4j 속성을 JSON 직렬화 가능한 형태로 변환

    - embedding 필드 제외 (큰 벡터 데이터)
    - DateTime/Duration → ISO format 문자열
    - 기타 Neo4j 타입 → 문자열 변환

    Args:
        props: Neo4j 노드/관계 속성 딕셔너리

    Returns:
        JSON 직렬화 가능한 딕셔너리
    """
    sanitized: dict[str, Any] = {}
    for key, value in props.items():
        # embedding 같은 큰 리스트는 제외
        if "embedding" in key.lower():
            continue
        # Neo4j DateTime, Duration 등은 ISO format으로 변환
        if hasattr(value, "isoformat"):
            sanitized[key] = value.isoformat()
        # Neo4j 특수 타입은 문자열로 변환
        elif hasattr(value, "__str__") and not isinstance(
            value, (str, int, float, bool, list, dict, type(None))
        ):
            sanitized[key] = str(value)
        # 기본 타입은 그대로 유지
        elif isinstance(value, (str, int, float, bool, type(None))):
            sanitized[key] = value
        # 리스트는 각 요소 변환
        elif isinstance(value, list):
            sanitized[key] = [
                v.isoformat() if hasattr(v, "isoformat") else v for v in value
            ]
    return sanitized
