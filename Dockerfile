FROM python:3.12-slim AS builder

# uv 설치 (Rust 기반 초고속 패키지 매니저)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 환경 변수 설정
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.12

WORKDIR /app

# 의존성 파일 복사 (캐시 최적화)
COPY pyproject.toml README.md ./

# 가상환경 생성 및 의존성 설치
RUN uv venv /app/.venv && \
    uv pip install --no-cache -r pyproject.toml

# 소스 코드 복사 및 패키지 설치
COPY src/ ./src/
RUN uv pip install --no-cache .

# ---------------------------------------------
# Stage 2: Runtime
# ---------------------------------------------
FROM python:3.12-slim AS runtime

# 런타임에 필요한 최소 패키지만 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 비root 사용자 생성 (보안)
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# 가상환경 복사
COPY --from=builder /app/.venv /app/.venv

# 소스 코드 복사
COPY --from=builder /app/src ./src/
COPY src/domain/ontology/*.yaml ./src/domain/ontology/
COPY src/prompts/ ./src/prompts/

# 환경 변수 설정
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 소유권 변경
RUN chown -R appuser:appuser /app

# 비root 사용자로 전환
USER appuser

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# 포트 노출
EXPOSE 8000

# 실행
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
