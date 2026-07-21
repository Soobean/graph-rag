"""
LLM Repository - LLM use-case 계층 (과도기)

책임:
- 프롬프트 조립 및 task 메서드 제공 (파이프라인 노드용)
- 프롬프트용 결과 포맷팅

전송 계층(클라이언트 관리, primitive, fallback, 임베딩)은
`src.infrastructure.llm.AzureOpenAIGateway`로 이관됨.
이 클래스는 리팩토링 과도기 동안 게이트웨이에 위임만 하며,
task 메서드는 application 계층(LLMTaskService)으로 이관 예정.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from src.application.llm.formatters import (
    format_chat_history_for_prompt,
    format_entities,
    format_query_plan,
    format_results,
    format_schema,
)
from src.config import Settings
from src.domain.types import (
    CypherGenerationResult,
    IntentEntityExtractionResult,
    QueryDecompositionResult,
)
from src.infrastructure.llm import (
    FALLBACK_EXCEPTIONS,
    AzureOpenAIGateway,
    ModelTier,
    classify_api_status_error,
)
from src.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

# 하위 호환 재수출 (bootstrap/노드/테스트가 이 경로로 import)
_classify_api_status_error = classify_api_status_error

__all__ = [
    "LLMRepository",
    "ModelTier",
    "FALLBACK_EXCEPTIONS",
    "_classify_api_status_error",
]


class LLMRepository:
    """
    LLM use-case 계층 (과도기 — 전송은 AzureOpenAIGateway에 위임)
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._gateway = AzureOpenAIGateway(settings)
        self._prompt_manager = PromptManager()

        logger.info(
            f"LLMRepository initialized: light={settings.light_model_deployment}, "
            f"heavy={settings.heavy_model_deployment}"
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_tier: ModelTier = ModelTier.LIGHT,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> str:
        """텍스트 생성 (게이트웨이 위임)"""
        return await self._gateway.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=model_tier,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
        )

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model_tier: ModelTier = ModelTier.LIGHT,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """JSON 형식 응답 생성 (게이트웨이 위임)"""
        return await self._gateway.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=model_tier,
            temperature=temperature,
        )

    # ============================================
    # Fallback 헬퍼 메서드 (HEAVY → LIGHT) — 게이트웨이 위임
    # ============================================

    async def _generate_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> str:
        """텍스트 생성 with Fallback (게이트웨이 위임)"""
        return await self._gateway.generate_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
        )

    async def _generate_json_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """JSON 생성 with Fallback (게이트웨이 위임)"""
        return await self._gateway.generate_json_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )

    async def classify_intent_and_extract_entities(
        self,
        question: str,
        available_intents: list[str],
        entity_types: list[str],
        chat_history: str = "",
    ) -> IntentEntityExtractionResult:
        """
        통합 의도 분류 + 엔티티 추출 (1회 LLM 호출)

        Latency Optimization: 2회 LLM 호출을 1회로 통합하여 ~200ms 절감

        Args:
            question: 사용자 질문
            available_intents: 분류 가능한 의도 목록
            entity_types: 추출할 엔티티 타입 목록
            chat_history: 이전 대화 기록 (포맷된 문자열)

        Returns:
            IntentEntityExtractionResult: 통합 결과 (intent, confidence, entities)
        """
        prompt = self._prompt_manager.load_prompt("intent_entity_combined")

        system_prompt = prompt["system"].format(
            available_intents=", ".join(available_intents),
            entity_types=", ".join(entity_types),
        )
        user_prompt = prompt["user"].format(
            question=question,
            chat_history=format_chat_history_for_prompt(chat_history),
        )

        result = await self.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.LIGHT,
        )
        return cast(IntentEntityExtractionResult, result)

    async def generate_cypher(
        self,
        question: str,
        schema: dict[str, Any],
        entities: list[dict[str, Any]],
        query_plan: dict[str, Any] | None = None,
        intent: str = "",
    ) -> CypherGenerationResult:
        """
        Cypher 쿼리 생성. HEAVY 우선, 실패 시 LIGHT fallback.

        Args:
            question: 사용자 질문
            schema: 그래프 스키마
            entities: 추출된 엔티티 목록
            query_plan: Multi-hop 쿼리 계획 (선택적)
            intent: 질문 의도 (TYPE A/B 매핑에 사용)

        Returns:
            CypherGenerationResult: Generated Cypher query and metadata

        Raises:
            LLMResponseError: 모든 티어 실패 시
        """
        prompt = self._prompt_manager.load_prompt("cypher_generation")

        schema_str = format_schema(schema)
        entities_str = format_entities(entities)
        query_plan_str = format_query_plan(query_plan)

        system_prompt = prompt["system"].format(schema_str=schema_str)
        user_prompt = prompt["user"].format(
            question=question,
            entities_str=entities_str,
            query_plan_str=query_plan_str,
            intent=intent or "unknown",
        )

        result = await self._generate_json_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return cast(CypherGenerationResult, result)

    async def generate_response(
        self,
        question: str,
        query_results: list[dict[str, Any]],
        cypher_query: str,
        chat_history: str = "",
    ) -> str:
        """
        최종 응답 생성 (with Fallback: HEAVY → LIGHT → Error)

        응답 생성은 복잡한 작업이므로 HEAVY 티어를 우선 사용하고,
        실패 시 LIGHT 티어로 fallback합니다.

        Args:
            question: 사용자 질문
            query_results: Neo4j 쿼리 결과
            cypher_query: 실행된 Cypher 쿼리
            chat_history: 이전 대화 기록 (포맷된 문자열)

        Raises:
            LLMResponseError: 모든 티어 실패 시
        """
        prompt = self._prompt_manager.load_prompt("response_generation")

        results_str = format_results(query_results)

        system_prompt = prompt["system"]
        user_prompt = prompt["user"].format(
            question=question,
            results_str=results_str,
            chat_history=format_chat_history_for_prompt(chat_history),
        )

        # Fallback 적용: HEAVY → LIGHT → Error
        return await self._generate_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    async def generate_response_stream(
        self,
        question: str,
        query_results: list[dict[str, Any]],
        cypher_query: str,
        chat_history: str = "",
    ) -> AsyncIterator[str]:
        """
        토큰 단위 스트리밍 응답 생성

        Latency Optimization: 첫 토큰을 ~100ms 내에 반환하여 체감 레이턴시 개선

        Args:
            question: 사용자 질문
            query_results: Neo4j 쿼리 결과
            cypher_query: 실행된 Cypher 쿼리 (디버깅용)
            chat_history: 이전 대화 기록 (포맷된 문자열)

        Yields:
            str: 토큰 단위 텍스트 청크

        Raises:
            LLMResponseError: 스트리밍 실패 시
        """
        prompt = self._prompt_manager.load_prompt("response_generation")

        results_str = format_results(query_results)

        system_prompt = prompt["system"]
        user_prompt = prompt["user"].format(
            question=question,
            results_str=results_str,
            chat_history=format_chat_history_for_prompt(chat_history),
        )

        # 전송은 게이트웨이 스트리밍 primitive에 위임 (async generator semantics 보존)
        async for chunk in self._gateway.generate_stream(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.HEAVY,
        ):
            yield chunk

    async def generate_clarification(
        self,
        question: str,
        unresolved_entities: str,
    ) -> str:
        """
        명확화 요청 생성
        """
        prompt = self._prompt_manager.load_prompt("clarification")

        system_prompt = prompt["system"]
        user_prompt = prompt["user"].format(
            question=question,
            unresolved_entities=unresolved_entities or "없음",
        )

        return await self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.LIGHT,
        )

    async def decompose_query(
        self,
        question: str,
        schema: dict[str, Any] | None = None,
    ) -> QueryDecompositionResult:
        """
        Multi-hop 쿼리 분해

        복잡한 관계 쿼리를 단계별 그래프 순회 계획으로 분해합니다.

        Args:
            question: 사용자 질문
            schema: 그래프 스키마 (동적 속성 정보 포함)

        Returns:
            QueryDecompositionResult: 쿼리 분해 결과
        """
        prompt = self._prompt_manager.load_prompt("query_decomposition")

        schema_str = (
            format_schema(schema)
            if schema
            else "Schema information not available"
        )
        system_prompt = prompt["system"].format(schema_str=schema_str)
        user_prompt = prompt["user"].format(question=question)

        result = await self.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.LIGHT,
        )
        return cast(QueryDecompositionResult, result)

    async def close(self) -> None:
        """클라이언트 리소스 정리 (게이트웨이 위임)"""
        await self._gateway.close()

    # ============================================
    # Embedding 관련 메서드 — 게이트웨이 위임
    # ============================================

    async def get_embedding(self, text: str) -> list[float]:
        """텍스트 임베딩 생성 (게이트웨이 위임)"""
        return await self._gateway.get_embedding(text)
