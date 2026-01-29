"""
애플리케이션 설정 모듈

Pydantic Settings를 활용한 환경변수 기반 설정 관리
- 타입 검증 자동화
- .env 파일 지원
- 환경별 설정 분리
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 프로젝트 루트 디렉토리 (src/config.py 기준으로 한 단계 상위)
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class AdaptiveOntologySettings(BaseModel):
    """
    Adaptive Ontology 설정

    미해결 엔티티 학습 및 자동 승인 관련 설정
    """

    # 기본 설정
    enabled: bool = Field(
        default=False,
        description="Adaptive Ontology 기능 활성화 여부",
    )

    # 자동 승인 설정
    auto_approve_enabled: bool = Field(
        default=True,
        description="자동 승인 기능 활성화 여부",
    )
    auto_approve_confidence: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="자동 승인 최소 신뢰도 (0.0 ~ 1.0)",
    )
    auto_approve_min_frequency: int = Field(
        default=5,
        ge=1,
        description="자동 승인 최소 등장 빈도",
    )
    auto_approve_types: list[str] = Field(
        default=["NEW_SYNONYM"],
        description="자동 승인 허용 제안 유형 (NEW_CONCEPT, NEW_SYNONYM, NEW_RELATION)",
    )
    auto_approve_daily_limit: int = Field(
        default=20,
        ge=0,
        description="일일 자동 승인 최대 수 (0 = 무제한)",
    )

    # 용어 검증 설정
    min_term_length: int = Field(
        default=2,
        ge=1,
        description="최소 용어 길이",
    )
    max_term_length: int = Field(
        default=100,
        ge=1,
        description="최대 용어 길이",
    )

    # 분석 설정
    batch_size: int = Field(
        default=10,
        ge=1,
        le=50,
        description="LLM 분석 배치 크기",
    )
    analysis_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        description="LLM 분석 타임아웃 (초)",
    )

    @field_validator("auto_approve_types")
    @classmethod
    def validate_auto_approve_types(cls, v: list[str]) -> list[str]:
        """자동 승인 유형이 유효한 ProposalType 값인지 검증"""
        valid_types = {"NEW_CONCEPT", "NEW_SYNONYM", "NEW_RELATION"}
        invalid_types = set(v) - valid_types
        if invalid_types:
            raise ValueError(
                f"Invalid proposal types: {invalid_types}. "
                f"Valid types are: {valid_types}"
            )
        return v

    @model_validator(mode="after")
    def validate_term_length_range(self) -> "AdaptiveOntologySettings":
        """min_term_length가 max_term_length보다 크지 않은지 검증"""
        if self.min_term_length > self.max_term_length:
            raise ValueError(
                f"min_term_length ({self.min_term_length}) cannot be greater "
                f"than max_term_length ({self.max_term_length})"
            )
        return self


class Settings(BaseSettings):
    """
    애플리케이션 전역 설정

    환경변수 또는 .env 파일에서 값을 로드합니다.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ============================================
    # 애플리케이션 설정
    # ============================================
    app_name: str = Field(default="Graph RAG API", description="애플리케이션 이름")
    app_version: str = Field(default="0.1.0", description="애플리케이션 버전")
    debug: bool = Field(default=False, description="디버그 모드")
    environment: str = Field(default="development", description="실행 환경")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS 허용 오리진 목록 (프론트엔드 URL)",
    )

    # ============================================
    # Neo4j 설정
    # ============================================
    neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        description="Neo4j Bolt URI",
    )
    neo4j_user: str = Field(
        default="neo4j",
        description="Neo4j 사용자명",
    )
    neo4j_password: str = Field(
        default="",
        description="Neo4j 비밀번호",
    )
    neo4j_database: str = Field(
        default="neo4j",
        description="Neo4j 데이터베이스 이름",
    )
    neo4j_max_connection_pool_size: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Neo4j 커넥션 풀 최대 크기",
    )
    neo4j_connection_timeout: float = Field(
        default=30.0,
        ge=1.0,
        description="Neo4j 연결 타임아웃 (초)",
    )

    # ============================================
    # Azure OpenAI 설정 (모델 버전 비의존적)
    # ============================================
    azure_openai_endpoint: str = Field(
        default="",
        description="Azure OpenAI 엔드포인트 URL",
    )
    azure_openai_api_key: str | None = Field(
        default=None,
        description="Azure OpenAI API 키 (Managed Identity 사용 시 불필요)",
    )
    azure_openai_api_version: str = Field(
        default="2024-10-21",
        description="Azure OpenAI API 버전",
    )

    # 배포 이름 (특정 모델 버전이 아닌 Azure Portal 배포 이름)
    light_model_deployment: str = Field(
        default="gpt-4o-mini",
        description="가벼운 작업용 모델 배포명 (intent_classifier, entity_extractor)",
    )
    heavy_model_deployment: str = Field(
        default="gpt-4o",
        description="복잡한 작업용 모델 배포명 (cypher_generator, response_generator)",
    )

    # LLM 공통 파라미터
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="LLM 응답 온도",
    )
    llm_max_tokens: int = Field(
        default=2000,
        ge=1,
        le=16000,
        description="LLM 최대 토큰 수",
    )

    # ============================================
    # Azure OpenAI Embedding 설정
    # ============================================
    embedding_model_deployment: str = Field(
        default="text-embedding-3-small",
        description="Azure OpenAI embedding 모델 배포명",
    )
    embedding_dimensions: int = Field(
        default=1536,
        ge=256,
        le=3072,
        description="Embedding 벡터 차원",
    )

    # ============================================
    # Vector Search 설정
    # ============================================
    vector_similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Vector Search 유사도 임계값",
    )
    query_cache_ttl_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="질문-Cypher 캐시 TTL (시간)",
    )
    vector_search_enabled: bool = Field(
        default=True,
        description="Vector Search 기능 활성화 여부",
    )

    # ============================================
    # 온톨로지 설정
    # ============================================
    ontology_mode: Literal["yaml", "neo4j", "hybrid"] = Field(
        default="yaml",
        description="온톨로지 로더 모드 (yaml: YAML 파일, neo4j: Neo4j DB, hybrid: Neo4j 우선 + YAML 폴백)",
    )

    # ============================================
    # Adaptive Ontology 설정
    # ============================================
    adaptive_ontology: AdaptiveOntologySettings = Field(
        default_factory=AdaptiveOntologySettings,
        description="Adaptive Ontology 학습 설정",
    )

    @field_validator("ontology_mode")
    @classmethod
    def validate_ontology_mode(cls, v: str) -> str:
        """온톨로지 모드 유효성 검사"""
        valid_modes = {"yaml", "neo4j", "hybrid"}
        lower_v = v.lower()
        if lower_v not in valid_modes:
            raise ValueError(f"ontology_mode must be one of {valid_modes}")
        return lower_v

    # ============================================
    # 캐시 설정
    # ============================================
    cache_enabled: bool = Field(
        default=True,
        description="캐시 활성화 여부",
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        ge=0,
        description="기본 캐시 TTL (초)",
    )
    cache_max_size: int = Field(
        default=1000,
        ge=1,
        description="캐시 최대 항목 수",
    )

    # ============================================
    # 로깅 설정
    # ============================================
    log_level: str = Field(
        default="INFO",
        description="로깅 레벨",
    )
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="로그 포맷",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """로그 레벨 유효성 검사"""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return upper_v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """환경 유효성 검사"""
        valid_envs = {"development", "staging", "production", "test"}
        lower_v = v.lower()
        if lower_v not in valid_envs:
            raise ValueError(f"environment must be one of {valid_envs}")
        return lower_v

    @property
    def is_production(self) -> bool:
        """프로덕션 환경 여부"""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """개발 환경 여부"""
        return self.environment == "development"

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """
        프로덕션 환경 필수 설정 검증

        프로덕션 환경에서는 민감한 설정이 반드시 지정되어야 합니다.
        """
        if self.environment == "production":
            missing_fields = []

            if not self.neo4j_password:
                missing_fields.append("neo4j_password")

            if not self.azure_openai_endpoint:
                missing_fields.append("azure_openai_endpoint")

            # API 키는 Managed Identity 사용 시 불필요할 수 있으므로 경고만
            if not self.azure_openai_api_key:
                import logging
                logging.getLogger(__name__).warning(
                    "azure_openai_api_key is not set. "
                    "Ensure Managed Identity is configured for Azure OpenAI access."
                )

            if missing_fields:
                raise ValueError(
                    f"Production environment requires these settings: {', '.join(missing_fields)}"
                )

        return self


@lru_cache
def get_settings() -> Settings:
    """
    설정 싱글톤 인스턴스 반환

    lru_cache를 사용하여 애플리케이션 생명주기 동안
    단일 Settings 인스턴스를 유지합니다.
    """
    return Settings()
