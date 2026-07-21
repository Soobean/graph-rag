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
        """클라이언트 리소스 정리 (게이트웨이 위임)"""
        await self._gateway.close()

    # ============================================
    # Embedding 관련 메서드 — 게이트웨이 위임
    # ============================================

    async def get_embedding(self, text: str) -> list[float]:
        """텍스트 임베딩 생성 (게이트웨이 위임)"""
        return await self._gateway.get_embedding(text)

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
