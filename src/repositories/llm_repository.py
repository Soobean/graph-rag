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
from enum import Enum
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, AsyncAzureOpenAI, RateLimitError

from src.config import Settings
from src.domain.exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
)
from src.domain.types import (
    CypherGenerationResult,
    EntityExtractionResult,
    IntentClassificationResult,
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
            logger.error(f"API status error: {e}")
            raise LLMResponseError(f"API error: {e.status_code} - {e.message}") from e
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
            logger.error(f"API status error: {e}")
            raise LLMResponseError(f"API error: {e.status_code} - {e.message}") from e
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

    async def generate_cypher(
        self,
        question: str,
        schema: dict[str, Any],
        entities: list[dict[str, Any]],
        query_plan: dict[str, Any] | None = None,
    ) -> CypherGenerationResult:
        """
        Cypher 쿼리 생성 (with Fallback: HEAVY → LIGHT → Error)

        Cypher 생성은 복잡한 작업이므로 HEAVY 티어를 우선 사용하고,
        실패 시 LIGHT 티어로 fallback합니다.

        Args:
            question: 사용자 질문
            schema: 그래프 스키마
            entities: 추출된 엔티티 목록
            query_plan: Multi-hop 쿼리 계획 (선택적)

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
        )

        # Fallback 적용: HEAVY → LIGHT → Error
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
    ) -> QueryDecompositionResult:
        """
        Multi-hop 쿼리 분해

        복잡한 관계 쿼리를 단계별 그래프 순회 계획으로 분해합니다.

        Args:
            question: 사용자 질문

        Returns:
            QueryDecompositionResult: 쿼리 분해 결과
        """
        prompt = self._prompt_manager.load_prompt("query_decomposition")

        system_prompt = prompt["system"]
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
        """스키마를 문자열로 포맷팅"""
        lines = []

        labels = schema.get("node_labels", [])
        if labels:
            lines.append(f"Node Labels: {', '.join(labels)}")

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
        """쿼리 결과를 문자열로 포맷팅 (엔티티 기준 그룹핑)"""
        if not results:
            return "No results found"

        # 엔티티(노드) 기준으로 결과 그룹핑
        entities: dict[str, dict[str, Any]] = {}
        relationships: list[str] = []

        for row in results:
            for _key, value in row.items():
                if isinstance(value, dict):
                    # 노드 형식 감지 (labels 속성이 있는 경우)
                    if "labels" in value and isinstance(value.get("labels"), list):
                        node_id = value.get("id", value.get("elementId", ""))
                        if node_id and node_id not in entities:
                            props = value.get("properties", {})
                            name = props.get("name", "Unknown")
                            label = value["labels"][0] if value["labels"] else "Node"
                            entities[node_id] = {
                                "label": label,
                                "name": name,
                                "properties": props,
                            }
                    # 관계 형식 감지
                    elif "type" in value and ("startNodeId" in value or "start" in value):
                        rel_type = value.get("type", "RELATED")
                        relationships.append(rel_type)

        # 엔티티를 라벨별로 그룹핑
        by_label: dict[str, list[dict[str, Any]]] = {}
        for _node_id, entity in entities.items():
            label = entity["label"]
            if label not in by_label:
                by_label[label] = []
            by_label[label].append(entity)

        # 포맷팅
        lines = [f"총 {len(entities)}개의 고유 엔티티, {len(results)}개의 관계 결과:"]

        for label, ents in by_label.items():
            lines.append(f"\n[{label}] ({len(ents)}개):")
            # 각 라벨별로 최대 15개까지 표시
            for i, ent in enumerate(ents[:15], 1):
                props = ent.get("properties", {})
                # 주요 속성 추출
                prop_strs = []
                for k, v in props.items():
                    if k not in ("embedding", "vector") and v is not None:
                        prop_strs.append(f"{k}={v}")
                props_display = ", ".join(prop_strs[:5])
                lines.append(f"  {i}. {ent['name']} ({props_display})")
            if len(ents) > 15:
                lines.append(f"  ... 외 {len(ents) - 15}개")

        return "\n".join(lines)
