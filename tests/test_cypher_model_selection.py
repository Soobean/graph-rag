"""
CypherGenerator 모델 선택 테스트

단순 쿼리에 LIGHT 모델 사용, 복잡한 쿼리에 HEAVY 모델 사용 검증
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Settings
from src.graph.nodes.cypher_generator import CypherGeneratorNode, QueryComplexity
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.neo4j_repository import Neo4jRepository


@pytest.fixture
def mock_llm_repository() -> MagicMock:
    """LLM Repository 목"""
    mock = MagicMock(spec=LLMRepository)
    mock.generate_cypher = AsyncMock(
        return_value={"cypher": "MATCH (p:Employee) RETURN p", "parameters": {}}
    )
    return mock


@pytest.fixture
def mock_neo4j_repository() -> MagicMock:
    """Neo4j Repository 목"""
    mock = MagicMock(spec=Neo4jRepository)
    mock.get_schema = AsyncMock(
        return_value={
            "node_labels": ["Employee", "Skill"],
            "relationship_types": ["HAS_SKILL"],
        }
    )
    return mock


@pytest.fixture
def settings_enabled() -> Settings:
    """LIGHT 모델 활성화된 설정"""
    return Settings(cypher_light_model_enabled=True)


@pytest.fixture
def settings_disabled() -> Settings:
    """LIGHT 모델 비활성화된 설정"""
    return Settings(cypher_light_model_enabled=False)


class TestQueryComplexityAnalysis:
    """쿼리 복잡도 분석 테스트"""

    def test_simple_query_personnel_search(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """단순 personnel_search 쿼리는 SIMPLE로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람 찾아줘",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.SIMPLE

    def test_simple_query_certificate_search(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """단순 certificate_search 쿼리는 SIMPLE로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "정보처리기사 자격증 가진 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "certificate_search",
            "entities": {"certificates": ["정보처리기사"]},
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.SIMPLE

    def test_complex_query_multi_hop(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """multi-hop 쿼리는 COMPLEX로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람의 멘토",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
            "query_plan": {
                "is_multi_hop": True,
                "hop_count": 2,
                "hops": [],
            },
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.COMPLEX

    def test_complex_query_complex_intent(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """복잡한 intent (path_analysis)는 COMPLEX로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "홍길동과 김철수 사이의 관계",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "path_analysis",
            "entities": {"Employee": ["홍길동", "김철수"]},
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.COMPLEX

    def test_complex_query_too_many_entities(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """엔티티가 3개 이상이면 COMPLEX로 분류"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python, Java, Go 스킬 가진 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python", "Java", "Go"]},
        }

        complexity = node._analyze_complexity(state)
        assert complexity == QueryComplexity.COMPLEX


class TestCypherGeneratorModelSelection:
    """CypherGenerator 모델 선택 테스트"""

    @pytest.mark.asyncio
    async def test_simple_query_uses_light_model(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """단순 쿼리는 LIGHT 모델 사용 (use_light_model=True)"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
            "schema": {
                "node_labels": ["Employee"],
                "relationship_types": [],
            },
        }

        await node._process(state)

        # generate_cypher가 use_light_model=True로 호출되었는지 검증
        mock_llm_repository.generate_cypher.assert_called_once()
        call_kwargs = mock_llm_repository.generate_cypher.call_args.kwargs
        assert call_kwargs.get("use_light_model") is True

    @pytest.mark.asyncio
    async def test_complex_query_uses_heavy_model(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """복잡한 쿼리는 HEAVY 모델 사용 (use_light_model=False)"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람의 멘토",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "mentoring_network",
            "entities": {"skills": ["Python"]},
            "query_plan": {
                "is_multi_hop": True,
                "hop_count": 2,
            },
            "schema": {
                "node_labels": ["Employee"],
                "relationship_types": [],
            },
        }

        await node._process(state)

        # generate_cypher가 use_light_model=False로 호출되었는지 검증
        mock_llm_repository.generate_cypher.assert_called_once()
        call_kwargs = mock_llm_repository.generate_cypher.call_args.kwargs
        assert call_kwargs.get("use_light_model") is False

    @pytest.mark.asyncio
    async def test_config_disabled_uses_heavy_model(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_disabled: Settings,
    ) -> None:
        """설정 비활성화 시 항상 HEAVY 모델 사용"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_disabled,
        )

        # 단순 쿼리로 설정
        state: GraphRAGState = {
            "question": "Python 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
            "schema": {
                "node_labels": ["Employee"],
                "relationship_types": [],
            },
        }

        await node._process(state)

        # 설정이 비활성화되어 있으므로 use_light_model=False
        mock_llm_repository.generate_cypher.assert_called_once()
        call_kwargs = mock_llm_repository.generate_cypher.call_args.kwargs
        assert call_kwargs.get("use_light_model") is False

    @pytest.mark.asyncio
    async def test_no_settings_uses_heavy_model(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """Settings가 없으면 HEAVY 모델 사용"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=None,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "personnel_search",
            "entities": {"skills": ["Python"]},
            "schema": {
                "node_labels": ["Employee"],
                "relationship_types": [],
            },
        }

        await node._process(state)

        # Settings가 없으므로 use_light_model=False
        mock_llm_repository.generate_cypher.assert_called_once()
        call_kwargs = mock_llm_repository.generate_cypher.call_args.kwargs
        assert call_kwargs.get("use_light_model") is False

    @pytest.mark.asyncio
    async def test_cache_hit_skips_model_selection(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
        settings_enabled: Settings,
    ) -> None:
        """캐시 히트 시 LLM 호출 스킵"""
        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
            settings=settings_enabled,
        )

        state: GraphRAGState = {
            "question": "Python 잘하는 사람",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "skip_generation": True,
            "cypher_query": "MATCH (p:Employee) RETURN p",
        }

        result = await node._process(state)

        # 캐시 히트 시 LLM 호출 없음
        mock_llm_repository.generate_cypher.assert_not_called()
        assert "cached" in result.get("execution_path", [])[0]


class TestParameterCorrection:
    """파라미터 보정 테스트"""

    def _make_node(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> CypherGeneratorNode:
        return CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
        )

    def test_correct_parameters_strips_suffix(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """LLM이 추가한 접미사를 엔티티 값으로 보정"""
        node = self._make_node(mock_llm_repository, mock_neo4j_repository)

        parameters = {"projectName": "챗봇 리뉴얼 프로젝트"}
        entities = {"projects": ["챗봇 리뉴얼"]}

        result = node._correct_parameters(parameters, entities)
        assert result["projectName"] == "챗봇 리뉴얼"

    def test_correct_parameters_no_change_on_exact_match(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """정확히 일치하면 변경하지 않음"""
        node = self._make_node(mock_llm_repository, mock_neo4j_repository)

        parameters = {"skillName": "Python"}
        entities = {"skills": ["Python"]}

        result = node._correct_parameters(parameters, entities)
        assert result["skillName"] == "Python"

    def test_correct_parameters_case_insensitive_exact_match(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """대소문자 무시 정확 매칭"""
        node = self._make_node(mock_llm_repository, mock_neo4j_repository)

        parameters = {"skillName": "python"}
        entities = {"skills": ["Python"]}

        result = node._correct_parameters(parameters, entities)
        assert result["skillName"] == "Python"

    def test_correct_parameters_entity_contains_param(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """엔티티가 파라미터를 포함하는 경우 엔티티 값으로 교체"""
        node = self._make_node(mock_llm_repository, mock_neo4j_repository)

        parameters = {"projectName": "데이터레이크"}
        entities = {"projects": ["데이터레이크 개선"]}

        result = node._correct_parameters(parameters, entities)
        assert result["projectName"] == "데이터레이크 개선"

    def test_correct_parameters_non_string_passthrough(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """문자열이 아닌 값은 그대로 유지"""
        node = self._make_node(mock_llm_repository, mock_neo4j_repository)

        parameters = {"limit": 10, "active": True}
        entities = {"skills": ["Python"]}

        result = node._correct_parameters(parameters, entities)
        assert result["limit"] == 10
        assert result["active"] is True

    def test_correct_parameters_no_match_fallback(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """매칭되는 엔티티가 없으면 원래 값 유지"""
        node = self._make_node(mock_llm_repository, mock_neo4j_repository)

        parameters = {"deptName": "경영지원팀"}
        entities = {"skills": ["Python", "Java"]}

        result = node._correct_parameters(parameters, entities)
        assert result["deptName"] == "경영지원팀"

    def test_correct_parameters_empty_entities(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """엔티티가 비어있으면 원래 파라미터 그대로 반환"""
        node = self._make_node(mock_llm_repository, mock_neo4j_repository)

        parameters = {"projectName": "챗봇 리뉴얼 프로젝트"}
        entities: dict[str, list[str]] = {}

        result = node._correct_parameters(parameters, entities)
        assert result["projectName"] == "챗봇 리뉴얼 프로젝트"

    def test_correct_parameters_selects_longest_contains_match(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """여러 엔티티가 매칭될 때 가장 긴 것을 선택"""
        node = self._make_node(mock_llm_repository, mock_neo4j_repository)

        parameters = {"projectName": "챗봇 리뉴얼 프로젝트 v2"}
        entities = {"projects": ["챗봇", "챗봇 리뉴얼"]}

        result = node._correct_parameters(parameters, entities)
        assert result["projectName"] == "챗봇 리뉴얼"

    @pytest.mark.asyncio
    async def test_process_applies_parameter_correction(
        self,
        mock_llm_repository: MagicMock,
        mock_neo4j_repository: MagicMock,
    ) -> None:
        """_process에서 파라미터 보정이 실제로 적용되는지 검증"""
        # LLM이 접미사가 붙은 파라미터를 반환하도록 설정
        mock_llm_repository.generate_cypher = AsyncMock(
            return_value={
                "cypher": "MATCH (p:Project)<-[r:WORKS_ON]-(e:Employee) WHERE toLower(p.name) = toLower($projectName) RETURN p, r, e",
                "parameters": {"projectName": "챗봇 리뉴얼 프로젝트"},
            }
        )

        node = CypherGeneratorNode(
            mock_llm_repository,
            mock_neo4j_repository,
        )

        state: GraphRAGState = {
            "question": "챗봇 리뉴얼 프로젝트에 필요한 인력 추천해줘",
            "session_id": "test",
            "messages": [],
            "execution_path": [],
            "intent": "project_matching",
            "entities": {"projects": ["챗봇 리뉴얼"]},
            "schema": {
                "node_labels": ["Employee", "Project"],
                "relationship_types": ["WORKS_ON"],
            },
        }

        result = await node._process(state)

        # 파라미터가 엔티티 값으로 보정되었는지 확인
        assert result["cypher_parameters"]["projectName"] == "챗봇 리뉴얼"
