"""
Neo4j Repository 단위 테스트

실행 방법:
    pytest tests/test_neo4j_repository.py -v
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.exceptions import EntityNotFoundError, QueryExecutionError, ValidationError
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

    def test_node_result_from_neo4j(self):
        """from_neo4j 팩토리 메서드 테스트"""
        neo4j_data = {
            "id": "4:abc123:123",
            "labels": ["Employee"],
            "properties": {"name": "테스트"},
        }
        node = NodeResult.from_neo4j(neo4j_data)
        assert node.id == "4:abc123:123"
        assert node.labels == ["Employee"]

    def test_node_result_from_neo4j_missing_fields(self):
        """from_neo4j 누락 필드 기본값 테스트"""
        node = NodeResult.from_neo4j({})
        assert node.id == ""
        assert node.labels == []
        assert node.properties == {}


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


class TestIdentifierValidation:
    """Cypher Injection 방어 검증 테스트"""

    @pytest.fixture
    def repo(self):
        """Mock 클라이언트로 Repository 생성"""
        mock_client = MagicMock()
        return Neo4jRepository(mock_client)

    def test_validate_identifier_valid(self, repo):
        """유효한 식별자 테스트"""
        assert repo._validate_identifier("Employee") == "Employee"
        assert repo._validate_identifier("WORKS_AT") == "WORKS_AT"
        assert repo._validate_identifier("사람") == "사람"
        assert repo._validate_identifier("Employee123") == "Employee123"
        assert repo._validate_identifier("person_type") == "person_type"

    def test_validate_identifier_empty(self, repo):
        """빈 식별자 검증"""
        with pytest.raises(ValidationError) as exc_info:
            repo._validate_identifier("")
        assert "Empty" in str(exc_info.value)

    def test_validate_identifier_injection_attempts(self, repo):
        """Cypher Injection 시도 검증"""
        # 특수문자, 공백, SQL/Cypher injection 패턴이 포함된 문자열 거부
        injection_attempts = [
            ("Employee; DROP DATABASE", "semicolon and space"),
            ("Employee`", "backtick"),
            ("Employee--", "double dash"),
            ("Employee/*", "comment start"),
            ("Employee]", "bracket"),
            ("Employee)", "parenthesis"),
            ("Employee'", "single quote"),
            ('Employee"', "double quote"),
            ("Employee OR 1=1", "space and equals"),
            ("Employee\t", "tab"),
            ("Employee{}", "braces"),
        ]
        for attempt, desc in injection_attempts:
            with pytest.raises(ValidationError, match="Invalid .* format"):
                repo._validate_identifier(attempt)

    def test_validate_labels(self, repo):
        """레이블 리스트 검증 테스트"""
        labels = ["Employee", "Employee", "사원"]
        validated = repo._validate_labels(labels)
        assert validated == labels

    def test_validate_labels_invalid(self, repo):
        """유효하지 않은 레이블 검증"""
        with pytest.raises(ValidationError):
            repo._validate_labels(["Valid", "Invalid;DROP"])

    def test_validate_relationship_types(self, repo):
        """관계 타입 검증 테스트"""
        rel_types = ["WORKS_AT", "KNOWS", "근무"]
        validated = repo._validate_relationship_types(rel_types)
        assert validated == rel_types

    def test_validate_direction_valid(self, repo):
        """유효한 방향 값 테스트"""
        for direction in ["in", "out", "both"]:
            assert repo._validate_direction(direction) == direction

    def test_validate_direction_invalid(self, repo):
        """유효하지 않은 방향 값 테스트"""
        with pytest.raises(ValidationError) as exc_info:
            repo._validate_direction("invalid")
        assert "direction" in str(exc_info.value)


class TestFilterBuilding:
    """필터 문자열 생성 테스트"""

    @pytest.fixture
    def repo(self):
        mock_client = MagicMock()
        return Neo4jRepository(mock_client)

    def test_build_label_filter_single(self, repo):
        """단일 레이블 필터"""
        result = repo._build_label_filter(["Employee"])
        assert result == ":Employee"

    def test_build_label_filter_multiple(self, repo):
        """다중 레이블 필터"""
        result = repo._build_label_filter(["Employee", "Employee"])
        assert result == ":Employee:Employee"

    def test_build_label_filter_empty(self, repo):
        """빈 레이블 필터"""
        assert repo._build_label_filter(None) == ""
        assert repo._build_label_filter([]) == ""

    def test_build_rel_filter_single(self, repo):
        """단일 관계 타입 필터"""
        result = repo._build_rel_filter(["WORKS_AT"])
        assert result == ":WORKS_AT"

    def test_build_rel_filter_multiple(self, repo):
        """다중 관계 타입 필터"""
        result = repo._build_rel_filter(["WORKS_AT", "KNOWS"])
        assert result == ":WORKS_AT|KNOWS"

    def test_build_rel_filter_empty(self, repo):
        """빈 관계 타입 필터"""
        assert repo._build_rel_filter(None) == ""
        assert repo._build_rel_filter([]) == ""


class TestSchemaCaching:
    """스키마 캐싱 테스트"""

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
    def repo(self, mock_client):
        return Neo4jRepository(mock_client)

    @pytest.mark.asyncio
    async def test_schema_cache_initial_fetch(self, repo, mock_client):
        """초기 스키마 조회 시 DB 호출"""
        schema = await repo.get_schema()
        assert schema["node_labels"] == ["Employee", "Company"]
        mock_client.get_schema_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_schema_cache_hit(self, repo, mock_client):
        """캐시 히트 시 DB 호출 없음"""
        await repo.get_schema()
        await repo.get_schema()
        await repo.get_schema()
        # 첫 번째 호출만 DB 접근
        assert mock_client.get_schema_info.call_count == 1

    @pytest.mark.asyncio
    async def test_schema_cache_force_refresh(self, repo, mock_client):
        """force_refresh 시 캐시 무시"""
        await repo.get_schema()
        await repo.get_schema(force_refresh=True)
        assert mock_client.get_schema_info.call_count == 2

    @pytest.mark.asyncio
    async def test_schema_cache_invalidation(self, repo, mock_client):
        """캐시 무효화 테스트"""
        await repo.get_schema()
        repo.invalidate_schema_cache()
        await repo.get_schema()
        assert mock_client.get_schema_info.call_count == 2

    @pytest.mark.asyncio
    async def test_schema_cache_ttl_expiry(self, repo, mock_client):
        """TTL 만료 시 재조회"""
        await repo.get_schema()

        # TTL 만료 시뮬레이션
        repo._schema_cache_time = time.time() - repo.SCHEMA_CACHE_TTL_SECONDS - 1

        await repo.get_schema()
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
            {"id": "4:abc123:123", "labels": ["Employee"], "properties": {"name": "홍길동"}}
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
            {"id": "4:abc123:1", "labels": ["Employee"], "properties": {"name": "홍길동"}},
            {"id": "4:abc123:2", "labels": ["Employee"], "properties": {"name": "홍길순"}},
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
            await repo.find_entities_by_name(
                "test", labels=["Employee; DROP DATABASE"]
            )


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
