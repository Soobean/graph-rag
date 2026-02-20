"""
AccessPolicy 테스트 — 3차원 접근 제어의 핵심 테스트

각 역할별 라벨/속성/부서범위 접근 검증
"""

from src.auth.access_policy import (
    ADMIN_POLICY,
    ALL_PROPS,
    ROLE_POLICIES,
    get_access_policy,
)

# =============================================================================
# 역할별 라벨 접근
# =============================================================================


class TestLabelAccess:
    """Dimension 1: 역할별 라벨 접근 테스트"""

    def test_admin_accesses_all_labels(self):
        """admin은 모든 라벨에 접근 가능 (Company 제외 — DB에 없음)"""
        admin = ROLE_POLICIES["admin"]
        expected = {
            "Employee",
            "Skill",
            "Project",
            "Department",
            "Position",
            "Certificate",
            "Office",
            "Concept",
        }
        assert admin.get_allowed_labels() == expected

    def test_manager_no_concept(self):
        """manager는 Concept 접근 불가"""
        manager = ROLE_POLICIES["manager"]
        labels = manager.get_allowed_labels()
        assert "Concept" not in labels
        assert "Employee" in labels
        assert "Project" in labels

    def test_editor_no_concept(self):
        """editor는 Concept 접근 불가"""
        editor = ROLE_POLICIES["editor"]
        assert "Concept" not in editor.get_allowed_labels()

    def test_viewer_no_company_office_concept(self):
        """viewer는 Company, Office, Concept 접근 불가"""
        viewer = ROLE_POLICIES["viewer"]
        labels = viewer.get_allowed_labels()
        assert "Company" not in labels
        assert "Office" not in labels
        assert "Concept" not in labels
        assert "Employee" in labels
        assert "Skill" in labels

    def test_viewer_label_returns_none_for_company(self):
        """viewer가 Company 라벨의 속성을 조회하면 None"""
        viewer = ROLE_POLICIES["viewer"]
        assert viewer.get_allowed_properties("Company") is None
        assert viewer.get_scope("Company") is None


# =============================================================================
# 속성 가시성
# =============================================================================


class TestPropertyVisibility:
    """Dimension 2: 역할별 속성 가시성 테스트"""

    def test_admin_all_properties(self):
        """admin은 모든 속성 접근 가능 (*)"""
        admin = ROLE_POLICIES["admin"]
        assert admin.get_allowed_properties("Employee") == ALL_PROPS

    def test_viewer_employee_limited_properties(self):
        """viewer는 Employee의 name, job_type, max_projects만"""
        viewer = ROLE_POLICIES["viewer"]
        props = viewer.get_allowed_properties("Employee")
        assert isinstance(props, tuple)
        assert set(props) == {"name", "job_type", "max_projects"}

    def test_editor_employee_properties(self):
        """editor는 Employee의 name, job_type, experience, hire_date, availability, max_projects"""
        editor = ROLE_POLICIES["editor"]
        props = editor.get_allowed_properties("Employee")
        assert isinstance(props, tuple)
        assert set(props) == {
            "name",
            "job_type",
            "years_experience",
            "hire_date",
            "availability",
            "max_projects",
        }

    def test_viewer_project_limited_properties(self):
        """viewer는 Project의 name, type, status, required_headcount"""
        viewer = ROLE_POLICIES["viewer"]
        props = viewer.get_allowed_properties("Project")
        assert isinstance(props, tuple)
        assert set(props) == {"name", "type", "status", "required_headcount"}

    def test_editor_project_properties(self):
        """editor는 Project의 name, type, status, start_date + duration/hours/headcount"""
        editor = ROLE_POLICIES["editor"]
        props = editor.get_allowed_properties("Project")
        assert isinstance(props, tuple)
        assert set(props) == {
            "name",
            "type",
            "status",
            "start_date",
            "duration_months",
            "estimated_hours",
            "required_headcount",
        }

    def test_viewer_skill_all_properties(self):
        """viewer도 Skill은 전체 속성 접근 가능"""
        viewer = ROLE_POLICIES["viewer"]
        assert viewer.get_allowed_properties("Skill") == ALL_PROPS

    def test_manager_all_employee_properties(self):
        """manager는 Employee 전체 속성"""
        manager = ROLE_POLICIES["manager"]
        assert manager.get_allowed_properties("Employee") == ALL_PROPS

    def test_viewer_department_only_name(self):
        """viewer는 Department의 name만"""
        viewer = ROLE_POLICIES["viewer"]
        props = viewer.get_allowed_properties("Department")
        assert props == ("name",)


# =============================================================================
# 부서 범위
# =============================================================================


class TestDepartmentScope:
    """Dimension 3: 부서 범위 테스트"""

    def test_admin_all_scope(self):
        """admin은 모든 라벨에서 전체 범위"""
        admin = ROLE_POLICIES["admin"]
        assert admin.get_scope("Employee") == "all"
        assert not admin.has_department_scope()

    def test_manager_department_scope_employee(self):
        """manager는 Employee에 부서 범위"""
        manager = ROLE_POLICIES["manager"]
        assert manager.get_scope("Employee") == "department"

    def test_manager_department_scope_project(self):
        """manager는 Project에 부서 범위"""
        manager = ROLE_POLICIES["manager"]
        assert manager.get_scope("Project") == "department"

    def test_manager_has_department_scope(self):
        """manager는 부서 제한이 있음"""
        manager = ROLE_POLICIES["manager"]
        assert manager.has_department_scope()

    def test_manager_skill_all_scope(self):
        """manager는 Skill에는 전체 범위"""
        manager = ROLE_POLICIES["manager"]
        assert manager.get_scope("Skill") == "all"

    def test_editor_all_scope(self):
        """editor는 모든 라벨에서 전체 범위"""
        editor = ROLE_POLICIES["editor"]
        assert editor.get_scope("Employee") == "all"
        assert not editor.has_department_scope()

    def test_viewer_all_scope(self):
        """viewer는 접근 가능한 라벨에서 전체 범위"""
        viewer = ROLE_POLICIES["viewer"]
        assert viewer.get_scope("Employee") == "all"


# =============================================================================
# 역할 병합 (복수 역할)
# =============================================================================


class TestRoleMerging:
    """복수 역할 병합 테스트"""

    def test_viewer_editor_merge_widens_properties(self):
        """viewer+editor → editor 수준 (속성 합집합)"""
        merged = get_access_policy(["viewer", "editor"])
        # Employee: viewer has (name, job_type, max_projects),
        # editor has (name, job_type, experience, hire_date, availability, max_projects)
        props = merged.get_allowed_properties("Employee")
        assert isinstance(props, tuple)
        assert set(props) == {
            "name",
            "job_type",
            "years_experience",
            "hire_date",
            "availability",
            "max_projects",
        }

    def test_viewer_manager_merge_widens_labels(self):
        """viewer+manager → manager의 라벨 포함 (Office)"""
        merged = get_access_policy(["viewer", "manager"])
        labels = merged.get_allowed_labels()
        assert "Office" in labels
        assert "Employee" in labels

    def test_viewer_manager_scope_merged(self):
        """viewer+manager → Employee scope: viewer=all 우선"""
        merged = get_access_policy(["viewer", "manager"])
        # viewer의 Employee scope=all이 manager의 department보다 우선
        assert merged.get_scope("Employee") == "all"

    def test_viewer_manager_properties_merged(self):
        """viewer+manager → Employee: manager의 '*' 우선"""
        merged = get_access_policy(["viewer", "manager"])
        assert merged.get_allowed_properties("Employee") == ALL_PROPS

    def test_empty_roles(self):
        """빈 역할 → 빈 정책"""
        merged = get_access_policy([])
        assert merged.get_allowed_labels() == set()

    def test_unknown_role_ignored(self):
        """알 수 없는 역할은 무시"""
        merged = get_access_policy(["unknown_role", "viewer"])
        assert (
            merged.get_allowed_labels() == ROLE_POLICIES["viewer"].get_allowed_labels()
        )


# =============================================================================
# UserContext.get_access_policy
# =============================================================================


class TestUserContextAccessPolicy:
    """UserContext.get_access_policy() 통합 테스트"""

    def test_anonymous_admin_returns_admin_policy(self):
        """anonymous admin → ADMIN_POLICY"""
        from src.auth.models import UserContext

        user = UserContext.anonymous_admin()
        policy = user.get_access_policy()
        assert policy.get_allowed_labels() == ADMIN_POLICY.get_allowed_labels()

    def test_viewer_user_returns_viewer_policy(self):
        """viewer 사용자 → viewer 정책"""
        from src.auth.models import UserContext

        user = UserContext(
            user_id="u1",
            username="viewer_user",
            roles=["viewer"],
            permissions=["query:*/search"],
            is_admin=False,
        )
        policy = user.get_access_policy()
        assert "Company" not in policy.get_allowed_labels()
        emp_props = policy.get_allowed_properties("Employee")
        assert isinstance(emp_props, tuple)
        assert set(emp_props) == {"name", "job_type", "max_projects"}

    def test_manager_user_has_department_scope(self):
        """manager 사용자 → 부서 범위"""
        from src.auth.models import UserContext

        user = UserContext(
            user_id="u2",
            username="manager_user",
            roles=["manager"],
            permissions=["query:*/search"],
            is_admin=False,
            department="마케팅",
        )
        policy = user.get_access_policy()
        assert policy.has_department_scope()
        assert policy.get_scope("Employee") == "department"
