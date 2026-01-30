"""
공통 테스트 Fixture

파이프라인 테스트에서 사용하는 공통 Mock 객체들을 정의합니다.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.config import Settings
from src.graph.pipeline import GraphRAGPipeline
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    settings = MagicMock(spec=Settings)
    settings.vector_search_enabled = False
    settings.ontology_mode = "file"  # Multi-hop 테스트용
    settings.adaptive_ontology = MagicMock()
    settings.adaptive_ontology.enabled = False
    # Latency Optimization 설정
    settings.cypher_light_model_enabled = True
    return settings


@pytest.fixture
def mock_llm():
    """Mock LLM Repository"""
    llm = MagicMock(spec=LLMRepository)
    # 통합 Intent + Entity 추출 (Latency Optimization)
    llm.classify_intent_and_extract_entities = AsyncMock(
        return_value={
            "intent": "personnel_search",
            "confidence": 0.9,
            "entities": [],
        }
    )
    llm.generate_cypher = AsyncMock()
    llm.generate_response = AsyncMock()
    llm.decompose_query = AsyncMock(
        return_value={
            "is_multi_hop": False,
            "hop_count": 1,
            "hops": [],
            "explanation": "Single-hop query",
        }
    )
    return llm


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j Repository"""
    neo4j = MagicMock(spec=Neo4jRepository)
    neo4j.find_entities_by_name = AsyncMock(return_value=[])
    neo4j.execute_cypher = AsyncMock(return_value=[])
    return neo4j


@pytest.fixture
def graph_schema():
    """테스트용 스키마"""
    return {
        "node_labels": ["Person"],
        "relationship_types": ["WORKS_AT"],
    }


@pytest.fixture
def pipeline(mock_settings, mock_neo4j, mock_llm, graph_schema):
    """테스트용 파이프라인 (스키마 주입)"""
    return GraphRAGPipeline(
        settings=mock_settings,
        neo4j_repository=mock_neo4j,
        llm_repository=mock_llm,
        graph_schema=graph_schema,
    )
