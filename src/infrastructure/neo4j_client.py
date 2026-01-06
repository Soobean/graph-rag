"""
Neo4j 비동기 드라이버 래퍼

책임:
- Neo4j 드라이버 연결 관리 (연결 풀링)
- 비동기 세션 컨텍스트 제공
- 연결 상태 확인 (health check)
- 리소스 정리 (graceful shutdown)
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession, basic_auth
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable

from src.domain.exceptions import (
    DatabaseAuthenticationError,
    DatabaseConnectionError,
    DatabaseError,
)

logger = logging.getLogger(__name__)


class Neo4jClient:
    """
    Neo4j 비동기 드라이버 래퍼

    사용 예시:
        async with Neo4jClient(...) as client:
            async with client.session() as session:
                result = await session.run("MATCH (n) RETURN n LIMIT 10")
                records = [record async for record in result]
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_connection_pool_size: int = 50,
        connection_timeout: float = 30.0,
    ):
        """
        Neo4j 클라이언트 초기화

        Args:
            uri: Neo4j Bolt URI (예: "bolt://localhost:7687")
            user: Neo4j 사용자명
            password: Neo4j 비밀번호
            database: 데이터베이스 이름 (기본값: "neo4j")
            max_connection_pool_size: 커넥션 풀 최대 크기
            connection_timeout: 연결 타임아웃 (초)
        """
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._max_connection_pool_size = max_connection_pool_size
        self._connection_timeout = connection_timeout

        self._driver: AsyncDriver | None = None

        logger.info(
            f"Neo4jClient initialized: uri={uri}, database={database}, "
            f"pool_size={max_connection_pool_size}"
        )

    async def connect(self) -> None:
        """
        Neo4j 드라이버 연결 초기화

        Raises:
            DatabaseAuthenticationError: 인증 실패 시
            DatabaseConnectionError: 연결 실패 시
        """
        if self._driver is not None:
            logger.debug("Driver already connected, skipping connection")
            return

        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=basic_auth(self._user, self._password),
                max_connection_pool_size=self._max_connection_pool_size,
                connection_timeout=self._connection_timeout,
            )
            # 연결 확인
            await self._driver.verify_connectivity()
            logger.info(f"Successfully connected to Neo4j at {self._uri}")

        except AuthError as e:
            logger.error(f"Neo4j authentication failed: {e}")
            raise DatabaseAuthenticationError(
                f"Failed to authenticate with Neo4j: {e}"
            ) from e
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            raise DatabaseConnectionError(
                f"Neo4j service is unavailable at {self._uri}: {e}"
            ) from e
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise DatabaseConnectionError(f"Failed to connect to Neo4j: {e}") from e

    async def close(self) -> None:
        """
        Neo4j 드라이버 연결 종료

        graceful shutdown을 위해 모든 연결을 정리합니다.
        """
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j driver closed")

    async def __aenter__(self) -> "Neo4jClient":
        """비동기 컨텍스트 매니저 진입"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """비동기 컨텍스트 매니저 종료"""
        await self.close()

    @property
    def driver(self) -> AsyncDriver:
        """
        내부 드라이버 인스턴스 반환

        Raises:
            DatabaseConnectionError: 드라이버가 초기화되지 않은 경우
        """
        if self._driver is None:
            raise DatabaseConnectionError(
                "Neo4j driver is not initialized. Call connect() first."
            )
        return self._driver

    @asynccontextmanager
    async def session(
        self,
        database: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AsyncSession]:
        """
        비동기 세션 컨텍스트 매니저

        Args:
            database: 데이터베이스 이름 (기본값: 초기화 시 지정된 값)
            **kwargs: 추가 세션 옵션

        Yields:
            AsyncSession: Neo4j 비동기 세션

        사용 예시:
            async with client.session() as session:
                result = await session.run("MATCH (n:Employee) RETURN n")
        """
        db = database or self._database
        session = self.driver.session(database=db, **kwargs)
        try:
            yield session
        finally:
            await session.close()

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        단일 쿼리 실행 및 결과 반환

        간단한 쿼리 실행을 위한 편의 메서드입니다.
        복잡한 트랜잭션은 session()을 직접 사용하세요.

        Args:
            query: Cypher 쿼리 문자열
            parameters: 쿼리 파라미터 (선택)
            database: 데이터베이스 이름 (선택)

        Returns:
            쿼리 결과 레코드 리스트 (각 레코드는 dict)

        Raises:
            DatabaseError: 쿼리 실행 실패 시
        """
        try:
            async with self.session(database=database) as session:
                result = await session.run(query, parameters or {})
                records = [record.data() async for record in result]
                logger.debug(
                    f"Query executed successfully: {len(records)} records returned"
                )
                return records
        except Neo4jError as e:
            logger.error(f"Query execution failed: {e}")
            raise DatabaseError(f"Failed to execute query: {e}") from e

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        쓰기 쿼리 실행 (트랜잭션 보장)

        Args:
            query: Cypher 쿼리 문자열
            parameters: 쿼리 파라미터 (선택)
            database: 데이터베이스 이름 (선택)

        Returns:
            쿼리 결과 레코드 리스트
        """

        async def _write_tx(tx, q: str, params: dict) -> list[dict]:
            result = await tx.run(q, params)
            return [record.data() async for record in result]

        try:
            async with self.session(database=database) as session:
                records = await session.execute_write(
                    _write_tx, query, parameters or {}
                )
                logger.debug(f"Write query executed: {len(records)} records affected")
                return records
        except Neo4jError as e:
            logger.error(f"Write query failed: {e}")
            raise DatabaseError(f"Failed to execute write query: {e}") from e

    async def health_check(self) -> dict[str, Any]:
        """
        Neo4j 연결 상태 확인

        Returns:
            상태 정보 딕셔너리
            - connected: 연결 여부
            - uri: 연결 URI
            - database: 데이터베이스 이름
            - server_info: 서버 정보 (연결 시)
        """
        result = {
            "connected": False,
            "uri": self._uri,
            "database": self._database,
            "server_info": None,
            "error": None,
        }

        if self._driver is None:
            result["error"] = "Driver not initialized"
            return result

        try:
            await self._driver.verify_connectivity()
            server_info = await self._driver.get_server_info()
            result["connected"] = True
            result["server_info"] = {
                "address": str(server_info.address),
                "agent": server_info.agent,
                "protocol_version": server_info.protocol_version,
            }
        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"Health check failed: {e}")

        return result

    async def get_schema_info(self) -> dict[str, Any]:
        """
        데이터베이스 스키마 정보 조회

        Returns:
            스키마 정보 (노드 레이블, 관계 타입, 인덱스 등)
        """
        schema_info = {
            "node_labels": [],
            "relationship_types": [],
            "indexes": [],
            "constraints": [],
        }

        try:
            # 노드 레이블 조회
            labels_result = await self.execute_query("CALL db.labels()")
            schema_info["node_labels"] = [r.get("label") for r in labels_result]

            # 관계 타입 조회
            rel_result = await self.execute_query("CALL db.relationshipTypes()")
            schema_info["relationship_types"] = [
                r.get("relationshipType") for r in rel_result
            ]

            # 인덱스 조회
            idx_result = await self.execute_query("SHOW INDEXES")
            schema_info["indexes"] = [
                {
                    "name": r.get("name"),
                    "type": r.get("type"),
                    "labelsOrTypes": r.get("labelsOrTypes"),
                    "properties": r.get("properties"),
                }
                for r in idx_result
            ]

            # 제약 조건 조회
            const_result = await self.execute_query("SHOW CONSTRAINTS")
            schema_info["constraints"] = [
                {
                    "name": r.get("name"),
                    "type": r.get("type"),
                    "labelsOrTypes": r.get("labelsOrTypes"),
                    "properties": r.get("properties"),
                }
                for r in const_result
            ]

        except Exception as e:
            logger.warning(f"Failed to get schema info: {e}")
            schema_info["error"] = str(e)

        return schema_info
