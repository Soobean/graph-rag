# Graph RAG

Neo4j 그래프 데이터베이스와 Azure OpenAI를 활용한 RAG(Retrieval-Augmented Generation) 시스템

## 설치

```bash
# 가상환경 생성 (Python 3.12 권장)
conda create -n graph python=3.12 -y
conda activate graph

# 의존성 설치
pip install -e ".[dev]"
```

## 환경 설정

`.env.example`을 `.env`로 복사하고 필요한 값을 설정합니다:

```bash
cp .env.example .env
```

## 테스트

```bash
# 단위 테스트
pytest tests/ -v

# 커버리지 포함
pytest tests/ --cov=src --cov-report=term-missing
```

## 실행

```bash
uvicorn main:app --reload
```
