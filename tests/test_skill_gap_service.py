"""
SkillGapService 테스트

온톨로지 기반 스킬 갭 분석 서비스 테스트
- 스킬 커버리지 분석
- 유사 스킬 매칭
- 추천 기능
- 캐시 동작
"""

from time import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.schemas.skill_gap import CoverageStatus, MatchType
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.skill_gap_service import (
    CACHE_TTL_SECONDS,
    SkillGapService,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j Repository for SkillGapService"""
    neo4j = MagicMock(spec=Neo4jRepository)
    neo4j.execute_cypher = AsyncMock(return_value=[])
    return neo4j


@pytest.fixture
def skill_gap_service(mock_neo4j):
    """SkillGapService 인스턴스"""
    return SkillGapService(mock_neo4j)


# =============================================================================
# analyze() 테스트 - Happy Path
# =============================================================================


class TestAnalyzeHappyPath:
    """analyze() 메서드의 정상 케이스 테스트"""

    async def test_analyze_exact_match_returns_covered(
        self, skill_gap_service, mock_neo4j
    ):
        """정확한 스킬 매칭 시 COVERED 상태 반환"""
        # Given: 팀원이 필요한 스킬을 직접 보유
        mock_neo4j.execute_cypher = AsyncMock(
            side_effect=[
                # _get_team_skills 결과
                [{"employee": "홍길동", "skills": ["Python", "FastAPI"]}],
                # _prefetch_skill_metadata 결과
                [
                    {
                        "skill_name": "Python",
                        "canonical": None,
                        "category": "Backend",
                    }
                ],
            ]
        )

        # When
        result = await skill_gap_service.analyze(
            required_skills=["Python"],
            team_members=["홍길동"],
        )

        # Then
        assert result.overall_status == CoverageStatus.COVERED
        assert len(result.skill_details) == 1
        assert result.skill_details[0].status == CoverageStatus.COVERED
        assert "홍길동" in result.skill_details[0].exact_matches
        assert result.gaps == []

    async def test_analyze_similar_skill_returns_partial(
        self, skill_gap_service, mock_neo4j
    ):
        """유사 스킬 매칭 시 PARTIAL 상태 반환"""
        # Given: 팀원이 같은 카테고리의 다른 스킬 보유
        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1

            if "HAS_SKILL" in query:
                # _get_team_skills
                return [{"employee": "홍길동", "skills": ["Java"]}]
            elif "UNWIND" in query:
                # _prefetch_skill_metadata
                return [
                    {
                        "skill_name": "Python",
                        "canonical": None,
                        "category": "Backend",
                    },
                    {"skill_name": "Java", "canonical": None, "category": "Backend"},
                ]
            elif "IS_A*0.." in query:
                # _find_skill_relation (LCA 쿼리)
                return [{"common_ancestor": "Backend"}]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.analyze(
            required_skills=["Python"],
            team_members=["홍길동"],
        )

        # Then
        assert result.overall_status == CoverageStatus.PARTIAL
        assert result.skill_details[0].status == CoverageStatus.PARTIAL
        assert len(result.skill_details[0].similar_matches) == 1
        assert result.skill_details[0].similar_matches[0].possessed_skill == "Java"
        assert (
            result.skill_details[0].similar_matches[0].match_type
            == MatchType.SAME_CATEGORY
        )

    async def test_analyze_no_match_returns_gap(self, skill_gap_service, mock_neo4j):
        """관련 스킬 없을 시 GAP 상태 반환"""
        # Given: 팀원의 스킬이 필요 스킬과 무관
        async def mock_execute(query, params=None):
            if "HAS_SKILL" in query:
                return [{"employee": "홍길동", "skills": ["Excel"]}]
            elif "UNWIND" in query:
                return [
                    {"skill_name": "Python", "canonical": None, "category": "Backend"},
                    {"skill_name": "Excel", "canonical": None, "category": "Office"},
                ]
            elif "IS_A*0.." in query:
                # 공통 조상 없음
                return []
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.analyze(
            required_skills=["Python"],
            team_members=["홍길동"],
        )

        # Then
        assert result.overall_status == CoverageStatus.GAP
        assert result.skill_details[0].status == CoverageStatus.GAP
        assert result.gaps == ["Python"]


# =============================================================================
# analyze() 테스트 - Edge Cases
# =============================================================================


class TestAnalyzeEdgeCases:
    """analyze() 메서드의 엣지 케이스 테스트"""

    async def test_analyze_empty_team_raises_error(self, skill_gap_service):
        """빈 team_members는 허용하지 않음"""
        # When/Then
        with pytest.raises(ValueError) as exc_info:
            await skill_gap_service.analyze(
                required_skills=["Python", "Java"],
                team_members=[],
            )

        assert "빈 리스트" in str(exc_info.value)

    async def test_analyze_unknown_skill_returns_gap(
        self, skill_gap_service, mock_neo4j
    ):
        """온톨로지에 없는 스킬은 GAP 처리"""
        # Given: 온톨로지에 존재하지 않는 스킬
        async def mock_execute(query, params=None):
            if "HAS_SKILL" in query:
                return [{"employee": "홍길동", "skills": ["Python"]}]
            elif "UNWIND" in query:
                # UnknownTech는 온톨로지에 없음 - category가 None
                return [
                    {
                        "skill_name": "UnknownTech",
                        "canonical": None,
                        "category": None,
                    },
                    {
                        "skill_name": "Python",
                        "canonical": None,
                        "category": "Backend",
                    },
                ]
            elif "IS_A*0.." in query:
                return []  # 관계 없음
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.analyze(
            required_skills=["UnknownTech"],
            team_members=["홍길동"],
        )

        # Then
        assert result.skill_details[0].category is None
        assert result.skill_details[0].status == CoverageStatus.GAP

    async def test_analyze_multiple_skills_mixed_status(
        self, skill_gap_service, mock_neo4j
    ):
        """여러 스킬 분석 시 혼합된 상태 처리"""
        # Given: 일부 스킬만 보유
        async def mock_execute(query, params=None):
            if "HAS_SKILL" in query:
                return [{"employee": "홍길동", "skills": ["Python"]}]
            elif "UNWIND" in query:
                return [
                    {
                        "skill_name": "Python",
                        "canonical": None,
                        "category": "Backend",
                    },
                    {"skill_name": "NLP", "canonical": None, "category": "AI/ML"},
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.analyze(
            required_skills=["Python", "NLP"],
            team_members=["홍길동"],
        )

        # Then
        assert result.total_required_skills == 2
        # Python은 COVERED, NLP는 GAP → 전체는 GAP
        assert result.overall_status == CoverageStatus.GAP
        assert len(result.gaps) == 1
        assert "NLP" in result.gaps


# =============================================================================
# recommend_for_skill() 테스트
# =============================================================================


class TestRecommendForSkill:
    """recommend_for_skill() 메서드 테스트"""

    async def test_recommend_returns_internal_candidates(
        self, skill_gap_service, mock_neo4j
    ):
        """유사 스킬 보유자를 내부 추천으로 반환"""
        # Given: 형제 스킬 보유자 존재
        async def mock_execute(query, params=None):
            # 쿼리 패턴에 따라 결과 반환 (순서 중요: 구체적인 패턴 먼저)
            if "sibling" in query.lower():
                # _find_internal_candidates - 형제 스킬 찾기 쿼리
                return [
                    {
                        "employee": "김철수",
                        "department": "AI팀",
                        "matched_skills": ["TensorFlow"],
                        "common_category": "AI/ML",
                        "all_skills": ["TensorFlow", "Python", "Keras"],
                        "project_count": 2,
                    }
                ]
            elif "IS_A]->(category)" in query:
                # _get_skill_category
                return [{"category": "AI/ML"}]
            elif "SAME_AS" in query:
                # _generate_external_search_query
                return [{"synonyms": ["자연어처리", "Natural Language Processing"]}]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.recommend_for_skill(
            skill="NLP",
            exclude_members=["홍길동"],
            limit=5,
        )

        # Then
        assert result.target_skill == "NLP"
        assert result.category == "AI/ML"
        assert len(result.internal_candidates) == 1
        assert result.internal_candidates[0].name == "김철수"
        assert result.internal_candidates[0].matched_skill == "TensorFlow"

    async def test_recommend_generates_external_search_query(
        self, skill_gap_service, mock_neo4j
    ):
        """동의어 기반 외부 검색 키워드 생성"""
        # Given
        async def mock_execute(query, params=None):
            if "SAME_AS" in query:
                return [{"synonyms": ["NLP", "자연어처리"]}]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.recommend_for_skill(
            skill="NLP",
            exclude_members=[],
        )

        # Then
        assert "NLP" in result.external_search_query
        assert "자연어처리" in result.external_search_query


# =============================================================================
# get_categories() 테스트
# =============================================================================


class TestGetCategories:
    """get_categories() 메서드 테스트"""

    async def test_get_categories_returns_list(self, skill_gap_service, mock_neo4j):
        """카테고리 목록 반환"""
        # Given
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[
                {"category": "Backend", "skills": ["Python", "Java", "Go"]},
                {"category": "Frontend", "skills": ["React", "Vue", "Angular"]},
            ]
        )

        # When
        result = await skill_gap_service.get_categories()

        # Then
        assert len(result) == 2
        assert result[0].name == "Backend"
        assert "Python" in result[0].skills
        # 색상이 할당되어야 함
        assert result[0].color == "#10B981"  # Backend 색상

    async def test_get_categories_handles_error(self, skill_gap_service, mock_neo4j):
        """카테고리 조회 실패 시 빈 리스트 반환"""
        # Given
        mock_neo4j.execute_cypher = AsyncMock(side_effect=Exception("DB Error"))

        # When
        result = await skill_gap_service.get_categories()

        # Then
        assert result == []


# =============================================================================
# 캐시 동작 테스트
# =============================================================================


class TestCacheBehavior:
    """캐시 관련 동작 테스트"""

    async def test_cache_is_used_for_repeated_queries(
        self, skill_gap_service, mock_neo4j
    ):
        """반복 조회 시 캐시 사용"""
        # Given
        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            if "category" in query.lower() and "IS_A" in query:
                call_count += 1
                return [{"category": "Backend"}]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When: 같은 스킬 카테고리를 두 번 조회
        await skill_gap_service._get_skill_category("Python")
        await skill_gap_service._get_skill_category("Python")

        # Then: DB는 한 번만 호출됨
        assert call_count == 1

    async def test_cache_expires_after_ttl(self, skill_gap_service, mock_neo4j):
        """TTL 초과 시 캐시 만료"""
        # Given: 캐시에 데이터 저장
        skill_gap_service._category_cache["Python"] = "Backend"

        # When: TTL 초과 시뮬레이션
        skill_gap_service._cache_timestamp = time() - CACHE_TTL_SECONDS - 1
        skill_gap_service._clear_cache_if_expired()

        # Then: 캐시가 비워짐
        assert len(skill_gap_service._category_cache) == 0

    async def test_analyze_clears_expired_cache(self, skill_gap_service, mock_neo4j):
        """analyze() 호출 시 만료된 캐시 정리"""
        # Given
        skill_gap_service._category_cache["OldSkill"] = "OldCategory"
        skill_gap_service._cache_timestamp = time() - CACHE_TTL_SECONDS - 1

        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        # When
        await skill_gap_service.analyze(
            required_skills=["Python"],
            team_members=["홍길동"],
        )

        # Then: 기존 캐시가 정리됨
        assert "OldSkill" not in skill_gap_service._category_cache

    async def test_recommend_clears_expired_cache(self, skill_gap_service, mock_neo4j):
        """recommend_for_skill() 호출 시 만료된 캐시 정리"""
        # Given
        skill_gap_service._category_cache["OldSkill"] = "OldCategory"
        skill_gap_service._cache_timestamp = time() - CACHE_TTL_SECONDS - 1

        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        # When
        await skill_gap_service.recommend_for_skill(
            skill="Python",
            exclude_members=[],
        )

        # Then
        assert "OldSkill" not in skill_gap_service._category_cache

    async def test_get_categories_clears_expired_cache(
        self, skill_gap_service, mock_neo4j
    ):
        """get_categories() 호출 시 만료된 캐시 정리"""
        # Given
        skill_gap_service._category_cache["OldSkill"] = "OldCategory"
        skill_gap_service._cache_timestamp = time() - CACHE_TTL_SECONDS - 1

        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        # When
        await skill_gap_service.get_categories()

        # Then
        assert "OldSkill" not in skill_gap_service._category_cache


# =============================================================================
# 카테고리 요약 테스트
# =============================================================================


class TestCategorySummary:
    """_summarize_by_category() 메서드 테스트"""

    async def test_category_summary_calculates_ratio_correctly(
        self, skill_gap_service, mock_neo4j
    ):
        """카테고리별 커버리지 비율 계산"""
        # Given: Backend 2개 스킬 - 1 covered, 1 partial
        async def mock_execute(query, params=None):
            if "HAS_SKILL" in query:
                return [{"employee": "홍길동", "skills": ["Python", "Go"]}]
            elif "UNWIND" in query:
                return [
                    {
                        "skill_name": "Python",
                        "canonical": None,
                        "category": "Backend",
                    },
                    {"skill_name": "Java", "canonical": None, "category": "Backend"},
                    {"skill_name": "Go", "canonical": None, "category": "Backend"},
                ]
            elif "IS_A*0.." in query:
                # Java와 Go는 같은 Backend 카테고리
                return [{"common_ancestor": "Backend"}]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.analyze(
            required_skills=["Python", "Java"],
            team_members=["홍길동"],
        )

        # Then
        backend_summary = next(
            (c for c in result.category_summary if c.category == "Backend"), None
        )
        assert backend_summary is not None
        assert backend_summary.total_skills == 2
        # Python: covered (1), Java: partial via Go (0.5)
        # coverage_ratio = (1 + 0.5) / 2 = 0.75
        assert backend_summary.coverage_ratio == 0.75


# =============================================================================
# 추천 메시지 테스트
# =============================================================================


class TestRecommendations:
    """_generate_recommendations() 메서드 테스트"""

    async def test_recommendations_for_partial_coverage(
        self, skill_gap_service, mock_neo4j
    ):
        """PARTIAL 상태 스킬에 대한 교육 추천"""
        # Given
        async def mock_execute(query, params=None):
            if "HAS_SKILL" in query:
                return [{"employee": "홍길동", "skills": ["TensorFlow"]}]
            elif "UNWIND" in query:
                return [
                    {"skill_name": "NLP", "canonical": None, "category": "AI/ML"},
                    {
                        "skill_name": "TensorFlow",
                        "canonical": None,
                        "category": "AI/ML",
                    },
                ]
            elif "IS_A*0.." in query:
                return [{"common_ancestor": "AI/ML"}]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.analyze(
            required_skills=["NLP"],
            team_members=["홍길동"],
        )

        # Then
        assert len(result.recommendations) > 0
        assert "TensorFlow" in result.recommendations[0]
        assert "홍길동" in result.recommendations[0]
        assert "NLP" in result.recommendations[0]

    async def test_recommendations_for_gap(self, skill_gap_service, mock_neo4j):
        """GAP 상태 스킬에 대한 충원 추천"""
        # Given
        mock_neo4j.execute_cypher = AsyncMock(
            side_effect=[
                [],  # _get_team_skills
                [],  # _prefetch_skill_metadata
            ]
        )

        # When
        result = await skill_gap_service.analyze(
            required_skills=["Kubernetes"],
            team_members=["홍길동"],
        )

        # Then
        assert any("Kubernetes" in r and "충원" in r for r in result.recommendations)


# =============================================================================
# 에러 핸들링 테스트
# =============================================================================


class TestErrorHandling:
    """에러 핸들링 테스트"""

    async def test_get_team_skills_propagates_db_error(
        self, skill_gap_service, mock_neo4j
    ):
        """팀 스킬 조회 실패 시 예외 전파"""
        # Given
        mock_neo4j.execute_cypher = AsyncMock(side_effect=Exception("DB Error"))

        # When/Then: 예외가 전파되어야 함
        with pytest.raises(Exception) as exc_info:
            await skill_gap_service._get_team_skills(["홍길동"])

        assert "DB Error" in str(exc_info.value)

    async def test_prefetch_handles_db_error_gracefully(
        self, skill_gap_service, mock_neo4j
    ):
        """메타데이터 prefetch 실패해도 계속 진행"""
        # Given
        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # _get_team_skills
            elif call_count == 2:
                raise Exception("Prefetch failed")  # _prefetch_skill_metadata
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When: 예외가 발생하지 않아야 함
        result = await skill_gap_service.analyze(
            required_skills=["Python"],
            team_members=["홍길동"],
        )

        # Then: 결과가 반환되어야 함 (빈 결과라도)
        assert result is not None
        assert result.overall_status == CoverageStatus.GAP


# =============================================================================
# project_id 기반 팀원 조회 테스트
# =============================================================================


class TestProjectIdResolution:
    """project_id 기반 팀원 자동 조회 테스트"""

    async def test_resolve_with_team_members_uses_direct_list(
        self, skill_gap_service, mock_neo4j
    ):
        """team_members 직접 지정 시 그대로 사용"""
        # Given
        team_members = ["홍길동", "김철수"]

        # When
        result = await skill_gap_service._resolve_team_members(
            team_members=team_members,
            project_id=None,
        )

        # Then: 직접 지정한 목록 반환
        assert result == team_members
        # DB 호출 없음
        mock_neo4j.execute_cypher.assert_not_called()

    async def test_resolve_with_project_id_queries_db(
        self, skill_gap_service, mock_neo4j
    ):
        """project_id 지정 시 프로젝트에서 팀원 조회"""
        # Given
        mock_neo4j.execute_cypher = AsyncMock(
            return_value=[{"members": ["홍길동", "김철수", "박지수"]}]
        )

        # When
        result = await skill_gap_service._resolve_team_members(
            team_members=None,
            project_id="GraphRAG 프로젝트",
        )

        # Then
        assert result == ["홍길동", "김철수", "박지수"]
        mock_neo4j.execute_cypher.assert_called_once()

    async def test_resolve_with_both_prefers_team_members(
        self, skill_gap_service, mock_neo4j
    ):
        """team_members와 project_id 둘 다 있으면 team_members 우선"""
        # Given
        team_members = ["홍길동"]

        # When
        result = await skill_gap_service._resolve_team_members(
            team_members=team_members,
            project_id="GraphRAG 프로젝트",
        )

        # Then: team_members 우선 사용
        assert result == team_members
        # DB 호출 없음
        mock_neo4j.execute_cypher.assert_not_called()

    async def test_resolve_raises_error_when_neither_provided(
        self, skill_gap_service, mock_neo4j
    ):
        """team_members와 project_id 모두 없으면 에러"""
        # When/Then
        with pytest.raises(ValueError) as exc_info:
            await skill_gap_service._resolve_team_members(
                team_members=None,
                project_id=None,
            )

        assert "team_members 또는 project_id" in str(exc_info.value)

    async def test_resolve_raises_error_when_project_has_no_members(
        self, skill_gap_service, mock_neo4j
    ):
        """프로젝트에 팀원이 없으면 에러"""
        # Given: 빈 팀원 목록 반환
        mock_neo4j.execute_cypher = AsyncMock(return_value=[{"members": []}])

        # When/Then
        with pytest.raises(ValueError) as exc_info:
            await skill_gap_service._resolve_team_members(
                team_members=None,
                project_id="빈 프로젝트",
            )

        assert "참여 중인 팀원이 없습니다" in str(exc_info.value)

    async def test_resolve_raises_error_on_db_failure(
        self, skill_gap_service, mock_neo4j
    ):
        """DB 조회 실패 시 에러"""
        # Given
        mock_neo4j.execute_cypher = AsyncMock(side_effect=Exception("Connection failed"))

        # When/Then
        with pytest.raises(ValueError) as exc_info:
            await skill_gap_service._resolve_team_members(
                team_members=None,
                project_id="GraphRAG 프로젝트",
            )

        assert "조회 실패" in str(exc_info.value)

    async def test_analyze_with_project_id_resolves_members(
        self, skill_gap_service, mock_neo4j
    ):
        """analyze()에서 project_id로 팀원 조회 후 분석"""
        # Given
        async def mock_execute(query, params=None):
            if "WORKS_ON" in query:
                # _resolve_team_members - 프로젝트 팀원 조회
                return [{"members": ["홍길동"]}]
            elif "HAS_SKILL" in query:
                # _get_team_skills
                return [{"employee": "홍길동", "skills": ["Python"]}]
            elif "UNWIND" in query:
                # _prefetch_skill_metadata
                return [
                    {"skill_name": "Python", "canonical": None, "category": "Backend"}
                ]
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute)

        # When
        result = await skill_gap_service.analyze(
            required_skills=["Python"],
            project_id="GraphRAG 프로젝트",
        )

        # Then
        assert result.team_members == ["홍길동"]
        assert result.overall_status == CoverageStatus.COVERED
