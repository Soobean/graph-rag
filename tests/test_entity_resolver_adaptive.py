from unittest.mock import AsyncMock, MagicMock

import pytest

from src.graph.nodes.entity_resolver import EntityResolverNode


@pytest.fixture
def mock_neo4j_repository():
    return AsyncMock()


@pytest.fixture
def entity_resolver_node(mock_neo4j_repository):
    return EntityResolverNode(mock_neo4j_repository)


@pytest.mark.asyncio
async def test_collect_unresolved_when_no_match(
    entity_resolver_node, mock_neo4j_repository
):
    # Given
    state = {
        "entities": {"Skill": ["NonExistentSkill"]},
        "question": "Find someone with NonExistentSkill",
    }

    # Mock find_entities_by_name to return empty list (no match)
    mock_neo4j_repository.find_entities_by_name.return_value = []

    # When
    result = await entity_resolver_node._process(state)

    # Then
    assert len(result["resolved_entities"]) == 0
    assert len(result["unresolved_entities"]) == 1

    unresolved = result["unresolved_entities"][0]
    assert unresolved["term"] == "NonExistentSkill"
    assert unresolved["category"] == "Skill"
    assert unresolved["question"] == "Find someone with NonExistentSkill"
    assert "timestamp" in unresolved


@pytest.mark.asyncio
async def test_mixed_resolved_and_unresolved(
    entity_resolver_node, mock_neo4j_repository
):
    # Given
    state = {
        "entities": {"Skill": ["Python", "UnknownSkill"]},
        "question": "Python and UnknownSkill",
    }

    # Mock behavior: Python exists, UnknownSkill does not
    async def side_effect(name, labels=None, limit=None):
        if name == "Python":
            mock_node = MagicMock()
            mock_node.id = 1
            mock_node.labels = ["Skill"]
            mock_node.properties = {"name": "Python"}
            return [mock_node]
        return []

    mock_neo4j_repository.find_entities_by_name.side_effect = side_effect

    # When
    result = await entity_resolver_node._process(state)

    # Then
    assert len(result["resolved_entities"]) == 1
    assert result["resolved_entities"][0]["name"] == "Python"

    assert len(result["unresolved_entities"]) == 1
    assert result["unresolved_entities"][0]["term"] == "UnknownSkill"


@pytest.mark.asyncio
async def test_empty_entities_returns_empty_unresolved(entity_resolver_node):
    # Given
    state = {"entities": {}}

    # When
    result = await entity_resolver_node._process(state)

    # Then
    assert result["resolved_entities"] == []
    assert result["unresolved_entities"] == []


@pytest.mark.asyncio
async def test_error_handling_adds_to_unresolved(
    entity_resolver_node, mock_neo4j_repository
):
    # Given
    state = {"entities": {"Skill": ["ErrorSkill"]}, "question": "Error case"}

    # Mock exception
    mock_neo4j_repository.find_entities_by_name.side_effect = Exception("DB Error")

    # When
    result = await entity_resolver_node._process(state)

    # Then
    assert len(result["resolved_entities"]) == 0
    assert len(result["unresolved_entities"]) == 1
    assert result["unresolved_entities"][0]["term"] == "ErrorSkill"
