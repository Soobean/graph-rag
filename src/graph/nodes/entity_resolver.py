"""
Entity Resolver Node

추출된 엔티티를 Neo4j 그래프의 실제 노드와 매칭합니다.
"""

from datetime import UTC, datetime

from src.domain.types import EntityResolverUpdate, ResolvedEntity, UnresolvedEntity
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
        return ["entities"]

    async def _process(self, state: GraphRAGState) -> EntityResolverUpdate:
        """
        엔티티 해석 (그래프 노드 매칭)

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리 (resolved + unresolved 엔티티 포함)
        """
        # expanded_entities 우선, 없으면 entities 사용 (명시적 None 체크)
        entities_map = state.get("expanded_entities")
        if entities_map is None:
            entities_map = state.get("entities", {})

        if not entities_map:
            self._logger.info("No entities to resolve")
            return EntityResolverUpdate(
                resolved_entities=[],
                unresolved_entities=[],
                execution_path=[f"{self.name}_skipped"],
            )

        total_entities_count = sum(len(values) for values in entities_map.values())
        self._logger.info(f"Resolving {total_entities_count} entities...")

        resolved: list[ResolvedEntity] = []
        unresolved: list[UnresolvedEntity] = []
        question = state.get("question", "")
        now = datetime.now(UTC).isoformat()

        for entity_type, values in entities_map.items():
            for value in values:
                value = value.strip()
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
                        best_match = matches[0]
                        resolved.append(
                            {
                                "id": best_match.id,
                                "labels": best_match.labels,
                                "name": best_match.properties.get("name", value),
                                "properties": best_match.properties,
                                "match_score": 1.0,
                                "original_value": value,
                            }
                        )
                        self._logger.debug(
                            f"Resolved '{value}' to node {best_match.id}"
                        )
                    else:
                        unresolved.append(
                            UnresolvedEntity(
                                term=value,
                                category=entity_type,
                                question=question,
                                timestamp=now,
                            )
                        )
                        self._logger.info(
                            f"Unresolved entity: '{value}' (category: {entity_type})"
                        )

                except Exception as e:
                    self._logger.warning(f"Failed to resolve entity '{value}': {e}")
                    unresolved.append(
                        UnresolvedEntity(
                            term=value,
                            category=entity_type,
                            question=question,
                            timestamp=now,
                        )
                    )

        self._logger.info(
            f"Resolved {len(resolved)} entities, {len(unresolved)} unresolved"
        )

        return EntityResolverUpdate(
            resolved_entities=resolved,
            unresolved_entities=unresolved,
            execution_path=[self.name],
        )
