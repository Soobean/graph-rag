"""
KG 추출을 위한 스키마 정의 (Human Control Layer)

이 파일은 LLM이 데이터를 추출할 때 따라야 할 "법전" 역할을 합니다.
허용된 Node/Relation 타입과 유효성 규칙을 정의합니다.
"""

from enum import Enum


class NodeType(str, Enum):
    """허용된 노드 타입"""

    PERSON = "Person"  # Employee → Person으로 통일
    PROJECT = "Project"
    SKILL = "Skill"
    DEPARTMENT = "Department"  # 조직 분석 등을 위해 추가
    POSITION = "Position"  # 직급 체계
    CERTIFICATE = "Certificate"  # 자격증


class RelationType(str, Enum):
    """허용된 관계 타입"""

    # Person 관련
    WORKS_ON = "WORKS_ON"  # Person -> Project
    HAS_SKILL = "HAS_SKILL"  # Person -> Skill
    BELONGS_TO = "BELONGS_TO"  # Person -> Department
    HAS_POSITION = "HAS_POSITION"  # Person -> Position
    HAS_CERTIFICATE = "HAS_CERTIFICATE"  # Person -> Certificate
    MENTORS = "MENTORS"  # Person -> Person

    # Project 관련
    REQUIRES = "REQUIRES"  # Project -> Skill
    OWNED_BY = "OWNED_BY"  # Project -> Department


# [LLM 가이드라인] 노드별 추출해야 할 핵심 속성(Property)
# LLM 프롬프트에 포함되어 환각을 방지하고 필요한 정보만 추출하도록 유도함
NODE_PROPERTIES = {
    NodeType.PERSON: ["name", "email", "job_type", "years_experience", "hire_date"],
    NodeType.PROJECT: ["name", "type", "status", "start_date", "budget"],
    NodeType.SKILL: ["name", "category", "difficulty"],
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
