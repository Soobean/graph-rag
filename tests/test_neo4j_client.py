"""
Neo4j 클라이언트 테스트

실행 방법:
    pytest tests/test_neo4j_client.py -v
"""

import pytest

from src.config import Settings, get_settings
from src.infrastructure.neo4j_client import Neo4jClient


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
