"""
4차원 접근 제어 정책 (Node & Relationship Level Access Control)

Dimension 1: 라벨 접근 — 역할별 조회 가능한 Neo4j 노드 라벨
Dimension 2: 속성 가시성 — 같은 라벨이라도 역할별 보이는 속성이 다름
             + 관계 속성 가시성 (relationship_rules)
Dimension 3: 부서 범위 — manager는 자기 부서 데이터만 조회 가능
Dimension 4: 관계 필터링 — 역할별 조회 가능한 관계 타입
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ALL_PROPS: Literal["*"] = "*"


@dataclass(frozen=True)
class NodeAccessRule:
    """단일 노드 라벨의 접근 규칙"""

    allowed_properties: tuple[str, ...] | Literal["*"]  # "*" = 전체 속성 접근
    scope: Literal["all", "department"]  # "department" = 자기 부서만


@dataclass(frozen=True)
class RelationshipAccessRule:
    """단일 관계 타입의 속성 접근 규칙"""

    allowed_properties: tuple[str, ...] | Literal["*"]


@dataclass(frozen=True)
class AccessPolicy:
    """역할의 4차원 접근 정책"""

    node_rules: dict[str, NodeAccessRule]  # label → rule
    allowed_relationships: frozenset[str] = frozenset()  # D4: 허용된 관계 타입
    relationship_rules: dict[str, RelationshipAccessRule] = field(default_factory=dict)

    def get_allowed_labels(self) -> set[str]:
        """접근 가능한 노드 라벨 목록"""
        return set(self.node_rules.keys())

    def get_allowed_properties(
        self, label: str
    ) -> tuple[str, ...] | Literal["*"] | None:
        """특정 라벨의 접근 가능 속성. None이면 라벨 자체 접근 불가"""
        rule = self.node_rules.get(label)
        if rule is None:
            return None
        return rule.allowed_properties

    def get_scope(self, label: str) -> Literal["all", "department"] | None:
        """특정 라벨의 부서 범위. None이면 접근 불가"""
        rule = self.node_rules.get(label)
        if rule is None:
            return None
        return rule.scope

    def has_department_scope(self) -> bool:
        """부서 제한이 있는 라벨이 하나라도 있는지"""
        return any(rule.scope == "department" for rule in self.node_rules.values())

    def is_relationship_allowed(self, rel_type: str) -> bool:
        """관계 타입 접근 허용 여부"""
        return rel_type in self.allowed_relationships

    def get_relationship_allowed_properties(
        self, rel_type: str
    ) -> tuple[str, ...] | Literal["*"] | None:
        """관계 타입의 접근 가능 속성. None이면 규칙 미정의 (전체 허용)"""
        rule = self.relationship_rules.get(rel_type)
        if rule is None:
            return None
        return rule.allowed_properties


def get_access_policy(roles: list[str]) -> AccessPolicy:
    """
    여러 역할의 정책을 병합 (most permissive wins)

    - 라벨: 합집합
    - 속성: 합집합 (어느 한 역할이 "*"이면 "*")
    - Scope: "all" 우선 (더 넓은 범위가 우선)
    - 관계: 합집합
    - 관계 속성: 합집합 (어느 한 역할이 "*"이면 "*")
    """
    merged_rules: dict[str, NodeAccessRule] = {}
    merged_rels: set[str] = set()
    merged_rel_rules: dict[str, RelationshipAccessRule] = {}

    for role in roles:
        policy = ROLE_POLICIES.get(role)
        if policy is None:
            continue

        # D4: 관계 합집합
        merged_rels |= policy.allowed_relationships

        for label, rule in policy.node_rules.items():
            if label not in merged_rules:
                merged_rules[label] = rule
            else:
                existing = merged_rules[label]
                # 속성 병합: "*" 우선, 아니면 합집합
                if (
                    existing.allowed_properties == ALL_PROPS
                    or rule.allowed_properties == ALL_PROPS
                ):
                    merged_props: tuple[str, ...] | Literal["*"] = ALL_PROPS
                else:
                    merged_props = tuple(
                        set(existing.allowed_properties) | set(rule.allowed_properties)
                    )
                # Scope 병합: "all" 우선
                merged_scope: Literal["all", "department"] = (
                    "all"
                    if existing.scope == "all" or rule.scope == "all"
                    else "department"
                )
                merged_rules[label] = NodeAccessRule(
                    allowed_properties=merged_props,
                    scope=merged_scope,
                )

        # 관계 속성 규칙 병합
        for rel_type, rel_rule in policy.relationship_rules.items():
            if rel_type not in merged_rel_rules:
                merged_rel_rules[rel_type] = rel_rule
            else:
                existing_rel = merged_rel_rules[rel_type]
                if (
                    existing_rel.allowed_properties == ALL_PROPS
                    or rel_rule.allowed_properties == ALL_PROPS
                ):
                    merged_rel_props: tuple[str, ...] | Literal["*"] = ALL_PROPS
                else:
                    merged_rel_props = tuple(
                        set(existing_rel.allowed_properties)
                        | set(rel_rule.allowed_properties)
                    )
                merged_rel_rules[rel_type] = RelationshipAccessRule(
                    allowed_properties=merged_rel_props
                )

    return AccessPolicy(
        node_rules=merged_rules,
        allowed_relationships=frozenset(merged_rels),
        relationship_rules=merged_rel_rules,
    )


# =============================================================================
# 역할별 관계 접근 정책
# =============================================================================

# 공통 관계: 모든 역할이 접근 가능
_COMMON_RELS = frozenset(
    {
        "HAS_SKILL",
        "WORKS_ON",
        "BELONGS_TO",
        "HAS_POSITION",
        "REQUIRES",
        "HAS_CERTIFICATE",
        "LOCATED_AT",
        "OWNED_BY",
    }
)

# admin: 전체 관계 접근
_ADMIN_RELS = _COMMON_RELS | frozenset({"MENTORS", "IS_A", "SAME_AS"})

# manager: 멘토링 포함, 온톨로지 제외
_MANAGER_RELS = _COMMON_RELS | frozenset({"MENTORS"})

# editor/viewer: 공통 관계만
_EDITOR_RELS = _COMMON_RELS
_VIEWER_RELS = _COMMON_RELS

# =============================================================================
# 역할별 관계 속성 규칙
# =============================================================================

_ADMIN_REL_RULES: dict[str, RelationshipAccessRule] = {}  # 빈 dict = 전체 허용

_MANAGER_REL_RULES: dict[str, RelationshipAccessRule] = {}  # 전체 허용

_EDITOR_REL_RULES: dict[str, RelationshipAccessRule] = {
    "HAS_SKILL": RelationshipAccessRule(("proficiency", "years_used", "rate_factor")),
    "WORKS_ON": RelationshipAccessRule(
        ("role", "contribution_percent", "allocated_hours")
    ),
    "REQUIRES": RelationshipAccessRule(
        ("required_proficiency", "required_headcount", "priority", "importance")
    ),
}

_VIEWER_REL_RULES: dict[str, RelationshipAccessRule] = {
    "HAS_SKILL": RelationshipAccessRule(("proficiency", "years_used")),
    "WORKS_ON": RelationshipAccessRule(("role",)),
    "REQUIRES": RelationshipAccessRule(
        ("required_proficiency", "priority", "importance")
    ),
}

# =============================================================================
# 역할별 노드 정책 정의
# =============================================================================

_ADMIN_RULES: dict[str, NodeAccessRule] = {
    "Employee": NodeAccessRule(ALL_PROPS, "all"),
    "Skill": NodeAccessRule(ALL_PROPS, "all"),
    "Project": NodeAccessRule(ALL_PROPS, "all"),
    "Department": NodeAccessRule(ALL_PROPS, "all"),
    "Position": NodeAccessRule(ALL_PROPS, "all"),
    "Certificate": NodeAccessRule(ALL_PROPS, "all"),
    "Office": NodeAccessRule(ALL_PROPS, "all"),
    "Concept": NodeAccessRule(ALL_PROPS, "all"),
}

_MANAGER_RULES: dict[str, NodeAccessRule] = {
    "Employee": NodeAccessRule(ALL_PROPS, "department"),
    "Skill": NodeAccessRule(ALL_PROPS, "all"),
    "Project": NodeAccessRule(ALL_PROPS, "department"),
    "Department": NodeAccessRule(ALL_PROPS, "all"),
    "Position": NodeAccessRule(ALL_PROPS, "all"),
    "Certificate": NodeAccessRule(ALL_PROPS, "all"),
    "Office": NodeAccessRule(ALL_PROPS, "all"),
}

_EDITOR_RULES: dict[str, NodeAccessRule] = {
    "Employee": NodeAccessRule(
        (
            "name",
            "job_type",
            "years_experience",
            "hire_date",
            "availability",
            "max_projects",
        ),
        "all",
    ),
    "Skill": NodeAccessRule(ALL_PROPS, "all"),
    "Project": NodeAccessRule(
        (
            "name",
            "type",
            "status",
            "start_date",
            "duration_months",
            "estimated_hours",
            "required_headcount",
        ),
        "all",
    ),
    "Department": NodeAccessRule(("name", "head_count"), "all"),
    "Position": NodeAccessRule(ALL_PROPS, "all"),
    "Certificate": NodeAccessRule(ALL_PROPS, "all"),
    "Office": NodeAccessRule(ALL_PROPS, "all"),
}

_VIEWER_RULES: dict[str, NodeAccessRule] = {
    "Employee": NodeAccessRule(("name", "job_type", "max_projects"), "all"),
    "Skill": NodeAccessRule(ALL_PROPS, "all"),
    "Project": NodeAccessRule(("name", "type", "status", "required_headcount"), "all"),
    "Department": NodeAccessRule(("name",), "all"),
    "Position": NodeAccessRule(("name", "level"), "all"),
    "Certificate": NodeAccessRule(ALL_PROPS, "all"),
    "Office": NodeAccessRule(("name",), "all"),
}

ADMIN_POLICY = AccessPolicy(
    node_rules=_ADMIN_RULES,
    allowed_relationships=_ADMIN_RELS,
    relationship_rules=_ADMIN_REL_RULES,
)

ROLE_POLICIES: dict[str, AccessPolicy] = {
    "admin": ADMIN_POLICY,
    "manager": AccessPolicy(
        node_rules=_MANAGER_RULES,
        allowed_relationships=_MANAGER_RELS,
        relationship_rules=_MANAGER_REL_RULES,
    ),
    "editor": AccessPolicy(
        node_rules=_EDITOR_RULES,
        allowed_relationships=_EDITOR_RELS,
        relationship_rules=_EDITOR_REL_RULES,
    ),
    "viewer": AccessPolicy(
        node_rules=_VIEWER_RULES,
        allowed_relationships=_VIEWER_RELS,
        relationship_rules=_VIEWER_REL_RULES,
    ),
}
