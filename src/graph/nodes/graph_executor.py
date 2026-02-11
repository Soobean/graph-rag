"""
Graph Executor Node — Cypher 실행 + 4차원 접근 제어 필터링 (D1~D4)
"""

from typing import Any

from src.auth.access_policy import ALL_PROPS, AccessPolicy
from src.domain.types import GraphExecutorUpdate
from src.domain.validators import validate_read_only_cypher
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.neo4j_repository import Neo4jRepository


def _is_node(value: Any) -> bool:
    """Neo4j 노드인지 판별 (labels 키가 list인 dict)"""
    return (
        isinstance(value, dict)
        and isinstance(value.get("labels"), list)
    )


def _is_relationship(value: Any) -> bool:
    """Neo4j 관계인지 판별 (type 키 + startNodeId/endNodeId가 있는 dict)"""
    return (
        isinstance(value, dict)
        and "type" in value
        and ("startNodeId" in value or "endNodeId" in value)
    )


def _get_node_label(node: dict[str, Any]) -> str | None:
    """노드의 첫 번째 라벨 반환 (보통 1개)"""
    labels = node.get("labels", [])
    return labels[0] if labels else None


def _filter_node_properties(
    node: dict[str, Any],
    allowed_properties: tuple[str, ...],
) -> dict[str, Any]:
    """노드의 properties를 허용 목록으로 필터링한 복사본 반환"""
    filtered = dict(node)
    props = node.get("properties")
    if isinstance(props, dict):
        filtered["properties"] = {
            k: v for k, v in props.items()
            if k in allowed_properties
        }
    return filtered


class GraphExecutorNode(BaseNode[GraphExecutorUpdate]):
    """그래프 쿼리 실행 노드"""

    def __init__(self, neo4j_repository: Neo4jRepository):
        super().__init__()
        self._neo4j = neo4j_repository

    @property
    def name(self) -> str:
        return "graph_executor"

    @property
    def input_keys(self) -> list[str]:
        return ["cypher_query"]

    async def _process(self, state: GraphRAGState) -> GraphExecutorUpdate:
        """Cypher 쿼리 실행 + 접근 제어 필터링"""
        cypher_query = state.get("cypher_query", "")
        parameters = state.get("cypher_parameters", {})

        if not cypher_query:
            self._logger.warning("No Cypher query to execute")
            return GraphExecutorUpdate(
                graph_results=[],
                result_count=0,
                execution_path=[f"{self.name}_skipped"],
            )

        self._logger.info(f"Executing Cypher: {cypher_query[:100]}...")

        try:
            validate_read_only_cypher(cypher_query)
        except ValueError as e:
            self._logger.error(f"Write query blocked: {e}")
            return GraphExecutorUpdate(
                graph_results=[],
                result_count=0,
                error=f"Security: {e}",
                execution_path=[f"{self.name}_blocked"],
            )

        try:
            results = await self._neo4j.execute_cypher(
                query=cypher_query,
                parameters=parameters,
            )

            self._logger.info(f"Query returned {len(results)} results")

            # 접근 제어 필터링
            user_context = state.get("user_context")
            if user_context and not user_context.is_admin:
                policy = user_context.get_access_policy()
                original_count = len(results)
                results = self._apply_access_policy(
                    results, policy, user_context.department
                )
                filtered_count = original_count - len(results)
                if filtered_count > 0:
                    self._logger.info(
                        f"Access policy filtered {filtered_count}/{original_count} records "
                        f"(user={user_context.username}, roles={user_context.roles})"
                    )

            return GraphExecutorUpdate(
                graph_results=results,
                result_count=len(results),
                execution_path=[self.name],
            )

        except Exception as e:
            self._logger.error(f"Query execution failed: {e}")
            return GraphExecutorUpdate(
                graph_results=[],
                result_count=0,
                error=f"Query execution failed: {str(e)}",
                execution_path=[f"{self.name}_error"],
            )

    def _apply_access_policy(
        self,
        results: list[dict[str, Any]],
        policy: AccessPolicy,
        user_department: str | None,
    ) -> list[dict[str, Any]]:
        """D1~D4 접근 제어 필터링 적용"""
        allowed_labels = policy.get_allowed_labels()
        filtered: list[dict[str, Any]] = []

        for record in results:
            if not self._is_record_allowed(
                record, policy, allowed_labels, user_department
            ):
                continue

            # D2: 속성 필터링 (레코드를 통과한 경우에만)
            filtered_record = self._filter_record_properties(record, policy)
            filtered.append(filtered_record)

        return filtered

    def _is_record_allowed(
        self,
        record: dict[str, Any],
        policy: AccessPolicy,
        allowed_labels: set[str],
        user_department: str | None,
    ) -> bool:
        """D1/D3/D4 위반 시 False → 레코드 전체 제거"""
        # 같은 row의 Department 노드에서 부서 이름 수집 (D3용)
        row_departments: set[str] = set()
        for value in record.values():
            if _is_node(value):
                label = _get_node_label(value)
                if label == "Department":
                    dept_name = value.get("properties", {}).get("name")
                    if dept_name:
                        row_departments.add(dept_name.lower())

        for value in record.values():
            # --- 노드 검사 ---
            if _is_node(value):
                labels = value.get("labels", [])
                if not labels:
                    return False  # 라벨 없는 노드는 거부

                # D1: 모든 라벨이 허용 목록에 있어야 함
                if any(label not in allowed_labels for label in labels):
                    return False

                # D3: 부서 범위 제어 (첫 번째 라벨 = primary)
                scope = policy.get_scope(labels[0])
                if (
                    scope == "department"
                    and user_department
                    and row_departments
                    and user_department.lower() not in row_departments
                ):
                    return False

            # --- 관계 검사 ---
            elif _is_relationship(value):
                # D4: 관계 타입 제어
                rel_type = value.get("type", "")
                if not policy.is_relationship_allowed(rel_type):
                    return False

        return True

    def _filter_record_properties(
        self,
        record: dict[str, Any],
        policy: AccessPolicy,
    ) -> dict[str, Any]:
        """D2: 노드 속성을 허용 목록으로 필터링"""
        filtered_record: dict[str, Any] = {}

        for key, value in record.items():
            if _is_node(value):
                label = _get_node_label(value)
                if label is None:
                    filtered_record[key] = value
                    continue

                allowed_props = policy.get_allowed_properties(label)
                if allowed_props is None or allowed_props == ALL_PROPS:
                    # 접근 불가(None)는 _is_record_allowed에서 이미 걸러짐
                    # "*"는 전체 허용
                    filtered_record[key] = value
                else:
                    filtered_record[key] = _filter_node_properties(
                        value, allowed_props
                    )
            else:
                # 관계, 스칼라 값은 그대로
                filtered_record[key] = value

        return filtered_record
