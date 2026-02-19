"""
Neo4j Graph CRUD Repository - 노드/엣지 CRUD

책임:
- 범용 노드 생성/수정/삭제
- 범용 관계 생성/삭제
- 중복 확인
- 관계 수 조회
"""

import logging
from typing import Any

from src.domain.exceptions import (
    EntityNotFoundError,
    QueryExecutionError,
)
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.neo4j_validators import validate_identifier

logger = logging.getLogger(__name__)


class Neo4jGraphCrudRepository:
    """Graph CRUD 전담 레포지토리"""

    def __init__(self, client: Neo4jClient):
        self._client = client

    async def create_node_generic(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        """범용 노드 생성 (atomic — 이름 중복 시 생성하지 않음)"""
        validated_label = validate_identifier(label, "label")

        query = f"""
        OPTIONAL MATCH (existing:{validated_label})
        WHERE toLower(existing.name) = toLower($name)
        WITH existing
        WHERE existing IS NULL
        CREATE (n:{validated_label} $props)
        SET n.created_at = datetime()
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        """

        try:
            name = properties.get("name", "")
            results = await self._client.execute_write(
                query, {"props": properties, "name": name}
            )
            if not results:
                return None
            return results[0]
        except Exception as e:
            logger.error(f"Failed to create node with label '{label}': {e}")
            raise QueryExecutionError(
                f"Failed to create node: {e}", query=query
            ) from e

    async def check_duplicate_node(
        self,
        label: str,
        name: str,
    ) -> bool:
        """동일 레이블 내 이름 중복 확인 (대소문자 무시)"""
        validated_label = validate_identifier(label, "label")

        query = f"""
        MATCH (n:{validated_label})
        WHERE toLower(n.name) = toLower($name)
        RETURN count(n) > 0 as exists
        """

        results = await self._client.execute_query(query, {"name": name})
        return results[0]["exists"] if results else False

    async def update_node_properties(
        self,
        node_id: str,
        properties: dict[str, Any],
        remove_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        """노드 속성 수정"""
        remove_clause = ""
        if remove_keys:
            validated_keys = [
                validate_identifier(key, "property_name")
                for key in remove_keys
            ]
            remove_parts = [f"n.{key}" for key in validated_keys]
            remove_clause = "REMOVE " + ", ".join(remove_parts)

        query = f"""
        MATCH (n)
        WHERE elementId(n) = $node_id
        SET n += $props, n.updated_at = datetime()
        {remove_clause}
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        """

        try:
            results = await self._client.execute_write(
                query, {"node_id": node_id, "props": properties}
            )
            if not results:
                raise EntityNotFoundError("Node", node_id)
            return results[0]
        except EntityNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to update node {node_id}: {e}")
            raise QueryExecutionError(
                f"Failed to update node: {e}", query=query
            ) from e

    async def delete_node_generic(
        self,
        node_id: str,
        force: bool = False,
    ) -> bool:
        """노드 삭제"""
        delete_keyword = "DETACH DELETE" if force else "DELETE"
        query = f"""
        MATCH (n)
        WHERE elementId(n) = $node_id
        {delete_keyword} n
        RETURN true as deleted
        """

        try:
            results = await self._client.execute_write(
                query, {"node_id": node_id}
            )
            return len(results) > 0
        except Exception as e:
            logger.error(f"Failed to delete node {node_id}: {e}")
            raise QueryExecutionError(
                f"Failed to delete node: {e}", query=query
            ) from e

    async def get_node_relationship_count(self, node_id: str) -> int:
        """노드에 연결된 관계 수 조회"""
        query = """
        MATCH (n)
        WHERE elementId(n) = $node_id
        OPTIONAL MATCH (n)-[r]-()
        RETURN count(r) as count
        """

        results = await self._client.execute_query(query, {"node_id": node_id})
        return results[0]["count"] if results else 0

    async def delete_node_atomic(
        self,
        node_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """노드 삭제 (atomic — 관계 확인과 삭제를 단일 트랜잭션으로 수행)"""
        if force:
            query = """
            MATCH (n)
            WHERE elementId(n) = $node_id
            DETACH DELETE n
            RETURN true as deleted, 0 as rel_count
            """
        else:
            query = """
            MATCH (n)
            WHERE elementId(n) = $node_id
            OPTIONAL MATCH (n)-[r]-()
            WITH n, count(DISTINCT r) as rel_count
            CALL {
                WITH n, rel_count
                WITH n WHERE rel_count = 0
                DELETE n
                RETURN true as was_deleted
            }
            RETURN rel_count, coalesce(was_deleted, false) as deleted
            """

        try:
            results = await self._client.execute_write(
                query, {"node_id": node_id}
            )
            if not results:
                return {"deleted": False, "rel_count": 0, "not_found": True}
            return {
                "deleted": results[0]["deleted"],
                "rel_count": results[0]["rel_count"],
                "not_found": False,
            }
        except Exception as e:
            logger.error(f"Failed to delete node {node_id}: {e}")
            raise QueryExecutionError(
                f"Failed to delete node: {e}", query=query
            ) from e

    async def create_relationship_generic(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """범용 관계 생성"""
        validated_type = validate_identifier(rel_type, "relationship_type")
        props = properties or {}

        query = f"""
        MATCH (src), (tgt)
        WHERE elementId(src) = $source_id AND elementId(tgt) = $target_id
        MERGE (src)-[r:{validated_type}]->(tgt)
        ON CREATE SET r += $props, r.created_at = datetime()
        ON MATCH SET r += $props, r.updated_at = datetime()
        RETURN
            elementId(r) as id,
            type(r) as type,
            elementId(src) as source_id,
            elementId(tgt) as target_id,
            properties(r) as properties,
            labels(src) as source_labels,
            labels(tgt) as target_labels
        """

        try:
            results = await self._client.execute_write(
                query, {"source_id": source_id, "target_id": target_id, "props": props}
            )
            if not results:
                raise EntityNotFoundError("Source or target node", f"{source_id}, {target_id}")
            return results[0]
        except EntityNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to create relationship {rel_type}: {e}")
            raise QueryExecutionError(
                f"Failed to create relationship: {e}", query=query
            ) from e

    async def delete_relationship_generic(self, rel_id: str) -> bool:
        """관계 삭제"""
        query = """
        MATCH ()-[r]->()
        WHERE elementId(r) = $rel_id
        DELETE r
        RETURN true as deleted
        """

        try:
            results = await self._client.execute_write(query, {"rel_id": rel_id})
            return len(results) > 0
        except Exception as e:
            logger.error(f"Failed to delete relationship {rel_id}: {e}")
            raise QueryExecutionError(
                f"Failed to delete relationship: {e}", query=query
            ) from e
