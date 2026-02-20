"""
Bootstrap 데이터 모델 테스트

Triple, SchemaProposal, RelationGroup 등 핵심 데이터 모델을 테스트합니다.
"""

import pytest

from src.bootstrap.models import (
    ConfidenceLevel,
    ExtractionResult,
    NormalizationResult,
    RelationGroup,
    SchemaProposal,
    Triple,
)


class TestConfidenceLevel:
    """ConfidenceLevel enum 테스트"""

    def test_from_score_high(self):
        """0.8 이상은 HIGH"""
        assert ConfidenceLevel.from_score(0.8) == ConfidenceLevel.HIGH
        assert ConfidenceLevel.from_score(0.95) == ConfidenceLevel.HIGH
        assert ConfidenceLevel.from_score(1.0) == ConfidenceLevel.HIGH

    def test_from_score_medium(self):
        """0.5 이상 0.8 미만은 MEDIUM"""
        assert ConfidenceLevel.from_score(0.5) == ConfidenceLevel.MEDIUM
        assert ConfidenceLevel.from_score(0.7) == ConfidenceLevel.MEDIUM
        assert ConfidenceLevel.from_score(0.79) == ConfidenceLevel.MEDIUM

    def test_from_score_low(self):
        """0.5 미만은 LOW"""
        assert ConfidenceLevel.from_score(0.0) == ConfidenceLevel.LOW
        assert ConfidenceLevel.from_score(0.3) == ConfidenceLevel.LOW
        assert ConfidenceLevel.from_score(0.49) == ConfidenceLevel.LOW


class TestTriple:
    """Triple 데이터 모델 테스트"""

    def test_create_triple(self):
        """기본 Triple 생성"""
        triple = Triple(
            subject="홍길동",
            relation="참여했다",
            object="AI 프로젝트",
            confidence=0.95,
            source_text="홍길동은 AI 프로젝트에 참여했다.",
        )

        assert triple.subject == "홍길동"
        assert triple.relation == "참여했다"
        assert triple.object == "AI 프로젝트"
        assert triple.confidence == 0.95
        assert triple.confidence_level == ConfidenceLevel.HIGH

    def test_invalid_confidence_raises_error(self):
        """잘못된 confidence 값은 에러"""
        with pytest.raises(ValueError):
            Triple(
                subject="A",
                relation="B",
                object="C",
                confidence=1.5,  # Invalid
                source_text="",
            )

        with pytest.raises(ValueError):
            Triple(
                subject="A",
                relation="B",
                object="C",
                confidence=-0.1,  # Invalid
                source_text="",
            )

    def test_to_dict(self):
        """딕셔너리 변환"""
        triple = Triple(
            subject="A",
            relation="R",
            object="B",
            confidence=0.8,
            source_text="text",
            metadata={"key": "value"},
        )

        d = triple.to_dict()
        assert d["subject"] == "A"
        assert d["relation"] == "R"
        assert d["object"] == "B"
        assert d["confidence"] == 0.8
        assert d["metadata"] == {"key": "value"}

    def test_from_dict(self):
        """딕셔너리에서 생성"""
        data = {
            "subject": "X",
            "relation": "Y",
            "object": "Z",
            "confidence": 0.7,
            "source_text": "test",
        }

        triple = Triple.from_dict(data)
        assert triple.subject == "X"
        assert triple.relation == "Y"
        assert triple.confidence == 0.7


class TestSchemaProposal:
    """SchemaProposal 테스트"""

    def test_create_schema(self):
        """기본 스키마 생성"""
        schema = SchemaProposal(
            node_labels=["Employee", "Project"],
            relationship_types=["WORKS_ON", "MANAGES"],
            properties={"Employee": ["name", "email"]},
        )

        assert "Employee" in schema.node_labels
        assert "WORKS_ON" in schema.relationship_types
        assert "Employee" in schema.properties

    def test_label_normalization_pascal_case(self):
        """노드 라벨 PascalCase 정규화"""
        schema = SchemaProposal(
            node_labels=["person", "my_project", "skill category"],
            relationship_types=[],
            properties={},
        )

        assert "Person" in schema.node_labels
        assert "MyProject" in schema.node_labels
        assert "SkillCategory" in schema.node_labels

    def test_relationship_normalization_screaming_snake(self):
        """관계 타입 SCREAMING_SNAKE_CASE 정규화"""
        schema = SchemaProposal(
            node_labels=[],
            relationship_types=["worksOn", "hasSkill", "reports-to"],
            properties={},
        )

        assert "WORKS_ON" in schema.relationship_types
        assert "HAS_SKILL" in schema.relationship_types
        assert "REPORTS_TO" in schema.relationship_types

    def test_to_cypher_constraints(self):
        """Cypher 제약조건 생성"""
        schema = SchemaProposal(
            node_labels=["Employee"],
            relationship_types=[],
            properties={},
            constraints={"Employee": ["email", "employeeId"]},
        )

        constraints = schema.to_cypher_constraints()
        assert len(constraints) == 2
        assert "Employee" in constraints[0]
        assert "IS UNIQUE" in constraints[0]

    def test_get_schema_summary(self):
        """스키마 요약 생성"""
        schema = SchemaProposal(
            node_labels=["Employee", "Project"],
            relationship_types=["WORKS_ON"],
            properties={"Employee": ["name"]},
            reasoning="Test reasoning",
        )

        summary = schema.get_schema_summary()
        assert "Employee" in summary
        assert "Project" in summary
        assert "WORKS_ON" in summary
        assert "Test reasoning" in summary

    def test_to_dict_from_dict_roundtrip(self):
        """딕셔너리 변환 왕복 테스트"""
        original = SchemaProposal(
            node_labels=["Employee"],
            relationship_types=["KNOWS"],
            properties={"Employee": ["name"]},
            constraints={"Employee": ["email"]},
            confidence=0.9,
            reasoning="test",
        )

        restored = SchemaProposal.from_dict(original.to_dict())
        assert restored.node_labels == original.node_labels
        assert restored.relationship_types == original.relationship_types
        assert restored.confidence == original.confidence


class TestRelationGroup:
    """RelationGroup 테스트"""

    def test_create_group(self):
        """기본 그룹 생성"""
        group = RelationGroup(
            canonical_name="MANAGES",
            variants=["담당했다", "책임졌다"],
            frequency=10,
        )

        assert group.canonical_name == "MANAGES"
        assert len(group.variants) == 2
        assert group.frequency == 10

    def test_canonical_name_normalization(self):
        """대표 이름 정규화"""
        group = RelationGroup(
            canonical_name="works on",
            variants=[],
        )

        assert group.canonical_name == "WORKS_ON"

    def test_add_variant(self):
        """변형 추가"""
        group = RelationGroup(
            canonical_name="TEST",
            variants=["a"],
            frequency=1,
        )

        group.add_variant("b")
        assert "b" in group.variants
        assert group.frequency == 2

        # 중복 추가 시 variants에는 추가 안됨
        group.add_variant("b")
        assert group.variants.count("b") == 1
        assert group.frequency == 3  # 빈도는 증가

    def test_to_dict_from_dict_roundtrip(self):
        """딕셔너리 변환 왕복"""
        original = RelationGroup(
            canonical_name="TEST",
            variants=["a", "b"],
            frequency=5,
            description="Test group",
        )

        restored = RelationGroup.from_dict(original.to_dict())
        assert restored.canonical_name == original.canonical_name
        assert restored.variants == original.variants


class TestExtractionResult:
    """ExtractionResult 테스트"""

    def test_add_triples(self):
        """트리플 추가"""
        result = ExtractionResult()
        triples = [
            Triple("A", "R1", "B", 0.9, "text1"),
            Triple("C", "R2", "D", 0.7, "text2"),
        ]

        result.add_triples(triples)
        assert len(result.triples) == 2

    def test_get_relation_frequencies(self):
        """관계 빈도 계산"""
        result = ExtractionResult(
            triples=[
                Triple("A", "R1", "B", 0.9, ""),
                Triple("C", "R1", "D", 0.9, ""),
                Triple("E", "R2", "F", 0.9, ""),
            ]
        )

        freq = result.get_relation_frequencies()
        assert freq["R1"] == 2
        assert freq["R2"] == 1

    def test_filter_by_confidence(self):
        """신뢰도 필터링"""
        result = ExtractionResult(
            triples=[
                Triple("A", "R", "B", 0.9, ""),
                Triple("C", "R", "D", 0.4, ""),
                Triple("E", "R", "F", 0.6, ""),
            ]
        )

        filtered = result.filter_by_confidence(0.5)
        assert len(filtered) == 2


class TestNormalizationResult:
    """NormalizationResult 테스트"""

    def test_get_canonical(self):
        """대표 이름 조회"""
        result = NormalizationResult(
            mapping={"담당했다": "MANAGES", "책임졌다": "MANAGES"}
        )

        assert result.get_canonical("담당했다") == "MANAGES"
        assert result.get_canonical("unknown") is None

    def test_normalize_triple(self):
        """트리플 정규화"""
        result = NormalizationResult(mapping={"참여했다": "WORKS_ON"})

        original = Triple("A", "참여했다", "B", 0.9, "text")
        normalized = result.normalize_triple(original)

        assert normalized.relation == "WORKS_ON"
        assert normalized.metadata.get("original_relation") == "참여했다"

    def test_normalize_triple_unmapped(self):
        """미매핑 트리플은 그대로"""
        result = NormalizationResult(mapping={})

        original = Triple("A", "unknown", "B", 0.9, "text")
        normalized = result.normalize_triple(original)

        assert normalized.relation == "unknown"
