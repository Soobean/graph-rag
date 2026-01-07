"""
Ingestion Models 단위 테스트

generate_entity_id() 함수의 UUID5 기반 결정적 ID 생성 로직을 검증합니다.

실행 방법:
    pytest tests/test_ingestion_models.py -v
"""

from src.ingestion.models import generate_entity_id


class TestGenerateEntityId:
    """generate_entity_id() 함수 테스트"""

    def test_deterministic_same_input_same_output(self):
        """동일 입력 → 동일 UUID 출력 (결정적 특성)"""
        id1 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동", "email": "hong@example.com"},
        )
        id2 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동", "email": "hong@example.com"},
        )
        assert id1 == id2

    def test_different_label_different_uuid(self):
        """다른 label → 다른 UUID"""
        id1 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동"},
        )
        id2 = generate_entity_id(
            label="Department",
            properties={"name": "홍길동"},
        )
        assert id1 != id2

    def test_different_properties_different_uuid(self):
        """다른 속성 → 다른 UUID (동명이인 구분)"""
        id1 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동", "email": "hong1@example.com"},
        )
        id2 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동", "email": "hong2@example.com"},
        )
        assert id1 != id2

    def test_uuid_format(self):
        """UUID 형식 검증"""
        entity_id = generate_entity_id(
            label="Employee",
            properties={"name": "테스트"},
        )
        # UUID5 형식: xxxxxxxx-xxxx-5xxx-xxxx-xxxxxxxxxxxx
        assert len(entity_id) == 36
        assert entity_id.count("-") == 4
        # UUID5는 버전 5 (5번째 그룹 첫 문자가 5)
        parts = entity_id.split("-")
        assert parts[2][0] == "5"


class TestNaturalKeyPriority:
    """Natural Key 우선순위 테스트"""

    def test_explicit_id_field_priority(self):
        """명시적 ID 필드가 최우선"""
        id_with_explicit = generate_entity_id(
            label="Employee",
            properties={
                "id": "EMP001",
                "email": "test@example.com",
                "name": "테스트",
            },
        )
        id_with_different_explicit = generate_entity_id(
            label="Employee",
            properties={
                "id": "EMP002",
                "email": "test@example.com",
                "name": "테스트",
            },
        )
        # ID 필드가 다르면 UUID도 달라야 함
        assert id_with_explicit != id_with_different_explicit

    def test_employee_id_priority(self):
        """employee_id 필드 우선순위"""
        id1 = generate_entity_id(
            label="Employee",
            properties={
                "employee_id": "EMP001",
                "email": "test@example.com",
                "name": "테스트",
            },
        )
        id2 = generate_entity_id(
            label="Employee",
            properties={
                "employee_id": "EMP001",
                "email": "different@example.com",  # 다른 이메일
                "name": "다른이름",  # 다른 이름
            },
        )
        # employee_id가 같으면 같은 UUID
        assert id1 == id2

    def test_email_priority_over_name(self):
        """email이 name보다 우선"""
        id1 = generate_entity_id(
            label="Employee",
            properties={"email": "same@example.com", "name": "이름1"},
        )
        id2 = generate_entity_id(
            label="Employee",
            properties={"email": "same@example.com", "name": "이름2"},
        )
        # email이 같으면 같은 UUID (name 무시)
        assert id1 == id2

    def test_name_fallback(self):
        """Natural Key가 없으면 name 사용"""
        id1 = generate_entity_id(
            label="Skill",
            properties={"name": "Python"},
        )
        id2 = generate_entity_id(
            label="Skill",
            properties={"name": "Python"},
        )
        assert id1 == id2

        id3 = generate_entity_id(
            label="Skill",
            properties={"name": "Java"},
        )
        assert id1 != id3


class TestEntityResolution:
    """Entity Resolution 테스트 - 다른 소스에서도 같은 엔티티는 같은 UUID"""

    def test_same_entity_from_different_sources(self):
        """다른 소스에서 같은 엔티티 → 같은 UUID (Entity Resolution)"""
        # employees.csv에서 홍길동
        id1 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동", "email": "hong@company.com"},
        )
        # projects.csv에서 같은 홍길동 언급
        id2 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동", "email": "hong@company.com"},
        )
        # 같은 엔티티 → 같은 UUID (source 무관)
        assert id1 == id2

    def test_same_name_different_email_different_uuid(self):
        """동명이인은 email로 구분"""
        id1 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동", "email": "hong1@company.com"},
        )
        id2 = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동", "email": "hong2@company.com"},
        )
        # 동명이인 → 다른 UUID
        assert id1 != id2

    def test_merge_friendly_uuid(self):
        """Neo4j MERGE에 적합한 UUID 생성"""
        # 같은 속성이면 항상 같은 UUID → MERGE가 올바르게 동작
        uuid1 = generate_entity_id(
            label="Department",
            properties={"name": "개발팀"},
        )
        uuid2 = generate_entity_id(
            label="Department",
            properties={"name": "개발팀"},
        )
        assert uuid1 == uuid2
        assert len(uuid1) == 36


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_properties(self):
        """빈 속성으로도 동작"""
        entity_id = generate_entity_id(
            label="Unknown",
            properties={},
        )
        assert entity_id is not None
        assert len(entity_id) == 36

    def test_none_values_in_properties(self):
        """None 값은 무시"""
        id1 = generate_entity_id(
            label="Employee",
            properties={"name": "테스트", "email": None},
        )
        id2 = generate_entity_id(
            label="Employee",
            properties={"name": "테스트"},
        )
        # None 값은 무시되므로 같은 결과
        assert id1 == id2

    def test_korean_names(self):
        """한글 이름 처리"""
        entity_id = generate_entity_id(
            label="Employee",
            properties={"name": "홍길동"},
        )
        assert entity_id is not None
        assert len(entity_id) == 36

    def test_special_characters_in_properties(self):
        """특수 문자 포함 속성"""
        entity_id = generate_entity_id(
            label="Project",
            properties={"name": "AI/ML 프로젝트 (2024)"},
        )
        assert entity_id is not None
        assert len(entity_id) == 36

    def test_numeric_values(self):
        """숫자 값 처리"""
        entity_id = generate_entity_id(
            label="Employee",
            properties={"employee_id": 12345, "name": "테스트"},
        )
        assert entity_id is not None
        # 숫자도 문자열로 변환되어 처리됨

    def test_property_order_independence(self):
        """속성 순서에 무관하게 동일 UUID"""
        id1 = generate_entity_id(
            label="Employee",
            properties={"a": "1", "b": "2", "c": "3"},
        )
        id2 = generate_entity_id(
            label="Employee",
            properties={"c": "3", "a": "1", "b": "2"},
        )
        # Natural Key가 없으면 정렬된 속성으로 UUID 생성
        assert id1 == id2
