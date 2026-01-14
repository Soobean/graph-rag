#!/usr/bin/env python3
"""
Multi-hop 쿼리 분해 테스트 스크립트

QueryDecomposerNode의 쿼리 분해 기능을 테스트합니다.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.repositories.llm_repository import LLMRepository


async def test_query_decomposition():
    """쿼리 분해 테스트"""
    settings = get_settings()
    llm = LLMRepository(settings)

    print("=" * 70)
    print("🔬 Multi-hop 쿼리 분해 테스트")
    print("=" * 70)

    # 테스트 쿼리들
    test_queries = [
        # Multi-hop 쿼리
        ("Python 잘하는 사람의 멘토 중 AWS 경험자는?", True, 3),
        ("김철수와 같은 프로젝트에 참여한 사람들의 스킬은?", True, 3),
        ("ML팀 출신 중 현재 DevOps팀에서 리더인 사람?", True, 3),
        ("React 개발자가 참여한 프로젝트의 다른 참여자들은?", True, 3),
        # Single-hop 쿼리
        ("Python 개발자 누구야?", False, 1),
        ("개발팀 팀장 알려줘", False, 1),
    ]

    results = []

    for i, (query, expected_multi_hop, expected_hops) in enumerate(test_queries, 1):
        print(f"\n📋 테스트 {i}: {query}")
        print("-" * 70)

        try:
            result = await llm.decompose_query(question=query)

            is_multi_hop = result.get("is_multi_hop", False)
            hop_count = result.get("hop_count", 0)
            hops = result.get("hops", [])
            explanation = result.get("explanation", "")

            # 결과 출력
            print(f"   ✅ Multi-hop: {is_multi_hop} (expected: {expected_multi_hop})")
            print(f"   ✅ Hop count: {hop_count} (expected: {expected_hops})")
            print(f"   ✅ Explanation: {explanation}")

            if hops:
                print("\n   📊 분해된 단계:")
                for hop in hops:
                    step = hop.get("step", "?")
                    desc = hop.get("description", "")
                    rel = hop.get("relationship", "")
                    direction = hop.get("direction", "")
                    filter_cond = hop.get("filter_condition", "")
                    print(f"      Step {step}: {desc}")
                    print(f"         - Relationship: {rel} ({direction})")
                    if filter_cond:
                        print(f"         - Filter: {filter_cond}")

            # 검증
            passed = (is_multi_hop == expected_multi_hop)
            results.append((query, passed, is_multi_hop, expected_multi_hop))

            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"\n   {status}")

        except Exception as e:
            print(f"   ❌ 에러: {e}")
            results.append((query, False, None, expected_multi_hop))

    # 요약
    print("\n" + "=" * 70)
    print("📊 테스트 요약")
    print("=" * 70)

    passed = sum(1 for _, p, _, _ in results if p)
    total = len(results)

    print(f"\n   통과: {passed}/{total}")

    for query, p, actual, expected in results:
        status = "✅" if p else "❌"
        print(f"   {status} {query[:40]}... (actual={actual}, expected={expected})")

    await llm.close()

    print("\n" + "=" * 70)
    return passed == total


async def test_full_pipeline():
    """전체 파이프라인 테스트 (Multi-hop 쿼리)"""
    from src.infrastructure.neo4j_client import Neo4jClient
    from src.repositories.neo4j_repository import Neo4jRepository
    from src.graph.pipeline import GraphRAGPipeline

    settings = get_settings()

    print("\n" + "=" * 70)
    print("🔬 전체 파이프라인 Multi-hop 테스트")
    print("=" * 70)

    async with Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    ) as neo4j_client:
        neo4j_repo = Neo4jRepository(neo4j_client)
        llm_repo = LLMRepository(settings)

        # 스키마 로드
        schema = await neo4j_repo.get_schema()

        pipeline = GraphRAGPipeline(
            settings=settings,
            neo4j_repository=neo4j_repo,
            llm_repository=llm_repo,
            neo4j_client=neo4j_client,
            graph_schema=schema,
        )

        # Multi-hop 테스트 쿼리
        test_queries = [
            "Python 개발자 중에서 AWS 경험도 있는 사람은?",
            "개발팀에서 Kubernetes 쓰는 사람의 멘토는 누구야?",
        ]

        for query in test_queries:
            print(f"\n📋 쿼리: {query}")
            print("-" * 70)

            result = await pipeline.run(query, session_id="test-multihop")

            if result["success"]:
                print(f"   ✅ 응답: {result['response'][:200]}...")

                metadata = result.get("metadata", {})
                exec_path = metadata.get("execution_path", [])
                print(f"   📊 실행 경로: {' → '.join(exec_path)}")

                # query_decomposer가 실행되었는지 확인
                if any("query_decomposer" in p for p in exec_path):
                    print("   ✅ QueryDecomposer 노드 실행됨")
                else:
                    print("   ⚠️ QueryDecomposer 노드 미실행")
            else:
                print(f"   ❌ 에러: {result.get('error', 'Unknown error')}")

        await llm_repo.close()

    print("\n" + "=" * 70)


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Multi-hop 쿼리 테스트")
    parser.add_argument(
        "--full",
        action="store_true",
        help="전체 파이프라인 테스트 포함",
    )
    args = parser.parse_args()

    # 쿼리 분해 테스트
    success = await test_query_decomposition()

    # 전체 파이프라인 테스트 (옵션)
    if args.full:
        await test_full_pipeline()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
