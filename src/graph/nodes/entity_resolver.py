"""
Entity Resolver Node

추출된 엔티티를 Neo4j 그래프의 실제 노드와 매칭합니다.
"""

from src.domain.types import EntityResolverUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.neo4j_repository import Neo4jRepository


class EntityResolverNode(BaseNode[EntityResolverUpdate]):
    """엔티티 해석 노드"""

    def __init__(self, neo4j_repository: Neo4jRepository):
        super().__init__()
        self._neo4j = neo4j_repository

    @property
    def name(self) -> str:
        return "entity_resolver"

    @property
    def input_keys(self) -> list[str]:
        # expanded_entities가 있으면 우선 사용, 없으면 entities 사용
        return ["entities"]  # 최소 필수 키


    async def _process(self, state: GraphRAGState) -> EntityResolverUpdate:
        """
        엔티티 해석 (그래프 노드 매칭)

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        # expanded_entities가 있으면 우선 사용 (온톨로지 확장된 엔티티)
        # 없으면 entities 사용 (원본 엔티티)
        # 주의: or 연산자는 빈 dict {}를 False로 평가하므로 명시적 None 체크
        entities_map = state.get("expanded_entities")
        if entities_map is None:
            entities_map = state.get("entities", {})

        if not entities_map:
            self._logger.info("No entities to resolve")
            return EntityResolverUpdate(
                resolved_entities=[],
                execution_path=[f"{self.name}_skipped"],
            )

        total_entities_count = sum(len(values) for values in entities_map.values())
        self._logger.info(f"Resolving {total_entities_count} entities...")

        resolved = []

        # 각 엔티티 타입과 값에 대해 순회
        for entity_type, values in entities_map.items():
            for value in values:
                if not value:
                    continue

                try:
                    # 이름으로 노드 검색
                    matches = await self._neo4j.find_entities_by_name(
                        name=value,
                        labels=[entity_type]
                        if entity_type and entity_type != "Unknown"
                        else None,
                        limit=3,
                    )

                    if matches:
                        # 가장 좋은 매치 선택 (첫 번째)
                        best_match = matches[0]
                        resolved.append(
                            {
                                "id": best_match.id,
                                "labels": best_match.labels,
                                # name 속성이 없으면 원래 값 사용
                                "name": best_match.properties.get("name", value),
                                "properties": best_match.properties,
                                "match_score": 1.0,  # 첫 번째 매치(가장 정확) 기준
                                "original_value": value,
                            }
                        )
                        self._logger.debug(
                            f"Resolved '{value}' to node {best_match.id}"
                        )
                    else:
                        self._logger.debug(f"Could not resolve '{value}'")

                except Exception as e:
                    self._logger.warning(f"Failed to resolve entity '{value}': {e}")
                    # 에러 발생 시 건너뜀

        self._logger.info(f"Resolved {len(resolved)} entities")

        return EntityResolverUpdate(
            resolved_entities=resolved,
            execution_path=[self.name],
        )
