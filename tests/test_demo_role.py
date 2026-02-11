"""X-Demo-Role 헤더 기반 데모 역할 전환 테스트"""

from unittest.mock import MagicMock, patch

import pytest

from src.auth.access_policy import ADMIN_POLICY
from src.auth.models import UserContext
from src.dependencies import ALLOWED_DEMO_ROLES, get_current_user
from src.domain.exceptions import AuthenticationError


def _make_request(headers: dict[str, str] | None = None) -> MagicMock:
    """테스트용 Request mock 생성"""
    request = MagicMock()
    request.headers = headers or {}
    return request


@pytest.fixture()
def _auth_disabled():
    """AUTH_ENABLED=false 환경 설정 mock"""
    mock_settings = MagicMock()
    mock_settings.auth_enabled = False
    with patch("src.dependencies.get_settings", return_value=mock_settings):
        yield mock_settings


class TestFromDemoRole:
    """UserContext.from_demo_role() 팩토리 메서드 테스트"""

    def test_viewer_role(self):
        ctx = UserContext.from_demo_role("viewer")
        assert ctx.roles == ["viewer"]
        assert ctx.is_admin is False
        assert ctx.department is None
        assert ctx.user_id == "demo_viewer"
        assert "query:*/search" in ctx.permissions
        assert "graph:edit/write" not in ctx.permissions

    def test_manager_role_has_department(self):
        ctx = UserContext.from_demo_role("manager")
        assert ctx.roles == ["manager"]
        assert ctx.department == "백엔드개발팀"
        assert ctx.is_admin is False

    def test_admin_role(self):
        ctx = UserContext.from_demo_role("admin")
        assert ctx.roles == ["admin"]
        assert ctx.is_admin is True
        assert "*" in ctx.permissions

    def test_editor_role(self):
        ctx = UserContext.from_demo_role("editor")
        assert ctx.roles == ["editor"]
        assert ctx.is_admin is False
        assert ctx.department is None
        assert "graph:edit/write" in ctx.permissions


class TestFromDemoRoleAccessPolicy:
    """from_demo_role() → get_access_policy() 통합 검증"""

    def test_admin_returns_admin_policy(self):
        ctx = UserContext.from_demo_role("admin")
        policy = ctx.get_access_policy()
        assert policy is ADMIN_POLICY
        assert "Concept" in policy.get_allowed_labels()
        assert policy.is_relationship_allowed("IS_A")
        assert policy.is_relationship_allowed("MENTORS")

    def test_viewer_restricted_labels_and_properties(self):
        ctx = UserContext.from_demo_role("viewer")
        policy = ctx.get_access_policy()
        allowed = policy.get_allowed_labels()
        assert "Employee" in allowed
        assert "Company" not in allowed  # D1: viewer는 Company 접근 불가
        assert "Concept" not in allowed  # D1: viewer는 Concept 접근 불가
        # D2: viewer의 Employee 속성은 name, job_type만
        assert policy.get_allowed_properties("Employee") == ("name", "job_type")
        # D4: viewer는 MENTORS 접근 불가
        assert not policy.is_relationship_allowed("MENTORS")
        assert not policy.is_relationship_allowed("IS_A")

    def test_manager_department_scope(self):
        ctx = UserContext.from_demo_role("manager")
        policy = ctx.get_access_policy()
        # D3: manager의 Employee는 department scope
        assert policy.get_scope("Employee") == "department"
        assert policy.get_scope("Skill") == "all"
        # D4: manager는 MENTORS 가능, IS_A 불가
        assert policy.is_relationship_allowed("MENTORS")
        assert not policy.is_relationship_allowed("IS_A")

    def test_editor_no_salary_no_mentors(self):
        ctx = UserContext.from_demo_role("editor")
        policy = ctx.get_access_policy()
        # D2: editor의 Employee 속성에 salary 없음
        emp_props = policy.get_allowed_properties("Employee")
        assert emp_props is not None
        assert "salary" not in emp_props
        # D4: editor는 MENTORS 접근 불가
        assert not policy.is_relationship_allowed("MENTORS")


@pytest.mark.usefixtures("_auth_disabled")
class TestGetCurrentUserDemoHeader:
    """get_current_user()의 X-Demo-Role 헤더 처리 테스트"""

    @pytest.mark.asyncio
    async def test_demo_role_viewer(self):
        request = _make_request({"X-Demo-Role": "viewer"})
        ctx = await get_current_user(request)
        assert ctx.roles == ["viewer"]
        assert ctx.is_admin is False

    @pytest.mark.asyncio
    async def test_demo_role_manager(self):
        request = _make_request({"X-Demo-Role": "manager"})
        ctx = await get_current_user(request)
        assert ctx.department == "백엔드개발팀"

    @pytest.mark.asyncio
    async def test_demo_role_admin(self):
        request = _make_request({"X-Demo-Role": "admin"})
        ctx = await get_current_user(request)
        assert ctx.is_admin is True

    @pytest.mark.asyncio
    async def test_invalid_role_ignored(self):
        """허용되지 않은 역할 → 무시, anonymous_admin 반환"""
        request = _make_request({"X-Demo-Role": "superuser"})
        ctx = await get_current_user(request)
        assert ctx.username == "anonymous_admin"
        assert ctx.is_admin is True

    @pytest.mark.asyncio
    async def test_no_header_returns_anonymous_admin(self):
        """헤더 없음 → 기존 동작 (anonymous_admin)"""
        request = _make_request()
        ctx = await get_current_user(request)
        assert ctx.username == "anonymous_admin"
        assert ctx.is_admin is True

    @pytest.mark.asyncio
    async def test_empty_role_ignored(self):
        """빈 문자열 헤더 → 무시"""
        request = _make_request({"X-Demo-Role": ""})
        ctx = await get_current_user(request)
        assert ctx.username == "anonymous_admin"


class TestDemoRoleBlockedWhenAuthEnabled:
    """AUTH_ENABLED=true일 때 X-Demo-Role 헤더가 무시되는지 검증"""

    @pytest.mark.asyncio
    async def test_demo_header_ignored_when_auth_enabled(self):
        """AUTH_ENABLED=true → X-Demo-Role 무시, AuthenticationError 발생"""
        mock_settings = MagicMock()
        mock_settings.auth_enabled = True
        with patch("src.dependencies.get_settings", return_value=mock_settings):
            request = _make_request({"X-Demo-Role": "admin"})
            with pytest.raises(AuthenticationError, match="Missing or invalid"):
                await get_current_user(request)


class TestAllowedDemoRoles:
    """ALLOWED_DEMO_ROLES 상수 검증"""

    def test_contains_all_four_roles(self):
        assert ALLOWED_DEMO_ROLES == {"admin", "manager", "editor", "viewer"}
