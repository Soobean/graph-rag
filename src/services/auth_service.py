"""
Auth Service — 인증/인가 비즈니스 로직

로그인, 토큰 갱신, 사용자 조회/관리를 처리합니다.
"""

import logging
import uuid
from typing import Any

import jwt
from neo4j.exceptions import ConstraintError

from src.auth.jwt_handler import JWTHandler
from src.auth.models import UserContext, permissions_for_roles
from src.auth.password import PasswordHandler
from src.config import Settings
from src.domain.exceptions import AuthenticationError
from src.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    """인증/인가 서비스"""

    def __init__(
        self,
        user_repository: UserRepository,
        jwt_handler: JWTHandler,
        password_handler: PasswordHandler,
        settings: Settings,
    ):
        self._users = user_repository
        self._jwt = jwt_handler
        self._password = password_handler
        self._settings = settings

    async def login(self, username: str, password: str) -> dict[str, str]:
        """
        로그인 처리

        Returns:
            {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

        Raises:
            AuthenticationError: 인증 실패
        """
        user = await self._users.find_by_username(username)
        if not user:
            raise AuthenticationError("Invalid username or password")

        if not user.get("is_active", True):
            raise AuthenticationError("Account is disabled")

        stored_hash = user.get("hashed_password", "")
        if not stored_hash or not self._password.verify_password(password, stored_hash):
            raise AuthenticationError("Invalid username or password")

        roles = user.get("roles", [])
        user_id = user.get("id", "")

        access_token = self._jwt.create_access_token(
            {
                "sub": user_id,
                "username": user.get("username", ""),
                "roles": roles,
                "department": user.get("department"),
            }
        )
        refresh_token = self._jwt.create_refresh_token(user_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def refresh_token(self, refresh_token: str) -> dict[str, str]:
        """
        리프레시 토큰으로 새 액세스 토큰 발급

        Raises:
            AuthenticationError: 토큰이 유효하지 않거나 사용자를 찾을 수 없음
        """
        try:
            payload = self._jwt.decode_token(refresh_token)
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Refresh token expired") from None
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid refresh token") from None

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        user_id = payload.get("sub", "")
        if not user_id:
            raise AuthenticationError("Invalid refresh token")

        user = await self._users.find_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found")

        if not user.get("is_active", True):
            raise AuthenticationError("Account is disabled")

        roles = user.get("roles", [])
        access_token = self._jwt.create_access_token(
            {
                "sub": user_id,
                "username": user.get("username", ""),
                "roles": roles,
                "department": user.get("department"),
            }
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def get_current_user(self, token: str) -> UserContext:
        """
        액세스 토큰에서 UserContext 생성

        Raises:
            AuthenticationError: 토큰 검증 실패
        """
        try:
            payload = self._jwt.decode_token(token)
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired") from None
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token") from None

        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")

        user_id = payload.get("sub", "")
        username = payload.get("username", "")
        roles = payload.get("roles", [])
        department = payload.get("department")

        is_admin = "admin" in roles
        permissions = ["*"] if is_admin else permissions_for_roles(roles)

        return UserContext(
            user_id=user_id,
            username=username,
            roles=roles,
            permissions=permissions,
            is_admin=is_admin,
            department=department,
        )

    async def create_user(
        self,
        username: str,
        password: str,
        roles: list[str] | None = None,
        department: str | None = None,
    ) -> dict[str, Any]:
        """사용자 생성"""
        existing = await self._users.find_by_username(username)
        if existing:
            raise AuthenticationError(f"Username '{username}' already exists")

        hashed = self._password.hash_password(password)
        user_id = str(uuid.uuid4())
        try:
            user = await self._users.create_user(
                user_id=user_id,
                username=username,
                hashed_password=hashed,
                roles=roles,
                department=department,
            )
        except ConstraintError:
            raise AuthenticationError(f"Username '{username}' already exists") from None
        # hashed_password 제거 후 반환
        user.pop("hashed_password", None)
        return user

    async def update_user(
        self, user_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """사용자 업데이트"""
        safe_updates = updates.copy()
        if "password" in safe_updates:
            password = safe_updates.pop("password")
            safe_updates["hashed_password"] = self._password.hash_password(password)

        user = await self._users.update_user(user_id, safe_updates)
        if user:
            user.pop("hashed_password", None)
        return user

    async def list_users(self, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        """사용자 목록"""
        users = await self._users.list_users(skip=skip, limit=limit)
        for u in users:
            u.pop("hashed_password", None)
        return users

    async def list_roles(self) -> list[str]:
        """역할 목록"""
        return await self._users.list_roles()
