"""
Graph RAG API

FastAPI 애플리케이션 진입점
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import query_router
from src.config import get_settings
from src.graph import GraphRAGPipeline
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories import LLMRepository, Neo4jRepository

# 로깅 설정
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format=settings.log_format,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    애플리케이션 라이프사이클 관리

    시작 시: Neo4j 연결, Pipeline 초기화
    종료 시: 리소스 정리
    """
    logger.info("Starting Graph RAG API...")

    # Neo4j 클라이언트 초기화
    neo4j_client = Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
        max_connection_pool_size=settings.neo4j_max_connection_pool_size,
        connection_timeout=settings.neo4j_connection_timeout,
    )
    await neo4j_client.connect()
    logger.info("Neo4j client connected")

    # Repository 초기화
    neo4j_repo = Neo4jRepository(neo4j_client)
    llm_repo = LLMRepository(settings)

    # Pipeline 초기화
    pipeline = GraphRAGPipeline(settings, neo4j_repo, llm_repo)
    logger.info("Pipeline initialized")

    # app.state에 저장 (멀티 워커 환경에서 각 워커가 자체 인스턴스 보유)
    app.state.neo4j_client = neo4j_client
    app.state.llm_repo = llm_repo
    app.state.pipeline = pipeline

    yield

    # 종료 시 리소스 정리
    logger.info("Shutting down Graph RAG API...")

    if hasattr(app.state, "llm_repo") and app.state.llm_repo:
        await app.state.llm_repo.close()
        logger.info("LLM client closed")

    if hasattr(app.state, "neo4j_client") and app.state.neo4j_client:
        await app.state.neo4j_client.close()
        logger.info("Neo4j connection closed")


# FastAPI 앱 생성
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Neo4j 그래프 데이터베이스와 Azure OpenAI를 활용한 RAG 시스템",
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(query_router)


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
    )
