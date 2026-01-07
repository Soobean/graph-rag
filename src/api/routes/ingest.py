"""
Ingestion API Routes

데이터 적재 관련 API 엔드포인트 (비동기 Job 방식)
"""

import logging
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from src.api.job_store import JobStatus, job_store
from src.api.schemas import (
    IngestRequest,
    IngestResponse,
    IngestStats,
    IngestStatusResponse,
    SourceType,
)
from src.ingestion.loaders.csv_loader import CSVLoader
from src.ingestion.loaders.excel_loader import ExcelLoader
from src.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ingest"])


async def _run_ingestion_job(
    job_id: str,
    request: IngestRequest,
    file_path: Path,
) -> None:
    """
    백그라운드에서 실행되는 Ingestion 작업

    Args:
        job_id: 작업 ID
        request: 적재 요청
        file_path: 파일 경로
    """
    logger.info(f"[Job {job_id}] Starting ingestion...")

    job_store.update_job(job_id, status=JobStatus.RUNNING, progress=0.1)

    try:
        # 로더 생성
        if request.source_type == SourceType.CSV:
            loader = CSVLoader(file_path)
        else:  # EXCEL
            loader = ExcelLoader(
                file_path,
                sheet_name=request.sheet_name,
                header_row=request.header_row,
            )

        # 파이프라인 실행
        pipeline = IngestionPipeline(
            batch_size=request.batch_size,
            concurrency=request.concurrency,
        )

        start_time = time.time()
        job_store.update_job(job_id, progress=0.3)

        stats = await pipeline.run(loader)
        duration = time.time() - start_time

        # 완료 상태 업데이트
        job_store.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=1.0,
            total_nodes=stats["total_nodes"],
            total_edges=stats["total_edges"],
            failed_documents=stats["failed_docs"],
            duration_seconds=round(duration, 2),
        )

        logger.info(
            f"[Job {job_id}] Completed: {stats['total_nodes']} nodes, "
            f"{stats['total_edges']} edges in {duration:.2f}s"
        )

    except Exception as e:
        logger.error(f"[Job {job_id}] Failed: {e}")
        job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            error=str(e),
        )


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
) -> IngestResponse:
    """
    데이터 적재 (비동기)

    CSV 또는 Excel 파일을 읽어 LLM으로 그래프를 추출하고 Neo4j에 저장합니다.
    작업은 백그라운드에서 실행되며, job_id로 상태를 조회할 수 있습니다.

    Returns:
        job_id가 포함된 응답 (즉시 반환)
    """
    logger.info(f"Ingest request: {request.source_type} - {request.file_path}")

    # 파일 존재 여부 확인
    file_path = Path(request.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {request.file_path}",
        )

    # 파일 확장자 검증
    valid_extensions = {
        SourceType.CSV: [".csv"],
        SourceType.EXCEL: [".xlsx", ".xls"],
    }
    if file_path.suffix.lower() not in valid_extensions[request.source_type]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension for {request.source_type}: {file_path.suffix}",
        )

    # Job 생성
    job_id = job_store.create_job()
    logger.info(f"Created job: {job_id}")

    # 백그라운드 태스크 등록
    background_tasks.add_task(_run_ingestion_job, job_id, request, file_path)

    return IngestResponse(
        success=True,
        message=f"Ingestion job created. Use GET /api/v1/ingest/{job_id} to check status.",
        stats=IngestStats(
            total_documents=0,
            total_nodes=0,
            total_edges=0,
            failed_documents=0,
            duration_seconds=0.0,
        ),
        job_id=job_id,
    )


@router.get("/ingest/{job_id}", response_model=IngestStatusResponse)
async def get_ingest_status(job_id: str) -> IngestStatusResponse:
    """
    적재 작업 상태 조회

    Args:
        job_id: 작업 ID

    Returns:
        작업 상태 및 통계
    """
    job = job_store.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    return IngestStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        progress=job.progress,
        stats=IngestStats(
            total_documents=job.total_documents,
            total_nodes=job.total_nodes,
            total_edges=job.total_edges,
            failed_documents=job.failed_documents,
            duration_seconds=job.duration_seconds,
        ),
        error=job.error,
    )


@router.get("/ingest", response_model=list[IngestStatusResponse])
async def list_ingest_jobs(limit: int = 20) -> list[IngestStatusResponse]:
    """
    적재 작업 목록 조회

    Args:
        limit: 조회할 작업 수 (기본: 20)

    Returns:
        최근 작업 목록
    """
    jobs = job_store.list_jobs(limit=limit)

    return [
        IngestStatusResponse(
            job_id=job.job_id,
            status=job.status.value,
            progress=job.progress,
            stats=IngestStats(
                total_documents=job.total_documents,
                total_nodes=job.total_nodes,
                total_edges=job.total_edges,
                failed_documents=job.failed_documents,
                duration_seconds=job.duration_seconds,
            ),
            error=job.error,
        )
        for job in jobs
    ]
