# 온톨로지 시스템 (Ontology System)

> **작성일**: 2026-01-14
> **상태**: Active
> **관련 Phase**: Phase 3~6

---

## 1. 개요

온톨로지 시스템은 Graph RAG 파이프라인에서 **개념 확장(Concept Expansion)**을 담당합니다.
사용자 질문에서 추출된 엔티티를 동의어 및 계층 관계를 통해 확장하여 검색 범위를 넓힙니다.

### 핵심 기능

| 기능 | 설명 | 예시 |
|------|------|------|
| **동의어 확장** | 한글↔영문, 축약어 매핑 | "파이썬" → ["Python", "Python3", "Py"] |
| **계층 확장** | 상위/하위 개념 탐색 | "Backend" → ["Java", "Python", "Go", ...] |
| **가중치 정렬** | 사용 빈도 기반 우선순위 | weight 1.0 > 0.6 |
| **전략 기반 확장** | Intent에 따른 확장 범위 조절 | STRICT / NORMAL / BROAD |

### 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    ConceptExpanderNode                       │
├─────────────────────────────────────────────────────────────┤
│                            │                                 │
│                   ┌────────┴────────┐                       │
│                   │                 │                        │
│          ┌────────▼────────┐ ┌──────▼──────┐               │
│          │ OntologyLoader  │ │HybridLoader │               │
│          │   (YAML 동기)   │ │ (Neo4j 비동기)│              │
│          └────────┬────────┘ └──────┬──────┘               │
│                   │                 │                        │
│          ┌────────▼────────┐ ┌──────▼──────┐               │
│          │  synonyms.yaml  │ │  Neo4j DB   │               │
│          │  schema.yaml    │ │  (:Concept) │               │
│          └─────────────────┘ └─────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 로더 종류

### 2.1 OntologyLoader (YAML 기반)

YAML 파일에서 온톨로지를 로드하는 **동기** 로더입니다.

```python
from src.domain.ontology import OntologyLoader

loader = OntologyLoader()

# 동의어 조회
synonyms = loader.get_synonyms("Python", "skills")
# → ["Python", "파이썬", "Python3", "Py"]

# 개념 확장 (동의어 + 계층)
expanded = loader.expand_concept("파이썬", "skills")
# → ["Python", "파이썬", "Python3", "Py", ...]
```

**데이터 파일 위치:**
```
src/domain/ontology/data/
├── schema.yaml      # 카테고리 계층 정의
└── synonyms.yaml    # 동의어 사전 (가중치 포함)
```

### 2.2 HybridOntologyLoader (Neo4j + YAML)

Neo4j와 YAML을 조합하는 **비동기** 로더입니다.

```python
from src.domain.ontology.hybrid_loader import HybridOntologyLoader

# 하이브리드 모드 (권장)
loader = HybridOntologyLoader(
    neo4j_client=client,
    mode="hybrid"  # Neo4j 우선, 실패 시 YAML 폴백
)

# 비동기 호출
expanded = await loader.expand_concept("파이썬", "skills")
```

**모드 설명:**

| 모드 | 동작 | 사용 시나리오 |
|------|------|--------------|
| `yaml` | YAML만 사용 | 기본값, 하위호환 |
| `neo4j` | Neo4j만 사용 | 마이그레이션 완료 후 |
| `hybrid` | Neo4j 우선 + YAML 폴백 | **프로덕션 권장** |

---

## 3. 데이터 모델

### 3.1 YAML 구조

**synonyms.yaml:**
```yaml
Python:
  canonical: "Python"
  aliases:
    - name: "파이썬"
      weight: 1.0       # 한글 정규 표현
    - name: "Python3"
      weight: 0.9       # 버전 표현
    - name: "Py"
      weight: 0.6       # 축약형
```

**schema.yaml:**
```yaml
skills:
  Programming:
    subcategories:
      Backend:
        skills: [Java, Python, Go, Node.js]
      Frontend:
        skills: [React, Vue, Angular]
```

### 3.2 Neo4j 구조

**노드:**
```cypher
(:Concept {
  name: "Python",
  type: "skill",        // skill, category, subcategory
  description: "...",
  created_at: datetime()
})
```

**관계:**
```cypher
// 동의어 관계
(:Concept {name: "Python"})-[:SAME_AS {weight: 1.0}]->(:Concept {name: "파이썬"})

// 계층 관계 (child → parent)
(:Concept {name: "Python"})-[:IS_A {depth: 1}]->(:Concept {name: "Backend"})
(:Concept {name: "Backend"})-[:IS_A {depth: 1}]->(:Concept {name: "Programming"})
```

---

## 4. 확장 전략 (ExpansionStrategy)

Intent와 신뢰도에 따라 확장 범위를 자동 조절합니다.

### 4.1 전략 종류

| 전략 | max_synonyms | max_children | max_total | 사용 시나리오 |
|------|:-----------:|:------------:|:---------:|--------------|
| **STRICT** | 3 | 0 | 5 | 정확한 검색 (project_matching) |
| **NORMAL** | 5 | 10 | 15 | 일반 검색 (personnel_search) |
| **BROAD** | 10 | 20 | 30 | 넓은 검색 (skill_search) |

### 4.2 Intent → Strategy 매핑

```python
from src.domain.ontology import get_strategy_for_intent

strategy = get_strategy_for_intent("skill_search", confidence=0.85)
# → ExpansionStrategy.BROAD
```

| Intent | 기본 전략 |
|--------|----------|
| `personnel_search` | NORMAL |
| `project_matching` | STRICT |
| `skill_search` | BROAD |
| `relationship_search` | BROAD |
| `org_info` | STRICT |
| `count_query` | NORMAL |

### 4.3 가중치 기반 필터링

```python
from src.domain.ontology import ExpansionConfig

config = ExpansionConfig(
    min_weight=0.5,        # weight < 0.5 제외
    sort_by_weight=True,   # 가중치 내림차순 정렬
)

expanded = loader.expand_concept("Python", "skills", config)
# weight 0.6 이상만 포함, 높은 weight 순서
```

---

## 5. 파이프라인 통합

### 5.1 환경변수 설정

```bash
# .env
ONTOLOGY_MODE=hybrid   # yaml | neo4j | hybrid
```

### 5.2 GraphRAGPipeline 초기화

`ontology_mode`에 따라 적절한 로더가 자동 선택됩니다.

```python
# src/graph/pipeline.py (자동 처리)
if settings.ontology_mode in ("neo4j", "hybrid"):
    if neo4j_client is None:
        logger.warning("Falling back to YAML mode")
        self._ontology_loader = OntologyLoader()
    else:
        self._ontology_loader = HybridOntologyLoader(
            neo4j_client=neo4j_client,
            mode=settings.ontology_mode
        )
else:
    self._ontology_loader = OntologyLoader()
```

### 5.3 ConceptExpanderNode

Duck Typing으로 동기/비동기 로더 모두 지원합니다.

```python
# src/graph/nodes/concept_expander.py
class ConceptExpanderNode(BaseNode):
    def __init__(self, ontology_loader: OntologyLoader | HybridOntologyLoader):
        # inspect.iscoroutinefunction()으로 비동기 여부 판단
        self._is_async_loader = inspect.iscoroutinefunction(
            getattr(ontology_loader, "expand_concept", None)
        )
```

---

## 6. 마이그레이션

### 6.1 YAML → Neo4j 마이그레이션

```bash
# 미리보기
python scripts/migrate_ontology.py --dry-run

# 실행
python scripts/migrate_ontology.py

# 검증
python scripts/migrate_ontology.py --verify
```

**마이그레이션 결과 (2026-01-13):**
- Concept 노드: 138개 (skills 131, categories 3, subcategories 4)
- SAME_AS 관계: 100개
- IS_A 관계: 36개

### 6.2 온톨로지 검증

```bash
python scripts/validate_ontology.py
```

**검사 항목:**
- 고아 스킬 (schema에만 있고 synonyms에 없는)
- 중복 canonical
- 깨진 참조

---

## 7. 테스트

```bash
# 단위 테스트
pytest tests/test_ontology_loader.py -v

# Neo4j 통합 테스트
pytest tests/test_neo4j_ontology_loader.py -m integration -v

# ConceptExpander 테스트
pytest tests/test_concept_expander.py -v
```

**테스트 현황:**
- `test_ontology_loader.py`: 59 passed
- `test_neo4j_ontology_loader.py`: 30 passed
- `test_concept_expander.py`: 13 passed

---

## 8. 성능 최적화

### 온톨로지 확장 효과 (10,000명 데이터 기준)

| 검색어 | 미적용 | 적용 후 | 개선율 |
|--------|:------:|:------:|:------:|
| "파이썬" | 361명 | 1,783명 | **+394%** |
| "Backend" | 0명 | 3,774명 | **∞** |

### 캐싱 전략

- `@lru_cache`: OntologyLoader 싱글톤
- 역인덱스: `_reverse_index`로 O(1) 조회
- Neo4j 인덱스: `:Concept(name)`, `:Concept(type)`

---

## 9. 관련 파일

| 파일 | 설명 |
|------|------|
| `src/domain/ontology/loader.py` | YAML 로더, ExpansionConfig, ExpansionStrategy |
| `src/domain/ontology/neo4j_loader.py` | Neo4j 로더 |
| `src/domain/ontology/hybrid_loader.py` | 하이브리드 로더 |
| `src/domain/ontology/data/` | YAML 데이터 파일 |
| `src/graph/nodes/concept_expander.py` | 파이프라인 노드 |
| `scripts/migrate_ontology.py` | 마이그레이션 스크립트 |
| `scripts/validate_ontology.py` | 검증 스크립트 |

---

## 10. 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-01-14 | Phase 6: ConceptExpanderNode + HybridOntologyLoader 연동 |
| 2026-01-13 | Phase 5: 가중치 기반 확장, OntologyCategory enum |
| 2026-01-13 | Phase 4: Neo4j 마이그레이션, HybridOntologyLoader |
| 2026-01-11 | Phase 3: ExpansionStrategy, Intent 기반 전략 |
| 2026-01-11 | Phase 2: ExpansionConfig, 검증 스크립트 |
| 2026-01-08 | Phase 1: 기초 구축 (YAML 로더) |
