"""
Intent Classifier Node

사용자 질문의 의도를 분류합니다.
"""

from typing import cast

from src.domain.types import IntentClassifierUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState, IntentType
from src.graph.utils import format_chat_history
from src.repositories.llm_repository import LLMRepository


class IntentClassifierNode(BaseNode[IntentClassifierUpdate]):
    """의도 분류 노드"""

    # 분류 가능한 의도 정의 (ARCHITECTURE.md 준수)
    AVAILABLE_INTENTS = [
        "personnel_search",
        "project_matching",
        "relationship_search",
        "org_analysis",
        "mentoring_network",
        "certificate_search",
        "path_analysis",
    ]

    def __init__(self, llm_repository: LLMRepository):
        super().__init__()
        self._llm = llm_repository

    @property
    def name(self) -> str:
        return "intent_classifier"

    @property
    def input_keys(self) -> list[str]:
        return ["question"]


    async def _process(self, state: GraphRAGState) -> IntentClassifierUpdate:
        """
        질문 의도 분류

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state.get("question", "")
        self._logger.info(f"Classifying intent for: {question[:50]}...")

        try:
            # 대화 기록 포맷팅 (현재 질문 제외)
            messages = state.get("messages", [])
            chat_history = format_chat_history(messages)

            result = await self._llm.classify_intent(
                question=question,
                available_intents=self.AVAILABLE_INTENTS,
                chat_history=chat_history,
            )

            intent_str = result.get("intent", "unknown")
            confidence = result.get("confidence", 0.0)

            # 유효하지 않은 intent string이 넘어왔을 경우 unknown 처리
            if intent_str not in self.AVAILABLE_INTENTS and intent_str != "unknown":
                self._logger.warning(
                    f"Invalid intent returned: {intent_str}. Fallback to unknown."
                )
                intent = "unknown"
            else:
                intent = cast(IntentType, intent_str)

            self._logger.info(f"Intent classified: {intent} (confidence: {confidence})")

            return IntentClassifierUpdate(
                intent=intent,
                intent_confidence=confidence,
                execution_path=[self.name],
            )

        except Exception as e:
            self._logger.error(f"Intent classification failed: {e}")
            return IntentClassifierUpdate(
                intent="unknown",
                intent_confidence=0.0,
                error=f"Intent classification failed: {e}",
                execution_path=[f"{self.name}_error"],
            )
