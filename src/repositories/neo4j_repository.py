"""
Neo4j Repository - 그래프 데이터 접근 계층

책임:
- 엔티티 검색 (노드 조회)
- 관계 탐색
- Cypher 쿼리 실행
- 스키마 정보 제공 (TTL 기반 캐싱)
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from src.domain.exceptions import (
    EntityNotFoundError,
    QueryExecutionError,
    ValidationError,
)
from src.domain.types import SubGraphResult
from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# Cypher Injection 방어용 정규식 패턴
# 레이블/관계 타입은 알파벳, 숫자, 언더스코어, 한글만 허용
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_\uAC00-\uD7A3]+$")


@dataclass
class NodeResult:
    """노드 검색 결과"""

    id: str  # elementId() 반환값 (Neo4j 5.x+)
    labels: list[str]
    properties: dict[str, Any]

    @classmethod
    def from_neo4j(cls, node: dict[str, Any]) -> "NodeResult":
        """Neo4j 노드 데이터에서 생성"""
        return cls(
            id=node.get("id", ""),
            labels=node.get("labels", []),
            properties=node.get("properties", {}),
        )


@dataclass
class RelationshipResult:
    """관계 검색 결과"""

    id: str  # elementId() 반환값 (Neo4j 5.x+)
    type: str
    start_node_id: str
    end_node_id: str
    properties: dict[str, Any]


@dataclass
class PathResult:
    """경로 검색 결과"""

    nodes: list[NodeResult]
    relationships: list[RelationshipResult]
    length: int


class Neo4jRepository:
    """
    Neo4j 그래프 데이터 Repository

    사용 예시:
        repo = Neo4jRepository(neo4j_client)
        entities = await repo.find_entities_by_name("홍길동")
        neighbors = await repo.get_neighbors(entity_id=123, depth=2)
    """

    # 허용되는 방향 값
    VALID_DIRECTIONS = {"in", "out", "both"}

    # 스키마 캐시 TTL (초) - 스키마는 자주 변경되지 않으므로 5분
    SCHEMA_CACHE_TTL_SECONDS = 300

    def __init__(self, client: Neo4jClient):
        self._client = client
        # 스키마 캐시
        self._schema_cache: dict[str, Any] | None = None
        self._schema_cache_time: float = 0.0

    @staticmethod
    def _validate_identifier(value: str, field_name: str = "identifier") -> str:
        """
        Cypher 식별자(레이블, 관계 타입) 검증

        Args:
            value: 검증할 값
            field_name: 에러 메시지용 필드명

        Returns:
            검증된 값

        Raises:
            ValidationError: 유효하지 않은 형식인 경우
        """
        if not value:
            raise ValidationError(
                f"Empty {field_name} is not allowed", field=field_name
            )
        if not IDENTIFIER_PATTERN.match(value):
            raise ValidationError(
                f"Invalid {field_name} format: '{value}'. "
                "Only alphanumeric, underscore, and Korean characters are allowed.",
                field=field_name,
            )
        return value

    def _validate_labels(self, labels: list[str]) -> list[str]:
        """레이블 리스트 검증"""
        return [self._validate_identifier(label, "label") for label in labels]

    def _validate_relationship_types(self, rel_types: list[str]) -> list[str]:
        """관계 타입 리스트 검증"""
        return [self._validate_identifier(rt, "relationship_type") for rt in rel_types]

    def _validate_direction(self, direction: str) -> str:
        """방향 값 검증"""
        if direction not in self.VALID_DIRECTIONS:
            raise ValidationError(
                f"Invalid direction: '{direction}'. Must be one of {self.VALID_DIRECTIONS}",
                field="direction",
            )
        return direction

    def _build_label_filter(self, labels: list[str] | None) -> str:
        """안전한 레이블 필터 문자열 생성"""
        if not labels:
            return ""
        validated = self._validate_labels(labels)
        return ":" + ":".join(validated)

    def _build_rel_filter(self, relationship_types: list[str] | None) -> str:
        """안전한 관계 타입 필터 문자열 생성"""
        if not relationship_types:
            return ""
        validated = self._validate_relationship_types(relationship_types)
        return ":" + "|".join(validated)

    async def find_entities_by_name(
        self,
        name: str,
        labels: list[str] | None = None,
        limit: int = 10,
    ) -> list[NodeResult]:
        """
        이름으로 엔티티 검색

        Args:
            name: 검색할 이름 (부분 일치)
            labels: 필터링할 노드 레이블 (선택)
            limit: 최대 결과 수

        Returns:
            매칭된 노드 리스트
        """
        label_filter = self._build_label_filter(labels)

        query = f"""
        MATCH (n{label_filter})
        WHERE n.name CONTAINS $name
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        LIMIT $limit
        """

        try:
            results = await self._client.execute_query(
                query, {"name": name, "limit": limit}
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
        """
        ID로 엔티티 조회

        Args:
            entity_id: Neo4j elementId (문자열)

        Returns:
            노드 결과

        Raises:
            EntityNotFoundError: 엔티티를 찾을 수 없는 경우
        """
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

    async def find_entities_by_property(
        self,
        property_name: str,
        property_value: Any,
        labels: list[str] | None = None,
        limit: int = 10,
    ) -> list[NodeResult]:
        """
        속성 값으로 엔티티 검색

        Args:
            property_name: 속성 이름
            property_value: 속성 값
            labels: 필터링할 노드 레이블 (선택)
            limit: 최대 결과 수

        Returns:
            매칭된 노드 리스트
        """
        label_filter = self._build_label_filter(labels)

        query = f"""
        MATCH (n{label_filter})
        WHERE n[$property_name] = $property_value
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        LIMIT $limit
        """

        results = await self._client.execute_query(
            query,
            {
                "property_name": property_name,
                "property_value": property_value,
                "limit": limit,
            },
        )

        return [
            NodeResult(
                id=r["id"],
                labels=r["labels"],
                properties=r["properties"],
            )
            for r in results
        ]

    async def get_neighbors(
        self,
        entity_id: str,
        relationship_types: list[str] | None = None,
        direction: str = "both",
        depth: int = 1,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        이웃 노드 조회

        Args:
            entity_id: 시작 노드 elementId (문자열)
            relationship_types: 필터링할 관계 타입 (선택)
            direction: 관계 방향 ("in", "out", "both")
            depth: 탐색 깊이
            limit: 최대 결과 수

        Returns:
            이웃 노드와 관계 정보 리스트
        """
        rel_filter = self._build_rel_filter(relationship_types)
        validated_direction = self._validate_direction(direction)

        # 방향에 따른 패턴 설정
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
        """
        엔티티의 관계 조회

        Args:
            entity_id: 노드 elementId (문자열)
            relationship_types: 필터링할 관계 타입
            direction: 관계 방향
            limit: 최대 결과 수

        Returns:
            관계 정보 리스트
        """
        rel_filter = self._build_rel_filter(relationship_types)
        validated_direction = self._validate_direction(direction)

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

    async def execute_cypher(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Cypher 쿼리 직접 실행

        LLM이 생성한 Cypher 쿼리를 실행합니다.

        Args:
            query: Cypher 쿼리
            parameters: 쿼리 파라미터

        Returns:
            쿼리 결과
        """
        try:
            results = await self._client.execute_query(query, parameters)
            logger.info(f"Cypher query executed: {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Cypher query failed: {e}\nQuery: {query}")
            raise QueryExecutionError(str(e), query=query) from e

    async def get_schema(self, force_refresh: bool = False) -> dict[str, Any]:
        """
        그래프 스키마 정보 조회 (TTL 기반 캐싱)
        """
        current_time = time.time()
        cache_expired = (
            current_time - self._schema_cache_time
        ) > self.SCHEMA_CACHE_TTL_SECONDS

        if force_refresh or self._schema_cache is None or cache_expired:
            logger.debug("Fetching schema from database (cache miss or expired)")
            self._schema_cache = await self._client.get_schema_info()
            self._schema_cache_time = current_time
        else:
            logger.debug("Using cached schema")

        return self._schema_cache

    def invalidate_schema_cache(self) -> None:
        """스키마 캐시 무효화"""
        self._schema_cache = None
        self._schema_cache_time = 0.0
        logger.debug("Schema cache invalidated")

    async def get_node_labels(self) -> list[str]:
        """노드 레이블 목록 조회"""
        schema = await self.get_schema()
        return schema.get("node_labels", [])

    async def get_relationship_types(self) -> list[str]:
        """관계 타입 목록 조회"""
        schema = await self.get_schema()
        return schema.get("relationship_types", [])

    async def get_node_properties(self, label: str) -> list[str]:
        """
        특정 레이블의 노드 속성 목록 조회

        Args:
            label: 노드 레이블

        Returns:
            속성 이름 리스트
        """
        query = """
        MATCH (n)
        WHERE $label IN labels(n)
        UNWIND keys(n) as key
        RETURN DISTINCT key
        LIMIT 100
        """

        results = await self._client.execute_query(query, {"label": label})
        return [r["key"] for r in results]

    async def search_fulltext(
        self,
        search_term: str,
        index_name: str = "entityIndex",
        limit: int = 10,
    ) -> list[NodeResult]:
        """
        전문 검색 (Full-text search)
        """
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
            # 전문 검색 인덱스가 없으면 일반 검색으로 폴백
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
        """
        서브그래프 추출

        주어진 엔티티들과 연결된 서브그래프를 반환합니다.

        Args:
            entity_ids: 시작 노드 elementId 리스트 (문자열)
            max_depth: 최대 탐색 깊이
            limit: 최대 노드 수

        Returns:
            노드와 관계 정보를 포함한 서브그래프
        """
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
