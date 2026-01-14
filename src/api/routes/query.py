"""
Query API Routes

질의 관련 API 엔드포인트
- Explainability: 추론 과정 시각화 및 그래프 데이터 반환 지원
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemas import (
    HealthResponse,
    QueryMetadata,
    QueryRequest,
    QueryResponse,
    SchemaResponse,
)
from src.api.schemas.explainability import ExplainableResponse
from src.config import Settings, get_settings
from src.dependencies import get_graph_pipeline, get_neo4j_client
from src.domain.exceptions import (
    DatabaseConnectionError,
    EntityNotFoundError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
)
from src.domain.exceptions import (
    ValidationError as DomainValidationError,
)
from src.graph import GraphRAGPipeline
from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


# ============================================
# API 엔드포인트
# ============================================


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    pipeline: Annotated[GraphRAGPipeline, Depends(get_graph_pipeline)],
) -> QueryResponse:
    """
    그래프 RAG 질의

    사용자의 자연어 질문을 받아 그래프 데이터베이스에서 정보를 검색하고
    자연어 응답을 생성합니다.

    Explainability 옵션:
    - include_explanation: 추론 과정 포함 (사고 과정 시각화)
    - include_graph: 그래프 데이터 포함 (인터랙티브 그래프용)
    - graph_limit: 그래프 최대 노드 수 (1-200)
    """
    logger.info(f"Query request: {request.question[:50]}...")

    try:
        # Explainability 요청 시 full_state 포함
        return_full_state = request.include_explanation or request.include_graph

        result = await pipeline.run(
            question=request.question,
            session_id=request.session_id,
            return_full_state=return_full_state,
        )

        # 기본 메타데이터 구축
        metadata = None
        explanation = None
        raw_metadata = result.get("metadata", {})

        if raw_metadata:
            # _full_state 제외한 메타데이터
            clean_metadata = {
                k: v for k, v in raw_metadata.items() if not k.startswith("_")
            }
            metadata = QueryMetadata(**clean_metadata)

            # Explainability 데이터 구축
            if return_full_state:
                full_state = raw_metadata.get("_full_state")

                thought_process = None
                graph_data = None

                # 서비스 인스턴스 생성 (필요하다면 의존성 주입으로 변경 가능)
                from src.api.services.explainability import ExplainabilityService

                service = ExplainabilityService()

                if request.include_explanation:
                    thought_process = service.build_thought_process(
                        raw_metadata, full_state
                    )

                if request.include_graph and full_state:
                    graph_data = service.build_graph_data(
                        full_state=full_state,
                        resolved_entities=raw_metadata.get("resolved_entities", []),
                        limit=request.graph_limit,
                    )

                if thought_process or graph_data:
                    explanation = ExplainableResponse(
                        thought_process=thought_process,
                        graph_data=graph_data,
                    )

        return QueryResponse(
            success=result["success"],
            question=result["question"],
            response=result["response"],
            metadata=metadata,
            error=result.get("error"),
            explanation=explanation,
        )

    except LLMRateLimitError as e:
        logger.warning(f"Rate limit exceeded: {e}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
            headers={"Retry-After": str(e.retry_after)} if e.retry_after else None,
        ) from e

    except LLMConnectionError as e:
        logger.error(f"LLM connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM service unavailable: {e}",
        ) from e

    except LLMResponseError as e:
        logger.error(f"LLM response error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM response error: {e}",
        ) from e

    except DatabaseConnectionError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {e}",
        ) from e

    except DomainValidationError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    except EntityNotFoundError as e:
        logger.info(f"Entity not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
    neo4j_client: Annotated[Neo4jClient, Depends(get_neo4j_client)],
) -> HealthResponse:
    """
    헬스체크

    서비스 및 Neo4j 연결 상태를 확인합니다.
    """
    health_info = await neo4j_client.health_check()

    return HealthResponse(
        status="healthy" if health_info["connected"] else "degraded",
        version=settings.app_version,
        neo4j_connected=health_info["connected"],
        neo4j_info=health_info.get("server_info"),
    )


@router.get("/schema", response_model=SchemaResponse)
async def schema(
    neo4j_client: Annotated[Neo4jClient, Depends(get_neo4j_client)],
) -> SchemaResponse:
    """
    그래프 스키마 조회

    데이터베이스의 노드 레이블, 관계 타입, 인덱스 정보를 반환합니다.
    """
    schema_info = await neo4j_client.get_schema_info()

    return SchemaResponse(
        node_labels=schema_info.get("node_labels", []),
        relationship_types=schema_info.get("relationship_types", []),
        indexes=schema_info.get("indexes", []),
        constraints=schema_info.get("constraints", []),
    )
