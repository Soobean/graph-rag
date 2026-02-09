"""
Neo4j Repository - 그래프 데이터 접근 계층

책임:
- 엔티티 검색 (노드 조회)
- 관계 탐색
- Cypher 쿼리 실행
- 스키마 정보 제공 (TTL 기반 캐싱)
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from src.domain.adaptive.models import OntologyProposal, ProposalStatus
from src.domain.exceptions import (
    EntityNotFoundError,
    QueryExecutionError,
    ValidationError,
)
from src.domain.types import SubGraphResult
from src.domain.validators import CYPHER_IDENTIFIER_PATTERN
from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


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
        self._schema_fetch_lock: asyncio.Lock | None = None  # Lazy initialization

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
        if not CYPHER_IDENTIFIER_PATTERN.match(value):
            raise ValidationError(
                f"Invalid {field_name} format: '{value}'. "
                "Must start with a letter and contain only alphanumeric, "
                "underscore, or Korean characters.",
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
        이름으로 엔티티 검색 (정확 일치 우선)

        Args:
            name: 검색할 이름
            labels: 필터링할 노드 레이블 (선택)
            limit: 최대 결과 수

        Returns:
            매칭된 노드 리스트 (정확 일치 우선, 없으면 대소문자 무시 일치)
        """
        label_filter = self._build_label_filter(labels)

        # 1단계: 정확 일치 (대소문자 무시)
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

            # 2단계: 결과 없으면 공백 제거 후 재시도 (예: "AI 연구소" → "AI연구소")
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
        그래프 스키마 정보 조회 (TTL 기반 캐싱, 동시성 안전)
        """
        current_time = time.time()
        cache_expired = (
            current_time - self._schema_cache_time
        ) > self.SCHEMA_CACHE_TTL_SECONDS

        if force_refresh or self._schema_cache is None or cache_expired:
            # Lazy lock initialization (이벤트 루프에서만 생성 가능)
            if self._schema_fetch_lock is None:
                self._schema_fetch_lock = asyncio.Lock()

            async with self._schema_fetch_lock:
                # Double-check after acquiring lock (다른 태스크가 이미 갱신했을 수 있음)
                if (
                    force_refresh
                    or self._schema_cache is None
                    or (time.time() - self._schema_cache_time)
                    > self.SCHEMA_CACHE_TTL_SECONDS
                ):
                    logger.debug(
                        "Fetching schema from database (cache miss or expired)"
                    )
                    self._schema_cache = await self._client.get_schema_info()
                    self._schema_cache_time = time.time()
                else:
                    logger.debug("Using cached schema (updated by another task)")
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

    # ============================================
    # Vector Search 관련 메서드
    # ============================================

    async def vector_search_nodes(
        self,
        embedding: list[float],
        index_name: str,
        labels: list[str] | None = None,
        limit: int = 10,
        threshold: float | None = None,
    ) -> list[tuple[NodeResult, float]]:
        """
        Vector Index를 사용한 노드 유사도 검색

        Args:
            embedding: 검색 쿼리 임베딩 벡터
            index_name: 사용할 Vector Index 이름
            labels: 필터링할 노드 레이블 (선택)
            limit: 최대 결과 수
            threshold: 최소 유사도 점수 (None이면 필터링 없음)

        Returns:
            (NodeResult, score) 튜플 리스트
        """
        try:
            results = await self._client.vector_search(
                index_name=index_name,
                embedding=embedding,
                limit=limit,
                threshold=threshold,
            )

            # 레이블 필터링 (필요시)
            if labels:
                validated_labels = set(self._validate_labels(labels))
                results = [
                    r
                    for r in results
                    if validated_labels.intersection(set(r.get("labels", [])))
                ]

            return [
                (
                    NodeResult(
                        id=r["id"],
                        labels=r["labels"],
                        properties=r["properties"],
                    ),
                    r["score"],
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Vector search failed on index '{index_name}': {e}")
            raise QueryExecutionError(
                f"Vector search failed: {e}", query=f"vector_search({index_name})"
            ) from e

    async def ensure_vector_index(
        self,
        index_name: str,
        label: str,
        property_name: str,
        dimensions: int = 1536,
    ) -> bool:
        """
        Vector Index가 존재하는지 확인하고 없으면 생성

        Args:
            index_name: 인덱스 이름
            label: 노드 레이블
            property_name: 임베딩이 저장된 속성명
            dimensions: 임베딩 차원

        Returns:
            성공 여부
        """
        return await self._client.create_vector_index(
            index_name=index_name,
            label=label,
            property_name=property_name,
            dimensions=dimensions,
        )

    async def upsert_node_embedding(
        self,
        node_id: str,
        property_name: str,
        embedding: list[float],
    ) -> bool:
        """
        노드에 임베딩 저장/업데이트

        Args:
            node_id: 노드의 elementId
            property_name: 임베딩을 저장할 속성명
            embedding: 임베딩 벡터

        Returns:
            성공 여부
        """
        return await self._client.upsert_embedding(
            node_id=node_id,
            property_name=property_name,
            embedding=embedding,
        )

    async def batch_upsert_node_embeddings(
        self,
        updates: list[dict[str, Any]],
        property_name: str,
    ) -> int:
        """
        여러 노드에 임베딩 일괄 저장

        Args:
            updates: [{"node_id": str, "embedding": list[float]}, ...]
            property_name: 임베딩을 저장할 속성명

        Returns:
            업데이트된 노드 수
        """
        return await self._client.batch_upsert_embeddings(
            updates=updates,
            property_name=property_name,
        )

    async def find_similar_nodes(
        self,
        embedding: list[float],
        index_name: str,
        exclude_ids: list[str] | None = None,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> list[tuple[NodeResult, float]]:
        """
        주어진 임베딩과 유사한 노드 검색 (특정 노드 제외 가능)

        Entity Resolution에서 유사 엔티티 찾기에 활용

        Args:
            embedding: 검색 쿼리 임베딩 벡터
            index_name: 사용할 Vector Index 이름
            exclude_ids: 결과에서 제외할 노드 ID 리스트
            limit: 최대 결과 수
            threshold: 최소 유사도 점수

        Returns:
            (NodeResult, score) 튜플 리스트
        """
        # 제외할 노드가 있으면 더 많이 가져와서 필터링
        fetch_limit = limit + len(exclude_ids) if exclude_ids else limit

        results = await self.vector_search_nodes(
            embedding=embedding,
            index_name=index_name,
            limit=fetch_limit,
            threshold=threshold,
        )

        # 제외 노드 필터링
        if exclude_ids:
            exclude_set = set(exclude_ids)
            results = [
                (node, score) for node, score in results if node.id not in exclude_set
            ]

        return results[:limit]

    # ============================================
    # Ontology Proposal 관련 메서드 (Adaptive Ontology)
    # ============================================

    async def save_ontology_proposal(
        self,
        proposal: OntologyProposal,
    ) -> OntologyProposal:
        """
        온톨로지 제안 저장 (MERGE 패턴)

        동일한 term + category 조합이 이미 존재하면 업데이트,
        없으면 새로 생성합니다.

        Args:
            proposal: 저장할 OntologyProposal

        Returns:
            저장된 OntologyProposal (id 포함)
        """
        query = """
        MERGE (p:OntologyProposal {term: $term, category: $category})
        ON CREATE SET
            p.id = $id,
            p.version = 1,
            p.proposal_type = $proposal_type,
            p.suggested_action = $suggested_action,
            p.suggested_parent = $suggested_parent,
            p.suggested_canonical = $suggested_canonical,
            p.evidence_questions = $evidence_questions,
            p.frequency = $frequency,
            p.confidence = $confidence,
            p.status = $status,
            p.source = $source,
            p.created_at = datetime(),
            p.updated_at = datetime()
        ON MATCH SET
            p.version = p.version + 1,
            p.frequency = p.frequency + 1,
            p.evidence_questions = CASE
                WHEN $question <> '' AND NOT $question IN COALESCE(p.evidence_questions, [])
                THEN COALESCE(p.evidence_questions, []) + [$question]
                ELSE COALESCE(p.evidence_questions, [])
            END,
            p.updated_at = datetime()
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by
        """

        data = proposal.to_dict()
        # MERGE 시 첫 번째 질문을 추출 (빈 리스트 안전 처리)
        evidence_questions = data.get("evidence_questions") or []
        question = evidence_questions[0] if evidence_questions else ""

        try:
            results = await self._client.execute_query(
                query,
                {
                    "id": data["id"],
                    "term": data["term"],
                    "category": data["category"],
                    "proposal_type": data["proposal_type"],
                    "suggested_action": data["suggested_action"],
                    "suggested_parent": data["suggested_parent"],
                    "suggested_canonical": data["suggested_canonical"],
                    "evidence_questions": data["evidence_questions"],
                    "frequency": data["frequency"],
                    "confidence": data["confidence"],
                    "status": data["status"],
                    "source": data["source"],
                    "question": question,
                },
            )

            if results:
                return OntologyProposal.from_dict(results[0])
            return proposal

        except Exception as e:
            logger.error(f"Failed to save ontology proposal: {e}")
            raise QueryExecutionError(
                f"Failed to save ontology proposal: {e}", query=query
            ) from e

    async def find_ontology_proposal(
        self,
        term: str,
        category: str,
    ) -> OntologyProposal | None:
        """
        term + category로 기존 제안 검색

        Args:
            term: 검색할 용어
            category: 카테고리

        Returns:
            찾은 OntologyProposal 또는 None
        """
        query = """
        MATCH (p:OntologyProposal {term: $term, category: $category})
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        """

        try:
            results = await self._client.execute_query(
                query, {"term": term, "category": category}
            )

            if results:
                return OntologyProposal.from_dict(results[0])
            return None

        except Exception as e:
            logger.error(f"Failed to find ontology proposal: {e}")
            return None

    async def update_proposal_frequency(
        self,
        proposal_id: str,
        question: str,
    ) -> bool:
        """
        제안의 빈도 증가 및 증거 질문 추가

        Args:
            proposal_id: 제안 ID
            question: 추가할 증거 질문

        Returns:
            성공 여부
        """
        query = """
        MATCH (p:OntologyProposal {id: $id})
        SET
            p.frequency = p.frequency + 1,
            p.evidence_questions = CASE
                WHEN $question <> '' AND NOT $question IN COALESCE(p.evidence_questions, [])
                THEN COALESCE(p.evidence_questions, []) + [$question]
                ELSE COALESCE(p.evidence_questions, [])
            END,
            p.updated_at = datetime()
        RETURN p.id as id
        """

        try:
            results = await self._client.execute_query(
                query, {"id": proposal_id, "question": question}
            )
            return len(results) > 0

        except Exception as e:
            logger.error(f"Failed to update proposal frequency: {e}")
            return False

    async def update_proposal_status(
        self,
        proposal: OntologyProposal,
        expected_version: int,
    ) -> bool:
        """
        제안 상태 업데이트 (Optimistic Locking)

        Args:
            proposal: 업데이트할 OntologyProposal
            expected_version: 예상 버전 (필수 - Optimistic Locking 보장)

        Returns:
            성공 여부

        Raises:
            ValueError: expected_version이 양수가 아닌 경우
        """
        if expected_version < 1:
            raise ValueError(f"expected_version must be >= 1, got {expected_version}")

        # Optimistic Locking: 버전 일치 시에만 업데이트
        query = """
        MATCH (p:OntologyProposal {id: $id})
        WHERE p.version = $expected_version
        SET
            p.status = $status,
            p.version = p.version + 1,
            p.reviewed_at = $reviewed_at,
            p.reviewed_by = $reviewed_by,
            p.updated_at = datetime()
        RETURN p.id as id, p.version as new_version
        """

        data = proposal.to_dict()

        try:
            results = await self._client.execute_query(
                query,
                {
                    "id": data["id"],
                    "status": data["status"],
                    "reviewed_at": data["reviewed_at"],
                    "reviewed_by": data["reviewed_by"],
                    "expected_version": expected_version,
                },
            )

            if not results:
                logger.warning(
                    f"Optimistic lock failed for proposal {data['id']} "
                    f"(expected version: {expected_version})"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to update proposal status: {e}")
            return False

    async def count_today_auto_approved(self) -> int:
        """
        오늘 자동 승인된 제안 수 조회

        Returns:
            오늘 자동 승인된 제안 수
        """
        query = """
        MATCH (p:OntologyProposal)
        WHERE p.status = $status
          AND date(p.reviewed_at) = date()
        RETURN count(p) as count
        """

        try:
            results = await self._client.execute_query(
                query, {"status": ProposalStatus.AUTO_APPROVED.value}
            )

            if results:
                count = results[0].get("count", 0)
                return int(count) if count is not None else 0
            return 0

        except Exception as e:
            logger.error(f"Failed to count today's auto-approved proposals: {e}")
            return 0

    async def try_auto_approve_with_limit(
        self,
        proposal_id: str,
        expected_version: int,
        daily_limit: int,
    ) -> bool:
        """
        일일 한도를 확인하면서 원자적으로 자동 승인 (Race Condition 방지)

        Args:
            proposal_id: 제안 ID
            expected_version: 예상 버전 (Optimistic Locking)
            daily_limit: 일일 자동 승인 한도 (0이면 무제한)

        Returns:
            True: 자동 승인 성공
            False: 한도 초과 또는 버전 불일치로 실패
        """
        # daily_limit이 0이면 무제한
        if daily_limit <= 0:
            # 한도 없음 - 일반 업데이트 사용
            query = """
            MATCH (p:OntologyProposal {id: $proposal_id})
            WHERE p.version = $expected_version
            SET
                p.status = $new_status,
                p.version = p.version + 1,
                p.reviewed_at = datetime(),
                p.reviewed_by = 'system',
                p.updated_at = datetime()
            RETURN p.id as id
            """
            params = {
                "proposal_id": proposal_id,
                "expected_version": expected_version,
                "new_status": ProposalStatus.AUTO_APPROVED.value,
            }
        else:
            # 원자적 카운트 + 업데이트 쿼리
            query = """
            // 오늘 자동 승인 수 카운트
            OPTIONAL MATCH (approved:OntologyProposal)
            WHERE approved.status = $auto_approved_status
              AND date(approved.reviewed_at) = date()
            WITH count(approved) as today_count

            // 한도 이하일 때만 타겟 제안 매칭
            MATCH (p:OntologyProposal {id: $proposal_id})
            WHERE today_count < $daily_limit
              AND p.version = $expected_version
            SET
                p.status = $new_status,
                p.version = p.version + 1,
                p.reviewed_at = datetime(),
                p.reviewed_by = 'system',
                p.updated_at = datetime()
            RETURN p.id as id, today_count
            """
            params = {
                "proposal_id": proposal_id,
                "expected_version": expected_version,
                "new_status": ProposalStatus.AUTO_APPROVED.value,
                "auto_approved_status": ProposalStatus.AUTO_APPROVED.value,
                "daily_limit": daily_limit,
            }

        try:
            results = await self._client.execute_query(query, params)

            if not results:
                logger.debug(
                    f"Auto-approve failed for {proposal_id}: "
                    f"limit exceeded or version mismatch (expected: {expected_version})"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to auto-approve proposal: {e}")
            return False

    async def get_pending_proposals(
        self,
        category: str | None = None,
        limit: int = 50,
    ) -> list[OntologyProposal]:
        """
        대기 중인 제안 목록 조회

        Args:
            category: 필터링할 카테고리 (None이면 전체)
            limit: 최대 결과 수

        Returns:
            OntologyProposal 리스트

        Raises:
            ValidationError: category가 빈 문자열인 경우
        """
        # 빈 문자열 검증 (None은 허용 - 전체 조회)
        if category is not None:
            category = category.strip()
            if not category:
                raise ValidationError(
                    "Category cannot be empty string (use None for all)",
                    field="category",
                )

        # 동적 쿼리 대신 파라미터화된 조건 사용 (Injection 방지)
        query = """
        MATCH (p:OntologyProposal)
        WHERE p.status = $status
          AND ($category IS NULL OR p.category = $category)
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        ORDER BY p.frequency DESC, p.confidence DESC
        LIMIT $limit
        """

        try:
            results = await self._client.execute_query(
                query,
                {
                    "status": ProposalStatus.PENDING.value,
                    "category": category,
                    "limit": limit,
                },
            )

            return [OntologyProposal.from_dict(r) for r in results]

        except Exception as e:
            logger.error(f"Failed to get pending proposals: {e}")
            return []

    # ============================================
    # Ontology Admin API 메서드
    # ============================================

    async def get_proposal_by_id(self, proposal_id: str) -> OntologyProposal | None:
        """
        ID로 단일 제안 조회

        Args:
            proposal_id: 제안 ID (UUID)

        Returns:
            OntologyProposal 또는 None
        """
        query = """
        MATCH (p:OntologyProposal {id: $id})
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        """

        try:
            results = await self._client.execute_query(query, {"id": proposal_id})

            if results:
                return OntologyProposal.from_dict(results[0])
            return None

        except Exception as e:
            logger.error(f"Failed to get proposal by id {proposal_id}: {e}")
            return None

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
        """
        필터링 + 페이지네이션 목록 조회

        Args:
            status: 필터링할 상태 (None이면 전체)
            proposal_type: 필터링할 제안 유형 (None이면 전체)
            source: 필터링할 출처 (chat, background, admin, None이면 전체)
            category: 필터링할 카테고리 (None이면 전체)
            term_search: 용어 검색어 (CONTAINS 매칭)
            sort_by: 정렬 필드 (created_at, frequency, confidence)
            sort_order: 정렬 방향 (asc, desc)
            offset: 건너뛸 레코드 수
            limit: 최대 결과 수

        Returns:
            (OntologyProposal 리스트, 총 개수) 튜플
        """
        # SECURITY: 화이트리스트 기반 정렬 필드 검증 (Cypher Injection 방지)
        # sort_by와 sort_direction은 아래 f-string에서 사용되므로 반드시 검증 필요
        allowed_sort_fields = {"created_at", "frequency", "confidence", "updated_at"}
        if sort_by not in allowed_sort_fields:
            sort_by = "created_at"  # 기본값으로 폴백

        # SECURITY: 방향값도 명시적으로 제한 (ASC/DESC만 허용)
        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        # 카운트 쿼리
        count_query = """
        MATCH (p:OntologyProposal)
        WHERE ($status IS NULL OR p.status = $status)
          AND ($proposal_type IS NULL OR p.proposal_type = $proposal_type)
          AND ($source IS NULL OR p.source = $source)
          AND ($category IS NULL OR p.category = $category)
          AND ($term_search IS NULL OR toLower(p.term) CONTAINS toLower($term_search))
        RETURN count(p) as total
        """

        # 데이터 쿼리
        # NOTE: ORDER BY에서 f-string 사용 - sort_by/sort_direction은 위에서 화이트리스트 검증됨
        data_query = f"""
        MATCH (p:OntologyProposal)
        WHERE ($status IS NULL OR p.status = $status)
          AND ($proposal_type IS NULL OR p.proposal_type = $proposal_type)
          AND ($source IS NULL OR p.source = $source)
          AND ($category IS NULL OR p.category = $category)
          AND ($term_search IS NULL OR toLower(p.term) CONTAINS toLower($term_search))
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        ORDER BY p.{sort_by} {sort_direction}
        SKIP $offset
        LIMIT $limit
        """

        params = {
            "status": status,
            "proposal_type": proposal_type,
            "source": source,
            "category": category,
            "term_search": term_search,
            "offset": offset,
            "limit": limit,
        }

        try:
            count_results = await self._client.execute_query(count_query, params)
            total = count_results[0]["total"] if count_results else 0

            data_results = await self._client.execute_query(data_query, params)
            proposals = [OntologyProposal.from_dict(r) for r in data_results]

            return proposals, total

        except Exception as e:
            logger.error(f"Failed to get paginated proposals: {e}")
            return [], 0

    async def get_ontology_stats(self) -> dict[str, Any]:
        """
        온톨로지 통계 집계

        Returns:
            상태별 카운트, 카테고리 분포, top 미해결 용어 등
        """
        query = """
        // 상태별 카운트
        MATCH (p:OntologyProposal)
        WITH
            count(p) as total,
            sum(CASE WHEN p.status = 'pending' THEN 1 ELSE 0 END) as pending,
            sum(CASE WHEN p.status = 'approved' THEN 1 ELSE 0 END) as approved,
            sum(CASE WHEN p.status = 'auto_approved' THEN 1 ELSE 0 END) as auto_approved,
            sum(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) as rejected

        // 카테고리 분포 (별도 쿼리로 분리)
        OPTIONAL MATCH (p2:OntologyProposal)
        WITH total, pending, approved, auto_approved, rejected,
             collect({category: p2.category, status: p2.status}) as all_categories

        RETURN
            total,
            pending,
            approved,
            auto_approved,
            rejected,
            all_categories
        """

        # Top 미해결 용어 (pending 상태, 빈도순)
        top_terms_query = """
        MATCH (p:OntologyProposal)
        WHERE p.status = 'pending'
        RETURN p.term as term, p.category as category,
               p.frequency as frequency, p.confidence as confidence
        ORDER BY p.frequency DESC, p.confidence DESC
        LIMIT 10
        """

        try:
            stats_results = await self._client.execute_query(query, {})
            top_terms_results = await self._client.execute_query(top_terms_query, {})

            if not stats_results:
                return {
                    "total_proposals": 0,
                    "pending_count": 0,
                    "approved_count": 0,
                    "auto_approved_count": 0,
                    "rejected_count": 0,
                    "category_distribution": {},
                    "top_unresolved_terms": [],
                }

            stats = stats_results[0]

            # 카테고리 분포 계산
            category_dist: dict[str, int] = {}
            for item in stats.get("all_categories", []):
                if item and item.get("category"):
                    cat = item["category"]
                    category_dist[cat] = category_dist.get(cat, 0) + 1

            return {
                "total_proposals": stats.get("total", 0),
                "pending_count": stats.get("pending", 0),
                "approved_count": stats.get("approved", 0),
                "auto_approved_count": stats.get("auto_approved", 0),
                "rejected_count": stats.get("rejected", 0),
                "category_distribution": category_dist,
                "top_unresolved_terms": [
                    {
                        "term": r["term"],
                        "category": r["category"],
                        "frequency": r["frequency"],
                        "confidence": r["confidence"],
                    }
                    for r in top_terms_results
                ],
            }

        except Exception as e:
            logger.error(f"Failed to get ontology stats: {e}")
            return {
                "total_proposals": 0,
                "pending_count": 0,
                "approved_count": 0,
                "auto_approved_count": 0,
                "rejected_count": 0,
                "category_distribution": {},
                "top_unresolved_terms": [],
            }

    async def batch_update_proposal_status(
        self,
        proposal_ids: list[str],
        new_status: str,
        reviewed_by: str | None = None,
        rejection_reason: str | None = None,
    ) -> tuple[int, list[str]]:
        """
        일괄 상태 업데이트 (Optimistic Locking 없음)

        Warning:
            이 메서드는 **버전 체크 없이** 업데이트합니다.
            동시성 충돌 시 마지막 요청이 이전 요청을 덮어씁니다.
            단일 관리자가 사용하는 Admin UI에서만 사용하세요.

            개별 제안의 동시성 제어가 필요하면 update_proposal_with_version()을 사용하세요.

        Args:
            proposal_ids: 업데이트할 제안 ID 목록
            new_status: 새 상태 값
            reviewed_by: 검토자 ID
            rejection_reason: 거절 사유 (rejected 상태일 때)

        Returns:
            (성공 수, 실패한 ID 목록) 튜플
            실패 원인: pending 상태가 아니거나 존재하지 않음
        """
        query = """
        UNWIND $proposal_ids as pid
        MATCH (p:OntologyProposal {id: pid})
        WHERE p.status = 'pending'
        SET
            p.status = $new_status,
            p.version = p.version + 1,
            p.reviewed_at = datetime(),
            p.reviewed_by = $reviewed_by,
            p.rejection_reason = $rejection_reason,
            p.updated_at = datetime()
        RETURN p.id as id
        """

        try:
            results = await self._client.execute_query(
                query,
                {
                    "proposal_ids": proposal_ids,
                    "new_status": new_status,
                    "reviewed_by": reviewed_by,
                    "rejection_reason": rejection_reason,
                },
            )

            updated_ids = {r["id"] for r in results}
            failed_ids = [pid for pid in proposal_ids if pid not in updated_ids]

            return len(updated_ids), failed_ids

        except Exception as e:
            logger.error(f"Failed to batch update proposals: {e}")
            return 0, proposal_ids

    async def update_proposal_with_version(
        self,
        proposal_id: str,
        expected_version: int,
        updates: dict[str, Any],
    ) -> OntologyProposal | None:
        """
        제안 수정 (Optimistic Locking)

        Args:
            proposal_id: 제안 ID
            expected_version: 예상 버전 (일치해야 업데이트)
            updates: 업데이트할 필드 딕셔너리

        Returns:
            업데이트된 OntologyProposal 또는 None (버전 불일치 시)
        """
        # SECURITY: 화이트리스트 기반 필드 검증 (Cypher Injection 방지)
        # 아래 f-string에서 필드명이 사용되므로 반드시 검증 필요
        allowed_fields = {
            "suggested_parent",
            "suggested_canonical",
            "category",
            "suggested_action",
            "status",
            "reviewed_at",
            "reviewed_by",
            "rejection_reason",
        }

        # SET 절 동적 생성 (허용된 필드만 - 화이트리스트 검증됨)
        set_clauses = []
        params: dict[str, Any] = {
            "id": proposal_id,
            "expected_version": expected_version,
        }

        for field, value in updates.items():
            if field in allowed_fields:
                # NOTE: field는 위 allowed_fields에서 검증됨 - Injection 안전
                set_clauses.append(f"p.{field} = ${field}")
                params[field] = value

        if not set_clauses:
            # 업데이트할 필드가 없으면 현재 상태 반환
            return await self.get_proposal_by_id(proposal_id)

        # 버전 증가 및 updated_at 추가
        set_clauses.extend(
            [
                "p.version = p.version + 1",
                "p.updated_at = datetime()",
            ]
        )

        query = f"""
        MATCH (p:OntologyProposal {{id: $id}})
        WHERE p.version = $expected_version
        SET {", ".join(set_clauses)}
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        """

        try:
            results = await self._client.execute_query(query, params)

            if results:
                return OntologyProposal.from_dict(results[0])
            return None

        except Exception as e:
            logger.error(f"Failed to update proposal {proposal_id}: {e}")
            return None

    async def create_proposal(
        self,
        proposal: OntologyProposal,
    ) -> OntologyProposal:
        """
        새 제안 생성 (수동 생성용)

        기존 save_ontology_proposal은 MERGE 패턴을 사용하지만,
        이 메서드는 항상 새로운 노드를 생성합니다.

        Args:
            proposal: 생성할 OntologyProposal

        Returns:
            생성된 OntologyProposal
        """
        query = """
        CREATE (p:OntologyProposal {
            id: $id,
            version: 1,
            proposal_type: $proposal_type,
            term: $term,
            category: $category,
            suggested_action: $suggested_action,
            suggested_parent: $suggested_parent,
            suggested_canonical: $suggested_canonical,
            suggested_relation_type: $suggested_relation_type,
            evidence_questions: $evidence_questions,
            frequency: $frequency,
            confidence: $confidence,
            status: $status,
            source: $source,
            created_at: datetime(),
            updated_at: datetime(),
            reviewed_at: null,
            reviewed_by: null,
            rejection_reason: null,
            applied_at: null
        })
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        """

        data = proposal.to_dict()

        try:
            results = await self._client.execute_query(
                query,
                {
                    "id": data["id"],
                    "proposal_type": data["proposal_type"],
                    "term": data["term"],
                    "category": data["category"],
                    "suggested_action": data["suggested_action"],
                    "suggested_parent": data["suggested_parent"],
                    "suggested_canonical": data["suggested_canonical"],
                    "suggested_relation_type": data["suggested_relation_type"],
                    "evidence_questions": data["evidence_questions"],
                    "frequency": data["frequency"],
                    "confidence": data["confidence"],
                    "status": data["status"],
                    "source": data["source"],
                },
            )

            if results:
                return OntologyProposal.from_dict(results[0])
            return proposal

        except Exception as e:
            logger.error(f"Failed to create proposal: {e}")
            raise QueryExecutionError(
                f"Failed to create proposal: {e}", query=query
            ) from e

    async def get_proposal_current_version(self, proposal_id: str) -> int | None:
        """
        제안의 현재 버전 조회

        Args:
            proposal_id: 제안 ID

        Returns:
            현재 버전 번호 또는 None (존재하지 않을 때)
        """
        query = """
        MATCH (p:OntologyProposal {id: $id})
        RETURN p.version as version
        """

        try:
            results = await self._client.execute_query(query, {"id": proposal_id})

            if results:
                return results[0]["version"]
            return None

        except Exception as e:
            logger.error(f"Failed to get proposal version: {e}")
            return None

    # ============================================
    # Ontology Application 메서드 (Phase 4)
    # ============================================

    # Concept 이름 검증 상수
    CONCEPT_NAME_MIN_LENGTH = 1
    CONCEPT_NAME_MAX_LENGTH = 100

    def _validate_concept_name(self, name: str, field_name: str = "name") -> str:
        """
        Concept 이름 검증

        Args:
            name: 검증할 이름
            field_name: 에러 메시지용 필드명

        Returns:
            정규화된 이름 (strip 적용)

        Raises:
            ValidationError: 유효하지 않은 이름인 경우
        """
        if name is None:
            raise ValidationError(f"{field_name} cannot be None", field=field_name)

        name = name.strip()

        if not name:
            raise ValidationError(
                f"{field_name} cannot be empty or whitespace only",
                field=field_name,
            )

        if len(name) < self.CONCEPT_NAME_MIN_LENGTH:
            raise ValidationError(
                f"{field_name} must be at least {self.CONCEPT_NAME_MIN_LENGTH} characters",
                field=field_name,
            )

        if len(name) > self.CONCEPT_NAME_MAX_LENGTH:
            raise ValidationError(
                f"{field_name} must be at most {self.CONCEPT_NAME_MAX_LENGTH} characters",
                field=field_name,
            )

        return name

    async def concept_exists(self, name: str) -> bool:
        """
        Concept 노드 존재 여부 확인

        Args:
            name: 개념 이름

        Returns:
            존재 여부

        Raises:
            ValidationError: 이름이 유효하지 않은 경우
        """
        validated_name = self._validate_concept_name(name)

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
        """
        Concept 노드 생성 또는 기존 노드 반환 (MERGE 패턴)

        Args:
            name: 개념 이름
            concept_type: 개념 유형 (skill, department 등)
            is_canonical: 정규 형태 여부 (alias면 False)
            description: 설명
            source: 출처 정보 (proposal:{id} 형식)

        Returns:
            생성/조회된 Concept 노드 정보

        Raises:
            ValidationError: 이름이 유효하지 않은 경우
            QueryExecutionError: 쿼리 실행 실패 시
        """
        validated_name = self._validate_concept_name(name)

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
            results = await self._client.execute_query(
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
        """
        SAME_AS 관계 생성 (동의어 매핑)

        Args:
            alias_name: 별칭 개념 이름
            canonical_name: 정규 개념 이름
            weight: 관계 가중치 (유사도)
            proposal_id: 출처 제안 ID

        Returns:
            성공 여부

        Raises:
            ValidationError: 이름이 유효하지 않은 경우
        """
        validated_alias = self._validate_concept_name(alias_name, "alias_name")
        validated_canonical = self._validate_concept_name(
            canonical_name, "canonical_name"
        )

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
            results = await self._client.execute_query(
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
        """
        IS_A 관계 생성 (계층 관계)

        Args:
            child_name: 자식 개념 이름
            parent_name: 부모 개념 이름
            depth: 계층 깊이
            proposal_id: 출처 제안 ID

        Returns:
            성공 여부

        Raises:
            ValidationError: 이름이 유효하지 않은 경우
        """
        validated_child = self._validate_concept_name(child_name, "child_name")
        validated_parent = self._validate_concept_name(parent_name, "parent_name")

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
            results = await self._client.execute_query(
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
        """
        REQUIRES 관계 생성 (엔티티-스킬 요구 관계)

        Args:
            entity_name: 엔티티 이름 (예: "Senior Engineer")
            skill_name: 스킬 이름 (예: "Python")
            proposal_id: 출처 제안 ID

        Returns:
            성공 여부

        Raises:
            ValidationError: 이름이 유효하지 않은 경우
        """
        validated_entity = self._validate_concept_name(entity_name, "entity_name")
        validated_skill = self._validate_concept_name(skill_name, "skill_name")

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
            results = await self._client.execute_query(
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
        """
        PART_OF 관계 생성 (부분-전체 관계)

        Args:
            part_name: 부분 개념 이름 (예: "Microservices")
            whole_name: 전체 개념 이름 (예: "Architecture")
            proposal_id: 출처 제안 ID

        Returns:
            성공 여부

        Raises:
            ValidationError: 이름이 유효하지 않은 경우
        """
        validated_part = self._validate_concept_name(part_name, "part_name")
        validated_whole = self._validate_concept_name(whole_name, "whole_name")

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
            results = await self._client.execute_query(
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

    async def update_proposal_applied_at(self, proposal_id: str) -> bool:
        """
        제안의 applied_at 필드 업데이트 (온톨로지 적용 완료 시각)

        Args:
            proposal_id: 제안 ID

        Returns:
            성공 여부
        """
        query = """
        MATCH (p:OntologyProposal {id: $id})
        SET p.applied_at = datetime()
        RETURN p.id as id
        """

        try:
            results = await self._client.execute_query(query, {"id": proposal_id})
            return len(results) > 0

        except Exception as e:
            logger.error(f"Failed to update proposal applied_at: {e}")
            return False

    # ============================================
    # Graph Edit CRUD 메서드
    # ============================================

    async def create_node_generic(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """
        범용 노드 생성

        Args:
            label: 노드 레이블 (사전 검증 필요)
            properties: 노드 속성

        Returns:
            생성된 노드 정보 (id, labels, properties)
        """
        validated_label = self._validate_identifier(label, "label")

        query = f"""
        CREATE (n:{validated_label} $props)
        SET n.created_at = datetime()
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        """

        try:
            results = await self._client.execute_write(query, {"props": properties})
            if not results:
                raise QueryExecutionError(
                    "Node creation returned no results", query=query
                )
            return results[0]
        except QueryExecutionError:
            raise
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
        """
        동일 레이블 내 이름 중복 확인 (대소문자 무시)

        Args:
            label: 노드 레이블
            name: 확인할 이름

        Returns:
            중복 존재 여부
        """
        validated_label = self._validate_identifier(label, "label")

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
        """
        노드 속성 수정

        Args:
            node_id: 노드 elementId
            properties: 추가/수정할 속성
            remove_keys: 삭제할 속성 키 리스트

        Returns:
            수정된 노드 정보

        Raises:
            EntityNotFoundError: 노드가 존재하지 않는 경우
        """
        # REMOVE 절 동적 생성 (속성명도 Cypher identifier 검증 필요)
        remove_clause = ""
        if remove_keys:
            validated_keys = [
                self._validate_identifier(key, "property_name")
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
        """
        노드 삭제

        Args:
            node_id: 노드 elementId
            force: True면 연결된 관계도 함께 삭제 (DETACH DELETE)

        Returns:
            삭제 성공 여부
        """
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
        """
        노드에 연결된 관계 수 조회

        Args:
            node_id: 노드 elementId

        Returns:
            관계 수
        """
        query = """
        MATCH (n)
        WHERE elementId(n) = $node_id
        OPTIONAL MATCH (n)-[r]-()
        RETURN count(r) as count
        """

        results = await self._client.execute_query(query, {"node_id": node_id})
        return results[0]["count"] if results else 0

    async def create_relationship_generic(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        범용 관계 생성

        Args:
            source_id: 소스 노드 elementId
            target_id: 타겟 노드 elementId
            rel_type: 관계 타입 (사전 검증 필요)
            properties: 관계 속성

        Returns:
            생성된 관계 정보
        """
        validated_type = self._validate_identifier(rel_type, "relationship_type")
        props = properties or {}

        query = f"""
        MATCH (src), (tgt)
        WHERE elementId(src) = $source_id AND elementId(tgt) = $target_id
        CREATE (src)-[r:{validated_type} $props]->(tgt)
        SET r.created_at = datetime()
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

    async def find_relationship_by_id(self, rel_id: str) -> dict[str, Any] | None:
        """
        ID로 관계 조회

        Args:
            rel_id: 관계 elementId

        Returns:
            관계 정보 또는 None
        """
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
        return results[0] if results else None

    async def delete_relationship_generic(self, rel_id: str) -> bool:
        """
        관계 삭제

        Args:
            rel_id: 관계 elementId

        Returns:
            삭제 성공 여부
        """
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

    async def search_nodes(
        self,
        label: str | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        노드 검색 (레이블 필터, 이름 CONTAINS 검색)

        Args:
            label: 필터링할 레이블 (None이면 전체)
            search: 이름 검색어 (CONTAINS, 대소문자 무시)
            limit: 최대 결과 수

        Returns:
            노드 정보 리스트
        """
        label_filter = ""
        if label:
            validated_label = self._validate_identifier(label, "label")
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
