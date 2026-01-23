"""
Open Information Extraction module.

Extracts (subject, relation, object) triples from unstructured text
using large language models. Works with or without a predefined schema.
"""

import asyncio
import logging
from typing import Any

from src.bootstrap.models import ExtractionResult, SchemaProposal, Triple
from src.repositories.llm_repository import LLMRepository, ModelTier
from src.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Maximum document length for LLM context window
MAX_DOCUMENT_LENGTH = 4000

# Characters to keep from source text for reference
SOURCE_TEXT_PREVIEW_LENGTH = 500

# Delay between batches to avoid rate limits (seconds)
BATCH_DELAY_SECONDS = 0.5


class OpenExtractor:
    """
    Open Information Extraction using LLMs.

    Extracts factual triples from documents without requiring
    a predefined schema, enabling schema-free knowledge extraction.
    """

    def __init__(
        self,
        llm_repository: LLMRepository,
        prompt_manager: PromptManager | None = None,
    ):
        """
        Initialize the OpenExtractor.

        Args:
            llm_repository: Repository for LLM API calls
            prompt_manager: Optional custom prompt manager (for testing)
        """
        self._llm = llm_repository
        self._prompt_manager = prompt_manager or PromptManager()

    async def extract_triples(
        self,
        document: str,
        schema_hint: SchemaProposal | None = None,
        min_confidence: float = 0.5,
    ) -> list[Triple]:
        """
        Extract triples from a single document.

        Args:
            document: Text document to extract triples from
            schema_hint: Optional schema to guide extraction
            min_confidence: Minimum confidence threshold (default 0.5)

        Returns:
            List of extracted Triples
        """
        if not document or not document.strip():
            logger.warning("Empty document provided for extraction")
            return []

        logger.debug(f"Extracting triples from document ({len(document)} chars)")

        # Load prompt template
        prompt = self._prompt_manager.load_prompt("open_extraction")

        # Format schema hint
        schema_hint_text = self._format_schema_hint(schema_hint)

        system_prompt = prompt["system"]
        user_prompt = prompt["user"].format(
            document=document[:MAX_DOCUMENT_LENGTH],
            schema_hint=schema_hint_text,
        )

        # Use LIGHT model for faster extraction
        response = await self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.LIGHT,
            temperature=0.1,  # Low temperature for consistent extraction
        )

        triples = self._parse_extraction_response(response, document, min_confidence)
        logger.info(f"Extracted {len(triples)} triples from document")

        return triples

    async def batch_extract(
        self,
        documents: list[str],
        schema_hint: SchemaProposal | None = None,
        batch_size: int = 10,
        min_confidence: float = 0.5,
    ) -> ExtractionResult:
        """
        Extract triples from multiple documents in batches.

        Args:
            documents: List of documents to process
            schema_hint: Optional schema to guide extraction
            batch_size: Number of concurrent extractions
            min_confidence: Minimum confidence threshold

        Returns:
            ExtractionResult containing all triples and metadata
        """
        if not documents:
            return ExtractionResult()

        logger.info(f"Batch extracting from {len(documents)} documents")
        result = ExtractionResult(document_count=len(documents))

        # Process in batches for rate limit management
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(documents) + batch_size - 1) // batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches}")

            # Create concurrent tasks
            tasks = [
                self._extract_with_error_handling(
                    doc=doc,
                    doc_id=f"doc_{i + j}",
                    schema_hint=schema_hint,
                    min_confidence=min_confidence,
                    result=result,
                )
                for j, doc in enumerate(batch)
            ]

            await asyncio.gather(*tasks)

            # Small delay between batches to avoid rate limits
            if i + batch_size < len(documents):
                await asyncio.sleep(BATCH_DELAY_SECONDS)

        logger.info(
            f"Extraction complete: {len(result.triples)} triples from "
            f"{result.document_count} documents, {len(result.errors)} errors"
        )

        return result

    async def _extract_with_error_handling(
        self,
        doc: str,
        doc_id: str,
        schema_hint: SchemaProposal | None,
        min_confidence: float,
        result: ExtractionResult,
    ) -> None:
        """Extract with error handling and result accumulation."""
        try:
            triples = await self.extract_triples(
                document=doc,
                schema_hint=schema_hint,
                min_confidence=min_confidence,
            )
            # Add document ID to metadata safely
            for triple in triples:
                if "document_id" not in triple.metadata:
                    triple.metadata["document_id"] = doc_id
            result.add_triples(triples)

        except TimeoutError as e:
            logger.warning(f"Timeout for {doc_id}: {e}")
            result.errors[doc_id] = f"TIMEOUT: {str(e)}"

        except ConnectionError as e:
            logger.error(f"Connection error for {doc_id}: {e}")
            result.errors[doc_id] = f"CONNECTION_ERROR: {str(e)}"

        except ValueError as e:
            # Validation errors (e.g., empty document)
            logger.warning(f"Validation error for {doc_id}: {e}")
            result.errors[doc_id] = f"VALIDATION_ERROR: {str(e)}"

        except Exception as e:
            # Unexpected errors - log with stack trace for debugging
            logger.exception(f"Unexpected error for {doc_id}")
            result.errors[doc_id] = f"UNKNOWN_ERROR: {str(e)}"

    async def extract_with_chunking(
        self,
        document: str,
        chunk_size: int = 2000,
        overlap: int = 200,
        schema_hint: SchemaProposal | None = None,
        min_confidence: float = 0.5,
    ) -> list[Triple]:
        """
        Extract triples from a long document by chunking.

        Useful for documents that exceed the context window limit.

        Args:
            document: Long document to process
            chunk_size: Size of each chunk in characters
            overlap: Overlap between chunks to preserve context
            schema_hint: Optional schema to guide extraction
            min_confidence: Minimum confidence threshold

        Returns:
            Deduplicated list of extracted Triples
        """
        if len(document) <= chunk_size:
            return await self.extract_triples(document, schema_hint, min_confidence)

        logger.info(f"Chunking document ({len(document)} chars) into {chunk_size}-char chunks")

        # Create overlapping chunks
        chunks = []
        start = 0
        while start < len(document):
            end = min(start + chunk_size, len(document))
            chunks.append(document[start:end])
            start = end - overlap
            if start >= len(document):
                break

        logger.info(f"Created {len(chunks)} chunks")

        # Extract from each chunk
        all_triples: list[Triple] = []
        for i, chunk in enumerate(chunks):
            triples = await self.extract_triples(chunk, schema_hint, min_confidence)
            for triple in triples:
                triple.metadata["chunk_index"] = i
            all_triples.extend(triples)

        # Deduplicate based on (subject, relation, object)
        unique_triples = self._deduplicate_triples(all_triples)
        logger.info(
            f"Deduplicated {len(all_triples)} -> {len(unique_triples)} triples"
        )

        return unique_triples

    def _format_schema_hint(self, schema: SchemaProposal | None) -> str:
        """Format schema as hint text for the prompt."""
        if schema is None:
            return "(스키마 힌트 없음 - 자유롭게 추출하세요)"

        lines = ["참고할 스키마:"]
        lines.append(f"- 노드 타입: {', '.join(schema.node_labels)}")
        lines.append(f"- 관계 타입: {', '.join(schema.relationship_types)}")
        return "\n".join(lines)

    def _parse_extraction_response(
        self,
        response: dict[str, Any],
        source_text: str,
        min_confidence: float,
    ) -> list[Triple]:
        """Parse LLM response into Triple objects."""
        triples = []

        raw_triples = response.get("triples", [])
        if not isinstance(raw_triples, list):
            logger.warning(f"Invalid triples format: {type(raw_triples)}")
            return []

        for item in raw_triples:
            try:
                confidence = float(item.get("confidence", 0.5))

                # Filter by confidence threshold
                if confidence < min_confidence:
                    continue

                triple = Triple(
                    subject=str(item.get("subject", "")).strip(),
                    relation=str(item.get("relation", "")).strip(),
                    object=str(item.get("object", "")).strip(),
                    confidence=confidence,
                    source_text=source_text[:SOURCE_TEXT_PREVIEW_LENGTH],
                )

                # Skip empty triples
                if triple.subject and triple.relation and triple.object:
                    triples.append(triple)

            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse triple {item}: {e}")
                continue

        return triples

    def _deduplicate_triples(self, triples: list[Triple]) -> list[Triple]:
        """Remove duplicate triples, keeping the highest confidence one."""
        seen: dict[tuple[str, str, str], Triple] = {}

        for triple in triples:
            key = (
                triple.subject.lower(),
                triple.relation.lower(),
                triple.object.lower(),
            )

            if key not in seen or triple.confidence > seen[key].confidence:
                seen[key] = triple

        return list(seen.values())
