"""
Config 단위 테스트

실행 방법:
    pytest tests/test_config.py -v
"""

import pytest
from pydantic import ValidationError

from src.config import Settings


class TestSettingsValidation:
    """Settings 유효성 검사 테스트"""

    def test_default_settings(self):
        """기본 설정 테스트"""
        settings = Settings(
            _env_file=None,  # .env 파일 무시
        )
        assert settings.app_name == "Graph RAG API"
        assert settings.environment == "development"
        assert settings.is_development is True
        assert settings.is_production is False

    def test_log_level_validation_valid(self):
        """유효한 로그 레벨 테스트"""
        for level in ["debug", "INFO", "Warning", "ERROR", "critical"]:
            settings = Settings(log_level=level, _env_file=None)
            assert settings.log_level == level.upper()

    def test_log_level_validation_invalid(self):
        """유효하지 않은 로그 레벨 테스트"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(log_level="INVALID", _env_file=None)
        assert "log_level" in str(exc_info.value)

    def test_environment_validation_valid(self):
        """유효한 환경 설정 테스트"""
        for env in ["development", "staging", "production", "test"]:
            # production은 필수 필드가 있어야 함
            if env == "production":
                settings = Settings(
                    environment=env,
                    neo4j_password="test",
                    azure_openai_endpoint="https://test.openai.azure.com",
                    _env_file=None,
                )
            else:
                settings = Settings(environment=env, _env_file=None)
            assert settings.environment == env

    def test_environment_validation_invalid(self):
        """유효하지 않은 환경 설정 테스트"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(environment="invalid_env", _env_file=None)
        assert "environment" in str(exc_info.value)

    def test_neo4j_pool_size_bounds(self):
        """Neo4j 풀 크기 경계 테스트"""
        # 최소값
        settings = Settings(neo4j_max_connection_pool_size=1, _env_file=None)
        assert settings.neo4j_max_connection_pool_size == 1

        # 최대값
        settings = Settings(neo4j_max_connection_pool_size=100, _env_file=None)
        assert settings.neo4j_max_connection_pool_size == 100

        # 범위 초과
        with pytest.raises(ValidationError):
            Settings(neo4j_max_connection_pool_size=0, _env_file=None)

        with pytest.raises(ValidationError):
            Settings(neo4j_max_connection_pool_size=101, _env_file=None)

    def test_llm_temperature_bounds(self):
        """LLM 온도 경계 테스트"""
        # 최소값
        settings = Settings(llm_temperature=0.0, _env_file=None)
        assert settings.llm_temperature == 0.0

        # 최대값
        settings = Settings(llm_temperature=2.0, _env_file=None)
        assert settings.llm_temperature == 2.0

        # 범위 초과
        with pytest.raises(ValidationError):
            Settings(llm_temperature=-0.1, _env_file=None)

        with pytest.raises(ValidationError):
            Settings(llm_temperature=2.1, _env_file=None)

    def test_llm_max_tokens_bounds(self):
        """LLM 최대 토큰 경계 테스트"""
        settings = Settings(llm_max_tokens=1, _env_file=None)
        assert settings.llm_max_tokens == 1

        settings = Settings(llm_max_tokens=16000, _env_file=None)
        assert settings.llm_max_tokens == 16000

        with pytest.raises(ValidationError):
            Settings(llm_max_tokens=0, _env_file=None)

        with pytest.raises(ValidationError):
            Settings(llm_max_tokens=16001, _env_file=None)


class TestProductionSettings:
    """프로덕션 환경 필수 설정 테스트"""

    def test_production_missing_neo4j_password(self):
        """프로덕션에서 neo4j_password 누락 시 에러"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                neo4j_password="",
                azure_openai_endpoint="https://test.openai.azure.com",
                _env_file=None,
            )
        assert "neo4j_password" in str(exc_info.value)

    def test_production_missing_azure_endpoint(self):
        """프로덕션에서 azure_openai_endpoint 누락 시 에러"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                neo4j_password="test",
                azure_openai_endpoint="",
                _env_file=None,
            )
        assert "azure_openai_endpoint" in str(exc_info.value)

    def test_production_valid_settings(self):
        """프로덕션 유효 설정 테스트"""
        settings = Settings(
            environment="production",
            neo4j_password="secure_password",
            azure_openai_endpoint="https://test.openai.azure.com",
            azure_openai_api_key="test_key",
            _env_file=None,
        )
        assert settings.is_production is True
        assert settings.neo4j_password == "secure_password"

    def test_development_allows_empty_credentials(self):
        """개발 환경에서 빈 자격증명 허용"""
        settings = Settings(
            environment="development",
            neo4j_password="",
            azure_openai_endpoint="",
            _env_file=None,
        )
        assert settings.is_development is True
        assert settings.neo4j_password == ""


class TestSettingsProperties:
    """Settings 속성 테스트"""

    def test_is_production_property(self):
        """is_production 속성 테스트"""
        prod_settings = Settings(
            environment="production",
            neo4j_password="test",
            azure_openai_endpoint="https://test.openai.azure.com",
            _env_file=None,
        )
        assert prod_settings.is_production is True
        assert prod_settings.is_development is False

    def test_is_development_property(self):
        """is_development 속성 테스트"""
        dev_settings = Settings(environment="development", _env_file=None)
        assert dev_settings.is_development is True
        assert dev_settings.is_production is False

    def test_staging_environment(self):
        """staging 환경 테스트"""
        settings = Settings(environment="staging", _env_file=None)
        assert settings.environment == "staging"
        assert settings.is_production is False
        assert settings.is_development is False
