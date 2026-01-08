# 4. LangGraph 기반 시스템 아키텍처

> ⭐ **핵심 문서**: 파이프라인의 핵심 구조를 설명합니다.

## 4.1 State 스키마 정의

```python
from typing import TypedDict, Literal, Any, Annotated
import operator

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

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
    messages: Annotated[list[BaseMessage], add_messages]  # 대화 기록 (LangGraph Native)
    question: str
    session_id: str

    # 2. Query Understanding
    intent: IntentType
    intent_confidence: float
    entities: dict[str, list[str]]

    # 3. Entity Resolution
    resolved_entities: list[dict]

    # 4. Graph Retrieval
    schema: dict
    cypher_query: str
    cypher_parameters: dict[str, Any]
    graph_results: list[dict[str, Any]]
    result_count: int

    # 5. Response
    response: str
    error: str | None
    execution_path: Annotated[list[str], operator.add]
```

## 4.1.1 Chat History (대화 기록 관리)

LangGraph의 `MemorySaver` Checkpointer와 `add_messages` reducer를 활용하여 세션별 대화 기록을 자동 관리합니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Chat History 아키텍처                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ MemorySaver Checkpointer                                            │   │
│  │ • 세션별 state 자동 저장/복원 (thread_id 기반)                      │   │
│  │ • In-Memory 저장 (MVP 단계)                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ add_messages Reducer                                                │   │
│  │ • HumanMessage: 사용자 질문                                          │   │
│  │ • AIMessage: 어시스턴트 응답                                         │   │
│  │ • 자동 누적 및 중복 제거 (message.id 기반)                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  [흐름]                                                                     │
│  run(question, session_id)                                                  │
│      ├─ 1. initial_state.messages = [HumanMessage(question)]               │
│      ├─ 2. Checkpointer: 이전 세션 state 복원                              │
│      ├─ 3. response_generator: format_chat_history(messages[:-1])          │
│      └─ 4. 파이프라인 종료: aupdate_state로 AIMessage 저장                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**사용 예시:**
```python
# 첫 번째 질문
result1 = await pipeline.run("홍길동의 부서는?", session_id="user-123")

# 두 번째 질문 (같은 session_id)
result2 = await pipeline.run("그 사람의 직급은?", session_id="user-123")
# → LLM이 "그 사람" = "홍길동"으로 이해
```

---

## 4.2 LangGraph 노드 정의

| 노드 | 역할 | 입력 | 출력 | 모델 |
|------|------|------|------|------|
| **intent_classifier** | 질문 유형 분류 | question | intent, confidence | light |
| **entity_extractor** | 엔티티 추출 | question | entities | light |
| **schema_fetcher** | 스키마 조회 (병렬) | - | schema | DB |
| **entity_resolver** | DB 엔티티 매칭 | entities | resolved_entities | DB |
| **cache_checker** | Vector 캐시 조회 | question | cypher_query (캐시 히트) | embedding |
| **cypher_generator** | Cypher 생성 | question, entities, schema | cypher_query | heavy |
| **graph_executor** | Neo4j 실행 | cypher_query | graph_results | DB |
| **response_generator** | 응답 생성 | question, results | response | heavy |
| **clarification_handler** | 동명이인 처리 | entities | response | light |

---

## 4.3 파이프라인 흐름도

```
                                      ┌─────────┐
                                      │  START  │
                                      └────┬────┘
                                           │
                                           ▼
                              ┌─────────────────────┐
                              │  intent_classifier  │
                              └──────────┬──────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │ (unknown)          │                    │ (valid)
                    ▼                    ▼                    ▼
              response_gen      ┌────────────────┐     cache_checker
                                │   (병렬 실행)   │           │
                                │ entity_extractor│     ┌─────┴─────┐
                                │ schema_fetcher  │     │cache hit  │cache miss
                                └───────┬────────┘     ▼           ▼
                                        │        graph_exec   (병렬 실행)
                                        ▼                          │
                              ┌─────────────────────┐              │
                              │   entity_resolver   │◄─────────────┘
                              └──────────┬──────────┘
                                         │
                         ┌───────────────┼───────────────┐
                         │ (미해결)      │               │ (해결됨)
                         ▼               │               ▼
                  clarification_handler  │      cypher_generator
                         │               │               │
                         │               │               ▼
                         │               │         graph_executor
                         │               │               │
                         ▼               ▼               ▼
                    ┌─────────────────────────────────────────┐
                    │           response_generator            │
                    └─────────────────────┬───────────────────┘
                                          │
                                          ▼
                                      ┌───────┐
                                      │  END  │
                                      └───────┘
```

---

## 4.4 조건부 라우팅

### A. Intent 분류 후
```python
def route_after_intent(state) -> list[Send] | str:
    if state.get("intent") == "unknown":
        return "response_generator"
    return "cache_checker"
```

### B. Cache 확인 후
```python
def route_after_cache(state) -> list[Send] | str:
    if state.get("skip_generation"):
        return "graph_executor"  # 캐시 히트
    return [
        Send("entity_extractor", state),
        Send("schema_fetcher", state),
    ]
```

### C. Entity Resolver 후
```python
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
```

---

## 4.5 Entity Resolver 상세

```python
SKILL_ALIASES = {
    "파이썬": "Python",
    "자바": "Java",
    "리액트": "React",
    "머신러닝": "ML",
}

async def resolve_skill(raw_skill: str) -> dict:
    search_name = SKILL_ALIASES.get(raw_skill, raw_skill)
    # 1. 정확 매칭
    # 2. 대소문자 무시
    # 3. 한글-영문 별칭
    # 4. 퍼지 매칭 (Levenshtein)
```
