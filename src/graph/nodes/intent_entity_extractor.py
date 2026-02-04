"""
Intent Entity Extractor Node (통합 노드)

Intent 분류와 Entity 추출을 하나의 LLM 호출로 처리합니다.
Latency Optimization: 2회 LLM 호출 → 1회로 통합 (~200ms 절감)
"""

from typing import cast

from src.domain.types import IntentEntityExtractorUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import (
    AVAILABLE_INTENTS,
    DEFAULT_ENTITY_TYPES,
    GraphRAGState,
    IntentType,
)
from src.graph.utils import format_chat_history
from src.repositories.llm_repository import LLMRepository


class IntentEntityExtractorNode(BaseNode[IntentEntityExtractorUpdate]):
    """
    통합 Intent + Entity 추출 노드

    LLM 호출 횟수를 줄이고 레이턴시를 최적화합니다.
    """

    def __init__(
        self,
        llm_repository: LLMRepository,
        entity_types: list[str] | None = None,
    ):
        super().__init__()
        self._llm = llm_repository
        self._entity_types = entity_types or DEFAULT_ENTITY_TYPES

    @property
    def name(self) -> str:
        return "intent_entity_extractor"

    @property
    def input_keys(self) -> list[str]:
        return ["question"]

    async def _process(self, state: GraphRAGState) -> IntentEntityExtractorUpdate:
        """
        통합 Intent 분류 + Entity 추출

        Args:
            state: 현재 파이프라인 상태

        Returns:
            IntentEntityExtractorUpdate: 의도 + 엔티티 결과
        """
        question = state.get("question", "")
        self._logger.info(f"Combined intent+entity extraction for: {question[:50]}...")

        try:
            # 대화 기록 포맷팅
            messages = state.get("messages", [])
            chat_history = format_chat_history(messages)

            # 통합 LLM 호출 (1회)
            result = await self._llm.classify_intent_and_extract_entities(
                question=question,
                available_intents=AVAILABLE_INTENTS,
                entity_types=self._entity_types,
                chat_history=chat_history,
            )

            # Intent 처리
            intent_str = result.get("intent", "unknown")
            confidence = result.get("confidence", 0.0)

            # 유효하지 않은 intent string 처리
            if intent_str not in AVAILABLE_INTENTS and intent_str != "unknown":
                self._logger.warning(
                    f"Invalid intent returned: {intent_str}. Fallback to unknown."
                )
                intent = "unknown"
            else:
                intent = cast(IntentType, intent_str)

            # Entity 처리: list[dict] -> dict[str, list[str]] 변환
            raw_entities = result.get("entities", [])
            structured_entities: dict[str, list[str]] = {}

            entity_count = 0
            for entity in raw_entities:
                entity_type = entity.get("type", "Unknown")
                value = entity.get("normalized") or entity.get("value")

                if value:
                    if entity_type not in structured_entities:
                        structured_entities[entity_type] = []
                    structured_entities[entity_type].append(str(value))
                    entity_count += 1

            self._logger.info(
                f"Combined extraction: intent={intent} (conf={confidence:.2f}), "
                f"entities={entity_count} in {len(structured_entities)} categories"
            )

            return IntentEntityExtractorUpdate(
                intent=intent,
                intent_confidence=confidence,
                entities=structured_entities,
                execution_path=[self.name],
            )

        except Exception as e:
            self._logger.error(f"Combined intent+entity extraction failed: {e}")
            return IntentEntityExtractorUpdate(
                intent="unknown",
                intent_confidence=0.0,
                entities={},
                error=f"Combined extraction failed: {e}",
                execution_path=[f"{self.name}_error"],
            )
