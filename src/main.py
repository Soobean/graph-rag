"""
Graph RAG API

FastAPI 애플리케이션 진입점
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api import (
    analytics_router,
    graph_edit_router,
    ingest_router,
    ontology_admin_router,
    ontology_router,
    query_router,
    visualization_router,
)
from src.api.services.explainability import ExplainabilityService
from src.config import get_settings
from src.domain.exceptions import (
    ConflictError,
    EntityNotFoundError,
    GraphRAGError,
    InvalidStateError,
)
from src.domain.ontology.registry import OntologyRegistry
from src.graph import GraphRAGPipeline
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories import LLMRepository, Neo4jRepository
from src.services.gds_service import GDSService
from src.services.graph_edit_service import GraphEditService
from src.services.ontology_service import OntologyService
from src.services.skill_gap_service import SkillGapService

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

    # 스키마 사전 로드 (파이프라인에 주입)
    try:
        graph_schema = await neo4j_repo.get_schema()
        logger.info(
            f"Schema loaded: "
            f"{len(graph_schema.get('node_labels', []))} labels, "
            f"{len(graph_schema.get('relationship_types', []))} relationships"
        )
    except Exception as e:
        logger.error(f"Failed to load graph schema: {e}")
        # 리소스 정리 후 예외 발생
        await neo4j_client.close()
        logger.info("Neo4j connection closed due to schema loading failure")
        raise RuntimeError(
            "Schema loading is required for pipeline initialization"
        ) from e

    # OntologyRegistry 초기화 (Pipeline/OntologyService에 주입)
    ontology_registry = OntologyRegistry(
        neo4j_client=neo4j_client,
        settings=settings,
    )
    logger.info(f"OntologyRegistry initialized (mode={ontology_registry.mode})")

    # OntologyService 초기화 (Pipeline에 주입하여 사용자 주도 온톨로지 업데이트 지원)
    ontology_service = OntologyService(
        neo4j_repository=neo4j_repo,
        ontology_registry=ontology_registry,
    )
    logger.info("OntologyService initialized for Pipeline injection")

    # Pipeline 초기화 (스키마 + 온톨로지 로더 + 온톨로지 서비스 주입)
    pipeline = GraphRAGPipeline(
        settings=settings,
        neo4j_repository=neo4j_repo,
        llm_repository=llm_repo,
        neo4j_client=neo4j_client,
        graph_schema=graph_schema,
        ontology_loader=ontology_registry.get_loader(),
        ontology_registry=ontology_registry,
        ontology_service=ontology_service,
    )
    logger.info("Pipeline initialized with pre-loaded schema, ontology registry, and ontology service")

    # GDS 서비스 초기화
    gds_service = GDSService(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    await gds_service.connect()
    logger.info("GDS service connected")

    # OntologyService는 위에서 이미 초기화됨 (Pipeline과 app.state 모두에서 사용)

    # ExplainabilityService 초기화 (stateless 서비스)
    explainability_service = ExplainabilityService()
    logger.info("ExplainabilityService initialized")

    # GraphEditService 초기화
    graph_edit_service = GraphEditService(neo4j_repo)
    logger.info("GraphEditService initialized")

    # SkillGapService 초기화
    skill_gap_service = SkillGapService(neo4j_repo)
    logger.info("SkillGapService initialized")

    # app.state에 저장 (멀티 워커 환경에서 각 워커가 자체 인스턴스 보유)
    app.state.neo4j_client = neo4j_client
    app.state.neo4j_repo = neo4j_repo
    app.state.llm_repo = llm_repo
    app.state.pipeline = pipeline
    app.state.gds_service = gds_service
    app.state.ontology_service = ontology_service
    app.state.ontology_registry = ontology_registry
    app.state.explainability_service = explainability_service
    app.state.graph_edit_service = graph_edit_service
    app.state.skill_gap_service = skill_gap_service

    yield

    # 종료 시 리소스 정리
    logger.info("Shutting down Graph RAG API...")

    if hasattr(app.state, "gds_service") and app.state.gds_service:
        await app.state.gds_service.close()
        logger.info("GDS service closed")

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

# CORS 설정 (명시적 오리진 지정으로 보안 강화)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],  # DELETE 추가 (Graph Edit API)
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


# ============================================
# 글로벌 예외 핸들러
# ============================================


@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(
    request: Request, exc: EntityNotFoundError
) -> JSONResponse:
    """엔티티를 찾을 수 없을 때 404 응답"""
    return JSONResponse(
        status_code=404,
        content={"detail": {"message": exc.message, "code": exc.code}},
    )


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    """동시성 충돌 시 409 응답"""
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "message": exc.message,
                "code": exc.code,
                "expected_version": exc.expected_version,
                "current_version": exc.current_version,
            }
        },
    )


@app.exception_handler(InvalidStateError)
async def invalid_state_handler(
    request: Request, exc: InvalidStateError
) -> JSONResponse:
    """유효하지 않은 상태 전이 시 400 응답"""
    return JSONResponse(
        status_code=400,
        content={
            "detail": {
                "message": exc.message,
                "code": exc.code,
                "current_state": exc.current_state,
            }
        },
    )


@app.exception_handler(GraphRAGError)
async def graphrag_error_handler(
    request: Request, exc: GraphRAGError
) -> JSONResponse:
    """기타 도메인 예외 시 500 응답"""
    logger.error(f"GraphRAGError: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": {"message": exc.message, "code": exc.code}},
    )


# 라우터 등록
app.include_router(query_router)
app.include_router(ingest_router)
app.include_router(analytics_router)
app.include_router(visualization_router)
app.include_router(ontology_router)
app.include_router(ontology_admin_router)
app.include_router(graph_edit_router)

# Frontend 정적 파일 경로
FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

@app.get("/api/v1/health")
async def health_check():
    """헬스체크 엔드포인트"""
    return {"status": "healthy", "version": settings.app_version}


# Frontend 정적 파일 서빙 (프로덕션용)
if FRONTEND_DIR.exists():
    # assets 폴더 마운트 (JS, CSS, 이미지 등)
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    async def serve_index():
        """메인 페이지 - React index.html 반환"""
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        React SPA fallback

        - 정적 파일이 있으면 해당 파일 반환
        - 없으면 index.html 반환 (React Router가 처리)
        """
        # API 경로는 여기 도달하지 않음 (위에서 먼저 매칭)
        file_path = (FRONTEND_DIR / full_path).resolve()

        # Path Traversal 방지: FRONTEND_DIR 외부 접근 차단
        if not file_path.is_relative_to(FRONTEND_DIR.resolve()):
            return FileResponse(FRONTEND_DIR / "index.html")

        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")

else:
    # Frontend 빌드가 없을 때 (개발 환경)
    @app.get("/")
    async def root():
        """루트 엔드포인트 (API 전용 모드)"""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "note": "Frontend not built. Run 'npm run build' in frontend directory.",
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
    )
