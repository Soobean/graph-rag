from pydantic import BaseModel

from src.auth.permissions import check_permission

# 기본 역할별 권한 매핑
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": ["*"],
    "manager": [
        "query:*/search",
        "node:*/read",
        "analytics:*/read",
        "graph:edit/read",
        "graph:edit/write",
        "admin:ontology/read",
        "admin:ontology/write",
    ],
    "editor": [
        "query:*/search",
        "node:*/read",
        "analytics:*/read",
        "graph:edit/read",
        "graph:edit/write",
    ],
    "viewer": [
        "query:*/search",
        "node:*/read",
        "analytics:*/read",
    ],
}


def permissions_for_roles(roles: list[str]) -> list[str]:
    """역할 목록에서 통합 권한 목록 생성 (중복 제거)"""
    perms: list[str] = []
    seen: set[str] = set()
    for role in roles:
        for perm in DEFAULT_ROLE_PERMISSIONS.get(role, []):
            if perm not in seen:
                perms.append(perm)
                seen.add(perm)
    return perms


class UserContext(BaseModel):
    """
    요청 컨텍스트에서 사용하는 사용자 정보

    AUTH_ENABLED=false일 때는 anonymous_admin()이 반환되어
    모든 권한을 가진 관리자로 동작합니다.
    """

    user_id: str
    username: str
    roles: list[str]
    permissions: list[str]
    is_admin: bool
    department: str | None = None

    def has_permission(self, resource: str, action: str) -> bool:
        """
        권한 보유 여부 확인

        Args:
            resource: 리소스 식별자 (예: "query:personnel_search", "admin:users")
            action: 액션 (예: "read", "write", "search")

        Returns:
            True면 허용
        """
        if self.is_admin:
            return True
        required = f"{resource}/{action}"
        return any(check_permission(perm, required) for perm in self.permissions)

    @classmethod
    def anonymous_admin(cls) -> "UserContext":
        """
        AUTH_ENABLED=false일 때 사용되는 익명 관리자 컨텍스트

        모든 권한을 가지므로 기존 동작이 100% 보존됩니다.
        """
        return cls(
            user_id="anonymous",
            username="anonymous_admin",
            roles=["admin"],
            permissions=["*"],
            is_admin=True,
        )
