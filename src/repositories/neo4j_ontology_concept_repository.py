"""
Neo4j Ontology Concept Repository - 온톨로지 개념 관리

책임:
- Concept 노드 생성/조회
- IS_A, SAME_AS, REQUIRES, PART_OF 관계 생성
"""

import logging
from typing import Any

from src.domain.exceptions import QueryExecutionError
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.neo4j_validators import validate_concept_name

logger = logging.getLogger(__name__)


class Neo4jOntologyConceptRepository:
    """온톨로지 개념 관리 전담 레포지토리"""

    def __init__(self, client: Neo4jClient):
        self._client = client

    async def concept_exists(self, name: str) -> bool:
        """Concept 노드 존재 여부 확인"""
        validated_name = validate_concept_name(name)

        query = """
        MATCH (c:Concept)
        WHERE toLower(c.name) = toLower($name)
        RETURN count(c) > 0 as exists
        """

        try:
            results = await self._client.execute_query(query, {"name": validated_name})
            return results[0]["exists"] if results else False

        except Exception as e:
            logger.error(f"Failed to check concept existence: {e}")
            return False

    async def create_or_get_concept(
        self,
        name: str,
        concept_type: str = "skill",
        is_canonical: bool = True,
        description: str | None = None,
        source: str = "admin_proposal",
    ) -> dict[str, Any]:
        """Concept 노드 생성 또는 기존 노드 반환 (MERGE 패턴)"""
        validated_name = validate_concept_name(name)

        query = """
        OPTIONAL MATCH (existing:Concept)
        WHERE toLower(existing.name) = toLower($name)
        WITH existing
        CALL {
            WITH existing
            WITH existing WHERE existing IS NOT NULL
            SET existing.updated_at = datetime()
            RETURN existing AS c
          UNION
            WITH existing
            WITH existing WHERE existing IS NULL
            CREATE (new:Concept {
                name: $name,
                type: $type,
                is_canonical: $is_canonical,
                description: $description,
                source: $source,
                created_at: datetime()
            })
            RETURN new AS c
        }
        RETURN
            elementId(c) as id,
            c.name as name,
            c.type as type,
            c.is_canonical as is_canonical,
            c.description as description,
            c.source as source
        """

        try:
            results = await self._client.execute_write(
                query,
                {
                    "name": validated_name,
                    "type": concept_type,
                    "is_canonical": is_canonical,
                    "description": description,
                    "source": source,
                },
            )

            if results:
                logger.info(f"Concept '{validated_name}' created or retrieved")
                return results[0]

            return {"name": validated_name, "type": concept_type}

        except Exception as e:
            logger.error(f"Failed to create/get concept '{validated_name}': {e}")
            raise QueryExecutionError(
                f"Failed to create/get concept: {e}", query=query
            ) from e

    async def create_same_as_relation(
        self,
        alias_name: str,
        canonical_name: str,
        weight: float = 1.0,
        proposal_id: str | None = None,
    ) -> bool:
        """SAME_AS 관계 생성 (동의어 매핑)"""
        validated_alias = validate_concept_name(alias_name, "alias_name")
        validated_canonical = validate_concept_name(canonical_name, "canonical_name")

        query = """
        MATCH (alias:Concept)
        WHERE toLower(alias.name) = toLower($alias_name)
        MATCH (canonical:Concept)
        WHERE toLower(canonical.name) = toLower($canonical_name)
        MERGE (alias)-[r:SAME_AS]->(canonical)
        ON CREATE SET
            r.weight = $weight,
            r.proposal_id = $proposal_id,
            r.created_at = datetime()
        ON MATCH SET
            r.updated_at = datetime()
        RETURN type(r) as rel_type
        """

        try:
            results = await self._client.execute_write(
                query,
                {
                    "alias_name": validated_alias,
                    "canonical_name": validated_canonical,
                    "weight": weight,
                    "proposal_id": proposal_id,
                },
            )

            if results:
                logger.info(
                    f"SAME_AS relation created: '{validated_alias}' -> '{validated_canonical}'"
                )
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to create SAME_AS relation: {e}")
            return False

    async def create_is_a_relation(
        self,
        child_name: str,
        parent_name: str,
        depth: int = 1,
        proposal_id: str | None = None,
    ) -> bool:
        """IS_A 관계 생성 (계층 관계)"""
        validated_child = validate_concept_name(child_name, "child_name")
        validated_parent = validate_concept_name(parent_name, "parent_name")

        query = """
        MATCH (child:Concept)
        WHERE toLower(child.name) = toLower($child_name)
        MATCH (parent:Concept)
        WHERE toLower(parent.name) = toLower($parent_name)
        MERGE (child)-[r:IS_A]->(parent)
        ON CREATE SET
            r.depth = $depth,
            r.proposal_id = $proposal_id,
            r.created_at = datetime()
        ON MATCH SET
            r.updated_at = datetime()
        RETURN type(r) as rel_type
        """

        try:
            results = await self._client.execute_write(
                query,
                {
                    "child_name": validated_child,
                    "parent_name": validated_parent,
                    "depth": depth,
                    "proposal_id": proposal_id,
                },
            )

            if results:
                logger.info(
                    f"IS_A relation created: '{validated_child}' -> '{validated_parent}'"
                )
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to create IS_A relation: {e}")
            return False

    async def create_requires_relation(
        self,
        entity_name: str,
        skill_name: str,
        proposal_id: str | None = None,
    ) -> bool:
        """REQUIRES 관계 생성 (엔티티-스킬 요구 관계)"""
        validated_entity = validate_concept_name(entity_name, "entity_name")
        validated_skill = validate_concept_name(skill_name, "skill_name")

        query = """
        MATCH (entity:Concept)
        WHERE toLower(entity.name) = toLower($entity_name)
        MATCH (skill:Concept)
        WHERE toLower(skill.name) = toLower($skill_name)
        MERGE (entity)-[r:REQUIRES]->(skill)
        ON CREATE SET
            r.proposal_id = $proposal_id,
            r.created_at = datetime()
        ON MATCH SET
            r.updated_at = datetime()
        RETURN type(r) as rel_type
        """

        try:
            results = await self._client.execute_write(
                query,
                {
                    "entity_name": validated_entity,
                    "skill_name": validated_skill,
                    "proposal_id": proposal_id,
                },
            )

            if results:
                logger.info(
                    f"REQUIRES relation created: '{validated_entity}' -> '{validated_skill}'"
                )
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to create REQUIRES relation: {e}")
            return False

    async def create_part_of_relation(
        self,
        part_name: str,
        whole_name: str,
        proposal_id: str | None = None,
    ) -> bool:
        """PART_OF 관계 생성 (부분-전체 관계)"""
        validated_part = validate_concept_name(part_name, "part_name")
        validated_whole = validate_concept_name(whole_name, "whole_name")

        query = """
        MATCH (part:Concept)
        WHERE toLower(part.name) = toLower($part_name)
        MATCH (whole:Concept)
        WHERE toLower(whole.name) = toLower($whole_name)
        MERGE (part)-[r:PART_OF]->(whole)
        ON CREATE SET
            r.proposal_id = $proposal_id,
            r.created_at = datetime()
        ON MATCH SET
            r.updated_at = datetime()
        RETURN type(r) as rel_type
        """

        try:
            results = await self._client.execute_write(
                query,
                {
                    "part_name": validated_part,
                    "whole_name": validated_whole,
                    "proposal_id": proposal_id,
                },
            )

            if results:
                logger.info(
                    f"PART_OF relation created: '{validated_part}' -> '{validated_whole}'"
                )
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to create PART_OF relation: {e}")
            return False
