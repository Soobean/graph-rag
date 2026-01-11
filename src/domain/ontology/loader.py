"""
Ontology Loader

YAML 기반 온톨로지 스키마 및 동의어 사전 로더
- 개념 계층 조회 (IS_A 관계)
- 동의어 조회 (SAME_AS 관계, 양방향)
- 개념 확장 (동의어 + 하위 개념)
- 확장 제한 (오버 확장 방지)
"""

import logging
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# =============================================================================
# 확장 전략 (Phase 3: 컨텍스트 기반 확장)
# =============================================================================


class ExpansionStrategy(Enum):
    """
    개념 확장 전략

    질문의 의도(Intent)에 따라 확장 범위를 조절합니다.

    Examples:
        - STRICT: "Python 시니어 찾아줘" → 정확한 매칭 필요
        - NORMAL: "Python 개발자 찾아줘" → 동의어 + 1단계 계층
        - BROAD: "Backend 관련 인력" → 넓은 확장 필요
    """

    STRICT = "strict"  # 동의어만 (정확한 검색)
    NORMAL = "normal"  # 동의어 + 1단계 하위 개념 (기본값)
    BROAD = "broad"    # 동의어 + 전체 하위 개념 (넓은 검색)


# Intent → Strategy 매핑 (기본값)
INTENT_STRATEGY_MAP: dict[str, ExpansionStrategy] = {
    # 인원 검색: 일반적인 확장
    "personnel_search": ExpansionStrategy.NORMAL,

    # 프로젝트 매칭: 정확한 스킬 필요
    "project_matching": ExpansionStrategy.STRICT,

    # 관계 검색: 넓은 확장 (팀 구성, 협업 관계 등)
    "relationship_search": ExpansionStrategy.BROAD,

    # 조직 정보: 정확한 매칭
    "org_info": ExpansionStrategy.STRICT,

    # 스킬 검색: 넓은 확장
    "skill_search": ExpansionStrategy.BROAD,

    # 카운트 쿼리: 일반 확장
    "count_query": ExpansionStrategy.NORMAL,

    # 알 수 없는 의도: 일반 확장
    "unknown": ExpansionStrategy.NORMAL,
}


def get_strategy_for_intent(
    intent: str,
    confidence: float = 1.0,
) -> ExpansionStrategy:
    """
    Intent와 신뢰도에 따른 확장 전략 결정

    Args:
        intent: 질문 의도 (예: "personnel_search", "project_matching")
        confidence: 의도 분류 신뢰도 (0.0 ~ 1.0)

    Returns:
        적절한 ExpansionStrategy

    Examples:
        >>> get_strategy_for_intent("personnel_search", 0.95)
        ExpansionStrategy.NORMAL

        >>> get_strategy_for_intent("unknown", 0.3)
        ExpansionStrategy.BROAD  # 신뢰도 낮으면 넓게 확장
    """
    # 신뢰도 기반 조정
    if confidence < 0.5:
        # 신뢰도 낮으면 넓게 확장 (불확실성 대응)
        return ExpansionStrategy.BROAD

    if confidence > 0.9:
        # 신뢰도 높으면 좁게 확장 (정확한 의도 파악)
        base_strategy = INTENT_STRATEGY_MAP.get(intent, ExpansionStrategy.NORMAL)
        # BROAD → NORMAL로 한 단계 좁힘 (NORMAL, STRICT는 유지)
        if base_strategy == ExpansionStrategy.BROAD:
            return ExpansionStrategy.NORMAL
        return base_strategy

    # 일반적인 경우: Intent 매핑 사용
    return INTENT_STRATEGY_MAP.get(intent, ExpansionStrategy.NORMAL)


def get_config_for_strategy(strategy: ExpansionStrategy) -> "ExpansionConfig":
    """
    확장 전략에 따른 ExpansionConfig 반환

    Args:
        strategy: 확장 전략

    Returns:
        해당 전략에 맞는 ExpansionConfig
    """
    if strategy == ExpansionStrategy.STRICT:
        return ExpansionConfig(
            max_synonyms=5,
            max_children=0,  # 하위 개념 제외
            max_total=5,
            include_synonyms=True,
            include_children=False,
        )
    elif strategy == ExpansionStrategy.BROAD:
        return ExpansionConfig(
            max_synonyms=10,
            max_children=20,
            max_total=30,
            include_synonyms=True,
            include_children=True,
        )
    else:  # NORMAL
        return ExpansionConfig(
            max_synonyms=5,
            max_children=10,
            max_total=15,
            include_synonyms=True,
            include_children=True,
        )


@dataclass
class ExpansionConfig:
    """
    개념 확장 설정

    오버 확장을 방지하기 위한 제한값 정의.
    "Backend" 검색 시 7개 이상의 스킬이 확장되는 것을 방지합니다.

    Attributes:
        max_synonyms: 동의어 최대 개수 (기본 5)
        max_children: 하위 개념 최대 개수 (기본 10)
        max_total: 전체 확장 최대 개수 (기본 15)
        include_synonyms: 동의어 포함 여부 (기본 True)
        include_children: 하위 개념 포함 여부 (기본 True)
    """

    max_synonyms: int = 5
    max_children: int = 10
    max_total: int = 15
    include_synonyms: bool = True
    include_children: bool = True

    def __post_init__(self) -> None:
        """유효성 검사"""
        if self.max_synonyms < 0:
            raise ValueError("max_synonyms must be non-negative")
        if self.max_children < 0:
            raise ValueError("max_children must be non-negative")
        if self.max_total < 1:
            raise ValueError("max_total must be at least 1")


# 기본 확장 설정 (전역)
DEFAULT_EXPANSION_CONFIG = ExpansionConfig()


class OntologyLoader:
    """
    온톨로지 YAML 로더

    사용 예시:
        loader = OntologyLoader(Path("src/domain/ontology"))
        synonyms = loader.get_synonyms("파이썬", "skills")  # ["Python", "Python3", ...]
        canonical = loader.get_canonical("파이썬", "skills")  # "Python"
        children = loader.get_children("Backend", "skills")  # ["Python", "Java", ...]
        expanded = loader.expand_concept("파이썬", "skills")  # 통합 확장
    """

    def __init__(self, ontology_dir: Path | str | None = None):
        """
        Args:
            ontology_dir: 온톨로지 YAML 파일 디렉토리 경로
                          None이면 기본 경로 사용
        """
        if ontology_dir is None:
            # 기본 경로: src/domain/ontology/
            self._dir = Path(__file__).parent
        else:
            self._dir = Path(ontology_dir)

        self._schema: dict[str, Any] | None = None
        self._synonyms: dict[str, Any] | None = None

        # 역방향 조회용 인덱스 (alias → canonical)
        self._reverse_index: dict[str, dict[str, str]] | None = None

        logger.info(f"OntologyLoader initialized: {self._dir}")

    # =========================================================================
    # YAML 로드
    # =========================================================================

    def load_schema(self) -> dict[str, Any]:
        """schema.yaml 로드 (캐싱)"""
        if self._schema is None:
            schema_path = self._dir / "schema.yaml"
            if not schema_path.exists():
                logger.warning(f"Schema file not found: {schema_path}")
                self._schema = {}
            else:
                try:
                    with open(schema_path, encoding="utf-8") as f:
                        self._schema = yaml.safe_load(f) or {}
                    logger.info(f"Schema loaded: {schema_path}")
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse schema YAML: {e}")
                    self._schema = {}
                except UnicodeDecodeError as e:
                    logger.error(f"Encoding error in schema file (expected UTF-8): {e}")
                    self._schema = {}
                except OSError as e:
                    logger.error(f"Failed to read schema file: {e}")
                    self._schema = {}
        return self._schema

    def load_synonyms(self) -> dict[str, Any]:
        """synonyms.yaml 로드 (캐싱)"""
        if self._synonyms is None:
            synonyms_path = self._dir / "synonyms.yaml"
            if not synonyms_path.exists():
                logger.warning(f"Synonyms file not found: {synonyms_path}")
                self._synonyms = {}
            else:
                try:
                    with open(synonyms_path, encoding="utf-8") as f:
                        self._synonyms = yaml.safe_load(f) or {}
                    logger.info(f"Synonyms loaded: {synonyms_path}")
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse synonyms YAML: {e}")
                    self._synonyms = {}
                except UnicodeDecodeError as e:
                    logger.error(f"Encoding error in synonyms file (expected UTF-8): {e}")
                    self._synonyms = {}
                except OSError as e:
                    logger.error(f"Failed to read synonyms file: {e}")
                    self._synonyms = {}

            # 역방향 인덱스 빌드
            self._build_reverse_index()

        return self._synonyms

    def _build_reverse_index(self) -> None:
        """역방향 조회 인덱스 빌드 (alias → canonical)"""
        # 중복 빌드 방지
        if self._reverse_index is not None:
            return

        self._reverse_index = {}

        if self._synonyms is None:
            return

        # _meta 제외한 카테고리 순회
        for category, entries in self._synonyms.items():
            if category.startswith("_") or not isinstance(entries, dict):
                continue

            self._reverse_index[category] = {}

            for main_term, info in entries.items():
                if not isinstance(info, dict):
                    continue

                canonical = info.get("canonical", main_term)
                aliases = info.get("aliases", [])

                # main_term → canonical
                self._reverse_index[category][main_term.lower()] = canonical

                # 각 alias → canonical
                for alias in aliases:
                    self._reverse_index[category][alias.lower()] = canonical

        logger.debug(f"Reverse index built: {len(self._reverse_index)} categories")

    # =========================================================================
    # 동의어 조회
    # =========================================================================

    def get_canonical(self, term: str, category: str = "skills") -> str:
        """
        정규화된 이름 반환

        Args:
            term: 검색어 (예: "파이썬", "Python3")
            category: 카테고리 (skills, positions, departments)

        Returns:
            정규화된 이름 (예: "Python")
            찾지 못하면 원본 term 반환
        """
        self.load_synonyms()

        if self._reverse_index is None:
            return term

        category_index = self._reverse_index.get(category, {})
        return category_index.get(term.lower(), term)

    def get_synonyms(self, term: str, category: str = "skills") -> list[str]:
        """
        동의어 목록 반환 (양방향 조회)

        Args:
            term: 검색어
            category: 카테고리

        Returns:
            동의어 목록 (canonical 포함)
            찾지 못하면 [term] 반환
        """
        synonyms_data = self.load_synonyms()

        # 먼저 canonical 이름 찾기
        canonical = self.get_canonical(term, category)

        # 해당 카테고리에서 canonical로 검색
        category_data = synonyms_data.get(category, {})

        for main_term, info in category_data.items():
            if not isinstance(info, dict):
                continue

            entry_canonical = info.get("canonical", main_term)
            if entry_canonical == canonical:
                # canonical + 모든 aliases 반환
                result = [canonical]
                result.extend(info.get("aliases", []))
                return list(set(result))  # 중복 제거

        # 찾지 못한 경우 원본 반환
        return [term]

    # =========================================================================
    # 개념 계층 조회
    # =========================================================================

    def get_children(self, concept: str, category: str = "skills") -> list[str]:
        """
        하위 개념 반환 (IS_A 관계의 역방향)

        Args:
            concept: 상위 개념 (예: "Backend", "Programming")
            category: 카테고리 (skills, positions)

        Returns:
            하위 개념 목록
        """
        schema = self.load_schema()
        concepts = schema.get("concepts", {})

        if category == "skills":
            return self._get_skill_children(concept, concepts)
        elif category == "positions":
            return self._get_position_children(concept, concepts)

        return []

    def _get_skill_children(
        self, concept: str, concepts: dict[str, Any]
    ) -> list[str]:
        """스킬 카테고리에서 하위 개념 조회"""
        result: list[str] = []

        skill_categories = concepts.get("SkillCategory", [])

        for top_category in skill_categories:
            if not isinstance(top_category, dict):
                continue

            # 최상위 카테고리 매칭 (예: "Programming", "Cloud")
            if top_category.get("name") == concept:
                # 직접 skills
                result.extend(top_category.get("skills", []))
                # 하위 카테고리의 skills
                for sub in top_category.get("subcategories", []):
                    result.extend(sub.get("skills", []))
                return result

            # 서브카테고리 매칭 (예: "Backend", "Frontend")
            for sub_category in top_category.get("subcategories", []):
                if sub_category.get("name") == concept:
                    return sub_category.get("skills", [])

        return result

    def _get_position_children(
        self, concept: str, concepts: dict[str, Any]
    ) -> list[str]:
        """직급 레벨에서 하위 직급 조회"""
        result: list[str] = []

        position_level = concepts.get("PositionLevel", {})
        hierarchy = position_level.get("hierarchy", [])

        # 해당 레벨 찾기
        target_level = None
        for level_info in hierarchy:
            if level_info.get("name") == concept:
                target_level = level_info.get("level", 0)
                result.extend(level_info.get("includes", []))
                break

        # 하위 레벨들도 포함 (level이 더 낮은 것들)
        if target_level is not None:
            for level_info in hierarchy:
                if level_info.get("level", 0) < target_level:
                    result.extend(level_info.get("includes", []))

        return result

    # =========================================================================
    # 통합 개념 확장
    # =========================================================================

    def expand_concept(
        self,
        term: str,
        category: str = "skills",
        config: ExpansionConfig | None = None,
    ) -> list[str]:
        """
        개념 확장 (동의어 + 하위 개념)

        Args:
            term: 검색어
            category: 카테고리
            config: 확장 설정 (None이면 DEFAULT_EXPANSION_CONFIG 사용)

        Returns:
            확장된 개념 목록 (중복 제거, 최대 max_total개)
        """
        if config is None:
            config = DEFAULT_EXPANSION_CONFIG

        result: list[str] = [term]
        seen: set[str] = {term}

        if config.include_synonyms:
            for syn in self.get_synonyms(term, category)[:config.max_synonyms]:
                if syn not in seen:
                    result.append(syn)
                    seen.add(syn)

        if config.include_children:
            canonical = self.get_canonical(term, category)
            for child in self.get_children(canonical, category)[:config.max_children]:
                if child not in seen:
                    result.append(child)
                    seen.add(child)

        return result[:config.max_total]

    def get_expansion_rules(self) -> dict[str, Any]:
        """확장 규칙 반환"""
        schema = self.load_schema()
        return schema.get("expansion_rules", {
            "default_depth": 2,
            "include_synonyms": True,
            "include_children": True,
            "include_parents": False,
        })


# =========================================================================
# 싱글톤 인스턴스 (전역 사용)
# =========================================================================

@lru_cache(maxsize=1)
def get_ontology_loader() -> OntologyLoader:
    """
    OntologyLoader 싱글톤 인스턴스 반환

    사용 예시:
        from src.domain.ontology.loader import get_ontology_loader
        loader = get_ontology_loader()
    """
    return OntologyLoader()
