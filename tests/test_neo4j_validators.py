"""
Neo4j Validators 단위 테스트

neo4j_validators.py의 검증/필터 함수 테스트.

실행 방법:
    pytest tests/test_neo4j_validators.py -v
"""

import pytest

from src.domain.exceptions import ValidationError
from src.repositories.neo4j_validators import (
    build_label_filter,
    build_rel_filter,
    validate_direction,
    validate_identifier,
    validate_labels,
    validate_relationship_types,
)


class TestIdentifierValidation:
    """Cypher Injection 방어 검증 테스트"""

    def test_validate_identifier_valid(self):
        """유효한 식별자 테스트"""
        assert validate_identifier("Employee") == "Employee"
        assert validate_identifier("WORKS_AT") == "WORKS_AT"
        assert validate_identifier("사람") == "사람"
        assert validate_identifier("Employee123") == "Employee123"
        assert validate_identifier("person_type") == "person_type"

    def test_validate_identifier_empty(self):
        """빈 식별자 검증"""
        with pytest.raises(ValidationError) as exc_info:
            validate_identifier("")
        assert "Empty" in str(exc_info.value)

    def test_validate_identifier_injection_attempts(self):
        """Cypher Injection 시도 검증"""
        injection_attempts = [
            ("Employee; DROP DATABASE", "semicolon and space"),
            ("Employee`", "backtick"),
            ("Employee--", "double dash"),
            ("Employee/*", "comment start"),
            ("Employee]", "bracket"),
            ("Employee)", "parenthesis"),
            ("Employee'", "single quote"),
            ('Employee"', "double quote"),
            ("Employee OR 1=1", "space and equals"),
            ("Employee\t", "tab"),
            ("Employee{}", "braces"),
        ]
        for attempt, _desc in injection_attempts:
            with pytest.raises(ValidationError, match="Invalid .* format"):
                validate_identifier(attempt)

    def test_validate_labels(self):
        """레이블 리스트 검증 테스트"""
        labels = ["Employee", "Employee", "사원"]
        validated = validate_labels(labels)
        assert validated == labels

    def test_validate_labels_invalid(self):
        """유효하지 않은 레이블 검증"""
        with pytest.raises(ValidationError):
            validate_labels(["Valid", "Invalid;DROP"])

    def test_validate_relationship_types(self):
        """관계 타입 검증 테스트"""
        rel_types = ["WORKS_AT", "KNOWS", "근무"]
        validated = validate_relationship_types(rel_types)
        assert validated == rel_types

    def test_validate_direction_valid(self):
        """유효한 방향 값 테스트"""
        for direction in ["in", "out", "both"]:
            assert validate_direction(direction) == direction

    def test_validate_direction_invalid(self):
        """유효하지 않은 방향 값 테스트"""
        with pytest.raises(ValidationError) as exc_info:
            validate_direction("invalid")
        assert "direction" in str(exc_info.value)


class TestFilterBuilding:
    """필터 문자열 생성 테스트"""

    def test_build_label_filter_single(self):
        """단일 레이블 필터"""
        result = build_label_filter(["Employee"])
        assert result == ":Employee"

    def test_build_label_filter_multiple(self):
        """다중 레이블 필터"""
        result = build_label_filter(["Employee", "Employee"])
        assert result == ":Employee:Employee"

    def test_build_label_filter_empty(self):
        """빈 레이블 필터"""
        assert build_label_filter(None) == ""
        assert build_label_filter([]) == ""

    def test_build_rel_filter_single(self):
        """단일 관계 타입 필터"""
        result = build_rel_filter(["WORKS_AT"])
        assert result == ":WORKS_AT"

    def test_build_rel_filter_multiple(self):
        """다중 관계 타입 필터"""
        result = build_rel_filter(["WORKS_AT", "KNOWS"])
        assert result == ":WORKS_AT|KNOWS"

    def test_build_rel_filter_empty(self):
        """빈 관계 타입 필터"""
        assert build_rel_filter(None) == ""
        assert build_rel_filter([]) == ""
