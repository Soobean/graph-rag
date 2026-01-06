# Graph RAG 시스템 아키텍처 설계서

## 1. 개요

### 1.1 시스템 목적
Neo4j에 적재된 기업/조직 도메인 그래프 데이터(850개 노드, 5000개 엣지)를 활용하여 자연어 질문에 대해 그래프 기반 지식을 검색하고 LLM을 통해 자연스러운 답변을 생성하는 Graph RAG 시스템 구축

### 1.2 설계 원칙
1. **단순함 우선**: 복잡한 아키텍처 없이 검증된 패턴으로 시작
2. **점진적 확장**: MVP 먼저, 이후 기능 추가
3. **디버깅 용이성**: 각 단계의 입출력을 명확히 추적 가능하게
4. **그래프 특성 활용**: 관계 탐색이 핵심 가치
5. **LangGraph 기반**: 노드/엣지 그래프로 파이프라인 구성

---

## 2. 프로젝트 구조

### 2.1 폴더 구조

```
graph-rag/
├── src/
│   ├── __init__.py
│   ├── main.py                          # FastAPI 엔트리포인트
│   ├── dependencies.py                  # FastAPI Depends (DI)
│   ├── config.py                        # Pydantic Settings
│   │
│   ├── api/                             # [Presentation Layer]
│   │   ├── routes/
│   │   │   └── query.py                 # POST /query, GET /health, GET /schema
│   │   └── schemas/
│   │       └── query.py                 # QueryRequest, QueryResponse (Pydantic)
│   │
│   ├── graph/                           # [Graph Layer - LangGraph]
│   │   ├── state.py                     # GraphRAGState (TypedDict)
│   │   ├── pipeline.py                  # StateGraph 구성 + 라우팅 통합
│   │   └── nodes/                       # 노드 구현체
│   │       ├── intent_classifier.py     # 의도 분류
│   │       ├── entity_extractor.py      # 엔티티 추출
│   │       ├── schema_fetcher.py        # 스키마 조회 (병렬 실행)
│   │       ├── entity_resolver.py       # DB 엔티티 매칭
│   │       ├── clarification_handler.py # 명확화 요청 (동명이인 등)
│   │       ├── cypher_generator.py      # Cypher 생성
│   │       ├── graph_executor.py        # Neo4j 실행
│   │       └── response_generator.py    # 응답 생성 + 에러/빈결과 처리
│   │
│   ├── prompts/                         # [Prompt Templates]
│   │   ├── intent_classification.yaml
│   │   ├── entity_extraction.yaml
│   │   ├── cypher_generation.yaml
│   │   ├── response_generation.yaml
│   │   └── clarification.yaml
│   │
│   ├── repositories/                    # [Repository Layer]
│   │   ├── neo4j_repository.py          # Neo4j 데이터 접근 + 스키마 캐싱
│   │   └── llm_repository.py            # Azure OpenAI (openai SDK 직접 사용)
│   │
│   ├── infrastructure/                  # [Infrastructure Layer]
│   │   └── neo4j_client.py              # Neo4j 드라이버 (Neo4j 5.x+ 호환)
│   │
│   ├── utils/                           # [Utilities]
│   │   └── prompt_manager.py            # YAML 프롬프트 로더 + 캐싱
│   │
│   └── domain/                          # [Domain Models]
│       ├── types.py                     # TypedDict 정의 (노드 입출력)
│       └── exceptions.py                # 도메인 예외
│
├── tests/                               # 테스트 (167개)
│   ├── test_config.py
│   ├── test_nodes.py
│   ├── test_pipeline_integration.py
│   └── ...
│
├── scripts/
│   └── verify_pipeline.py               # 파이프라인 검증 스크립트
│
├── docs/
│   └── ARCHITECTURE.md
│
├── app_chainlit.py                      # Chainlit UI (파이프라인 시각화)
├── app_ui.py                            # Streamlit UI (간단한 채팅)
├── load_to_neo4j.py                     # Neo4j 데이터 로드 스크립트
├── .env.example                         # 환경변수 템플릿
├── .gitignore
└── pyproject.toml
```

### 2.2 레이어드 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                     Layered Architecture                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Presentation Layer (api/)                               │    │
│  │  - FastAPI 엔드포인트, Pydantic 스키마                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  DI Layer (dependencies.py)                              │    │
│  │  - FastAPI Depends + lru_cache 싱글톤                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Graph Layer (graph/)                                    │    │
│  │  - LangGraph 파이프라인, 노드 구현체, TypedDict State    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Repository Layer (repositories/)                        │    │
│  │  - 데이터 접근 추상화                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Infrastructure Layer (infrastructure/)                  │    │
│  │  - Neo4j Driver, Azure OpenAI Client                     │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 요구사항 분석

### 3.1 질문 유형 분류 및 그래프 탐색 패턴

| 유형 | 설명 | 예시 질문 | 그래프 탐색 패턴 | 복잡도 |
|------|------|----------|-----------------|--------|
| **A. 인력 추천** | 특정 조건에 맞는 직원 검색 | "Python과 ML 스킬을 가진 시니어 개발자는?" | `(e:Employee)-[:HAS_SKILL]->(s:Skill)` | 중 |
| **B. 프로젝트 매칭** | 프로젝트 요구사항과 인력 매칭 | "AI 프로젝트에 투입 가능한 인력은?" | `(p:Project)-[:REQUIRES]->(s:Skill)<-[:HAS_SKILL]-(e:Employee)` | 중 |
| **C. 관계 탐색** | 노드 간 연결 경로 탐색 | "김철수와 박영희의 업무적 연결고리는?" | `shortestPath((a)-[*]-(b))` | 고 |
| **D. 조직 분석** | 부서/팀 구조 및 역량 분석 | "개발팀의 평균 경력과 보유 스킬 분포는?" | `(d:Department)<-[:BELONGS_TO]-(e:Employee)-[:HAS_SKILL]->(s)` | 중 |
| **E. 멘토링 네트워크** | 멘토-멘티 관계 탐색 | "ML 분야 멘토링 가능한 시니어는?" | `(e:Employee)-[:MENTORS]->(), (e)-[:HAS_SKILL]->(s:Skill)` | 중 |
| **F. 자격증 기반 검색** | 인증/자격 기반 필터링 | "AWS 자격증 보유자 중 프로젝트 미배정자는?" | `(e:Employee)-[:HAS_CERTIFICATE]->(c:Certificate)` | 저 |
| **G. 경로 기반 분석** | 다중 홉 관계 분석 | "A 프로젝트 경험자 중 B 부서로 이동 가능한 인력은?" | Multi-hop traversal | 고 |

### 3.2 질문 유형별 상세 탐색 패턴

```cypher
-- [A. 인력 추천 패턴]
MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill)
WHERE s.name IN ['Python', 'ML']
WITH e, COUNT(s) as matchedSkills
WHERE matchedSkills >= 2
OPTIONAL MATCH (e)-[:BELONGS_TO]->(d:Department)
OPTIONAL MATCH (e)-[:HAS_POSITION]->(p:Position)
RETURN e, d, p

-- [B. 프로젝트 매칭 패턴]
MATCH (proj:Project {name: $projectName})-[:REQUIRES]->(s)
WITH proj, COLLECT(s) as requiredSkills
MATCH (e:Employee)-[:HAS_SKILL]->(skill)
WHERE skill IN requiredSkills
WITH e, COUNT(skill) as coverage, SIZE(requiredSkills) as total
RETURN e, coverage * 1.0 / total as matchRate ORDER BY matchRate DESC

-- [C. 관계 탐색 패턴]
MATCH path = shortestPath(
  (a:Employee {name: $name1})-[*..5]-(b:Employee {name: $name2})
)
RETURN path, LENGTH(path) as distance

-- [D. 조직 분석 패턴]
MATCH (d:Department {name: $deptName})<-[:BELONGS_TO]-(e)
OPTIONAL MATCH (e)-[:HAS_SKILL]->(s:Skill)
WITH d, e, COLLECT(s.name) as skills
RETURN d.name, COUNT(e), COLLECT(skills)
```

---

## 4. LangGraph 기반 시스템 아키텍처

### 3.1 State 스키마 정의

```python
from typing import TypedDict, Literal, Any, Annotated
import operator

IntentType = Literal[
    "personnel_search",      # A. 인력 추천
    "project_matching",      # B. 프로젝트 매칭
    "relationship_search",   # C. 관계 탐색
    "org_analysis",          # D. 조직 분석
    "mentoring_network",     # E. 멘토링 네트워크
    "certificate_search",    # F. 자격증 기반 검색
    "path_analysis",         # G. 경로 기반 분석
    "unknown"                # 분류 불가
]

class GraphRAGState(TypedDict, total=False):
    # 1. 입력 (Input)
    question: str
    session_id: str

    # 2. Query Understanding (의도 분석 및 엔티티 추출)
    intent: IntentType
    intent_confidence: float
    entities: dict[str, list[str]]  # {'Skill': ['Python'], 'Person': ['김철수']}

    # 3. Entity Resolution (검증 단계)
    # resolved_entities: id=None이면 미해결 엔티티
    resolved_entities: list[dict]  # [{"id": "SK001", "labels": ["Skill"], "original_value": "..."}]

    # 4. Graph Retrieval
    schema: dict  # {"node_labels": [...], "relationship_types": [...]}
    cypher_query: str
    cypher_parameters: dict[str, Any]
    graph_results: list[dict[str, Any]]
    result_count: int

    # 5. Context & Response
    context: str  # (미사용 - response_generator에서 직접 처리)
    response: str

    # 6. 메타데이터 및 에러 처리
    error: str | None

    # 실행 경로 추적 (Reducer 사용 - append 방식)
    execution_path: Annotated[list[str], operator.add]
```

### 3.2 LangGraph 노드 정의

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LangGraph Nodes                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Phase 1: 의도 분류]                                                       │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Node: intent_classifier                                    [LLM]    │   │
│  │ ─────────────────────────────────────────────────────────────────── │   │
│  │ 입력: question                                                       │   │
│  │ 출력: intent, intent_confidence                                      │   │
│  │ 역할: 질문 유형 분류 (7개 카테고리)                                  │   │
│  │ 모델: light_model_deployment (가벼운 분류 작업)                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [Phase 2: 병렬 실행 - Send API]                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Node: entity_extractor                                     [LLM]    │   │
│  │ ─────────────────────────────────────────────────────────────────── │   │
│  │ 입력: question                                                       │   │
│  │ 출력: entities (dict[str, list[str]])                                │   │
│  │ 역할: 스킬, 이름, 부서 등 엔티티 추출 (원본 텍스트)                   │   │
│  │ 모델: light_model_deployment (가벼운 추출 작업)                      │   │
│  │ 예시: "파이썬" → entities = {"Skill": ["파이썬"]}                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Node: schema_fetcher                                       [DB]     │   │
│  │ ─────────────────────────────────────────────────────────────────── │   │
│  │ 입력: (없음)                                                         │   │
│  │ 출력: schema (node_labels, relationship_types)                       │   │
│  │ 역할: Neo4j 스키마 조회 (TTL 캐싱 적용)                              │   │
│  │ 참고: entity_extractor와 병렬 실행 (Send API)                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [Phase 3: 엔티티 해석 - Fan-in]                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Node: entity_resolver                                      [DB]     │   │
│  │ ─────────────────────────────────────────────────────────────────── │   │
│  │ 입력: entities                                                       │   │
│  │ 출력: resolved_entities (list[dict])                                 │   │
│  │ 역할: 추출된 엔티티를 실제 DB 노드와 매칭                             │   │
│  │                                                                      │   │
│  │ 처리 로직:                                                           │   │
│  │   1. 정확 매칭: "Python" → {id: "SK001", ...}                        │   │
│  │   2. 퍼지 매칭: "파이썬" → {id: "SK001", ...}                        │   │
│  │   3. 동명이인/미해결: {id: None, original_value: "김철수", ...}      │   │
│  │                                                                      │   │
│  │ 출력 예시:                                                           │   │
│  │   resolved_entities = [                                              │   │
│  │     {"id": "SK001", "labels": ["Skill"], "original_value": "파이썬"} │   │
│  │   ]                                                                  │   │
│  │ 미해결시: {"id": None, "labels": ["Person"], "original_value": "..."}│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [Phase 4: Cypher 생성]                                                     │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Node: cypher_generator                                     [LLM]    │   │
│  │ ─────────────────────────────────────────────────────────────────── │   │
│  │ 입력: question, intent, resolved_entities, schema                    │   │
│  │ 출력: cypher_query, cypher_parameters                                │   │
│  │ 역할: 검증된 엔티티로 Cypher 쿼리 생성 (스키마 참조)                  │   │
│  │ 모델: heavy_model_deployment (복잡한 쿼리 생성)                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [Phase 5: 실행 및 응답]                                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Node: graph_executor                                       [DB]     │   │
│  │ ─────────────────────────────────────────────────────────────────── │   │
│  │ 입력: cypher_query, cypher_parameters                                │   │
│  │ 출력: graph_results, result_count                                    │   │
│  │ 역할: Neo4j에 Cypher 실행, 결과 반환                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Node: response_generator                                   [LLM]    │   │
│  │ ─────────────────────────────────────────────────────────────────── │   │
│  │ 입력: question, graph_results, cypher_query                          │   │
│  │ 출력: response                                                       │   │
│  │ 역할: LLM으로 최종 자연어 응답 생성                                   │   │
│  │       - 에러 상태: 사용자 친화적 에러 메시지                          │   │
│  │       - 빈 결과: "결과를 찾지 못했습니다" 응답                        │   │
│  │       - 정상: 쿼리 결과 기반 자연어 응답                              │   │
│  │ 모델: heavy_model_deployment (자연스러운 응답)                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [명확화 분기 노드]                                                         │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Node: clarification_handler                                [LLM]    │   │
│  │ ─────────────────────────────────────────────────────────────────── │   │
│  │ 입력: question, resolved_entities, entities                          │   │
│  │ 출력: response (명확화 요청)                                         │   │
│  │ 역할: 동명이인, 모호한 엔티티에 대해 사용자에게 확인 요청             │   │
│  │ 트리거: resolved_entities 중 id=None인 항목이 있을 때                │   │
│  │ 모델: light_model_deployment (간단한 응답)                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 LangGraph 엣지 정의

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LangGraph Edges                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  순차 시작 → 조건부 병렬 실행 (Send API)                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  START → intent_classifier                                                  │
│  intent_classifier → [entity_extractor, schema_fetcher] (Send API 병렬)     │
│                                                                             │
│  동기화 후 순차 실행 (Fan-in → Sequential)                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  [entity_extractor, schema_fetcher] → entity_resolver  # 둘 다 완료 후      │
│  entity_resolver → cypher_generator 또는 clarification_handler             │
│  cypher_generator → graph_executor 또는 response_generator                 │
│  graph_executor → response_generator                                        │
│  response_generator → END                                                   │
│  clarification_handler → END                                                │
│                                                                             │
│  조건부 엣지 (Conditional Edges)                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  1. intent_classifier 이후 분기 (병렬 실행 또는 종료):                       │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ def route_after_intent(state) -> list[Send] | str:              │    │
│     │     if state.get("intent") == "unknown":                        │    │
│     │         return "response_generator"  # 바로 종료 응답           │    │
│     │     # 병렬 실행: Send API 사용                                  │    │
│     │     return [                                                    │    │
│     │         Send("entity_extractor", state),                        │    │
│     │         Send("schema_fetcher", state),                          │    │
│     │     ]                                                           │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  2. entity_resolver 이후 분기 (미해결 엔티티 처리):                          │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ def route_after_resolver(state) -> str:                         │    │
│     │     if state.get("error"):                                      │    │
│     │         return "response_generator"                             │    │
│     │     # resolved_entities 중 id=None인 항목이 있으면 명확화 요청  │    │
│     │     has_unresolved = any(                                       │    │
│     │         not entity.get("id")                                    │    │
│     │         for entity in state.get("resolved_entities", [])        │    │
│     │     )                                                           │    │
│     │     if has_unresolved:                                          │    │
│     │         return "clarification_handler"                          │    │
│     │     return "cypher_generator"                                   │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  3. cypher_generator 이후 분기:                                             │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ def route_after_cypher(state) -> str:                           │    │
│     │     if state.get("error") or not state.get("cypher_query"):     │    │
│     │         return "response_generator"  # 에러 메시지 생성         │    │
│     │     return "graph_executor"                                     │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 LangGraph 전체 구조 (시각화)

```
                                      ┌─────────┐
                                      │  START  │
                                      └────┬────┘
                                           │
                                           ▼
                              ┌─────────────────────┐
                              │  intent_classifier  │
                              │  (질문 유형 분류)    │
                              │  [light_model]      │
                              └──────────┬──────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │ (Send API 병렬)    │                    │
                    ▼                    │                    ▼
         ┌─────────────────────┐         │         ┌─────────────────────┐
         │  entity_extractor   │         │         │   schema_fetcher    │
         │  (엔티티 추출)       │         │         │  (스키마 조회)       │
         │  [light_model]      │         │         │  [DB + 캐시]        │
         └──────────┬──────────┘         │         └──────────┬──────────┘
                    │                    │                    │
                    │              ┌─────┴─────┐              │
                    └──────────────┤  Fan-in   ├──────────────┘
                                   └─────┬─────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │   entity_resolver   │
                              │  (DB 엔티티 매칭)   │
                              │  "파이썬"→"Python"  │
                              └──────────┬──────────┘
                                         │
                          ┌──────────────┴──────────────┐
                          │ (id=None 있음)               │ (모두 해결됨)
                          ▼                              ▼
               ┌──────────────────┐           ┌─────────────────────┐
               │ clarification_   │           │  cypher_generator   │
               │ handler          │           │  (Cypher 생성)      │
               │ (동명이인/모호)  │           │  [heavy_model]      │
               │ [light_model]    │           └──────────┬──────────┘
               └────────┬─────────┘                      │
                        │                     ┌──────────┴──────────┐
                        │                     │ (에러/빈 쿼리)       │ (정상)
                        │                     │                      ▼
                        │                     │           ┌─────────────────────┐
                        │                     │           │   graph_executor    │
                        │                     │           │   (Neo4j 실행)      │
                        │                     │           └──────────┬──────────┘
                        │                     │                      │
                        │                     ▼                      ▼
                        │           ┌─────────────────────────────────────┐
                        │           │       response_generator            │
                        │           │  (응답 생성 + 에러/빈결과 처리)     │
                        │           │  [heavy_model]                      │
                        │           └──────────────────┬──────────────────┘
                        │                              │
                        ▼                              ▼
                   ┌─────────┐                    ┌─────────┐
                   │   END   │                    │   END   │
                   └─────────┘                    └─────────┘
```

### 3.5 LangGraph 코드 구조

```python
from langgraph.graph import StateGraph, END
from langgraph.types import Send

# 그래프 빌더 생성
workflow = StateGraph(GraphRAGState)

# ============================================
# 노드 추가
# ============================================

# Phase 1: 의도 분류
workflow.add_node("intent_classifier", intent_classifier)

# Phase 2: 병렬 실행 (Send API)
workflow.add_node("entity_extractor", entity_extractor)
workflow.add_node("schema_fetcher", schema_fetcher)

# Phase 3: 엔티티 해석 (Fan-in)
workflow.add_node("entity_resolver", entity_resolver)

# 명확화 분기
workflow.add_node("clarification_handler", clarification_handler)

# Phase 4-5: 쿼리 생성 및 실행
workflow.add_node("cypher_generator", cypher_generator)
workflow.add_node("graph_executor", graph_executor)
workflow.add_node("response_generator", response_generator)

# ============================================
# 엣지 정의
# ============================================

# 시작점
workflow.set_entry_point("intent_classifier")

# Phase 1 → Phase 2: 조건부 병렬 실행 (Send API)
def route_after_intent(state) -> list[Send] | str:
    if state.get("intent") == "unknown":
        return "response_generator"
    return [
        Send("entity_extractor", state),
        Send("schema_fetcher", state),
    ]

workflow.add_conditional_edges(
    "intent_classifier",
    route_after_intent,
    ["entity_extractor", "schema_fetcher", "response_generator"],
)

# Phase 2 → Phase 3: Fan-in
workflow.add_edge("entity_extractor", "entity_resolver")
workflow.add_edge("schema_fetcher", "entity_resolver")

# Phase 3 이후 분기: 미해결 엔티티 처리
def route_after_resolver(state) -> str:
    if state.get("error"):
        return "response_generator"
    has_unresolved = any(
        not entity.get("id")
        for entity in state.get("resolved_entities", [])
    )
    if has_unresolved:
        return "clarification_handler"
    return "cypher_generator"

workflow.add_conditional_edges(
    "entity_resolver",
    route_after_resolver,
    {
        "cypher_generator": "cypher_generator",
        "clarification_handler": "clarification_handler",
        "response_generator": "response_generator",
    },
)

# Phase 4 이후 분기: Cypher 생성 실패 처리
def route_after_cypher(state) -> str:
    if state.get("error") or not state.get("cypher_query"):
        return "response_generator"
    return "graph_executor"

workflow.add_conditional_edges(
    "cypher_generator",
    route_after_cypher,
    {
        "graph_executor": "graph_executor",
        "response_generator": "response_generator",
    },
)

# Phase 5: 순차 실행
workflow.add_edge("graph_executor", "response_generator")

# 종료 엣지
workflow.add_edge("clarification_handler", END)
workflow.add_edge("response_generator", END)

# 그래프 컴파일
graph = workflow.compile()
```

### 3.6 각 노드 상세 명세

| 노드 | 클래스명 | 입력 State 필드 | 출력 State 필드 | LLM/DB | 모델 티어 |
|------|----------|----------------|----------------|--------|-----------|
| **intent_classifier** | `IntentClassifierNode` | question | intent, intent_confidence | LLM | light_model |
| **entity_extractor** | `EntityExtractorNode` | question | entities (dict[str, list[str]]) | LLM | light_model |
| **schema_fetcher** | `SchemaFetcherNode` | - | schema | DB | - (캐싱) |
| **entity_resolver** | `EntityResolverNode` | entities | resolved_entities (list[dict]) | DB | - |
| **clarification_handler** | `ClarificationHandlerNode` | question, resolved_entities, entities | response | LLM | light_model |
| **cypher_generator** | `CypherGeneratorNode` | question, resolved_entities, schema | cypher_query, cypher_parameters | LLM | heavy_model |
| **graph_executor** | `GraphExecutorNode` | cypher_query, cypher_parameters | graph_results, result_count | DB | - |
| **response_generator** | `ResponseGeneratorNode` | question, graph_results, cypher_query, error | response | LLM | heavy_model |

### 3.7 Entity Resolver 상세 로직

```python
# src/graph/nodes/entity_resolver.py

async def entity_resolver(state: GraphRAGState) -> dict:
    """
    추출된 엔티티를 Neo4j DB의 실제 노드와 매칭

    매칭 전략:
    1. 정확 매칭 (Exact Match)
    2. 대소문자 무시 매칭 (Case-insensitive)
    3. 한글-영문 매핑 (Alias Match)
    4. 퍼지 매칭 (Fuzzy Match) - Levenshtein distance
    """
    entities = state.get("entities", {})
    resolved = {}
    unresolved = []

    # 스킬 매칭
    for skill in entities.get("skills", []):
        result = await resolve_skill(skill)
        if result["matched"]:
            resolved.setdefault("skills", []).append(result)
        else:
            unresolved.append(f"skill:{skill}")

    # 이름 매칭 (동명이인 처리)
    for name in entities.get("names", []):
        result = await resolve_employee(name)
        if result["matched"]:
            if result["ambiguous"]:  # 동명이인
                unresolved.append(f"name:{name} (후보: {result['candidates']})")
            else:
                resolved.setdefault("employees", []).append(result)
        else:
            unresolved.append(f"name:{name}")

    return {
        "resolved_entities": resolved,
        "unresolved_entities": unresolved if unresolved else None
    }


async def resolve_skill(raw_skill: str) -> dict:
    """스킬 엔티티 해석"""
    # 1. 정확 매칭
    query = """
    MATCH (s:Skill)
    WHERE s.name = $name OR s.name =~ $pattern
    RETURN s.id as id, s.name as name
    """
    # 한글-영문 별칭 테이블
    SKILL_ALIASES = {
        "파이썬": "Python",
        "자바": "Java",
        "자바스크립트": "JavaScript",
        "리액트": "React",
        "머신러닝": "ML",
        "딥러닝": "Deep Learning",
    }

    search_name = SKILL_ALIASES.get(raw_skill, raw_skill)
    pattern = f"(?i){search_name}"  # case-insensitive regex

    results = await neo4j_repo.execute_cypher(query, {"name": search_name, "pattern": pattern})

    if results:
        return {
            "matched": True,
            "raw": raw_skill,
            "resolved": results[0]["name"],
            "id": results[0]["id"]
        }
    return {"matched": False, "raw": raw_skill}
```

---

## 5. 핵심 설계 결정사항

### 4.1 자연어 → Cypher 변환 전략

#### 전략 비교

| 전략 | 장점 | 단점 | 적합한 경우 |
|------|------|------|------------|
| **LangChain GraphCypherQAChain** | 빠른 구현, 검증된 패턴 | 커스터마이징 제한, 에러 핸들링 어려움 | 빠른 PoC |
| **하이브리드 (템플릿 + LLM)** | 안정성 + 유연성 균형 | 템플릿 관리 필요 | **권장 (MVP)** |
| **순수 LLM 생성** | 최대 유연성 | 불안정, 잘못된 쿼리 위험 | 고급 사용자 |

#### 권장 전략: 하이브리드 접근 (LangGraph 노드에서 구현)

```
cypher_generator 노드 내부 로직:

                         ┌───────────────┐
                         │ intent 확인   │
                         └───────┬───────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
  ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
  │  Simple (A, F)    │ │  Medium (B, D, E) │ │  Complex (C, G)   │
  └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘
            │                     │                     │
            ▼                     ▼                     ▼
  ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
  │  Template Only    │ │  Template + LLM   │ │  LLM + Validation │
  └───────────────────┘ └───────────────────┘ └───────────────────┘
```

### 4.2 그래프 탐색 깊이 제한

| 질문 유형 | 최대 홉 수 | 이유 |
|-----------|-----------|------|
| 직접 관계 (스킬, 부서) | 1-2 홉 | 직접 연결된 정보만 필요 |
| 프로젝트 매칭 | 2-3 홉 | 프로젝트→스킬→직원 |
| 경로 탐색 | 5 홉 | 조직 내 합리적 연결 거리 |
| 멘토링 체인 | 4 홉 | 멘토→멘티→멘티 계층 |

### 4.3 벡터 검색 필요 여부

**MVP에서는 벡터 검색 불필요**

이유:
1. 규모가 작아 전체 탐색도 빠름 (ms 단위)
2. 구조화된 데이터 → 키워드/속성 매칭으로 충분
3. 추가 인프라 복잡도 증가

**향후 필요한 경우:**
- 노드 10,000개 이상으로 확장
- 프로젝트 설명, 스킬 상세 등 긴 텍스트 추가
- 유사도 기반 검색 필요 ("ML과 비슷한 스킬은?")

### 4.4 데이터 모델 선택: TypedDict vs Pydantic

**결정: 레이어별 적합한 도구 사용 (혼용)**

#### 용도별 구분

| 용도 | 선택 | 이유 |
|------|------|------|
| **LangGraph State** | TypedDict | LangGraph 네이티브, Annotated reducer 지원, 성능 최적화 |
| **API Request/Response** | Pydantic BaseModel | FastAPI 자동 검증, OpenAPI 문서 생성 |
| **설정 (Config)** | Pydantic Settings | 환경변수 자동 로딩, 타입 변환 |

#### 통일화하지 않는 이유

| 통일 방향 | 문제점 |
|----------|--------|
| 전부 TypedDict | FastAPI 자동 검증/문서화 기능 상실, 수동 검증 코드 필요 |
| 전부 Pydantic | LangGraph에서 `.model_dump()` 변환 필요, Annotated reducer 미지원 |

#### 레이어 경계에서의 변환

```
┌─────────────────────────────────────────────────────────────────┐
│                     데이터 모델 흐름                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [Client]                                                        │
│      │                                                           │
│      ▼ JSON                                                      │
│  ┌─────────────────┐                                             │
│  │ Pydantic        │  ← API 경계: 자동 검증 + 문서화             │
│  │ QueryRequest    │                                             │
│  └────────┬────────┘                                             │
│           │ request.question                                     │
│           ▼                                                      │
│  ┌─────────────────┐                                             │
│  │ TypedDict       │  ← LangGraph 내부: 네이티브 State           │
│  │ GraphRAGState   │                                             │
│  └────────┬────────┘                                             │
│           │ result["response"]                                   │
│           ▼                                                      │
│  ┌─────────────────┐                                             │
│  │ Pydantic        │  ← API 경계: 응답 직렬화                    │
│  │ QueryResponse   │                                             │
│  └─────────────────┘                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 구현 예시

```python
# graph/state.py - LangGraph State (TypedDict)
from typing import TypedDict, Literal, Annotated
import operator

class GraphRAGState(TypedDict, total=False):
    question: str
    intent: Literal["personnel_search", "project_matching", "unknown"]
    entities: dict
    cypher_query: str
    graph_results: list[dict]
    response: str
    error: str | None
    execution_path: Annotated[list[str], operator.add]  # reducer 지원


# api/schemas/request.py - API 요청 (Pydantic)
from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


# api/schemas/response.py - API 응답 (Pydantic)
class QueryResponse(BaseModel):
    answer: str
    intent: str | None = None
    cypher_query: str | None = None
    execution_time_ms: float | None = None


# api/routes/query.py - 변환 지점
@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, pipeline = Depends(get_graph_pipeline)):
    # Pydantic → TypedDict (한 줄 변환)
    state: GraphRAGState = {"question": request.question}

    result = await pipeline.ainvoke(state)

    # TypedDict → Pydantic (응답 생성)
    return QueryResponse(
        answer=result["response"],
        intent=result.get("intent"),
        cypher_query=result.get("cypher_query"),
    )
```

#### 설계 원칙

1. **경계 명확화**: API 레이어와 Graph 레이어의 경계에서만 변환
2. **각 도구의 강점 활용**: 통일화보다 적재적소 활용
3. **변환 비용 최소화**: 변환은 API 진입/퇴출 지점에서 한 번씩만

---

## 6. 노드 재사용성 설계

### 5.1 설계 철학

각 노드는 **독립적인 컴포넌트**로 설계하여 다른 프로젝트/도메인에서 재사용 가능하도록 합니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       노드 재사용성 계층 구조                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Layer 1: 범용 노드] - 어떤 RAG/LLM 파이프라인에서든 재사용                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  intent_classifier     │ 도메인 스키마만 변경하면 어디서든 사용       │   │
│  │  entity_extractor      │ 엔티티 타입 정의만 변경                      │   │
│  │  context_builder       │ 직렬화 포맷만 커스터마이징                   │   │
│  │  response_generator    │ 프롬프트 템플릿만 변경                       │   │
│  │  error_handler         │ 에러 메시지 포맷만 변경                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [Layer 2: Graph 특화 노드] - Graph DB 사용하는 시스템에서 재사용            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  cypher_generator      │ 스키마 + 템플릿 주입으로 재사용              │   │
│  │  graph_executor        │ DB 연결 정보만 변경 (Neo4j, Memgraph 등)    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [Layer 3: 도메인 특화 노드] - 특정 도메인용 (필요시 생성)                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  hr_recommender        │ 인력 추천 특화 로직                          │   │
│  │  project_matcher       │ 프로젝트 매칭 특화 로직                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 노드 인터페이스 표준

모든 노드는 다음 인터페이스를 따릅니다:

```python
from typing import Protocol, TypeVar, Any
from abc import abstractmethod

StateT = TypeVar("StateT", bound=dict)

class BaseNode(Protocol[StateT]):
    """모든 LangGraph 노드가 따라야 할 인터페이스"""

    @property
    def name(self) -> str:
        """노드 고유 이름"""
        ...

    @property
    def input_keys(self) -> list[str]:
        """필요한 State 필드 목록"""
        ...

    @property
    def output_keys(self) -> list[str]:
        """출력하는 State 필드 목록"""
        ...

    def __call__(self, state: StateT) -> dict[str, Any]:
        """
        노드 실행
        Args:
            state: 현재 그래프 상태
        Returns:
            업데이트할 State 필드들
        """
        ...

    def validate_input(self, state: StateT) -> bool:
        """입력 State 검증"""
        ...


class ConfigurableNode(BaseNode[StateT]):
    """설정 주입이 가능한 노드 베이스 클래스"""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @classmethod
    def from_yaml(cls, path: str) -> "ConfigurableNode":
        """YAML 설정 파일에서 노드 생성"""
        ...
```

### 5.3 의존성 주입 패턴

각 노드는 외부 의존성을 생성자에서 주입받습니다:

```python
# ============================================
# 예시: IntentClassifier 노드
# ============================================

class IntentClassifier(ConfigurableNode):
    """
    재사용 가능한 의도 분류 노드

    다른 도메인에서 사용 시:
    - intent_schema 변경
    - prompt_template 변경
    """

    def __init__(
        self,
        llm_client: BaseLLM,              # LLM 클라이언트 주입
        intent_schema: dict[str, str],    # 도메인별 의도 정의
        prompt_template: str,             # 프롬프트 템플릿
        confidence_threshold: float = 0.7
    ):
        self.llm = llm_client
        self.intent_schema = intent_schema
        self.prompt_template = prompt_template
        self.threshold = confidence_threshold

    @property
    def name(self) -> str:
        return "intent_classifier"

    @property
    def input_keys(self) -> list[str]:
        return ["question"]

    @property
    def output_keys(self) -> list[str]:
        return ["intent", "intent_confidence"]

    def __call__(self, state: dict) -> dict:
        question = state["question"]
        # LLM 호출하여 의도 분류
        result = self._classify(question)
        return {
            "intent": result["intent"],
            "intent_confidence": result["confidence"],
            "execution_path": [self.name]
        }


# ============================================
# 예시: CypherGenerator 노드
# ============================================

class CypherGenerator(ConfigurableNode):
    """
    재사용 가능한 Cypher 생성 노드

    다른 Graph DB 프로젝트에서 사용 시:
    - graph_schema 변경
    - cypher_templates 변경
    """

    def __init__(
        self,
        llm_client: BaseLLM,
        graph_schema: GraphSchema,           # 그래프 스키마 주입
        cypher_templates: dict[str, str],    # 의도별 Cypher 템플릿
        use_hybrid: bool = True              # 템플릿 + LLM 하이브리드
    ):
        self.llm = llm_client
        self.schema = graph_schema
        self.templates = cypher_templates
        self.use_hybrid = use_hybrid

    @property
    def name(self) -> str:
        return "cypher_generator"

    @property
    def input_keys(self) -> list[str]:
        return ["question", "intent", "entities"]

    @property
    def output_keys(self) -> list[str]:
        return ["cypher_query"]


# ============================================
# 예시: GraphExecutor 노드
# ============================================

class GraphExecutor(ConfigurableNode):
    """
    재사용 가능한 그래프 실행 노드

    다른 Graph DB에서 사용 시:
    - db_client 변경 (Neo4j, Memgraph, Neptune 등)
    """

    def __init__(
        self,
        db_client: BaseGraphDB,    # DB 클라이언트 주입
        max_results: int = 100,
        timeout_seconds: int = 30
    ):
        self.db = db_client
        self.max_results = max_results
        self.timeout = timeout_seconds
```

### 5.4 설정 파일 구조

노드 설정을 외부 파일로 분리:

```yaml
# config/graph_rag_config.yaml

# LLM 설정 (Azure OpenAI - 모델 버전 비의존적)
llm:
  provider: "azure_openai"
  azure_endpoint: "${AZURE_OPENAI_ENDPOINT}"
  api_version: "${AZURE_OPENAI_API_VERSION}"  # 예: 2024-10-21

  # 배포 이름 (특정 모델 버전이 아닌 Azure Portal 배포 이름)
  light_model_deployment: "${AZURE_OPENAI_LIGHT_MODEL_DEPLOYMENT}"  # 가벼운 작업용
  heavy_model_deployment: "${AZURE_OPENAI_HEAVY_MODEL_DEPLOYMENT}"  # 복잡한 작업용

  # 공통 파라미터
  temperature: 0.0
  max_tokens: 2000

# Graph DB 설정
database:
  type: "neo4j"
  uri: "bolt://localhost:7687"
  auth:
    user: "neo4j"
    password: "${NEO4J_PASSWORD}"  # 환경변수 참조

# 의도 스키마 (도메인별 변경)
intent_schema:
  personnel_search: "특정 조건에 맞는 직원 검색"
  project_matching: "프로젝트 요구사항과 인력 매칭"
  relationship_search: "직원 간 연결 경로 탐색"
  org_analysis: "부서/팀 구조 및 역량 분석"
  mentoring_network: "멘토-멘티 관계 탐색"
  certificate_search: "자격증 기반 인력 필터링"
  path_analysis: "다중 홉 관계 분석"

# 그래프 스키마 (도메인별 변경)
graph_schema:
  nodes:
    - label: "Employee"
      properties: ["id", "name", "email", "job_type", "years_experience"]
    - label: "Skill"
      properties: ["id", "name", "category", "difficulty"]
    - label: "Project"
      properties: ["id", "name", "type", "status"]
    - label: "Department"
      properties: ["id", "name", "head_count"]
  relationships:
    - type: "HAS_SKILL"
      from: "Employee"
      to: "Skill"
      properties: ["proficiency", "years_used"]
    - type: "WORKS_ON"
      from: "Employee"
      to: "Project"
      properties: ["role", "contribution_percent"]
    - type: "BELONGS_TO"
      from: "Employee"
      to: "Department"

# Cypher 템플릿 (의도별)
cypher_templates:
  personnel_search: |
    MATCH (e:Employee)-[r:HAS_SKILL]->(s:Skill)
    WHERE s.name IN $skills
    RETURN e, COLLECT(s) as skills
    LIMIT $limit

  project_matching: |
    MATCH (p:Project)-[:REQUIRES]->(s:Skill)
    WHERE p.name CONTAINS $project_keyword
    WITH p, COLLECT(s) as required
    MATCH (e:Employee)-[:HAS_SKILL]->(skill)
    WHERE skill IN required
    RETURN e, p, COUNT(skill) as match_count
```

### 5.6 노드 독립 테스트

각 노드는 독립적으로 테스트 가능:

```python
# tests/test_nodes/test_intent_classifier.py

import pytest
from unittest.mock import Mock
from src.nodes.intent_classifier import IntentClassifier

class TestIntentClassifier:
    """IntentClassifier 노드 단위 테스트"""

    @pytest.fixture
    def mock_llm(self):
        llm = Mock()
        llm.invoke.return_value = {
            "intent": "personnel_search",
            "confidence": 0.95
        }
        return llm

    @pytest.fixture
    def classifier(self, mock_llm):
        return IntentClassifier(
            llm_client=mock_llm,
            intent_schema={"personnel_search": "인력 검색"},
            prompt_template="Classify: {question}"
        )

    def test_input_keys(self, classifier):
        assert classifier.input_keys == ["question"]

    def test_output_keys(self, classifier):
        assert classifier.output_keys == ["intent", "intent_confidence"]

    def test_classify_personnel_search(self, classifier):
        state = {"question": "Python 개발자 찾아줘"}
        result = classifier(state)

        assert result["intent"] == "personnel_search"
        assert result["intent_confidence"] >= 0.7

    def test_validate_input_missing_question(self, classifier):
        state = {}
        assert classifier.validate_input(state) == False


# tests/test_nodes/test_graph_executor.py

class TestGraphExecutor:
    """GraphExecutor 노드 단위 테스트"""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.execute.return_value = [
            {"e": {"name": "김철수"}, "skills": ["Python", "ML"]}
        ]
        return db

    @pytest.fixture
    def executor(self, mock_db):
        return GraphExecutor(db_client=mock_db, max_results=10)

    def test_execute_valid_cypher(self, executor):
        state = {"cypher_query": "MATCH (e:Employee) RETURN e LIMIT 5"}
        result = executor(state)

        assert "graph_results" in result
        assert result["result_count"] == 1

    def test_execute_invalid_cypher(self, executor, mock_db):
        mock_db.execute.side_effect = Exception("Syntax error")
        state = {"cypher_query": "INVALID QUERY"}
        result = executor(state)

        assert "error" in result
```

---

## 7. 구현 우선순위

### 6.1 MVP 단계 (Phase 1) - 4주

**Week 1-2: Core Pipeline (LangGraph)**
- [P0] LangGraph StateGraph 구조 설정
- [P0] intent_classifier, entity_extractor 노드 구현
- [P0] cypher_generator 노드 (기본 템플릿 5개)
- [P0] graph_executor 노드 (Neo4j 연결)

**Week 3: Generation & Error Handling**
- [P0] context_builder 노드
- [P0] response_generator 노드
- [P1] error_handler, empty_result_handler 노드
- [P1] 조건부 엣지 라우팅 로직

**Week 4: Integration & Testing**
- [P0] End-to-end 테스트
- [P1] 기본 CLI/API 인터페이스 (FastAPI)
- [P2] 실행 경로 로깅

**MVP 지원 질문 유형:**
- [O] A. 인력 추천 (스킬 기반)
- [O] B. 프로젝트 매칭 (단순)
- [O] D. 조직 분석 (부서별 통계)
- [O] F. 자격증 기반 검색

### 6.2 Phase 2 - 확장 기능 (4-6주)

- 관계 탐색 (shortestPath, allPaths) - C, G 유형
- 멘토링 네트워크 탐색 - E 유형
- 복합 질문 분해 노드 추가
- 대화 히스토리 (State 확장)
- 결과 시각화

### 6.3 Phase 3 - 고급 기능

- 벡터 검색 통합 노드
- Human-in-the-loop (LangGraph interrupt)
- 권한 기반 데이터 필터링

---

## 8. 기술 스택

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

### 7.1 모델 버전 호환성 전략

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

### 7.2 LangGraph 1.0 호환성

> **참고**: 본 문서의 모든 LangGraph 코드는 1.0+ 기준으로 작성되었습니다. (섹션 3.5 참조)

**LangGraph 1.0 주요 변경사항:**
| 항목 | 0.x (레거시) | 1.0+ (현재) |
|------|-------------|-------------|
| Import | `from langgraph.graph import StateGraph` | `from langgraph.graph import StateGraph, START, END` |
| 반환 타입 | `CompiledGraph` | `CompiledStateGraph` |
| 시작점 | `"__start__"` 문자열 | `START` 상수 |
| 종료점 | `"__end__"` 문자열 | `END` 상수 |
| 병렬 실행 | 암시적 fan-out | 명시적 다중 edge |

### 7.3 버전 호환성 매트릭스

| 컴포넌트 | 최소 버전 | 권장 버전 | 비고 |
|----------|----------|----------|------|
| Python | 3.11 | 3.12+ | async/typing 개선 |
| LangGraph | 1.0.0 | 최신 1.x | 정식 API 안정성 |
| FastAPI | 0.100+ | 최신 | Pydantic v2 호환 |
| Neo4j | 5.0+ | 5.x | 기존 데이터 호환 |
| Azure OpenAI SDK | 1.0+ | 최신 | API 버전 독립적 |

---

## 9. 성공 지표 (MVP)

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| Cypher 생성 정확도 | > 80% | 테스트 셋 기준 |
| 응답 정확도 | > 85% | 수동 평가 (100개 샘플) |
| 평균 응답 시간 | < 5초 | P50 기준 |
| 지원 질문 유형 커버리지 | 4/7 유형 | A, B, D, F 유형 |

---

## 10. 보안 요구사항

### 9.1 인증 및 권한

| 구분 | 방식 | 설명 |
|------|------|------|
| **API 인증** | API Key + JWT | 클라이언트별 API Key 발급, JWT로 세션 관리 |
| **Neo4j 인증** | 환경변수 기반 | `NEO4J_USER`, `NEO4J_PASSWORD` 환경변수 사용 |
| **Azure OpenAI 인증** | Managed Identity 또는 API Key | 프로덕션은 Managed Identity 권장 |

### 9.2 데이터 접근 제어

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

### 9.3 민감 데이터 처리

| 데이터 유형 | 처리 방식 |
|------------|----------|
| 직원 개인정보 (이메일, 연락처) | 마스킹 처리 후 응답 |
| 급여/평가 정보 | 관리자 권한만 접근 가능 |
| LLM 프롬프트 로깅 | 개인정보 제거 후 저장 |

### 9.4 감사 로깅

```python
# 감사 로그 스키마
class AuditLog(BaseModel):
    timestamp: datetime
    user_id: str
    action: str  # "query", "export", "admin_access"
    resource: str  # 접근한 데이터 유형
    query_hash: str  # 쿼리 해시 (전문 미저장)
    result_count: int
    ip_address: str
```

---

## 11. 에러 핸들링 상세

### 10.1 에러 유형 분류

| 에러 유형 | 코드 | 재시도 | 사용자 메시지 |
|----------|------|--------|--------------|
| **LLM API 실패** | E001 | 최대 3회 (지수 백오프) | "잠시 후 다시 시도해주세요" |
| **LLM Rate Limit** | E002 | 60초 대기 후 1회 | "요청이 많습니다. 잠시 후 시도해주세요" |
| **Neo4j 연결 실패** | E003 | 최대 2회 | "시스템 점검 중입니다" |
| **Cypher 문법 오류** | E004 | 재시도 없음 | "질문을 이해하지 못했습니다. 다시 표현해주세요" |
| **쿼리 타임아웃** | E005 | 재시도 없음 | "복잡한 질문입니다. 더 구체적으로 질문해주세요" |
| **빈 결과** | E006 | 재시도 없음 | "조건에 맞는 결과가 없습니다" |
| **권한 없음** | E007 | 재시도 없음 | "해당 정보에 접근 권한이 없습니다" |

### 10.2 재시도 정책

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

# Neo4j 재시도 설정
@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(ServiceUnavailable)
)
async def execute_cypher(query: str) -> list:
    ...
```

### 10.3 Fallback 전략

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

## 12. 성능 요구사항 상세

### 11.1 레이턴시 목표

| 지표 | 목표 | 알림 임계값 |
|------|------|------------|
| **P50 응답시간** | < 3초 | - |
| **P95 응답시간** | < 5초 | > 7초 시 경고 |
| **P99 응답시간** | < 10초 | > 15초 시 알림 |

### 11.2 노드별 타임아웃 설정

| 노드 | 타임아웃 | 비고 |
|------|---------|------|
| intent_classifier | 5초 | LLM 호출 포함 |
| entity_extractor | 5초 | LLM 호출 포함 |
| cypher_generator | 10초 | 복잡한 쿼리 생성 고려 |
| graph_executor | 30초 | 복잡한 경로 탐색 고려 |
| response_generator | 10초 | LLM 호출 포함 |
| **전체 파이프라인** | 60초 | 모든 노드 합계 |

### 11.3 동시성 및 처리량

| 지표 | MVP 목표 | Phase 2 목표 |
|------|---------|-------------|
| 동시 요청 처리 | 10 RPS | 50 RPS |
| 최대 동시 접속자 | 20명 | 100명 |
| LLM 동시 호출 | 5개 | 20개 (Rate Limit 고려) |

### 11.4 리소스 제한

```python
# FastAPI 설정
app = FastAPI()

# 동시 요청 제한
semaphore = asyncio.Semaphore(10)

@app.middleware("http")
async def limit_concurrency(request: Request, call_next):
    async with semaphore:
        response = await call_next(request)
    return response

# 요청별 타임아웃
@app.post("/query")
async def query(request: QueryRequest):
    try:
        async with asyncio.timeout(60):
            return await process_query(request)
    except asyncio.TimeoutError:
        raise HTTPException(408, "Request timeout")
```

---

## 13. 평가 체계

### 12.1 평가 데이터셋 구성

| 질문 유형 | 샘플 수 | 난이도 분포 |
|----------|--------|------------|
| A. 인력 추천 | 30개 | 쉬움 10, 중간 15, 어려움 5 |
| B. 프로젝트 매칭 | 25개 | 쉬움 8, 중간 12, 어려움 5 |
| D. 조직 분석 | 25개 | 쉬움 10, 중간 10, 어려움 5 |
| F. 자격증 검색 | 20개 | 쉬움 10, 중간 8, 어려움 2 |
| **합계** | **100개** | |

### 12.2 평가 기준

```yaml
# 평가 루브릭
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

  factual_correctness:
    description: "응답 내용이 그래프 데이터와 일치하는가"
    scoring:
      - 0: "Hallucination 포함"
      - 1: "모든 정보가 그래프 데이터 기반"
```

### 12.3 자동 평가 메트릭

```python
# 자동 평가 메트릭
class AutoMetrics:
    @staticmethod
    def cypher_syntax_valid(cypher: str) -> bool:
        """Cypher 문법 검증"""
        try:
            parse_cypher(cypher)
            return True
        except SyntaxError:
            return False

    @staticmethod
    def result_count_match(expected: int, actual: int) -> float:
        """결과 개수 일치율"""
        if expected == 0:
            return 1.0 if actual == 0 else 0.0
        return min(actual / expected, expected / actual)

    @staticmethod
    def entity_coverage(question_entities: list, response: str) -> float:
        """질문의 엔티티가 응답에 포함된 비율"""
        covered = sum(1 for e in question_entities if e in response)
        return covered / len(question_entities) if question_entities else 1.0
```

### 12.4 평가 프로세스

```
┌─────────────────────────────────────────────────────────────────┐
│                     평가 프로세스                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 자동 평가 (CI/CD 파이프라인)                                 │
│     ├── Cypher 문법 검증                                        │
│     ├── 결과 개수 일치 확인                                     │
│     └── 응답 시간 측정                                          │
│                                                                  │
│  2. 수동 평가 (주 1회, 2명 평가자)                               │
│     ├── 무작위 20개 샘플 추출                                   │
│     ├── 독립적 점수 부여                                        │
│     ├── Cohen's Kappa로 평가자 간 신뢰도 측정                   │
│     └── 불일치 시 합의 도출                                     │
│                                                                  │
│  3. 결과 리포팅                                                  │
│     ├── 주간 성능 대시보드 업데이트                             │
│     └── 목표 미달 시 개선 태스크 생성                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 14. 배포 및 운영 환경

### 13.1 컨테이너화

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 의존성 설치
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

# 애플리케이션 복사
COPY src/ ./src/
COPY config/ ./config/

# 헬스체크
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
      - NEO4J_USER=${NEO4J_USER}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
      - AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}
    depends_on:
      - neo4j
    restart: unless-stopped

  neo4j:
    image: neo4j:5.15
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data
    environment:
      - NEO4J_AUTH=${NEO4J_USER}/${NEO4J_PASSWORD}

volumes:
  neo4j_data:
```

### 13.2 환경별 설정

| 환경 | 용도 | LLM 배포 전략 | 로깅 레벨 |
|------|------|--------------|----------|
| **dev** | 로컬 개발 | light: 저비용 모델, heavy: 저비용 모델 | DEBUG |
| **staging** | 통합 테스트 | light: 저비용 모델, heavy: 고성능 모델 | INFO |
| **prod** | 운영 | light: 저비용 모델, heavy: 고성능 모델 | WARNING |

> **참고**: 실제 모델 버전(gpt-35-turbo, gpt-4, gpt-4o, gpt-5.x 등)은 Azure Portal 배포 이름으로 추상화됩니다.
> 환경변수 `AZURE_OPENAI_LIGHT_MODEL_DEPLOYMENT`, `AZURE_OPENAI_HEAVY_MODEL_DEPLOYMENT`로 설정합니다.

### 13.3 CI/CD 파이프라인

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run tests
        run: poetry run pytest --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4

  deploy-staging:
    needs: test
    if: github.ref == 'refs/heads/develop'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Staging
        run: |
          # Azure Container Apps 또는 AKS 배포

  deploy-prod:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy to Production
        run: |
          # 프로덕션 배포 (수동 승인 필요)
```

### 13.4 헬스체크 엔드포인트

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
    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks
    }

@app.get("/health/live")
async def liveness_check():
    """프로세스 생존 확인"""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
```

---

## 15. 캐싱 전략

### 14.1 캐싱 레이어

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

### 14.2 캐시 구현

```python
from functools import lru_cache
import hashlib
from cachetools import TTLCache

# 인메모리 캐시 (MVP)
response_cache = TTLCache(maxsize=1000, ttl=3600)  # 1시간
cypher_cache = TTLCache(maxsize=500, ttl=300)      # 5분

def cache_key(question: str) -> str:
    return hashlib.sha256(question.encode()).hexdigest()

async def get_cached_response(question: str) -> Optional[str]:
    key = cache_key(question)
    if key in response_cache:
        response_cache[key]["hit_count"] += 1
        return response_cache[key]["response"]
    return None

async def set_cached_response(question: str, response: str):
    key = cache_key(question)
    response_cache[key] = {
        "response": response,
        "timestamp": datetime.utcnow(),
        "hit_count": 0
    }
```

### 14.3 캐시 무효화 전략

| 이벤트 | 무효화 범위 |
|--------|------------|
| 그래프 데이터 업데이트 | L2, L3 전체 무효화 |
| 스키마 변경 | 전체 캐시 무효화 |
| TTL 만료 | 개별 항목 자동 삭제 |
| 수동 무효화 API | 지정된 키 또는 패턴 삭제 |

---

## 16. 모니터링 및 관측성

### 15.1 메트릭 수집

```python
from prometheus_client import Counter, Histogram, Gauge

# 요청 메트릭
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

# 시스템 메트릭
CACHE_HIT_RATE = Gauge(
    'graph_rag_cache_hit_rate',
    'Cache hit rate',
    ['cache_type']
)

LLM_TOKEN_USAGE = Counter(
    'graph_rag_llm_tokens_total',
    'LLM token usage',
    ['model', 'type']  # type: prompt, completion
)
```

### 15.2 로깅 표준

```python
import structlog

logger = structlog.get_logger()

# 구조화된 로깅
logger.info(
    "query_processed",
    question=question[:100],  # 개인정보 제거를 위해 잘림
    intent=state["intent"],
    latency_ms=elapsed_ms,
    result_count=state["result_count"],
    cache_hit=cache_hit,
    request_id=request_id
)

# 로그 레벨 가이드
# DEBUG: 개발 디버깅 (프로덕션 미사용)
# INFO: 정상 처리 흐름
# WARNING: 재시도, 성능 저하
# ERROR: 처리 실패, 사용자 영향
# CRITICAL: 시스템 장애
```

### 15.3 분산 추적

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# OpenTelemetry 설정
tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("process_query")
async def process_query(question: str):
    with tracer.start_as_current_span("intent_classification"):
        intent = await classify_intent(question)

    with tracer.start_as_current_span("entity_extraction"):
        entities = await extract_entities(question)

    with tracer.start_as_current_span("cypher_generation"):
        cypher = await generate_cypher(question, intent, entities)

    # ... 추적 계속
```

### 15.4 알림 규칙

| 조건 | 심각도 | 알림 채널 |
|------|--------|----------|
| P99 레이턴시 > 15초 (5분간) | Warning | Slack |
| 에러율 > 5% (10분간) | Critical | Slack + PagerDuty |
| Neo4j 연결 실패 | Critical | Slack + PagerDuty |
| LLM API 연속 실패 3회 | Warning | Slack |
| 캐시 히트율 < 20% | Info | Slack (일간 리포트) |

### 15.5 대시보드 구성

```yaml
# Grafana 대시보드 패널 구성
panels:
  - title: "Request Rate"
    type: graph
    query: rate(graph_rag_requests_total[5m])

  - title: "Latency Percentiles"
    type: graph
    query: |
      histogram_quantile(0.5, rate(graph_rag_request_latency_seconds_bucket[5m]))
      histogram_quantile(0.95, rate(graph_rag_request_latency_seconds_bucket[5m]))
      histogram_quantile(0.99, rate(graph_rag_request_latency_seconds_bucket[5m]))

  - title: "Error Rate by Intent"
    type: graph
    query: |
      sum(rate(graph_rag_requests_total{status="error"}[5m])) by (intent)
      / sum(rate(graph_rag_requests_total[5m])) by (intent)

  - title: "LLM Token Usage"
    type: stat
    query: sum(increase(graph_rag_llm_tokens_total[24h]))

  - title: "Cache Hit Rate"
    type: gauge
    query: graph_rag_cache_hit_rate
```

---

## 16. UI 옵션

### 16.1 Chainlit UI (권장)

파이프라인 실행 단계를 시각적으로 보여주는 대화형 UI

```bash
# 실행
chainlit run app_chainlit.py --port 8080
```

**특징:**
- 각 파이프라인 노드를 Step으로 시각화
- 중간 결과 확인 (Intent, Entity, Cypher 등)
- 실시간 스트리밍 지원
- Cypher 쿼리 syntax highlighting

**Step 표시:**
```
🎯 Intent Classification  → intent: personnel_search (0.85)
🔍 Entity Extraction      → Skill: ["Python", "SQL"]
📊 Schema Fetch           → 8 labels, 9 relationships
🔗 Entity Resolution      → ✅ Python, ✅ SQL
⚙️ Cypher Generation      → MATCH (e:Employee)...
🗃️ Graph Query            → 5 results found
💬 Response Generation    → 최종 응답
```

### 16.2 Streamlit UI (간단한 버전)

```bash
# 실행
streamlit run app_ui.py --server.port 8501
```

### 16.3 FastAPI REST API

```bash
# 실행
uvicorn src.main:app --reload --port 8000

# 엔드포인트
POST /api/v1/query    # 질문 처리
GET  /api/v1/health   # 헬스 체크
GET  /api/v1/schema   # 스키마 조회
```

---

## 17. 호환성 노트

### 17.1 Neo4j 5.x+ 호환성

**elementId() 사용:**
- Neo4j 5.x에서 `id()` 함수가 deprecated
- 모든 쿼리에서 `elementId()` 사용
- ID 타입이 `int` → `str`로 변경

```python
# Before (deprecated)
RETURN id(n) as id

# After (Neo4j 5.x+)
RETURN elementId(n) as id
```

**NodeResult 타입 변경:**
```python
@dataclass
class NodeResult:
    id: str  # elementId() 반환값 (문자열)
    labels: list[str]
    properties: dict[str, Any]
```

### 17.2 GPT-5 모델 호환성

GPT-5 이상 모델은 `temperature` 파라미터를 지원하지 않음:

```python
def _supports_temperature(self, deployment: str) -> bool:
    """모델이 temperature를 지원하는지 확인"""
    return not deployment.lower().startswith("gpt-5")

# API 호출 시 조건부 파라미터 추가
api_params = {"model": deployment, "messages": messages}
if self._supports_temperature(deployment):
    api_params["temperature"] = temperature
```

### 17.3 인증 방식 (Neo4j 2025.x)

Neo4j 2025.x 서버는 명시적 `basic_auth()` 사용 필요:

```python
from neo4j import basic_auth

# Before
driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

# After (Neo4j 2025.x)
driver = AsyncGraphDatabase.driver(uri, auth=basic_auth(user, password))
```

---

**문서 작성일**: 2026-01-06
**버전**: 2.2 (UI 옵션, Neo4j 5.x/GPT-5 호환성 추가)
