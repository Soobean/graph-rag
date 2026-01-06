import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from src.config import Settings
from src.graph.pipeline import GraphRAGPipeline
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_verification():
    """파이프라인 라우팅 로직 검증 스크립트"""

    # 1. Mock 의존성 설정
    settings = Settings()

    # Mock LLM
    mock_llm = MagicMock(spec=LLMRepository)
    mock_llm.classify_intent = AsyncMock()
    mock_llm.extract_entities = AsyncMock()
    mock_llm.generate_cypher = AsyncMock()
    mock_llm.generate_response = AsyncMock()

    # Mock Neo4j
    mock_neo4j = MagicMock(spec=Neo4jRepository)
    mock_neo4j.find_entities_by_name = AsyncMock(return_value=[])
    mock_neo4j.get_schema = AsyncMock(return_value={"node_labels": ["Person"]})
    mock_neo4j.execute_cypher = AsyncMock(return_value=[])

    pipeline = GraphRAGPipeline(settings, mock_neo4j, mock_llm)

    print("\n=== Test 1: Unknown Intent (Skip to End) ===")
    mock_llm.classify_intent.return_value = {"intent": "unknown", "confidence": 0.0}

    result = await pipeline.run("알 수 없는 질문")
    print(f"Path: {result['metadata']['execution_path']}")
    assert "entity_extractor" not in result["metadata"]["execution_path"]
    # ResponseGenerator adds "response_generator_empty" when result is empty
    assert "response_generator_empty" in result["metadata"]["execution_path"]
    print("✅ Passed: Unknown intent skipped directly to response_generator")

    print("\n=== Test 2: Cypher Generation Error (Skip Execution) ===")
    mock_llm.classify_intent.return_value = {
        "intent": "personnel_search",
        "confidence": 0.9,
    }
    mock_llm.extract_entities.return_value = {"entities": []}
    mock_llm.generate_cypher.side_effect = Exception("Cypher Error")  # 에러 발생
    mock_llm.generate_response.return_value = "오류가 발생했습니다."

    result = await pipeline.run("에러 유발 질문")
    print(f"Path: {result['metadata']['execution_path']}")
    assert "cypher_generator_error" in result["metadata"]["execution_path"]
    assert "graph_executor" not in result["metadata"]["execution_path"]
    assert "response_generator_error_handler" in result["metadata"]["execution_path"]
    print("✅ Passed: Cypher error skipped graph_executor")

    print("\n=== Test 3: Normal Flow ===")
    mock_llm.classify_intent.return_value = {
        "intent": "personnel_search",
        "confidence": 0.9,
    }
    mock_llm.extract_entities.return_value = {
        "entities": [{"type": "Person", "value": "Kim"}]
    }
    mock_llm.generate_cypher.side_effect = None
    mock_llm.generate_cypher.return_value = {
        "cypher": "MATCH (n) RETURN n",
        "parameters": {},
    }
    mock_neo4j.execute_cypher.return_value = [{"n": "Kim"}]
    mock_llm.generate_response.return_value = "Kim을 찾았습니다."

    result = await pipeline.run("정상 질문")
    print(f"Path: {result['metadata']['execution_path']}")
    expected_path = [
        "intent_classifier",
        "entity_extractor",
        "entity_resolver",
        "cypher_generator",
        "graph_executor",
        "response_generator",
    ]
    for node in expected_path:
        assert node in result["metadata"]["execution_path"]
    print("✅ Passed: Normal flow executed all nodes")


if __name__ == "__main__":
    asyncio.run(run_verification())
