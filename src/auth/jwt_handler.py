"""
JWT 토큰 생성 및 디코딩

Access Token / Refresh Token 이중 토큰 전략을 구현합니다.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from src.config import Settings


class JWTHandler:
    """JWT 생성/검증 핸들러"""

    ALGORITHM = "HS256"

    def __init__(self, settings: Settings):
        self._secret_key = settings.jwt_secret_key
        self._access_expire_minutes = settings.jwt_access_token_expire_minutes
        self._refresh_expire_days = settings.jwt_refresh_token_expire_days

    def create_access_token(self, payload: dict[str, Any]) -> str:
        """
        액세스 토큰 생성

        Args:
            payload: 토큰에 포함할 데이터 (user_id, roles 등)

        Returns:
            JWT 문자열
        """
        to_encode = payload.copy()
        expire = datetime.now(UTC) + timedelta(minutes=self._access_expire_minutes)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, self._secret_key, algorithm=self.ALGORITHM)

    def create_refresh_token(self, user_id: str) -> str:
        """
        리프레시 토큰 생성

        Args:
            user_id: 사용자 ID

        Returns:
            JWT 문자열
        """
        expire = datetime.now(UTC) + timedelta(days=self._refresh_expire_days)
        payload = {
            "sub": user_id,
            "exp": expire,
            "type": "refresh",
        }
        return jwt.encode(payload, self._secret_key, algorithm=self.ALGORITHM)

    def decode_token(self, token: str) -> dict[str, Any]:
        """
        토큰 디코딩 및 검증

        Args:
            token: JWT 문자열

        Returns:
            디코딩된 페이로드

        Raises:
            jwt.ExpiredSignatureError: 토큰 만료
            jwt.InvalidTokenError: 유효하지 않은 토큰
        """
        return jwt.decode(token, self._secret_key, algorithms=[self.ALGORITHM])
