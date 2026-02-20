"""
알려진 버그 Regression 테스트

실행: pytest tests/test_regression_bugs.py -v

커버리지:
  - Korean suffix stripping (strip_korean_suffix)
  - 3-step entity name fallback (find_entities_by_name)
  - Employee 중복 노드 name-based grouping (Cypher 패턴 검증)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.repositories.neo4j_entity_repository import Neo4jEntityRepository
from src.repositories.neo4j_validators import strip_korean_suffix


# ── Korean Suffix Stripping ──────────────────────────────────


MOCK_KOREAN_SUFFIXES = ("프로젝트", "팀", "부서", "회사", "센터", "연구소", "본부", "사업부")


@patch(
    "src.repositories.neo4j_validators.get_ontology_loader",
)
class TestStripKoreanSuffix:
    """strip_korean_suffix() regression 테스트"""

    def _setup_loader(self, mock_get_loader):
        loader = MagicMock()
        loader.get_korean_suffixes.return_value = MOCK_KOREAN_SUFFIXES
        mock_get_loader.return_value = loader

    def test_strip_project_suffix(self, mock_get_loader):
        """'챗봇 리뉴얼 프로젝트' → '챗봇 리뉴얼'"""
        self._setup_loader(mock_get_loader)
        assert strip_korean_suffix("챗봇 리뉴얼 프로젝트") == "챗봇 리뉴얼"

    def test_strip_team_suffix(self, mock_get_loader):
        """'AI 개발팀' → 'AI 개발'"""
        self._setup_loader(mock_get_loader)
        assert strip_korean_suffix("AI 개발팀") == "AI 개발"

    def test_strip_department_suffix(self, mock_get_loader):
        """'인사부서' → '인사'"""
        self._setup_loader(mock_get_loader)
        assert strip_korean_suffix("인사부서") == "인사"

    def test_no_suffix_english(self, mock_get_loader):
        """영문 이름은 변경 없음"""
        self._setup_loader(mock_get_loader)
        assert strip_korean_suffix("Python") == "Python"

    def test_no_suffix_korean(self, mock_get_loader):
        """접미사 없는 한국어도 변경 없음"""
        self._setup_loader(mock_get_loader)
        assert strip_korean_suffix("홍길동") == "홍길동"

    def test_safety_check_name_equals_suffix(self, mock_get_loader):
        """이름 자체가 접미사인 경우 제거하지 않음 (안전 장치)"""
        self._setup_loader(mock_get_loader)
        # "프로젝트"는 len(stripped) > len(suffix) + 1 조건 불충족
        assert strip_korean_suffix("프로젝트") == "프로젝트"

    def test_only_first_matching_suffix_removed(self, mock_get_loader):
        """여러 접미사가 매칭되어도 마지막 하나만 제거 (break)"""
        self._setup_loader(mock_get_loader)
        # "AI 연구소 프로젝트" → "AI 연구소" (프로젝트만 제거, 연구소는 남음)
        assert strip_korean_suffix("AI 연구소 프로젝트") == "AI 연구소"

    def test_whitespace_handling(self, mock_get_loader):
        """앞뒤 공백 처리"""
        self._setup_loader(mock_get_loader)
        assert strip_korean_suffix("  챗봇 리뉴얼 프로젝트  ") == "챗봇 리뉴얼"


# ── 3-Step Entity Name Fallback ──────────────────────────────


class TestFindEntitiesByNameFallback:
    """find_entities_by_name() 3단계 폴백 regression 테스트"""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.execute_query = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def repo(self, mock_client):
        return Neo4jEntityRepository(mock_client)

    async def test_exact_match_found(self, repo, mock_client):
        """1단계: toLower 정확 일치 성공"""
        mock_client.execute_query.return_value = [
            {"id": "1", "labels": ["Employee"], "properties": {"name": "홍길동"}}
        ]

        results = await repo.find_entities_by_name("홍길동")

        assert len(results) == 1
        assert results[0].properties["name"] == "홍길동"
        # 정확 일치 시 쿼리 1번만 호출
        assert mock_client.execute_query.await_count == 1

    async def test_case_insensitive_match(self, repo, mock_client):
        """대소문자 무시 매칭 (toLower)"""
        mock_client.execute_query.return_value = [
            {"id": "1", "labels": ["Skill"], "properties": {"name": "Python"}}
        ]

        results = await repo.find_entities_by_name("python")

        assert len(results) == 1
        # Cypher에서 toLower로 비교하므로 서버에서 매칭됨
        call_args = mock_client.execute_query.call_args_list[0]
        assert "toLower" in call_args[0][0]

    async def test_space_removed_fallback(self, repo, mock_client):
        """2단계: 공백 제거 매칭 폴백"""
        # 1단계 실패, 2단계 성공
        mock_client.execute_query.side_effect = [
            [],  # 1단계: 정확 일치 실패
            [{"id": "2", "labels": ["Skill"], "properties": {"name": "React Native"}}],
        ]

        results = await repo.find_entities_by_name("ReactNative")

        assert len(results) == 1
        assert mock_client.execute_query.await_count == 2
        # 2번째 쿼리에 replace(..., ' ', '') 포함
        second_query = mock_client.execute_query.call_args_list[1][0][0]
        assert "replace" in second_query

    @patch("src.repositories.neo4j_entity_repository.strip_korean_suffix")
    async def test_korean_suffix_fallback(self, mock_strip, repo, mock_client):
        """3단계: 한국어 접미사 제거 폴백"""
        mock_strip.return_value = "챗봇 리뉴얼"

        # 1, 2단계 실패 → 3단계 suffix strip 후 성공
        mock_client.execute_query.side_effect = [
            [],  # 1단계 실패
            [],  # 2단계 실패
            [{"id": "3", "labels": ["Project"], "properties": {"name": "챗봇 리뉴얼"}}],
        ]

        results = await repo.find_entities_by_name("챗봇 리뉴얼 프로젝트")

        assert len(results) == 1
        mock_strip.assert_called_once_with("챗봇 리뉴얼 프로젝트")
        # 3번 호출: exact fail → space fail → suffix exact success
        assert mock_client.execute_query.await_count == 3

    @patch("src.repositories.neo4j_entity_repository.strip_korean_suffix")
    async def test_all_fallbacks_exhausted(self, mock_strip, repo, mock_client):
        """3단계 모두 실패 시 빈 리스트 반환"""
        mock_strip.return_value = "AI 개발"

        mock_client.execute_query.side_effect = [
            [],  # 1단계 실패
            [],  # 2단계 실패
            [],  # 3단계 suffix exact 실패
            [],  # 3단계 suffix space-removed 실패
        ]

        results = await repo.find_entities_by_name("AI 개발팀")

        assert len(results) == 0
        assert mock_client.execute_query.await_count == 4

    @patch("src.repositories.neo4j_entity_repository.strip_korean_suffix")
    async def test_suffix_same_as_original_skips_retry(self, mock_strip, repo, mock_client):
        """접미사 제거 결과가 원본과 같으면 재시도 스킵"""
        mock_strip.return_value = "Python"  # 변경 없음

        mock_client.execute_query.side_effect = [
            [],  # 1단계 실패
            [],  # 2단계 실패
        ]

        results = await repo.find_entities_by_name("Python")

        assert len(results) == 0
        # suffix가 같으므로 3단계 쿼리 호출하지 않음 → 2번만 호출
        assert mock_client.execute_query.await_count == 2


# ── Employee Duplication Name-Based Grouping ─────────────────


class TestEmployeeDuplicationGrouping:
    """Employee 중복 노드 name-based grouping Cypher 패턴 검증"""

    def test_find_skill_candidates_uses_name_grouping(self):
        """_find_skill_candidates Cypher에 e.name 기반 그룹핑이 있는지 검증"""
        import inspect
        from src.services.project_staffing_service import ProjectStaffingService

        source = inspect.getsource(ProjectStaffingService._find_skill_candidates)

        # e.name 기반 그룹핑 존재 확인 (중복 노드 대응)
        assert "e.name AS emp_name" in source, \
            "_find_skill_candidates must group by e.name to handle duplicate Employee nodes"
        assert "WITH e.name" in source or "WITH emp_name" in source or "e.name AS emp_name" in source

    def test_analyze_budget_uses_name_grouping(self):
        """analyze_budget Cypher에도 name 기반 그룹핑 사용"""
        import inspect
        from src.services.project_staffing_service import ProjectStaffingService

        source = inspect.getsource(ProjectStaffingService.analyze_budget)

        assert "e.name AS emp_name" in source, \
            "analyze_budget must group by e.name to handle duplicate Employee nodes"

    def test_cypher_uses_tolower_for_skill_matching(self):
        """스킬 매칭에 toLower 사용 여부 확인"""
        import inspect
        from src.services.project_staffing_service import ProjectStaffingService

        source = inspect.getsource(ProjectStaffingService._find_skill_candidates)

        assert "toLower" in source, \
            "_find_skill_candidates must use toLower for case-insensitive skill matching"
