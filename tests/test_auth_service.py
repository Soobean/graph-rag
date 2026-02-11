"""
AuthService 테스트
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.auth.jwt_handler import JWTHandler
from src.auth.password import PasswordHandler
from src.config import Settings
from src.domain.exceptions import AuthenticationError
from src.repositories.user_repository import UserRepository
from src.services.auth_service import AuthService


@pytest.fixture
def mock_settings():
    s = MagicMock(spec=Settings)
    s.jwt_secret_key = "test-secret"
    s.jwt_access_token_expire_minutes = 60
    s.jwt_refresh_token_expire_days = 7
    return s


@pytest.fixture
def password_handler():
    return PasswordHandler()


@pytest.fixture
def jwt_handler(mock_settings):
    return JWTHandler(mock_settings)


@pytest.fixture
def mock_user_repo():
    return MagicMock(spec=UserRepository)


@pytest.fixture
def auth_service(mock_user_repo, jwt_handler, password_handler, mock_settings):
    return AuthService(
        user_repository=mock_user_repo,
        jwt_handler=jwt_handler,
        password_handler=password_handler,
        settings=mock_settings,
    )


class TestLogin:
    async def test_login_success(self, auth_service, mock_user_repo, password_handler):
        hashed = password_handler.hash_password("password123")
        mock_user_repo.find_by_username = AsyncMock(
            return_value={
                "id": "u1",
                "username": "testuser",
                "hashed_password": hashed,
                "roles": ["viewer"],
                "is_active": True,
                "department": "개발",
            }
        )
        result = await auth_service.login("testuser", "password123")
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"

    async def test_login_user_not_found(self, auth_service, mock_user_repo):
        mock_user_repo.find_by_username = AsyncMock(return_value=None)
        with pytest.raises(AuthenticationError, match="Invalid username"):
            await auth_service.login("nonexistent", "password")

    async def test_login_wrong_password(
        self, auth_service, mock_user_repo, password_handler
    ):
        hashed = password_handler.hash_password("correct_password")
        mock_user_repo.find_by_username = AsyncMock(
            return_value={
                "id": "u1",
                "username": "testuser",
                "hashed_password": hashed,
                "roles": [],
                "is_active": True,
            }
        )
        with pytest.raises(AuthenticationError, match="Invalid username"):
            await auth_service.login("testuser", "wrong_password")

    async def test_login_disabled_account(
        self, auth_service, mock_user_repo, password_handler
    ):
        hashed = password_handler.hash_password("password123")
        mock_user_repo.find_by_username = AsyncMock(
            return_value={
                "id": "u1",
                "username": "testuser",
                "hashed_password": hashed,
                "roles": [],
                "is_active": False,
            }
        )
        with pytest.raises(AuthenticationError, match="disabled"):
            await auth_service.login("testuser", "password123")


class TestRefreshToken:
    async def test_refresh_success(
        self, auth_service, mock_user_repo, jwt_handler
    ):
        refresh = jwt_handler.create_refresh_token("u1")
        mock_user_repo.find_by_id = AsyncMock(
            return_value={
                "id": "u1",
                "username": "testuser",
                "roles": ["viewer"],
                "is_active": True,
                "department": None,
            }
        )
        result = await auth_service.refresh_token(refresh)
        assert "access_token" in result

    async def test_refresh_expired_token(self, auth_service):
        with pytest.raises(AuthenticationError, match="Invalid refresh token"):
            await auth_service.refresh_token("invalid.token.here")

    async def test_refresh_with_access_token_fails(
        self, auth_service, jwt_handler
    ):
        """access token으로 refresh 시도 → 실패"""
        access = jwt_handler.create_access_token(
            {"sub": "u1", "username": "test", "roles": []}
        )
        with pytest.raises(AuthenticationError, match="Invalid token type"):
            await auth_service.refresh_token(access)


class TestGetCurrentUser:
    async def test_get_user_from_token(self, auth_service, jwt_handler):
        token = jwt_handler.create_access_token(
            {
                "sub": "u1",
                "username": "testuser",
                "roles": ["viewer", "editor"],
                "department": "개발",
            }
        )
        user = await auth_service.get_current_user(token)
        assert user.user_id == "u1"
        assert user.username == "testuser"
        assert user.roles == ["viewer", "editor"]
        assert user.department == "개발"
        assert not user.is_admin

    async def test_admin_user_from_token(self, auth_service, jwt_handler):
        token = jwt_handler.create_access_token(
            {
                "sub": "u1",
                "username": "admin",
                "roles": ["admin"],
                "department": None,
            }
        )
        user = await auth_service.get_current_user(token)
        assert user.is_admin
        assert user.permissions == ["*"]

    async def test_invalid_token(self, auth_service):
        with pytest.raises(AuthenticationError, match="Invalid token"):
            await auth_service.get_current_user("bad_token")

    async def test_refresh_token_rejected(self, auth_service, jwt_handler):
        """refresh token으로 get_current_user 시도 → 실패"""
        refresh = jwt_handler.create_refresh_token("u1")
        with pytest.raises(AuthenticationError, match="Invalid token type"):
            await auth_service.get_current_user(refresh)


class TestCreateUser:
    async def test_create_success(self, auth_service, mock_user_repo):
        mock_user_repo.find_by_username = AsyncMock(return_value=None)
        mock_user_repo.create_user = AsyncMock(
            return_value={
                "id": "new-id",
                "username": "newuser",
                "roles": ["viewer"],
                "department": "마케팅",
            }
        )
        result = await auth_service.create_user(
            "newuser", "password", roles=["viewer"], department="마케팅"
        )
        assert result["username"] == "newuser"
        assert "hashed_password" not in result

    async def test_create_duplicate_username(self, auth_service, mock_user_repo):
        mock_user_repo.find_by_username = AsyncMock(
            return_value={"id": "u1", "username": "existing"}
        )
        with pytest.raises(AuthenticationError, match="already exists"):
            await auth_service.create_user("existing", "password")


class TestListUsers:
    async def test_list_hides_password(self, auth_service, mock_user_repo):
        mock_user_repo.list_users = AsyncMock(
            return_value=[
                {"id": "u1", "username": "a", "hashed_password": "hash1", "roles": []},
                {"id": "u2", "username": "b", "hashed_password": "hash2", "roles": []},
            ]
        )
        result = await auth_service.list_users()
        assert len(result) == 2
        for u in result:
            assert "hashed_password" not in u
