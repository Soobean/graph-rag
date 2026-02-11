"""
권한 매칭 로직

와일드카드(*) 패턴을 지원하는 권한 매칭을 제공합니다.

매칭 규칙:
- "*" → 모든 권한 허용 (admin용)
- "node:*/read" → "node:Employee/read", "node:Skill/read" 등 매칭
- "admin:*" → "admin:users/read", "admin:ontology/write" 등 매칭
- "query:*/search" → "query:personnel_search/search" 매칭
"""

from fnmatch import fnmatchcase


def check_permission(granted: str, required: str) -> bool:
    """
    부여된 권한이 요구 권한을 만족하는지 확인

    fnmatchcase를 사용하여 OS 독립적인 대소문자 구분을 보장합니다.
    (fnmatch.fnmatch는 macOS에서 대소문자를 무시하므로 부적합)

    Args:
        granted: 사용자에게 부여된 권한 패턴 (와일드카드 가능)
        required: 요구되는 권한 (정확한 값)

    Returns:
        True면 매칭됨

    Examples:
        >>> check_permission("*", "admin:users/write")
        True
        >>> check_permission("node:*/read", "node:Employee/read")
        True
        >>> check_permission("node:*/read", "node:Employee/write")
        False
        >>> check_permission("admin:*", "admin:users/read")
        True
    """
    if granted == "*":
        return True
    return fnmatchcase(required, granted)
