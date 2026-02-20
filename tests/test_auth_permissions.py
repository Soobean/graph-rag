"""
권한 매칭 로직 테스트

와일드카드 패턴 매칭을 검증합니다.
"""

import pytest

from src.auth.permissions import check_permission


class TestCheckPermission:
    """check_permission 와일드카드 매칭 테스트"""

    def test_wildcard_matches_everything(self):
        """'*'는 모든 권한 매칭"""
        assert check_permission("*", "admin:users/write") is True
        assert check_permission("*", "node:Employee/read") is True
        assert check_permission("*", "anything/anything") is True

    def test_exact_match(self):
        """정확한 문자열 매칭"""
        assert check_permission("admin:users/read", "admin:users/read") is True
        assert check_permission("admin:users/read", "admin:users/write") is False

    def test_resource_wildcard(self):
        """리소스 부분 와일드카드: node:*/read"""
        assert check_permission("node:*/read", "node:Employee/read") is True
        assert check_permission("node:*/read", "node:Skill/read") is True
        assert check_permission("node:*/read", "node:Employee/write") is False

    def test_action_wildcard(self):
        """액션 부분 와일드카드: admin:*"""
        assert check_permission("admin:*", "admin:users/read") is True
        assert check_permission("admin:*", "admin:ontology/write") is True
        assert check_permission("admin:*", "node:Employee/read") is False

    def test_query_intent_wildcard(self):
        """쿼리 인텐트 와일드카드: query:*/search"""
        assert (
            check_permission("query:*/search", "query:personnel_search/search") is True
        )
        assert check_permission("query:*/search", "query:org_analysis/search") is True
        assert (
            check_permission("query:*/search", "query:personnel_search/write") is False
        )

    def test_no_wildcard_partial_match_fails(self):
        """와일드카드 없이 부분 매칭 안 됨"""
        assert check_permission("admin:users", "admin:users/read") is False
        assert check_permission("node:Employee", "node:Employee/read") is False

    @pytest.mark.parametrize(
        "granted,required,expected",
        [
            ("analytics:*/read", "analytics:dashboard/read", True),
            ("analytics:*/read", "analytics:reports/read", True),
            ("analytics:*/read", "analytics:dashboard/write", False),
            ("graph:edit/*", "graph:edit/read", True),
            ("graph:edit/*", "graph:edit/write", True),
            ("graph:edit/*", "graph:other/read", False),
        ],
    )
    def test_parametrized_patterns(self, granted, required, expected):
        """다양한 와일드카드 패턴 매칭"""
        assert check_permission(granted, required) is expected
