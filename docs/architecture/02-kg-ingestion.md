# 2. 견고한 KG 추출 파이프라인 (Robust KG Ingestion)

> ✅ **구현 상태**: 구현 완료

## 2.1 설계 철학: Human-in-the-loop 하이브리드 아키텍처

LLM의 창의성을 제한하고 신뢰성을 확보하기 위해 **"사람의 통제(Control)"**와 **"AI의 효율성(Efficiency)"**을 결합합니다.

```
[Raw Data] → (1. Extraction) → (2. Validation) → (3. Fusion) → [Neo4j]
```

| 역할 | 담당 | 설명 |
|------|------|------|
| **Human (Bone Logic)** | `schema.py` | 허용된 노드/관계의 "뼈대" 정의 (LLM 임의 확장 차단) |
| **LLM (Extraction)** | `extractor.py` | 정의된 뼈대 안에서 비정형 텍스트 분석 |
| **Human (Review)** | 로깅 + 검토 | 스키마 벗어나는 정보는 별도 로깅, 추후 스키마 확장 여부 결정 |

## 2.2 핵심 방어 계층 (Layers of Defense)

| 계층 | 역할 | 구현 방식 |
|------|------|----------|
| **1. Static Schema** | 구조적 제한 | `schema.py` 내 Enum 및 Pydantic 정의로 허용된 타입만 생성 |
| **2. Confidence Check** | 품질 보장 | LLM의 확신도(Confidence) 점수 0.8 미만 데이터 자동 폐기 |
| **3. Validation Logic** | 논리적 정합성 | 관계의 방향성 및 타입 일치 여부 검증 (예: Project가 Person을 고용 불가) |

## 2.3 상세 구현 명세

### A. Schema & Models (Human Control)

사람이 통제하는 "법전(Rule Book)" 역할을 합니다. 속성(Property)까지 명시하여 LLM의 환각을 방지합니다.

```python
# src/ingestion/schema.py
from enum import Enum

class NodeType(str, Enum):
    EMPLOYEE = "Employee"
    PROJECT = "Project"
    SKILL = "Skill"

class RelationType(str, Enum):
    WORKS_ON = "WORKS_ON"     # Employee -> Project
    HAS_SKILL = "HAS_SKILL"   # Employee -> Skill

# LLM 가이드라인: 각 노드별 허용 속성 정의
NODE_PROPERTIES = {
    NodeType.EMPLOYEE: ["name", "job_type", "years_experience"],
    NodeType.PROJECT: ["name", "status", "start_date"],
    NodeType.SKILL: ["name", "category"],
}

# 관계 유효성 규칙 (Source Type -> Target Type)
VALID_RELATIONS = {
    RelationType.WORKS_ON: (NodeType.EMPLOYEE, NodeType.PROJECT),
    RelationType.HAS_SKILL: (NodeType.EMPLOYEE, NodeType.SKILL),
}
```

### B. Data Models with Lineage & UUID5 Entity ID

데이터의 출처(Lineage)와 신뢰도(Confidence)를 관리하며, **UUID5 기반 결정적 Entity ID**를 생성합니다.

```python
# src/ingestion/models.py
import uuid
from pydantic import BaseModel, Field
from .schema import NodeType, RelationType

# UUID5 네임스페이스 (프로젝트 고유)
ENTITY_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

def generate_entity_id(label: str, properties: dict) -> str:
    """
    UUID5 기반 결정적 Entity ID 생성

    - 강한 식별자 (id, email, code): 단독 사용 → Entity Resolution에 유리
    - 약한 식별자 (name): 모든 속성과 조합 → 동명이인 충돌 방지
    - 대소문자 정규화: iPhone == iphone == IPHONE
    """
    # ... 구현 생략
```

### C. Extractor with Validation Logic

Azure OpenAI SDK를 직접 사용하여 LLM 추출 후 Confidence Cutoff와 Schema Validation을 수행합니다.

```python
# src/ingestion/extractor.py
EDGE_CONFIDENCE_THRESHOLD = 0.8

class GraphExtractor:
    async def extract(self, document: Document) -> ExtractedGraph:
        # 1. LLM 추출 (Structured Output)
        raw_graph = await self._run_llm(document.page_content)

        # 2. UUID5 ID 생성 + Validation
        # 3. Edge Validation (Confidence + Schema)
        return ExtractedGraph(nodes=valid_nodes, edges=valid_edges)
```

### D. Loaders (CSV, Excel)

다양한 데이터 소스를 `Document` 객체로 변환하는 어댑터 패턴 구현.

### E. Pipeline & Batch Processing

배치 처리 + 동시성 제어 + UNWIND를 활용한 Neo4j 저장.

### F. Idempotent Storage (MERGE)

**멱등성**: 파이프라인을 여러 번 실행해도 데이터가 중복되지 않습니다.

```cypher
UNWIND $nodes AS node
MERGE (n:Employee {id: node.id})
ON CREATE SET n += node.props, n.created_at = datetime()
ON MATCH SET n += node.props, n.updated_at = datetime()
```

## 2.4 업데이트 및 동기화 전략

| 데이터 유형 | 업데이트 방식 | 주기 | 예시 |
|------------|--------------|------|------|
| **Hot Data** | Event-Driven | 실시간 | 신규 입사자, 프로젝트 상태 변경 |
| **Cold Data** | Batch Processing | 일간/주간 | 자격증 데이터베이스, 과거 이력 정리 |

## 2.5 Query Pipeline과의 연결점

| Ingestion 컴포넌트 | Query 컴포넌트 | 공유 자원 |
|-------------------|---------------|----------|
| `ingestion/schema.py` | `graph/nodes/entity_resolver.py` | 동의어 사전 (Alias Table) |
| `ingestion/models.py` | `domain/types.py` | 노드/관계 타입 정의 |

## 2.6 검증 계획 (Testing)

| 구분 | 테스트 항목 | 설명 |
|------|------------|------|
| **Unit Test** | `test_schema_validation.py` | 허용되지 않은 관계 필터링 검증 |
| **Unit Test** | `test_idempotency.py` | 멱등성 확인 |
| **E2E Test** | 파이프라인 통합 테스트 | 데이터 무결성 확인 |
