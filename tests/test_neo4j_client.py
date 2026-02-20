"""
Neo4j 클라이언트 테스트

실행 방법:
    pytest tests/test_neo4j_client.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings, get_settings
from src.infrastructure.neo4j_client import Neo4jClient, TransactionScope


class TestNeo4jClientUnit:
    """Neo4j 클라이언트 단위 테스트"""

    def test_client_initialization(self):
        """클라이언트 초기화 테스트"""
        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test",
            database="neo4j",
        )
        assert client._uri == "bolt://localhost:7687"
        assert client._user == "neo4j"
        assert client._database == "neo4j"
        assert client._driver is None

    def test_driver_not_initialized_error(self):
        """드라이버 미초기화 시 에러 테스트"""
        from src.domain.exceptions import DatabaseConnectionError

        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test",
        )
        with pytest.raises(DatabaseConnectionError):
            _ = client.driver


class TestGetSchemaInfoUnit:
    """get_schema_info 속성 인트로스펙션 단위 테스트"""

    @pytest.mark.asyncio
    async def test_schema_info_includes_property_introspection(self):
        """get_schema_info가 노드/관계 속성 정보를 포함하는지 테스트"""
        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test",
        )

        # execute_query를 모킹하여 각 쿼리에 대한 응답을 시뮬레이션
        call_count = 0
        async def mock_execute_query(query, parameters=None):
            nonlocal call_count
            call_count += 1
            if "db.labels" in query:
                return [{"label": "Employee"}, {"label": "Project"}]
            elif "db.relationshipTypes" in query:
                return [{"relationshipType": "WORKS_ON"}]
            elif "SHOW INDEXES" in query:
                return []
            elif "SHOW CONSTRAINTS" in query:
                return []
            elif "Employee" in query and "keys" in query:
                return [{"key": "name"}, {"key": "department"}]
            elif "Project" in query and "keys" in query:
                return [{"key": "name"}, {"key": "status"}, {"key": "budget_million"}]
            elif "WORKS_ON" in query and "keys" in query:
                return [{"key": "role"}, {"key": "allocated_hours"}, {"key": "actual_hours"}]
            return []

        client.execute_query = mock_execute_query

        schema = await client.get_schema_info()

        # 기존 필드 확인
        assert schema["node_labels"] == ["Employee", "Project"]
        assert schema["relationship_types"] == ["WORKS_ON"]

        # 속성 인트로스펙션 결과 확인
        assert "nodes" in schema
        assert len(schema["nodes"]) == 2
        emp_node = next(n for n in schema["nodes"] if n["label"] == "Employee")
        assert {"name": "name"} in emp_node["properties"]
        assert {"name": "department"} in emp_node["properties"]

        proj_node = next(n for n in schema["nodes"] if n["label"] == "Project")
        assert {"name": "budget_million"} in proj_node["properties"]

        assert "relationships" in schema
        assert len(schema["relationships"]) == 1
        works_on = schema["relationships"][0]
        assert works_on["type"] == "WORKS_ON"
        assert {"name": "allocated_hours"} in works_on["properties"]
        assert {"name": "actual_hours"} in works_on["properties"]

    @pytest.mark.asyncio
    async def test_schema_info_property_introspection_failure_is_safe(self):
        """속성 인트로스펙션 실패 시 기존 결과는 보존"""
        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test",
        )

        call_count = 0
        async def mock_execute_query(query, parameters=None):
            nonlocal call_count
            call_count += 1
            if "db.labels" in query:
                return [{"label": "Employee"}]
            elif "db.relationshipTypes" in query:
                return [{"relationshipType": "WORKS_ON"}]
            elif "SHOW INDEXES" in query:
                return []
            elif "SHOW CONSTRAINTS" in query:
                return []
            elif "keys" in query:
                raise RuntimeError("Property introspection failed")
            return []

        client.execute_query = mock_execute_query

        schema = await client.get_schema_info()

        # 기존 데이터는 정상
        assert schema["node_labels"] == ["Employee"]
        assert schema["relationship_types"] == ["WORKS_ON"]
        # 인트로스펙션 실패 시 nodes/relationships 없음
        assert "nodes" not in schema


class TestTransactionScope:
    """TransactionScope 단위 테스트"""

    @pytest.mark.asyncio
    async def test_run_query_serializes_results(self):
        """트랜잭션 내 쿼리가 결과를 직렬화"""
        mock_record = MagicMock()
        mock_record.keys.return_value = ["name", "count"]
        mock_record.__getitem__ = lambda self, key: {"name": "test", "count": 42}[key]

        mock_result = AsyncMock()
        mock_result.__aiter__ = lambda self: self
        mock_result._items = [mock_record]
        mock_result.__anext__ = AsyncMock(side_effect=[mock_record, StopAsyncIteration])

        mock_tx = AsyncMock()
        mock_tx.run.return_value = mock_result

        scope = TransactionScope(mock_tx)
        results = await scope.run_query("MATCH (n) RETURN n.name AS name, count(n) AS count")

        assert len(results) == 1
        assert results[0]["name"] == "test"
        assert results[0]["count"] == 42
        mock_tx.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_begin_transaction_commits_on_success(self):
        """성공 시 트랜잭션 커밋"""
        mock_tx = AsyncMock()
        mock_tx.closed = False

        mock_session = AsyncMock()
        mock_session.begin_transaction.return_value = mock_tx
        mock_session.close = AsyncMock()

        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test",
        )
        # driver.session()이 mock_session을 반환하도록 설정
        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        client._driver = mock_driver

        async with client.begin_transaction() as tx:
            assert isinstance(tx, TransactionScope)

        mock_tx.commit.assert_awaited_once()
        mock_tx.rollback.assert_not_awaited()
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_begin_transaction_rollbacks_on_error(self):
        """에러 시 트랜잭션 롤백"""
        mock_tx = AsyncMock()
        mock_tx.closed = False

        mock_session = AsyncMock()
        mock_session.begin_transaction.return_value = mock_tx
        mock_session.close = AsyncMock()

        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test",
        )
        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        client._driver = mock_driver

        with pytest.raises(ValueError, match="test error"):
            async with client.begin_transaction() as tx:
                raise ValueError("test error")

        mock_tx.commit.assert_not_awaited()
        mock_tx.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()


class TestNeo4jClientIntegration:
    """Neo4j 클라이언트 통합 테스트 (실제 DB 연결 필요)"""

    @pytest.fixture
    def settings(self) -> Settings:
        """테스트용 설정"""
        return get_settings()

    @pytest.fixture
    async def neo4j_client(self, settings: Settings):
        """Neo4j 클라이언트 픽스처"""
        client = Neo4jClient(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )
        await client.connect()
        yield client
        await client.close()

    @pytest.mark.asyncio
    async def test_connection(self, neo4j_client: Neo4jClient):
        """연결 테스트"""
        health = await neo4j_client.health_check()
        assert health["connected"] is True
        assert health["server_info"] is not None

    @pytest.mark.asyncio
    async def test_execute_query(self, neo4j_client: Neo4jClient):
        """쿼리 실행 테스트"""
        result = await neo4j_client.execute_query(
            "MATCH (n) RETURN count(n) as count LIMIT 1"
        )
        assert len(result) == 1
        assert "count" in result[0]

    @pytest.mark.asyncio
    async def test_get_schema_info(self, neo4j_client: Neo4jClient):
        """스키마 정보 조회 테스트"""
        schema = await neo4j_client.get_schema_info()
        assert "node_labels" in schema
        assert "relationship_types" in schema
        assert isinstance(schema["node_labels"], list)

    @pytest.mark.asyncio
    async def test_context_manager(self, settings: Settings):
        """컨텍스트 매니저 테스트"""
        async with Neo4jClient(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        ) as client:
            health = await client.health_check()
            assert health["connected"] is True

    @pytest.mark.asyncio
    async def test_session_context_manager(self, neo4j_client: Neo4jClient):
        """세션 컨텍스트 매니저 테스트"""
        async with neo4j_client.session() as session:
            result = await session.run("RETURN 1 as num")
            record = await result.single()
            assert record["num"] == 1
