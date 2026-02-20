"""
GDSService 단위 테스트

ThreadPoolExecutor 브릿지, 프로젝션 관리, 커뮤니티 탐지,
유사 직원 탐색, 팀 추천 로직을 검증합니다.

실행: pytest tests/test_gds_service.py -v
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.services.gds_service import (
    CommunityResult,
    GDSService,
    TeamRecommendation,
)


@pytest.fixture
def gds_service():
    """GDSService 인스턴스 (mock GDS 클라이언트 주입)"""
    service = GDSService(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
    )
    # GDS 클라이언트를 mock으로 직접 주입 (connect() 우회)
    service._gds = MagicMock()
    return service


# ── Connection Lifecycle ──────────────────────────────────


class TestGDSConnectionLifecycle:
    """연결/해제 라이프사이클 테스트"""

    async def test_gds_property_raises_when_not_connected(self):
        """connect() 없이 gds 접근 시 RuntimeError"""
        service = GDSService(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password",
        )
        with pytest.raises(RuntimeError, match="GDS not connected"):
            _ = service.gds

    async def test_gds_property_returns_client_when_connected(self, gds_service):
        """connect() 후 gds 프로퍼티 접근 가능"""
        client = gds_service.gds
        assert client is not None

    async def test_connect_skips_if_already_connected(self, gds_service):
        """이미 연결되어 있으면 재연결하지 않음"""
        existing_gds = gds_service._gds
        await gds_service.connect()
        assert gds_service._gds is existing_gds  # 변경되지 않음

    @patch("src.services.gds_service.GraphDataScience")
    async def test_connect_creates_gds_client(self, MockGDS):
        """connect()가 GraphDataScience 클라이언트를 생성"""
        mock_instance = MagicMock()
        MockGDS.return_value = mock_instance

        service = GDSService(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password",
        )
        await service.connect()

        assert service._gds is mock_instance

    async def test_close_cleans_up(self, gds_service):
        """close()가 리소스를 정리"""
        await gds_service.close()
        assert gds_service._gds is None

    async def test_async_context_manager(self):
        """async with 컨텍스트 매니저"""
        service = GDSService(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password",
        )
        service._gds = MagicMock()

        async with service as svc:
            assert svc is service
            assert svc._gds is not None

        # __aexit__ 후 정리됨
        assert service._gds is None


# ── Projection Management ──────────────────────────────────


class TestProjectionManagement:
    """그래프 프로젝션 관리 테스트"""

    async def test_drop_projection_exists(self, gds_service):
        """존재하는 프로젝션 삭제 성공"""
        mock_gds = gds_service._gds
        mock_gds.graph.exists.return_value = MagicMock(exists=True)
        mock_gds.graph.get.return_value = MagicMock()

        result = await gds_service.drop_projection("test_proj")

        assert result is True
        mock_gds.graph.drop.assert_called_once()

    async def test_drop_projection_not_exists(self, gds_service):
        """존재하지 않는 프로젝션은 False 반환"""
        mock_gds = gds_service._gds
        mock_gds.graph.exists.return_value = MagicMock(exists=False)

        result = await gds_service.drop_projection("nonexistent")

        assert result is False
        mock_gds.graph.drop.assert_not_called()

    async def test_drop_projection_uses_default_name(self, gds_service):
        """프로젝션 이름 미지정 시 기본값 사용"""
        mock_gds = gds_service._gds
        mock_gds.graph.exists.return_value = MagicMock(exists=False)

        await gds_service.drop_projection()

        mock_gds.graph.exists.assert_called_once_with(GDSService.SKILL_PROJECTION)

    async def test_get_projection_info_exists(self, gds_service):
        """프로젝션 정보 조회 (존재하는 경우)"""
        mock_gds = gds_service._gds
        mock_gds.graph.exists.return_value = MagicMock(exists=True)

        mock_graph = MagicMock()
        mock_graph.name.return_value = "test_proj"
        mock_graph.node_count.return_value = 100
        mock_graph.relationship_count.return_value = 500
        mock_graph.node_labels.return_value = ["Employee"]
        mock_graph.relationship_types.return_value = ["SIMILAR"]
        mock_gds.graph.get.return_value = mock_graph

        exists, info = await gds_service.get_projection_info("test_proj")

        assert exists is True
        assert info["name"] == "test_proj"
        assert info["nodeCount"] == 100
        assert info["relationshipCount"] == 500

    async def test_get_projection_info_not_exists(self, gds_service):
        """프로젝션 정보 조회 (존재하지 않는 경우)"""
        mock_gds = gds_service._gds
        mock_gds.graph.exists.return_value = MagicMock(exists=False)

        exists, info = await gds_service.get_projection_info("missing")

        assert exists is False
        assert info == {}

    async def test_cleanup_all_projections(self, gds_service):
        """모든 프로젝션 정리"""
        mock_gds = gds_service._gds

        # 2개의 프로젝션이 있는 DataFrame 반환
        mock_df = pd.DataFrame(
            [
                {"graphName": "proj1"},
                {"graphName": "proj2"},
            ]
        )
        mock_gds.graph.list.return_value = mock_df
        mock_gds.graph.get.return_value = MagicMock()

        count = await gds_service.cleanup_all_projections()

        assert count == 2
        assert mock_gds.graph.drop.call_count == 2


# ── Community Detection ──────────────────────────────────


class TestCommunityDetection:
    """커뮤니티 탐지 테스트"""

    async def test_detect_communities_leiden(self, gds_service):
        """Leiden 알고리즘 커뮤니티 탐지"""
        mock_gds = gds_service._gds
        mock_gds.graph.exists.return_value = MagicMock(exists=True)
        mock_gds.graph.get.return_value = MagicMock()

        mock_gds.leiden.write.return_value = {
            "nodePropertiesWritten": 50,
            "communityCount": 5,
            "modularity": 0.72,
        }

        community_df = pd.DataFrame(
            [
                {
                    "community_id": 0,
                    "member_count": 20,
                    "sample_members": ["김철수", "이영희"],
                },
                {"community_id": 1, "member_count": 15, "sample_members": ["박지우"]},
            ]
        )
        mock_gds.run_cypher.return_value = community_df

        result = await gds_service.detect_communities(algorithm="leiden")

        assert isinstance(result, CommunityResult)
        assert result.algorithm == "leiden"
        assert result.node_count == 50
        assert result.community_count == 5
        assert result.modularity == 0.72
        assert len(result.communities) == 2

    async def test_detect_communities_louvain(self, gds_service):
        """Louvain 알고리즘 커뮤니티 탐지"""
        mock_gds = gds_service._gds
        mock_gds.graph.exists.return_value = MagicMock(exists=True)
        mock_gds.graph.get.return_value = MagicMock()

        mock_gds.louvain.write.return_value = {
            "nodePropertiesWritten": 30,
            "communityCount": 3,
            "modularity": 0.65,
        }

        mock_gds.run_cypher.return_value = pd.DataFrame([])

        result = await gds_service.detect_communities(algorithm="louvain")

        assert result.algorithm == "louvain"
        assert result.community_count == 3
        mock_gds.louvain.write.assert_called_once()
        mock_gds.leiden.write.assert_not_called()

    async def test_detect_communities_projection_missing(self, gds_service):
        """프로젝션이 없으면 ValueError"""
        mock_gds = gds_service._gds
        mock_gds.graph.exists.return_value = MagicMock(exists=False)

        with pytest.raises(ValueError, match="not found"):
            await gds_service.detect_communities()

    async def test_detect_communities_validates_write_property(self, gds_service):
        """write_property 인젝션 방지"""
        with pytest.raises(ValueError, match="Invalid write_property"):
            await gds_service.detect_communities(write_property="a; DROP")


# ── Similar Employees ──────────────────────────────────


class TestFindSimilarEmployees:
    """유사 직원 탐색 테스트"""

    async def test_find_similar_employees_success(self, gds_service):
        """유사 직원 탐색 정상 반환"""
        mock_gds = gds_service._gds
        result_df = pd.DataFrame(
            [
                {
                    "name": "이영희",
                    "job_type": "개발",
                    "experience": 5,
                    "community_id": 1,
                    "shared_skills": 4,
                    "similarity": 0.75,
                    "common_skills": ["Python", "React", "AWS", "Docker"],
                },
                {
                    "name": "박지우",
                    "job_type": "개발",
                    "experience": 3,
                    "community_id": 2,
                    "shared_skills": 3,
                    "similarity": 0.6,
                    "common_skills": ["Python", "React", "Node.js"],
                },
            ]
        )
        mock_gds.run_cypher.return_value = result_df

        results = await gds_service.find_similar_employees("김철수", top_k=5)

        assert len(results) == 2
        assert results[0]["name"] == "이영희"
        assert results[0]["similarity"] == 0.75

        # Cypher에 toLower 사용 확인
        call_args = mock_gds.run_cypher.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "toLower" in query
        assert params["name"] == "김철수"
        assert params["top_k"] == 5

    async def test_find_similar_employees_no_results(self, gds_service):
        """유사 직원 없는 경우 빈 리스트"""
        mock_gds = gds_service._gds
        mock_gds.run_cypher.return_value = pd.DataFrame([])

        results = await gds_service.find_similar_employees("새사람")

        assert results == []


# ── Team Recommendation ──────────────────────────────────


class TestTeamRecommendation:
    """팀 추천 테스트"""

    async def test_recommend_team_success(self, gds_service):
        """팀 추천 정상 반환"""
        mock_gds = gds_service._gds
        candidates_df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "김철수",
                    "job_type": "개발",
                    "experience": 5,
                    "community_id": 1,
                    "matchedSkills": ["Python", "AWS"],
                    "skillCount": 2,
                    "skill_score": 0.67,
                },
                {
                    "id": "2",
                    "name": "이영희",
                    "job_type": "개발",
                    "experience": 3,
                    "community_id": 2,
                    "matchedSkills": ["React"],
                    "skillCount": 1,
                    "skill_score": 0.33,
                },
            ]
        )
        mock_gds.run_cypher.return_value = candidates_df

        result = await gds_service.recommend_team(
            required_skills=["Python", "AWS", "React"],
            team_size=3,
        )

        assert isinstance(result, TeamRecommendation)
        assert len(result.members) == 2
        assert result.skill_coverage > 0
        assert result.community_diversity >= 1

    async def test_recommend_team_no_candidates(self, gds_service):
        """후보가 없는 경우"""
        mock_gds = gds_service._gds
        mock_gds.run_cypher.return_value = pd.DataFrame([])

        result = await gds_service.recommend_team(
            required_skills=["Rust", "Zig"],
        )

        assert isinstance(result, TeamRecommendation)
        assert result.members == []
        assert result.skill_coverage == 0.0
        assert result.missing_skills == ["Rust", "Zig"]
        assert result.total_score == 0.0

    async def test_recommend_team_skill_coverage_calculation(self, gds_service):
        """스킬 커버리지 계산 정확성"""
        mock_gds = gds_service._gds
        # 2명이 3개 스킬 중 2개를 커버
        candidates_df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "A",
                    "job_type": "개발",
                    "experience": 5,
                    "community_id": 1,
                    "matchedSkills": ["Python"],
                    "skillCount": 1,
                    "skill_score": 0.33,
                },
                {
                    "id": "2",
                    "name": "B",
                    "job_type": "개발",
                    "experience": 3,
                    "community_id": 2,
                    "matchedSkills": ["AWS"],
                    "skillCount": 1,
                    "skill_score": 0.33,
                },
            ]
        )
        mock_gds.run_cypher.return_value = candidates_df

        result = await gds_service.recommend_team(
            required_skills=["Python", "AWS", "React"],
        )

        # 3개 중 2개 커버 → 0.667
        assert result.skill_coverage == pytest.approx(0.667, abs=0.01)
        assert "React" in result.missing_skills

    async def test_recommend_team_respects_team_size(self, gds_service):
        """팀 크기 제한"""
        mock_gds = gds_service._gds
        # 5명 후보, 팀 크기 2
        candidates_df = pd.DataFrame(
            [
                {
                    "id": str(i),
                    "name": f"Employee{i}",
                    "job_type": "개발",
                    "experience": i,
                    "community_id": i,
                    "matchedSkills": [f"Skill{i}"],
                    "skillCount": 1,
                    "skill_score": 0.2,
                }
                for i in range(5)
            ]
        )
        mock_gds.run_cypher.return_value = candidates_df

        result = await gds_service.recommend_team(
            required_skills=["Skill0", "Skill1", "Skill2", "Skill3", "Skill4"],
            team_size=2,
        )

        assert len(result.members) <= 2


# ── Community Details ──────────────────────────────────


class TestCommunityDetails:
    """커뮤니티 상세 정보 테스트"""

    async def test_get_community_details(self, gds_service):
        """커뮤니티 상세 정보 조회"""
        mock_gds = gds_service._gds

        members_df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "김철수",
                    "job_type": "개발",
                    "experience": 5,
                    "top_skills": ["Python", "AWS"],
                },
            ]
        )
        skills_df = pd.DataFrame(
            [
                {"skill": "Python", "count": 5, "percentage": 83.3},
            ]
        )

        mock_gds.run_cypher.side_effect = [members_df, skills_df]

        result = await gds_service.get_community_details(community_id=1)

        assert result["community_id"] == 1
        assert result["member_count"] == 1
        assert len(result["members"]) == 1
        assert len(result["top_skills"]) == 1
        assert result["top_skills"][0]["skill"] == "Python"
