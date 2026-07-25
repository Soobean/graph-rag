# Graph RAG 시스템 아키텍처 설계서

> 📚 이 문서는 목차입니다. 상세 내용은 `architecture/` 폴더의 개별 문서를 참조하세요.
>
> ⚠️ **시점 주의**: architecture/ 문서들은 2026-02 설계 기준입니다.
> 2026-07 재편(LLM 계층 분해 → AzureOpenAIGateway+LLMTaskService, Cypher 도메인
> 모델 `src/domain/cypher/`, Self-Correction 루프, Eval Harness `evals/`)의
> 현행 기준은 루트 **CLAUDE.md**와 **docs/EVALS.md**입니다.

## 문서 구조

```
docs/
├── ARCHITECTURE.md              # 👈 현재 문서 (목차)
└── architecture/
    ├── 01-overview.md           # 개요 및 프로젝트 구조
    ├── 02-kg-ingestion.md       # KG 추출 파이프라인
    ├── 03-requirements.md       # 요구사항 분석
    ├── 04-langgraph.md          # ⭐ LangGraph 파이프라인 (핵심)
    ├── 05-design-decisions.md   # 설계 결정사항
    ├── 06-tech-stack.md         # 기술 스택
    ├── 07-operations.md         # 배포/보안/모니터링
    ├── 08-appendix.md           # 부록
    └── 09-ontology-system.md    # ⭐ 온톨로지 시스템 (개념 확장)
```

---

## 빠른 링크

### 핵심 문서
| 문서 | 설명 | 상태 |
|------|------|------|
| [01-overview.md](./architecture/01-overview.md) | 시스템 개요, 폴더 구조, 레이어 아키텍처 | ✅ |
| [02-kg-ingestion.md](./architecture/02-kg-ingestion.md) | KG 추출 파이프라인 (Human-in-the-loop) | ✅ |
| [04-langgraph.md](./architecture/04-langgraph.md) | **⭐ LangGraph 파이프라인, State, 노드, Chat History** | ✅ |

### 참고 문서
| 문서 | 설명 | 상태 |
|------|------|------|
| [03-requirements.md](./architecture/03-requirements.md) | 질문 유형 분류, 그래프 탐색 패턴 | ✅ |
| [05-design-decisions.md](./architecture/05-design-decisions.md) | 설계 결정사항, 노드 재사용성, 구현 우선순위 | ✅ |
| [06-tech-stack.md](./architecture/06-tech-stack.md) | 기술 스택, 모델 호환성, 성공 지표 | ✅ |
| [07-operations.md](./architecture/07-operations.md) | 보안, 에러 핸들링, 성능, 배포, 캐싱, 모니터링 | ✅ |
| [08-appendix.md](./architecture/08-appendix.md) | UI 옵션, 호환성 노트, 설정 예시 | ✅ |
| [09-ontology-system.md](./architecture/09-ontology-system.md) | **⭐ 온톨로지 시스템, 개념 확장, 가중치 기반 검색** | ✅ |

---

## 시스템 개요

### 목적
Neo4j 기반 Graph RAG 시스템으로 자연어 질문에 대해 그래프 탐색 후 LLM 응답 생성

### 핵심 흐름
```
[질문] → Intent분류 → Entity추출 → DB매칭 → Cypher생성 → 실행 → 응답생성
```

### 주요 컴포넌트
- **LangGraph 파이프라인**: 노드 기반 워크플로우
- **MemorySaver Checkpointer**: 세션별 대화 기록 관리
- **Vector Cache**: 유사 질문 캐싱 (Neo4j Vector Index)
- **Entity Resolver**: 한글-영문 매핑, 동명이인 처리

---

## 설계 원칙

1. **단순함 우선**: 복잡한 아키텍처 없이 검증된 패턴으로 시작
2. **점진적 확장**: MVP 먼저, 이후 기능 추가
3. **디버깅 용이성**: 각 단계의 입출력을 명확히 추적 가능하게
4. **그래프 특성 활용**: 관계 탐색이 핵심 가치
5. **LangGraph 기반**: 노드/엣지 그래프로 파이프라인 구성

---

## Quick Start

```python
from src.graph.pipeline import GraphRAGPipeline

pipeline = GraphRAGPipeline(settings, neo4j_repo, llm_repo)

# 기본 실행
result = await pipeline.run("Python 개발자 추천해줘")

# 세션 유지 (Chat History)
result1 = await pipeline.run("홍길동의 부서는?", session_id="user-123")
result2 = await pipeline.run("그 사람의 직급은?", session_id="user-123")
```

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-01-14 | 온톨로지 시스템 문서 추가 (09-ontology-system.md) |
| 2026-01 | 문서 구조 분리 |
| 2025-12 | Chat History (MemorySaver) 추가 |
| 2025-01 | 초기 설계 |
