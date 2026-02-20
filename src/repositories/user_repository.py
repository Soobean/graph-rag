"""
User Repository — Neo4j 기반 사용자 데이터 접근 계층

Neo4j에 User, Role 노드를 저장하고 관계를 관리합니다.
"""

import logging
from typing import Any

from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class UserRepository:
    """Neo4j 기반 사용자 저장소"""

    def __init__(self, neo4j_client: Neo4jClient):
        self._client = neo4j_client

    async def find_by_username(self, username: str) -> dict[str, Any] | None:
        """사용자명으로 조회 (대소문자 무시)"""
        query = """
        MATCH (u:User)
        WHERE toLower(u.username) = toLower($username)
        OPTIONAL MATCH (u)-[:HAS_ROLE]->(r:Role)
        RETURN u {.*, roles: collect(r.name)} AS user
        """
        results = await self._client.execute_query(query, {"username": username})
        if results:
            return results[0]["user"]
        return None

    async def find_by_id(self, user_id: str) -> dict[str, Any] | None:
        """사용자 ID로 조회"""
        query = """
        MATCH (u:User {id: $user_id})
        OPTIONAL MATCH (u)-[:HAS_ROLE]->(r:Role)
        RETURN u {.*, roles: collect(r.name)} AS user
        """
        results = await self._client.execute_query(query, {"user_id": user_id})
        if results:
            return results[0]["user"]
        return None

    async def create_user(
        self,
        user_id: str,
        username: str,
        hashed_password: str,
        roles: list[str] | None = None,
        department: str | None = None,
    ) -> dict[str, Any]:
        """사용자 생성 + 역할 연결"""
        query = """
        CREATE (u:User {
            id: $user_id,
            username: $username,
            hashed_password: $hashed_password,
            department: $department,
            is_active: true,
            created_at: datetime()
        })
        WITH u
        UNWIND $roles AS role_name
        MERGE (r:Role {name: role_name})
        MERGE (u)-[:HAS_ROLE]->(r)
        RETURN u {.*, roles: $roles} AS user
        """
        results = await self._client.execute_query(
            query,
            {
                "user_id": user_id,
                "username": username,
                "hashed_password": hashed_password,
                "department": department,
                "roles": roles or ["viewer"],
            },
        )
        return results[0]["user"]

    async def update_user(
        self, user_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """사용자 정보 업데이트"""
        set_clauses = []
        params: dict[str, Any] = {"user_id": user_id}
        for key, value in updates.items():
            if key in ("username", "hashed_password", "department", "is_active"):
                set_clauses.append(f"u.{key} = ${key}")
                params[key] = value

        if not set_clauses:
            return await self.find_by_id(user_id)

        set_clause = ", ".join(set_clauses)
        query = f"""
        MATCH (u:User {{id: $user_id}})
        SET {set_clause}, u.updated_at = datetime()
        OPTIONAL MATCH (u)-[:HAS_ROLE]->(r:Role)
        RETURN u {{.*, roles: collect(r.name)}} AS user
        """
        results = await self._client.execute_query(query, params)
        if results:
            return results[0]["user"]
        return None

    async def list_users(self, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        """사용자 목록 조회"""
        query = """
        MATCH (u:User)
        OPTIONAL MATCH (u)-[:HAS_ROLE]->(r:Role)
        RETURN u {.*, roles: collect(r.name)} AS user
        ORDER BY u.username
        SKIP $skip LIMIT $limit
        """
        results = await self._client.execute_query(
            query, {"skip": skip, "limit": limit}
        )
        return [r["user"] for r in results]

    async def assign_role(self, user_id: str, role_name: str) -> bool:
        """사용자에게 역할 할당 (역할명은 소문자로 정규화)"""
        query = """
        MATCH (u:User {id: $user_id})
        MERGE (r:Role {name: $role_name})
        MERGE (u)-[:HAS_ROLE]->(r)
        RETURN u.id AS user_id
        """
        results = await self._client.execute_query(
            query, {"user_id": user_id, "role_name": role_name.lower()}
        )
        return len(results) > 0

    async def remove_role(self, user_id: str, role_name: str) -> bool:
        """사용자에서 역할 제거"""
        query = """
        MATCH (u:User {id: $user_id})-[rel:HAS_ROLE]->(r:Role {name: $role_name})
        DELETE rel
        RETURN u.id AS user_id
        """
        results = await self._client.execute_query(
            query, {"user_id": user_id, "role_name": role_name}
        )
        return len(results) > 0

    async def list_roles(self) -> list[str]:
        """모든 역할 목록"""
        query = "MATCH (r:Role) RETURN r.name AS name ORDER BY r.name"
        results = await self._client.execute_query(query, {})
        return [r["name"] for r in results]

    async def seed_default_roles(self) -> None:
        """기본 역할 시드 (멱등성 보장)"""
        query = """
        UNWIND $roles AS role_name
        MERGE (r:Role {name: role_name})
        RETURN count(r) AS count
        """
        await self._client.execute_query(
            query,
            {"roles": ["admin", "manager", "editor", "viewer"]},
        )
        logger.info("Default roles seeded")

    async def seed_admin_user(
        self, username: str, hashed_password: str
    ) -> dict[str, Any]:
        """기본 admin 사용자 시드 (멱등성 보장)"""
        query = """
        MERGE (u:User {username: $username})
        ON CREATE SET
            u.id = randomUUID(),
            u.hashed_password = $hashed_password,
            u.is_active = true,
            u.is_admin = true,
            u.created_at = datetime()
        ON MATCH SET
            u.updated_at = datetime()
        WITH u
        MERGE (r:Role {name: 'admin'})
        MERGE (u)-[:HAS_ROLE]->(r)
        RETURN u {.*, roles: ['admin']} AS user
        """
        results = await self._client.execute_query(
            query,
            {"username": username, "hashed_password": hashed_password},
        )
        logger.info(f"Admin user seeded: {username}")
        return results[0]["user"]
