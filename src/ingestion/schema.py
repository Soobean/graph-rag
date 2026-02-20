"""
KG 추출을 위한 스키마 정의 (Human Control Layer)

이 파일은 LLM이 데이터를 추출할 때 따라야 할 "법전" 역할을 합니다.
허용된 Node/Relation 타입과 유효성 규칙을 정의합니다.
"""

from enum import Enum


class NodeType(str, Enum):
    """허용된 노드 타입"""

    PERSON = "Employee"  # DB에 Employee 라벨로 저장됨
    PROJECT = "Project"
    SKILL = "Skill"
    DEPARTMENT = "Department"  # 조직 분석 등을 위해 추가
    POSITION = "Position"  # 직급 체계
    CERTIFICATE = "Certificate"  # 자격증


class RelationType(str, Enum):
    """허용된 관계 타입"""

    # Employee 관련
    WORKS_ON = "WORKS_ON"  # Employee -> Project
    HAS_SKILL = "HAS_SKILL"  # Employee -> Skill
    BELONGS_TO = "BELONGS_TO"  # Employee -> Department
    HAS_POSITION = "HAS_POSITION"  # Employee -> Position
    HAS_CERTIFICATE = "HAS_CERTIFICATE"  # Employee -> Certificate
    MENTORS = "MENTORS"  # Employee -> Person

    # Project 관련
    REQUIRES = "REQUIRES"  # Project -> Skill
    OWNED_BY = "OWNED_BY"  # Project -> Department


# [LLM 가이드라인] 노드별 추출해야 할 핵심 속성(Property)
# LLM 프롬프트에 포함되어 환각을 방지하고 필요한 정보만 추출하도록 유도함
NODE_PROPERTIES = {
    NodeType.PERSON: [
        "name",
        "email",
        "job_type",
        "years_experience",
        "hire_date",
        "hourly_rate",
        "availability",
        "max_projects",
        "department",
    ],
    NodeType.PROJECT: [
        "name",
        "type",
        "status",
        "start_date",
        "budget_million",
        "budget_allocated",
        "budget_spent",
        "duration_months",
        "estimated_hours",
        "required_headcount",
    ],
    NodeType.SKILL: [
        "name",
        "category",
        "difficulty",
        "hourly_rate_min",
        "hourly_rate_max",
        "market_demand",
    ],
    NodeType.DEPARTMENT: ["name"],
    NodeType.POSITION: ["name", "level"],
    NodeType.CERTIFICATE: ["name", "issuer"],
}


# [Validation Logic] 관계 유효성 규칙 (Source Type -> Target Type)
# 이 규칙에 어긋나는 관계가 추출되면 필터링(Discard)됨
VALID_RELATIONS = {
    RelationType.WORKS_ON: (NodeType.PERSON, NodeType.PROJECT),
    RelationType.HAS_SKILL: (NodeType.PERSON, NodeType.SKILL),
    RelationType.BELONGS_TO: (NodeType.PERSON, NodeType.DEPARTMENT),
    RelationType.HAS_POSITION: (NodeType.PERSON, NodeType.POSITION),
    RelationType.HAS_CERTIFICATE: (NodeType.PERSON, NodeType.CERTIFICATE),
    RelationType.MENTORS: (NodeType.PERSON, NodeType.PERSON),
    RelationType.REQUIRES: (NodeType.PROJECT, NodeType.SKILL),
    RelationType.OWNED_BY: (NodeType.PROJECT, NodeType.DEPARTMENT),
}
