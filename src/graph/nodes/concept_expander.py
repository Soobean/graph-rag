"""
Concept Expander Node

온톨로지 기반 개념 확장 노드
- EntityExtractor의 출력을 받아 동의어/하위 개념으로 확장
- Intent 기반 컨텍스트 확장 전략 적용
- 예: {"Skill": ["파이썬"]} → {"Skill": ["Python", "파이썬", "Python3", "Py"]}
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from src.domain.ontology.loader import (
    ExpansionConfig,
    ExpansionStrategy,
    OntologyLoader,
    get_config_for_strategy,
    get_strategy_for_intent,
)
from src.domain.types import ConceptExpanderUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState

if TYPE_CHECKING:
    from src.domain.ontology.hybrid_loader import HybridOntologyLoader

# 엔티티 타입 → 온톨로지 카테고리 매핑
ENTITY_TO_CATEGORY: dict[str, str] = {
    "Skill": "skills",
    "Position": "positions",
    "Department": "departments",
}


class ConceptExpanderNode(BaseNode[ConceptExpanderUpdate]):
    """
    온톨로지 기반 개념 확장 노드

    EntityExtractor → ConceptExpander → EntityResolver 순서로 실행.
    Intent/신뢰도 기반으로 STRICT/NORMAL/BROAD 전략 자동 선택.
    """

    def __init__(
        self,
        ontology_loader: OntologyLoader | HybridOntologyLoader,
        expansion_config: ExpansionConfig | None = None,
        default_strategy: ExpansionStrategy = ExpansionStrategy.NORMAL,
    ):
        """
        Args:
            ontology_loader: 온톨로지 로더 인스턴스 (동기 또는 비동기)
            expansion_config: 고정 확장 설정 (None이면 동적 전략 사용)
            default_strategy: Intent 없을 때 기본 전략
        """
        super().__init__()
        self._ontology = ontology_loader
        self._default_strategy = default_strategy
        self._static_config = expansion_config

        # Duck typing: expand_concept이 코루틴 함수인지 체크
        self._is_async_loader = inspect.iscoroutinefunction(
            getattr(ontology_loader, "expand_concept", None)
        )

    @property
    def name(self) -> str:
        return "concept_expander"

    @property
    def input_keys(self) -> list[str]:
        return ["entities"]

    def _get_expansion_config(self, state: GraphRAGState) -> tuple[ExpansionConfig, ExpansionStrategy]:
        """상태 기반으로 확장 설정 결정"""
        if self._static_config is not None:
            return self._static_config, self._default_strategy

        intent = state.get("intent", "unknown")
        confidence = state.get("intent_confidence", 0.7)
        strategy = get_strategy_for_intent(intent, confidence)

        return get_config_for_strategy(strategy), strategy

    async def _expand_concept(
        self,
        value: str,
        category: str,
        config: ExpansionConfig,
    ) -> list[str]:
        """동기/비동기 로더 모두 지원 (duck typing)"""
        if self._is_async_loader:
            return await self._ontology.expand_concept(value, category, config)
        return self._ontology.expand_concept(value, category, config)

    async def _process(self, state: GraphRAGState) -> ConceptExpanderUpdate:
        """엔티티를 온톨로지 기반으로 확장"""
        original_entities = state.get("entities", {})

        if not original_entities:
            self._logger.info("No entities to expand")
            return ConceptExpanderUpdate(
                expanded_entities={},
                expanded_entities_by_original={},
                original_entities={},
                expansion_count=0,
                expansion_strategy="normal",
                execution_path=[self.name],
            )

        config, strategy = self._get_expansion_config(state)
        self._logger.info(f"Expanding with strategy={strategy.value}")

        expanded_entities: dict[str, list[str]] = {}
        expanded_by_original: dict[str, dict[str, list[str]]] = {}
        total_expansion_count = 0

        for entity_type, values in original_entities.items():
            category = ENTITY_TO_CATEGORY.get(entity_type)

            if category is None:
                expanded_entities[entity_type] = list(values)
                expanded_by_original[entity_type] = {v: [v] for v in values}
                continue

            expanded_values: set[str] = set()
            type_by_original: dict[str, list[str]] = {}
            for value in values:
                expanded = await self._expand_concept(value, category, config)
                expanded_values.update(expanded)
                type_by_original[value] = expanded

            expanded_entities[entity_type] = list(expanded_values)
            expanded_by_original[entity_type] = type_by_original
            total_expansion_count += max(0, len(expanded_values) - len(set(values)))

        return ConceptExpanderUpdate(
            expanded_entities=expanded_entities,
            expanded_entities_by_original=expanded_by_original,
            original_entities=dict(original_entities),
            expansion_count=total_expansion_count,
            expansion_strategy=strategy.value,
            execution_path=[self.name],
        )
