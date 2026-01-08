# 부록

## A. UI 옵션

### A.1 Chainlit UI (권장)

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

### A.2 Streamlit UI (간단한 버전)

```bash
# 실행
streamlit run app_ui.py --server.port 8501
```

### A.3 FastAPI REST API

```bash
# 실행
uvicorn src.main:app --reload --port 8000

# 엔드포인트
POST /api/v1/query    # 질문 처리
GET  /api/v1/health   # 헬스 체크
GET  /api/v1/schema   # 스키마 조회
```

---

## B. 호환성 노트

### B.1 Neo4j 5.x+ 호환성

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

### B.2 GPT-5 모델 호환성

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

### B.3 인증 방식 (Neo4j 2025.x)

Neo4j 2025.x 서버는 명시적 `basic_auth()` 사용 필요:

```python
from neo4j import basic_auth

# Before
driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

# After (Neo4j 2025.x)
driver = AsyncGraphDatabase.driver(uri, auth=basic_auth(user, password))
```

---

## C. 설정 파일 예시

### C.1 환경변수 템플릿

```bash
# .env.example

# Neo4j 설정
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Azure OpenAI 설정
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2025-04-01-preview

# 모델 배포 이름
AZURE_OPENAI_LIGHT_MODEL_DEPLOYMENT=gpt-4o-mini-deploy
AZURE_OPENAI_HEAVY_MODEL_DEPLOYMENT=gpt-4o-deploy

# 앱 설정
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### C.2 그래프 스키마 설정

```yaml
# config/graph_schema.yaml
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
```

---

## D. 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2024-01 | 1.0 | 초기 설계 |
| 2024-12 | 2.0 | Chat History (MemorySaver) 추가 |
| 2025-01 | 2.1 | 문서 구조 분리 |
| 2025-01 | 2.2 | UI 옵션, Neo4j 5.x/GPT-5 호환성 추가 |
