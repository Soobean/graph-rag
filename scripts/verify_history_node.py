import asyncio
import logging
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

# 프로젝트 루트 경로 추가
sys.path.append(str(Path(__file__).parent.parent))

from src.config import get_settings
from src.graph.pipeline import GraphRAGPipeline
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_history_native():
    logger.info("Starting Native Chat History verification...")

    settings = get_settings()

    # Simple Mock Repositories
    class MockNeo4jRepo:
        pass

    class MockLLMRepo:
        async def classify_intent(self, *args, **kwargs):
            return {"intent": "unknown", "confidence": 1.0}

        async def generate_response(self, *args, **kwargs):
            return "Mock AI Response"

    neo4j_repo = MockNeo4jRepo()
    llm_repo = MockLLMRepo()

    pipeline = GraphRAGPipeline(settings, neo4j_repo, llm_repo)

    # 1. First Turn
    session_id = "native-sess-1"
    question1 = "My name is Subin."
    logger.info(f"--- Turn 1: {question1} ---")

    # Run pipeline (Mock LLM returns 'unknown' intent -> response generator)
    result1 = await pipeline.run(question1, session_id=session_id)

    # Verify State in Checkpointer
    checkpointer = pipeline._checkpointer
    config = {"configurable": {"thread_id": session_id}}

    # Note: MemorySaver.aget behaves differently?
    # Actually LangGraph's get_state calls checkpoint.aget/get.
    # Let's use the graph's method to inspect state.
    state_snapshot = await pipeline._graph.aget_state(config)
    messages = state_snapshot.values.get("messages", [])

    logger.info(f"After Turn 1, Messages: {len(messages)}")
    for m in messages:
        logger.info(f" - {m.type}: {m.content}")

    # Expect: HumanMessage + AIMessage (total 2)
    if len(messages) >= 2:
        logger.info("✅ Turn 1 Saved.")
    else:
        logger.error("❌ Turn 1 Failed to save.")

    # 2. Second Turn
    question2 = "What is my name?"
    logger.info(f"--- Turn 2: {question2} ---")

    # Run pipeline again
    result2 = await pipeline.run(question2, session_id=session_id)

    state_snapshot_2 = await pipeline._graph.aget_state(config)
    messages_2 = state_snapshot_2.values.get("messages", [])

    logger.info(f"After Turn 2, Messages: {len(messages_2)}")
    for m in messages_2:
        logger.info(f" - {m.type}: {m.content}")

    # Expect: 2 (from turn 1) + 2 (from turn 2) = 4 messages
    if len(messages_2) >= 4:
        logger.info("✅ Verification SUCCESS: History accumulated correctly.")
    else:
        logger.error(
            f"❌ Verification FAILED: Expected 4+ messages, got {len(messages_2)}"
        )


if __name__ == "__main__":
    asyncio.run(verify_history_native())
