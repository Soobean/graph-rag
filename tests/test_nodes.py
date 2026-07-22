import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.llm import LLMTaskService
from src.graph.nodes.cypher_generator import CypherGeneratorNode
from src.graph.nodes.entity_resolver import EntityResolverNode
from src.graph.nodes.graph_executor import GraphExecutorNode
from src.graph.nodes.response_generator import ResponseGeneratorNode
from src.graph.state import GraphRAGState
from src.repositories.neo4j_repository import Neo4jRepository


class TestEntityResolverNode:
    """EntityResolverNode 테스트"""

    @pytest.fixture
    def mock_neo4j(self):
        """Mock Neo4j Repository"""
        neo4j = MagicMock(spec=Neo4jRepository)
        neo4j.find_entities_by_name = AsyncMock()
        return neo4j

    @pytest.fixture
    def node(self, mock_neo4j):
        """EntityResolverNode 인스턴스"""
        return EntityResolverNode(mock_neo4j)

    @pytest.mark.asyncio
    async def test_resolve_success(self, node, mock_neo4j):
        """엔티티 리졸브 성공"""
        mock_match = MagicMock()
        mock_match.id = 123
        mock_match.labels = ["Employee"]
        mock_match.properties = {"name": "홍길동", "dept": "IT"}
        mock_neo4j.find_entities_by_name.return_value = [mock_match]

        state: GraphRAGState = {
            "entities": {"Employee": ["홍길동"]},
            "execution_path": [],
        }

        result = await node(state)

        assert "resolved_entities" in result
        assert len(result["resolved_entities"]) == 1

        resolved = result["resolved_entities"][0]
        assert resolved["id"] == 123
        assert resolved["labels"] == ["Employee"]
        assert resolved["name"] == "홍길동"
        assert resolved["original_value"] == "홍길동"
        assert resolved["match_score"] == 1.0
        assert resolved["properties"] == {"name": "홍길동", "dept": "IT"}

        assert "entity_resolver" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, node, mock_neo4j):
        """엔티티 못 찾음"""
        mock_neo4j.find_entities_by_name.return_value = []

        state: GraphRAGState = {
            "entities": {"Employee": ["없는사람"]},
            "execution_path": [],
        }

        result = await node(state)

        # 찾지 못한 경우 리스트에 포함되지 않음
        assert "resolved_entities" in result
        assert len(result["resolved_entities"]) == 0
        assert "entity_resolver" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_resolve_skipped(self, node, mock_neo4j):
        """엔티티 없으면 스킵"""
        state = GraphRAGState(question="질문", entities={})
        result = await node(state)

        assert result["resolved_entities"] == []
        assert "entity_resolver_skipped" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_resolve_error(self, node, mock_neo4j):
        """리졸브 에러"""
        mock_neo4j.find_entities_by_name.side_effect = Exception("DB Error")

        state: GraphRAGState = {
            "entities": {"Employee": ["에러유발"]},
            "execution_path": [],
        }

        result = await node(state)

        assert "resolved_entities" in result
        assert len(result["resolved_entities"]) == 0
        assert "entity_resolver" in result["execution_path"]


class TestCypherGeneratorNode:
    """CypherGeneratorNode 테스트"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock(spec=LLMTaskService)
        llm.generate_cypher = AsyncMock()
        return llm

    @pytest.fixture
    def mock_neo4j(self):
        neo4j = MagicMock()
        neo4j.get_schema = AsyncMock(return_value={"node_labels": ["Employee"]})
        return neo4j

    @pytest.fixture
    def node(self, mock_llm, mock_neo4j):
        return CypherGeneratorNode(mock_llm, mock_neo4j)

    @pytest.fixture
    def base_state(self) -> GraphRAGState:
        return GraphRAGState(
            question="홍길동 찾기",
            entities={"Employee": ["홍길동"]},
        )

    @pytest.mark.asyncio
    async def test_generate_success(self, node, mock_llm, base_state):
        """Cypher 생성 성공"""
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }

        result = await node(base_state)

        assert result["cypher_query"] == "MATCH (n) RETURN n"
        assert "cypher_generator" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_generate_passes_intent(self, node, mock_llm, mock_neo4j):
        """intent가 generate_cypher에 전달됨"""
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (e)-[r]->(s) RETURN e, r, s",
            "parameters": {},
        }

        state = GraphRAGState(
            question="홍길동의 스킬은?",
            intent="personnel_search",
            entities={"Employee": ["홍길동"]},
        )

        await node(state)

        call_kwargs = mock_llm.generate_cypher.call_args.kwargs
        assert call_kwargs["intent"] == "personnel_search"

    @pytest.mark.asyncio
    async def test_generate_intent_defaults_to_unknown(
        self, node, mock_llm, base_state
    ):
        """intent 미설정 시 'unknown' 전달"""
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }

        await node(base_state)

        call_kwargs = mock_llm.generate_cypher.call_args.kwargs
        assert call_kwargs["intent"] == "unknown"

    @pytest.mark.asyncio
    async def test_generate_error(self, node, mock_llm, base_state):
        """Cypher 생성 실패"""
        mock_llm.generate_cypher.side_effect = Exception("LLM Fail")

        result = await node(base_state)

        assert result["cypher_query"] == ""
        assert "cypher_generator_error" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_content_filter_uses_friendly_message(
        self, node, mock_llm, base_state
    ):
        """Content Filter는 raw Azure 메시지 노출 금지, 친화적 메시지만 전달"""
        from src.domain.exceptions import LLMContentFilterError

        mock_llm.generate_cypher.side_effect = LLMContentFilterError(
            categories={"self_harm": "medium"}, param="prompt"
        )

        result = await node(base_state)

        # raw Azure 정보가 사용자 메시지에 누출되지 않음
        assert "ResponsibleAI" not in result.get("error", "")
        assert "self_harm" not in result.get("error", "")
        # 친화적 한국어 메시지가 들어감
        assert "콘텐츠 정책" in result.get("error", "")
        assert "cypher_generator_content_filter" in result["execution_path"]

    def test_fix_in_clause_converts_name_to_tolower(self, node):
        """`WHERE x.name IN $list` → ANY(...toLower(x.name)=toLower(_item))"""
        cypher = "MATCH (s:Skill) WHERE s.name IN $skillNames RETURN s"
        fixed = node._fix_in_clause_to_tolower(cypher)

        assert "ANY(_item IN $skillNames" in fixed
        assert "toLower(s.name)" in fixed
        assert "toLower(_item)" in fixed
        # 원본의 단순 IN 패턴은 사라짐
        assert "s.name IN $skillNames" not in fixed

    def test_fix_in_clause_preserves_already_tolower(self, node):
        """이미 toLower(x) IN $list 형태면 변환하지 않음"""
        cypher = "WHERE toLower(s.name) IN $names"
        assert node._fix_in_clause_to_tolower(cypher) == cypher

    def test_fix_in_clause_skips_non_name_properties(self, node):
        """status/id/type 같은 속성은 변환 대상 아님 (정확한 매칭 의도)"""
        for prop in ("status", "id", "type", "category"):
            cypher = f"WHERE s.{prop} IN $list"
            assert node._fix_in_clause_to_tolower(cypher) == cypher

    # ------------------------------------------------------------------
    # Characterization 테스트: 도메인 모델 이전(2단계) 전 현재 동작 고정
    # ------------------------------------------------------------------

    # --- _fix_not_in_syntax ---

    def test_fix_not_in_converts_sql_style(self, node):
        """SQL식 `x.name NOT IN $list` → Cypher `NOT x.name IN $list`"""
        cypher = "MATCH (s:Skill) WHERE s.name NOT IN $excluded RETURN s"
        fixed = node._fix_not_in_syntax(cypher)
        assert "WHERE NOT s.name IN $excluded" in fixed

    def test_fix_not_in_converts_after_and(self, node):
        """AND 뒤 NOT IN도 교정 (리터럴 리스트 포함)"""
        cypher = "WHERE e.active = true AND s.status NOT IN ['done', 'hold']"
        fixed = node._fix_not_in_syntax(cypher)
        assert "AND NOT s.status IN ['done', 'hold']" in fixed

    def test_fix_not_in_converts_function_call_lhs(self, node):
        """함수 호출 LHS: toLower(s.name) NOT IN → NOT toLower(s.name) IN"""
        cypher = "WHERE toLower(s.name) NOT IN $names"
        fixed = node._fix_not_in_syntax(cypher)
        assert "WHERE NOT toLower(s.name) IN $names" in fixed

    def test_fix_not_in_case_insensitive_keywords(self, node):
        """소문자 where/not/in 키워드도 교정 (IGNORECASE)"""
        cypher = "match (s) where s.name not in $list return s"
        fixed = node._fix_not_in_syntax(cypher)
        assert re.search(r"where\s+NOT\s+s\.name\s+IN", fixed, re.IGNORECASE)

    def test_fix_not_in_noop_when_already_canonical(self, node):
        """이미 `NOT x IN` 정식형이면 무변환"""
        cypher = "WHERE NOT s.name IN $list"
        assert node._fix_not_in_syntax(cypher) == cypher

    def test_fix_not_in_noop_without_not_in(self, node):
        """NOT IN이 없으면 무변환"""
        cypher = "MATCH (s) WHERE s.name IN $list RETURN s"
        assert node._fix_not_in_syntax(cypher) == cypher

    # --- _fix_aggregation_type_a_return ---

    def test_fix_aggregation_rewrites_type_a_return(self, node):
        """WITH+집계 → re-MATCH → alias 없는 RETURN 안티패턴을 TYPE B로 재작성"""
        cypher = (
            "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill)\n"
            "WITH e, COUNT(s) AS skillCount\n"
            "MATCH (e)-[:WORKS_ON]->(p:Project)\n"
            "RETURN e, p"
        )
        fixed = node._fix_aggregation_type_a_return(cypher)
        assert "RETURN e.name AS name, skillCount" in fixed
        assert "ORDER BY skillCount DESC" in fixed
        # re-MATCH 라인은 제거됨
        assert "WORKS_ON" not in fixed

    def test_fix_aggregation_noop_without_agg_with(self, node):
        """집계 없는 WITH만 있으면 무변환"""
        cypher = "MATCH (e)\nWITH e, e.name AS n\nMATCH (e)-[r]->(x)\nRETURN e, x"
        assert node._fix_aggregation_type_a_return(cypher) == cypher

    def test_fix_aggregation_noop_without_rematch(self, node):
        """집계 후 re-MATCH가 없으면 무변환"""
        cypher = "MATCH (e)-[:HAS_SKILL]->(s)\nWITH e, COUNT(s) AS c\nRETURN e, c"
        assert node._fix_aggregation_type_a_return(cypher) == cypher

    def test_fix_aggregation_noop_when_return_has_alias(self, node):
        """RETURN에 AS(alias)가 있으면 TYPE B로 판단, 무변환"""
        cypher = (
            "MATCH (e)-[:HAS_SKILL]->(s)\n"
            "WITH e, COUNT(s) AS c\n"
            "MATCH (e)-[:WORKS_ON]->(p)\n"
            "RETURN e.name AS name, c"
        )
        assert node._fix_aggregation_type_a_return(cypher) == cypher

    def test_fix_aggregation_noop_when_with_var_unmatched(self, node):
        """WITH 선두가 `var,` 형태가 아니면 무변환"""
        cypher = (
            "MATCH (e)-[:HAS_SKILL]->(s)\n"
            "WITH COUNT(s) AS c\n"
            "MATCH (x)\n"
            "RETURN x"
        )
        assert node._fix_aggregation_type_a_return(cypher) == cypher

    def test_fix_aggregation_noop_without_alias_in_with(self, node):
        """WITH에 AS alias가 없으면 무변환"""
        cypher = (
            "MATCH (e)-[:HAS_SKILL]->(s)\n"
            "WITH e, COUNT(s)\n"
            "MATCH (x)\n"
            "RETURN x"
        )
        assert node._fix_aggregation_type_a_return(cypher) == cypher

    # --- _correct_parameters / _correct_single_value ---

    def test_correct_params_exact_match_restores_casing(self, node):
        """대소문자 무시 정확 일치 시 엔티티 케이싱으로 복원"""
        result = node._correct_parameters(
            {"skillName": "python"}, {"Skill": ["Python"]}
        )
        assert result["skillName"] == "Python"

    def test_correct_params_param_contains_entity_longest(self, node):
        """param ⊃ entity: 가장 긴 엔티티로 교체 (접미사 제거 효과)"""
        result = node._correct_parameters(
            {"projectName": "챗봇 리뉴얼 프로젝트"},
            {"Project": ["챗봇", "챗봇 리뉴얼"]},
        )
        assert result["projectName"] == "챗봇 리뉴얼"

    def test_correct_params_entity_contains_param_shortest(self, node):
        """entity ⊃ param: 가장 짧은 엔티티로 교체"""
        result = node._correct_parameters(
            {"projectName": "데이터레이크"},
            {"Project": ["데이터레이크 개선 프로젝트", "데이터레이크 개선"]},
        )
        assert result["projectName"] == "데이터레이크 개선"

    def test_correct_params_no_match_keeps_original(self, node):
        """매칭 실패 시 원본 유지"""
        result = node._correct_parameters(
            {"skillName": "Rust"}, {"Skill": ["Python"]}
        )
        assert result["skillName"] == "Rust"

    def test_correct_params_list_elements_corrected(self, node):
        """리스트 파라미터의 문자열 요소도 개별 보정"""
        result = node._correct_parameters(
            {"names": ["python", "자바스크립트 스킬"]},
            {"Skill": ["Python", "자바스크립트"]},
        )
        assert result["names"] == ["Python", "자바스크립트"]

    def test_correct_params_empty_entities_early_return(self, node):
        """엔티티가 비어 있으면 파라미터 그대로 반환"""
        params = {"skillName": "python"}
        assert node._correct_parameters(params, {}) is params

    def test_correct_params_non_string_preserved(self, node):
        """숫자/불리언 등 비문자열 파라미터는 보존"""
        result = node._correct_parameters(
            {"limit": 10, "active": True, "rates": [1, 2]},
            {"Skill": ["Python"]},
        )
        assert result["limit"] == 10
        assert result["active"] is True
        assert result["rates"] == [1, 2]

    # --- _coerce_tolower_params ---

    def test_coerce_direct_tolower_int_to_str(self, node):
        """toLower($p) 직접 사용 시 int → str 강제"""
        result = node._coerce_tolower_params(
            "WHERE toLower(s.name) = toLower($val)", {"val": 123}
        )
        assert result["val"] == "123"

    def test_coerce_indirect_any_pattern_list(self, node):
        """ANY(v IN $p ... toLower(v)) 간접 패턴 시 리스트 요소 int → str"""
        cypher = "WHERE ANY(_item IN $names WHERE toLower(s.name) = toLower(_item))"
        result = node._coerce_tolower_params(cypher, {"names": [1, "Python", 2]})
        assert result["names"] == ["1", "Python", "2"]

    def test_coerce_preserves_unrelated_params(self, node):
        """toLower에 쓰이지 않는 파라미터는 타입 보존"""
        cypher = "WHERE toLower($name) = 'x' AND e.rate > $rate"
        result = node._coerce_tolower_params(cypher, {"name": "A", "rate": 50000})
        assert result["rate"] == 50000

    def test_coerce_noop_without_tolower(self, node):
        """toLower가 없으면 파라미터 그대로 반환"""
        params = {"val": 123}
        assert node._coerce_tolower_params("MATCH (n) RETURN n", params) is params

    def test_coerce_float_and_mixed_list(self, node):
        """float 및 혼합 타입 리스트도 문자열로 강제"""
        result = node._coerce_tolower_params(
            "WHERE toLower($a) = 'x' AND ANY(v IN $b WHERE toLower(v) = 'y')",
            {"a": 1.5, "b": [2.5, True, "s"]},
        )
        assert result["a"] == "1.5"
        # bool은 int의 서브클래스 → 현재 구현은 str로 강제함 (동작 고정)
        assert result["b"] == ["2.5", "True", "s"]

    # --- 현재 버그 고정 (negation IN 절 — 커밋 4에서 기대 동작으로 갱신 예정) ---

    def test_bug_negation_in_clause_not_converted(self, node):
        """[버그 고정] `WHERE NOT x.name IN $list`는 toLower 변환에서 누락됨.

        2단계 커밋 4(2-pass 정규화)에서 NONE(...) 변환으로 갱신될 예정.
        """
        cypher = "MATCH (s) WHERE NOT s.name IN $excluded RETURN s"
        assert node._fix_in_clause_to_tolower(cypher) == cypher

    def test_bug_not_in_chain_stops_at_canonical_form(self, node):
        """[버그 고정] `x.name NOT IN $l` 연쇄: 문법 교정까지만 되고 toLower 누락.

        _fix_not_in_syntax → `NOT x.name IN $l` → _fix_in_clause_to_tolower가
        건너뜀. 커밋 4에서 NONE(...) 변환으로 갱신될 예정.
        """
        cypher = "WHERE s.name NOT IN $excluded"
        step1 = node._fix_not_in_syntax(cypher)
        assert step1 == "WHERE NOT s.name IN $excluded"
        step2 = node._fix_in_clause_to_tolower(step1)
        assert step2 == step1  # 변환 안 됨 (버그)


class TestGraphExecutorNode:
    """GraphExecutorNode 테스트"""

    @pytest.fixture
    def mock_neo4j(self):
        neo4j = MagicMock()
        neo4j.execute_cypher = AsyncMock()
        return neo4j

    @pytest.fixture
    def node(self, mock_neo4j):
        return GraphExecutorNode(mock_neo4j)

    @pytest.mark.asyncio
    async def test_execute_success(self, node, mock_neo4j):
        state = GraphRAGState(
            cypher_query="MATCH (n) RETURN n",
            cypher_parameters={},
        )
        mock_neo4j.execute_cypher.return_value = [{"n": "data"}]

        result = await node(state)

        assert len(result["graph_results"]) == 1
        assert result["result_count"] == 1
        assert "graph_executor" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_execute_no_query(self, node):
        state = GraphRAGState(cypher_query="")
        result = await node(state)
        assert result["result_count"] == 0
        assert "graph_executor_skipped" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_execute_error(self, node, mock_neo4j):
        state = GraphRAGState(cypher_query="BAD QUERY")
        mock_neo4j.execute_cypher.side_effect = Exception("DB Fail")

        result = await node(state)
        assert "error" in result
        assert "graph_executor_error" in result["execution_path"]


class TestResponseGeneratorNode:
    """ResponseGeneratorNode 테스트"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock(spec=LLMTaskService)
        llm.generate_response = AsyncMock()
        return llm

    @pytest.fixture
    def node(self, mock_llm):
        return ResponseGeneratorNode(mock_llm)

    @pytest.mark.asyncio
    async def test_generate_response_success(self, node, mock_llm):
        state = GraphRAGState(
            question="q",
            graph_results=[{"name": "test"}],
        )
        mock_llm.generate_response.return_value = "This is a response."

        result = await node(state)
        assert result["response"] == "This is a response."
        assert "response_generator" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_generate_response_empty_results(self, node):
        state = GraphRAGState(question="q", graph_results=[])
        result = await node(state)
        assert "죄송합니다" in result["response"]
        assert "response_generator_empty" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_generate_response_entity_found_but_no_relation(self, node):
        """엔티티는 찾았지만 관계가 없는 경우 - 구체적 피드백"""
        state = GraphRAGState(
            question="박수빈이 참여한 프로젝트는?",
            graph_results=[],  # 빈 결과
            intent="project_matching",
            resolved_entities=[
                {
                    "id": "123",
                    "labels": ["Employee"],
                    "name": "박수빈",
                    "properties": {"name": "박수빈"},
                    "match_score": 1.0,
                    "original_value": "박수빈",
                }
            ],
        )
        result = await node(state)

        # 구체적 피드백이 포함되어야 함
        assert "박수빈" in result["response"]
        assert "등록되어 있지만" in result["response"]
        assert "프로젝트" in result["response"]  # intent별 관계 설명
        assert "response_generator_empty" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_generate_response_multiple_entities_found_no_relation(self, node):
        """여러 엔티티 찾았지만 관계 없는 경우"""
        state = GraphRAGState(
            question="김철수, 이영희의 멘토링 관계는?",
            graph_results=[],
            intent="mentoring_network",
            resolved_entities=[
                {"id": "101", "name": "김철수", "labels": ["Employee"]},
                {"id": "102", "name": "이영희", "labels": ["Employee"]},
            ],
        )
        result = await node(state)

        assert "김철수" in result["response"]
        assert "이영희" in result["response"]
        assert "멘토링" in result["response"]  # mentoring_network intent

    @pytest.mark.asyncio
    async def test_generate_response_entity_id_none_treated_as_not_found(self, node):
        """ID가 None인 엔티티는 '못 찾은 것'으로 간주"""
        state = GraphRAGState(
            question="없는사람의 프로젝트는?",
            graph_results=[],
            intent="project_matching",
            resolved_entities=[
                {
                    "id": None,  # 매칭 실패
                    "labels": ["Employee"],
                    "original_value": "없는사람",
                    "match_score": 0.0,
                }
            ],
        )
        result = await node(state)

        # ID가 None이면 "엔티티를 못 찾은 경우"로 처리
        assert "찾을 수 없습니다" in result["response"]
        assert "등록되어 있지만" not in result["response"]

    @pytest.mark.asyncio
    async def test_generate_response_mixed_resolved_and_unresolved(self, node):
        """일부는 찾고 일부는 못 찾은 경우 - 찾은 것만 피드백"""
        state = GraphRAGState(
            question="박수빈과 없는사람의 멘토링 관계는?",
            graph_results=[],
            intent="mentoring_network",
            resolved_entities=[
                {"id": "123", "labels": ["Employee"], "name": "박수빈"},
                {"id": None, "labels": ["Employee"], "original_value": "없는사람"},
            ],
        )
        result = await node(state)

        # 찾은 엔티티(박수빈)에 대해서만 피드백
        assert "박수빈" in result["response"]
        assert "등록되어 있지만" in result["response"]
        # 못 찾은 엔티티(없는사람)는 언급하지 않음
        assert "없는사람" not in result["response"]

    @pytest.mark.asyncio
    async def test_generate_response_error_in_state(self, node):
        state = GraphRAGState(question="q", error="Previous failure")
        result = await node(state)
        assert "오류가 발생" in result["response"]
        assert "response_generator_error_handler" in result["execution_path"]


class TestBaseNodeTimeout:
    """BaseNode 타임아웃 테스트"""

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        """노드 타임아웃 시 에러 상태 반환"""
        from src.graph.nodes.base import BaseNode

        class SlowNode(BaseNode[dict]):
            @property
            def name(self) -> str:
                return "slow_node"

            @property
            def timeout_seconds(self) -> float:
                return 0.1  # 100ms

            @property
            def input_keys(self) -> list[str]:
                return []

            async def _process(self, state):
                import asyncio

                await asyncio.sleep(5)  # 5초 — 타임아웃 유발
                return {"execution_path": ["slow_node"]}

        node = SlowNode()
        state = GraphRAGState(question="test")
        result = await node(state)

        assert "error" in result
        assert "slow_node_timeout" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_no_timeout_on_fast_node(self):
        """빠른 노드는 정상 반환"""
        from src.graph.nodes.base import BaseNode

        class FastNode(BaseNode[dict]):
            @property
            def name(self) -> str:
                return "fast_node"

            @property
            def timeout_seconds(self) -> float:
                return 5.0

            @property
            def input_keys(self) -> list[str]:
                return []

            async def _process(self, state):
                return {"execution_path": ["fast_node"]}

        node = FastNode()
        state = GraphRAGState(question="test")
        result = await node(state)

        assert result["execution_path"] == ["fast_node"]
        assert "error" not in result

    def test_default_timeout_values(self):
        """노드별 기본 타임아웃 확인"""
        from src.graph.nodes.base import CPU_TIMEOUT, DB_TIMEOUT, DEFAULT_TIMEOUT

        assert DEFAULT_TIMEOUT == 30
        assert DB_TIMEOUT == 15
        assert CPU_TIMEOUT == 10


class TestGraphRAGState:
    """GraphRAGState 테스트"""

    def test_minimal_state(self):
        """최소 상태 생성"""
        state = GraphRAGState(question="테스트 질문")
        assert state["question"] == "테스트 질문"

    def test_full_state(self):
        """전체 상태 생성"""
        state = GraphRAGState(
            question="홍길동 찾아줘",
            session_id="session-123",
            intent="personnel_search",
            intent_confidence=0.95,
            entities={"Employee": ["홍길동"]},
            resolved_entities=[
                {
                    "id": 1,
                    "name": "홍길동",
                    "labels": ["Employee"],
                    "properties": {},
                    "match_score": 1,
                    "original_value": "홍길동",
                }
            ],
            schema={"node_labels": ["Employee"]},
            cypher_query="MATCH (p:Employee) RETURN p",
            cypher_parameters={},
            graph_results=[{"name": "홍길동"}],
            result_count=1,
            response="홍길동을 찾았습니다.",
            error=None,
            execution_path=["intent_classifier", "entity_extractor"],
        )

        assert state["intent"] == "personnel_search"
        assert len(state["execution_path"]) == 2

    def test_execution_path_reducer(self):
        """execution_path Reducer 동작 확인"""
        # execution_path는 Annotated[list[str], operator.add] 타입이므로
        # LangGraph에서 자동으로 리스트 병합됨
        state = GraphRAGState(execution_path=["step1"])
        # 새로운 상태 업데이트 시 리스트가 합쳐짐 (LangGraph 동작)
        assert state["execution_path"] == ["step1"]
