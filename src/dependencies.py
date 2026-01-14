"""
FastAPI 의존성 주입 모듈

FastAPI의 Depends 패턴을 활용한 의존성 주입을 관리합니다.
- lru_cache를 통한 싱글톤 관리
- 레이어별 의존성 계층 구조
- 테스트 시 의존성 오버라이드 지원

의존성 흐름:
    Settings -> Infrastructure Clients -> Repositories -> Pipeline
"""

import logging

from fastapi import Request

from src.config import Settings, get_settings
from src.graph.pipeline import GraphRAGPipeline
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.gds_service import GDSService

logger = logging.getLogger(__name__)


# ============================================
# Infrastructure Layer 의존성
# ============================================


def get_neo4j_client(request: Request) -> Neo4jClient:
    """
    Neo4j 클라이언트 의존성 주입

    main.py lifespan에서 초기화된 app.state.neo4j_client를 반환합니다.
    """
    return request.app.state.neo4j_client


# ============================================
# Repository Layer 의존성
# ============================================


def get_neo4j_repository(request: Request) -> Neo4jRepository:
    """
    Neo4j Repository 의존성 주입

    app.state.neo4j_client를 사용해 경량 래퍼 인스턴스 생성
    """
    client = request.app.state.neo4j_client
    return Neo4jRepository(client)


def get_llm_repository(request: Request) -> LLMRepository:
    """
    LLM Repository 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.llm_repo


# ============================================
# Graph Pipeline 의존성
# ============================================


def get_graph_pipeline(request: Request) -> GraphRAGPipeline:
    """
    GraphRAG Pipeline 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.pipeline


# ============================================
# 유틸리티 의존성
# ============================================


def get_current_settings() -> Settings:
    """현재 설정 반환 (Depends 래퍼)"""
    return get_settings()


# ============================================
# GDS Service 의존성
# ============================================


def get_gds_service(request: Request) -> GDSService:
    """
    GDS Service 의존성 주입
    app.state에서 초기화된 인스턴스를 가져옵니다.
    """
    return request.app.state.gds_service
