"""
Repositories Package

데이터 접근 계층을 제공합니다.
"""

from src.repositories.llm_repository import LLMRepository, ModelTier
from src.repositories.neo4j_entity_repository import Neo4jEntityRepository
from src.repositories.neo4j_graph_crud_repository import Neo4jGraphCrudRepository
from src.repositories.neo4j_ontology_concept_repository import (
    Neo4jOntologyConceptRepository,
)
from src.repositories.neo4j_ontology_proposal_repository import (
    Neo4jOntologyProposalRepository,
)
from src.repositories.neo4j_repository import Neo4jRepository
from src.repositories.neo4j_schema_repository import Neo4jSchemaRepository
from src.repositories.neo4j_types import NodeResult, RelationshipResult
from src.repositories.neo4j_vector_repository import Neo4jVectorRepository

__all__ = [
    # Facade (하위 호환성)
    "Neo4jRepository",
    # Data classes
    "NodeResult",
    "RelationshipResult",
    # Sub-repositories (직접 사용 가능)
    "Neo4jEntityRepository",
    "Neo4jSchemaRepository",
    "Neo4jVectorRepository",
    "Neo4jOntologyProposalRepository",
    "Neo4jOntologyConceptRepository",
    "Neo4jGraphCrudRepository",
    # LLM
    "LLMRepository",
    "ModelTier",
]
