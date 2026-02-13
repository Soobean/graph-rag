"""
CommunitySummarizerNode 단위 테스트

Global RAG — 커뮤니티 기반 거시적 분석 노드 테스트

실행 방법:
    pytest tests/test_community_summarizer.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.graph.nodes.community_summarizer import CommunitySummarizerNode
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository


@pytest.fixture
def mock_neo4j():
    neo4j = MagicMock(spec=Neo4jRepository)
    neo4j.execute_cypher = AsyncMock(return_value=[])
    return neo4j


@pytest.fixture
def mock_llm():
    llm = MagicMock(spec=LLMRepository)
    llm.generate = AsyncMock(return_value="조직 요약 결과입니다.")
    return llm


@pytest.fixture
def node(mock_neo4j, mock_llm):
    return CommunitySummarizerNode(
        neo4j_repository=mock_neo4j,
        llm_repository=mock_llm,
    )


@pytest.fixture
def sample_department_stats():
    return [
        {
            "dept": "개발팀",
            "headcount": 10,
            "unique_skills": 15,
            "top_skills": ["Python", "Java", "React"],
        },
        {
            "dept": "기획팀",
            "headcount": 5,
            "unique_skills": 8,
            "top_skills": ["Figma", "SQL"],
        },
    ]


@pytest.fixture
def sample_project_stats():
    return [
        {"status": "진행중", "cnt": 3, "sample_projects": ["프로젝트A", "프로젝트B"]},
        {"status": "완료", "cnt": 5, "sample_projects": ["프로젝트C"]},
    ]


@pytest.fixture
def sample_skill_distribution():
    return [
        {"skill": "Python", "holders": 8},
        {"skill": "Java", "holders": 6},
        {"skill": "React", "holders": 5},
        {"skill": "Figma", "holders": 3},
        {"skill": "SQL", "holders": 4},
    ]


class TestCommunitySummarizerBasic:
    """기본 동작 테스트"""

    async def test_community_summarizer_basic(
        self, node, mock_neo4j, mock_llm,
        sample_department_stats, sample_project_stats, sample_skill_distribution,
    ):
        """정상 데이터 → LLM 요약 호출 → response 반환"""
        call_count = 0

        async def mock_execute_cypher(query, params=None):
            nonlocal call_count
            call_count += 1
            # 1: cache check, 2: department, 3: project, 4: skill, 5: cache save
            if call_count == 1:
                return []  # no cache
            elif call_count == 2:
                return sample_department_stats
            elif call_count == 3:
                return sample_project_stats
            elif call_count == 4:
                return sample_skill_distribution
            return []

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute_cypher)

        state = {
            "question": "조직 전체 기술 분포는?",
            "intent": "global_analysis",
            "entities": {},
        }

        result = await node(state)

        assert result["response"] == "조직 요약 결과입니다."
        assert "community_summarizer" in result["execution_path"]
        assert len(result["graph_results"]) > 0
        mock_llm.generate.assert_called_once()

    async def test_community_summarizer_empty_data(self, node, mock_neo4j, mock_llm):
        """빈 DB → 적절한 '데이터 없음' 응답"""
        mock_neo4j.execute_cypher = AsyncMock(return_value=[])

        state = {
            "question": "전체 현황 요약해줘",
            "intent": "global_analysis",
            "entities": {},
        }

        result = await node(state)

        assert "데이터가 아직 등록되지 않았" in result["response"]
        assert "community_summarizer_empty" in result["execution_path"]
        mock_llm.generate.assert_not_called()


class TestCommunitySummarizerCache:
    """캐시 관련 테스트"""

    async def test_cache_hit(self, node, mock_neo4j, mock_llm):
        """캐시에 유사 질문 존재 → LLM 미호출, 캐시 반환"""
        cached_data = [
            {
                "question": "조직 전체 기술 분포는?",
                "summary": "캐시된 요약입니다.",
                "source_data": "[]",
            }
        ]
        mock_neo4j.execute_cypher = AsyncMock(return_value=cached_data)

        state = {
            "question": "조직 전체 기술 분포는?",
            "intent": "global_analysis",
            "entities": {},
        }

        result = await node(state)

        assert result["response"] == "캐시된 요약입니다."
        assert "community_summarizer_cached" in result["execution_path"]
        mock_llm.generate.assert_not_called()

    async def test_cache_miss(
        self, node, mock_neo4j, mock_llm,
        sample_department_stats, sample_project_stats, sample_skill_distribution,
    ):
        """캐시 없음 → 정상 처리 → 캐시 저장"""
        call_count = 0

        async def mock_execute_cypher(query, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # cache miss
            elif call_count == 2:
                return sample_department_stats
            elif call_count == 3:
                return sample_project_stats
            elif call_count == 4:
                return sample_skill_distribution
            return []  # cache save

        mock_neo4j.execute_cypher = AsyncMock(side_effect=mock_execute_cypher)

        state = {
            "question": "부서별 현황 요약",
            "intent": "global_analysis",
            "entities": {},
        }

        result = await node(state)

        assert result["response"] == "조직 요약 결과입니다."
        # cache save call should have happened (call_count == 5)
        assert call_count == 5


class TestKeywordSimilarity:
    """키워드 유사도 테스트"""

    def test_is_similar_question_same_meaning(self):
        """같은 의미 다른 표현 → True"""
        assert CommunitySummarizerNode._is_similar_question(
            "조직 전체 기술 분포는?",
            "조직 전체 기술 분포 알려줘",
        )

    def test_is_similar_question_different(self):
        """완전히 다른 질문 → False"""
        assert not CommunitySummarizerNode._is_similar_question(
            "조직 전체 기술 분포는?",
            "홍길동의 스킬은 뭐야?",
        )

    def test_is_similar_question_empty(self):
        """빈 질문 → False"""
        assert not CommunitySummarizerNode._is_similar_question("", "")

    def test_is_similar_question_stopword_only(self):
        """불용어만 있는 질문 → False"""
        assert not CommunitySummarizerNode._is_similar_question("은 는 이 가", "을 를 의")


class TestBuildCommunityGraph:
    """합성 그래프 데이터 생성 테스트"""

    def test_build_community_graph(
        self, sample_department_stats, sample_skill_distribution
    ):
        """Department/Skill 노드 + DEPT_HAS_SKILL 엣지 존재 확인"""
        result = CommunitySummarizerNode._build_community_graph(
            sample_department_stats, sample_skill_distribution
        )

        # 노드 확인
        nodes = [r for r in result if "node" in r]
        edges = [r for r in result if "rel" in r]

        dept_nodes = [n for n in nodes if "Department" in n["node"]["labels"]]
        skill_nodes = [n for n in nodes if "Skill" in n["node"]["labels"]]

        assert len(dept_nodes) == 2  # 개발팀, 기획팀
        assert len(skill_nodes) == 5  # Python, Java, React, Figma, SQL
        assert len(edges) > 0  # Department → Skill 엣지 존재

        # 엣지의 startNodeId가 dept_ 접두어, endNodeId가 skill_ 접두어인지 확인
        for edge in edges:
            assert edge["rel"]["startNodeId"].startswith("dept_")
            assert edge["rel"]["endNodeId"].startswith("skill_")
            assert edge["rel"]["type"] == "DEPT_HAS_SKILL"

    def test_build_community_graph_empty(self):
        """빈 데이터 → 빈 graph_results"""
        result = CommunitySummarizerNode._build_community_graph([], [])
        assert result == []

    def test_build_community_graph_node_properties(
        self, sample_department_stats, sample_skill_distribution
    ):
        """노드 properties에 필요한 필드 포함 확인"""
        result = CommunitySummarizerNode._build_community_graph(
            sample_department_stats, sample_skill_distribution
        )

        dept_node = next(r for r in result if "node" in r and "Department" in r["node"]["labels"])
        assert "name" in dept_node["node"]["properties"]
        assert "headcount" in dept_node["node"]["properties"]

        skill_node = next(r for r in result if "node" in r and "Skill" in r["node"]["labels"])
        assert "name" in skill_node["node"]["properties"]
        assert "holders" in skill_node["node"]["properties"]


class TestFormatCommunityContext:
    """컨텍스트 포매팅 테스트"""

    def test_format_with_all_data(
        self, sample_department_stats, sample_project_stats, sample_skill_distribution
    ):
        context = CommunitySummarizerNode._format_community_context(
            sample_department_stats, sample_project_stats, sample_skill_distribution
        )

        assert "부서별 현황" in context
        assert "개발팀" in context
        assert "프로젝트 현황" in context
        assert "스킬 분포" in context
        assert "Python" in context

    def test_format_with_empty_data(self):
        context = CommunitySummarizerNode._format_community_context([], [], [])
        assert context == ""
