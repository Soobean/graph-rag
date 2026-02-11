"""
UserRepository 테스트

Neo4j 의존성은 Mock으로 처리합니다.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.user_repository import UserRepository


@pytest.fixture
def mock_client():
    client = MagicMock(spec=Neo4jClient)
    client.execute_query = AsyncMock()
    return client


@pytest.fixture
def repo(mock_client):
    return UserRepository(mock_client)


class TestFindByUsername:
    async def test_found(self, repo, mock_client):
        mock_client.execute_query.return_value = [
            {"user": {"id": "u1", "username": "admin", "roles": ["admin"]}}
        ]
        result = await repo.find_by_username("admin")
        assert result is not None
        assert result["username"] == "admin"

    async def test_not_found(self, repo, mock_client):
        mock_client.execute_query.return_value = []
        result = await repo.find_by_username("nonexistent")
        assert result is None


class TestFindById:
    async def test_found(self, repo, mock_client):
        mock_client.execute_query.return_value = [
            {"user": {"id": "u1", "username": "test", "roles": ["viewer"]}}
        ]
        result = await repo.find_by_id("u1")
        assert result is not None
        assert result["id"] == "u1"

    async def test_not_found(self, repo, mock_client):
        mock_client.execute_query.return_value = []
        result = await repo.find_by_id("missing")
        assert result is None


class TestCreateUser:
    async def test_create_with_roles(self, repo, mock_client):
        mock_client.execute_query.return_value = [
            {
                "user": {
                    "id": "u1",
                    "username": "new_user",
                    "roles": ["editor"],
                    "department": "개발",
                }
            }
        ]
        result = await repo.create_user(
            user_id="u1",
            username="new_user",
            hashed_password="hashed",
            roles=["editor"],
            department="개발",
        )
        assert result["username"] == "new_user"
        assert result["roles"] == ["editor"]
        mock_client.execute_query.assert_called_once()


class TestUpdateUser:
    async def test_update_department(self, repo, mock_client):
        mock_client.execute_query.return_value = [
            {"user": {"id": "u1", "username": "test", "department": "마케팅", "roles": []}}
        ]
        result = await repo.update_user("u1", {"department": "마케팅"})
        assert result is not None
        assert result["department"] == "마케팅"

    async def test_empty_updates_returns_user(self, repo, mock_client):
        """변경사항 없으면 기존 사용자 반환"""
        mock_client.execute_query.return_value = [
            {"user": {"id": "u1", "username": "test", "roles": []}}
        ]
        result = await repo.update_user("u1", {"unknown_field": "value"})
        # find_by_id 호출됨
        assert result is not None


class TestListUsers:
    async def test_list(self, repo, mock_client):
        mock_client.execute_query.return_value = [
            {"user": {"id": "u1", "username": "a", "roles": []}},
            {"user": {"id": "u2", "username": "b", "roles": []}},
        ]
        result = await repo.list_users()
        assert len(result) == 2


class TestRoles:
    async def test_assign_role(self, repo, mock_client):
        mock_client.execute_query.return_value = [{"user_id": "u1"}]
        assert await repo.assign_role("u1", "editor")

    async def test_remove_role(self, repo, mock_client):
        mock_client.execute_query.return_value = [{"user_id": "u1"}]
        assert await repo.remove_role("u1", "viewer")

    async def test_list_roles(self, repo, mock_client):
        mock_client.execute_query.return_value = [
            {"name": "admin"},
            {"name": "viewer"},
        ]
        roles = await repo.list_roles()
        assert roles == ["admin", "viewer"]


class TestSeed:
    async def test_seed_default_roles(self, repo, mock_client):
        mock_client.execute_query.return_value = [{"count": 4}]
        await repo.seed_default_roles()
        mock_client.execute_query.assert_called_once()

    async def test_seed_admin_user(self, repo, mock_client):
        mock_client.execute_query.return_value = [
            {"user": {"id": "u1", "username": "admin", "roles": ["admin"]}}
        ]
        result = await repo.seed_admin_user("admin", "hashed")
        assert result["username"] == "admin"
