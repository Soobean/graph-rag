"""
OntologyLoader 테스트
"""

from pathlib import Path

import pytest

from src.domain.ontology.loader import (
    DEFAULT_EXPANSION_CONFIG,
    ExpansionConfig,
    OntologyLoader,
)


class TestOntologyLoader:
    """OntologyLoader 테스트"""

    @pytest.fixture
    def loader(self) -> OntologyLoader:
        """기본 로더 인스턴스 (실제 YAML 파일 사용)"""
        return OntologyLoader()

    # =========================================================================
    # YAML 로드 테스트
    # =========================================================================

    def test_load_schema(self, loader: OntologyLoader):
        """schema.yaml 로드"""
        schema = loader.load_schema()

        assert schema is not None
        assert "concepts" in schema
        assert "SkillCategory" in schema["concepts"]
        assert "relations" in schema

    def test_load_synonyms(self, loader: OntologyLoader):
        """synonyms.yaml 로드"""
        synonyms = loader.load_synonyms()

        assert synonyms is not None
        assert "skills" in synonyms
        assert "positions" in synonyms

    def test_load_nonexistent_directory(self, tmp_path: Path):
        """존재하지 않는 디렉토리 처리"""
        # 존재하지 않는 디렉토리는 ValueError 발생
        with pytest.raises(ValueError, match="Directory does not exist"):
            OntologyLoader(tmp_path / "nonexistent")

    # =========================================================================
    # 동의어 조회 테스트
    # =========================================================================

    def test_get_canonical_korean(self, loader: OntologyLoader):
        """한글 → 정규화된 이름"""
        canonical = loader.get_canonical("파이썬", "skills")
        assert canonical == "Python"

    def test_get_canonical_alias(self, loader: OntologyLoader):
        """별칭 → 정규화된 이름"""
        canonical = loader.get_canonical("Python3", "skills")
        assert canonical == "Python"

    def test_get_canonical_already_canonical(self, loader: OntologyLoader):
        """이미 정규화된 이름"""
        canonical = loader.get_canonical("Python", "skills")
        assert canonical == "Python"

    def test_get_canonical_case_insensitive(self, loader: OntologyLoader):
        """대소문자 무시"""
        canonical = loader.get_canonical("python", "skills")
        assert canonical == "Python"

    def test_get_canonical_not_found(self, loader: OntologyLoader):
        """찾지 못한 경우 원본 반환"""
        canonical = loader.get_canonical("UnknownSkill", "skills")
        assert canonical == "UnknownSkill"

    def test_get_synonyms_from_korean(self, loader: OntologyLoader):
        """한글에서 동의어 조회"""
        synonyms = loader.get_synonyms("파이썬", "skills")

        assert "Python" in synonyms
        assert "파이썬" in synonyms
        assert "Python3" in synonyms

    def test_get_synonyms_from_canonical(self, loader: OntologyLoader):
        """정규화된 이름에서 동의어 조회"""
        synonyms = loader.get_synonyms("Python", "skills")

        assert "Python" in synonyms
        assert "파이썬" in synonyms

    def test_get_synonyms_positions(self, loader: OntologyLoader):
        """직급 동의어 조회"""
        synonyms = loader.get_synonyms("백엔드 개발자", "positions")

        assert "Backend Developer" in synonyms
        assert "서버 개발자" in synonyms

    def test_get_synonyms_not_found(self, loader: OntologyLoader):
        """찾지 못한 경우 원본만 반환"""
        synonyms = loader.get_synonyms("UnknownTerm", "skills")

        assert synonyms == ["UnknownTerm"]

    # =========================================================================
    # 하위 개념 조회 테스트
    # =========================================================================

    def test_get_children_backend(self, loader: OntologyLoader):
        """Backend 하위 스킬 조회"""
        children = loader.get_children("Backend", "skills")

        assert "Python" in children
        assert "Java" in children
        assert "Node.js" in children

    def test_get_children_programming(self, loader: OntologyLoader):
        """Programming 전체 하위 스킬 조회"""
        children = loader.get_children("Programming", "skills")

        # Backend + Frontend + AI/ML + Data 스킬들
        assert "Python" in children
        assert "React" in children
        assert "ML" in children

    def test_get_children_cloud(self, loader: OntologyLoader):
        """Cloud 하위 스킬 조회"""
        children = loader.get_children("Cloud", "skills")

        assert "AWS" in children
        assert "GCP" in children
        assert "Azure" in children

    def test_get_children_not_found(self, loader: OntologyLoader):
        """존재하지 않는 개념"""
        children = loader.get_children("UnknownCategory", "skills")

        assert children == []

    # =========================================================================
    # 통합 개념 확장 테스트
    # =========================================================================

    def test_expand_concept_korean_skill(self, loader: OntologyLoader):
        """한글 스킬 확장"""
        expanded = loader.expand_concept("파이썬", "skills")

        # 동의어 포함
        assert "Python" in expanded
        assert "파이썬" in expanded
        assert "Python3" in expanded

    def test_expand_concept_category(self, loader: OntologyLoader):
        """카테고리 확장 (하위 개념 포함)"""
        expanded = loader.expand_concept("Backend", "skills")

        # 카테고리 자체
        assert "Backend" in expanded
        # 하위 스킬들
        assert "Python" in expanded
        assert "Java" in expanded

    def test_expand_concept_no_synonyms(self, loader: OntologyLoader):
        """동의어 없이 확장"""
        config = ExpansionConfig(include_synonyms=False, include_children=True)
        expanded = loader.expand_concept("Backend", "skills", config=config)

        assert "Backend" in expanded
        assert "Python" in expanded

    def test_expand_concept_no_children(self, loader: OntologyLoader):
        """하위 개념 없이 확장"""
        config = ExpansionConfig(include_synonyms=True, include_children=False)
        expanded = loader.expand_concept("파이썬", "skills", config=config)

        assert "Python" in expanded
        assert "파이썬" in expanded

    def test_expand_concept_unknown(self, loader: OntologyLoader):
        """알 수 없는 개념 확장"""
        expanded = loader.expand_concept("UnknownSkill", "skills")

        # 원본만 반환
        assert expanded == ["UnknownSkill"]

    # =========================================================================
    # 캐싱 테스트
    # =========================================================================

    def test_schema_cached(self, loader: OntologyLoader):
        """스키마 캐싱 확인"""
        schema1 = loader.load_schema()
        schema2 = loader.load_schema()

        assert schema1 is schema2  # 같은 객체

    def test_synonyms_cached(self, loader: OntologyLoader):
        """동의어 캐싱 확인"""
        synonyms1 = loader.load_synonyms()
        synonyms2 = loader.load_synonyms()

        assert synonyms1 is synonyms2  # 같은 객체


class TestExpansionConfig:
    """ExpansionConfig 테스트"""

    def test_default_config(self):
        """기본 설정값 확인"""
        config = ExpansionConfig()

        assert config.max_synonyms == 5
        assert config.max_children == 10
        assert config.max_total == 15
        assert config.include_synonyms is True
        assert config.include_children is True

    def test_custom_config(self):
        """사용자 정의 설정"""
        config = ExpansionConfig(
            max_synonyms=3,
            max_children=5,
            max_total=8,
        )

        assert config.max_synonyms == 3
        assert config.max_children == 5
        assert config.max_total == 8

    def test_invalid_max_synonyms(self):
        """잘못된 max_synonyms 값"""
        with pytest.raises(ValueError, match="max_synonyms must be non-negative"):
            ExpansionConfig(max_synonyms=-1)

    def test_invalid_max_children(self):
        """잘못된 max_children 값"""
        with pytest.raises(ValueError, match="max_children must be non-negative"):
            ExpansionConfig(max_children=-1)

    def test_invalid_max_total(self):
        """잘못된 max_total 값"""
        with pytest.raises(ValueError, match="max_total must be at least 1"):
            ExpansionConfig(max_total=0)

    def test_default_expansion_config_singleton(self):
        """전역 기본 설정 확인"""
        assert DEFAULT_EXPANSION_CONFIG.max_synonyms == 5
        assert DEFAULT_EXPANSION_CONFIG.max_total == 15


class TestExpansionLimit:
    """확장 제한 테스트"""

    @pytest.fixture
    def loader(self) -> OntologyLoader:
        """기본 로더 인스턴스"""
        return OntologyLoader()

    def test_expand_with_config(self, loader: OntologyLoader):
        """config 파라미터 사용"""
        # max_total >= max(max_synonyms, max_children) 조건 만족 필요
        config = ExpansionConfig(max_synonyms=2, max_children=2, max_total=3)
        expanded = loader.expand_concept("Backend", "skills", config=config)

        assert len(expanded) <= 3

    def test_expand_with_strict_limit(self, loader: OntologyLoader):
        """매우 제한적인 설정"""
        config = ExpansionConfig(
            max_synonyms=1,
            max_children=2,
            max_total=3,
        )
        expanded = loader.expand_concept("Backend", "skills", config=config)

        assert len(expanded) <= 3

    def test_expand_unlimited(self, loader: OntologyLoader):
        """높은 제한값 (사실상 무제한)"""
        config = ExpansionConfig(
            max_synonyms=100,
            max_children=100,
            max_total=200,
        )
        expanded = loader.expand_concept("Backend", "skills", config=config)

        # Backend 하위에 Python, Java, Node.js, Go, Kotlin, Spring 등이 있음
        assert "Backend" in expanded
        assert "Python" in expanded
        assert "Java" in expanded

    def test_expand_default_config(self, loader: OntologyLoader):
        """기본 설정 (max_total=15) 적용"""
        # Backend 카테고리는 하위 스킬이 많음
        expanded = loader.expand_concept("Backend", "skills")

        # 기본 max_total=15 적용
        assert len(expanded) <= 15

    def test_expand_synonyms_only(self, loader: OntologyLoader):
        """동의어만 확장 (하위 개념 제외)"""
        config = ExpansionConfig(
            include_synonyms=True,
            include_children=False,
            max_synonyms=10,
        )
        expanded = loader.expand_concept("파이썬", "skills", config=config)

        # 동의어만 포함
        assert "Python" in expanded
        assert "파이썬" in expanded
        # Backend 같은 하위 개념은 없어야 함 (Python은 하위 개념이 없음)

    def test_expand_preserves_original_term(self, loader: OntologyLoader):
        """원본 용어는 항상 포함"""
        # max_total >= max(max_synonyms, max_children) 조건 만족 필요
        config = ExpansionConfig(max_synonyms=0, max_children=0, max_total=1)
        expanded = loader.expand_concept("SomeUnknownTerm", "skills", config=config)

        assert "SomeUnknownTerm" in expanded

    def test_expand_with_config_no_children(self, loader: OntologyLoader):
        """config로 하위 개념 제외"""
        config = ExpansionConfig(include_synonyms=True, include_children=False)
        expanded = loader.expand_concept("파이썬", "skills", config=config)

        assert "Python" in expanded
        assert "파이썬" in expanded


class TestExpansionStrategy:
    """ExpansionStrategy 테스트 (Phase 3)"""

    def test_strategy_enum_values(self):
        """전략 enum 값 확인"""
        from src.domain.ontology.loader import ExpansionStrategy

        assert ExpansionStrategy.STRICT.value == "strict"
        assert ExpansionStrategy.NORMAL.value == "normal"
        assert ExpansionStrategy.BROAD.value == "broad"

    def test_get_strategy_for_intent_normal(self):
        """일반 의도에 대한 전략"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_strategy_for_intent,
        )

        # personnel_search → NORMAL
        strategy = get_strategy_for_intent("personnel_search", 0.7)
        assert strategy == ExpansionStrategy.NORMAL

    def test_get_strategy_for_intent_strict(self):
        """정확한 매칭이 필요한 의도"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_strategy_for_intent,
        )

        # project_matching → STRICT
        strategy = get_strategy_for_intent("project_matching", 0.8)
        assert strategy == ExpansionStrategy.STRICT

    def test_get_strategy_for_intent_broad(self):
        """넓은 검색이 필요한 의도"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_strategy_for_intent,
        )

        # relationship_search → BROAD
        strategy = get_strategy_for_intent("relationship_search", 0.7)
        assert strategy == ExpansionStrategy.BROAD

    def test_get_strategy_low_confidence(self):
        """신뢰도 낮으면 기본 전략 유지 (보수적 접근)"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_strategy_for_intent,
        )

        # 신뢰도 < 0.5 → 기본 전략 유지 (personnel_search는 NORMAL)
        strategy = get_strategy_for_intent("personnel_search", 0.3)
        assert strategy == ExpansionStrategy.NORMAL

    def test_get_strategy_high_confidence(self):
        """신뢰도 높으면 좁게"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_strategy_for_intent,
        )

        # 신뢰도 > 0.9 + BROAD → NORMAL
        strategy = get_strategy_for_intent("relationship_search", 0.95)
        assert strategy == ExpansionStrategy.NORMAL

        # 신뢰도 > 0.9 + NORMAL → NORMAL (유지)
        strategy = get_strategy_for_intent("personnel_search", 0.95)
        assert strategy == ExpansionStrategy.NORMAL

    def test_get_strategy_unknown_intent(self):
        """알 수 없는 의도는 NORMAL"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_strategy_for_intent,
        )

        strategy = get_strategy_for_intent("unknown", 0.7)
        assert strategy == ExpansionStrategy.NORMAL

    def test_get_config_for_strategy_strict(self):
        """STRICT 전략 config"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_config_for_strategy,
        )

        config = get_config_for_strategy(ExpansionStrategy.STRICT)
        assert config.include_children is False
        assert config.max_total == 5

    def test_get_config_for_strategy_normal(self):
        """NORMAL 전략 config"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_config_for_strategy,
        )

        config = get_config_for_strategy(ExpansionStrategy.NORMAL)
        assert config.include_children is True
        assert config.max_total == 15

    def test_get_config_for_strategy_broad(self):
        """BROAD 전략 config"""
        from src.domain.ontology.loader import (
            ExpansionStrategy,
            get_config_for_strategy,
        )

        config = get_config_for_strategy(ExpansionStrategy.BROAD)
        assert config.include_children is True
        assert config.max_total == 30

    def test_intent_strategy_map_completeness(self):
        """모든 IntentType에 대한 매핑 존재"""
        from src.domain.ontology.loader import INTENT_STRATEGY_MAP

        expected_intents = [
            "personnel_search",
            "project_matching",
            "relationship_search",
            "org_info",
            "skill_search",
            "count_query",
            "unknown",
        ]

        for intent in expected_intents:
            assert intent in INTENT_STRATEGY_MAP, f"Missing mapping for {intent}"


class TestWeightBasedExpansion:
    """가중치 기반 확장 테스트 (Phase 5)"""

    @pytest.fixture
    def loader(self) -> OntologyLoader:
        """기본 로더 인스턴스"""
        return OntologyLoader()

    def test_expansion_config_min_weight_default(self):
        """기본 min_weight는 0.0 (필터링 없음)"""
        config = ExpansionConfig()
        assert config.min_weight == 0.0
        assert config.sort_by_weight is True

    def test_expansion_config_min_weight_validation(self):
        """min_weight 유효성 검사"""
        # 유효한 값
        config = ExpansionConfig(min_weight=0.5)
        assert config.min_weight == 0.5

        # 경계값
        config = ExpansionConfig(min_weight=0.0)
        assert config.min_weight == 0.0

        config = ExpansionConfig(min_weight=1.0)
        assert config.min_weight == 1.0

    def test_expansion_config_invalid_min_weight(self):
        """잘못된 min_weight 값"""
        with pytest.raises(ValueError, match="min_weight must be between"):
            ExpansionConfig(min_weight=-0.1)

        with pytest.raises(ValueError, match="min_weight must be between"):
            ExpansionConfig(min_weight=1.1)

    def test_get_synonyms_with_weights_python(self, loader: OntologyLoader):
        """Python 동의어와 가중치 조회"""
        synonyms = loader.get_synonyms_with_weights("Python", "skills")

        # canonical은 항상 weight=1.0
        assert ("Python", 1.0) in synonyms

        # 가중치가 있는 동의어 확인
        weights_dict = dict(synonyms)
        assert "파이썬" in weights_dict
        assert weights_dict["파이썬"] == 1.0  # 한글 정규 표현
        assert "Py" in weights_dict
        assert weights_dict["Py"] == 0.6  # 축약형

    def test_get_synonyms_with_weights_korean(self, loader: OntologyLoader):
        """한글 검색어로 동의어와 가중치 조회"""
        synonyms = loader.get_synonyms_with_weights("파이썬", "skills")

        # canonical Python이 포함되어야 함
        names = [s[0] for s in synonyms]
        assert "Python" in names

    def test_get_synonyms_with_weights_unknown(self, loader: OntologyLoader):
        """알 수 없는 용어는 (term, 1.0) 반환"""
        synonyms = loader.get_synonyms_with_weights("UnknownSkill", "skills")

        assert len(synonyms) == 1
        assert synonyms[0] == ("UnknownSkill", 1.0)

    def test_expand_with_min_weight_filter(self, loader: OntologyLoader):
        """min_weight 임계값 필터링"""
        # 낮은 가중치 동의어도 포함 (기본값)
        config_no_filter = ExpansionConfig(min_weight=0.0)
        expanded_all = loader.expand_concept("Python", "skills", config_no_filter)

        # 높은 임계값으로 필터링
        config_filtered = ExpansionConfig(min_weight=0.7)
        expanded_filtered = loader.expand_concept("Python", "skills", config_filtered)

        # 필터링된 결과가 더 적어야 함
        assert len(expanded_filtered) <= len(expanded_all)

        # Py(0.6)는 min_weight=0.7에서 제외되어야 함
        assert "Py" in expanded_all
        assert "Py" not in expanded_filtered

    def test_expand_with_sort_by_weight(self, loader: OntologyLoader):
        """가중치 기준 정렬 확인"""
        config = ExpansionConfig(sort_by_weight=True, include_children=False)
        expanded = loader.expand_concept("Python", "skills", config)

        # 원본 term은 항상 첫 번째
        assert expanded[0] == "Python"

        # Python 이후 가중치 순서 확인 (높은 것이 먼저)
        # 파이썬(1.0), Python3(0.9), Py(0.6), python(0.4)
        # 단, Python은 canonical이므로 별도 처리됨

    def test_expand_backward_compatibility(self, loader: OntologyLoader):
        """하위호환: 기존 config로 동작"""
        config = ExpansionConfig()  # 기본값
        expanded = loader.expand_concept("JavaScript", "skills", config)

        # 기존처럼 동의어가 포함되어야 함
        assert "JavaScript" in expanded
        assert "자바스크립트" in expanded or "JS" in expanded

    def test_expand_mixed_yaml_format(self, loader: OntologyLoader):
        """혼합 YAML 형식 (str + dict) 지원"""
        # TypeScript는 기존 형식(문자열만)
        expanded = loader.expand_concept("TypeScript", "skills")

        # 기존 형식도 정상 동작해야 함
        assert "TypeScript" in expanded
        assert "TS" in expanded or "타입스크립트" in expanded

    def test_get_synonyms_preserves_order_with_weights(self, loader: OntologyLoader):
        """get_synonyms()는 가중치 순서를 유지"""
        # get_synonyms는 내부적으로 get_synonyms_with_weights 사용
        synonyms = loader.get_synonyms("Python", "skills")

        # 원래 순서대로 반환 (가중치 정렬은 expand_concept에서만)
        assert "Python" in synonyms
        assert len(synonyms) >= 3  # Python, 파이썬, Python3, Py, python 등
