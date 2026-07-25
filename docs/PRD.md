# Product Requirements Document (PRD)

# Graph RAG — HR 인재 검색 & 분석 시스템

> **Version**: 1.0
> **Last Updated**: 2026-02-25
> **Status**: Production-Ready (Beta)

---

## 1. 개요 (Overview)

### 1.1 제품 요약

Graph RAG는 **Neo4j 그래프 데이터베이스**와 **Azure OpenAI**를 결합한 HR 인재 검색 및 분석 시스템이다. 사용자가 한국어/영어 자연어로 질문하면, LangGraph 기반 AI 파이프라인이 이를 Cypher 쿼리로 변환하여 그래프 DB에서 결과를 조회하고, 자연어 응답으로 합성하여 반환한다.

### 1.2 핵심 가치

| 가치 | 설명 |
|------|------|
| **자연어 인재 검색** | "Python 3년 이상 경력자 중 프로젝트 여유 있는 직원" 같은 복합 조건을 자연어로 검색 |
| **관계 기반 분석** | 직원-스킬-프로젝트-부서 간 그래프 관계를 활용한 다차원 분석 |
| **실시간 시각화** | 검색 결과를 인터랙티브 그래프로 즉시 시각화 |
| **HR 의사결정 지원** | 팀 구성 추천, 프로젝트 인력 배치, 스킬 갭 분석 등 데이터 기반 의사결정 |

### 1.3 대상 사용자

| 역할 | 사용 시나리오 |
|------|-------------|
| **HR 담당자** | 인재 검색, 프로젝트 인력 배치, 스킬 현황 파악 |
| **팀 리드 / PM** | 프로젝트 팀 구성, 대체 인력 추천, 예산 분석 |
| **관리자 (Admin)** | 온톨로지 관리, 데이터 수집, 그래프 편집, 커뮤니티 분석 |
| **경영진** | 조직 분석, 인력 분포, 스킬 트렌드 파악 |

---

## 2. 시스템 아키텍처 (Architecture)

### 2.1 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| Frontend | React 19 + TypeScript + Vite + Tailwind CSS | SPA, Zustand 상태 관리 |
| Backend | FastAPI (Python 3.12) | 비동기 처리, `uv` 패키지 매니저 |
| AI Pipeline | LangGraph StateGraph (12 노드) | 상태 기계 기반 RAG |
| LLM | Azure OpenAI (gpt-4o, gpt-4o-mini) | Light/Heavy 이중 모델 구조 |
| Database | Neo4j 5.15 Community + GDS 플러그인 | 그래프 알고리즘 지원 |
| Infra | Docker Compose, Azure Pipelines | 컨테이너 기반 배포 |

### 2.2 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (React)                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ ChatPage │  │ Compare  │  │   Admin Pages     │  │
│  │ (메인)   │  │  Page    │  │ (Ontology/Ingest/ │  │
│  │          │  │          │  │  Analytics/Edit)   │  │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       └──────────────┼─────────────────┘             │
│                      │ SSE / REST                    │
└──────────────────────┼───────────────────────────────┘
                       │
┌──────────────────────┼───────────────────────────────┐
│              FastAPI Backend (8 Routers)              │
│                      │                               │
│  ┌───────────────────┼───────────────────────────┐   │
│  │           LangGraph Pipeline                  │   │
│  │                                               │   │
│  │  Cache → Intent/Entity → Concept Expand       │   │
│  │    → Entity Resolve → Cypher Gen → Execute    │   │
│  │    → Response Gen → Ontology Learn            │   │
│  └───────────────────┬───────────────────────────┘   │
│                      │                               │
│  ┌────────┐ ┌────────┤ ┌───────────┐ ┌──────────┐   │
│  │Staffing│ │  GDS   │ │Graph Edit │ │ Ontology │   │
│  │Service │ │Service │ │ Service   │ │ Service  │   │
│  └────┬───┘ └────┬───┘ └─────┬─────┘ └────┬─────┘   │
└───────┼──────────┼───────────┼─────────────┼─────────┘
        │          │           │             │
┌───────┴──────────┴───────────┴─────────────┴─────────┐
│                  Neo4j Graph Database                 │
│  (Employee, Skill, Project, Department, Concept ...) │
└──────────────────────────────────────────────────────┘
```

### 2.3 데이터 모델 (Graph Schema)

#### 노드 (Node Labels)

| 라벨 | 설명 | 주요 속성 |
|------|------|-----------|
| `Employee` | 직원 | name, email, hourly_rate, max_projects, availability |
| `Skill` | 기술 스킬 (데이터 계층) | name, category |
| `Concept` | 온톨로지 개념 (분류 계층) | name, category, level |
| `Project` | 프로젝트 | name, status, budget, start_date, end_date |
| `Department` | 부서 | name, code |
| `Position` | 직급/직책 | name, level |
| `Organization` | 조직/회사 | name |
| `Certificate` | 자격증 | name, issuer |
| `Location` | 위치 | name, region |

#### 관계 (Relationships)

| 관계 | 방향 | 설명 | 주요 속성 |
|------|------|------|-----------|
| `HAS_SKILL` | Employee → Skill | 보유 스킬 | proficiency, effective_rate |
| `IS_A` | Concept → Concept | 온톨로지 계층 | - |
| `SAME_AS` | Concept ↔ Concept | 동의어 | - |
| `WORKS_ON` | Employee → Project | 프로젝트 참여 | role, start_date |
| `BELONGS_TO` | Employee → Department | 소속 부서 | - |
| `HAS_POSITION` | Employee → Position | 직급 | - |
| `MENTORS` | Employee → Employee | 멘토링 관계 | - |
| `REQUIRES` | Project → Skill | 프로젝트 필요 스킬 | required_proficiency, importance |
| `HAS_CERTIFICATE` | Employee → Certificate | 자격증 보유 | issue_date |
| `LOCATED_AT` | Employee → Location | 근무지 | - |

#### Two-Label 온톨로지 시스템

```
[데이터 계층]                     [온톨로지 계층]
Employee ──HAS_SKILL──> Skill    Concept ──IS_A──> Concept
                          │                          │
                          └── 이름(toLower) 기반 브리지 ─┘
```

- **Skill**: 실제 직원이 보유한 스킬 데이터
- **Concept**: 스킬 분류 체계 (Programming > Backend > Python)
- 두 계층은 `toLower(name)` 매칭으로 연결되며, 직접 관계(`Skill-IS_A->Concept`)는 존재하지 않음

---

## 3. 기능 요구사항 (Functional Requirements)

### 3.1 자연어 질의 (Natural Language Query)

**사용자가 한국어/영어 자연어로 HR 관련 질문을 하면, AI 파이프라인이 그래프 DB를 조회하여 답변을 생성한다.**

#### 3.1.1 지원 의도 유형 (9 Intent Types)

| 의도 | 설명 | 예시 질문 |
|------|------|-----------|
| `personnel_search` | 인력 검색 | "Python과 React 스킬이 있는 직원 찾아줘" |
| `project_matching` | 프로젝트 매칭 | "AI 플랫폼 프로젝트에 적합한 인력 추천" |
| `relationship_search` | 관계 탐색 | "김철수와 같은 프로젝트에 참여한 직원은?" |
| `org_analysis` | 조직 분석 | "개발1팀의 스킬 분포는?" |
| `mentoring_network` | 멘토링 네트워크 | "김철수의 멘토링 관계를 보여줘" |
| `certificate_search` | 자격증 검색 | "AWS 자격증 보유자 목록" |
| `path_analysis` | 경로 분석 | "김철수에서 박지우까지의 연결 관계" |
| `ontology_update` | 온톨로지 수정 | "새로운 스킬 'LangChain'을 AI 카테고리에 추가해줘" |
| `global_analysis` | 전체 분석 | "전체 조직의 스킬 트렌드 분석" |

#### 3.1.2 파이프라인 처리 흐름

```
질문 입력
  │
  ▼
[CacheChecker] ── cache hit (유사도 ≥ 0.93) ──→ [ResponseGenerator] → 응답
  │ cache miss
  ▼
[IntentEntityExtractor] ── LLM 1회 호출로 의도 + 엔티티 동시 추출
  │
  ▼
[QueryDecomposer] ── 복합 질문 분해 (선택적, multi-hop 지원)
  │
  ▼
[ConceptExpander] ── 온톨로지 기반 동의어/상위개념 확장
  │                  (예: "JS" → ["JavaScript", "TypeScript", "Node.js"])
  ▼
[EntityResolver] ── Neo4j에서 실제 노드 매칭
  │                    │
  │                    ▼ (미해결 엔티티)
  │              [ClarificationHandler] → "혹시 OOO을 말씀하시나요?"
  ▼
[CypherGenerator] ── Cypher 쿼리 생성 (Light/Heavy 모델 자동 선택)
  │
  ▼
[GraphExecutor] ── Neo4j에서 Cypher 실행
  │
  ▼
[ResponseGenerator] ── 결과를 자연어 응답으로 합성
  │
  ▼
[OntologyLearner] ── 미해결 용어 학습 제안 (선택적)
```

#### 3.1.3 실시간 스트리밍

- **SSE(Server-Sent Events)** 기반 실시간 응답 스트리밍
- 5가지 이벤트 타입: `step`(파이프라인 단계), `metadata`(의도/엔티티), `chunk`(응답 토큰), `done`(완료), `error`(에러)
- 각 파이프라인 노드 완료 시 즉시 프론트엔드에 단계 표시
- First token latency: ~100ms

#### 3.1.4 설명 가능성 (Explainability)

- `include_explanation=true` 요청 시, 파이프라인 각 단계의 추론 과정(thought process) 반환
- `include_graph=true` 요청 시, 결과를 시각화 가능한 그래프 데이터로 반환
- 생성된 Cypher 쿼리, 의도 분류 근거, 엔티티 해결 결과 등 투명하게 제공

---

### 3.2 인터랙티브 그래프 시각화

**검색 결과를 인터랙티브 그래프로 시각화하여 직원-스킬-프로젝트 관계를 직관적으로 탐색한다.**

#### 기능 상세

| 기능 | 설명 |
|------|------|
| **결과 그래프** | 질의 결과를 노드-엣지 그래프로 자동 렌더링 |
| **라벨별 색상** | Employee=초록, Skill=파랑, Project=보라, Department=주황, Certificate=오렌지 등 |
| **Force Layout** | 물리 시뮬레이션 기반 자동 배치 (단일/다중 중심 노드 지원) |
| **노드 상세** | 노드 클릭 시 속성, 연결 관계, 서브그래프 확장 |
| **서브그래프 탐색** | 특정 노드 중심 N-depth 서브그래프 조회 (1~3 depth) |
| **커뮤니티 시각화** | GDS 커뮤니티 탐지 결과 그래프로 표시 |
| **미니맵** | 전체 그래프 축소 뷰, 빠른 네비게이션 |
| **제한** | 최대 200 노드까지 표시 |

---

### 3.3 프로젝트 인력 배치 (Project Staffing)

**프로젝트 요구 스킬에 맞는 후보 인력을 검색하고, 최적 팀 구성 및 예산 분석을 수행한다.**

#### 기능 상세

| 기능 | 설명 |
|------|------|
| **프로젝트 목록** | 전체 프로젝트 조회 (상태, 예산, 요구 스킬) |
| **후보 인력 검색** | 프로젝트 필요 스킬 기반 후보자 필터링 (숙련도 ≥ 요구치, 비용 ≤ 상한, 가용성) |
| **인력 배치 계획** | 스킬별 Top N 후보자 추천, 총 예상 비용 산출 |
| **예산 분석** | 계획 비용 vs 실제 비용 비교, 예산 초과/절감 분석 |
| **스킬 카테고리** | 프로젝트별 필요 스킬 카테고리 필터링 |

---

### 3.4 인력 비교 분석 (Compare)

**다수 직원의 시급, 프로젝트 예산, 멘토링 관계 등을 테이블 형태로 비교 분석한다.**

#### 기능 상세

- 자연어로 비교 대상 및 기준 지정
- 결과 테이블: 필터 가능한 컬럼 (hourly_rate, effective_rate, budget, mentoring 등)
- 데이터 유형별 뱃지 표시 (가용 데이터 유형 식별)

---

### 3.5 GDS 분석 (Graph Data Science)

**Neo4j GDS 플러그인을 활용한 고급 그래프 분석 기능을 제공한다.**

#### 기능 상세

| 기능 | 설명 | 알고리즘 |
|------|------|----------|
| **커뮤니티 탐지** | 스킬 유사성 기반 직원 그룹핑 | Leiden / Louvain |
| **유사 직원 검색** | 특정 직원과 스킬 프로필이 유사한 직원 탐색 | Cosine Similarity |
| **팀 구성 추천** | 필요 스킬 커버리지 + 다양성을 고려한 최적 팀 구성 | Greedy Skill Coverage |
| **프로젝션 관리** | In-memory 그래프 프로젝션 생성/조회/삭제 | - |

#### 팀 구성 추천 상세

- **입력**: 필요 스킬 목록, 팀 규모, 다양성 가중치
- **알고리즘**: Greedy 방식 스킬 커버리지 최적화 + 커뮤니티 다양성 점수
- **출력**: 추천 팀원, 스킬 커버리지 %, 누락 스킬, 커뮤니티 다양성 점수

---

### 3.6 온톨로지 관리 (Ontology Management)

**스킬 분류 체계를 동적으로 관리하며, AI가 미해결 용어를 학습하여 제안하는 적응형 온톨로지 시스템.**

#### 3.6.1 스킬 분류 체계

```
SkillCategory (7대 카테고리)
├── Programming
│   ├── Backend (Python, Java, Go, C#, Node.js ...)
│   ├── Frontend (React, Vue, Angular, TypeScript ...)
│   ├── AI/ML (TensorFlow, PyTorch, scikit-learn ...)
│   ├── LLM Framework (LangChain, LlamaIndex, RAG ...)
│   └── Data (Pandas, Spark, Airflow ...)
├── Infrastructure
│   ├── Cloud (AWS, Azure, GCP ...)
│   ├── DevOps (Docker, Kubernetes, Jenkins ...)
│   └── Database (PostgreSQL, MongoDB, Neo4j ...)
├── Collaboration (Git, Jira, Figma, Agile ...)
└── ... (총 98개 스킬)
```

#### 3.6.2 적응형 온톨로지 (Adaptive Ontology)

| 기능 | 설명 |
|------|------|
| **자동 학습** | 파이프라인에서 미해결 엔티티 발생 시, OntologyLearner가 새 개념/동의어/관계 제안 |
| **제안 워크플로우** | pending → approved/rejected 상태 관리 (낙관적 잠금) |
| **자동 승인** | 신뢰도 ≥ 0.95 & 빈도 ≥ 5인 제안은 자동 승인 (일일 20건 한도) |
| **일괄 처리** | 대량 제안 일괄 승인/거절 |
| **통계** | 상태별 제안 수, 카테고리 분포, 미해결 용어 Top 10 빈도 |
| **채팅 업데이트** | 대화 중 "새 스킬 추가해줘" 같은 요청으로 온톨로지 직접 수정 |

#### 3.6.3 온톨로지 로더 모드

| 모드 | 설명 |
|------|------|
| `yaml` | YAML 파일(`schema.yaml`, `synonyms.yaml`)에서 로드 (기본값) |
| `neo4j` | Neo4j `:Concept` 노드에서 동적 로드 |
| `hybrid` | Neo4j 우선 조회 + YAML 폴백 |

---

### 3.7 데이터 수집 (Ingestion)

**CSV/Excel 파일을 업로드하여 직원, 스킬, 프로젝트 등의 데이터를 그래프 DB에 자동으로 로딩한다.**

#### 기능 상세

| 기능 | 설명 |
|------|------|
| **파일 업로드** | CSV/Excel 파일 업로드 (최대 100MB) |
| **LLM 기반 추출** | 업로드 파일에서 엔티티/관계 자동 추출 (GPT 기반) |
| **비동기 처리** | 백그라운드 작업으로 진행, job_id로 상태 추적 |
| **배치 처리** | 기본 배치 크기 50, 동시성 5 |
| **멱등 저장** | MERGE 기반 중복 방지, UUID5 결정적 노드 ID |
| **신뢰도 필터** | 추출 관계의 신뢰도 임계값 0.8 이상만 저장 |
| **진행률** | 실시간 진행률 추적 (%) 및 에러 로그 |

---

### 3.8 그래프 편집 (Graph Edit)

**관리자가 직접 그래프 노드와 엣지를 생성/수정/삭제하는 CRUD 기능.**

#### 기능 상세

| 기능 | 설명 |
|------|------|
| **노드 CRUD** | 생성, 조회, 수정, 삭제 (라벨/관계 화이트리스트 기반 검증) |
| **엣지 CRUD** | 관계 생성, 조회, 삭제 |
| **삭제 영향 분석** | 노드 삭제 전 연결된 관계/노드에 미치는 영향 사전 분석 (dry-run) |
| **이름 변경 영향** | 속성 변경이 참조하는 다른 노드에 미치는 영향 분석 |
| **노드 검색** | 라벨, 이름(CONTAINS 부분 매칭)으로 검색 |
| **스키마 정보** | 허용된 라벨, 필수 속성, 유효 관계 조합 정보 제공 |

---

### 3.9 인증 및 인가 (Authentication & Authorization)

#### 기능 상세

| 기능 | 설명 |
|------|------|
| **JWT 인증** | 로그인 → Access Token + Refresh Token 발급 |
| **역할 기반 접근** | admin, manager, editor, viewer 4단계 |
| **데모 모드** | `AUTH_ENABLED=false` 시 모든 API 공개 (AnonymousAdmin) |
| **프로덕션 보안** | JWT 시크릿 키 기본값 차단, 프로덕션 필수 설정 검증 |
| **토큰 갱신** | Refresh Token으로 Access Token 재발급 |

#### 권한 매트릭스

| 기능 | viewer | editor | manager | admin |
|------|--------|--------|---------|-------|
| 질의 | O | O | O | O |
| 시각화 | O | O | O | O |
| 그래프 편집 | X | O | O | O |
| 온톨로지 관리 | X | X | O | O |
| 데이터 수집 | X | X | O | O |
| GDS 분석 | X | X | O | O |
| 사용자 관리 | X | X | X | O |

---

## 4. 비기능 요구사항 (Non-Functional Requirements)

### 4.1 성능

| 항목 | 목표 |
|------|------|
| 첫 토큰 응답 시간 | ≤ 100ms (SSE 스트리밍) |
| 캐시 히트 응답 | ≤ 500ms (벡터 유사도 ≥ 0.93) |
| 파이프라인 전체 | ≤ 5s (캐시 미스, 일반 질의 기준) |
| 그래프 렌더링 | ≤ 200 노드까지 부드러운 인터랙션 |
| 파일 업로드 | 최대 100MB |

### 4.2 성능 최적화 전략

| 전략 | 설명 |
|------|------|
| **Intent + Entity 통합** | 2회 LLM 호출 → 1회로 통합 (~200ms 절감) |
| **Light/Heavy 모델** | 단순 질의는 gpt-4o-mini, 복잡 질의는 gpt-4o 자동 선택 (~400ms 절감) |
| **벡터 캐시** | 유사 질문 캐싱으로 반복 질의 즉시 응답 |
| **스키마 사전 로드** | 서버 시작 시 그래프 스키마 1회 로드 (매 질의마다 조회 X) |
| **비동기 처리** | FastAPI + asyncio 기반 논블로킹 I/O |

### 4.3 확장성

| 항목 | 설명 |
|------|------|
| 커넥션 풀 | Neo4j 최대 50 커넥션 (설정 가능) |
| 배치 처리 | 인제스트 동시성 5 (설정 가능) |
| 멀티 워커 | 각 워커가 자체 서비스 인스턴스 보유 |
| 커뮤니티 갱신 | 동시 실행 방지 (409 Conflict) |

### 4.4 보안

| 항목 | 설명 |
|------|------|
| CORS | 명시적 오리진 목록 (와일드카드와 credentials 혼용 방지) |
| Path Traversal | 프론트엔드 정적 파일 서빙 시 디렉토리 외부 접근 차단 |
| SQL Injection | Cypher 파라미터 바인딩 사용 (문자열 연결 X) |
| JWT 보안 | 프로덕션 기본 시크릿 키 차단, 만료 시간 설정 |
| 읽기 전용 쿼리 | 시각화 API는 READ-ONLY 쿼리만 허용 |
| 프로덕션 검증 | 환경이 production일 때 필수 설정 누락 시 서버 시작 차단 |

### 4.5 한국어 지원

| 항목 | 설명 |
|------|------|
| IME 처리 | React `onKeyDown`에서 `isComposing` 가드로 한국어 입력 중 실행 방지 |
| 접미사 제거 | "프로젝트", "팀", "부서" 등 한국어 접미사 자동 제거 후 매칭 |
| 대소문자 | `toLower()` 기반 일관된 매칭 (Cypher + Python 양쪽) |
| 프롬프트 | 파이프라인 단계 설명, 응답 생성 모두 한국어 지원 |

---

## 5. 사용자 인터페이스 (UI)

### 5.1 페이지 구성

```
/                    ── ChatPage (메인 질의 + 그래프 시각화)
/compare             ── ComparePage (인력 비교 분석)
/staffing            ── ProjectStaffingPage (프로젝트 인력 배치)
/admin
  ├── /overview      ── 시스템 대시보드
  ├── /ontology      ── 온톨로지 제안 관리
  ├── /ingest        ── 데이터 수집 관리
  ├── /analytics     ── GDS 분석 (커뮤니티, 유사도, 팀 추천)
  └── /graph-edit    ── 그래프 편집
```

### 5.2 ChatPage (메인 화면)

```
┌──────────────────────────────────────────────────┐
│  [Health ●] [Compare] [Staffing] [Admin] [Role▾] │
├─────────────────────┬────────────────────────────┤
│                     │                            │
│   Chat Panel        │    Graph Visualization     │
│                     │                            │
│   ┌──────────────┐  │    ┌──────────────────┐    │
│   │ Q: Python    │  │    │   ○ Employee      │    │
│   │    스킬 보유  │  │    │  / \              │    │
│   │    직원은?   │  │    │ ○   ○ Skill       │    │
│   │              │  │    │                    │    │
│   │ A: Python을  │  │    │     ● Project     │    │
│   │    보유한    │  │    │                    │    │
│   │    직원은... │  │    └──────────────────┘    │
│   └──────────────┘  │    [MiniMap]               │
│                     │                            │
│   [파이프라인 단계]  │    [Node Detail Panel]     │
│   ✓ 의도 분석      │                            │
│   ✓ 엔티티 추출    │                            │
│   ✓ Cypher 생성    │                            │
│   ✓ 응답 생성      │                            │
│                     │                            │
│   ┌──────────────┐  │                            │
│   │ 질문 입력... │  │                            │
│   └──────────────┘  │                            │
├─────────────────────┴────────────────────────────┤
```

### 5.3 상태 관리 (Zustand Stores)

| Store | 역할 |
|-------|------|
| `chatStore` | 메시지 목록, 세션 ID, 스트리밍 상태 |
| `graphStore` | 그래프 노드/엣지, 레이아웃 계산, 선택 상태 |
| `uiStore` | 사이드바 열기/닫기, 테마, 토스트 알림 |

---

## 6. API 명세 요약

### 6.1 엔드포인트 전체 목록

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/v1/query` | 자연어 질의 |
| POST | `/api/v1/query/stream` | SSE 스트리밍 질의 |
| GET | `/api/v1/health` | 헬스 체크 |
| GET | `/api/v1/schema` | DB 스키마 조회 |
| POST | `/api/v1/graph/nodes` | 노드 생성 |
| GET | `/api/v1/graph/nodes` | 노드 검색 |
| GET | `/api/v1/graph/nodes/{id}` | 노드 상세 |
| PATCH | `/api/v1/graph/nodes/{id}` | 노드 수정 |
| DELETE | `/api/v1/graph/nodes/{id}` | 노드 삭제 |
| GET | `/api/v1/graph/nodes/{id}/impact` | 삭제 영향 분석 |
| POST | `/api/v1/graph/edges` | 엣지 생성 |
| DELETE | `/api/v1/graph/edges/{id}` | 엣지 삭제 |
| POST | `/api/v1/visualization/subgraph` | 서브그래프 조회 |
| POST | `/api/v1/visualization/community` | 커뮤니티 시각화 |
| POST | `/api/v1/visualization/query-result` | 쿼리 결과 시각화 |
| POST | `/api/v1/visualization/query-path` | 쿼리 경로 시각화 |
| POST | `/api/v1/analytics/projection/create` | GDS 프로젝션 생성 |
| POST | `/api/v1/analytics/communities/detect` | 커뮤니티 탐지 |
| POST | `/api/v1/analytics/employees/similar` | 유사 직원 검색 |
| POST | `/api/v1/analytics/team/recommend` | 팀 구성 추천 |
| GET | `/api/v1/analytics/staffing/projects` | 프로젝트 목록 |
| POST | `/api/v1/analytics/staffing/find-candidates` | 후보 인력 검색 |
| POST | `/api/v1/analytics/staffing/plan` | 인력 배치 계획 |
| POST | `/api/v1/analytics/staffing/budget-analysis` | 예산 분석 |
| POST | `/api/v1/upload` | 파일 업로드 |
| POST | `/api/v1/ingest` | 인제스트 시작 |
| GET | `/api/v1/ingest/{job_id}` | 작업 상태 조회 |
| GET | `/api/v1/ontology/admin/proposals` | 온톨로지 제안 목록 |
| POST | `/api/v1/ontology/admin/proposals/{id}/approve` | 제안 승인 |
| POST | `/api/v1/ontology/admin/proposals/{id}/reject` | 제안 거절 |
| POST | `/api/v1/communities/refresh` | 커뮤니티 일괄 갱신 |
| GET | `/api/v1/communities/status` | 커뮤니티 상태 조회 |

---

## 7. 배포 및 인프라 (Deployment)

### 7.1 Docker Compose 구성

| 서비스 | 이미지 | 포트 | 설명 |
|--------|--------|------|------|
| `api` | 커스텀 빌드 | 8000 | FastAPI + uvicorn |
| `neo4j` | neo4j:latest | 7474 (브라우저), 7687 (Bolt) | GDS 플러그인 포함 |

### 7.2 Neo4j 리소스

| 설정 | 값 |
|------|-----|
| Heap (initial) | 512MB |
| Heap (max) | 1GB |
| Page Cache | 512MB |
| 플러그인 | graph-data-science (GDS) |

### 7.3 환경 변수

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `NEO4J_URI` | O | bolt://localhost:7687 | Neo4j Bolt URI |
| `NEO4J_USER` | O | neo4j | Neo4j 사용자명 |
| `NEO4J_PASSWORD` | O | - | Neo4j 비밀번호 |
| `AZURE_OPENAI_ENDPOINT` | O | - | Azure OpenAI 엔드포인트 |
| `AZURE_OPENAI_API_KEY` | △ | - | API 키 (Managed Identity 시 불필요) |
| `LIGHT_MODEL_DEPLOYMENT` | X | gpt-4o-mini | 경량 모델 배포명 |
| `HEAVY_MODEL_DEPLOYMENT` | X | gpt-4o | 중량 모델 배포명 |
| `AUTH_ENABLED` | X | false | 인증 활성화 |
| `ONTOLOGY_MODE` | X | yaml | 온톨로지 모드 |
| `ENVIRONMENT` | X | development | 실행 환경 |

---

## 8. 테스트 전략 (Testing)

### 8.1 테스트 현황

| 항목 | 값 |
|------|-----|
| 전체 테스트 수 | 1,004+ |
| 프레임워크 | pytest + httpx AsyncClient |
| 비동기 모드 | `asyncio_mode = "auto"` |
| 커버리지 영역 | Unit, Integration, API, Auth, Ontology |

### 8.2 테스트 전략

| 계층 | 방법 | 도구 |
|------|------|------|
| Unit | 개별 노드/서비스 테스트, mock 의존성 | pytest, mock fixtures |
| Integration | 파이프라인 전체 흐름 (mock LLM + mock Neo4j) | httpx AsyncClient |
| API | 라우트별 요청/응답 검증 | FastAPI TestClient |
| Frontend | 컴포넌트 단위 테스트 | Vitest |

### 8.3 테스트 네이밍 규칙

```
test_<행위>_<조건>

예시:
- test_find_candidates_filters_by_proficiency
- test_cypher_generator_handles_not_in_syntax
- test_auth_rejects_expired_token
```

---

## 9. 알려진 제약 및 향후 과제

### 9.1 알려진 제약

| 제약 | 영향 | 대응 |
|------|------|------|
| Employee 노드 중복 | 같은 직원이 여러 노드로 존재 | `e.name` 기반 그룹핑으로 우회 |
| Concept 대소문자 중복 | 'Python'/'python' 등 중복 쌍 23개+ | MERGE 수정 완료, 기존 데이터 정리 필요 |
| LLM Cypher 문법 오류 | NOT IN → NOT x IN 등 Neo4j 비호환 문법 | 후처리 자동 교정 + 프롬프트 강화 |
| GDS 동기 API | Neo4j GDS는 sync만 지원 | ThreadPoolExecutor로 async 래핑 |

### 9.2 향후 과제

| 과제 | 우선순위 | 설명 |
|------|----------|------|
| Employee 중복 제거 | 높음 | 동일인 노드 병합 스크립트 + 방지 제약 |
| 다국어 확장 | 중간 | 일본어/중국어 등 추가 언어 지원 |
| 성능 모니터링 | 중간 | 파이프라인 노드별 latency 대시보드 |
| RAG 평가 체계 | 높음 | 자동화된 답변 품질 평가 파이프라인 |
| 실시간 동기화 | 낮음 | HR 시스템(SAP, Workday) 연동 |

---

## 부록

### A. 용어 정의

| 용어 | 정의 |
|------|------|
| **Graph RAG** | 그래프 데이터베이스 + Retrieval-Augmented Generation |
| **Cypher** | Neo4j의 쿼리 언어 |
| **LangGraph** | LangChain 기반 상태 그래프 프레임워크 |
| **GDS** | Neo4j Graph Data Science 라이브러리 |
| **온톨로지** | 스킬/개념의 분류 체계 및 관계 정의 |
| **Two-Label 시스템** | Skill(데이터)과 Concept(분류)를 분리한 이중 라벨 구조 |
| **SSE** | Server-Sent Events (단방향 실시간 스트리밍) |
| **Checkpointer** | LangGraph 대화 기록 영속화 모듈 |
