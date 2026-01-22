# Graph RAG

Neo4j 그래프 데이터베이스와 Azure OpenAI를 활용한 RAG(Retrieval-Augmented Generation) 시스템

## 주요 기능

- **자연어 질의**: 한국어/영어로 질문하면 그래프 기반 답변 생성
- **온톨로지 시스템**: 동의어/계층 확장으로 검색 정확도 향상
- **Explainable AI**: 추론 과정 시각화
- **GDS 분석**: 커뮤니티 탐지, 유사도 분석, 팀 추천

## 빠른 시작 (Docker)

### 1. 환경 설정

```bash
cp .env.example .env
# .env 파일에서 Azure OpenAI 설정 수정
```

### 2. 실행

```bash
# 전체 스택 실행 (API + Neo4j)
docker compose up -d

# 로그 확인
docker compose logs -f api

# 중지
docker compose down
```

### 3. 접속

- **API**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474

---

## 개발 환경

### Docker 개발 모드 (Hot Reload)

```bash
# 개발 모드 실행
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 소스 코드 변경 시 자동 반영됨
```

### 로컬 개발 (Docker 없이)

```bash
# 가상환경 생성 (Python 3.12 권장)
conda create -n graph python=3.12 -y
conda activate graph

# 의존성 설치
pip install -e ".[dev]"

# 또는 uv 사용 (더 빠름)
uv pip install -e ".[dev]"

# 환경 설정
cp .env.example .env

# Neo4j 로컬 실행 필요
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password123 \
  neo4j:5.15-community

# API 실행
uvicorn src.main:app --reload
```

---

## 테스트

```bash
# 단위 테스트
pytest tests/ -v

# 커버리지 포함
pytest tests/ --cov=src --cov-report=term-missing

# 통합 테스트 (Neo4j 필요)
pytest tests/ -m integration -v
```

---

## 프로젝트 구조

```
graph-search/
├── src/
│   ├── api/           # FastAPI 라우터, 스키마
│   ├── graph/         # LangGraph 파이프라인
│   ├── domain/        # 도메인 모델, 온톨로지
│   ├── repositories/  # 데이터 접근 (Neo4j, LLM)
│   └── prompts/       # LLM 프롬프트 템플릿
├── tests/             # 테스트
├── docs/              # 문서
│   ├── design/        # 설계 문서
│   └── presentation/  # 발표 자료
└── scripts/           # 유틸리티 스크립트
```

---

## API 예시

```bash
# 질의 API
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Python 개발자 찾아줘",
    "include_explanation": true,
    "include_graph": true
  }'

# 헬스체크
curl http://localhost:8000/api/v1/health
```

---

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `NEO4J_URI` | Neo4j 연결 URI | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j 사용자 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 비밀번호 | - |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI 엔드포인트 | - |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API 키 | - |
| `LIGHT_MODEL_DEPLOYMENT` | 경량 모델 배포명 | `gpt-4o-mini` |
| `HEAVY_MODEL_DEPLOYMENT` | 중량 모델 배포명 | `gpt-4o` |

전체 설정은 `.env.example` 참조

---

## 문서

- [API 문서](API_DOCUMENTATION.md)
- [아키텍처 설계](docs/ARCHITECTURE.md)
- [Adaptive Ontology 설계](docs/design/ADAPTIVE_ONTOLOGY.md)

---

## 라이선스

MIT License
