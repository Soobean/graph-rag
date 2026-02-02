"""
Ingestion API Routes

데이터 적재 관련 API 엔드포인트 (비동기 Job 방식)
"""

import logging
import re
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from src.api.job_store import JobStatus, job_store
from src.api.schemas import (
    FileUploadResponse,
    IngestRequest,
    IngestResponse,
    IngestStats,
    IngestStatusResponse,
    SourceType,
)
from src.ingestion.loaders.base import BaseLoader
from src.ingestion.loaders.csv_loader import CSVLoader
from src.ingestion.loaders.excel_loader import ExcelLoader
from src.ingestion.pipeline import IngestionPipeline

# 업로드 파일 저장 디렉토리
UPLOAD_DIR = Path("/tmp/graph-rag-uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 허용되는 파일 확장자
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# 파일 크기 제한 (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024

logger = logging.getLogger(__name__)


def sanitize_filename(filename: str) -> str:
    """
    파일명에서 위험한 문자 제거 (Path Traversal 방지)

    Args:
        filename: 원본 파일명

    Returns:
        정규화된 안전한 파일명
    """
    # 경로 구분자 제거
    filename = filename.replace("/", "_").replace("\\", "_")
    # 위험한 문자 제거 (알파벳, 숫자, 한글, 언더스코어, 하이픈, 점만 허용)
    filename = re.sub(r"[^\w\s\-\.\uac00-\ud7af]", "", filename)
    # 연속된 점 제거 (.. 방지)
    filename = re.sub(r"\.{2,}", ".", filename)
    # 앞뒤 공백 및 점 제거
    filename = filename.strip(". ")
    # 최대 길이 제한
    if "." in filename:
        name, ext = filename.rsplit(".", 1)
        name = name[:100]
        return f"{name}.{ext}"
    return filename[:100]

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
        # 로더 생성 (BaseLoader 타입으로 명시하여 mypy 에러 방지)
        loader: BaseLoader
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
    finally:
        # Ingestion 완료/실패 후 업로드된 임시 파일 삭제
        if file_path.exists() and UPLOAD_DIR in file_path.parents:
            try:
                file_path.unlink()
                logger.info(f"[Job {job_id}] Deleted processed file: {file_path}")
            except Exception as cleanup_err:
                logger.warning(
                    f"[Job {job_id}] Failed to delete file {file_path}: {cleanup_err}"
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


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)) -> FileUploadResponse:
    """
    파일 업로드

    로컬 파일을 서버에 업로드하고, 저장된 경로를 반환합니다.
    이후 /ingest API에 해당 경로를 전달하여 적재를 시작할 수 있습니다.

    Args:
        file: 업로드할 파일 (CSV, Excel, 최대 100MB)

    Returns:
        업로드된 파일 정보 및 서버 경로
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # 파일 크기 체크 (저장 전에 검증)
    file.file.seek(0, 2)  # 파일 끝으로 이동
    file_size = file.file.tell()
    file.file.seek(0)  # 처음으로 되돌림

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {file_size} bytes. Maximum: {MAX_FILE_SIZE} bytes (100MB)",
        )

    # 파일 확장자 검증
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file_ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 소스 타입 결정
    source_type = SourceType.CSV if file_ext == ".csv" else SourceType.EXCEL

    # 고유 파일명 생성 (충돌 방지 + Path Traversal 방지)
    unique_id = uuid.uuid4().hex  # 전체 UUID 사용
    sanitized_name = sanitize_filename(file.filename)
    safe_filename = f"{unique_id}_{sanitized_name}"
    file_path = UPLOAD_DIR / safe_filename

    # 경로 검증 (Path Traversal 방지)
    file_path = file_path.resolve()
    if not file_path.is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )

    # 파일 저장
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        # 저장 실패 시 partial file 삭제
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as cleanup_err:
                logger.error(f"Failed to cleanup partial file: {cleanup_err}")

        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file",
        ) from e
    finally:
        file.file.close()

    logger.info(f"File uploaded: {file.filename} -> {file_path} ({file_size} bytes)")

    return FileUploadResponse(
        success=True,
        file_path=str(file_path),
        file_name=file.filename,
        file_size=file_size,
        source_type=source_type,
    )
