"""
LLM-based Schema Generator.

Automatically discovers and proposes a knowledge graph schema
by analyzing sample documents using large language models.
"""

import logging
from typing import Any

from src.bootstrap.models import SchemaProposal
from src.bootstrap.utils import sanitize_user_input
from src.repositories.llm_repository import LLMRepository, ModelTier
from src.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class SchemaGenerator:
    """
    LLM-based automatic schema generation for knowledge graphs.

    Uses large language models to analyze sample documents and propose
    an optimal schema including node labels, relationship types, and properties.
    """

    def __init__(
        self,
        llm_repository: LLMRepository,
        prompt_manager: PromptManager | None = None,
    ):
        """
        Initialize the SchemaGenerator.

        Args:
            llm_repository: Repository for LLM API calls
            prompt_manager: Optional custom prompt manager (for testing)
        """
        self._llm = llm_repository
        self._prompt_manager = prompt_manager or PromptManager()

    async def discover_schema(
        self,
        sample_documents: list[str],
        domain_hint: str | None = None,
    ) -> SchemaProposal:
        """
        Discover and propose a schema from sample documents.

        Args:
            sample_documents: List of sample text documents to analyze
            domain_hint: Optional description of the domain (e.g., "기업 인사/프로젝트 관리")

        Returns:
            SchemaProposal containing suggested node labels, relationships, and properties

        Raises:
            ValueError: If no documents provided
        """
        if not sample_documents:
            raise ValueError("At least one sample document is required")

        logger.info(f"Discovering schema from {len(sample_documents)} documents")

        # Format documents for prompt
        formatted_docs = self._format_documents(sample_documents)

        # Load prompt template
        prompt = self._prompt_manager.load_prompt("schema_discovery")

        system_prompt = prompt["system"]
        user_prompt = prompt["user"].format(
            domain_hint=domain_hint or "(도메인 힌트 없음)",
            document_count=len(sample_documents),
            documents=formatted_docs,
        )

        # Use HEAVY model for complex reasoning task
        response = await self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.HEAVY,
            temperature=0.3,  # Lower temperature for more consistent schema
        )

        logger.debug(f"Schema discovery response: {response}")

        return self._parse_schema_response(response)

    async def refine_schema(
        self,
        current_schema: SchemaProposal,
        feedback: str,
    ) -> SchemaProposal:
        """
        Refine an existing schema based on human feedback (HITL).

        Args:
            current_schema: The current schema proposal to refine
            feedback: Human feedback describing desired changes

        Returns:
            Refined SchemaProposal incorporating the feedback

        Raises:
            ValueError: If feedback is empty or contains malicious content
        """
        if not feedback or not feedback.strip():
            raise ValueError("Feedback cannot be empty")

        # Sanitize feedback to prevent prompt injection
        sanitized_feedback = sanitize_user_input(
            feedback,
            max_length=2000,
            field_name="feedback",
        )

        logger.info("Refining schema based on feedback")

        system_prompt = """당신은 지식 그래프 스키마 설계 전문가입니다.
기존 스키마를 사용자 피드백에 따라 개선하세요.

## 개선 원칙
1. 피드백에서 요청한 변경사항을 정확히 반영
2. 기존 스키마의 장점은 유지
3. 변경 근거를 reasoning에 명시"""

        user_prompt = f"""## 현재 스키마
{current_schema.get_schema_summary()}

## 사용자 피드백
{sanitized_feedback}

## 요청사항
피드백을 반영하여 스키마를 개선해주세요.

## 출력 형식 (JSON)
{{
    "node_labels": [...],
    "relationship_types": [...],
    "properties": {{...}},
    "constraints": {{...}},
    "reasoning": "변경 사항 설명..."
}}"""

        response = await self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.HEAVY,
            temperature=0.3,
        )

        return self._parse_schema_response(response)

    async def merge_schemas(
        self,
        schemas: list[SchemaProposal],
    ) -> SchemaProposal:
        """
        Merge multiple schema proposals into a unified schema.

        Useful when processing documents in batches or combining schemas
        from different document sets.

        Args:
            schemas: List of schema proposals to merge

        Returns:
            Unified SchemaProposal
        """
        if not schemas:
            raise ValueError("At least one schema is required for merging")

        if len(schemas) == 1:
            return schemas[0]

        logger.info(f"Merging {len(schemas)} schema proposals")

        # Format schemas for prompt
        schemas_text = "\n\n".join(
            f"### 스키마 {i + 1}\n{s.get_schema_summary()}" for i, s in enumerate(schemas)
        )

        system_prompt = """당신은 지식 그래프 스키마 통합 전문가입니다.
여러 스키마를 하나의 일관된 스키마로 통합하세요.

## 통합 원칙
1. 중복 라벨/관계는 하나로 병합
2. 유사한 개념은 더 일반적인 이름 사용
3. 모든 중요 속성 포함
4. 제약조건은 가장 엄격한 것 유지"""

        user_prompt = f"""## 통합할 스키마들
{schemas_text}

## 출력 형식 (JSON)
{{
    "node_labels": [...],
    "relationship_types": [...],
    "properties": {{...}},
    "constraints": {{...}},
    "reasoning": "통합 결정 근거..."
}}"""

        response = await self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.HEAVY,
            temperature=0.2,
        )

        return self._parse_schema_response(response)

    def _format_documents(
        self,
        documents: list[str],
        max_chars: int = 15000,
        max_doc_length: int = 2000,
    ) -> str:
        """Format documents for prompt, with truncation if needed."""
        formatted_parts = []
        total_chars = 0

        for i, doc in enumerate(documents):
            doc_len = len(doc)
            if doc_len > max_doc_length:
                truncated_chars = doc_len - max_doc_length
                doc = f"{doc[:max_doc_length]}... ({truncated_chars} chars truncated)"

            entry = f"### 문서 {i + 1}\n{doc}"
            entry_len = len(entry)

            if total_chars + entry_len > max_chars:
                remaining = len(documents) - i
                formatted_parts.append(f"\n... ({remaining}개 문서 생략, 토큰 제한)")
                break

            formatted_parts.append(entry)
            total_chars += entry_len

        return "\n\n".join(formatted_parts)

    def _parse_schema_response(self, response: dict[str, Any]) -> SchemaProposal:
        """Parse LLM response into SchemaProposal."""
        return SchemaProposal(
            node_labels=response.get("node_labels", []),
            relationship_types=response.get("relationship_types", []),
            properties=response.get("properties", {}),
            constraints=response.get("constraints", {}),
            confidence=response.get("confidence", 0.8),
            reasoning=response.get("reasoning", ""),
        )
