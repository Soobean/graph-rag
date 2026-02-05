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

        concept_expander를 거친 경우 (expanded_entities + original_entities 존재):
        - 확장된 동의어 중 하나라도 DB에서 찾으면 해당 원본 엔티티는 resolved로 처리

        concept_expander를 거치지 않은 경우:
        - 각 엔티티를 개별적으로 처리

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리 (resolved + unresolved 엔티티 포함)
        """
        expanded_by_original = state.get("expanded_entities_by_original")
        original_map = state.get("original_entities")

        # concept_expander를 거쳤는지 확인
        has_expansion = expanded_by_original is not None and original_map is not None

        # entities_map: 실제 DB 검색에 사용할 맵
        # reference_map: unresolved 판단 기준이 되는 원본 맵
        expanded_to_originals: dict[str, dict[str, set[str]]] = {}
        if has_expansion:
            entities_map = {}
            reference_map = original_map
            for entity_type, original_to_expanded in expanded_by_original.items():
                expanded_values: set[str] = set()
                expanded_to_originals[entity_type] = {}
                for original_value, expanded_values_list in original_to_expanded.items():
                    for expanded_value in expanded_values_list:
                        expanded_value = expanded_value.strip()
                        if not expanded_value:
                            continue
                        expanded_values.add(expanded_value)
                        expanded_to_originals[entity_type].setdefault(
                            expanded_value, set()
                        ).add(original_value)
                entities_map[entity_type] = list(expanded_values)
        else:
            entities_map = state.get("entities", {})
            reference_map = entities_map

        if not entities_map:
            self._logger.info("No entities to resolve")
            return EntityResolverUpdate(
                resolved_entities=[],
                unresolved_entities=[],
                execution_path=[f"{self.name}_skipped"],
            )

        reference_count = sum(len(values) for values in reference_map.values())
        self._logger.info(f"Resolving {reference_count} entities...")

        resolved: list[ResolvedEntity] = []
        unresolved: list[UnresolvedEntity] = []
        resolved_originals: set[tuple[str, str]] = set()  # (entity_type, original_value)
        question = state.get("question", "")
        now = datetime.now(UTC).isoformat()

        # 1단계: 엔티티 검색
        for entity_type, values in entities_map.items():
            for value in values:
                value = value.strip()
                if not value:
                    continue

                try:
                    matches = await self._neo4j.find_entities_by_name(
                        name=value,
                        labels=[entity_type]
                        if entity_type and entity_type != "Unknown"
                        else None,
                        limit=3,
                    )

                    if matches:
                        best_match = matches[0]
                        # 중복 방지
                        existing_ids = {r["id"] for r in resolved}
                        if best_match.id not in existing_ids:
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

                        if has_expansion:
                            # 확장 맵을 통해 원본별 resolved 처리
                            for orig in expanded_to_originals.get(entity_type, {}).get(value, set()):
                                resolved_originals.add((entity_type, orig))
                        else:
                            # 개별 처리: 찾은 값만 resolved로 마킹
                            resolved_originals.add((entity_type, value))

                except Exception as e:
                    self._logger.warning(f"Failed to resolve entity '{value}': {e}")

        # 2단계: reference_map 기준으로 unresolved 판단
        for entity_type, ref_values in reference_map.items():
            for ref_value in ref_values:
                ref_value = ref_value.strip()
                if not ref_value:
                    continue

                if (entity_type, ref_value) not in resolved_originals:
                    unresolved.append(
                        UnresolvedEntity(
                            term=ref_value,
                            category=entity_type,
                            question=question,
                            timestamp=now,
                        )
                    )
                    self._logger.info(
                        f"Unresolved entity: '{ref_value}' (category: {entity_type})"
                    )

        self._logger.info(
            f"Resolved {len(resolved)} entities, {len(unresolved)} unresolved"
        )

        # 3단계: entities를 DB 실제 이름으로 보정
        # (예: "AI 연구소" → "AI연구소", Cypher generator가 정확한 이름 사용)
        corrected_entities: dict[str, list[str]] | None = None
        original_entities = state.get("entities", {})
        for r in resolved:
            db_name = r.get("name", "")
            original_value = r.get("original_value", "")
            if db_name and original_value and db_name != original_value:
                if corrected_entities is None:
                    corrected_entities = {
                        k: list(v) for k, v in original_entities.items()
                    }
                for entity_type, values in corrected_entities.items():
                    corrected_entities[entity_type] = [
                        db_name if v == original_value else v for v in values
                    ]
                self._logger.info(
                    f"Corrected entity: '{original_value}' → '{db_name}'"
                )

        result = EntityResolverUpdate(
            resolved_entities=resolved,
            unresolved_entities=unresolved,
            execution_path=[self.name],
        )

        if corrected_entities is not None:
            result["entities"] = corrected_entities

        return result
