"""
Neo4j Entity Repository - 엔티티 검색/탐색

책임:
- 이름/ID 기반 엔티티 검색
- 이웃 노드 탐색
- 관계 조회
- 서브그래프 추출
- 전문 검색 (Fulltext)
- 노드 검색 (GraphEdit용)
"""

import logging
import re
from typing import Any

from src.domain.exceptions import (
    EntityNotFoundError,
    QueryExecutionError,
)
from src.domain.types import SubGraphResult
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.neo4j_types import NodeResult, RelationshipResult
from src.repositories.neo4j_validators import (
    build_label_filter,
    build_rel_filter,
    strip_korean_suffix,
    validate_direction,
    validate_identifier,
)

logger = logging.getLogger(__name__)


class Neo4jEntityRepository:
    """엔티티 검색/탐색 전담 레포지토리"""

    def __init__(self, client: Neo4jClient):
        self._client = client

    async def find_entities_by_name(
        self,
        name: str,
        labels: list[str] | None = None,
        limit: int = 10,
    ) -> list[NodeResult]:
        """
        이름으로 엔티티 검색 (정확 일치 우선)

        3단계 폴백: 정확 일치 → 공백 제거 → 한국어 접미사 제거
        """
        label_filter = build_label_filter(labels)

        query = f"""
        MATCH (n{label_filter})
        WHERE toLower(n.name) = toLower($name)
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        LIMIT $limit
        """

        try:
            results = await self._client.execute_query(
                query, {"name": name, "limit": limit}
            )

            if not results:
                query_no_space = f"""
                MATCH (n{label_filter})
                WHERE replace(toLower(n.name), ' ', '') = replace(toLower($name), ' ', '')
                RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
                LIMIT $limit
                """
                results = await self._client.execute_query(
                    query_no_space, {"name": name, "limit": limit}
                )

            if not results:
                stripped = strip_korean_suffix(name)
                if stripped != name:
                    results = await self._client.execute_query(
                        query, {"name": stripped, "limit": limit}
                    )
                    if not results:
                        results = await self._client.execute_query(
                            query_no_space, {"name": stripped, "limit": limit}
                        )

            return [
                NodeResult(
                    id=r["id"],
                    labels=r["labels"],
                    properties=r["properties"],
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to find entities by name '{name}': {e}")
            raise QueryExecutionError(
                f"Failed to find entities: {e}", query=query
            ) from e

    async def find_entity_by_id(
        self,
        entity_id: str,
    ) -> NodeResult:
        """ID로 엔티티 조회"""
        query = """
        MATCH (n)
        WHERE elementId(n) = $entity_id
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        """

        results = await self._client.execute_query(query, {"entity_id": entity_id})

        if not results:
            raise EntityNotFoundError("Node", str(entity_id))

        r = results[0]
        return NodeResult(
            id=r["id"],
            labels=r["labels"],
            properties=r["properties"],
        )

    async def get_neighbors(
        self,
        entity_id: str,
        relationship_types: list[str] | None = None,
        direction: str = "both",
        depth: int = 1,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """이웃 노드 조회"""
        rel_filter = build_rel_filter(relationship_types)
        validated_direction = validate_direction(direction)

        if validated_direction == "out":
            pattern = f"-[r{rel_filter}*1..{depth}]->"
        elif validated_direction == "in":
            pattern = f"<-[r{rel_filter}*1..{depth}]-"
        else:
            pattern = f"-[r{rel_filter}*1..{depth}]-"

        query = f"""
        MATCH (start){pattern}(neighbor)
        WHERE elementId(start) = $entity_id
        RETURN DISTINCT
            elementId(neighbor) as neighbor_id,
            labels(neighbor) as neighbor_labels,
            properties(neighbor) as neighbor_properties,
            [rel in r | type(rel)] as relationship_types
        LIMIT $limit
        """

        results = await self._client.execute_query(
            query, {"entity_id": entity_id, "limit": limit}
        )

        return [
            {
                "node": NodeResult(
                    id=r["neighbor_id"],
                    labels=r["neighbor_labels"],
                    properties=r["neighbor_properties"],
                ),
                "relationship_types": r["relationship_types"],
            }
            for r in results
        ]

    async def get_relationships(
        self,
        entity_id: str,
        relationship_types: list[str] | None = None,
        direction: str = "both",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """엔티티의 관계 조회"""
        rel_filter = build_rel_filter(relationship_types)
        validated_direction = validate_direction(direction)

        if validated_direction == "out":
            query = f"""
            MATCH (n)-[r{rel_filter}]->(other)
            WHERE elementId(n) = $entity_id
            RETURN
                elementId(r) as rel_id, type(r) as rel_type, properties(r) as rel_props,
                elementId(n) as start_id, elementId(other) as end_id,
                labels(other) as other_labels, properties(other) as other_props
            LIMIT $limit
            """
        elif validated_direction == "in":
            query = f"""
            MATCH (n)<-[r{rel_filter}]-(other)
            WHERE elementId(n) = $entity_id
            RETURN
                elementId(r) as rel_id, type(r) as rel_type, properties(r) as rel_props,
                elementId(other) as start_id, elementId(n) as end_id,
                labels(other) as other_labels, properties(other) as other_props
            LIMIT $limit
            """
        else:
            query = f"""
            MATCH (n)-[r{rel_filter}]-(other)
            WHERE elementId(n) = $entity_id
            RETURN
                elementId(r) as rel_id, type(r) as rel_type, properties(r) as rel_props,
                elementId(startNode(r)) as start_id, elementId(endNode(r)) as end_id,
                labels(other) as other_labels, properties(other) as other_props
            LIMIT $limit
            """

        results = await self._client.execute_query(
            query, {"entity_id": entity_id, "limit": limit}
        )

        return [
            {
                "relationship": RelationshipResult(
                    id=r["rel_id"],
                    type=r["rel_type"],
                    start_node_id=r["start_id"],
                    end_node_id=r["end_id"],
                    properties=r["rel_props"],
                ),
                "other_node": {
                    "labels": r["other_labels"],
                    "properties": r["other_props"],
                },
            }
            for r in results
        ]

    async def search_fulltext(
        self,
        search_term: str,
        index_name: str = "entityIndex",
        limit: int = 10,
    ) -> list[NodeResult]:
        """전문 검색 (Full-text search)"""
        query = """
        CALL db.index.fulltext.queryNodes($index_name, $search_term)
        YIELD node, score
        RETURN elementId(node) as id, labels(node) as labels, properties(node) as properties, score
        ORDER BY score DESC
        LIMIT $limit
        """

        try:
            results = await self._client.execute_query(
                query,
                {"index_name": index_name, "search_term": search_term, "limit": limit},
            )
            return [
                NodeResult(
                    id=r["id"],
                    labels=r["labels"],
                    properties=r["properties"],
                )
                for r in results
            ]
        except Exception:
            logger.warning(
                f"Fulltext index '{index_name}' not found, falling back to CONTAINS search"
            )
            return await self.find_entities_by_name(search_term, limit=limit)

    async def get_subgraph(
        self,
        entity_ids: list[str],
        max_depth: int = 1,
        limit: int = 100,
    ) -> SubGraphResult:
        """서브그래프 추출"""
        query = f"""
        MATCH path = (n)-[*0..{max_depth}]-(m)
        WHERE elementId(n) IN $entity_ids
        WITH collect(DISTINCT n) + collect(DISTINCT m) as nodes,
             collect(DISTINCT relationships(path)) as rels
        UNWIND nodes as node
        WITH collect(DISTINCT node)[0..$limit] as limited_nodes, rels
        UNWIND limited_nodes as node
        UNWIND rels as rel_list
        UNWIND rel_list as rel
        RETURN
            collect(DISTINCT {{
                id: elementId(node),
                labels: labels(node),
                properties: properties(node)
            }}) as nodes,
            collect(DISTINCT {{
                id: elementId(rel),
                type: type(rel),
                start_id: elementId(startNode(rel)),
                end_id: elementId(endNode(rel)),
                properties: properties(rel)
            }}) as relationships
        """

        results = await self._client.execute_query(
            query, {"entity_ids": entity_ids, "limit": limit}
        )

        if not results:
            return {"nodes": [], "relationships": []}

        result = results[0]

        return {
            "nodes": [
                {
                    "id": n["id"],
                    "labels": n["labels"],
                    "properties": n["properties"],
                }
                for n in result.get("nodes", [])
            ],
            "relationships": [
                {
                    "id": r["id"],
                    "type": r["type"],
                    "start_node_id": r["start_id"],
                    "end_node_id": r["end_id"],
                    "properties": r["properties"],
                }
                for r in result.get("relationships", [])
            ],
        }

    async def find_similar_nodes(
        self,
        embedding: list[float],
        index_name: str,
        exclude_ids: list[str] | None = None,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> list[tuple[NodeResult, float]]:
        """주어진 임베딩과 유사한 노드 검색 (특정 노드 제외 가능)"""
        fetch_limit = limit + len(exclude_ids) if exclude_ids else limit

        try:
            raw_results = await self._client.vector_search(
                index_name=index_name,
                embedding=embedding,
                limit=fetch_limit,
                threshold=threshold,
            )

            results = [
                (
                    NodeResult(
                        id=r["id"],
                        labels=r["labels"],
                        properties=r["properties"],
                    ),
                    r["score"],
                )
                for r in raw_results
            ]

            if exclude_ids:
                exclude_set = set(exclude_ids)
                results = [
                    (node, score)
                    for node, score in results
                    if node.id not in exclude_set
                ]

            return results[:limit]
        except Exception as e:
            logger.error(f"find_similar_nodes failed on index '{index_name}': {e}")
            raise QueryExecutionError(
                f"Vector search failed: {e}", query=f"vector_search({index_name})"
            ) from e

    async def search_nodes(
        self,
        label: str | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """노드 검색 (레이블 필터, 이름 검색)"""
        if search:
            try:
                return await self._search_nodes_fulltext(label, search, limit)
            except Exception as e:
                err_msg = str(e).lower()
                if (
                    "index" in err_msg
                    or "fulltext" in err_msg
                    or "procedure" in err_msg
                ):
                    logger.debug(
                        "Fulltext index not available, falling back to CONTAINS: %s", e
                    )
                    return await self._search_nodes_contains(label, search, limit)
                raise

        return await self._search_nodes_contains(label, None, limit)

    async def _search_nodes_fulltext(
        self,
        label: str | None,
        search: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fulltext Index를 사용한 검색"""
        label_where = ""
        if label:
            validate_identifier(label, "label")
            label_where = "WHERE $label IN labels(n)"

        escaped = re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", search)
        fulltext_search = f"{escaped}*"

        query = f"""
        CALL db.index.fulltext.queryNodes('graph_edit_name_fulltext', $search)
        YIELD node, score
        WITH node as n, score
        {label_where}
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        ORDER BY score DESC
        LIMIT $limit
        """

        params: dict[str, Any] = {"search": fulltext_search, "limit": limit}
        if label:
            params["label"] = label

        return await self._client.execute_query(query, params)

    async def _search_nodes_contains(
        self,
        label: str | None,
        search: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """기존 CONTAINS 방식 검색 (폴백용)"""
        label_filter = ""
        if label:
            validated_label = validate_identifier(label, "label")
            label_filter = f":{validated_label}"

        where_clauses = []
        params: dict[str, Any] = {"limit": limit}

        if search:
            where_clauses.append("toLower(n.name) CONTAINS toLower($search)")
            params["search"] = search

        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        query = f"""
        MATCH (n{label_filter})
        {where_clause}
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        ORDER BY n.name
        LIMIT $limit
        """

        return await self._client.execute_query(query, params)

    async def find_concept_bridge(
        self,
        skill_name: str,
    ) -> dict[str, Any] | None:
        """Skill 이름으로 매칭되는 Concept + IS_A 계층 조회"""
        query = """
        MATCH (c:Concept) WHERE toLower(c.name) = toLower($name)
        OPTIONAL MATCH (c)-[:IS_A*0..5]->(parent:Concept)
        WITH c, collect(DISTINCT parent.name) AS ancestors
        ORDER BY elementId(c) ASC
        LIMIT 1
        RETURN c.name AS concept_name, ancestors AS hierarchy
        """

        results = await self._client.execute_query(query, {"name": skill_name})
        if not results:
            return None
        return results[0]

    async def find_relationship_by_id(self, rel_id: str) -> dict[str, Any]:
        """ID로 관계 조회"""
        query = """
        MATCH (src)-[r]->(tgt)
        WHERE elementId(r) = $rel_id
        RETURN
            elementId(r) as id,
            type(r) as type,
            elementId(src) as source_id,
            elementId(tgt) as target_id,
            properties(r) as properties,
            labels(src) as source_labels,
            properties(src) as source_properties,
            labels(tgt) as target_labels,
            properties(tgt) as target_properties
        """

        results = await self._client.execute_query(query, {"rel_id": rel_id})
        if not results:
            raise EntityNotFoundError("Edge", rel_id)
        return results[0]

    async def get_node_relationships_detailed(
        self,
        node_id: str,
    ) -> list[dict[str, Any]]:
        """노드에 연결된 관계 상세 조회 (방향, 상대 노드 정보 포함)"""
        query = """
        MATCH (n) WHERE elementId(n) = $node_id
        OPTIONAL MATCH (n)-[r_out]->(target)
        WITH n,
             [x IN collect(DISTINCT {
                 id: elementId(r_out),
                 type: type(r_out),
                 connected_node_id: elementId(target),
                 connected_node_labels: labels(target),
                 connected_node_name: coalesce(target.name, ''),
                 direction: 'outgoing'
             }) WHERE x.id IS NOT NULL] AS outgoing
        OPTIONAL MATCH (n)<-[r_in]-(source)
        WITH outgoing,
             [x IN collect(DISTINCT {
                 id: elementId(r_in),
                 type: type(r_in),
                 connected_node_id: elementId(source),
                 connected_node_labels: labels(source),
                 connected_node_name: coalesce(source.name, ''),
                 direction: 'incoming'
             }) WHERE x.id IS NOT NULL] AS incoming
        RETURN outgoing + incoming AS relationships
        """

        results = await self._client.execute_query(query, {"node_id": node_id})
        if not results:
            return []

        return results[0].get("relationships", [])

    async def check_cached_queries_exist(self) -> int:
        """CachedQuery 노드 수 조회"""
        query = """
        MATCH (c:CachedQuery)
        RETURN count(c) AS count
        """

        results = await self._client.execute_query(query, {})
        return results[0]["count"] if results else 0

    async def check_similar_relationships_exist(self) -> int:
        """SIMILAR 관계 수 조회"""
        query = """
        MATCH ()-[r:SIMILAR]->()
        RETURN count(r) AS count
        """

        results = await self._client.execute_query(query, {})
        return results[0]["count"] if results else 0
