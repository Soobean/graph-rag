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

    @pytest.mark.asyncio
    async def test_retry_passes_error_feedback(self, node, mock_llm, mock_neo4j):
        """재시도 상태(cypher_error 존재)면 피드백을 generate_cypher에 전달 +
        재생성 성공 시 stale error/힌트 클리어"""
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }

        state = GraphRAGState(
            question="질문",
            entities={"Employee": ["홍길동"]},
            cypher_retry_count=1,
            cypher_error="SyntaxError: Invalid input 'OVER'",
            failed_cypher="RETURN max(x) OVER ()",
            error="Query execution failed: ...",  # 이전 실행이 남긴 stale error
        )

        result = await node(state)

        # 피드백에 에러와 실패 쿼리가 포함되어 전달됨
        feedback = mock_llm.generate_cypher.call_args.kwargs["error_feedback"]
        assert "SyntaxError: Invalid input 'OVER'" in feedback
        assert "RETURN max(x) OVER ()" in feedback
        # 재생성 성공 → stale error/힌트 클리어 (route_after_cypher 오염 방지)
        assert result["error"] is None
        assert result["cypher_error"] is None
        assert result["failed_cypher"] is None

    @pytest.mark.asyncio
    async def test_first_attempt_empty_feedback(self, node, mock_llm, base_state):
        """최초 생성 시 error_feedback은 빈 문자열"""
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (n) RETURN n",
            "parameters": {},
        }

        await node(base_state)

        assert mock_llm.generate_cypher.call_args.kwargs["error_feedback"] == ""

    @pytest.mark.asyncio
    async def test_domain_corrections_applied(self, node, mock_llm, base_state):
        """노드 → 도메인 교정(apply_corrections) 배선 스모크.

        교정 규칙 자체의 상세 검증은 tests/domain/test_cypher_corrections.py 담당.
        """
        mock_llm.generate_cypher.return_value = {
            "cypher": "MATCH (s:Skill) WHERE s.name IN $skillNames RETURN s",
            "parameters": {"skillNames": ["python"]},
        }

        result = await node(base_state)

        # IN 절이 도메인 규칙에 의해 case-insensitive 형태로 교정됨
        assert "ANY(_item IN $skillNames" in result["cypher_query"]
        assert "toLower(s.name)" in result["cypher_query"]


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

    # --- Self-Correction: SyntaxError 판별 ---

    @pytest.mark.asyncio
    async def test_syntax_error_sets_retry_hints(self, node, mock_neo4j):
        """SyntaxError 실패 시 재생성 루프 힌트(cypher_error 등) 세팅"""
        from src.domain.exceptions import QueryExecutionError

        state = GraphRAGState(cypher_query="MATCH (n RETURN n", cypher_retry_count=0)
        mock_neo4j.execute_cypher.side_effect = QueryExecutionError(
            "Neo.ClientError.Statement.SyntaxError: Invalid input 'RETURN'",
            query="MATCH (n RETURN n",
        )

        result = await node(state)

        assert result["cypher_retry_count"] == 1
        assert "SyntaxError" in result["cypher_error"]
        assert result["failed_cypher"] == "MATCH (n RETURN n"
        assert result["skip_generation"] is False  # 캐시 재사용 방지
        assert "graph_executor_error" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_non_syntax_error_no_retry_hints(self, node, mock_neo4j):
        """연결 실패 등 비-신텍스 에러는 재시도 힌트 없음 (재생성 무의미)"""
        state = GraphRAGState(cypher_query="MATCH (n) RETURN n")
        mock_neo4j.execute_cypher.side_effect = Exception("Connection refused")

        result = await node(state)

        assert "cypher_error" not in result
        assert "cypher_retry_count" not in result
        assert "graph_executor_error" in result["execution_path"]

    @pytest.mark.asyncio
    async def test_success_clears_retry_hints(self, node, mock_neo4j):
        """실행 성공 시 stale 재시도 힌트 클리어 (재시도 후 성공 경로)"""
        state = GraphRAGState(
            cypher_query="MATCH (n) RETURN n",
            cypher_retry_count=1,
            cypher_error="이전 SyntaxError",
            failed_cypher="MATCH (n RETURN n",
        )
        mock_neo4j.execute_cypher.return_value = [{"n": "data"}]

        result = await node(state)

        assert result["cypher_error"] is None
        assert result["failed_cypher"] is None
        assert result["result_count"] == 1

    @pytest.mark.asyncio
    async def test_retry_count_increments_from_previous(self, node, mock_neo4j):
        """재시도 카운터는 이전 값에서 +1 (한도 판정의 근거)"""
        from src.domain.exceptions import QueryExecutionError

        state = GraphRAGState(cypher_query="BAD", cypher_retry_count=1)
        mock_neo4j.execute_cypher.side_effect = QueryExecutionError(
            "SyntaxError: Invalid input", query="BAD"
        )

        result = await node(state)
        assert result["cypher_retry_count"] == 2


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


class TestBaseNodeTiming:
    """BaseNode 노드별 소요시간 계측 테스트"""

    def _make_node(self):
        from src.graph.nodes.base import BaseNode

        class FastNode(BaseNode[dict]):
            @property
            def name(self) -> str:
                return "fast_node"

            @property
            def input_keys(self) -> list[str]:
                return []

            async def _process(self, state):
                return {"execution_path": ["fast_node"]}

        return FastNode()

    @pytest.mark.asyncio
    async def test_success_injects_node_timing(self):
        """성공 경로에서 node_timings에 자기 항목 주입"""
        node = self._make_node()
        result = await node(GraphRAGState(question="t"))

        assert "fast_node" in result["node_timings"]
        assert result["node_timings"]["fast_node"] >= 0.0

    @pytest.mark.asyncio
    async def test_timeout_injects_node_timing(self):
        """타임아웃 경로에서도 소요시간 기록"""
        from src.graph.nodes.base import BaseNode

        class SlowNode(BaseNode[dict]):
            @property
            def name(self) -> str:
                return "slow_node"

            @property
            def timeout_seconds(self) -> float:
                return 0.05

            @property
            def input_keys(self) -> list[str]:
                return []

            async def _process(self, state):
                import asyncio

                await asyncio.sleep(5)
                return {}

        result = await SlowNode()(GraphRAGState(question="t"))

        assert "slow_node" in result["node_timings"]
        assert result["node_timings"]["slow_node"] >= 0.05
        assert "slow_node_timeout" in result["execution_path"]
