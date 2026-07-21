"""
Azure OpenAI Gateway - LLM 전송 계층 (infrastructure)

책임:
- Azure OpenAI 클라이언트 관리 (lazy init, 리소스 정리)
- 모델 티어(LIGHT/HEAVY) → 배포명 라우팅
- 텍스트/JSON/스트리밍 생성 primitive
- HEAVY → LIGHT fallback 정책
- 임베딩 생성
- API 에러 → 도메인 예외 분류

프롬프트 조립/포맷팅은 이 계층의 책임이 아님 (application 계층 담당).
"""

import json
import logging
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncAzureOpenAI, RateLimitError

from src.config import Settings
from src.domain.exceptions import (
    LLMConnectionError,
    LLMContentFilterError,
    LLMRateLimitError,
    LLMResponseError,
)

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


def classify_api_status_error(e: APIStatusError) -> Exception:
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


class AzureOpenAIGateway:
    """
    Azure OpenAI 전송 게이트웨이 (openai SDK 직접 사용)

    프로덕션 최적화:
    - openai SDK 직접 사용으로 최신 API 즉시 대응
    - 세밀한 retry/timeout 제어
    - 최소 의존성
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: AsyncAzureOpenAI | None = None

        logger.info(
            f"AzureOpenAIGateway initialized: light={settings.light_model_deployment}, "
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
            mapped = classify_api_status_error(e)
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
            mapped = classify_api_status_error(e)
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

    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model_tier: ModelTier = ModelTier.HEAVY,
    ) -> AsyncIterator[str]:
        """
        토큰 단위 스트리밍 생성 (전송 primitive)

        Latency Optimization: 첫 토큰을 ~100ms 내에 반환하여 체감 레이턴시 개선

        Args:
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트
            model_tier: 모델 티어 (기본 HEAVY)

        Yields:
            str: 토큰 단위 텍스트 청크

        Raises:
            LLMResponseError: 스트리밍 실패 시
        """
        client = self._get_client()
        deployment = self._get_deployment(model_tier)

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
            mapped = classify_api_status_error(e)
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

    # ============================================
    # Fallback 정책 (HEAVY → LIGHT)
    # ============================================

    async def generate_with_fallback(
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

    async def generate_json_with_fallback(
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

    # ============================================
    # Embedding
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

    async def close(self) -> None:
        """클라이언트 리소스 정리"""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("LLM client closed")
