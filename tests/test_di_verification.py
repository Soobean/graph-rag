import pytest
from unittest.mock import MagicMock
from fastapi import Request
from src.dependencies import (
    get_neo4j_repository,
    get_llm_repository,
    get_graph_pipeline,
)
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.neo4j_repository import Neo4jRepository
from src.repositories.llm_repository import LLMRepository
from src.graph.pipeline import GraphRAGPipeline


def test_di_providers():
    # Mock Request and app.state
    mock_request = MagicMock(spec=Request)
    mock_app = MagicMock()
    mock_state = MagicMock()

    mock_request.app = mock_app
    mock_app.state = mock_state

    # Mock initialized objects in state
    mock_neo4j_client = MagicMock(spec=Neo4jClient)
    mock_llm_repo = MagicMock(spec=LLMRepository)
    mock_pipeline = MagicMock(spec=GraphRAGPipeline)

    mock_state.neo4j_client = mock_neo4j_client
    mock_state.llm_repo = mock_llm_repo
    mock_state.pipeline = mock_pipeline

    # Test get_neo4j_repository
    # Note: get_neo4j_repository creates a NEW instance using the client from state
    repo = get_neo4j_repository(mock_request)
    assert isinstance(repo, Neo4jRepository)
    assert repo._client == mock_neo4j_client

    # Test get_llm_repository
    llm = get_llm_repository(mock_request)
    assert llm == mock_llm_repo

    # Test get_graph_pipeline
    pipeline = get_graph_pipeline(mock_request)
    assert pipeline == mock_pipeline


if __name__ == "__main__":
    # Allow running directly
    test_di_providers()
    print("DI Verification Passed!")
