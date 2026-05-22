"""
LLM Repository - Azure OpenAI 접근 계층 (openai SDK 직접 사용)

책임:
- Azure OpenAI 클라이언트 관리
- 프롬프트 실행 및 응답 파싱
- 모델별 (light/heavy) 라우팅
- 재시도 및 에러 핸들링
"""

import json
import logging
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, AsyncAzureOpenAI, RateLimitError

from src.config import Settings
from src.domain.exceptions import (
    LLMConnectionError,
    LLMContentFilterError,
    LLMRateLimitError,
    LLMResponseError,
)
from src.domain.types import (
    CypherGenerationResult,
    EntityExtractionResult,
    IntentClassificationResult,
    IntentEntityExtractionResult,
    QueryDecompositionResult,
)
from src.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """모델 티어 구분"""

    LIGHT = "light"  # 빠른 작업 (intent, entity extraction)
    HEAVY = "heavy"  # 복잡한 작업 (cypher generation, response)


FALLBACK_EXCEPTIONS = (
    LLMRateLimitError,  # Rate limit 발생 시 (429)
    LLMConnectionError,  # 네트워크/연결 실패 시
    LLMResponseError,  # 응답 처리/파싱 실패 시
)
# LLMContentFilterError는 fallback 대상이 아님 — LIGHT/HEAVY 같은 정책 통과해야 하므로
# 재시도해도 막힘. 즉시 사용자에게 친화적 메시지로 전달.
#
# 현재 ContentFilter를 명시적으로 catch하는 노드는 cypher_generator만임.
# intent_entity_extractor, response_generator 등 다른 노드는 generic Exception으로
# 처리되어 사용자에게 "처리할 수 없습니다" 정도의 일반 에러로 전달됨.
# Phase 4 (Query 컨텍스트 마이그레이션) 시 BaseNode 또는 도메인 모델 레벨에서
# 일괄 처리 예정.


def _classify_api_status_error(e: APIStatusError) -> Exception:
    """
    Azure OpenAI APIStatusError를 도메인 예외로 분류.

    content_filter는 별도 예외로 분리 (fallback 불필요 + raw 메시지 노출 차단).
    그 외 400/4xx/5xx는 일반 LLMResponseError.
    """
    message = str(e.message) if e.message else str(e)
    if e.status_code == 400 and "content_filter" in message.lower():
        # Azure 응답에서 categories/param 추출 시도 (best effort)
        categories: dict[str, str] = {}
        param: str | None = None
        try:
            body = getattr(e, "body", None) or {}
            err = body.get("error", {}) if isinstance(body, dict) else {}
            param = err.get("param")
            inner = err.get("innererror", {}) or {}
            cfr = inner.get("content_filter_result", {}) or {}
            for k, v in cfr.items():
                if isinstance(v, dict) and v.get("filtered"):
                    categories[k] = v.get("severity", "unknown")
        except Exception:
            pass
        return LLMContentFilterError(categories=categories, param=param)
    # raw Azure 메시지를 노출하지 않도록 status_code만 전달
    return LLMResponseError(f"LLM API error (status={e.status_code})")


class LLMRepository:
    """
    Azure OpenAI LLM Repository (openai SDK 직접 사용)

    프로덕션 최적화:
    - openai SDK 직접 사용으로 최신 API 즉시 대응
    - 세밀한 retry/timeout 제어
    - 최소 의존성
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: AsyncAzureOpenAI | None = None
        self._prompt_manager = PromptManager()

        logger.info(
            f"LLMRepository initialized: light={settings.light_model_deployment}, "
            f"heavy={settings.heavy_model_deployment}"
        )

    def _get_client(self) -> AsyncAzureOpenAI:
        """Azure OpenAI 클라이언트 반환 (lazy initialization)"""
        if self._client is None:
            try:
                self._client = AsyncAzureOpenAI(
                    azure_endpoint=self._settings.azure_openai_endpoint,
                    api_key=self._settings.azure_openai_api_key,
                    api_version=self._settings.azure_openai_api_version,
                    timeout=60.0,
                    max_retries=3,
                )
            except Exception as e:
                logger.error(f"Failed to create Azure OpenAI client: {e}")
                raise LLMConnectionError(f"Failed to initialize LLM client: {e}") from e
        return self._client

    def _get_deployment(self, tier: ModelTier) -> str:
        """모델 티어에 따른 배포명 반환"""
        if tier == ModelTier.LIGHT:
            return self._settings.light_model_deployment
        return self._settings.heavy_model_deployment

    def _supports_temperature(self, deployment: str) -> bool:
        """모델이 temperature 파라미터를 지원하는지 확인"""
        # GPT-5 이상 모델은 temperature를 지원하지 않음
        return not deployment.lower().startswith("gpt-5")

    def _format_chat_history_for_prompt(self, chat_history: str) -> str:
        """
        프롬프트용 chat_history 포맷팅

        빈 문자열이나 공백만 있는 경우 기본 메시지로 대체합니다.

        Args:
            chat_history: format_chat_history()의 반환값

        Returns:
            프롬프트에 삽입할 chat_history 문자열
        """
        return chat_history.strip() or "(No previous conversation)"

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_tier: ModelTier = ModelTier.LIGHT,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> str:
        """
        텍스트 생성
        """
        client = self._get_client()
        deployment = self._get_deployment(model_tier)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # API 호출 파라미터 구성
            api_params: dict[str, Any] = {
                "model": deployment,
                "messages": messages,
                "max_completion_tokens": max_completion_tokens
                if max_completion_tokens is not None
                else self._settings.llm_max_tokens,
            }

            # GPT-5 이상 모델은 temperature 미지원
            if self._supports_temperature(deployment):
                api_params["temperature"] = (
                    temperature
                    if temperature is not None
                    else self._settings.llm_temperature
                )

            response = await client.chat.completions.create(**api_params)

            # 빈 응답 체크
            if not response.choices:
                raise LLMResponseError("No response choices returned from LLM")

            result = response.choices[0].message.content or ""
            logger.debug(f"LLM response ({model_tier.value}): {result[:100]}...")
            return result

        except RateLimitError as e:
            logger.warning(f"Rate limit exceeded: {e}")
            raise LLMRateLimitError(str(e)) from e
        except APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            raise LLMConnectionError(str(e)) from e
        except APIStatusError as e:
            # content_filter 등 raw Azure 메시지는 사용자에게 노출하지 않음
            mapped = _classify_api_status_error(e)
            if isinstance(mapped, LLMContentFilterError):
                logger.warning(
                    f"Content filter triggered: param={mapped.param}, "
                    f"categories={mapped.categories}"
                )
            else:
                logger.error(f"API status error (status={e.status_code})")
            raise mapped from e
        except Exception as e:
            # 예상치 못한 에러
            logger.error(f"LLM generation failed: {e}")
            raise LLMResponseError(f"Failed to generate response: {e}") from e

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model_tier: ModelTier = ModelTier.LIGHT,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """
        JSON 형식 응답 생성 (기본 dict 반환)
        """
        client = self._get_client()
        deployment = self._get_deployment(model_tier)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # API 호출 파라미터 구성
            api_params: dict[str, Any] = {
                "model": deployment,
                "messages": messages,
                "max_completion_tokens": self._settings.llm_max_tokens,
                "response_format": {"type": "json_object"},
            }

            # GPT-5 이상 모델은 temperature 미지원
            if self._supports_temperature(deployment):
                api_params["temperature"] = (
                    temperature
                    if temperature is not None
                    else self._settings.llm_temperature
                )

            response = await client.chat.completions.create(**api_params)

            if not response.choices:
                raise LLMResponseError("No response choices returned from LLM")

            content = response.choices[0].message.content or "{}"
            result: dict[str, Any] = json.loads(content)
            logger.debug(f"LLM JSON response ({model_tier.value}): {result}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            raise LLMResponseError(f"Invalid JSON response: {e}") from e
        except RateLimitError as e:
            logger.warning(f"Rate limit exceeded: {e}")
            raise LLMRateLimitError(str(e)) from e
        except APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            raise LLMConnectionError(str(e)) from e
        except APIStatusError as e:
            mapped = _classify_api_status_error(e)
            if isinstance(mapped, LLMContentFilterError):
                logger.warning(
                    f"Content filter triggered (JSON): param={mapped.param}, "
                    f"categories={mapped.categories}"
                )
            else:
                logger.error(f"API status error (JSON, status={e.status_code})")
            raise mapped from e
        except Exception as e:
            logger.error(f"LLM JSON generation failed: {e}")
            raise LLMResponseError(f"Failed to generate JSON response: {e}") from e

    # ============================================
    # Fallback 헬퍼 메서드 (HEAVY → LIGHT)
    # ============================================

    async def _generate_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> str:
        """
        텍스트 생성 with Fallback (HEAVY → LIGHT → Error)

        HEAVY 티어 실패 시 LIGHT 티어로 자동 fallback합니다.

        Args:
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트
            temperature: 온도 파라미터 (선택, 모델 미지원 시 자동 제외)
            max_completion_tokens: 최대 토큰 수 (선택)

        Returns:
            생성된 텍스트

        Raises:
            LLMResponseError: HEAVY, LIGHT 모두 실패 시

        Note:
            - 모든 티어가 실패하면 마지막 에러를 포함한 LLMResponseError 발생
            - HEAVY와 LIGHT가 서로 다른 예외로 실패할 수 있음
        """
        # 1. HEAVY 티어 시도
        try:
            return await self.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_tier=ModelTier.HEAVY,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
            )
        except FALLBACK_EXCEPTIONS as e:
            logger.warning(
                f"HEAVY tier failed, falling back to LIGHT: {type(e).__name__}: {e}"
            )

        # 2. LIGHT 티어 fallback
        try:
            result = await self.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_tier=ModelTier.LIGHT,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
            )
            logger.info("Fallback to LIGHT tier succeeded")
            return result
        except FALLBACK_EXCEPTIONS as e:
            logger.error(f"LIGHT tier also failed: {type(e).__name__}: {e}")
            raise LLMResponseError(f"All model tiers failed. Last error: {e}") from e

    async def _generate_json_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """
        JSON 생성 with Fallback (HEAVY → LIGHT → Error)

        HEAVY 티어 실패 시 LIGHT 티어로 자동 fallback합니다.

        Args:
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트
            temperature: 온도 파라미터 (선택, 모델 미지원 시 자동 제외)

        Returns:
            생성된 JSON (dict)

        Raises:
            LLMResponseError: HEAVY, LIGHT 모두 실패 시

        Note:
            - 모든 티어가 실패하면 마지막 에러를 포함한 LLMResponseError 발생
            - HEAVY와 LIGHT가 서로 다른 예외로 실패할 수 있음
        """
        # 1. HEAVY 티어 시도
        try:
            return await self.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_tier=ModelTier.HEAVY,
                temperature=temperature,
            )
        except FALLBACK_EXCEPTIONS as e:
            logger.warning(
                f"HEAVY tier failed, falling back to LIGHT: {type(e).__name__}: {e}"
            )

        # 2. LIGHT 티어 fallback
        try:
            result = await self.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_tier=ModelTier.LIGHT,
                temperature=temperature,
            )
            logger.info("Fallback to LIGHT tier succeeded (JSON)")
            return result
        except FALLBACK_EXCEPTIONS as e:
            logger.error(f"LIGHT tier also failed (JSON): {type(e).__name__}: {e}")
            raise LLMResponseError(f"All model tiers failed. Last error: {e}") from e

    async def classify_intent(
        self,
        question: str,
        available_intents: list[str],
        chat_history: str = "",
    ) -> IntentClassificationResult:
        """
        질문 의도 분류

        Returns:
            IntentClassificationResult: Intent classification result
        """
        prompt = self._prompt_manager.load_prompt("intent_classification")

        system_prompt = prompt["system"].format(
            available_intents=", ".join(available_intents)
        )
        user_prompt = prompt["user"].format(
            question=question,
            chat_history=self._format_chat_history_for_prompt(chat_history),
        )

        result = await self.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.LIGHT,
        )
        # Type safety: Cast result to TypedDict
        # In a strict environment, we might want to use Pydantic to validate here.
        # But for now we trust the LLM/JSON structure or let it fail downstream if missing keys.
        return cast(IntentClassificationResult, result)

    async def extract_entities(
        self,
        question: str,
        entity_types: list[str],
        chat_history: str = "",
    ) -> EntityExtractionResult:
        """
        질문에서 엔티티 추출

        Returns:
            EntityExtractionResult: Extracted entities
        """
        prompt = self._prompt_manager.load_prompt("entity_extraction")

        system_prompt = prompt["system"].format(entity_types=", ".join(entity_types))
        user_prompt = prompt["user"].format(
            question=question,
            chat_history=self._format_chat_history_for_prompt(chat_history),
        )

        result = await self.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.LIGHT,
        )
        return cast(EntityExtractionResult, result)

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
            chat_history=self._format_chat_history_for_prompt(chat_history),
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

        schema_str = self._format_schema(schema)
        entities_str = self._format_entities(entities)
        query_plan_str = self._format_query_plan(query_plan)

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

        results_str = self._format_results(query_results)

        system_prompt = prompt["system"]
        user_prompt = prompt["user"].format(
            question=question,
            results_str=results_str,
            chat_history=self._format_chat_history_for_prompt(chat_history),
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

        results_str = self._format_results(query_results)

        system_prompt = prompt["system"]
        user_prompt = prompt["user"].format(
            question=question,
            results_str=results_str,
            chat_history=self._format_chat_history_for_prompt(chat_history),
        )

        client = self._get_client()
        deployment = self._get_deployment(ModelTier.HEAVY)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            api_params: dict[str, Any] = {
                "model": deployment,
                "messages": messages,
                "max_completion_tokens": self._settings.llm_max_tokens,
                "stream": True,
            }

            # GPT-5 이상 모델은 temperature 미지원
            if self._supports_temperature(deployment):
                api_params["temperature"] = self._settings.llm_temperature

            logger.info(f"Starting response streaming (deployment: {deployment})")

            response = await client.chat.completions.create(**api_params)

            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except RateLimitError as e:
            logger.warning(f"Rate limit exceeded during streaming: {e}")
            raise LLMRateLimitError(str(e)) from e
        except APIConnectionError as e:
            logger.error(f"API connection error during streaming: {e}")
            raise LLMConnectionError(str(e)) from e
        except APIStatusError as e:
            mapped = _classify_api_status_error(e)
            if isinstance(mapped, LLMContentFilterError):
                logger.warning(
                    f"Content filter triggered (stream): param={mapped.param}, "
                    f"categories={mapped.categories}"
                )
            else:
                logger.error(
                    f"API status error during streaming (status={e.status_code})"
                )
            raise mapped from e
        except Exception as e:
            logger.error(f"Response streaming failed: {e}")
            raise LLMResponseError(f"Failed to stream response: {e}") from e

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
            self._format_schema(schema)
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
        """클라이언트 리소스 정리"""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("LLM client closed")

    # ============================================
    # Embedding 관련 메서드
    # ============================================

    async def get_embedding(self, text: str) -> list[float]:
        """
        Azure OpenAI Embedding API를 통해 텍스트 임베딩 생성

        Args:
            text: 임베딩할 텍스트

        Returns:
            임베딩 벡터 (list[float])

        Raises:
            LLMResponseError: 임베딩 생성 실패 시
        """
        client = self._get_client()

        try:
            # text-embedding-3-small/large는 dimensions 파라미터 지원
            deployment = self._settings.embedding_model_deployment
            expected_dims = self._settings.embedding_dimensions

            response = await client.embeddings.create(
                model=deployment,
                input=text,
                dimensions=expected_dims,
            )

            embedding = response.data[0].embedding
            logger.debug(
                f"Generated embedding: dim={len(embedding)}, text='{text[:50]}...'"
            )
            return embedding

        except RateLimitError as e:
            logger.warning(f"Embedding rate limit exceeded: {e}")
            raise LLMRateLimitError(str(e)) from e
        except APIConnectionError as e:
            logger.error(f"Embedding API connection error: {e}")
            raise LLMConnectionError(str(e)) from e
        except APIStatusError as e:
            logger.error(f"Embedding API status error: {e}")
            raise LLMResponseError(
                f"Embedding API error: {e.status_code} - {e.message}"
            ) from e
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise LLMResponseError(f"Failed to generate embedding: {e}") from e

    async def get_embeddings_batch(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        """
        여러 텍스트 일괄 임베딩 생성 (배치 처리)

        Args:
            texts: 임베딩할 텍스트 리스트 (최대 2048개)
            batch_size: 배치 크기 (API 제한에 맞게 조절)

        Returns:
            임베딩 벡터 리스트

        Raises:
            LLMResponseError: 임베딩 생성 실패 시
        """
        if not texts:
            return []

        client = self._get_client()
        all_embeddings: list[list[float]] = []
        deployment = self._settings.embedding_model_deployment

        try:
            # 배치 단위로 처리
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]

                response = await client.embeddings.create(
                    model=deployment,
                    input=batch,
                    dimensions=self._settings.embedding_dimensions,
                )

                # 순서대로 결과 추가
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

            logger.info(f"Generated {len(all_embeddings)} embeddings in batch")
            return all_embeddings

        except RateLimitError as e:
            logger.warning(f"Batch embedding rate limit exceeded: {e}")
            raise LLMRateLimitError(str(e)) from e
        except APIConnectionError as e:
            logger.error(f"Batch embedding API connection error: {e}")
            raise LLMConnectionError(str(e)) from e
        except APIStatusError as e:
            logger.error(f"Batch embedding API status error: {e}")
            raise LLMResponseError(
                f"Embedding API error: {e.status_code} - {e.message}"
            ) from e
        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            raise LLMResponseError(f"Failed to generate batch embeddings: {e}") from e

    def _format_schema(self, schema: dict[str, Any]) -> str:
        """스키마를 문자열로 포맷팅 (속성 정보 + enum 값 포함)"""
        lines = []

        # 노드 스키마 (속성 정보가 있으면 포함)
        nodes = schema.get("nodes")
        if nodes:
            lines.append("Nodes:")
            for node in nodes:
                label = node.get("label", "Unknown")
                props = node.get("properties", [])
                if props:
                    prop_parts = []
                    for p in props:
                        name = p.get("name", "")
                        if not name:
                            continue
                        sample = p.get("sample_values")
                        if sample:
                            prop_parts.append(f"{name}[{', '.join(sample)}]")
                        else:
                            prop_parts.append(name)
                    lines.append(f"  {label} ({', '.join(prop_parts)})")
                else:
                    lines.append(f"  {label}")
        else:
            labels = schema.get("node_labels", [])
            if labels:
                lines.append(f"Node Labels: {', '.join(labels)}")

        # 관계 스키마 (속성 정보가 있으면 포함)
        rels = schema.get("relationships")
        if rels:
            lines.append("Relationships:")
            for rel in rels:
                rel_type = rel.get("type", "Unknown")
                props = rel.get("properties", [])
                if props:
                    prop_parts = []
                    for p in props:
                        name = p.get("name", "")
                        if not name:
                            continue
                        sample = p.get("sample_values")
                        if sample:
                            prop_parts.append(f"{name}[{', '.join(sample)}]")
                        else:
                            prop_parts.append(name)
                    lines.append(f"  {rel_type} ({', '.join(prop_parts)})")
                else:
                    lines.append(f"  {rel_type}")
        else:
            rel_types = schema.get("relationship_types", [])
            if rel_types:
                lines.append(f"Relationship Types: {', '.join(rel_types)}")

        return "\n".join(lines) if lines else "Schema information not available"

    def _format_entities(self, entities: list[dict[str, Any]]) -> str:
        """엔티티 리스트를 문자열로 포맷팅"""
        if not entities:
            return "No entities extracted"

        lines = []
        for entity in entities:
            lines.append(
                f"- {entity.get('type', 'Unknown')}: {entity.get('value', '')} "
                f"(normalized: {entity.get('normalized', '')})"
            )
        return "\n".join(lines)

    def _format_query_plan(self, query_plan: dict[str, Any] | None) -> str:
        """Multi-hop 쿼리 계획을 문자열로 포맷팅"""
        if not query_plan:
            return "No query plan (single-hop query)"

        if not query_plan.get("is_multi_hop"):
            return "Single-hop query"

        lines = [
            f"Multi-hop Query Plan ({query_plan.get('hop_count', 0)} hops):",
            f"Goal: {query_plan.get('final_return', 'unknown')}",
        ]

        hops = query_plan.get("hops", [])
        for hop in hops:
            step = hop.get("step", "?")
            desc = hop.get("description", "")
            rel = hop.get("relationship", "")
            direction = hop.get("direction", "")
            filter_cond = hop.get("filter_condition", "")

            hop_line = f"  Step {step}: {desc}"
            if rel:
                hop_line += f" [{rel}, {direction}]"
            if filter_cond:
                hop_line += f" WHERE {filter_cond}"
            lines.append(hop_line)

        return "\n".join(lines)

    def _format_results(self, results: list[dict[str, Any]]) -> str:
        """
        쿼리 결과를 문자열로 포맷팅.

        핵심 원칙: 각 row의 (노드, 관계, 노드) 페어 정보를 보존한다.
        이전 구현은 노드를 라벨별로 그룹화하여 어떤 노드가 어떤 노드와 관계되는지 잃었음.
        """
        if not results:
            return "No results found"

        MAX_PAIR_ROWS = 60  # row 단위로 직접 보여줄 최대 개수
        MAX_PROP_DISPLAY = 6  # 한 노드의 표시 속성 수
        SKIP_PROPS = {"embedding", "vector", "id"}

        def _is_node(value: Any) -> bool:
            return (
                isinstance(value, dict)
                and "labels" in value
                and isinstance(value.get("labels"), list)
            )

        def _is_rel(value: Any) -> bool:
            return (
                isinstance(value, dict)
                and "type" in value
                and ("startNodeId" in value or "start" in value)
            )

        def _fmt_node(value: dict[str, Any]) -> str:
            """노드를 '이름:라벨(주요속성)' 형태로 직렬화"""
            labels = value.get("labels", [])
            label = labels[0] if labels else "Node"
            props = value.get("properties", {}) or {}
            name = props.get("name", "?")
            prop_strs = []
            for k, v in props.items():
                if k in SKIP_PROPS or k == "name" or v is None:
                    continue
                prop_strs.append(f"{k}={v}")
            extras = ", ".join(prop_strs[:MAX_PROP_DISPLAY])
            return f"{name}:{label}" + (f"({extras})" if extras else "")

        def _fmt_rel(value: dict[str, Any]) -> str:
            """관계를 '-[TYPE props]->' 형태로 직렬화"""
            rel_type = value.get("type", "RELATED")
            props = value.get("properties", {}) or {}
            prop_strs = [
                f"{k}={v}"
                for k, v in props.items()
                if k not in SKIP_PROPS and v is not None
            ]
            extras = " ".join(prop_strs[:4])
            return f"-[{rel_type}{(' ' + extras) if extras else ''}]->"

        # 라벨/관계 통계 수집 + row별 표현 생성
        node_count_by_label: dict[str, int] = {}
        seen_node_ids: set[str] = set()
        rel_counts: dict[str, int] = {}
        formatted_rows: list[str] = []
        scalar_rows: list[dict[str, Any]] = []

        for row in results:
            has_struct = False
            parts: list[str] = []
            for key, value in row.items():
                if _is_node(value):
                    has_struct = True
                    # id가 빈 문자열인 경우에도 elementId로 fallback
                    node_id = value.get("id") or value.get("elementId") or ""
                    if node_id and node_id not in seen_node_ids:
                        seen_node_ids.add(node_id)
                        labels = value.get("labels", [])
                        if labels:
                            node_count_by_label[labels[0]] = (
                                node_count_by_label.get(labels[0], 0) + 1
                            )
                    parts.append(f"{key}={_fmt_node(value)}")
                elif _is_rel(value):
                    has_struct = True
                    rel_type = value.get("type", "RELATED")
                    rel_counts[rel_type] = rel_counts.get(rel_type, 0) + 1
                    parts.append(f"{key}{_fmt_rel(value)}")
                elif value is not None:
                    parts.append(f"{key}={value}")

            if has_struct:
                formatted_rows.append(" | ".join(parts))
            else:
                scalar_rows.append(row)

        lines: list[str] = []

        # 1) 헤더: 전체 통계 (LLM에게 데이터 규모 안내)
        if formatted_rows:
            stats_parts = []
            if node_count_by_label:
                stats_parts.append(
                    "노드: "
                    + ", ".join(
                        f"{lbl}={cnt}" for lbl, cnt in node_count_by_label.items()
                    )
                )
            if rel_counts:
                stats_parts.append(
                    "관계: " + ", ".join(f"{r}={c}" for r, c in rel_counts.items())
                )
            lines.append(
                f"총 {len(results)}행 ({'; '.join(stats_parts) if stats_parts else ''})"
            )
            lines.append("")
            lines.append("--- 각 행 (subject | relation | object) ---")

            # 2) row 단위 페어 데이터 (페어 정보 보존)
            for i, row_str in enumerate(formatted_rows[:MAX_PAIR_ROWS], 1):
                lines.append(f"{i}. {row_str}")
            if len(formatted_rows) > MAX_PAIR_ROWS:
                lines.append(
                    f"... 외 {len(formatted_rows) - MAX_PAIR_ROWS}개 행 (LLM은 위 샘플로 답변)"
                )

        # 3) 스칼라/집계 결과 (그대로 표시)
        if scalar_rows:
            if lines:
                lines.append("")
            lines.append(f"집계 결과 ({len(scalar_rows)}행):")
            for i, row in enumerate(scalar_rows[:30], 1):
                parts = [f"{k}={v}" for k, v in row.items() if v is not None]
                lines.append(f"  {i}. {', '.join(parts)}")
            if len(scalar_rows) > 30:
                lines.append(f"  ... 외 {len(scalar_rows) - 30}개")

        if not lines:
            return "No results found"

        return "\n".join(lines)
