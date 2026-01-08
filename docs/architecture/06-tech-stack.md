# 6. 기술 스택

## 6.1 핵심 기술 스택

| 레이어 | 기술 | 이유 |
|--------|------|------|
| **언어** | Python 3.12+ | ML/LLM 생태계, 빠른 개발 |
| **워크플로우** | **LangGraph 0.2+** | 노드/엣지 기반 파이프라인, 상태 관리 |
| **프레임워크** | FastAPI | 비동기, 자동 문서화 |
| **그래프 DB** | Neo4j 5.x | 기존 데이터 활용 |
| **Neo4j 드라이버** | neo4j-python-driver | 공식 드라이버 |
| **LLM** | Azure OpenAI | 기업 보안 정책 준수, API 안정성 (모델 버전 비의존적) |
| **LLM SDK** | **openai (직접 사용)** | 최신 API 즉시 대응, 의존성 최소화, 세밀한 제어 |

> **Note**: langchain-openai 대신 openai SDK를 직접 사용합니다. 이유:
> - 최신 API 파라미터 즉시 대응 (`max_completion_tokens` 등)
> - 의존성 최소화 (langchain 버전 종속성 제거)
> - 세밀한 retry/timeout 제어
> - 디버깅 용이성

---

## 6.2 모델 버전 호환성 전략

시스템은 특정 모델 버전에 의존하지 않고, 모든 Azure OpenAI 배포 모델과 호환되도록 설계합니다:

```python
# src/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class LLMSettings(BaseSettings):
    """모델 버전 비의존적 LLM 설정"""

    # Azure OpenAI 기본 설정
    azure_openai_endpoint: str
    azure_openai_api_key: Optional[str] = None  # Managed Identity 사용 시 불필요
    azure_openai_api_version: str = "2025-04-01-preview"  # 최신 API 버전

    # 배포 이름 (Azure Portal에서 설정한 이름)
    # 실제 모델 버전(gpt-4, gpt-4o, gpt-5.2 등)과 무관하게 배포 이름만 지정
    light_model_deployment: str = "light-model"   # 가벼운 작업용 배포
    heavy_model_deployment: str = "heavy-model"   # 복잡한 작업용 배포

    # 모델 파라미터 (모델 버전과 무관한 공통 설정)
    temperature: float = 0.0
    max_tokens: int = 2000

    class Config:
        env_prefix = "AZURE_OPENAI_"
```

**설계 원칙:**
1. **배포 이름 추상화**: 특정 모델명(gpt-4, gpt-35-turbo) 대신 Azure 배포 이름 사용
2. **역할 기반 분류**: `light_model` / `heavy_model`로 용도만 구분
3. **환경변수 설정**: 운영 환경에서 배포 이름만 변경하여 모델 업그레이드 가능

**환경변수 예시:**
```bash
# .env.example - 모델 버전에 따른 배포 이름 설정

# 옵션 1: GPT-3.5 + GPT-4 조합
AZURE_OPENAI_LIGHT_MODEL_DEPLOYMENT=gpt-35-turbo-deploy
AZURE_OPENAI_HEAVY_MODEL_DEPLOYMENT=gpt-4-deploy

# 옵션 2: GPT-4o-mini + GPT-4o 조합
AZURE_OPENAI_LIGHT_MODEL_DEPLOYMENT=gpt-4o-mini-deploy
AZURE_OPENAI_HEAVY_MODEL_DEPLOYMENT=gpt-4o-deploy

# 옵션 3: 최신 GPT-5.x 조합
AZURE_OPENAI_LIGHT_MODEL_DEPLOYMENT=gpt-5-mini-deploy
AZURE_OPENAI_HEAVY_MODEL_DEPLOYMENT=gpt-5-2-deploy
```

---

## 6.3 LangGraph 1.0 호환성

> **참고**: 본 문서의 모든 LangGraph 코드는 1.0+ 기준으로 작성되었습니다.

**LangGraph 1.0 주요 변경사항:**

| 항목 | 0.x (레거시) | 1.0+ (현재) |
|------|-------------|-------------|
| Import | `from langgraph.graph import StateGraph` | `from langgraph.graph import StateGraph, START, END` |
| 반환 타입 | `CompiledGraph` | `CompiledStateGraph` |
| 시작점 | `"__start__"` 문자열 | `START` 상수 |
| 종료점 | `"__end__"` 문자열 | `END` 상수 |
| 병렬 실행 | 암시적 fan-out | 명시적 다중 edge |

---

## 6.4 버전 호환성 매트릭스

| 컴포넌트 | 최소 버전 | 권장 버전 | 비고 |
|----------|----------|----------|------|
| Python | 3.11 | 3.12+ | async/typing 개선 |
| LangGraph | 1.0.0 | 최신 1.x | 정식 API 안정성 |
| FastAPI | 0.100+ | 최신 | Pydantic v2 호환 |
| Neo4j | 5.0+ | 5.x | 기존 데이터 호환 |
| Azure OpenAI SDK | 1.0+ | 최신 | API 버전 독립적 |

---

## 6.5 성공 지표 (MVP)

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| Cypher 생성 정확도 | > 80% | 테스트 셋 기준 |
| 응답 정확도 | > 85% | 수동 평가 (100개 샘플) |
| 평균 응답 시간 | < 5초 | P50 기준 |
| 지원 질문 유형 커버리지 | 4/7 유형 | A, B, D, F 유형 |
