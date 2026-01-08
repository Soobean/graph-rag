# 7. 운영 및 인프라

> 보안, 에러 핸들링, 성능, 배포, 캐싱, 모니터링 관련 문서

---

## 7.1 보안 요구사항

### 인증 및 권한

| 구분 | 방식 | 설명 |
|------|------|------|
| **API 인증** | API Key + JWT | 클라이언트별 API Key 발급, JWT로 세션 관리 |
| **Neo4j 인증** | 환경변수 기반 | `NEO4J_USER`, `NEO4J_PASSWORD` 환경변수 사용 |
| **Azure OpenAI 인증** | Managed Identity 또는 API Key | 프로덕션은 Managed Identity 권장 |

### 데이터 접근 제어

```python
# 역할 기반 접근 제어 (RBAC)
class AccessLevel(Enum):
    PUBLIC = "public"           # 기본 조직 정보
    INTERNAL = "internal"       # 상세 직원 정보
    CONFIDENTIAL = "confidential"  # 급여, 평가 등 민감 정보

# 쿼리 필터링 예시
def apply_access_filter(cypher: str, user_role: str) -> str:
    if user_role != "admin":
        # 민감 필드 제외
        cypher = exclude_confidential_fields(cypher)
    return cypher
```

### 민감 데이터 처리

| 데이터 유형 | 처리 방식 |
|------------|----------|
| 직원 개인정보 (이메일, 연락처) | 마스킹 처리 후 응답 |
| 급여/평가 정보 | 관리자 권한만 접근 가능 |
| LLM 프롬프트 로깅 | 개인정보 제거 후 저장 |

---

## 7.2 에러 핸들링

### 에러 유형 분류

| 에러 유형 | 코드 | 재시도 | 사용자 메시지 |
|----------|------|--------|--------------|
| **LLM API 실패** | E001 | 최대 3회 (지수 백오프) | "잠시 후 다시 시도해주세요" |
| **LLM Rate Limit** | E002 | 60초 대기 후 1회 | "요청이 많습니다. 잠시 후 시도해주세요" |
| **Neo4j 연결 실패** | E003 | 최대 2회 | "시스템 점검 중입니다" |
| **Cypher 문법 오류** | E004 | 재시도 없음 | "질문을 이해하지 못했습니다. 다시 표현해주세요" |
| **쿼리 타임아웃** | E005 | 재시도 없음 | "복잡한 질문입니다. 더 구체적으로 질문해주세요" |
| **빈 결과** | E006 | 재시도 없음 | "조건에 맞는 결과가 없습니다" |
| **권한 없음** | E007 | 재시도 없음 | "해당 정보에 접근 권한이 없습니다" |

### 재시도 정책

```python
from tenacity import retry, stop_after_attempt, wait_exponential

# LLM 호출 재시도 설정
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError))
)
async def call_llm(prompt: str) -> str:
    ...
```

### Fallback 전략

```
┌─────────────────────────────────────────────────────────────────┐
│                     Fallback Chain                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LLM 실패 시:                                                    │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ GPT-4 호출   │ -> │ GPT-3.5 호출 │ -> │ 템플릿 응답  │       │
│  │ (Primary)    │    │ (Fallback)   │    │ (Last Resort)│       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
│  Cypher 실패 시:                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ LLM 생성     │ -> │ 템플릿 매칭  │ -> │ 에러 메시지  │       │
│  │ Cypher       │    │ Cypher       │    │ 반환         │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7.3 성능 요구사항

### 레이턴시 목표

| 지표 | 목표 | 알림 임계값 |
|------|------|------------|
| **P50 응답시간** | < 3초 | - |
| **P95 응답시간** | < 5초 | > 7초 시 경고 |
| **P99 응답시간** | < 10초 | > 15초 시 알림 |

### 노드별 타임아웃 설정

| 노드 | 타임아웃 | 비고 |
|------|---------|------|
| intent_classifier | 5초 | LLM 호출 포함 |
| entity_extractor | 5초 | LLM 호출 포함 |
| cypher_generator | 10초 | 복잡한 쿼리 생성 고려 |
| graph_executor | 30초 | 복잡한 경로 탐색 고려 |
| response_generator | 10초 | LLM 호출 포함 |
| **전체 파이프라인** | 60초 | 모든 노드 합계 |

### 동시성 및 처리량

| 지표 | MVP 목표 | Phase 2 목표 |
|------|---------|-------------|
| 동시 요청 처리 | 10 RPS | 50 RPS |
| 최대 동시 접속자 | 20명 | 100명 |
| LLM 동시 호출 | 5개 | 20개 (Rate Limit 고려) |

---

## 7.4 평가 체계

### 평가 데이터셋 구성

| 질문 유형 | 샘플 수 | 난이도 분포 |
|----------|--------|------------|
| A. 인력 추천 | 30개 | 쉬움 10, 중간 15, 어려움 5 |
| B. 프로젝트 매칭 | 25개 | 쉬움 8, 중간 12, 어려움 5 |
| D. 조직 분석 | 25개 | 쉬움 10, 중간 10, 어려움 5 |
| F. 자격증 검색 | 20개 | 쉬움 10, 중간 8, 어려움 2 |
| **합계** | **100개** | |

### 평가 기준

```yaml
evaluation_criteria:
  cypher_accuracy:
    description: "생성된 Cypher가 올바른 결과를 반환하는가"
    scoring:
      - 1: "완전히 잘못됨 (문법 오류 또는 무관한 결과)"
      - 2: "부분적 정확 (일부 결과만 맞음)"
      - 3: "대체로 정확 (주요 결과 포함)"
      - 4: "정확함 (모든 기대 결과 포함)"
      - 5: "완벽함 (최적화된 쿼리, 정확한 결과)"

  response_quality:
    description: "자연어 응답의 품질"
    scoring:
      - 1: "이해 불가"
      - 2: "정보 부족 또는 부정확"
      - 3: "기본 정보 제공"
      - 4: "명확하고 유용한 응답"
      - 5: "완벽한 응답 (추가 인사이트 포함)"
```

---

## 7.5 배포 및 운영 환경

### 컨테이너화

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

COPY src/ ./src/
COPY config/ ./config/

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["poetry", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  graph-rag-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
    depends_on:
      - neo4j

  neo4j:
    image: neo4j:5.15
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
```

### 환경별 설정

| 환경 | 용도 | LLM 배포 전략 | 로깅 레벨 |
|------|------|--------------|----------|
| **dev** | 로컬 개발 | light: 저비용 모델, heavy: 저비용 모델 | DEBUG |
| **staging** | 통합 테스트 | light: 저비용 모델, heavy: 고성능 모델 | INFO |
| **prod** | 운영 | light: 저비용 모델, heavy: 고성능 모델 | WARNING |

### 헬스체크 엔드포인트

```python
@app.get("/health")
async def health_check():
    """기본 헬스체크"""
    return {"status": "healthy"}

@app.get("/health/ready")
async def readiness_check():
    """의존성 포함 헬스체크"""
    checks = {
        "neo4j": await check_neo4j_connection(),
        "azure_openai": await check_azure_openai(),
    }
    all_healthy = all(checks.values())
    return {"status": "ready" if all_healthy else "not_ready", "checks": checks}
```

---

## 7.6 캐싱 전략

### 캐싱 레이어

```
┌─────────────────────────────────────────────────────────────────┐
│                     캐싱 레이어 구조                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  L1: 응답 캐시 (완전 일치)                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Key: hash(question)                                      │    │
│  │ Value: {response, timestamp, hit_count}                  │    │
│  │ TTL: 1시간                                               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  L2: Cypher 결과 캐시                                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Key: hash(cypher_query + params)                         │    │
│  │ Value: {graph_results, result_count}                     │    │
│  │ TTL: 5분 (그래프 데이터 변경 주기 고려)                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  L3: 엔티티 캐시                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Key: entity_type + entity_value                          │    │
│  │ Value: {exists, node_id, properties}                     │    │
│  │ TTL: 30분                                                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 캐시 무효화 전략

| 이벤트 | 무효화 범위 |
|--------|------------|
| 그래프 데이터 업데이트 | L2, L3 전체 무효화 |
| 스키마 변경 | 전체 캐시 무효화 |
| TTL 만료 | 개별 항목 자동 삭제 |
| 수동 무효화 API | 지정된 키 또는 패턴 삭제 |

---

## 7.7 모니터링 및 관측성

### 메트릭 수집

```python
from prometheus_client import Counter, Histogram, Gauge

REQUEST_COUNT = Counter(
    'graph_rag_requests_total',
    'Total requests',
    ['intent', 'status']
)

REQUEST_LATENCY = Histogram(
    'graph_rag_request_latency_seconds',
    'Request latency',
    ['node'],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30]
)

LLM_TOKEN_USAGE = Counter(
    'graph_rag_llm_tokens_total',
    'LLM token usage',
    ['model', 'type']
)
```

### 로깅 표준

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "query_processed",
    question=question[:100],  # 개인정보 제거를 위해 잘림
    intent=state["intent"],
    latency_ms=elapsed_ms,
    result_count=state["result_count"],
    cache_hit=cache_hit,
    request_id=request_id
)
```

### 알림 규칙

| 조건 | 심각도 | 알림 채널 |
|------|--------|----------|
| P99 레이턴시 > 15초 (5분간) | Warning | Slack |
| 에러율 > 5% (10분간) | Critical | Slack + PagerDuty |
| Neo4j 연결 실패 | Critical | Slack + PagerDuty |
| LLM API 연속 실패 3회 | Warning | Slack |
| 캐시 히트율 < 20% | Info | Slack (일간 리포트) |

### 대시보드 패널 구성

```yaml
panels:
  - title: "Request Rate"
    query: rate(graph_rag_requests_total[5m])

  - title: "Latency Percentiles"
    query: |
      histogram_quantile(0.5, rate(graph_rag_request_latency_seconds_bucket[5m]))
      histogram_quantile(0.95, rate(graph_rag_request_latency_seconds_bucket[5m]))
      histogram_quantile(0.99, rate(graph_rag_request_latency_seconds_bucket[5m]))

  - title: "Error Rate by Intent"
    query: |
      sum(rate(graph_rag_requests_total{status="error"}[5m])) by (intent)
      / sum(rate(graph_rag_requests_total[5m])) by (intent)
```
