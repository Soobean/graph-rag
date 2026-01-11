# 5. 핵심 설계 결정사항

## 5.1 자연어 → Cypher 변환 전략

### 전략 비교

| 전략 | 장점 | 단점 | 적합한 경우 |
|------|------|------|------------|
| **LangChain GraphCypherQAChain** | 빠른 구현, 검증된 패턴 | 커스터마이징 제한, 에러 핸들링 어려움 | 빠른 PoC |
| **하이브리드 (템플릿 + LLM)** | 안정성 + 유연성 균형 | 템플릿 관리 필요 | **권장 (MVP)** |
| **순수 LLM 생성** | 최대 유연성 | 불안정, 잘못된 쿼리 위험 | 고급 사용자 |

### 권장 전략: 하이브리드 접근 (LangGraph 노드에서 구현)

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

---

## 5.2 그래프 탐색 깊이 제한

| 질문 유형 | 최대 홉 수 | 이유 |
|-----------|-----------|------|
| 직접 관계 (스킬, 부서) | 1-2 홉 | 직접 연결된 정보만 필요 |
| 프로젝트 매칭 | 2-3 홉 | 프로젝트→스킬→직원 |
| 경로 탐색 | 5 홉 | 조직 내 합리적 연결 거리 |
| 멘토링 체인 | 4 홉 | 멘토→멘티→멘티 계층 |

---

## 5.3 벡터 검색 필요 여부

**MVP에서는 벡터 검색 불필요**

이유:
1. 규모가 작아 전체 탐색도 빠름 (ms 단위)
2. 구조화된 데이터 → 키워드/속성 매칭으로 충분
3. 추가 인프라 복잡도 증가

**향후 필요한 경우:**
- 노드 10,000개 이상으로 확장
- 프로젝트 설명, 스킬 상세 등 긴 텍스트 추가
- 유사도 기반 검색 필요 ("ML과 비슷한 스킬은?")

---

## 5.4 데이터 모델 선택: TypedDict vs Pydantic

**결정: 레이어별 적합한 도구 사용 (혼용)**

### 용도별 구분

| 용도 | 선택 | 이유 |
|------|------|------|
| **LangGraph State** | TypedDict | LangGraph 네이티브, Annotated reducer 지원, 성능 최적화 |
| **API Request/Response** | Pydantic BaseModel | FastAPI 자동 검증, OpenAPI 문서 생성 |
| **설정 (Config)** | Pydantic Settings | 환경변수 자동 로딩, 타입 변환 |

### 통일화하지 않는 이유

| 통일 방향 | 문제점 |
|----------|--------|
| 전부 TypedDict | FastAPI 자동 검증/문서화 기능 상실, 수동 검증 코드 필요 |
| 전부 Pydantic | LangGraph에서 `.model_dump()` 변환 필요, Annotated reducer 미지원 |

### 레이어 경계에서의 변환

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

### 구현 예시

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

### 설계 원칙

1. **경계 명확화**: API 레이어와 Graph 레이어의 경계에서만 변환
2. **각 도구의 강점 활용**: 통일화보다 적재적소 활용
3. **변환 비용 최소화**: 변환은 API 진입/퇴출 지점에서 한 번씩만

---

# 5.5 노드 재사용성 설계

### 설계 철학

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

---

### 노드 인터페이스 표준

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
        """필요한 State 필드 목록 (입력 검증용)"""
        ...

    def __call__(self, state: StateT) -> dict[str, Any]:
        """
        노드 실행
        Args:
            state: 현재 그래프 상태
        Returns:
            업데이트할 State 필드들 (TypedDict로 타입 정의)
        """
        ...

    def validate_input(self, state: StateT) -> bool:
        """입력 State 검증"""
        ...
```

---

### 의존성 주입 패턴

각 노드는 외부 의존성을 생성자에서 주입받습니다:

```python
class IntentClassifier(ConfigurableNode):
    """재사용 가능한 의도 분류 노드"""

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
```

---

### 노드 독립 테스트

각 노드는 독립적으로 테스트 가능:

```python
# tests/test_nodes/test_intent_classifier.py

class TestIntentClassifier:
    @pytest.fixture
    def mock_llm(self):
        llm = Mock()
        llm.invoke.return_value = {
            "intent": "personnel_search",
            "confidence": 0.95
        }
        return llm

    def test_classify_personnel_search(self, classifier):
        state = {"question": "Python 개발자 찾아줘"}
        result = classifier(state)
        assert result["intent"] == "personnel_search"
        assert result["intent_confidence"] >= 0.7
```

---

# 5.6 구현 우선순위

### MVP 단계 (Phase 1) - 4주

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

### Phase 2 - 확장 기능 (4-6주)

- 관계 탐색 (shortestPath, allPaths) - C, G 유형
- 멘토링 네트워크 탐색 - E 유형
- 복합 질문 분해 노드 추가
- 대화 히스토리 (State 확장) ✅ 구현 완료
- 결과 시각화

### Phase 3 - 고급 기능

- 벡터 검색 통합 노드
- Human-in-the-loop (LangGraph interrupt)
- 권한 기반 데이터 필터링

---

## 5.7 아키텍처 진화 전략 (Architecture Evolution)

### 결정: 기존 아키텍처 진화 (Evolution) vs 재작성 (Rewrite)

**결정: Path A - 기존 아키텍처 진화 (Ontology-Enhanced Graph RAG)**

| 항목 | Path A (진화) | Path B (RDF/SPARQL 재작성) |
|---|---|---|
| **핵심 철학** | **Pragmatism**: Graph RAG의 유연성에 온톨로지 추론(Reasoning)을 Layer로 추가 | **Purity**: RDF/OWL 표준 준수, 엄격한 논리적 무결성 |
| **데이터 모델** | **LPG (Labeled Property Graph)** + `IS_A`, `SAME_AS` 엣지 직접 구현 | RDF Triple Store (`Subject-Predicate-Object`) |
| **추론 방식** | Python 코드 레벨 (`ConceptExpanderNode`) + Neo4j Cypher | SPARQL Reasoner / Inference Engine |
| **장점** | 학습 곡선 낮음, 기존 코드 100% 재활용, 유연한 확장 | 표준 준수, 복잡한 논리 추론 강력 |
| **단점** | 표준 온톨로지(OWL) 호환성 낮음 | 개발 난이도 높음, LLM의 SPARQL 생성 능력 저조 |

### 구현 방안

1.  **YAML 기반 온톨로지 관리**:
    *   `src/domain/ontology/schema.yaml`: 개념 계층 (`IS_A`) 정의
    *   `src/domain/ontology/synonyms.yaml`: 동의어 (`SAME_AS`) 정의

2.  **Pipeline 변경**:
    *   **[AS-IS]** `EntityExtractor` → `EntityResolver` → `CypherGenerator`
    *   **[TO-BE]** `EntityExtractor` → **`ConceptExpander`** → `EntityResolver` → `CypherGenerator`

3.  **ConceptExpander 역할**:
    *   "백엔드 개발자" 입력 시 → 온톨로지 로더를 통해 "Python", "Java", "Node.js" 등 하위 개념 및 동의어 확장
    *   확장된 키워드들을 `CypherGenerator`에 전달하여 `WHERE n.skill IN ['Backend', 'Python', ...]` 형태로 쿼리 생성 지원

