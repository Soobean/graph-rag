"""
Response Generator Node

쿼리 결과를 바탕으로 자연어 응답을 생성합니다.
"""

import logging
from typing import Any

from src.domain.types import ResponseGeneratorUpdate
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository

logger = logging.getLogger(__name__)


class ResponseGeneratorNode:
    """응답 생성 노드"""

    def __init__(self, llm_repository: LLMRepository):
        self._llm = llm_repository

    async def __call__(self, state: GraphRAGState) -> ResponseGeneratorUpdate:
        """
        자연어 응답 생성

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state["question"]
        graph_results = state.get("graph_results", [])
        cypher_query = state.get("cypher_query", "")
        error_msg = state.get("error")

        logger.info(f"Generating response for {len(graph_results)} results...")

        # 에러가 있는 경우 에러 메시지 생성
        if error_msg:
            return {
                "response": f"죄송합니다. 질문을 처리하는 중 오류가 발생했습니다: {error_msg}",
                "execution_path": ["response_generator_error_handler"],
            }

        # 결과가 없는 경우
        if not graph_results:
            return {
                "response": "죄송합니다. 질문에 해당하는 정보를 찾을 수 없습니다. 다른 방식으로 질문해 주시거나, 검색 조건을 확인해 주세요.",
                "execution_path": ["response_generator_empty"],
            }

        try:
            response = await self._llm.generate_response(
                question=question,
                query_results=graph_results,
                cypher_query=cypher_query,
            )

            logger.info(f"Generated response: {response[:100]}...")

            return {
                "response": response,
                "execution_path": ["response_generator"],
            }

        except Exception as e:
            logger.error(f"Response generation failed: {e}")

            # 폴백: 간단한 결과 요약
            fallback_response = self._generate_fallback_response(graph_results)

            return {
                "response": fallback_response,
                "execution_path": ["response_generator_fallback"],
            }

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
