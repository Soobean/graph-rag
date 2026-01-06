"""
Intent Classifier Node

사용자 질문의 의도를 분류합니다.
"""

import logging
from typing import cast

from src.domain.types import IntentClassifierUpdate
from src.graph.state import GraphRAGState, IntentType
from src.repositories.llm_repository import LLMRepository

logger = logging.getLogger(__name__)


class IntentClassifierNode:
    """의도 분류 노드"""

    def __init__(self, llm_repository: LLMRepository):
        self._llm = llm_repository

    async def __call__(self, state: GraphRAGState) -> IntentClassifierUpdate:
        """
        질문 의도 분류

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state["question"]
        logger.info(f"Classifying intent for: {question[:50]}...")

        try:
            # 분류 가능한 의도 정의 (ARCHITECTURE.md 준수)
            available_intents = [
                "personnel_search",
                "project_matching",
                "relationship_search",
                "org_analysis",
                "mentoring_network",
                "certificate_search",
                "path_analysis",
            ]

            result = await self._llm.classify_intent(
                question=question,
                available_intents=available_intents,
            )

            intent_str = result.get("intent", "unknown")
            confidence = result.get("confidence", 0.0)

            # 유효하지 않은 intent string이 넘어왔을 경우 unknown 처리
            if intent_str not in available_intents and intent_str != "unknown":
                logger.warning(
                    f"Invalid intent returned: {intent_str}. Fallback to unknown."
                )
                intent = "unknown"
            else:
                intent = cast(IntentType, intent_str)

            logger.info(f"Intent classified: {intent} (confidence: {confidence})")

            return {
                "intent": intent,
                "intent_confidence": confidence,
                "execution_path": ["intent_classifier"],
            }

        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return {
                "intent": "unknown",
                "intent_confidence": 0.0,
                "error": f"Intent classification failed: {e}",
                "execution_path": ["intent_classifier_error"],
            }
