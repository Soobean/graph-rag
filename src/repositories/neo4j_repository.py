"""
Neo4j Repository — Facade

기존 Neo4jRepository의 모든 메서드를 유지하면서
내부적으로 6개의 서브 레포지토리에 위임합니다.

하위 호환성 100%:
- `neo4j_repo.find_entities_by_name()` → `self._entity.find_entities_by_name()`
- 기존 import, 테스트, 서비스 코드 수정 0건
"""

import logging
from typing import Any

from src.domain.adaptive.models import OntologyProposal
from src.domain.exceptions import QueryExecutionError
from src.domain.types import SubGraphResult
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.neo4j_entity_repository import Neo4jEntityRepository
from src.repositories.neo4j_graph_crud_repository import Neo4jGraphCrudRepository
from src.repositories.neo4j_ontology_concept_repository import (
    Neo4jOntologyConceptRepository,
)
from src.repositories.neo4j_ontology_proposal_repository import (
    Neo4jOntologyProposalRepository,
)
from src.repositories.neo4j_schema_repository import Neo4jSchemaRepository
from src.repositories.neo4j_types import NodeResult, RelationshipResult
from src.repositories.neo4j_vector_repository import Neo4jVectorRepository

logger = logging.getLogger(__name__)

# Re-export dataclasses (하위 호환성)
__all__ = [
    "Neo4jRepository",
    "NodeResult",
    "RelationshipResult",
]


class Neo4jRepository:
    """
    Neo4j 그래프 데이터 Repository — Facade

    내부적으로 6개 서브 레포지토리에 위임합니다.
    기존 API를 100% 유지하므로 호출자 코드 수정이 불필요합니다.

    사용 예시:
        repo = Neo4jRepository(neo4j_client)
        entities = await repo.find_entities_by_name("홍길동")
        neighbors = await repo.get_neighbors(entity_id=123, depth=2)
    """

    def __init__(self, client: Neo4jClient):
        self._client = client

        # 서브 레포지토리 초기화
        self._entity = Neo4jEntityRepository(client)
        self._schema = Neo4jSchemaRepository(client)
        self._vector = Neo4jVectorRepository(client)
        self._ontology_proposal = Neo4jOntologyProposalRepository(client)
        self._ontology_concept = Neo4jOntologyConceptRepository(client)
        self._graph_crud = Neo4jGraphCrudRepository(client)

    # ── Entity Repository 위임 ────────────────────────────────

    async def find_entities_by_name(
        self, name: str, labels: list[str] | None = None, limit: int = 10
    ) -> list[NodeResult]:
        return await self._entity.find_entities_by_name(name, labels, limit)

    async def find_entity_by_id(self, entity_id: str) -> NodeResult:
        return await self._entity.find_entity_by_id(entity_id)

    async def get_neighbors(
        self,
        entity_id: str,
        relationship_types: list[str] | None = None,
        direction: str = "both",
        depth: int = 1,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self._entity.get_neighbors(
            entity_id, relationship_types, direction, depth, limit
        )

    async def get_relationships(
        self,
        entity_id: str,
        relationship_types: list[str] | None = None,
        direction: str = "both",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self._entity.get_relationships(
            entity_id, relationship_types, direction, limit
        )

    async def search_fulltext(
        self, search_term: str, index_name: str = "entityIndex", limit: int = 10
    ) -> list[NodeResult]:
        return await self._entity.search_fulltext(search_term, index_name, limit)

    async def get_subgraph(
        self, entity_ids: list[str], max_depth: int = 1, limit: int = 100
    ) -> SubGraphResult:
        return await self._entity.get_subgraph(entity_ids, max_depth, limit)

    async def find_similar_nodes(
        self,
        embedding: list[float],
        index_name: str,
        exclude_ids: list[str] | None = None,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> list[tuple[NodeResult, float]]:
        return await self._entity.find_similar_nodes(
            embedding, index_name, exclude_ids, limit, threshold
        )

    async def search_nodes(
        self, label: str | None = None, search: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return await self._entity.search_nodes(label, search, limit)

    async def find_concept_bridge(self, skill_name: str) -> dict[str, Any] | None:
        return await self._entity.find_concept_bridge(skill_name)

    async def find_relationship_by_id(self, rel_id: str) -> dict[str, Any]:
        return await self._entity.find_relationship_by_id(rel_id)

    async def get_node_relationships_detailed(
        self, node_id: str
    ) -> list[dict[str, Any]]:
        return await self._entity.get_node_relationships_detailed(node_id)

    async def check_cached_queries_exist(self) -> int:
        return await self._entity.check_cached_queries_exist()

    async def check_similar_relationships_exist(self) -> int:
        return await self._entity.check_similar_relationships_exist()

    # ── Direct Cypher (widely used) ───────────────────────────

    async def execute_cypher(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Cypher 쿼리 직접 실행"""
        try:
            results = await self._client.execute_query(query, parameters)
            logger.info(f"Cypher query executed: {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Cypher query failed: {e}\nQuery: {query}")
            raise QueryExecutionError(str(e), query=query) from e

    # ── Schema Repository 위임 ────────────────────────────────

    async def get_schema(self, force_refresh: bool = False) -> dict[str, Any]:
        return await self._schema.get_schema(force_refresh)

    def invalidate_schema_cache(self) -> None:
        self._schema.invalidate_schema_cache()

    async def get_node_labels(self) -> list[str]:
        return await self._schema.get_node_labels()

    async def get_relationship_types(self) -> list[str]:
        return await self._schema.get_relationship_types()

    async def get_node_properties(self, label: str) -> list[str]:
        return await self._schema.get_node_properties(label)

    # ── Vector Repository 위임 ────────────────────────────────

    async def vector_search_nodes(
        self,
        embedding: list[float],
        index_name: str,
        labels: list[str] | None = None,
        limit: int = 10,
        threshold: float | None = None,
    ) -> list[tuple[NodeResult, float]]:
        return await self._vector.vector_search_nodes(
            embedding, index_name, labels, limit, threshold
        )

    async def ensure_vector_index(
        self,
        index_name: str,
        label: str,
        property_name: str,
        dimensions: int = 1536,
    ) -> bool:
        return await self._vector.ensure_vector_index(
            index_name, label, property_name, dimensions
        )

    async def upsert_node_embedding(
        self, node_id: str, property_name: str, embedding: list[float]
    ) -> bool:
        return await self._vector.upsert_node_embedding(
            node_id, property_name, embedding
        )

    async def batch_upsert_node_embeddings(
        self, updates: list[dict[str, Any]], property_name: str
    ) -> int:
        return await self._vector.batch_upsert_node_embeddings(updates, property_name)

    # ── Ontology Proposal Repository 위임 ─────────────────────

    async def save_ontology_proposal(
        self, proposal: OntologyProposal
    ) -> OntologyProposal:
        return await self._ontology_proposal.save_ontology_proposal(proposal)

    async def find_ontology_proposal(
        self, term: str, category: str
    ) -> OntologyProposal | None:
        return await self._ontology_proposal.find_ontology_proposal(term, category)

    async def update_proposal_frequency(self, proposal_id: str, question: str) -> bool:
        return await self._ontology_proposal.update_proposal_frequency(
            proposal_id, question
        )

    async def update_proposal_status(
        self, proposal: OntologyProposal, expected_version: int
    ) -> bool:
        return await self._ontology_proposal.update_proposal_status(
            proposal, expected_version
        )

    async def count_today_auto_approved(self) -> int:
        return await self._ontology_proposal.count_today_auto_approved()

    async def try_auto_approve_with_limit(
        self, proposal_id: str, expected_version: int, daily_limit: int
    ) -> bool:
        return await self._ontology_proposal.try_auto_approve_with_limit(
            proposal_id, expected_version, daily_limit
        )

    async def get_pending_proposals(
        self, category: str | None = None, limit: int = 50
    ) -> list[OntologyProposal]:
        return await self._ontology_proposal.get_pending_proposals(category, limit)

    async def get_proposal_by_id(self, proposal_id: str) -> OntologyProposal | None:
        return await self._ontology_proposal.get_proposal_by_id(proposal_id)

    async def get_proposals_paginated(
        self,
        status: str | None = None,
        proposal_type: str | None = None,
        source: str | None = None,
        category: str | None = None,
        term_search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[OntologyProposal], int]:
        return await self._ontology_proposal.get_proposals_paginated(
            status,
            proposal_type,
            source,
            category,
            term_search,
            sort_by,
            sort_order,
            offset,
            limit,
        )

    async def get_ontology_stats(self) -> dict[str, Any]:
        return await self._ontology_proposal.get_ontology_stats()

    async def batch_update_proposal_status(
        self,
        proposal_ids: list[str],
        new_status: str,
        reviewed_by: str | None = None,
        rejection_reason: str | None = None,
    ) -> tuple[int, list[str]]:
        return await self._ontology_proposal.batch_update_proposal_status(
            proposal_ids, new_status, reviewed_by, rejection_reason
        )

    async def update_proposal_with_version(
        self,
        proposal_id: str,
        expected_version: int,
        updates: dict[str, Any],
    ) -> OntologyProposal | None:
        return await self._ontology_proposal.update_proposal_with_version(
            proposal_id, expected_version, updates
        )

    async def create_proposal(self, proposal: OntologyProposal) -> OntologyProposal:
        return await self._ontology_proposal.create_proposal(proposal)

    async def get_proposal_current_version(self, proposal_id: str) -> int | None:
        return await self._ontology_proposal.get_proposal_current_version(proposal_id)

    async def update_proposal_applied_at(self, proposal_id: str) -> bool:
        return await self._ontology_proposal.update_proposal_applied_at(proposal_id)

    # ── Ontology Concept Repository 위임 ──────────────────────

    async def concept_exists(self, name: str) -> bool:
        return await self._ontology_concept.concept_exists(name)

    async def create_or_get_concept(
        self,
        name: str,
        concept_type: str = "skill",
        is_canonical: bool = True,
        description: str | None = None,
        source: str = "admin_proposal",
    ) -> dict[str, Any]:
        return await self._ontology_concept.create_or_get_concept(
            name, concept_type, is_canonical, description, source
        )

    async def create_same_as_relation(
        self,
        alias_name: str,
        canonical_name: str,
        weight: float = 1.0,
        proposal_id: str | None = None,
    ) -> bool:
        return await self._ontology_concept.create_same_as_relation(
            alias_name, canonical_name, weight, proposal_id
        )

    async def create_is_a_relation(
        self,
        child_name: str,
        parent_name: str,
        depth: int = 1,
        proposal_id: str | None = None,
    ) -> bool:
        return await self._ontology_concept.create_is_a_relation(
            child_name, parent_name, depth, proposal_id
        )

    async def create_requires_relation(
        self,
        entity_name: str,
        skill_name: str,
        proposal_id: str | None = None,
    ) -> bool:
        return await self._ontology_concept.create_requires_relation(
            entity_name, skill_name, proposal_id
        )

    async def create_part_of_relation(
        self,
        part_name: str,
        whole_name: str,
        proposal_id: str | None = None,
    ) -> bool:
        return await self._ontology_concept.create_part_of_relation(
            part_name, whole_name, proposal_id
        )

    # ── Graph CRUD Repository 위임 ────────────────────────────

    async def create_node_generic(
        self, label: str, properties: dict[str, Any]
    ) -> dict[str, Any] | None:
        return await self._graph_crud.create_node_generic(label, properties)

    async def check_duplicate_node(self, label: str, name: str) -> bool:
        return await self._graph_crud.check_duplicate_node(label, name)

    async def update_node_properties(
        self,
        node_id: str,
        properties: dict[str, Any],
        remove_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._graph_crud.update_node_properties(
            node_id, properties, remove_keys
        )

    async def delete_node_generic(self, node_id: str, force: bool = False) -> bool:
        return await self._graph_crud.delete_node_generic(node_id, force)

    async def get_node_relationship_count(self, node_id: str) -> int:
        return await self._graph_crud.get_node_relationship_count(node_id)

    async def delete_node_atomic(
        self, node_id: str, force: bool = False
    ) -> dict[str, Any]:
        return await self._graph_crud.delete_node_atomic(node_id, force)

    async def create_relationship_generic(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._graph_crud.create_relationship_generic(
            source_id, target_id, rel_type, properties
        )

    async def delete_relationship_generic(self, rel_id: str) -> bool:
        return await self._graph_crud.delete_relationship_generic(rel_id)
