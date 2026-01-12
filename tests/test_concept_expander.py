"""
ConceptExpanderNode 테스트

Neo4j 의존성 없이 독립적으로 테스트 가능하도록 설계
"""

import pytest

from src.domain.ontology.loader import ExpansionConfig, OntologyLoader


# ConceptExpanderNode의 ENTITY_TO_CATEGORY 매핑 (직접 정의)
ENTITY_TO_CATEGORY: dict[str, str] = {
    "Skill": "skills",
    "Position": "positions",
    "Department": "departments",
}


class TestConceptExpander:
    """ConceptExpanderNode 로직 테스트"""

    @pytest.fixture
    def loader(self) -> OntologyLoader:
        """OntologyLoader 인스턴스"""
        return OntologyLoader()

    # =========================================================================
    # 스킬 확장 테스트
    # =========================================================================

    def test_expand_skill_korean(self, loader: OntologyLoader):
        """한글 스킬 확장"""
        entities = {"Skill": ["파이썬"]}
        expanded = self._expand_entities(entities, loader)

        assert "Skill" in expanded
        assert "Python" in expanded["Skill"]
        assert "파이썬" in expanded["Skill"]
        assert "Python3" in expanded["Skill"]

    def test_expand_skill_english(self, loader: OntologyLoader):
        """영문 스킬 확장"""
        entities = {"Skill": ["React"]}
        expanded = self._expand_entities(entities, loader)

        assert "Skill" in expanded
        assert "React" in expanded["Skill"]
        assert "리액트" in expanded["Skill"]

    def test_expand_multiple_skills(self, loader: OntologyLoader):
        """복수 스킬 확장"""
        entities = {"Skill": ["파이썬", "React"]}
        expanded = self._expand_entities(entities, loader)

        assert "Skill" in expanded
        # Python 관련
        assert "Python" in expanded["Skill"]
        # React 관련
        assert "리액트" in expanded["Skill"]

    # =========================================================================
    # 직급 확장 테스트
    # =========================================================================

    def test_expand_position_korean(self, loader: OntologyLoader):
        """한글 직급 확장"""
        entities = {"Position": ["백엔드 개발자"]}
        expanded = self._expand_entities(entities, loader)

        assert "Position" in expanded
        assert "Backend Developer" in expanded["Position"]
        assert "서버 개발자" in expanded["Position"]

    def test_expand_position_english(self, loader: OntologyLoader):
        """영문 직급 확장"""
        entities = {"Position": ["ML Engineer"]}
        expanded = self._expand_entities(entities, loader)

        assert "Position" in expanded
        assert "ML Engineer" in expanded["Position"]
        assert "머신러닝 엔지니어" in expanded["Position"]

    # =========================================================================
    # 매핑되지 않은 엔티티 타입 테스트
    # =========================================================================

    def test_passthrough_unmapped_entity(self, loader: OntologyLoader):
        """매핑되지 않은 엔티티 타입은 그대로 전달"""
        entities = {"Person": ["홍길동"]}
        expanded = self._expand_entities(entities, loader)

        assert "Person" in expanded
        assert expanded["Person"] == ["홍길동"]

    def test_mixed_entity_types(self, loader: OntologyLoader):
        """혼합 엔티티 타입 (일부만 확장)"""
        entities = {
            "Skill": ["파이썬"],
            "Person": ["홍길동"],  # 매핑 없음
            "Date": ["2024-01-01"],  # 매핑 없음
        }
        expanded = self._expand_entities(entities, loader)

        # Skill은 확장됨
        assert "Python" in expanded["Skill"]
        # Person, Date는 그대로
        assert expanded["Person"] == ["홍길동"]
        assert expanded["Date"] == ["2024-01-01"]

    # =========================================================================
    # 빈 입력 테스트
    # =========================================================================

    def test_empty_entities(self, loader: OntologyLoader):
        """빈 엔티티 처리"""
        entities: dict[str, list[str]] = {}
        expanded = self._expand_entities(entities, loader)

        assert expanded == {}

    def test_empty_values(self, loader: OntologyLoader):
        """빈 값 리스트 처리"""
        entities = {"Skill": []}
        expanded = self._expand_entities(entities, loader)

        assert expanded["Skill"] == []

    # =========================================================================
    # 알 수 없는 용어 테스트
    # =========================================================================

    def test_unknown_skill(self, loader: OntologyLoader):
        """온톨로지에 없는 스킬"""
        entities = {"Skill": ["UnknownFramework"]}
        expanded = self._expand_entities(entities, loader)

        # 원본 유지
        assert "UnknownFramework" in expanded["Skill"]

    def test_unknown_position(self, loader: OntologyLoader):
        """온톨로지에 없는 직급"""
        entities = {"Position": ["Chief Happiness Officer"]}
        expanded = self._expand_entities(entities, loader)

        # 원본 유지
        assert "Chief Happiness Officer" in expanded["Position"]

    # =========================================================================
    # 확장 옵션 테스트
    # =========================================================================

    def test_no_synonyms(self, loader: OntologyLoader):
        """동의어 없이 확장"""
        entities = {"Skill": ["Backend"]}
        config = ExpansionConfig(include_synonyms=False, include_children=True)
        expanded = self._expand_entities(entities, loader, config)

        assert "Python" in expanded["Skill"]
        assert "Java" in expanded["Skill"]

    def test_no_children(self, loader: OntologyLoader):
        """하위 개념 없이 확장"""
        entities = {"Skill": ["파이썬"]}
        config = ExpansionConfig(include_synonyms=True, include_children=False)
        expanded = self._expand_entities(entities, loader, config)

        assert "Python" in expanded["Skill"]
        assert "Python3" in expanded["Skill"]

    # =========================================================================
    # 헬퍼 메서드
    # =========================================================================

    def _expand_entities(
        self,
        entities: dict[str, list[str]],
        loader: OntologyLoader,
        config: ExpansionConfig | None = None,
    ) -> dict[str, list[str]]:
        """ConceptExpanderNode._process() 로직 재현"""
        expanded_entities: dict[str, list[str]] = {}

        for entity_type, values in entities.items():
            category = ENTITY_TO_CATEGORY.get(entity_type)

            if category is None:
                expanded_entities[entity_type] = list(values)
                continue

            expanded_values: set[str] = set()
            for value in values:
                expanded_values.update(
                    loader.expand_concept(value, category, config)
                )

            expanded_entities[entity_type] = list(expanded_values)

        return expanded_entities
