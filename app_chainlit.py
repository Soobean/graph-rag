"""
Graph RAG Chat UI - Chainlit

파이프라인 실행 단계를 시각적으로 보여주는 Chat UI
"""

import chainlit as cl

from src.config import get_settings
from src.graph.pipeline import GraphRAGPipeline
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository


# 노드별 표시 정보
NODE_INFO = {
    "intent_classifier": {
        "name": "Intent Classification",
        "icon": "🎯",
        "type": "llm",
    },
    "entity_extractor": {
        "name": "Entity Extraction",
        "icon": "🔍",
        "type": "llm",
    },
    "schema_fetcher": {
        "name": "Schema Fetch",
        "icon": "📊",
        "type": "retrieval",
    },
    "entity_resolver": {
        "name": "Entity Resolution",
        "icon": "🔗",
        "type": "retrieval",
    },
    "clarification_handler": {
        "name": "Clarification",
        "icon": "❓",
        "type": "llm",
    },
    "cypher_generator": {
        "name": "Cypher Generation",
        "icon": "⚙️",
        "type": "llm",
    },
    "graph_executor": {
        "name": "Graph Query",
        "icon": "🗃️",
        "type": "retrieval",
    },
    "response_generator": {
        "name": "Response Generation",
        "icon": "💬",
        "type": "llm",
    },
}


def format_step_output(node_name: str, output: dict) -> str:
    """노드 출력을 읽기 쉬운 형태로 포맷팅"""
    if node_name == "intent_classifier":
        intent = output.get("intent", "unknown")
        confidence = output.get("intent_confidence", 0)
        return f"**Intent:** `{intent}` (confidence: {confidence:.2f})"

    elif node_name == "entity_extractor":
        entities = output.get("entities", {})
        if not entities:
            return "No entities extracted"
        lines = ["**Extracted Entities:**"]
        for category, items in entities.items():
            lines.append(f"- **{category}:** {', '.join(items)}")
        return "\n".join(lines)

    elif node_name == "schema_fetcher":
        schema = output.get("schema", {})
        labels = schema.get("node_labels", [])[:10]
        rels = schema.get("relationship_types", [])[:10]
        return f"**Labels:** {', '.join(labels)}\n**Relationships:** {', '.join(rels)}"

    elif node_name == "entity_resolver":
        resolved = output.get("resolved_entities", [])
        if not resolved:
            return "No entities to resolve"
        lines = ["**Resolved Entities:**"]
        for entity in resolved:
            status = "✅" if entity.get("id") else "❌"
            lines.append(f"- {status} {entity.get('type')}: {entity.get('value')}")
        return "\n".join(lines)

    elif node_name == "clarification_handler":
        response = output.get("response", "")
        return f"**Clarification needed:**\n{response}"

    elif node_name == "cypher_generator":
        cypher = output.get("cypher_query", "")
        params = output.get("cypher_parameters", {})
        if not cypher:
            return "No Cypher query generated"
        result = f"```cypher\n{cypher}\n```"
        if params:
            result += f"\n**Parameters:** `{params}`"
        return result

    elif node_name == "graph_executor":
        count = output.get("result_count", 0)
        results = output.get("query_results", [])
        if count == 0:
            return "No results found"
        preview = results[:3] if results else []
        lines = [f"**Found {count} results**"]
        for r in preview:
            lines.append(f"- {r}")
        if count > 3:
            lines.append(f"... and {count - 3} more")
        return "\n".join(lines)

    elif node_name == "response_generator":
        return output.get("response", "No response generated")

    return str(output)


@cl.on_chat_start
async def on_chat_start():
    """채팅 세션 시작 시 초기화"""
    settings = get_settings()

    # Neo4j 클라이언트 초기화
    neo4j_client = Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    await neo4j_client.connect()

    # Repository 초기화
    neo4j_repo = Neo4jRepository(neo4j_client)
    llm_repo = LLMRepository(settings)

    # Pipeline 초기화
    pipeline = GraphRAGPipeline(settings, neo4j_repo, llm_repo)

    # 세션에 저장
    cl.user_session.set("pipeline", pipeline)
    cl.user_session.set("neo4j_client", neo4j_client)

    await cl.Message(
        content="**Graph RAG System Ready**\n\n"
        "Neo4j 그래프 데이터베이스와 연결되었습니다.\n"
        "질문을 입력해주세요!"
    ).send()


@cl.on_chat_end
async def on_chat_end():
    """채팅 세션 종료 시 리소스 정리"""
    neo4j_client = cl.user_session.get("neo4j_client")
    if neo4j_client:
        await neo4j_client.close()


@cl.on_message
async def on_message(message: cl.Message):
    """사용자 메시지 처리"""
    pipeline: GraphRAGPipeline = cl.user_session.get("pipeline")

    if not pipeline:
        await cl.Message(content="Pipeline이 초기화되지 않았습니다.").send()
        return

    question = message.content

    # 최종 응답 메시지 (스트리밍용)
    final_msg = cl.Message(content="")
    await final_msg.send()

    final_response = ""

    # 파이프라인 스트리밍 실행
    async for event in pipeline.run_with_streaming(question):
        node_name = event.get("node")
        output = event.get("output", {})

        if node_name == "error":
            await cl.Message(content=f"**Error:** {output.get('error')}").send()
            return

        # 노드 정보 가져오기
        node_info = NODE_INFO.get(node_name, {
            "name": node_name,
            "icon": "📦",
            "type": "tool",
        })

        # Step으로 중간 결과 표시
        async with cl.Step(
            name=f"{node_info['icon']} {node_info['name']}",
            type=node_info["type"],
        ) as step:
            step.input = question if node_name == "intent_classifier" else ""
            formatted_output = format_step_output(node_name, output)
            step.output = formatted_output

        # response_generator의 경우 최종 응답 저장
        if node_name == "response_generator":
            final_response = output.get("response", "")
        elif node_name == "clarification_handler":
            final_response = output.get("response", "")

    # 최종 응답 업데이트
    final_msg.content = final_response
    await final_msg.update()


if __name__ == "__main__":
    from chainlit.cli import run_chainlit

    run_chainlit(__file__)
