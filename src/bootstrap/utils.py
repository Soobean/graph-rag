"""
Bootstrap utilities module.

Contains shared utility functions for the bootstrap pipeline.
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.bootstrap.models import SchemaProposal, Triple

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Maximum lengths for various inputs
MAX_FEEDBACK_LENGTH = 2000
MAX_DOCUMENT_LENGTH = 4000
MAX_RELATION_TYPE_LENGTH = 100
SOURCE_TEXT_PREVIEW_LENGTH = 500
BATCH_DELAY_SECONDS = 0.5

# Dangerous patterns for prompt injection detection
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above|prior)\s+(instructions?|prompts?)",
    r"disregard\s+(previous|all|above|prior)",
    r"forget\s+(everything|all|previous)",
    r"system\s*[:：]\s*",
    r"assistant\s*[:：]\s*",
    r"<\|.*?\|>",  # Special tokens
    r"\[INST\]|\[/INST\]",  # Instruction markers
    r"```\s*(system|assistant)",  # Code block injection
]


# =============================================================================
# String Conversion Functions
# =============================================================================


def to_pascal_case(s: str) -> str:
    """
    Convert string to PascalCase.

    Examples:
        - "person" -> "Person"
        - "my_project" -> "MyProject"
        - "skill category" -> "SkillCategory"
    """
    if not s:
        return s
    # Handle already PascalCase or camelCase
    if "_" not in s and " " not in s:
        return s[0].upper() + s[1:]
    # Handle snake_case or space-separated
    return "".join(word.capitalize() for word in s.replace("_", " ").split())


def to_screaming_snake(s: str) -> str:
    """
    Convert string to SCREAMING_SNAKE_CASE.

    Examples:
        - "worksOn" -> "WORKS_ON"
        - "hasSkill" -> "HAS_SKILL"
        - "reports-to" -> "REPORTS_TO"
    """
    if not s:
        return s
    # Handle already all uppercase (MANAGES or WORKS_ON)
    if s.isupper():
        return s.replace(" ", "_").replace("-", "_")
    # Handle camelCase or PascalCase
    result = []
    for i, char in enumerate(s):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.upper())
    return "".join(result).replace(" ", "_").replace("-", "_")


# =============================================================================
# Security Functions
# =============================================================================


def sanitize_user_input(
    text: str,
    max_length: int = MAX_FEEDBACK_LENGTH,
    field_name: str = "input",
) -> str:
    """
    Sanitize user input to prevent prompt injection attacks.

    Args:
        text: The user input text to sanitize
        max_length: Maximum allowed length
        field_name: Name of the field for error messages

    Returns:
        Sanitized text

    Raises:
        ValueError: If input exceeds max length or contains dangerous patterns
    """
    if not text:
        return ""

    # Length check
    if len(text) > max_length:
        raise ValueError(
            f"{field_name} is too long: {len(text)} chars (max {max_length})"
        )

    # Check for dangerous patterns
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(f"Potential prompt injection detected in {field_name}")
            raise ValueError(
                f"{field_name} contains disallowed pattern. "
                "Please rephrase without special instructions."
            )

    return text.strip()


def normalize_relation_type(rel_type: str) -> str:
    """
    Normalize relation type to a safe Cypher identifier.

    Converts to SCREAMING_SNAKE_CASE and validates for Neo4j compatibility.

    Args:
        rel_type: The relation type string to normalize

    Returns:
        Normalized relation type

    Raises:
        ValueError: If relation type is invalid or too long
    """
    if not rel_type:
        raise ValueError("Relation type cannot be empty")

    # Length limit
    if len(rel_type) > MAX_RELATION_TYPE_LENGTH:
        raise ValueError(f"Relation type too long: {len(rel_type)} chars")

    # Convert to uppercase and replace spaces/hyphens with underscores
    safe = rel_type.upper().replace(" ", "_").replace("-", "_")

    # Keep only alphanumeric and underscore
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in safe)

    # Remove consecutive underscores
    while "__" in safe:
        safe = safe.replace("__", "_")

    # Remove leading/trailing underscores
    safe = safe.strip("_")

    # Ensure it doesn't start with a number
    if safe and safe[0].isdigit():
        safe = "REL_" + safe

    # Validate result
    if not safe:
        raise ValueError(f"Invalid relation type after normalization: {rel_type}")

    return safe


# =============================================================================
# File I/O Functions
# =============================================================================


def load_schema_from_file(schema_path: str | None) -> "SchemaProposal | None":
    """
    Load schema from a YAML file.

    Args:
        schema_path: Path to the schema YAML file, or None

    Returns:
        SchemaProposal if loaded successfully, None otherwise
    """
    if not schema_path:
        return None

    # Import here to avoid circular imports
    from src.bootstrap.models import SchemaProposal

    try:
        path = Path(schema_path)
        if not path.exists():
            logger.warning(f"Schema file not found: {schema_path}")
            return None

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            logger.warning(f"Empty schema file: {schema_path}")
            return None

        return SchemaProposal.from_dict(data)

    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse schema YAML: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to load schema from {schema_path}: {e}")
        return None


def load_triples_from_file(input_path: str) -> "list[Triple]":
    """
    Load triples from a JSON file.

    Args:
        input_path: Path to the triples JSON file

    Returns:
        List of Triple objects
    """
    import json

    # Import here to avoid circular imports
    from src.bootstrap.models import Triple

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    triples = []
    for item in data.get("triples", []):
        triples.append(Triple.from_dict(item))

    return triples


def save_triples_to_file(triples: "list[Triple]", output_path: str) -> None:
    """
    Save triples to a JSON file.

    Args:
        triples: List of Triple objects to save
        output_path: Path to the output JSON file
    """
    import json

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {"triples": [t.to_dict() for t in triples]},
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info(f"Triples saved to: {output_path}")
