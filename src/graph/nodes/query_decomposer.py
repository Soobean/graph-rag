"""
Query Decomposer Node

Multi-hop 쿼리를 분해하여 단계별 실행 계획을 생성합니다.
예: "Python 잘하는 사람의 멘토 중 AWS 경험자는?"
    → hop1: Employee-[:HAS_SKILL]->Skill(Python)
    → hop2: Employee<-[:MENTORS]-Employee
    → hop3: Employee-[:HAS_SKILL]->Skill(AWS)
"""

from src.domain.types import QueryDecomposerUpdate, QueryPlan
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository


class QueryDecomposerNode(BaseNode[QueryDecomposerUpdate]):
    """Multi-hop 쿼리 분해 노드"""

    # Multi-hop 쿼리로 분류할 Intent 목록
    MULTI_HOP_INTENTS = [
        "path_analysis",
        "relationship_search",
        "mentoring_network",
    ]

    def __init__(self, llm_repository: LLMRepository):
        super().__init__()
        self._llm = llm_repository

    @property
    def name(self) -> str:
        return "query_decomposer"

    @property
    def input_keys(self) -> list[str]:
        return ["question", "intent"]

    async def _process(self, state: GraphRAGState) -> QueryDecomposerUpdate:
        """
        쿼리 분해 처리

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state.get("question", "")
        intent = state.get("intent", "unknown")

        # Multi-hop이 아닌 Intent는 스킵
        if intent not in self.MULTI_HOP_INTENTS:
            self._logger.info(f"Skipping decomposition for intent: {intent}")
            return QueryDecomposerUpdate(
                query_plan=QueryPlan(
                    is_multi_hop=False,
                    hop_count=1,
                    hops=[],
                    final_return="",
                    explanation="Single-hop query",
                ),
                execution_path=[f"{self.name}_skipped"],
            )

        self._logger.info(f"Decomposing query: {question[:50]}...")

        try:
            result = await self._llm.decompose_query(question=question)

            query_plan = QueryPlan(
                is_multi_hop=result.get("is_multi_hop", False),
                hop_count=result.get("hop_count", 1),
                hops=result.get("hops", []),
                final_return=result.get("final_return", ""),
                explanation=result.get("explanation", ""),
            )

            self._logger.info(
                f"Query decomposed: {query_plan['hop_count']} hops, "
                f"multi_hop={query_plan['is_multi_hop']}"
            )

            return QueryDecomposerUpdate(
                query_plan=query_plan,
                execution_path=[self.name],
            )

        except Exception as e:
            self._logger.error(f"Query decomposition failed: {e}")
            # 실패 시 단일 홉으로 폴백
            return QueryDecomposerUpdate(
                query_plan=QueryPlan(
                    is_multi_hop=False,
                    hop_count=1,
                    hops=[],
                    final_return="",
                    explanation=f"Decomposition failed: {e}",
                ),
                error=f"Query decomposition failed: {e}",
                execution_path=[f"{self.name}_error"],
            )
