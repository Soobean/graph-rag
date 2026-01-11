# Ontology Layer 설계 개선 계획

> **현재 설계 평가**: 41% (29/70)
> **목표 설계 평가**: 70%+ (49/70)
> **작성일**: 2024-01
> **상태**: Draft

---

## 1. 현재 설계의 핵심 문제점

### 1.1 이중 진실의 원천 (Two Sources of Truth)

**현재 상태:**
```
YAML 파일 (schema.yaml, synonyms.yaml)
    ↓
OntologyLoader (Python)
    ↓
ConceptExpanderNode
    ↓
EntityResolver → Neo4j (실제 데이터)
```

**문제:**
- 온톨로지 정의 (YAML)와 실제 데이터 (Neo4j)가 분리됨
- 동기화 보장 메커니즘 없음
- YAML에 "Spring Boot"가 있는데 Neo4j에는 "SpringBoot"로 저장된 경우 매칭 실패

**영향:**
- 데이터 불일치로 검색 실패
- 디버깅 어려움 (어디서 틀렸는지 추적 불가)

---

### 1.2 정적 온톨로지의 한계

**현재 상태:**
```yaml
# synonyms.yaml - 정적 정의
Python:
  canonical: "Python"
  aliases: ["파이썬", "Python3"]
```

**문제:**
- 트렌드 변화 반영 불가 (2020년 vs 2024년 기술 스택)
- 사용 빈도 기반 재정렬 불가
- 동적 학습 불가 (사용자 피드백 반영)

**영향:**
- 시간이 지날수록 온톨로지 품질 저하
- 수동 업데이트 필요 → 유지보수 비용 증가

---

### 1.3 컨텍스트 무시 확장

**현재 상태:**
```python
# 모든 검색에 동일한 확장 규칙 적용
expanded = loader.expand_concept("Python", "skills")
# → ["Python", "파이썬", "Python3", "Py"]
```

**문제:**
- "Python 시니어 찾아줘" → 정확한 매칭 필요
- "Python 관련 인력 찾아줘" → 넓은 확장 필요
- 현재는 구분 없이 동일하게 확장

**영향:**
- 시니어 검색 시 노이즈 증가 (정확도 하락)
- 넓은 검색 시 누락 발생 (재현율 하락)

---

### 1.4 오버 확장 문제

**현재 상태:**
```python
# "Backend" 검색 시
expanded = loader.expand_concept("Backend", "skills")
# → ["Backend", "Python", "Java", "Node.js", "Go", "Kotlin", "Spring"]
# 7개 스킬 모두 검색!
```

**문제:**
- 사용자가 "Backend 경험자"를 원했는데
- "Python만 아는 사람"도 결과에 포함
- 결과가 너무 넓어져서 의미 없음

**영향:**
- 정확도 급락
- 사용자 신뢰도 하락

---

### 1.5 관계의 단순화

**현재 상태:**
```yaml
# schema.yaml에 정의는 있지만 구현 안 됨
relations:
  IS_A:
    transitive: true  # 미구현
  REQUIRES:
    description: "직급이 요구하는 스킬"  # 미구현
```

**문제:**
- 관계 타입이 IS_A, SAME_AS 뿐
- 관계 강도/확률 없음 (Python과 Backend의 관련도는?)
- 전이적 관계 미구현

**영향:**
- 복잡한 질의 처리 불가 ("Python 잘하는 Backend 시니어")
- 관계 기반 추천 불가

---

## 2. 개선 방안

### 2.1 Neo4j 기반 온톨로지 마이그레이션

**목표:** 이중 진실의 원천 해소, 그래프 DB 강점 활용

#### 2.1.1 데이터 모델

```cypher
// 스킬 노드
CREATE (python:Skill {name: "Python", canonical: true})
CREATE (py:Alias {name: "파이썬"})
CREATE (py3:Alias {name: "Python3"})

// 동의어 관계
CREATE (py)-[:SAME_AS]->(python)
CREATE (py3)-[:SAME_AS]->(python)

// 계층 관계 (가중치 포함)
CREATE (backend:SkillCategory {name: "Backend"})
CREATE (python)-[:IS_A {weight: 0.9}]->(backend)
CREATE (java)-[:IS_A {weight: 0.8}]->(backend)

// 요구 관계
CREATE (senior_backend:Position {name: "Senior Backend Developer"})
CREATE (senior_backend)-[:REQUIRES {level: "expert"}]->(python)
```

#### 2.1.2 확장 쿼리

```cypher
// 동의어 + 계층 확장 (가중치 기반)
MATCH (s:Skill {name: $term})
OPTIONAL MATCH (s)-[:SAME_AS*0..1]-(syn)
OPTIONAL MATCH (s)-[:IS_A*0..2]->(parent)
WITH s, collect(DISTINCT syn.name) AS synonyms,
     collect(DISTINCT parent.name) AS parents
RETURN synonyms + parents AS expanded
```

#### 2.1.3 마이그레이션 전략

```
Phase 1: YAML → Neo4j 초기 로드
  - scripts/migrate_ontology.py 작성
  - YAML 파싱 → Cypher CREATE 문 생성
  - 일회성 마이그레이션 실행

Phase 2: OntologyLoader 수정
  - YAML 읽기 → Neo4j 쿼리로 변경
  - 기존 인터페이스 유지 (하위 호환성)

Phase 3: YAML 파일 제거
  - 초기 데이터용으로만 유지
  - 런타임 조회는 모두 Neo4j
```

---

### 2.2 컨텍스트 기반 확장

**목표:** 질문 의도에 따른 차별화된 확장

#### 2.2.1 확장 전략 정의

```python
class ExpansionStrategy(Enum):
    STRICT = "strict"      # 동의어만 (시니어 검색)
    NORMAL = "normal"      # 동의어 + 1단계 계층
    BROAD = "broad"        # 동의어 + 전체 계층

# Intent → Strategy 매핑
INTENT_STRATEGY_MAP = {
    "personnel_search": ExpansionStrategy.NORMAL,
    "project_matching": ExpansionStrategy.STRICT,
    "relationship_search": ExpansionStrategy.BROAD,
}
```

#### 2.2.2 ConceptExpander 수정

```python
class ConceptExpanderNode(BaseNode[ConceptExpanderUpdate]):
    def __init__(
        self,
        ontology_loader: OntologyLoader,
        default_strategy: ExpansionStrategy = ExpansionStrategy.NORMAL,
    ):
        self._default_strategy = default_strategy

    async def _process(self, state: GraphRAGState) -> ConceptExpanderUpdate:
        # Intent에서 전략 결정
        intent = state.get("intent", "unknown")
        strategy = self._get_strategy(intent, state)

        # 전략에 따른 확장
        if strategy == ExpansionStrategy.STRICT:
            include_children = False
        elif strategy == ExpansionStrategy.BROAD:
            include_children = True
            max_depth = 3
        else:
            include_children = True
            max_depth = 1
```

#### 2.2.3 신뢰도 기반 확장

```python
def _get_strategy(self, intent: str, state: GraphRAGState) -> ExpansionStrategy:
    confidence = state.get("intent_confidence", 0.0)

    # 신뢰도 높으면 좁은 확장 (정확한 의도 파악)
    if confidence > 0.9:
        return ExpansionStrategy.STRICT

    # 신뢰도 낮으면 넓은 확장 (불확실성 대응)
    if confidence < 0.5:
        return ExpansionStrategy.BROAD

    return INTENT_STRATEGY_MAP.get(intent, ExpansionStrategy.NORMAL)
```

---

### 2.3 확장 제한 메커니즘

**목표:** 오버 확장 방지

#### 2.3.1 최대 확장 수 제한

```python
class ExpansionConfig:
    max_synonyms: int = 5          # 동의어 최대 5개
    max_children: int = 10         # 하위 개념 최대 10개
    max_total: int = 15            # 전체 최대 15개

def expand_concept(
    self,
    term: str,
    category: str,
    config: ExpansionConfig = ExpansionConfig(),
) -> list[str]:
    result = {term}

    # 동의어 추가 (제한)
    synonyms = self.get_synonyms(term, category)[:config.max_synonyms]
    result.update(synonyms)

    # 하위 개념 추가 (제한)
    if len(result) < config.max_total:
        remaining = config.max_total - len(result)
        children = self.get_children(term, category)[:remaining]
        result.update(children)

    return list(result)[:config.max_total]
```

#### 2.3.2 가중치 기반 선택

```python
def expand_concept_weighted(
    self,
    term: str,
    category: str,
    min_weight: float = 0.5,
) -> list[str]:
    """가중치가 높은 관계만 확장"""

    query = """
    MATCH (s:Skill {name: $term})
    OPTIONAL MATCH (s)-[r:IS_A]->(parent)
    WHERE r.weight >= $min_weight
    RETURN parent.name AS expanded, r.weight AS weight
    ORDER BY r.weight DESC
    LIMIT 10
    """

    results = self._neo4j.execute(query, {"term": term, "min_weight": min_weight})
    return [r["expanded"] for r in results]
```

---

### 2.4 검증 및 모니터링

**목표:** 온톨로지 품질 보장, 지속적 개선

#### 2.4.1 온톨로지 검증 스크립트

```python
# scripts/validate_ontology.py

class OntologyValidator:
    def validate_all(self) -> ValidationReport:
        return ValidationReport(
            orphan_nodes=self._find_orphan_nodes(),
            circular_refs=self._find_circular_references(),
            broken_links=self._find_broken_links(),
            duplicate_canonicals=self._find_duplicate_canonicals(),
        )

    def _find_orphan_nodes(self) -> list[str]:
        """계층에 속하지 않은 고아 노드"""
        query = """
        MATCH (s:Skill)
        WHERE NOT (s)-[:IS_A]->()
        RETURN s.name
        """
        return self._neo4j.execute(query)

    def _find_circular_references(self) -> list[str]:
        """순환 참조 탐지"""
        query = """
        MATCH path = (s:Skill)-[:IS_A*]->(s)
        RETURN nodes(path) AS cycle
        """
        return self._neo4j.execute(query)
```

#### 2.4.2 확장 메트릭 수집

```python
# 확장 통계 수집
class ExpansionMetrics:
    def __init__(self):
        self.expansion_ratios: list[float] = []  # 확장 비율
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.unused_expansions: dict[str, int] = {}  # 사용되지 않은 확장

    def record_expansion(
        self,
        original_count: int,
        expanded_count: int,
        used_count: int,
    ):
        self.expansion_ratios.append(expanded_count / max(original_count, 1))

        # 사용되지 않은 확장 추적
        unused = expanded_count - used_count
        if unused > 0:
            # 오버 확장 감지
            logger.warning(f"Unused expansions: {unused}/{expanded_count}")

    def get_average_expansion_ratio(self) -> float:
        return sum(self.expansion_ratios) / len(self.expansion_ratios)
```

#### 2.4.3 A/B 테스트 프레임워크

```python
class OntologyExperiment:
    """확장 전략 A/B 테스트"""

    def __init__(self, variant: str):
        self.variant = variant  # "control" or "treatment"

    def get_expansion_strategy(self) -> ExpansionStrategy:
        if self.variant == "control":
            return ExpansionStrategy.NORMAL
        else:
            return ExpansionStrategy.STRICT

    def record_result(self, query: str, clicked_result: str | None):
        """사용자 클릭 기록 → 성공 여부 판단"""
        # 분석 시스템에 기록
        analytics.record(
            experiment="ontology_expansion",
            variant=self.variant,
            query=query,
            success=clicked_result is not None,
        )
```

---

### 2.5 동적 학습

**목표:** 사용 패턴 기반 자동 개선

#### 2.5.1 사용 빈도 기반 정렬

```python
class UsageBasedRanker:
    def rank_expansions(
        self,
        expansions: list[str],
        category: str,
    ) -> list[str]:
        """사용 빈도 기반 정렬"""

        # 최근 30일 검색 로그에서 빈도 집계
        query = """
        MATCH (q:Query)-[:RESULTED_IN]->(s:Skill)
        WHERE q.timestamp > datetime() - duration('P30D')
          AND s.name IN $expansions
        RETURN s.name AS skill, count(*) AS usage
        ORDER BY usage DESC
        """

        usage_map = {r["skill"]: r["usage"] for r in self._neo4j.execute(query, {"expansions": expansions})}

        return sorted(expansions, key=lambda x: usage_map.get(x, 0), reverse=True)
```

#### 2.5.2 클릭 피드백 학습

```python
class FeedbackLearner:
    def learn_from_click(
        self,
        query: str,
        expanded_terms: list[str],
        clicked_result: dict,
    ):
        """사용자 클릭에서 관계 강도 학습"""

        clicked_skills = clicked_result.get("skills", [])

        for term in expanded_terms:
            if term in clicked_skills:
                # 긍정적 피드백 → 가중치 증가
                self._increase_weight(query, term)
            else:
                # 부정적 피드백 → 가중치 감소
                self._decrease_weight(query, term)

    def _increase_weight(self, query_term: str, expanded_term: str):
        query = """
        MATCH (q:Skill {name: $query_term})-[r:IS_A|SAME_AS]->(e:Skill {name: $expanded_term})
        SET r.weight = COALESCE(r.weight, 0.5) + 0.01
        """
        self._neo4j.execute(query, {"query_term": query_term, "expanded_term": expanded_term})
```

---

## 3. 구현 로드맵

### Phase 1: 측정 및 기준선 (1주)

| 태스크 | 설명 | 우선순위 |
|--------|------|:--------:|
| 확장 메트릭 수집 | 현재 확장 비율, 사용률 측정 | P0 |
| 검색 정확도 측정 | 확장 전/후 비교 | P0 |
| 사용자 클릭 로그 | 결과 품질 평가 | P1 |

### Phase 2: Quick Wins (2주)

| 태스크 | 설명 | 우선순위 |
|--------|------|:--------:|
| 확장 제한 추가 | max_total=15 적용 | P0 |
| 검증 스크립트 | validate_ontology.py | P0 |
| 에러 처리 강화 | IOError, UnicodeDecodeError | P1 |

### Phase 3: 컨텍스트 기반 확장 (3주)

| 태스크 | 설명 | 우선순위 |
|--------|------|:--------:|
| ExpansionStrategy enum | STRICT/NORMAL/BROAD | P0 |
| Intent-Strategy 매핑 | 의도별 전략 | P0 |
| 신뢰도 기반 조정 | confidence 활용 | P1 |

### Phase 4: Neo4j 마이그레이션 (4주)

| 태스크 | 설명 | 우선순위 |
|--------|------|:--------:|
| 데이터 모델 설계 | Skill, Alias, IS_A 관계 | P0 |
| 마이그레이션 스크립트 | YAML → Neo4j | P0 |
| OntologyLoader 수정 | Neo4j 쿼리 사용 | P0 |
| 가중치 기반 확장 | weight 필드 활용 | P1 |

### Phase 5: 동적 학습 (장기)

| 태스크 | 설명 | 우선순위 |
|--------|------|:--------:|
| 사용 빈도 기반 정렬 | 검색 로그 분석 | P1 |
| 클릭 피드백 학습 | 가중치 자동 조정 | P2 |
| A/B 테스트 | 전략 비교 실험 | P2 |

---

## 4. 성공 지표

### 4.1 정량적 지표

| 지표 | 현재 (추정) | 목표 | 측정 방법 |
|------|:-----------:|:----:|-----------|
| 평균 확장 비율 | 5x | 2-3x | 로그 분석 |
| 확장 사용률 | 30% | 70%+ | 클릭 분석 |
| 검색 정확도 (P@5) | 60% | 80%+ | 사용자 평가 |
| 검색 재현율 | 80% | 85%+ | 테스트 셋 |

### 4.2 정성적 지표

- [ ] 온톨로지 업데이트가 Neo4j Admin으로 가능
- [ ] 새 스킬 추가 시 코드 변경 불필요
- [ ] A/B 테스트로 전략 효과 측정 가능
- [ ] 사용자 피드백이 자동으로 반영됨

---

## 5. 리스크 및 대응

### 5.1 Neo4j 마이그레이션 리스크

| 리스크 | 확률 | 영향 | 대응 |
|--------|:----:|:----:|------|
| 쿼리 성능 저하 | 중 | 높음 | 인덱스 최적화, 캐싱 |
| 데이터 불일치 | 낮 | 높음 | 검증 스크립트, 롤백 계획 |
| 하위 호환성 문제 | 중 | 중간 | 인터페이스 유지, 점진적 전환 |

### 5.2 롤백 계획

```
1. 마이그레이션 실패 시
   → YAML 기반 OntologyLoader로 즉시 복귀
   → feature flag로 Neo4j 온톨로지 비활성화

2. 성능 문제 발생 시
   → 캐싱 레이어 추가
   → 배치 쿼리로 전환

3. 정확도 하락 시
   → A/B 테스트로 원인 분석
   → 확장 전략 조정
```

---

## 6. 결론

현재 Ontology Layer는 **MVP로는 합격이지만 프로덕션으로는 개선 필요**합니다.

**핵심 개선 방향:**
1. **Neo4j 기반으로 전환** → 이중 진실의 원천 해소
2. **컨텍스트 기반 확장** → 의도에 맞는 정확한 확장
3. **확장 제한** → 오버 확장 방지
4. **동적 학습** → 지속적 품질 개선

**먼저 측정하고, 그 다음 개선하세요.**
- 현재 확장이 실제로 얼마나 사용되는가?
- 오버 확장으로 인한 노이즈가 얼마나 되는가?
- 사용자가 정말 "파이썬"을 검색하는가, "Python"을 검색하는가?

측정 결과에 따라 투자 우선순위를 결정해야 합니다.
