"""
인증 시드 데이터 생성 스크립트

기본 역할 4개 + admin 계정을 Neo4j에 생성합니다.
멱등 실행 가능 (MERGE 사용).

Usage:
    python scripts/seed_auth_data.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth.password import PasswordHandler
from src.config import get_settings
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.user_repository import UserRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    client = Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    await client.connect()
    logger.info("Connected to Neo4j")

    try:
        # 제약조건 생성
        constraints = [
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT user_username_unique IF NOT EXISTS FOR (u:User) REQUIRE u.username IS UNIQUE",
            "CREATE CONSTRAINT role_name_unique IF NOT EXISTS FOR (r:Role) REQUIRE r.name IS UNIQUE",
        ]
        for stmt in constraints:
            await client.execute_query(stmt, {})
        logger.info("Constraints created")

        # 기본 역할 시드
        repo = UserRepository(client)
        await repo.seed_default_roles()

        # admin 계정 시드
        password_handler = PasswordHandler()
        admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "admin123")
        if admin_password == "admin123":
            logger.warning("Using default admin password — set INITIAL_ADMIN_PASSWORD for production")
        hashed = password_handler.hash_password(admin_password)
        admin = await repo.seed_admin_user("admin", hashed)
        logger.info(f"Admin user ready: {admin.get('username')}")

    finally:
        await client.close()
        logger.info("Neo4j connection closed")


if __name__ == "__main__":
    asyncio.run(main())
