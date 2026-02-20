"""
Neo4j Repository 공유 유틸리티

모든 서브 레포지토리에서 공통으로 사용하는 검증/필터링 함수.
모듈 레벨 함수로 제공하여 import 편의성 및 재사용성 극대화.
"""

from src.domain.exceptions import ValidationError
from src.domain.ontology.loader import get_ontology_loader
from src.domain.validators import CYPHER_IDENTIFIER_PATTERN

# ── 공유 상수 ──────────────────────────────────────────────

VALID_DIRECTIONS = {"in", "out", "both"}
CONCEPT_NAME_MAX_LENGTH = 100


# ── 검증 함수 ──────────────────────────────────────────────


def validate_identifier(value: str, field_name: str = "identifier") -> str:
    """
    Cypher 식별자(레이블, 관계 타입) 검증

    Args:
        value: 검증할 값
        field_name: 에러 메시지용 필드명

    Returns:
        검증된 값

    Raises:
        ValidationError: 유효하지 않은 형식인 경우
    """
    if not value:
        raise ValidationError(f"Empty {field_name} is not allowed", field=field_name)
    if not CYPHER_IDENTIFIER_PATTERN.match(value):
        raise ValidationError(
            f"Invalid {field_name} format: '{value}'. "
            "Must start with a letter and contain only alphanumeric, "
            "underscore, or Korean characters.",
            field=field_name,
        )
    return value


def validate_labels(labels: list[str]) -> list[str]:
    """레이블 리스트 검증"""
    return [validate_identifier(label, "label") for label in labels]


def validate_relationship_types(rel_types: list[str]) -> list[str]:
    """관계 타입 리스트 검증"""
    return [validate_identifier(rt, "relationship_type") for rt in rel_types]


def validate_direction(direction: str) -> str:
    """방향 값 검증"""
    if direction not in VALID_DIRECTIONS:
        raise ValidationError(
            f"Invalid direction: '{direction}'. Must be one of {VALID_DIRECTIONS}",
            field="direction",
        )
    return direction


def strip_korean_suffix(name: str) -> str:
    """한국어 접미사 제거 (예: '챗봇 리뉴얼 프로젝트' → '챗봇 리뉴얼')"""
    stripped = name.strip()
    for suffix in get_ontology_loader().get_korean_suffixes():
        if stripped.endswith(suffix) and len(stripped) > len(suffix) + 1:
            stripped = stripped[: -len(suffix)].strip()
            break
    return stripped


# ── 필터 빌더 ──────────────────────────────────────────────


def build_label_filter(labels: list[str] | None) -> str:
    """안전한 레이블 필터 문자열 생성"""
    if not labels:
        return ""
    validated = validate_labels(labels)
    return ":" + ":".join(validated)


def build_rel_filter(relationship_types: list[str] | None) -> str:
    """안전한 관계 타입 필터 문자열 생성"""
    if not relationship_types:
        return ""
    validated = validate_relationship_types(relationship_types)
    return ":" + "|".join(validated)


def validate_concept_name(name: str, field_name: str = "name") -> str:
    """
    Concept 이름 검증

    Args:
        name: 검증할 이름
        field_name: 에러 메시지용 필드명

    Returns:
        정규화된 이름 (strip 적용)

    Raises:
        ValidationError: 유효하지 않은 이름인 경우
    """
    name = name.strip()

    if not name:
        raise ValidationError(
            f"{field_name} cannot be empty or whitespace only",
            field=field_name,
        )

    if len(name) > CONCEPT_NAME_MAX_LENGTH:
        raise ValidationError(
            f"{field_name} must be at most {CONCEPT_NAME_MAX_LENGTH} characters",
            field=field_name,
        )

    return name
