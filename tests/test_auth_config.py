"""
Auth Config 테스트

Settings의 auth 관련 필드 기본값 및 프로덕션 검증을 테스트합니다.
"""

import logging

import pytest
from pydantic import ValidationError

from src.config import Settings


class TestAuthConfigDefaults:
    """auth 설정 기본값 검증"""

    def test_auth_disabled_by_default(self):
        """AUTH_ENABLED 기본값은 False"""
        settings = Settings(
            environment="development",
            neo4j_password="test",
        )
        assert settings.auth_enabled is False

    def test_jwt_secret_key_has_default(self):
        """JWT_SECRET_KEY에 개발용 기본값 존재"""
        settings = Settings(
            environment="development",
            neo4j_password="test",
        )
        assert settings.jwt_secret_key.startswith("dev-insecure")

    def test_jwt_access_token_expire_default(self):
        """JWT 액세스 토큰 만료 기본값 = 60분"""
        settings = Settings(
            environment="development",
            neo4j_password="test",
        )
        assert settings.jwt_access_token_expire_minutes == 60

    def test_jwt_refresh_token_expire_default(self):
        """JWT 리프레시 토큰 만료 기본값 = 7일"""
        settings = Settings(
            environment="development",
            neo4j_password="test",
        )
        assert settings.jwt_refresh_token_expire_days == 7

    def test_graph_edit_require_auth_default(self):
        """그래프 편집 인증 필수 기본값 = True"""
        settings = Settings(
            environment="development",
            neo4j_password="test",
        )
        assert settings.graph_edit_require_auth is True


class TestAuthProductionValidation:
    """프로덕션 환경 auth 설정 검증"""

    def test_production_blocks_insecure_jwt_secret(self):
        """프로덕션 + auth_enabled=True에서 기본 JWT 시크릿 키 사용 시 에러"""
        with pytest.raises(ValidationError, match="jwt_secret_key"):
            Settings(
                environment="production",
                neo4j_password="prod-pw",
                azure_openai_endpoint="https://test.openai.azure.com/",
                auth_enabled=True,
                jwt_secret_key="dev-insecure-secret-key-change-in-production",
            )

    def test_production_allows_strong_secret(self):
        """프로덕션에서 강력한 JWT 시크릿 키 사용 시 정상 생성"""
        settings = Settings(
            environment="production",
            neo4j_password="prod-pw",
            azure_openai_endpoint="https://test.openai.azure.com/",
            auth_enabled=True,
            jwt_secret_key="a-very-strong-and-random-production-secret-key-2024",
        )
        assert settings.is_production is True

    def test_production_warns_auth_disabled(self, caplog):
        """프로덕션에서 auth_enabled=False면 경고 (차단은 아님)"""
        with caplog.at_level(logging.WARNING):
            settings = Settings(
                environment="production",
                neo4j_password="prod-pw",
                azure_openai_endpoint="https://test.openai.azure.com/",
                auth_enabled=False,
            )
        assert settings.is_production is True
        assert "AUTH_ENABLED" in caplog.text

    def test_production_no_jwt_check_when_auth_disabled(self):
        """auth_enabled=False면 JWT secret 검사 스킵"""
        settings = Settings(
            environment="production",
            neo4j_password="prod-pw",
            azure_openai_endpoint="https://test.openai.azure.com/",
            auth_enabled=False,
            jwt_secret_key="dev-insecure-secret-key-change-in-production",
        )
        assert settings.auth_enabled is False
