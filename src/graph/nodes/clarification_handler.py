"""
Clarification Handler Node

동명이인, 모호한 엔티티에 대해 사용자에게 확인을 요청합니다.
"""

from langchain_core.messages import AIMessage

from src.domain.types import ResolvedEntity, ResponseGeneratorUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository


class ClarificationHandlerNode(BaseNode[ResponseGeneratorUpdate]):
    """명확화 요청 노드"""

    def __init__(self, llm_repository: LLMRepository):
        super().__init__()
        self._llm = llm_repository

    @property
    def name(self) -> str:
        return "clarification_handler"

    @property
    def input_keys(self) -> list[str]:
        return ["question", "resolved_entities", "entities"]

    async def _process(self, state: GraphRAGState) -> ResponseGeneratorUpdate:
        """
        명확화 요청 응답 생성

        동명이인이나 모호한 엔티티가 있을 때 사용자에게 확인 질문을 생성합니다.

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state.get("question", "")
        resolved_entities = state.get("resolved_entities", [])
        entities = state.get("entities", {})

        self._logger.info("Generating clarification request...")

        try:
            # 미해결 엔티티 추출
            unresolved = self._extract_unresolved_entities(resolved_entities, entities)

            if not unresolved:
                # 미해결 엔티티가 없으면 일반적인 명확화 요청
                response = await self._generate_general_clarification(question)
            else:
                # 미해결 엔티티에 대한 구체적인 명확화 요청
                response = await self._generate_entity_clarification(
                    question, unresolved
                )

            self._logger.info(f"Clarification response: {response[:100]}...")

            return ResponseGeneratorUpdate(
                response=response,
                messages=[AIMessage(content=response)],
                execution_path=[self.name],
            )

        except Exception as e:
            self._logger.error(f"Clarification generation failed: {e}")
            fallback_response = self._generate_fallback_clarification(entities)
            return ResponseGeneratorUpdate(
                response=fallback_response,
                messages=[AIMessage(content=fallback_response)],
                execution_path=[f"{self.name}_fallback"],
            )

    def _extract_unresolved_entities(
        self,
        resolved_entities: list[ResolvedEntity],
        entities: dict[str, list[str]],
    ) -> list[dict[str, str]]:
        """
        미해결 엔티티 추출

        Args:
            resolved_entities: 매칭된 엔티티 리스트 (ResolvedEntity)
            entities: 추출된 원본 엔티티 맵

        Returns:
            list[dict]: 미해결된(매칭되지 않은) 엔티티 리스트
        """
        unresolved: list[dict[str, str]] = []

        # 1. resolved_entities에서 id=None인 항목 찾기 (매칭 실패)
        for entity in resolved_entities:
            if not entity.get("id"):
                labels = entity.get("labels", [])
                entity_type = labels[0] if labels else "Unknown"
                unresolved.append(
                    {
                        "type": entity_type,
                        "value": entity.get("original_value", ""),
                    }
                )

        # 2. entities에서 resolved_entities에 없는 항목 찾기
        resolved_values = {e.get("original_value") for e in resolved_entities}
        for entity_type, values in entities.items():
            for value in values:
                if value not in resolved_values:
                    unresolved.append(
                        {
                            "type": entity_type,
                            "value": value,
                        }
                    )

        return unresolved

    async def _generate_entity_clarification(
        self,
        question: str,
        unresolved: list[dict[str, str]],
    ) -> str:
        """엔티티 관련 명확화 요청 생성"""
        unresolved_str = ", ".join(f"{e['type']}: {e['value']}" for e in unresolved)

        return await self._llm.generate_clarification(
            question=question,
            unresolved_entities=unresolved_str,
        )

    async def _generate_general_clarification(self, question: str) -> str:
        """일반적인 명확화 요청 생성"""
        return await self._llm.generate_clarification(
            question=question,
            unresolved_entities="",
        )

    def _generate_fallback_clarification(self, entities: dict[str, list[str]]) -> str:
        """폴백 명확화 메시지 생성"""
        if not entities:
            return (
                "죄송합니다. 질문을 이해하기 어렵습니다. "
                "조금 더 구체적으로 질문해 주시겠어요?"
            )

        entity_mentions = []
        for _, values in entities.items():
            for value in values:
                entity_mentions.append(f"'{value}'")

        if entity_mentions:
            return (
                f"질문에서 {', '.join(entity_mentions)}을(를) 찾았지만, "
                "데이터베이스에서 정확히 일치하는 정보를 찾지 못했습니다. "
                "혹시 다른 이름이나 추가 정보가 있으시다면 알려주세요."
            )

        return "질문을 더 명확하게 해주시면 도움이 될 것 같습니다."
