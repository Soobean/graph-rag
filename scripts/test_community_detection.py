#!/usr/bin/env python3
"""
커뮤니티 탐지 테스트 스크립트

GDSService의 커뮤니티 탐지 기능을 테스트합니다.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.services.gds_service import GDSService


async def main():
    settings = get_settings()

    print("=" * 70)
    print("🔬 커뮤니티 탐지 테스트")
    print("=" * 70)

    async with GDSService(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    ) as gds:
        # 1. 스킬 유사도 그래프 프로젝션 생성
        print("\n📊 Step 1: 스킬 유사도 그래프 프로젝션 생성...")
        projection = await gds.create_skill_similarity_projection(
            min_shared_skills=2  # 최소 2개 이상 공유 스킬
        )
        print(f"   ✅ 노드: {projection['node_count']:,}개")
        print(f"   ✅ 관계: {projection['relationship_count']:,}개")

        # 2. Leiden 커뮤니티 탐지
        print("\n🎯 Step 2: Leiden 커뮤니티 탐지...")
        communities = await gds.detect_communities(
            algorithm="leiden",
            gamma=1.0,
        )
        print(f"   ✅ 알고리즘: {communities.algorithm}")
        print(f"   ✅ 커뮤니티 수: {communities.community_count}개")
        print(f"   ✅ Modularity: {communities.modularity:.4f}")

        # 상위 10개 커뮤니티 출력
        print("\n📋 상위 10개 커뮤니티:")
        print("-" * 70)
        for i, comm in enumerate(communities.communities[:10], 1):
            members = ", ".join(comm["sample_members"][:3])
            print(
                f"   {i}. 커뮤니티 {comm['community_id']}: "
                f"{comm['member_count']}명 ({members}...)"
            )

        # 3. 유사 직원 탐색 테스트
        print("\n🔍 Step 3: 유사 직원 탐색 테스트...")
        # 첫 번째 커뮤니티의 멤버로 테스트
        if communities.communities:
            test_name = communities.communities[0]["sample_members"][0]
            similar = await gds.find_similar_employees(test_name, top_k=5)
            print(f"   '{test_name}'와 유사한 직원:")
            for emp in similar:
                print(
                    f"   - {emp['name']} ({emp['job_type']}): "
                    f"유사도 {emp['similarity']:.1%}, "
                    f"공유 스킬 {emp['shared_skills']}개"
                )

        # 4. 팀 추천 테스트
        print("\n👥 Step 4: 팀 추천 테스트...")
        required_skills = ["Python", "Kubernetes", "React", "AWS"]
        print(f"   필요 스킬: {required_skills}")
        team = await gds.recommend_team(
            required_skills=required_skills,
            team_size=5,
            diversity_weight=0.3,
        )
        print(f"   ✅ 추천 팀원: {len(team.members)}명")
        print(f"   ✅ 스킬 커버리지: {team.skill_coverage:.1%}")
        print(f"   ✅ 커뮤니티 다양성: {team.community_diversity}개")

        print("\n   추천 팀원 상세:")
        for member in team.members:
            skills = ", ".join(member.get("matchedSkills", []))
            print(
                f"   - {member['name']} ({member['job_type']}): "
                f"스킬=[{skills}]"
            )

        # 5. 프로젝션 정리
        print("\n🧹 Step 5: 프로젝션 정리...")
        await gds.drop_projection()
        print("   ✅ 프로젝션 삭제 완료")

    print("\n" + "=" * 70)
    print("✅ 커뮤니티 탐지 테스트 완료!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
