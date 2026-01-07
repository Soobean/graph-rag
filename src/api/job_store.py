"""
Job Store

비동기 작업 상태를 관리하는 인메모리 저장소
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import ClassVar


class JobStatus(str, Enum):
    """작업 상태"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobState:
    """작업 상태 정보"""

    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    total_documents: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    failed_documents: int = 0
    duration_seconds: float = 0.0
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class JobStore:
    """
    인메모리 Job 저장소

    Note:
        프로덕션에서는 Redis 또는 DB로 대체 필요
        멀티 워커 환경에서는 공유 저장소 필요
    """

    _instance: ClassVar["JobStore | None"] = None
    _jobs: ClassVar[dict[str, JobState]] = {}
    _lock: ClassVar[Lock] = Lock()

    def __new__(cls) -> "JobStore":
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def create_job(self) -> str:
        """새 작업 생성 및 job_id 반환"""
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = JobState(job_id=job_id)
        return job_id

    def get_job(self, job_id: str) -> JobState | None:
        """작업 상태 조회"""
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: JobStatus | None = None,
        progress: float | None = None,
        total_documents: int | None = None,
        total_nodes: int | None = None,
        total_edges: int | None = None,
        failed_documents: int | None = None,
        duration_seconds: float | None = None,
        error: str | None = None,
    ) -> None:
        """작업 상태 업데이트"""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if total_documents is not None:
                job.total_documents = total_documents
            if total_nodes is not None:
                job.total_nodes = total_nodes
            if total_edges is not None:
                job.total_edges = total_edges
            if failed_documents is not None:
                job.failed_documents = failed_documents
            if duration_seconds is not None:
                job.duration_seconds = duration_seconds
            if error is not None:
                job.error = error

            job.updated_at = datetime.now()

    def delete_job(self, job_id: str) -> None:
        """작업 삭제"""
        with self._lock:
            self._jobs.pop(job_id, None)

    def list_jobs(self, limit: int = 100) -> list[JobState]:
        """최근 작업 목록 조회"""
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
            return jobs[:limit]


# 글로벌 인스턴스
job_store = JobStore()
