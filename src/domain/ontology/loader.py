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


# YAML 보안 설정: 중첩 깊이 제한 (YAML Bomb 방지)
# compose_node 레벨에서 체크하여 모든 재귀 호출에서 깊이 검증
class SafeLineLoader(yaml.SafeLoader):
    """
    중첩 깊이 제한이 있는 SafeLoader (YAML Bomb 방지)

    compose_node()를 오버라이드하여 모든 노드 구성 시 깊이를 체크합니다.
    이 방식은 내부 재귀 호출에서도 정확하게 깊이를 추적합니다.
    """

    MAX_DEPTH = 20  # 최대 중첩 깊이

    def __init__(self, stream):
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent, index):
        """노드 구성 시 깊이 체크 (모든 재귀 호출에서 실행됨)"""
        self._depth += 1
        if self._depth > self.MAX_DEPTH:
            raise yaml.YAMLError(
                f"YAML nesting depth exceeds maximum ({self.MAX_DEPTH})"
            )
        try:
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1


logger = logging.getLogger(__name__)


# =============================================================================
# 온톨로지 카테고리
# =============================================================================


class OntologyCategory(str, Enum):
    """
    온톨로지 카테고리
    """

    SKILLS = "skills"
    POSITIONS = "positions"
    DEPARTMENTS = "departments"


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
    BROAD = "broad"  # 동의어 + 전체 하위 개념 (넓은 검색)


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

        >>> get_strategy_for_intent("skill_search", 0.3)
        ExpansionStrategy.BROAD  # 신뢰도 낮아도 기본 전략 유지
    """
    base_strategy = INTENT_STRATEGY_MAP.get(intent, ExpansionStrategy.NORMAL)

    # 신뢰도가 낮으면 기본 전략 유지 (보수적 접근)
    if confidence < 0.5:
        return base_strategy

    # 신뢰도가 높고 BROAD 전략이면 NORMAL로 좁힘
    if confidence > 0.9 and base_strategy == ExpansionStrategy.BROAD:
        return ExpansionStrategy.NORMAL

    return base_strategy


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
        min_weight: 최소 가중치 임계값 (기본 0.0 = 필터링 없음)
        sort_by_weight: 가중치 기준 정렬 여부 (기본 True)
    """

    max_synonyms: int = 5
    max_children: int = 10
    max_total: int = 15
    include_synonyms: bool = True
    include_children: bool = True
    min_weight: float = 0.0
    sort_by_weight: bool = True

    def __post_init__(self) -> None:
        """기본 유효성 검사 (음수 방지)"""
        if self.max_synonyms < 0:
            raise ValueError("max_synonyms must be non-negative")
        if self.max_children < 0:
            raise ValueError("max_children must be non-negative")
        if self.max_total < 1:
            raise ValueError("max_total must be at least 1")
        if not 0.0 <= self.min_weight <= 1.0:
            raise ValueError("min_weight must be between 0.0 and 1.0")


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
            self._dir = Path(__file__).parent
        else:
            dir_path = Path(ontology_dir).resolve()
            if not dir_path.exists():
                raise ValueError(f"Directory does not exist: {dir_path}")
            if not dir_path.is_dir():
                raise ValueError(f"Path is not a directory: {dir_path}")
            self._dir = dir_path

        self._schema: dict[str, Any] | None = None
        self._synonyms: dict[str, Any] | None = None

        # 역방향 조회용 인덱스 (alias → canonical)
        self._reverse_index: dict[str, dict[str, str]] | None = None

        logger.info(f"OntologyLoader initialized: {self._dir}")

    # =========================================================================
    # YAML 로드
    # =========================================================================

    # 파일 크기 제한 (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024

    def _load_yaml_file(self, filename: str) -> dict[str, Any]:
        """YAML 파일 로드 (공통 로직)"""
        file_path = self._dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Required file not found: {file_path}")

        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(f"File too large: {file_path} ({file_size} bytes)")

        with open(file_path, encoding="utf-8") as f:
            data = yaml.load(f, Loader=SafeLineLoader) or {}

        logger.info(f"Loaded: {file_path}")
        return data

    def load_schema(self) -> dict[str, Any]:
        """schema.yaml 로드 (캐싱)"""
        if self._schema is None:
            self._schema = self._load_yaml_file("schema.yaml")
        return self._schema

    def load_synonyms(self) -> dict[str, Any]:
        """synonyms.yaml 로드 (캐싱)"""
        if self._synonyms is None:
            self._synonyms = self._load_yaml_file("synonyms.yaml")
            self._build_reverse_index()
        return self._synonyms

    def clear_cache(self) -> None:
        """
        내부 캐시 클리어

        OntologyRegistry.refresh() 호출 시 사용됩니다.
        스키마, 동의어, 역방향 인덱스를 모두 초기화합니다.
        """
        self._schema = None
        self._synonyms = None
        self._reverse_index = None

    def _build_reverse_index(self) -> None:
        """
        역방향 조회 인덱스 빌드 (alias → canonical)

        Note: 이 메서드는 load_synonyms()의 lock 내부에서 호출됩니다.
              호출 전에 _reverse_index is None 체크가 완료되었다고 가정합니다.
        """
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

                # 각 alias → canonical (하위호환: str 또는 dict 형식 지원)
                for alias in aliases:
                    alias_name, _ = self._parse_alias(alias)
                    self._reverse_index[category][alias_name.lower()] = canonical

        logger.debug(f"Reverse index built: {len(self._reverse_index)} categories")

    @staticmethod
    def _parse_alias(alias_entry: str | dict[str, Any]) -> tuple[str, float]:
        """
        alias 엔트리에서 이름과 가중치 추출 (하위호환)

        Args:
            alias_entry: 문자열 또는 {name, weight} 형식의 딕셔너리

        Returns:
            (이름, 가중치) 튜플. 문자열이면 가중치는 1.0
        """
        if isinstance(alias_entry, dict):
            return alias_entry.get("name", ""), float(alias_entry.get("weight", 1.0))
        return alias_entry, 1.0

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
        synonyms_with_weights = self.get_synonyms_with_weights(term, category)
        return [name for name, _ in synonyms_with_weights]

    def get_synonyms_with_weights(
        self, term: str, category: str = "skills"
    ) -> list[tuple[str, float]]:
        """
        동의어와 가중치 목록 반환 (양방향 조회)

        Args:
            term: 검색어
            category: 카테고리

        Returns:
            (동의어, 가중치) 튜플 목록
            찾지 못하면 [(term, 1.0)] 반환
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
                # canonical (weight=1.0) + 모든 aliases (with weights)
                result: list[tuple[str, float]] = [(canonical, 1.0)]
                seen = {canonical}

                for alias in info.get("aliases", []):
                    alias_name, alias_weight = self._parse_alias(alias)
                    if alias_name and alias_name not in seen:
                        result.append((alias_name, alias_weight))
                        seen.add(alias_name)

                return result

        # 찾지 못한 경우 원본 반환
        return [(term, 1.0)]

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

        if category == OntologyCategory.SKILLS:
            return self._get_skill_children(concept, concepts)
        elif category == OntologyCategory.POSITIONS:
            return self._get_position_children(concept, concepts)

        return []

    def _get_skill_children(self, concept: str, concepts: dict[str, Any]) -> list[str]:
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
        """
        직급 레벨에서 하위 직급 조회 (level < target)

        예시:
            - get_children("Senior") → Mid, Junior 레벨 직급들
            - "시니어 이상" 검색에는 get_position_level_and_above() 사용

        Note:
            IS_A 관계상 하위 개념을 반환 (Senior IS_A Executive 아님)
        """
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

    def get_position_level_and_above(
        self, concept: str, category: str = "positions"
    ) -> list[str]:
        """
        지정 레벨 이상의 직급 조회 (level >= target)

        "시니어 이상" 검색 시 사용.

        Args:
            concept: 기준 레벨명 (예: "Senior")
            category: 카테고리 (positions만 지원)

        Returns:
            해당 레벨 이상의 모든 직급명

        Examples:
            >>> loader.get_position_level_and_above("Senior")
            ["Senior Engineer", "Tech Lead", "Staff Engineer", "CTO", "VP", "Director"]
        """
        if category != OntologyCategory.POSITIONS:
            return []

        schema = self.load_schema()
        concepts = schema.get("concepts", {})
        position_level = concepts.get("PositionLevel", {})
        hierarchy = position_level.get("hierarchy", [])

        result: list[str] = []

        # 타겟 레벨 찾기
        target_level = None
        for level_info in hierarchy:
            if level_info.get("name") == concept:
                target_level = level_info.get("level", 0)
                break

        if target_level is None:
            logger.warning(f"Position level '{concept}' not found in hierarchy")
            return []

        # 타겟 레벨 이상 수집 (level >= target)
        for level_info in hierarchy:
            if level_info.get("level", 0) >= target_level:
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

        Note:
            - min_weight > 0: 해당 가중치 이상인 동의어만 포함
            - sort_by_weight=True: 가중치 내림차순 정렬
        """
        if config is None:
            config = DEFAULT_EXPANSION_CONFIG

        result: list[str] = [term]
        seen: set[str] = {term}

        if config.include_synonyms:
            # 가중치와 함께 동의어 조회
            synonyms_with_weights = self.get_synonyms_with_weights(term, category)

            # 임계값 필터링
            if config.min_weight > 0:
                synonyms_with_weights = [
                    (s, w) for s, w in synonyms_with_weights if w >= config.min_weight
                ]

            # 가중치 기준 정렬
            if config.sort_by_weight:
                synonyms_with_weights.sort(key=lambda x: x[1], reverse=True)

            # 결과 추가
            for syn, _ in synonyms_with_weights[: config.max_synonyms]:
                if syn not in seen:
                    result.append(syn)
                    seen.add(syn)

        if config.include_children:
            canonical = self.get_canonical(term, category)
            for child in self.get_children(canonical, category)[: config.max_children]:
                if child not in seen:
                    result.append(child)
                    seen.add(child)

        return result[: config.max_total]

    def get_style_for_concept(
        self, concept: str, category: str = "skills"
    ) -> dict[str, str] | None:
        """
        개념에 대한 스타일(색상, 아이콘) 반환

        Args:
            concept: 개념 이름 (예: "Python", "Senior Engineer")
            category: 카테고리 (skills, positions)

        Returns:
            {"color": "#...", "icon": "..."} 또는 None
        """
        schema = self.load_schema()
        concepts = schema.get("concepts", {})

        # 1. Canonical 이름 확인
        canonical = self.get_canonical(concept, category)

        # 2. Category별 탐색
        if category == OntologyCategory.SKILLS:
            return self._get_skill_style(canonical, concepts)
        elif category == OntologyCategory.POSITIONS:
            return self._get_position_style(canonical, concepts)

        return None

    def _get_skill_style(
        self, concept: str, concepts: dict[str, Any]
    ) -> dict[str, str] | None:
        """스킬 카테고리에서 스타일 탐색 (상속 지원)"""
        skill_categories = concepts.get("SkillCategory", [])

        for top_category in skill_categories:
            if not isinstance(top_category, dict):
                continue

            top_style = top_category.get("style")

            # Case 1: 최상위 카테고리 자체 (예: "Programming")
            if top_category.get("name") == concept:
                return top_style

            # Case 2: 서브카테고리 탐색
            for sub in top_category.get("subcategories", []):
                sub_style = (
                    sub.get("style") or top_style
                )  # 서브에 없으면 상위 스타일 상속

                # Case 2-1: 서브카테고리 자체 (예: "Backend")
                if sub.get("name") == concept:
                    return sub_style

                # Case 2-2: 서브카테고리 내 스킬 (예: "Python")
                if concept in sub.get("skills", []):
                    return sub_style

            # Case 3: 최상위 카테고리 직속 스킬
            if concept in top_category.get("skills", []):
                return top_style

        return None

    def _get_position_style(
        self, concept: str, concepts: dict[str, Any]
    ) -> dict[str, str] | None:
        """직급 카테고리에서 스타일 탐색"""
        position_level = concepts.get("PositionLevel", {})
        hierarchy = position_level.get("hierarchy", [])

        for level_info in hierarchy:
            style = level_info.get("style")

            # Case 1: 레벨 이름 자체 (예: "Senior")
            if level_info.get("name") == concept:
                return style

            # Case 2: 레벨 내 직급 (예: "Senior Engineer")
            if concept in level_info.get("includes", []):
                return style

        return None


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
