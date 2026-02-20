"""
접근 제어 필터링 테스트 (Phase 3-D)

GraphExecutorNode의 4차원 결과 필터링과
CypherGeneratorNode의 스키마 필터링을 검증합니다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.auth.access_policy import get_access_policy
from src.auth.models import UserContext
from src.domain.types import GraphSchema
from src.graph.nodes.cypher_generator import CypherGeneratorNode
from src.graph.nodes.graph_executor import GraphExecutorNode
from src.graph.state import GraphRAGState

# =============================================================================
# 테스트 헬퍼: Neo4j 결과 레코드 팩토리
# =============================================================================


def _node(label: str, props: dict | None = None) -> dict:
    """Neo4j 노드 형태 dict 생성"""
    return {
        "labels": [label],
        "properties": props or {},
        "elementId": f"4:fake:{label}",
    }


def _rel(rel_type: str, props: dict | None = None) -> dict:
    """Neo4j 관계 형태 dict 생성"""
    return {
        "type": rel_type,
        "startNodeId": "4:fake:start",
        "endNodeId": "4:fake:end",
        "properties": props or {},
    }


def _user(
    roles: list[str], department: str | None = None, is_admin: bool = False
) -> UserContext:
    """테스트용 UserContext 생성"""
    return UserContext(
        user_id="test",
        username="tester",
        roles=roles,
        permissions=["*"] if is_admin else [],
        is_admin=is_admin,
        department=department,
    )


# =============================================================================
# GraphExecutorNode 4차원 필터링 테스트
# =============================================================================


class TestAccessEnforcementD1:
    """D1: 라벨 접근 제어"""

    @pytest.fixture
    def node(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return GraphExecutorNode(neo4j), neo4j

    @pytest.mark.asyncio
    async def test_viewer_blocked_from_company_label(self, node):
        """viewer는 Company 라벨에 접근 불가 → 레코드 제거"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {"c": _node("Company", {"name": "테스트사"})},
        ]

        state = GraphRAGState(
            cypher_query="MATCH (c:Company) RETURN c",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_viewer_allowed_employee_label(self, node):
        """viewer는 Employee 라벨 접근 가능"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {"e": _node("Employee", {"name": "김철수", "job_type": "정규직"})},
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_viewer_blocked_from_concept_label(self, node):
        """viewer는 Concept 라벨에 접근 불가"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {"c": _node("Concept", {"name": "Python"})},
        ]

        state = GraphRAGState(
            cypher_query="MATCH (c:Concept) RETURN c",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_multi_label_node_blocked_if_any_forbidden(self, node):
        """다중 라벨 노드: 하나라도 금지 라벨이면 제거"""
        executor, mock_neo4j = node
        # Employee는 viewer 허용, Company는 viewer 금지 → 전체 거부
        multi_label_node = {
            "labels": ["Employee", "Company"],
            "properties": {"name": "테스트"},
            "elementId": "4:fake:multi",
        }
        mock_neo4j.execute_cypher.return_value = [{"n": multi_label_node}]

        state = GraphRAGState(
            cypher_query="MATCH (n) RETURN n",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_empty_labels_node_blocked(self, node):
        """빈 라벨 노드는 거부"""
        executor, mock_neo4j = node
        empty_label_node = {
            "labels": [],
            "properties": {"name": "unknown"},
            "elementId": "4:fake:empty",
        }
        mock_neo4j.execute_cypher.return_value = [{"n": empty_label_node}]

        state = GraphRAGState(
            cypher_query="MATCH (n) RETURN n",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 0


class TestAccessEnforcementD2:
    """D2: 속성 가시성"""

    @pytest.fixture
    def node(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return GraphExecutorNode(neo4j), neo4j

    @pytest.mark.asyncio
    async def test_viewer_employee_only_name_and_job_type(self, node):
        """viewer → Employee에서 name, job_type만 보임"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node(
                    "Employee",
                    {
                        "name": "김철수",
                        "job_type": "정규직",
                        "years_experience": 5,
                        "hire_date": "2020-01-01",
                        "salary": 50000000,
                    },
                )
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 1

        props = result["graph_results"][0]["e"]["properties"]
        assert set(props.keys()) == {"name", "job_type"}
        assert props["name"] == "김철수"

    @pytest.mark.asyncio
    async def test_editor_employee_more_properties(self, node):
        """editor → Employee에서 name, job_type, experience, hire_date 보임"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node(
                    "Employee",
                    {
                        "name": "김철수",
                        "job_type": "정규직",
                        "years_experience": 5,
                        "hire_date": "2020-01-01",
                        "salary": 50000000,
                    },
                )
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["editor"]),
        )

        result = await executor(state)
        props = result["graph_results"][0]["e"]["properties"]
        assert "name" in props
        assert "years_experience" in props
        assert "hire_date" in props
        assert "salary" not in props

    @pytest.mark.asyncio
    async def test_viewer_skill_all_props(self, node):
        """viewer → Skill은 ALL_PROPS이므로 전체 속성 접근"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {"s": _node("Skill", {"name": "Python", "category": "programming"})},
        ]

        state = GraphRAGState(
            cypher_query="MATCH (s:Skill) RETURN s",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        props = result["graph_results"][0]["s"]["properties"]
        assert props == {"name": "Python", "category": "programming"}

    @pytest.mark.asyncio
    async def test_viewer_employee_hourly_rate_hidden(self, node):
        """viewer → Employee.hourly_rate는 숨김"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node(
                    "Employee",
                    {
                        "name": "김철수",
                        "job_type": "백엔드개발자",
                        "hourly_rate": 89250,
                        "availability": "available",
                        "max_projects": 4,
                    },
                )
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        props = result["graph_results"][0]["e"]["properties"]
        assert "hourly_rate" not in props
        assert "max_projects" in props  # viewer에게 max_projects는 허용

    @pytest.mark.asyncio
    async def test_editor_project_budget_allocated_hidden(self, node):
        """editor → Project.budget_allocated 숨김 (start_date, duration_months 노출)"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "p": _node(
                    "Project",
                    {
                        "name": "챗봇 리뉴얼",
                        "type": "AI/ML",
                        "status": "진행중",
                        "start_date": "2025-01-01",
                        "budget_allocated": 5000000000,
                        "duration_months": 12,
                        "required_headcount": 8,
                    },
                )
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (p:Project) RETURN p",
            cypher_parameters={},
            user_context=_user(roles=["editor"]),
        )

        result = await executor(state)
        props = result["graph_results"][0]["p"]["properties"]
        assert "budget_allocated" not in props
        assert "duration_months" in props
        assert "required_headcount" in props


class TestAccessEnforcementD2Relationship:
    """D2 확장: 관계 속성 가시성"""

    @pytest.fixture
    def node(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return GraphExecutorNode(neo4j), neo4j

    @pytest.mark.asyncio
    async def test_viewer_has_skill_only_proficiency_years(self, node):
        """viewer → HAS_SKILL에서 proficiency, years_used만 보임"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수", "job_type": "백엔드개발자"}),
                "r": _rel(
                    "HAS_SKILL",
                    {
                        "proficiency": "고급",
                        "years_used": 5,
                        "rate_factor": 0.85,
                        "effective_rate": 123000,
                    },
                ),
                "s": _node("Skill", {"name": "Python"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[r:HAS_SKILL]->(s) RETURN e, r, s",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 1
        rel_props = result["graph_results"][0]["r"]["properties"]
        assert set(rel_props.keys()) == {"proficiency", "years_used"}
        assert "effective_rate" not in rel_props
        assert "rate_factor" not in rel_props

    @pytest.mark.asyncio
    async def test_editor_has_skill_includes_rate_factor(self, node):
        """editor → HAS_SKILL에서 rate_factor도 보임 (effective_rate는 숨김)"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수", "job_type": "백엔드개발자"}),
                "r": _rel(
                    "HAS_SKILL",
                    {
                        "proficiency": "고급",
                        "years_used": 5,
                        "rate_factor": 0.85,
                        "effective_rate": 123000,
                    },
                ),
                "s": _node("Skill", {"name": "Python"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[r:HAS_SKILL]->(s) RETURN e, r, s",
            cypher_parameters={},
            user_context=_user(roles=["editor"]),
        )

        result = await executor(state)
        rel_props = result["graph_results"][0]["r"]["properties"]
        assert "rate_factor" in rel_props
        assert "proficiency" in rel_props
        assert "effective_rate" not in rel_props

    @pytest.mark.asyncio
    async def test_admin_has_skill_all_props(self, node):
        """admin → HAS_SKILL 전체 속성 노출"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수"}),
                "r": _rel(
                    "HAS_SKILL",
                    {
                        "proficiency": "고급",
                        "years_used": 5,
                        "rate_factor": 0.85,
                        "effective_rate": 123000,
                    },
                ),
                "s": _node("Skill", {"name": "Python"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[r:HAS_SKILL]->(s) RETURN e, r, s",
            cypher_parameters={},
            user_context=_user(roles=["admin"], is_admin=True),
        )

        result = await executor(state)
        # admin은 is_admin=True이므로 필터 자체가 적용 안 됨
        rel_props = result["graph_results"][0]["r"]["properties"]
        assert "effective_rate" in rel_props
        assert "rate_factor" in rel_props

    @pytest.mark.asyncio
    async def test_viewer_works_on_only_role(self, node):
        """viewer → WORKS_ON에서 role만 보임"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수", "job_type": "백엔드개발자"}),
                "r": _rel(
                    "WORKS_ON",
                    {
                        "role": "개발자",
                        "contribution_percent": 70,
                        "agreed_rate": 89250,
                        "allocated_hours": 625,
                        "actual_hours": 312,
                    },
                ),
                "p": _node(
                    "Project",
                    {"name": "AI 프로젝트", "type": "AI/ML", "status": "진행중"},
                ),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[r:WORKS_ON]->(p) RETURN e, r, p",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        rel_props = result["graph_results"][0]["r"]["properties"]
        assert set(rel_props.keys()) == {"role"}
        assert "agreed_rate" not in rel_props

    @pytest.mark.asyncio
    async def test_editor_works_on_includes_contribution(self, node):
        """editor → WORKS_ON에서 role, contribution_percent, allocated_hours 보임"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수", "job_type": "백엔드개발자"}),
                "r": _rel(
                    "WORKS_ON",
                    {
                        "role": "개발자",
                        "contribution_percent": 70,
                        "agreed_rate": 89250,
                        "allocated_hours": 625,
                    },
                ),
                "p": _node(
                    "Project",
                    {"name": "AI 프로젝트", "type": "AI/ML", "status": "진행중"},
                ),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[r:WORKS_ON]->(p) RETURN e, r, p",
            cypher_parameters={},
            user_context=_user(roles=["editor"]),
        )

        result = await executor(state)
        rel_props = result["graph_results"][0]["r"]["properties"]
        assert "role" in rel_props
        assert "contribution_percent" in rel_props
        assert "allocated_hours" in rel_props
        assert "agreed_rate" not in rel_props

    @pytest.mark.asyncio
    async def test_viewer_requires_filters_sensitive_props(self, node):
        """viewer → REQUIRES에서 max_hourly_rate, required_headcount 숨김"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "p": _node(
                    "Project",
                    {"name": "AI 프로젝트", "type": "AI/ML", "status": "진행중"},
                ),
                "r": _rel(
                    "REQUIRES",
                    {
                        "importance": "필수",
                        "required_proficiency": "고급",
                        "required_headcount": 2,
                        "max_hourly_rate": 180000,
                        "priority": 1,
                    },
                ),
                "s": _node("Skill", {"name": "Python"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (p)-[r:REQUIRES]->(s) RETURN p, r, s",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        rel_props = result["graph_results"][0]["r"]["properties"]
        assert "importance" in rel_props
        assert "required_proficiency" in rel_props
        assert "priority" in rel_props
        assert "max_hourly_rate" not in rel_props
        assert "required_headcount" not in rel_props

    @pytest.mark.asyncio
    async def test_manager_relationship_all_props(self, node):
        """manager → 관계 속성 전체 노출 (relationship_rules 빈 dict)"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수"}),
                "r": _rel(
                    "HAS_SKILL",
                    {
                        "proficiency": "고급",
                        "years_used": 5,
                        "rate_factor": 0.85,
                        "effective_rate": 123000,
                    },
                ),
                "s": _node("Skill", {"name": "Python"}),
                "d": _node("Department", {"name": "백엔드개발팀"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[r:HAS_SKILL]->(s) RETURN e, r, s",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="백엔드개발팀"),
        )

        result = await executor(state)
        rel_props = result["graph_results"][0]["r"]["properties"]
        assert "effective_rate" in rel_props
        assert "rate_factor" in rel_props


class TestAccessEnforcementD3:
    """D3: 부서 범위 제어"""

    @pytest.fixture
    def node(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return GraphExecutorNode(neo4j), neo4j

    @pytest.mark.asyncio
    async def test_manager_own_department_allowed(self, node):
        """manager → 자기 부서 데이터 접근 가능"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수"}),
                "d": _node("Department", {"name": "백엔드개발팀"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[:BELONGS_TO]->(d) RETURN e, d",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="백엔드개발팀"),
        )

        result = await executor(state)
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_manager_other_department_blocked(self, node):
        """manager → 다른 부서 데이터 접근 불가"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "이영희"}),
                "d": _node("Department", {"name": "AI연구소"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[:BELONGS_TO]->(d) RETURN e, d",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="백엔드개발팀"),
        )

        result = await executor(state)
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_manager_no_department_node_passes(self, node):
        """Department 노드가 없는 레코드는 부서 필터 통과"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {"e": _node("Employee", {"name": "김철수"})},
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="백엔드개발팀"),
        )

        result = await executor(state)
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_manager_department_case_insensitive(self, node):
        """부서 비교는 대소문자 무시"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수"}),
                "d": _node("Department", {"name": "Backend팀"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[:BELONGS_TO]->(d) RETURN e, d",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="backend팀"),
        )

        result = await executor(state)
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_manager_employee_department_denorm_allowed(self, node):
        """manager → Employee.department 비정규화 속성으로도 부서 필터링"""
        executor, mock_neo4j = node
        # Department 노드 없이 Employee.department만 있는 경우
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node(
                    "Employee",
                    {
                        "name": "김철수",
                        "department": "백엔드개발팀",
                    },
                ),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="백엔드개발팀"),
        )

        result = await executor(state)
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_manager_employee_department_denorm_blocked(self, node):
        """manager → Employee.department가 다른 부서면 차단"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node(
                    "Employee",
                    {
                        "name": "이영희",
                        "department": "AI연구소",
                    },
                ),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="백엔드개발팀"),
        )

        result = await executor(state)
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_manager_employee_department_denorm_case_insensitive(self, node):
        """Employee.department 비교도 대소문자 무시"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node(
                    "Employee",
                    {
                        "name": "김철수",
                        "department": "Backend개발팀",
                    },
                ),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="backend개발팀"),
        )

        result = await executor(state)
        assert result["result_count"] == 1


class TestAccessEnforcementD4:
    """D4: 관계 필터링"""

    @pytest.fixture
    def node(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return GraphExecutorNode(neo4j), neo4j

    @pytest.mark.asyncio
    async def test_viewer_blocked_from_mentors_rel(self, node):
        """viewer → MENTORS 관계 포함 레코드 제거"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e1": _node("Employee", {"name": "김철수"}),
                "r": _rel("MENTORS"),
                "e2": _node("Employee", {"name": "이영희"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e1)-[r:MENTORS]->(e2) RETURN e1, r, e2",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_viewer_allowed_has_skill_rel(self, node):
        """viewer → HAS_SKILL 관계 허용"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수", "job_type": "정규직"}),
                "r": _rel("HAS_SKILL"),
                "s": _node("Skill", {"name": "Python"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e)-[r:HAS_SKILL]->(s) RETURN e, r, s",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_editor_blocked_from_is_a_rel(self, node):
        """editor → IS_A 관계 접근 불가"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "c1": _node("Skill", {"name": "Python"}),
                "r": _rel("IS_A"),
                "c2": _node("Skill", {"name": "Programming"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (c1)-[r:IS_A]->(c2) RETURN c1, r, c2",
            cypher_parameters={},
            user_context=_user(roles=["editor"]),
        )

        result = await executor(state)
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_manager_allowed_mentors_rel(self, node):
        """manager → MENTORS 관계 허용"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e1": _node("Employee", {"name": "김철수"}),
                "r": _rel("MENTORS"),
                "e2": _node("Employee", {"name": "이영희"}),
                "d": _node("Department", {"name": "백엔드개발팀"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e1)-[r:MENTORS]->(e2) RETURN e1, r, e2",
            cypher_parameters={},
            user_context=_user(roles=["manager"], department="백엔드개발팀"),
        )

        result = await executor(state)
        assert result["result_count"] == 1


class TestAccessEnforcementAdmin:
    """admin / 미인증 시나리오"""

    @pytest.fixture
    def node(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return GraphExecutorNode(neo4j), neo4j

    @pytest.mark.asyncio
    async def test_admin_passes_all(self, node):
        """admin → 모든 결과 통과, 필터링 없음"""
        executor, mock_neo4j = node
        records = [
            {"c": _node("Company", {"name": "테스트사"})},
            {"e": _node("Employee", {"name": "김철수", "salary": 50000000})},
            {"r": _rel("IS_A")},
        ]
        mock_neo4j.execute_cypher.return_value = records

        state = GraphRAGState(
            cypher_query="MATCH (n) RETURN n",
            cypher_parameters={},
            user_context=_user(roles=["admin"], is_admin=True),
        )

        result = await executor(state)
        assert result["result_count"] == 3
        # admin은 salary도 그대로 보임
        assert result["graph_results"][1]["e"]["properties"]["salary"] == 50000000

    @pytest.mark.asyncio
    async def test_no_user_context_no_filtering(self, node):
        """user_context=None → 필터 없음 (AUTH_ENABLED=false)"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {"c": _node("Company", {"name": "테스트사"})},
        ]

        state = GraphRAGState(
            cypher_query="MATCH (c:Company) RETURN c",
            cypher_parameters={},
        )

        result = await executor(state)
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_anonymous_admin_no_filtering(self, node):
        """anonymous_admin() → is_admin=True → 필터 없음"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {"c": _node("Company", {"name": "테스트사"})},
            {"r": _rel("IS_A")},
        ]

        state = GraphRAGState(
            cypher_query="MATCH (n) RETURN n",
            cypher_parameters={},
            user_context=UserContext.anonymous_admin(),
        )

        result = await executor(state)
        assert result["result_count"] == 2


class TestAccessEnforcementCombined:
    """복합 시나리오"""

    @pytest.fixture
    def node(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return GraphExecutorNode(neo4j), neo4j

    @pytest.mark.asyncio
    async def test_mixed_records_partial_filter(self, node):
        """허용된 레코드만 통과, 나머지 제거"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            # 통과: Employee + HAS_SKILL + Skill (viewer 접근 가능)
            {
                "e": _node(
                    "Employee", {"name": "김철수", "job_type": "정규직", "salary": 5000}
                ),
                "r": _rel("HAS_SKILL"),
                "s": _node("Skill", {"name": "Python"}),
            },
            # 제거: Company 라벨 (D1 위반)
            {
                "c": _node("Company", {"name": "테스트사"}),
            },
            # 제거: MENTORS 관계 (D4 위반)
            {
                "e1": _node("Employee", {"name": "이영희"}),
                "r": _rel("MENTORS"),
                "e2": _node("Employee", {"name": "박수빈"}),
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (n) RETURN n",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 1

        # D2: Employee 속성 필터링 확인
        emp_props = result["graph_results"][0]["e"]["properties"]
        assert "salary" not in emp_props
        assert emp_props["name"] == "김철수"

    @pytest.mark.asyncio
    async def test_scalar_values_preserved(self, node):
        """스칼라 값(count 등)은 필터링 없이 그대로 통과"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node("Employee", {"name": "김철수", "job_type": "정규직"}),
                "skill_count": 5,
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e) RETURN e, count(*) as skill_count",
            cypher_parameters={},
            user_context=_user(roles=["viewer"]),
        )

        result = await executor(state)
        assert result["result_count"] == 1
        assert result["graph_results"][0]["skill_count"] == 5

    @pytest.mark.asyncio
    async def test_multi_role_union(self, node):
        """viewer+editor → 병합 정책 (most permissive)"""
        executor, mock_neo4j = node
        mock_neo4j.execute_cypher.return_value = [
            {
                "e": _node(
                    "Employee",
                    {
                        "name": "김철수",
                        "job_type": "정규직",
                        "years_experience": 5,
                        "salary": 5000,
                    },
                )
            },
        ]

        state = GraphRAGState(
            cypher_query="MATCH (e:Employee) RETURN e",
            cypher_parameters={},
            user_context=_user(roles=["viewer", "editor"]),
        )

        result = await executor(state)
        props = result["graph_results"][0]["e"]["properties"]
        # editor가 experience를 볼 수 있으므로 병합 시 포함
        assert "years_experience" in props
        # salary는 editor도 접근 불가
        assert "salary" not in props


# =============================================================================
# CypherGeneratorNode 스키마 필터링 테스트
# =============================================================================


class TestSchemaFiltering:
    """CypherGenerator._filter_schema_for_policy 테스트"""

    @pytest.fixture
    def full_schema(self) -> GraphSchema:
        return GraphSchema(
            node_labels=["Employee", "Skill", "Company", "Concept", "Department"],
            relationship_types=["HAS_SKILL", "WORKS_ON", "MENTORS", "IS_A", "SAME_AS"],
            nodes=[
                {"label": "Employee", "properties": []},
                {"label": "Skill", "properties": []},
                {"label": "Company", "properties": []},
                {"label": "Concept", "properties": []},
                {"label": "Department", "properties": []},
            ],
            relationships=[
                {"type": "HAS_SKILL"},
                {"type": "WORKS_ON"},
                {"type": "MENTORS"},
                {"type": "IS_A"},
                {"type": "SAME_AS"},
            ],
            indexes=[],
            constraints=[],
        )

    @pytest.fixture
    def generator(self):
        llm = MagicMock()
        neo4j = MagicMock()
        return CypherGeneratorNode(llm, neo4j)

    def test_viewer_schema_labels_filtered(self, generator, full_schema):
        """viewer → Company, Concept 라벨 제거"""
        policy = get_access_policy(["viewer"])
        filtered = generator._filter_schema_for_policy(full_schema, policy)

        assert "Company" not in filtered["node_labels"]
        assert "Concept" not in filtered["node_labels"]
        assert "Employee" in filtered["node_labels"]
        assert "Skill" in filtered["node_labels"]

    def test_viewer_schema_rels_filtered(self, generator, full_schema):
        """viewer → MENTORS, IS_A, SAME_AS 관계 제거"""
        policy = get_access_policy(["viewer"])
        filtered = generator._filter_schema_for_policy(full_schema, policy)

        assert "MENTORS" not in filtered["relationship_types"]
        assert "IS_A" not in filtered["relationship_types"]
        assert "SAME_AS" not in filtered["relationship_types"]
        assert "HAS_SKILL" in filtered["relationship_types"]

    def test_viewer_schema_nodes_filtered(self, generator, full_schema):
        """viewer → nodes 배열에서도 Company, Concept 제거"""
        policy = get_access_policy(["viewer"])
        filtered = generator._filter_schema_for_policy(full_schema, policy)

        node_labels = [n["label"] for n in filtered["nodes"]]
        assert "Company" not in node_labels
        assert "Concept" not in node_labels

    def test_admin_schema_unchanged(self, generator, full_schema):
        """admin → Company 제외, 나머지 스키마 유지"""
        policy = get_access_policy(["admin"])
        filtered = generator._filter_schema_for_policy(full_schema, policy)

        # Company는 admin 정책에서도 제거됨 (DB에 존재하지 않음)
        assert "Employee" in filtered["node_labels"]
        assert "Skill" in filtered["node_labels"]
        assert "Concept" in filtered["node_labels"]
        assert "Department" in filtered["node_labels"]
        assert len(filtered["relationship_types"]) == len(
            full_schema["relationship_types"]
        )

    def test_manager_schema_mentors_included(self, generator, full_schema):
        """manager → MENTORS 포함, IS_A/SAME_AS 제거"""
        policy = get_access_policy(["manager"])
        filtered = generator._filter_schema_for_policy(full_schema, policy)

        assert "MENTORS" in filtered["relationship_types"]
        assert "IS_A" not in filtered["relationship_types"]
        assert "SAME_AS" not in filtered["relationship_types"]

    def test_indexes_and_constraints_preserved(self, generator):
        """indexes/constraints는 필터링 없이 통과"""
        schema = GraphSchema(
            node_labels=["Employee"],
            relationship_types=["HAS_SKILL"],
            nodes=[],
            relationships=[],
            indexes=[{"name": "idx_employee_name", "label": "Employee"}],
            constraints=[{"name": "uniq_employee", "label": "Employee"}],
        )
        policy = get_access_policy(["viewer"])
        filtered = generator._filter_schema_for_policy(schema, policy)

        assert len(filtered["indexes"]) == 1
        assert len(filtered["constraints"]) == 1
