"""
공통 테스트 Fixture

파이프라인 테스트에서 사용하는 공통 Mock 객체들을 정의합니다.
"""

from datetime import UTC, datetime

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.config import Settings
from src.domain.adaptive.models import OntologyProposal, ProposalStatus, ProposalType
from src.graph.pipeline import GraphRAGPipeline
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.ontology_service import OntologyService


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
    # 채팅 자동 승인 설정
    settings.chat_auto_approve_enabled = True
    settings.chat_auto_approve_threshold = 0.9
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
    from src.repositories.neo4j_repository import NodeResult

    neo4j = MagicMock(spec=Neo4jRepository)

    # find_entities_by_name: 엔티티가 발견되면 resolved로 처리됨
    # 빈 리스트를 반환하면 unresolved로 분류되어 clarification_handler로 라우팅됨
    async def mock_find_entities(name: str, labels=None, limit=10):
        # 테스트에서 사용하는 일반적인 엔티티 이름에 대해 매칭 결과 반환
        return [
            NodeResult(
                id=f"node_{name}",
                labels=labels or ["Person"],
                properties={"name": name},
            )
        ]

    neo4j.find_entities_by_name = AsyncMock(side_effect=mock_find_entities)
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


@pytest.fixture
def mock_ontology_service(mock_neo4j):
    """Mock OntologyService for ontology_update tests"""
    service = MagicMock(spec=OntologyService)

    async def mock_approve(
        proposal_id: str,
        expected_version: int,
        reviewer: str | None = None,
        canonical: str | None = None,
        parent: str | None = None,
        note: str | None = None,
    ) -> OntologyProposal:
        return OntologyProposal(
            id=proposal_id,
            proposal_type=ProposalType.NEW_CONCEPT,
            term="LangGraph",
            category="skills",
            suggested_action="test",
            status=ProposalStatus.APPROVED,
            applied_at=datetime.now(UTC),
        )

    service.approve_proposal = AsyncMock(side_effect=mock_approve)
    return service


@pytest.fixture
def pipeline_with_ontology(
    mock_settings, mock_neo4j, mock_llm, graph_schema, mock_ontology_service
):
    """테스트용 파이프라인 (OntologyService 포함)"""
    # Neo4j에 proposal 저장 mock 추가
    mock_neo4j.save_ontology_proposal = AsyncMock(side_effect=lambda p: p)

    return GraphRAGPipeline(
        settings=mock_settings,
        neo4j_repository=mock_neo4j,
        llm_repository=mock_llm,
        graph_schema=graph_schema,
        ontology_service=mock_ontology_service,
    )
