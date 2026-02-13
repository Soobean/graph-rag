"""
Response Generator Node

쿼리 결과를 바탕으로 자연어 응답을 생성합니다.
"""

from typing import Any

from langchain_core.messages import AIMessage

from src.domain.types import ResolvedEntity, ResponseGeneratorUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState, IntentType
from src.graph.utils import format_chat_history
from src.repositories.llm_repository import LLMRepository

# Intent별 관계 설명 매핑
INTENT_RELATION_DESCRIPTIONS: dict[IntentType, str] = {
    "personnel_search": "관련 인력 정보",
    "project_matching": "참여한 프로젝트 정보",
    "relationship_search": "관계 정보",
    "org_analysis": "소속 조직 정보",
    "mentoring_network": "멘토링 관계",
    "certificate_search": "자격증 정보",
    "path_analysis": "연결 경로",
    "ontology_update": "온톨로지 정보",
    "global_analysis": "조직 전체 분석",
    "unknown": "관련 정보",
}


class ResponseGeneratorNode(BaseNode[ResponseGeneratorUpdate]):
    """응답 생성 노드"""

    def __init__(self, llm_repository: LLMRepository):
        super().__init__()
        self._llm = llm_repository

    @property
    def name(self) -> str:
        return "response_generator"

    @property
    def input_keys(self) -> list[str]:
        return ["question", "graph_results"]

    async def _process(self, state: GraphRAGState) -> ResponseGeneratorUpdate:
        """
        자연어 응답 생성

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state.get("question", "")
        graph_results = state.get("graph_results", [])
        cypher_query = state.get("cypher_query", "")
        error_msg = state.get("error")
        messages = state.get("messages", [])

        # 이전 대화 기록 포맷팅
        chat_history = format_chat_history(messages)
        prev_msg_count = max(0, len(messages) - 1)

        self._logger.info(
            f"Generating response for {len(graph_results)} results "
            f"(chat_history: {prev_msg_count} previous messages)..."
        )

        # 에러가 있는 경우 에러 메시지 생성
        if error_msg:
            error_response = (
                f"죄송합니다. 질문을 처리하는 중 오류가 발생했습니다: {error_msg}"
            )
            return ResponseGeneratorUpdate(
                response=error_response,
                messages=[AIMessage(content=error_response)],
                execution_path=[f"{self.name}_error_handler"],
            )

        # 결과가 없는 경우
        if not graph_results:
            resolved_entities = state.get("resolved_entities", [])
            intent = state.get("intent", "unknown")

            actually_resolved = [e for e in resolved_entities if e.get("id")]

            if actually_resolved:
                empty_response = self._generate_entity_found_but_no_relation_response(
                    actually_resolved, intent
                )
            else:
                # 엔티티도 못 찾은 경우 - 기존 일반 메시지
                empty_response = "죄송합니다. 질문에 해당하는 정보를 찾을 수 없습니다. 다른 방식으로 질문해 주시거나, 검색 조건을 확인해 주세요."

            return ResponseGeneratorUpdate(
                response=empty_response,
                messages=[AIMessage(content=empty_response)],
                execution_path=[f"{self.name}_empty"],
            )

        try:
            response = await self._llm.generate_response(
                question=question,
                query_results=graph_results,
                cypher_query=cypher_query,
                chat_history=chat_history,
            )

            self._logger.info(f"Generated response: {response[:100]}...")

            return ResponseGeneratorUpdate(
                response=response,
                messages=[AIMessage(content=response)],
                execution_path=[self.name],
            )

        except Exception as e:
            self._logger.error(f"Response generation failed: {e}")

            # 폴백: 간단한 결과 요약
            fallback_response = self._generate_fallback_response(graph_results)

            return ResponseGeneratorUpdate(
                response=fallback_response,
                messages=[AIMessage(content=fallback_response)],
                execution_path=[f"{self.name}_fallback"],
            )

    def _generate_entity_found_but_no_relation_response(
        self, resolved_entities: list[ResolvedEntity], intent: IntentType
    ) -> str:
        """
        엔티티는 찾았지만 해당 관계가 없는 경우의 응답 생성
        """
        # 해결된 엔티티 이름 추출
        entity_names: list[str] = []
        for entity in resolved_entities:
            name = entity.get("name") or entity.get("original_value", "")
            if name and name not in entity_names:
                entity_names.append(name)

        # Intent에 따른 관계 설명 가져오기
        relation_desc = INTENT_RELATION_DESCRIPTIONS.get(intent, "관련 정보")

        if entity_names:
            # 이름 목록 포맷팅 (3개까지)
            if len(entity_names) == 1:
                names_str = f"'{entity_names[0]}'"
            elif len(entity_names) <= 3:
                names_str = ", ".join(f"'{n}'" for n in entity_names)
            else:
                names_str = ", ".join(f"'{n}'" for n in entity_names[:3]) + " 등"

            response = (
                f"{names_str}은(는) 시스템에 등록되어 있지만, "
                f"{relation_desc}가 없습니다. "
                f"데이터가 아직 등록되지 않았을 수 있습니다."
            )
        else:
            response = (
                f"검색한 항목은 시스템에 등록되어 있지만, {relation_desc}가 없습니다."
            )

        self._logger.info(
            f"Entity found but no relation: entities={entity_names}, intent={intent}"
        )

        return response

    def _generate_fallback_response(self, results: list[dict[str, Any]]) -> str:
        """폴백 응답 생성"""
        if not results:
            return "결과를 찾을 수 없습니다."

        lines = [f"총 {len(results)}개의 결과를 찾았습니다:"]

        for i, result in enumerate(results[:5], 1):
            # 주요 속성 추출
            summary_parts = []
            for key, value in result.items():
                if value and key not in ("id", "labels"):
                    summary_parts.append(f"{key}: {value}")
            if summary_parts:
                lines.append(f"{i}. {', '.join(summary_parts[:3])}")

        if len(results) > 5:
            lines.append(f"... 외 {len(results) - 5}개")

        return "\n".join(lines)
