"""
JWTHandler 테스트

토큰 생성, 디코딩, 만료 검증을 테스트합니다.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import jwt
import pytest

from src.auth.jwt_handler import JWTHandler
from src.config import Settings


@pytest.fixture
def jwt_settings():
    """JWT 테스트용 설정"""
    settings = MagicMock(spec=Settings)
    settings.jwt_secret_key = "test-secret-key-for-unit-tests"
    settings.jwt_access_token_expire_minutes = 60
    settings.jwt_refresh_token_expire_days = 7
    return settings


@pytest.fixture
def handler(jwt_settings):
    """JWTHandler 인스턴스"""
    return JWTHandler(jwt_settings)


class TestCreateAccessToken:
    """액세스 토큰 생성 테스트"""

    def test_create_access_token_returns_string(self, handler):
        """토큰은 문자열"""
        token = handler.create_access_token({"sub": "user1"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_token_contains_payload(self, handler):
        """토큰에 페이로드 데이터 포함"""
        token = handler.create_access_token({
            "sub": "user1",
            "roles": ["admin"],
        })
        decoded = handler.decode_token(token)
        assert decoded["sub"] == "user1"
        assert decoded["roles"] == ["admin"]

    def test_access_token_has_type_field(self, handler):
        """액세스 토큰의 type 필드 = "access" """
        token = handler.create_access_token({"sub": "user1"})
        decoded = handler.decode_token(token)
        assert decoded["type"] == "access"

    def test_access_token_has_expiration(self, handler):
        """액세스 토큰에 만료 시간 포함"""
        token = handler.create_access_token({"sub": "user1"})
        decoded = handler.decode_token(token)
        assert "exp" in decoded


class TestCreateRefreshToken:
    """리프레시 토큰 생성 테스트"""

    def test_refresh_token_returns_string(self, handler):
        """토큰은 문자열"""
        token = handler.create_refresh_token("user1")
        assert isinstance(token, str)

    def test_refresh_token_has_type_field(self, handler):
        """리프레시 토큰의 type 필드 = "refresh" """
        token = handler.create_refresh_token("user1")
        decoded = handler.decode_token(token)
        assert decoded["type"] == "refresh"
        assert decoded["sub"] == "user1"

    def test_refresh_token_has_longer_expiration(self, handler):
        """리프레시 토큰은 액세스 토큰보다 만료가 김"""
        access = handler.create_access_token({"sub": "user1"})
        refresh = handler.create_refresh_token("user1")

        access_decoded = handler.decode_token(access)
        refresh_decoded = handler.decode_token(refresh)

        assert refresh_decoded["exp"] > access_decoded["exp"]


class TestDecodeToken:
    """토큰 디코딩 테스트"""

    def test_decode_valid_token(self, handler):
        """유효한 토큰 디코딩 성공"""
        token = handler.create_access_token({"sub": "user1"})
        decoded = handler.decode_token(token)
        assert decoded["sub"] == "user1"

    def test_decode_expired_token_raises(self, jwt_settings):
        """만료된 토큰 디코딩 시 ExpiredSignatureError"""
        jwt_settings.jwt_access_token_expire_minutes = -1  # 즉시 만료
        handler = JWTHandler(jwt_settings)

        # 과거 시간으로 직접 토큰 생성
        payload = {
            "sub": "user1",
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(
            payload, jwt_settings.jwt_secret_key, algorithm="HS256"
        )

        with pytest.raises(jwt.ExpiredSignatureError):
            handler.decode_token(token)

    def test_decode_invalid_token_raises(self, handler):
        """유효하지 않은 토큰 디코딩 시 InvalidTokenError"""
        with pytest.raises(jwt.InvalidTokenError):
            handler.decode_token("invalid.token.string")

    def test_decode_token_with_wrong_secret_raises(self, handler):
        """다른 시크릿 키로 서명된 토큰은 거부"""
        # 다른 키로 서명된 토큰
        token = jwt.encode(
            {"sub": "user1", "exp": datetime.now(UTC) + timedelta(hours=1)},
            "different-secret",
            algorithm="HS256",
        )
        with pytest.raises(jwt.InvalidSignatureError):
            handler.decode_token(token)
