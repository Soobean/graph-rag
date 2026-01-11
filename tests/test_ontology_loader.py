"""
OntologyLoader 테스트
"""

from pathlib import Path

import pytest

from src.domain.ontology.loader import OntologyLoader


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
        loader = OntologyLoader(tmp_path / "nonexistent")

        # 빈 dict 반환 (에러 아님)
        schema = loader.load_schema()
        assert schema == {}

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
        expanded = loader.expand_concept(
            "Backend", "skills", include_synonyms=False
        )

        assert "Backend" in expanded
        assert "Python" in expanded

    def test_expand_concept_no_children(self, loader: OntologyLoader):
        """하위 개념 없이 확장"""
        expanded = loader.expand_concept(
            "파이썬", "skills", include_children=False
        )

        # 동의어만 포함
        assert "Python" in expanded
        assert "파이썬" in expanded

    def test_expand_concept_unknown(self, loader: OntologyLoader):
        """알 수 없는 개념 확장"""
        expanded = loader.expand_concept("UnknownSkill", "skills")

        # 원본만 반환
        assert expanded == ["UnknownSkill"]

    # =========================================================================
    # 확장 규칙 테스트
    # =========================================================================

    def test_get_expansion_rules(self, loader: OntologyLoader):
        """확장 규칙 조회"""
        rules = loader.get_expansion_rules()

        assert "default_depth" in rules
        assert "include_synonyms" in rules
        assert "include_children" in rules

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
