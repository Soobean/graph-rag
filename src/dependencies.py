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
from collections.abc import AsyncIterator

from fastapi import Depends, Request

from src.config import Settings, get_settings
from src.graph.pipeline import GraphRAGPipeline
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.gds_service import GDSService

logger = logging.getLogger(__name__)


# ============================================
# 전역 상태 (애플리케이션 라이프사이클 관리)
# ============================================

# 싱글톤 클라이언트 인스턴스 저장소
_neo4j_client: Neo4jClient | None = None


# ============================================
# Infrastructure Layer 의존성
# ============================================


def _create_neo4j_client(settings: Settings) -> Neo4jClient:
    """
    Neo4j 클라이언트 인스턴스 생성

    내부 헬퍼 함수로, 설정값을 기반으로 클라이언트를 생성합니다.
    """
    return Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
        max_connection_pool_size=settings.neo4j_max_connection_pool_size,
        connection_timeout=settings.neo4j_connection_timeout,
    )


async def get_neo4j_client(
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[Neo4jClient]:
    """
    Neo4j 클라이언트 의존성 주입

    FastAPI의 lifespan 이벤트와 연계하여 사용됩니다.
    요청 범위에서 연결된 클라이언트를 제공합니다.
    """
    global _neo4j_client

    if _neo4j_client is None:
        _neo4j_client = _create_neo4j_client(settings)
        await _neo4j_client.connect()
        logger.info("Neo4j client initialized via dependency injection")

    yield _neo4j_client


# ============================================
# 라이프사이클 관리 함수
# ============================================


async def startup_clients() -> None:
    """
    애플리케이션 시작 시 클라이언트 초기화
    FastAPI lifespan 이벤트에서 호출됩니다.
    """
    global _neo4j_client

    settings = get_settings()

    # Neo4j 클라이언트 초기화
    _neo4j_client = _create_neo4j_client(settings)
    await _neo4j_client.connect()
    logger.info("All infrastructure clients initialized")

    # Health check
    health = await _neo4j_client.health_check()
    if health["connected"]:
        logger.info(f"Neo4j connected: {health['server_info']}")
    else:
        logger.warning(f"Neo4j health check failed: {health['error']}")


async def shutdown_clients() -> None:
    """
    애플리케이션 종료 시 클라이언트 정리
    """
    global _neo4j_client

    if _neo4j_client is not None:
        await _neo4j_client.close()
        _neo4j_client = None
        logger.info("Neo4j client closed")

    logger.info("All infrastructure clients shut down")


# ============================================
# Repository Layer 의존성
# ============================================


def get_neo4j_repository(request: Request) -> Neo4jRepository:
    """
    Neo4j Repository 의존성 주입
    main.py lifespan에서 초기화된 인스턴스를 app.state에서 가져옵니다.
    """
    # Neo4jRepository는 client를 인자로 받지만, lifespan에서 이미 생성됨.
    # main.py에서 app.state.neo4j_repo로 저장하거나,
    # 여기서는 임시로 client를 가져와서 생성할 수도 있지만,
    # Singleton 유지를 위해 app.state에 저장된 것을 가져오는 것이 좋음.
    # main.py를 확인해보면 현재는 app.state.neo4j_client만 저장하고 있음. Wait, let me check main.py again.
    # Checked main.py: It initializes neo4j_repo but DOES NOT save it to app.state.
    # It saves: app.state.neo4j_client, app.state.llm_repo, app.state.pipeline.
    # So for Neo4jRepository, we can either instantiate it here using the client from state,
    # or update main.py to save it. Instantiating here is fine as it's lightweight wrapper.

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
