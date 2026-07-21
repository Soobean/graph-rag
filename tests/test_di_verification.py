from unittest.mock import MagicMock

from fastapi import Request

from src.application.llm import LLMTaskService
from src.dependencies import (
    get_graph_pipeline,
    get_llm_gateway,
    get_llm_task_service,
    get_neo4j_repository,
)
from src.graph.pipeline import GraphRAGPipeline
from src.infrastructure.llm import AzureOpenAIGateway
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.neo4j_repository import Neo4jRepository


def test_di_providers():
    # Mock Request and app.state
    mock_request = MagicMock(spec=Request)
    mock_app = MagicMock()
    mock_state = MagicMock()

    mock_request.app = mock_app
    mock_app.state = mock_state

    # Mock initialized objects in state
    # Note: dependencies now return pre-initialized instances from app.state
    mock_neo4j_client = MagicMock(spec=Neo4jClient)
    mock_neo4j_repo = MagicMock(spec=Neo4jRepository)
    mock_neo4j_repo._client = mock_neo4j_client  # Set internal client reference
    mock_gateway = MagicMock(spec=AzureOpenAIGateway)
    mock_tasks = MagicMock(spec=LLMTaskService)
    mock_pipeline = MagicMock(spec=GraphRAGPipeline)

    mock_state.neo4j_client = mock_neo4j_client
    mock_state.neo4j_repo = mock_neo4j_repo  # Pre-initialized repository
    mock_state.llm_gateway = mock_gateway
    mock_state.llm_tasks = mock_tasks
    mock_state.pipeline = mock_pipeline

    # Test get_neo4j_repository
    # Note: get_neo4j_repository returns the pre-initialized instance from state
    repo = get_neo4j_repository(mock_request)
    assert repo == mock_neo4j_repo
    assert repo._client == mock_neo4j_client

    # Test get_llm_gateway / get_llm_task_service
    gateway = get_llm_gateway(mock_request)
    assert gateway == mock_gateway
    tasks = get_llm_task_service(mock_request)
    assert tasks == mock_tasks

    # Test get_graph_pipeline
    pipeline = get_graph_pipeline(mock_request)
    assert pipeline == mock_pipeline


if __name__ == "__main__":
    # Allow running directly
    test_di_providers()
    print("DI Verification Passed!")
