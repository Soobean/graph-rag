"""
UserContext 모델 테스트

anonymous_admin, has_permission, permissions_for_roles를 검증합니다.
"""

from src.auth.models import UserContext, permissions_for_roles


class TestAnonymousAdmin:
    """anonymous_admin() 팩토리 메서드 테스트"""

    def test_anonymous_admin_is_admin(self):
        """AnonymousAdmin은 is_admin=True"""
        ctx = UserContext.anonymous_admin()
        assert ctx.is_admin is True

    def test_anonymous_admin_has_wildcard_permission(self):
        """AnonymousAdmin은 와일드카드 권한 보유"""
        ctx = UserContext.anonymous_admin()
        assert "*" in ctx.permissions

    def test_anonymous_admin_has_admin_role(self):
        """AnonymousAdmin은 admin 역할"""
        ctx = UserContext.anonymous_admin()
        assert "admin" in ctx.roles

    def test_anonymous_admin_user_id(self):
        """AnonymousAdmin의 user_id는 'anonymous'"""
        ctx = UserContext.anonymous_admin()
        assert ctx.user_id == "anonymous"
        assert ctx.username == "anonymous_admin"


class TestHasPermission:
    """has_permission 메서드 테스트"""

    def test_admin_has_all_permissions(self):
        """admin은 모든 권한"""
        ctx = UserContext.anonymous_admin()
        assert ctx.has_permission("admin:users", "write") is True
        assert ctx.has_permission("node:Employee", "read") is True
        assert ctx.has_permission("anything", "anything") is True

    def test_viewer_can_read(self):
        """viewer는 읽기 가능"""
        ctx = UserContext(
            user_id="v1",
            username="viewer1",
            roles=["viewer"],
            permissions=permissions_for_roles(["viewer"]),
            is_admin=False,
        )
        assert ctx.has_permission("node:Employee", "read") is True
        assert ctx.has_permission("query:personnel_search", "search") is True

    def test_viewer_cannot_write(self):
        """viewer는 쓰기 불가"""
        ctx = UserContext(
            user_id="v1",
            username="viewer1",
            roles=["viewer"],
            permissions=permissions_for_roles(["viewer"]),
            is_admin=False,
        )
        assert ctx.has_permission("graph:edit", "write") is False
        assert ctx.has_permission("admin:users", "write") is False

    def test_editor_can_edit_graph(self):
        """editor는 그래프 편집 가능"""
        ctx = UserContext(
            user_id="e1",
            username="editor1",
            roles=["editor"],
            permissions=permissions_for_roles(["editor"]),
            is_admin=False,
        )
        assert ctx.has_permission("graph:edit", "write") is True
        assert ctx.has_permission("graph:edit", "read") is True

    def test_editor_cannot_admin(self):
        """editor는 관리자 기능 불가"""
        ctx = UserContext(
            user_id="e1",
            username="editor1",
            roles=["editor"],
            permissions=permissions_for_roles(["editor"]),
            is_admin=False,
        )
        assert ctx.has_permission("admin:users", "write") is False
        assert ctx.has_permission("admin:ingest", "write") is False

    def test_manager_can_manage_ontology(self):
        """manager는 온톨로지 관리 가능"""
        ctx = UserContext(
            user_id="m1",
            username="manager1",
            roles=["manager"],
            permissions=permissions_for_roles(["manager"]),
            is_admin=False,
        )
        assert ctx.has_permission("admin:ontology", "write") is True
        assert ctx.has_permission("admin:ontology", "read") is True

    def test_manager_cannot_admin_users(self):
        """manager는 사용자 관리 불가"""
        ctx = UserContext(
            user_id="m1",
            username="manager1",
            roles=["manager"],
            permissions=permissions_for_roles(["manager"]),
            is_admin=False,
        )
        assert ctx.has_permission("admin:users", "write") is False


class TestPermissionsForRoles:
    """permissions_for_roles 유틸 함수 테스트"""

    def test_admin_gets_wildcard(self):
        """admin 역할은 와일드카드 권한"""
        perms = permissions_for_roles(["admin"])
        assert "*" in perms

    def test_multiple_roles_merged(self):
        """여러 역할의 권한이 합쳐짐"""
        perms = permissions_for_roles(["viewer", "editor"])
        # viewer 권한
        assert "query:*/search" in perms
        # editor 추가 권한
        assert "graph:edit/write" in perms

    def test_no_duplicates(self):
        """중복 권한 제거"""
        perms = permissions_for_roles(["viewer", "editor"])
        assert len(perms) == len(set(perms))

    def test_unknown_role_returns_empty(self):
        """존재하지 않는 역할은 빈 권한"""
        perms = permissions_for_roles(["nonexistent"])
        assert perms == []

    def test_model_serialization(self):
        """UserContext model_dump 직렬화"""
        ctx = UserContext.anonymous_admin()
        d = ctx.model_dump()
        assert d["user_id"] == "anonymous"
        assert d["is_admin"] is True
        assert isinstance(d["permissions"], list)
