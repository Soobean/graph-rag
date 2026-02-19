"""
Ingest API 엔드포인트 테스트

파일 업로드, 적재 작업 생성/조회 API 테스트
"""

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.job_store import JobStatus, job_store
from src.api.routes.ingest import UPLOAD_DIR, router


@pytest.fixture(autouse=True)
def _cleanup_job_store():
    """테스트 간 job_store 초기화"""
    yield
    # 테스트 후 모든 job 삭제
    with job_store._lock:
        job_store._jobs.clear()


@pytest.fixture
def app():
    """테스트용 FastAPI 앱"""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return TestClient(app)


# =============================================================================
# POST /upload
# =============================================================================


class TestUploadAPI:
    def test_upload_csv_success(self, client, tmp_path):
        """CSV 파일 업로드 성공"""
        content = b"name,age\nAlice,30\nBob,25"
        resp = client.post(
            "/api/v1/upload",
            files={"file": ("test_data.csv", io.BytesIO(content), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["file_name"] == "test_data.csv"
        assert data["source_type"] == "csv"

        # 업로드된 파일 정리
        uploaded = Path(data["file_path"])
        if uploaded.exists():
            uploaded.unlink()

    def test_upload_invalid_extension_400(self, client):
        """잘못된 확장자 → 400"""
        content = b"some content"
        resp = client.post(
            "/api/v1/upload",
            files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
        )
        assert resp.status_code == 400
        assert "Invalid file type" in resp.json()["detail"]


# =============================================================================
# POST /ingest
# =============================================================================


class TestIngestAPI:
    def test_ingest_success(self, client):
        """적재 작업 생성 성공 (202)"""
        # UPLOAD_DIR 내에 임시 파일 생성
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        test_file = UPLOAD_DIR / "test_ingest.csv"
        test_file.write_text("name,age\nAlice,30")

        try:
            resp = client.post("/api/v1/ingest", json={
                "source_type": "csv",
                "file_path": str(test_file),
            })
            assert resp.status_code == 202
            data = resp.json()
            assert data["success"] is True
            assert "job_id" in data
        finally:
            if test_file.exists():
                test_file.unlink()


# =============================================================================
# GET /ingest/{job_id}
# =============================================================================


class TestIngestStatusAPI:
    def test_get_status_existing(self, client):
        """존재하는 작업 조회"""
        job_id = job_store.create_job()
        job_store.update_job(job_id, status=JobStatus.RUNNING, progress=0.5)

        resp = client.get(f"/api/v1/ingest/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "running"

    def test_get_status_not_found(self, client):
        """존재하지 않는 작업 → 404"""
        resp = client.get("/api/v1/ingest/nonexistent-id")
        assert resp.status_code == 404


# =============================================================================
# GET /ingest
# =============================================================================


class TestIngestListAPI:
    def test_list_jobs(self, client):
        """작업 목록 조회"""
        job_store.create_job()
        job_store.create_job()

        resp = client.get("/api/v1/ingest")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_list_jobs_empty(self, client):
        """빈 목록"""
        resp = client.get("/api/v1/ingest")
        assert resp.status_code == 200
        assert resp.json() == []
