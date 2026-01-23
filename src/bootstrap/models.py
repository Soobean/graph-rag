from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.bootstrap.utils import to_pascal_case, to_screaming_snake


class ConfidenceLevel(Enum):
    """Confidence level categorization for extracted information."""

    HIGH = "high"  # >= 0.8
    MEDIUM = "medium"  # >= 0.5
    LOW = "low"  # < 0.5

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        """Convert numeric confidence to categorical level."""
        if score >= 0.8:
            return cls.HIGH
        elif score >= 0.5:
            return cls.MEDIUM
        else:
            return cls.LOW


@dataclass
class Triple:
    """
    Open Extraction result - a single fact as (subject, relation, object).

    Attributes:
        subject: The entity performing the action or having the property
        relation: The relationship or action connecting subject to object
        object: The target entity or value
        confidence: Extraction confidence score (0.0 to 1.0)
        source_text: Original text from which this triple was extracted
        metadata: Additional extraction metadata (e.g., document_id, position)
    """

    subject: str
    relation: str
    object: str
    confidence: float
    source_text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate confidence score."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Confidence must be between 0 and 1, got {self.confidence}"
            )

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get categorical confidence level."""
        return ConfidenceLevel.from_score(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "subject": self.subject,
            "relation": self.relation,
            "object": self.object,
            "confidence": self.confidence,
            "source_text": self.source_text,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Triple":
        """Create Triple from dictionary."""
        return cls(
            subject=data["subject"],
            relation=data["relation"],
            object=data["object"],
            confidence=data.get("confidence", 0.5),
            source_text=data.get("source_text", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SchemaProposal:
    """
    LLM-generated schema suggestion for a knowledge graph.

    Attributes:
        node_labels: Proposed entity types (e.g., ["Person", "Project", "Skill"])
        relationship_types: Proposed relation types (e.g., ["WORKS_ON", "HAS_SKILL"])
        properties: Property names for each node label
        constraints: Suggested uniqueness/index constraints
        confidence: Overall schema confidence score
        reasoning: LLM's explanation for schema design choices
    """

    node_labels: list[str]
    relationship_types: list[str]
    properties: dict[str, list[str]]  # label -> property names
    constraints: dict[str, list[str]] = field(
        default_factory=dict
    )  # label -> unique props
    confidence: float = 0.8
    reasoning: str = ""

    def __post_init__(self) -> None:
        """Validate and normalize schema proposal."""
        # Normalize labels to PascalCase
        self.node_labels = [to_pascal_case(label) for label in self.node_labels]
        # Normalize relationship types to SCREAMING_SNAKE_CASE
        self.relationship_types = [
            to_screaming_snake(rel) for rel in self.relationship_types
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "node_labels": self.node_labels,
            "relationship_types": self.relationship_types,
            "properties": self.properties,
            "constraints": self.constraints,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchemaProposal":
        """Create SchemaProposal from dictionary."""
        return cls(
            node_labels=data.get("node_labels", []),
            relationship_types=data.get("relationship_types", []),
            properties=data.get("properties", {}),
            constraints=data.get("constraints", {}),
            confidence=data.get("confidence", 0.8),
            reasoning=data.get("reasoning", ""),
        )

    def to_cypher_constraints(self) -> list[str]:
        """Generate Cypher statements for creating constraints."""
        statements = []
        for label, props in self.constraints.items():
            for prop in props:
                stmt = (
                    f"CREATE CONSTRAINT IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                )
                statements.append(stmt)
        return statements

    def get_schema_summary(self) -> str:
        """Get human-readable schema summary."""
        lines = ["=== Schema Proposal ==="]
        lines.append(f"\nNode Labels ({len(self.node_labels)}):")
        for label in self.node_labels:
            props = self.properties.get(label, [])
            lines.append(
                f"  - {label}: {', '.join(props) if props else '(no properties)'}"
            )

        lines.append(f"\nRelationship Types ({len(self.relationship_types)}):")
        for rel in self.relationship_types:
            lines.append(f"  - {rel}")

        if self.constraints:
            lines.append("\nConstraints:")
            for label, props in self.constraints.items():
                for prop in props:
                    lines.append(f"  - {label}.{prop} IS UNIQUE")

        lines.append(f"\nConfidence: {self.confidence:.2f}")
        if self.reasoning:
            lines.append(f"\nReasoning: {self.reasoning}")

        return "\n".join(lines)


@dataclass
class RelationGroup:
    """
    Normalized relation group - clusters semantically similar relations.

    Attributes:
        canonical_name: Standardized relation name (e.g., "MANAGES")
        variants: Original relation strings that map to this canonical form
        frequency: Total count of occurrences across all variants
        examples: Sample triples using this relation group
        description: Human-readable description of this relation type
    """

    canonical_name: str
    variants: list[str]
    frequency: int = 0
    examples: list[Triple] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        """Normalize canonical name to SCREAMING_SNAKE_CASE."""
        self.canonical_name = to_screaming_snake(self.canonical_name)

    def add_variant(self, variant: str, example: Triple | None = None) -> None:
        """Add a new variant to this group."""
        if variant not in self.variants:
            self.variants.append(variant)
        self.frequency += 1
        if example and len(self.examples) < 5:  # Keep max 5 examples
            self.examples.append(example)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "canonical_name": self.canonical_name,
            "variants": self.variants,
            "frequency": self.frequency,
            "examples": [ex.to_dict() for ex in self.examples],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelationGroup":
        """Create RelationGroup from dictionary."""
        examples = [Triple.from_dict(ex) for ex in data.get("examples", [])]
        return cls(
            canonical_name=data["canonical_name"],
            variants=data.get("variants", []),
            frequency=data.get("frequency", 0),
            examples=examples,
            description=data.get("description", ""),
        )


@dataclass
class ExtractionResult:
    """
    Result of an extraction operation over multiple documents.

    Attributes:
        triples: All extracted triples
        document_count: Number of documents processed
        total_tokens: Approximate token count processed
        errors: List of extraction errors (document_id -> error message)
    """

    triples: list[Triple] = field(default_factory=list)
    document_count: int = 0
    total_tokens: int = 0
    errors: dict[str, str] = field(default_factory=dict)

    def add_triples(self, new_triples: list[Triple]) -> None:
        """Add extracted triples."""
        self.triples.extend(new_triples)

    def get_relation_frequencies(self) -> dict[str, int]:
        """Get frequency count for each unique relation."""
        freq: dict[str, int] = {}
        for triple in self.triples:
            freq[triple.relation] = freq.get(triple.relation, 0) + 1
        return dict(sorted(freq.items(), key=lambda x: x[1], reverse=True))

    def filter_by_confidence(self, min_confidence: float = 0.5) -> list[Triple]:
        """Get triples above confidence threshold."""
        return [t for t in self.triples if t.confidence >= min_confidence]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "triples": [t.to_dict() for t in self.triples],
            "document_count": self.document_count,
            "total_tokens": self.total_tokens,
            "errors": self.errors,
        }


@dataclass
class NormalizationResult:
    """
    Result of relation normalization.

    Attributes:
        groups: Normalized relation groups
        unmapped_relations: Relations that couldn't be mapped to any group
        mapping: Original relation -> canonical name mapping
    """

    groups: list[RelationGroup] = field(default_factory=list)
    unmapped_relations: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)

    def get_canonical(self, relation: str) -> str | None:
        """Get canonical name for a relation."""
        return self.mapping.get(relation)

    def normalize_triple(self, triple: Triple) -> Triple:
        """Return a new triple with normalized relation."""
        canonical = self.get_canonical(triple.relation)
        if canonical:
            return Triple(
                subject=triple.subject,
                relation=canonical,
                object=triple.object,
                confidence=triple.confidence,
                source_text=triple.source_text,
                metadata={**triple.metadata, "original_relation": triple.relation},
            )
        return triple

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "groups": [g.to_dict() for g in self.groups],
            "unmapped_relations": self.unmapped_relations,
            "mapping": self.mapping,
        }
