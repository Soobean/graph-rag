"""
인증 의존성 테스트 (Phase 3-E)

get_current_user() FastAPI 의존성의 동작을 검증합니다.
- AUTH_ENABLED=false → anonymous_admin
- AUTH_ENABLED=true → Bearer 토큰 → UserContext
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.auth.models import UserContext
from src.dependencies import get_current_user
from src.domain.exceptions import AuthenticationError


def _mock_request(auth_header: str | None = None, auth_service: object | None = None):
    """테스트용 Request mock"""
    request = MagicMock()
    headers = {}
    if auth_header is not None:
        headers["Authorization"] = auth_header
    request.headers = headers
    if auth_service is not None:
        request.app.state.auth_service = auth_service
    return request


class TestGetCurrentUserAuthDisabled:
    """AUTH_ENABLED=false (기본값) → anonymous_admin"""

    @pytest.mark.asyncio
    async def test_returns_anonymous_admin(self):
        """인증 비활성 시 anonymous_admin 반환"""
        mock_settings = MagicMock()
        mock_settings.auth_enabled = False
        request = _mock_request()

        with patch("src.dependencies.get_settings", return_value=mock_settings):
            user = await get_current_user(request)

        assert user.is_admin is True
        assert user.username == "anonymous_admin"
        assert user.roles == ["admin"]

    @pytest.mark.asyncio
    async def test_no_token_required(self):
        """인증 비활성 시 토큰 없어도 정상"""
        mock_settings = MagicMock()
        mock_settings.auth_enabled = False
        request = _mock_request()  # Authorization 헤더 없음

        with patch("src.dependencies.get_settings", return_value=mock_settings):
            user = await get_current_user(request)

        assert user.is_admin is True


class TestGetCurrentUserAuthEnabled:
    """AUTH_ENABLED=true → JWT 토큰 검증"""

    @pytest.fixture
    def settings(self):
        s = MagicMock()
        s.auth_enabled = True
        return s

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, settings):
        """유효한 Bearer 토큰 → UserContext 반환"""
        expected_user = UserContext(
            user_id="user-1",
            username="홍길동",
            roles=["viewer"],
            permissions=["query:*/search"],
            is_admin=False,
            department="백엔드개발팀",
        )
        auth_service = MagicMock()
        auth_service.get_current_user = AsyncMock(return_value=expected_user)

        request = _mock_request(
            auth_header="Bearer valid-token-123",
            auth_service=auth_service,
        )

        with patch("src.dependencies.get_settings", return_value=settings):
            user = await get_current_user(request)

        assert user.username == "홍길동"
        assert user.department == "백엔드개발팀"
        auth_service.get_current_user.assert_called_once_with("valid-token-123")

    @pytest.mark.asyncio
    async def test_missing_auth_header_raises(self, settings):
        """Authorization 헤더 없음 → AuthenticationError"""
        request = _mock_request()  # 헤더 없음

        with patch("src.dependencies.get_settings", return_value=settings):
            with pytest.raises(AuthenticationError, match="Missing"):
                await get_current_user(request)

    @pytest.mark.asyncio
    async def test_invalid_scheme_raises(self, settings):
        """Bearer가 아닌 스킴 → AuthenticationError"""
        request = _mock_request(auth_header="Basic dXNlcjpwYXNz")

        with patch("src.dependencies.get_settings", return_value=settings):
            with pytest.raises(AuthenticationError, match="Missing"):
                await get_current_user(request)

    @pytest.mark.asyncio
    async def test_empty_token_raises(self, settings):
        """Bearer 뒤에 빈 토큰 → AuthenticationError"""
        request = _mock_request(auth_header="Bearer ")

        with patch("src.dependencies.get_settings", return_value=settings):
            with pytest.raises(AuthenticationError, match="Empty"):
                await get_current_user(request)

    @pytest.mark.asyncio
    async def test_expired_token_raises(self, settings):
        """만료된 토큰 → AuthService가 AuthenticationError 발생"""
        auth_service = MagicMock()
        auth_service.get_current_user = AsyncMock(
            side_effect=AuthenticationError("Token expired"),
        )

        request = _mock_request(
            auth_header="Bearer expired-token",
            auth_service=auth_service,
        )

        with patch("src.dependencies.get_settings", return_value=settings):
            with pytest.raises(AuthenticationError, match="expired"):
                await get_current_user(request)

    @pytest.mark.asyncio
    async def test_token_whitespace_stripped(self, settings):
        """토큰 앞뒤 공백은 그대로 전달 (AuthService가 처리)"""
        auth_service = MagicMock()
        auth_service.get_current_user = AsyncMock(
            return_value=UserContext(
                user_id="u1",
                username="test",
                roles=["viewer"],
                permissions=[],
                is_admin=False,
            ),
        )

        request = _mock_request(
            auth_header="Bearer  token-with-space",
            auth_service=auth_service,
        )

        with patch("src.dependencies.get_settings", return_value=settings):
            await get_current_user(request)

        # "Bearer " (7자) 이후 전체가 토큰으로 전달됨
        auth_service.get_current_user.assert_called_once_with(" token-with-space")
