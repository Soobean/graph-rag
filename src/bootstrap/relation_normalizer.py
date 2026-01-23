"""
Relation Normalizer module.

Groups semantically similar relations and assigns canonical names,
enabling consistent relationship types across the knowledge graph.
"""

import logging
from collections import Counter
from typing import Any

from src.bootstrap.models import (
    NormalizationResult,
    RelationGroup,
    SchemaProposal,
    Triple,
)
from src.bootstrap.utils import sanitize_user_input
from src.repositories.llm_repository import LLMRepository, ModelTier
from src.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class RelationNormalizer:
    """
    Normalizes relations by grouping semantically similar variants.

    Uses LLM to identify relation synonyms and assign canonical names
    in SCREAMING_SNAKE_CASE format suitable for Neo4j.
    """

    def __init__(
        self,
        llm_repository: LLMRepository,
        prompt_manager: PromptManager | None = None,
    ):
        """
        Initialize the RelationNormalizer.

        Args:
            llm_repository: Repository for LLM API calls
            prompt_manager: Optional custom prompt manager (for testing)
        """
        self._llm = llm_repository
        self._prompt_manager = prompt_manager or PromptManager()

    async def group_relations(
        self,
        triples: list[Triple],
        schema_hint: SchemaProposal | None = None,
        min_frequency: int = 1,
    ) -> NormalizationResult:
        """
        Group semantically similar relations from extracted triples.

        Args:
            triples: List of extracted triples
            schema_hint: Optional schema to guide grouping
            min_frequency: Minimum occurrences to include a relation

        Returns:
            NormalizationResult containing groups and mappings
        """
        if not triples:
            return NormalizationResult()

        # Count relation frequencies
        relation_counts = Counter(t.relation for t in triples)

        # Filter by minimum frequency
        filtered_relations = {
            rel: count
            for rel, count in relation_counts.items()
            if count >= min_frequency
        }

        if not filtered_relations:
            logger.warning("No relations meet minimum frequency threshold")
            return NormalizationResult()

        logger.info(
            f"Grouping {len(filtered_relations)} unique relations "
            f"(from {len(triples)} triples)"
        )

        # Format for prompt
        relations_text = self._format_relations_with_frequency(filtered_relations)
        schema_hint_text = self._format_schema_hint(schema_hint)

        # Load prompt template
        prompt = self._prompt_manager.load_prompt("relation_grouping")

        system_prompt = prompt["system"]
        user_prompt = prompt["user"].format(
            relations_with_frequency=relations_text,
            schema_hint=schema_hint_text,
        )

        # Use HEAVY model for semantic understanding
        response = await self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.HEAVY,
            temperature=0.2,
        )

        result = self._parse_grouping_response(response, triples, relation_counts)

        logger.info(
            f"Created {len(result.groups)} groups, "
            f"{len(result.unmapped_relations)} unmapped relations"
        )

        return result

    def normalize_triples(
        self,
        triples: list[Triple],
        normalization_result: NormalizationResult,
    ) -> list[Triple]:
        """
        Apply normalization to a list of triples.

        Args:
            triples: List of triples to normalize
            normalization_result: Result containing relation mappings

        Returns:
            List of triples with normalized relations
        """
        normalized = []
        for triple in triples:
            normalized_triple = normalization_result.normalize_triple(triple)
            normalized.append(normalized_triple)
        return normalized

    def merge_groups(
        self,
        groups: list[RelationGroup],
        manual_mappings: dict[str, str],
    ) -> list[RelationGroup]:
        """
        Merge groups based on manual HITL feedback.

        Args:
            groups: List of relation groups
            manual_mappings: User-provided mappings (variant -> canonical)

        Returns:
            Merged list of RelationGroup objects
        """
        if not manual_mappings:
            return groups

        logger.info(f"Applying {len(manual_mappings)} manual mappings")

        # Build canonical -> group mapping
        canonical_to_group: dict[str, RelationGroup] = {}
        for group in groups:
            canonical_to_group[group.canonical_name] = group

        # Apply manual mappings
        for variant, target_canonical in manual_mappings.items():
            target_canonical = target_canonical.upper().replace(" ", "_")

            # Find source group containing this variant
            source_group = None
            for group in groups:
                if variant in group.variants:
                    source_group = group
                    break

            if source_group is None:
                # Variant not found, create new group or add to existing
                if target_canonical in canonical_to_group:
                    canonical_to_group[target_canonical].add_variant(variant)
                else:
                    new_group = RelationGroup(
                        canonical_name=target_canonical,
                        variants=[variant],
                        frequency=1,
                    )
                    canonical_to_group[target_canonical] = new_group
                continue

            # Move variant to target group
            if target_canonical != source_group.canonical_name:
                # Remove from source
                source_group.variants.remove(variant)

                # Add to target (create if needed)
                if target_canonical in canonical_to_group:
                    canonical_to_group[target_canonical].add_variant(variant)
                else:
                    new_group = RelationGroup(
                        canonical_name=target_canonical,
                        variants=[variant],
                        frequency=1,
                    )
                    canonical_to_group[target_canonical] = new_group

        # Filter out empty groups
        result = [g for g in canonical_to_group.values() if g.variants]

        return result

    async def suggest_canonical_name(
        self,
        variants: list[str],
    ) -> str:
        """
        Suggest a canonical name for a list of relation variants.

        Args:
            variants: List of relation strings to unify

        Returns:
            Suggested canonical name in SCREAMING_SNAKE_CASE

        Raises:
            ValueError: If no variants provided or variants contain malicious content
        """
        if not variants:
            raise ValueError("At least one variant is required")

        # Sanitize each variant to prevent prompt injection
        sanitized_variants = []
        for i, variant in enumerate(variants[:20]):  # Limit to 20 variants
            try:
                sanitized = sanitize_user_input(
                    variant,
                    max_length=100,
                    field_name=f"variant[{i}]",
                )
                if sanitized:
                    sanitized_variants.append(sanitized)
            except ValueError:
                logger.warning(f"Skipping invalid variant: {variant[:50]}...")
                continue

        if not sanitized_variants:
            raise ValueError("No valid variants after sanitization")

        system_prompt = """당신은 관계 정규화 전문가입니다.
주어진 관계 변형들을 대표하는 영어 관계명을 SCREAMING_SNAKE_CASE로 제안하세요.

일반적인 지식 그래프 관계명 예시:
- WORKS_ON, MANAGES, REPORTS_TO, HAS_SKILL, KNOWS, MENTORS, CERTIFIED_IN"""

        user_prompt = f"""다음 관계들의 대표 이름을 제안하세요:
{', '.join(sanitized_variants)}

출력: 단일 SCREAMING_SNAKE_CASE 관계명만 응답하세요 (예: WORKS_ON)"""

        response = await self._llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_tier=ModelTier.LIGHT,
            temperature=0.1,
        )

        # Clean up response
        canonical = response.strip().upper().replace(" ", "_")
        # Remove any quotes or extra characters
        canonical = "".join(c for c in canonical if c.isalnum() or c == "_")

        return canonical

    def _format_relations_with_frequency(
        self,
        relation_counts: dict[str, int],
    ) -> str:
        """Format relations with their frequencies for the prompt."""
        # Sort by frequency descending
        sorted_relations = sorted(
            relation_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        lines = []
        for rel, count in sorted_relations[:100]:  # Limit to top 100
            lines.append(f"- \"{rel}\": {count}회")

        return "\n".join(lines)

    def _format_schema_hint(self, schema: SchemaProposal | None) -> str:
        """Format schema as hint text for the prompt."""
        if schema is None:
            return "(스키마 힌트 없음)"

        return f"권장 관계 타입: {', '.join(schema.relationship_types)}"

    def _parse_grouping_response(
        self,
        response: dict[str, Any],
        triples: list[Triple],
        relation_counts: dict[str, int],
    ) -> NormalizationResult:
        """Parse LLM response into NormalizationResult."""
        result = NormalizationResult()

        # Build triple lookup for examples
        relation_to_triples: dict[str, list[Triple]] = {}
        for triple in triples:
            if triple.relation not in relation_to_triples:
                relation_to_triples[triple.relation] = []
            relation_to_triples[triple.relation].append(triple)

        # Parse groups
        raw_groups = response.get("groups", [])
        for group_data in raw_groups:
            canonical = group_data.get("canonical_name", "UNKNOWN")
            variants = group_data.get("variants", [])
            description = group_data.get("description", "")

            # Calculate total frequency
            total_freq = sum(relation_counts.get(v, 0) for v in variants)

            # Collect examples
            examples: list[Triple] = []
            for variant in variants:
                if variant in relation_to_triples:
                    examples.extend(relation_to_triples[variant][:2])
                if len(examples) >= 5:
                    break

            group = RelationGroup(
                canonical_name=canonical,
                variants=variants,
                frequency=total_freq,
                examples=examples[:5],
                description=description,
            )

            result.groups.append(group)

            # Build mapping
            for variant in variants:
                result.mapping[variant] = group.canonical_name

        # Track unmapped relations
        mapped_relations = set(result.mapping.keys())
        all_relations = set(relation_counts.keys())
        result.unmapped_relations = list(all_relations - mapped_relations)

        # Also include unmapped from LLM response
        result.unmapped_relations.extend(response.get("unmapped", []))
        result.unmapped_relations = list(set(result.unmapped_relations))

        return result
