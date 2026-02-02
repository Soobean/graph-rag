"""
Ingestion API Schemas

데이터 적재 API 요청/응답 스키마 정의
"""

from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """지원하는 데이터 소스 타입"""

    CSV = "csv"
    EXCEL = "excel"


class IngestRequest(BaseModel):
    """데이터 적재 요청"""

    source_type: SourceType = Field(
        ...,
        description="데이터 소스 타입",
        examples=["csv", "excel"],
    )
    file_path: str = Field(
        ...,
        min_length=1,
        description="데이터 파일 경로",
        examples=["/data/employees.csv"],
    )
    batch_size: int = Field(
        default=50,
        ge=1,
        le=500,
        description="배치 크기 (1-500)",
    )
    concurrency: int = Field(
        default=5,
        ge=1,
        le=20,
        description="동시 처리 수 (1-20)",
    )
    # Excel 전용 옵션
    sheet_name: str | int = Field(
        default=0,
        description="Excel 시트 이름 또는 인덱스",
    )
    header_row: int = Field(
        default=0,
        description="헤더 행 인덱스 (0-based)",
    )


class IngestStats(BaseModel):
    """적재 결과 통계"""

    total_documents: int = Field(description="처리된 문서 수")
    total_nodes: int = Field(description="생성된 노드 수")
    total_edges: int = Field(description="생성된 관계 수")
    failed_documents: int = Field(description="실패한 문서 수")
    duration_seconds: float = Field(description="처리 시간 (초)")


class IngestResponse(BaseModel):
    """데이터 적재 응답"""

    success: bool = Field(description="성공 여부")
    message: str = Field(description="결과 메시지")
    stats: IngestStats | None = Field(default=None, description="적재 통계")
    job_id: str | None = Field(default=None, description="작업 ID (비동기 처리용)")
    error: str | None = Field(default=None, description="에러 메시지")


class IngestStatusResponse(BaseModel):
    """적재 상태 조회 응답 (향후 비동기 처리용)"""

    job_id: str = Field(description="작업 ID")
    status: str = Field(description="작업 상태 (pending, running, completed, failed)")
    progress: float = Field(default=0.0, description="진행률 (0.0 ~ 1.0)")
    stats: IngestStats | None = Field(default=None, description="현재까지 통계")
    error: str | None = Field(default=None, description="에러 메시지")


class FileUploadResponse(BaseModel):
    """파일 업로드 응답"""

    success: bool = Field(description="성공 여부")
    file_path: str = Field(description="서버에 저장된 파일 경로")
    file_name: str = Field(description="원본 파일 이름")
    file_size: int = Field(description="파일 크기 (bytes)")
    source_type: SourceType = Field(description="감지된 소스 타입")
