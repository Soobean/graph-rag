"""
Neo4j Repository 단위 테스트

실행 방법:
    pytest tests/test_neo4j_repository.py -v
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.exceptions import (
    EntityNotFoundError,
    QueryExecutionError,
    ValidationError,
)
from src.repositories.neo4j_repository import (
    Neo4jRepository,
    NodeResult,
    RelationshipResult,
)


class TestNodeResult:
    """NodeResult 데이터클래스 테스트"""

    def test_node_result_creation(self):
        """NodeResult 생성 테스트"""
        node = NodeResult(
            id="4:abc123:1",
            labels=["Employee", "Employee"],
            properties={"name": "홍길동", "age": 30},
        )
        assert node.id == "4:abc123:1"
        assert node.labels == ["Employee", "Employee"]
        assert node.properties["name"] == "홍길동"


class TestRelationshipResult:
    """RelationshipResult 데이터클래스 테스트"""

    def test_relationship_result_creation(self):
        """RelationshipResult 생성 테스트"""
        rel = RelationshipResult(
            id="5:abc123:1",
            type="WORKS_AT",
            start_node_id="4:abc123:10",
            end_node_id="4:abc123:20",
            properties={"since": 2020},
        )
        assert rel.id == "5:abc123:1"
        assert rel.type == "WORKS_AT"
        assert rel.start_node_id == "4:abc123:10"
        assert rel.end_node_id == "4:abc123:20"


class TestSchemaCaching:
    """스키마 캐싱 테스트 — Neo4jSchemaRepository 직접 테스트"""

    @pytest.fixture
    def mock_client(self):
        """Mock Neo4j 클라이언트"""
        client = MagicMock()
        client.get_schema_info = AsyncMock(
            return_value={
                "node_labels": ["Employee", "Company"],
                "relationship_types": ["WORKS_AT"],
            }
        )
        return client

    @pytest.fixture
    def schema_repo(self, mock_client):
        from src.repositories.neo4j_schema_repository import Neo4jSchemaRepository

        return Neo4jSchemaRepository(mock_client)

    @pytest.mark.asyncio
    async def test_schema_cache_initial_fetch(self, schema_repo, mock_client):
        """초기 스키마 조회 시 DB 호출"""
        schema = await schema_repo.get_schema()
        assert schema["node_labels"] == ["Employee", "Company"]
        mock_client.get_schema_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_schema_cache_hit(self, schema_repo, mock_client):
        """캐시 히트 시 DB 호출 없음"""
        await schema_repo.get_schema()
        await schema_repo.get_schema()
        await schema_repo.get_schema()
        # 첫 번째 호출만 DB 접근
        assert mock_client.get_schema_info.call_count == 1

    @pytest.mark.asyncio
    async def test_schema_cache_force_refresh(self, schema_repo, mock_client):
        """force_refresh 시 캐시 무시"""
        await schema_repo.get_schema()
        await schema_repo.get_schema(force_refresh=True)
        assert mock_client.get_schema_info.call_count == 2

    @pytest.mark.asyncio
    async def test_schema_cache_invalidation(self, schema_repo, mock_client):
        """캐시 무효화 테스트"""
        await schema_repo.get_schema()
        schema_repo.invalidate_schema_cache()
        await schema_repo.get_schema()
        assert mock_client.get_schema_info.call_count == 2

    @pytest.mark.asyncio
    async def test_schema_cache_ttl_expiry(self, schema_repo, mock_client):
        """TTL 만료 시 재조회"""
        await schema_repo.get_schema()

        # TTL 만료 시뮬레이션
        schema_repo._schema_cache_time = (
            time.time() - schema_repo.SCHEMA_CACHE_TTL_SECONDS - 1
        )

        await schema_repo.get_schema()
        assert mock_client.get_schema_info.call_count == 2


class TestEntityOperations:
    """엔티티 조회 연산 테스트"""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.execute_query = AsyncMock()
        return client

    @pytest.fixture
    def repo(self, mock_client):
        return Neo4jRepository(mock_client)

    @pytest.mark.asyncio
    async def test_find_entity_by_id_found(self, repo, mock_client):
        """ID로 엔티티 조회 - 성공"""
        mock_client.execute_query.return_value = [
            {
                "id": "4:abc123:123",
                "labels": ["Employee"],
                "properties": {"name": "홍길동"},
            }
        ]

        result = await repo.find_entity_by_id("4:abc123:123")
        assert result.id == "4:abc123:123"
        assert result.labels == ["Employee"]
        assert result.properties["name"] == "홍길동"

    @pytest.mark.asyncio
    async def test_find_entity_by_id_not_found(self, repo, mock_client):
        """ID로 엔티티 조회 - 미발견"""
        mock_client.execute_query.return_value = []

        with pytest.raises(EntityNotFoundError):
            await repo.find_entity_by_id("4:abc123:999")

    @pytest.mark.asyncio
    async def test_find_entities_by_name(self, repo, mock_client):
        """이름으로 엔티티 검색"""
        mock_client.execute_query.return_value = [
            {
                "id": "4:abc123:1",
                "labels": ["Employee"],
                "properties": {"name": "홍길동"},
            },
            {
                "id": "4:abc123:2",
                "labels": ["Employee"],
                "properties": {"name": "홍길순"},
            },
        ]

        results = await repo.find_entities_by_name("홍길")
        assert len(results) == 2
        assert all(isinstance(r, NodeResult) for r in results)

    @pytest.mark.asyncio
    async def test_find_entities_by_name_with_labels(self, repo, mock_client):
        """레이블 필터와 함께 이름 검색"""
        mock_client.execute_query.return_value = []

        await repo.find_entities_by_name("테스트", labels=["Employee", "Employee"])

        # 쿼리에 레이블 필터가 포함되었는지 확인
        call_args = mock_client.execute_query.call_args
        query = call_args[0][0]
        assert ":Employee:Employee" in query

    @pytest.mark.asyncio
    async def test_find_entities_by_name_injection_blocked(self, repo, mock_client):
        """이름 검색 시 레이블 Injection 차단"""
        with pytest.raises(ValidationError):
            await repo.find_entities_by_name("test", labels=["Employee; DROP DATABASE"])


class TestCypherExecution:
    """Cypher 쿼리 실행 테스트"""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.execute_query = AsyncMock()
        return client

    @pytest.fixture
    def repo(self, mock_client):
        return Neo4jRepository(mock_client)

    @pytest.mark.asyncio
    async def test_execute_cypher_success(self, repo, mock_client):
        """Cypher 쿼리 실행 성공"""
        mock_client.execute_query.return_value = [{"count": 10}]

        result = await repo.execute_cypher(
            "MATCH (n) RETURN count(n) as count",
            {"param": "value"},
        )
        assert result == [{"count": 10}]

    @pytest.mark.asyncio
    async def test_execute_cypher_failure(self, repo, mock_client):
        """Cypher 쿼리 실행 실패"""
        mock_client.execute_query.side_effect = Exception("Query syntax error")

        with pytest.raises(QueryExecutionError) as exc_info:
            await repo.execute_cypher("INVALID QUERY")

        assert "Query syntax error" in str(exc_info.value)


class TestNeighborOperations:
    """이웃 노드 조회 테스트"""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.execute_query = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def repo(self, mock_client):
        return Neo4jRepository(mock_client)

    @pytest.mark.asyncio
    async def test_get_neighbors_direction_out(self, repo, mock_client):
        """나가는 방향 이웃 조회"""
        await repo.get_neighbors(entity_id="4:abc123:1", direction="out")

        query = mock_client.execute_query.call_args[0][0]
        assert "->" in query

    @pytest.mark.asyncio
    async def test_get_neighbors_direction_in(self, repo, mock_client):
        """들어오는 방향 이웃 조회"""
        await repo.get_neighbors(entity_id="4:abc123:1", direction="in")

        query = mock_client.execute_query.call_args[0][0]
        assert "<-" in query

    @pytest.mark.asyncio
    async def test_get_neighbors_direction_both(self, repo, mock_client):
        """양방향 이웃 조회"""
        await repo.get_neighbors(entity_id="4:abc123:1", direction="both")

        query = mock_client.execute_query.call_args[0][0]
        # 양방향은 화살표 없이 단순 연결
        assert "-[r" in query and "->" not in query and "<-" not in query

    @pytest.mark.asyncio
    async def test_get_neighbors_with_relationship_filter(self, repo, mock_client):
        """관계 타입 필터와 함께 이웃 조회"""
        await repo.get_neighbors(
            entity_id="4:abc123:1",
            relationship_types=["WORKS_AT", "KNOWS"],
        )

        query = mock_client.execute_query.call_args[0][0]
        assert ":WORKS_AT|KNOWS" in query

    @pytest.mark.asyncio
    async def test_get_neighbors_invalid_direction(self, repo):
        """유효하지 않은 방향 값"""
        with pytest.raises(ValidationError):
            await repo.get_neighbors(entity_id="4:abc123:1", direction="invalid")
