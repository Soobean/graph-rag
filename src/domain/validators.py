"""
Domain Validators

도메인 전반에서 사용되는 검증 유틸리티
"""

import re

# Cypher 식별자 패턴 (한글 지원)
# - 문자(ASCII 또는 한글)로 시작
# - 문자, 숫자, 언더스코어, 한글 허용
CYPHER_IDENTIFIER_PATTERN = re.compile(
    r"^[a-zA-Z\uAC00-\uD7A3][a-zA-Z0-9_\uAC00-\uD7A3]*$"
)


# 쓰기 작업 키워드 (대소문자 무관)
CYPHER_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|DELETE|DETACH|SET|REMOVE|MERGE|DROP|CALL\s*\{)\b",
    re.IGNORECASE,
)


def validate_read_only_cypher(query: str) -> str:
    """
    Cypher 쿼리가 READ-ONLY인지 검증

    쓰기 작업(CREATE, DELETE, SET 등)이 포함된 쿼리를 차단합니다.

    Args:
        query: 검증할 Cypher 쿼리

    Returns:
        검증된 쿼리 (원본과 동일)

    Raises:
        ValueError: 쓰기 작업이 포함된 경우
    """
    if CYPHER_WRITE_KEYWORDS.search(query):
        raise ValueError(
            "Only read-only queries are allowed. "
            "CREATE, DELETE, SET, REMOVE, MERGE, DROP, CALL{} are not permitted."
        )
    return query


def validate_cypher_identifier(name: str, field_name: str = "identifier") -> str:
    """
    Cypher 식별자 검증 (Injection 방지)

    Neo4j Cypher 쿼리에서 사용되는 식별자(라벨, 속성명, 인덱스명 등)를
    검증하여 Injection 공격을 방지합니다.

    Args:
        name: 검증할 식별자
        field_name: 에러 메시지에 표시할 필드명

    Returns:
        검증된 식별자 (원본과 동일)

    Raises:
        ValueError: 유효하지 않은 식별자
    """
    if not name or not CYPHER_IDENTIFIER_PATTERN.match(name):
        raise ValueError(
            f"Invalid {field_name}: '{name}'. "
            "Must start with a letter and contain only alphanumeric characters, "
            "underscores, or Korean characters."
        )
    return name
