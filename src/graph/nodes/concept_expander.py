"""
Concept Expander Node

온톨로지 기반 개념 확장 노드
- EntityExtractor의 출력을 받아 동의어/하위 개념으로 확장
- 예: {"Skill": ["파이썬"]} → {"Skill": ["Python", "파이썬", "Python3", "Py"]}
"""

from src.domain.ontology.loader import OntologyLoader
from src.domain.types import ConceptExpanderUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState


# 엔티티 타입 → 온톨로지 카테고리 매핑
ENTITY_TO_CATEGORY: dict[str, str] = {
    "Skill": "skills",
    "Position": "positions",
    "Department": "departments",
}


class ConceptExpanderNode(BaseNode[ConceptExpanderUpdate]):
    """
    온톨로지 기반 개념 확장 노드

    EntityExtractor 이후, EntityResolver 이전에 실행됩니다.
    추출된 엔티티를 동의어 및 하위 개념으로 확장하여
    검색 범위를 넓힙니다.

    Example:
        Input:  {"Skill": ["파이썬"], "Position": ["백엔드 개발자"]}
        Output: {"Skill": ["Python", "파이썬", "Python3", "Py"],
                 "Position": ["Backend Developer", "서버 개발자", ...]}
    """

    def __init__(
        self,
        ontology_loader: OntologyLoader,
        include_synonyms: bool = True,
        include_children: bool = True,
    ):
        """
        Args:
            ontology_loader: 온톨로지 로더 인스턴스
            include_synonyms: 동의어 포함 여부
            include_children: 하위 개념 포함 여부
        """
        super().__init__()
        self._ontology = ontology_loader
        self._include_synonyms = include_synonyms
        self._include_children = include_children

    @property
    def name(self) -> str:
        return "concept_expander"

    @property
    def input_keys(self) -> list[str]:
        return ["entities"]

    async def _process(self, state: GraphRAGState) -> ConceptExpanderUpdate:
        """
        엔티티 확장

        Args:
            state: 현재 파이프라인 상태

        Returns:
            확장된 엔티티와 메타데이터
        """
        # 원본 엔티티 가져오기
        original_entities = state.get("entities", {})

        if not original_entities:
            self._logger.info("No entities to expand")
            return ConceptExpanderUpdate(
                expanded_entities={},
                original_entities={},
                expansion_count=0,
                execution_path=[self.name],
            )

        self._logger.info(f"Expanding entities: {original_entities}")

        expanded_entities: dict[str, list[str]] = {}
        total_expansion_count = 0

        for entity_type, values in original_entities.items():
            # 온톨로지 카테고리 매핑 (없으면 스킵)
            category = ENTITY_TO_CATEGORY.get(entity_type)

            if category is None:
                # 매핑되지 않은 엔티티 타입은 그대로 전달
                expanded_entities[entity_type] = list(values)
                self._logger.debug(
                    f"No ontology mapping for '{entity_type}', passing through"
                )
                continue

            # 각 값을 확장
            expanded_values: set[str] = set()

            for value in values:
                expanded = self._ontology.expand_concept(
                    term=value,
                    category=category,
                    include_synonyms=self._include_synonyms,
                    include_children=self._include_children,
                )
                expanded_values.update(expanded)

            expanded_entities[entity_type] = list(expanded_values)
            # 원본도 set으로 변환하여 중복 제거 후 비교 (정확한 확장 수 계산)
            original_unique_count = len(set(values))
            expansion_count = len(expanded_values) - original_unique_count
            total_expansion_count += max(0, expansion_count)

            self._logger.debug(
                f"{entity_type}: {values} → {len(expanded_values)} terms "
                f"(+{expansion_count})"
            )

        self._logger.info(
            f"Expansion complete: {sum(len(v) for v in original_entities.values())} "
            f"→ {sum(len(v) for v in expanded_entities.values())} terms "
            f"(+{total_expansion_count})"
        )

        return ConceptExpanderUpdate(
            expanded_entities=expanded_entities,
            original_entities=dict(original_entities),  # 원본 보존
            expansion_count=total_expansion_count,
            execution_path=[self.name],
        )
