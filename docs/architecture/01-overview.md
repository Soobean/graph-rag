# 1. 개요 및 프로젝트 구조

## 1.1 시스템 목적

Neo4j에 적재된 기업/조직 도메인 그래프 데이터(850개 노드, 5000개 엣지)를 활용하여 자연어 질문에 대해 **온톨로지 기반 지식 확장(Reasoning)**과 그래프 탐색을 결합한 Graph RAG 시스템 구축

## 1.2 설계 원칙

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
│   ├── ingestion/                       # [Ingestion Layer - KG 구축]
│   │   ├── __init__.py
│   │   ├── schema.py                    # 노드/관계 타입 정의 (Human Control)
│   │   ├── models.py                    # Pydantic 모델 (Lineage, Confidence)
│   │   ├── extractor.py                 # LLM 기반 Triple 추출 + 검증
│   │   ├── pipeline.py                  # Extract → Validate → Save 오케스트레이션
│   │   └── loaders/                     # 데이터 소스 어댑터
│   │       ├── base.py
│   │       ├── csv_loader.py
│   │       └── excel_loader.py
│   │
│   ├── api/                             # [Presentation Layer]
│   │   ├── routes/
│   │   │   └── query.py                 # POST /query, GET /health, GET /schema
│   │   └── schemas/
│   │       └── query.py                 # QueryRequest, QueryResponse (Pydantic)
│   │
│   ├── graph/                           # [Graph Layer - LangGraph Query]
│   │   ├── state.py                     # GraphRAGState (TypedDict)
│   │   ├── pipeline.py                  # StateGraph 구성 + 라우팅 통합
│   │   └── nodes/                       # 노드 구현체
│   │       ├── intent_classifier.py     # 의도 분류
│   │       ├── entity_extractor.py      # 엔티티 추출
│   │       ├── concept_expander.py      # [New] 온톨로지 기반 개념 확장
│   │       ├── schema_fetcher.py        # 스키마 조회 (병렬 실행)
│   │       ├── entity_resolver.py       # DB 엔티티 매칭
│   │       ├── clarification_handler.py # 명확화 요청 (동명이인 등)
│   │       ├── cache_checker.py         # 캐시 조회 (Vector Similarity)
│   │       ├── cypher_generator.py      # Cypher 생성 + 캐시 저장
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
│   │   ├── llm_repository.py            # Azure OpenAI (openai SDK 직접 사용)
│   │   └── query_cache_repository.py    # 질문-Cypher 캐싱 (Vector Index)
│   │
│   ├── infrastructure/                  # [Infrastructure Layer]
│   │   └── neo4j_client.py              # Neo4j 드라이버 + Vector Index (Neo4j 5.11+)
│   │
│   ├── utils/                           # [Utilities]
│   │   └── prompt_manager.py            # YAML 프롬프트 로더 + 캐싱
│   │
│   └── domain/                          # [Domain Models & Ontology]
│       ├── types.py                     # TypedDict 정의 (노드 입출력)
│       ├── exceptions.py                # 도메인 예외
│       └── ontology/                    # [New] 온톨로지 정의
│           ├── __init__.py
│           ├── loader.py                # YAML 로더
│           ├── schema.yaml              # 개념 계층 정의 (Concept Hierarchy)
│           └── synonyms.yaml            # 동의어 사전 (Synonyms)
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
