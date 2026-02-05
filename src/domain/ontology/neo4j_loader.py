"""
Neo4j Ontology Loader

Neo4j 기반 온톨로지 로더
- Cypher 쿼리를 사용한 개념 조회
- YAML OntologyLoader와 동일한 인터페이스 제공
- 비동기 지원

사용 예시:
    loader = Neo4jOntologyLoader(neo4j_client)
    canonical = await loader.get_canonical("파이썬", "skills")  # "Python"
    synonyms = await loader.get_synonyms("Python", "skills")    # ["Python", "파이썬", ...]
    children = await loader.get_children("Backend", "skills")   # ["Python", "Java", ...]
"""

import logging
from typing import Any

from src.domain.ontology.loader import (
    DEFAULT_EXPANSION_CONFIG,
    ExpansionConfig,
    OntologyCategory,
)
from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class Neo4jOntologyLoader:
    """
    Neo4j 기반 온톨로지 로더

    YAML OntologyLoader와 동일한 인터페이스를 제공하지만,
    모든 메서드가 비동기(async)입니다.

    Note:
        이 로더는 migrate_ontology.py로 생성된 Concept 노드와
        SAME_AS, IS_A 관계를 조회합니다.
    """

    def __init__(self, neo4j_client: Neo4jClient):
        """
        Args:
            neo4j_client: 연결된 Neo4jClient 인스턴스
        """
        self._client = neo4j_client
        logger.info("Neo4jOntologyLoader initialized")

    async def get_canonical(
        self,
        term: str,
        category: str = "skills",
    ) -> str:
        """
        정규화된 이름 반환

        SAME_AS 관계를 통해 canonical name을 찾습니다.
        term이 이미 canonical이면 그대로 반환합니다.

        Args:
            term: 검색어 (예: "파이썬", "Python3")
            category: 카테고리 (skills만 지원, 향후 확장)

        Returns:
            정규화된 이름 (예: "Python")
            찾지 못하면 원본 term 반환
        """
        if category != OntologyCategory.SKILLS:
            return term

        # Case-insensitive 검색
        query = """
        // 먼저 정확한 이름 매칭 시도
        OPTIONAL MATCH (exact:Concept {type: 'skill'})
        WHERE toLower(exact.name) = toLower($term)

        // SAME_AS 관계로 canonical 찾기
        OPTIONAL MATCH (exact)-[:SAME_AS]->(canonical:Concept {is_canonical: true})

        RETURN
            CASE
                // alias → canonical 관계가 있으면 canonical 반환
                WHEN canonical IS NOT NULL THEN canonical.name
                // exact 매칭이 canonical이면 그대로 반환
                WHEN exact.is_canonical = true THEN exact.name
                // 찾지 못하면 null
                ELSE null
            END as canonical_name
        """

        try:
            results = await self._client.execute_query(query, {"term": term})
            if results and results[0]["canonical_name"]:
                return results[0]["canonical_name"]
        except Exception as e:
            logger.warning(f"get_canonical query failed: {e}")

        return term

    async def get_synonyms(
        self,
        term: str,
        category: str = "skills",
    ) -> list[str]:
        """
        동의어 목록 반환 (양방향 조회)

        canonical 기준으로 모든 동의어(alias)를 반환합니다.
        양방향 SAME_AS 탐색을 통해 전체 동의어 그룹을 찾습니다.

        Args:
            term: 검색어
            category: 카테고리

        Returns:
            동의어 목록 (canonical 포함)
            찾지 못하면 [term] 반환
        """
        if category != OntologyCategory.SKILLS:
            return [term]

        # 먼저 canonical 찾기
        canonical = await self.get_canonical(term, category)

        # canonical과 연결된 모든 동의어 조회 (양방향)
        query = """
        MATCH (c:Concept {type: 'skill'})
        WHERE toLower(c.name) = toLower($canonical)

        // 양방향 SAME_AS 탐색 (canonical → alias, alias → canonical)
        OPTIONAL MATCH (c)-[:SAME_AS]-(related:Concept {type: 'skill'})

        WITH c, collect(DISTINCT related.name) as aliases

        RETURN c.name as canonical, aliases
        """

        try:
            results = await self._client.execute_query(
                query, {"canonical": canonical}
            )
            if results:
                result = results[0]
                synonyms = [result["canonical"]] + (result["aliases"] or [])
                return list(set(synonyms))  # 중복 제거
        except Exception as e:
            logger.warning(f"get_synonyms query failed: {e}")

        return [term]

    async def get_children(
        self,
        concept: str,
        category: str = "skills",
    ) -> list[str]:
        """
        하위 개념 반환 (IS_A 관계의 역방향)

        "Backend" 검색 시 Python, Java, Node.js 등 하위 스킬 반환.
        다단계 IS_A 관계도 탐색합니다 (최대 3단계).

        Args:
            concept: 상위 개념 (예: "Backend", "Programming")
            category: 카테고리

        Returns:
            하위 개념 목록 (스킬만, 카테고리 제외)
        """
        if category != OntologyCategory.SKILLS:
            return []

        # 재귀적 IS_A 탐색 (최대 3단계)
        query = """
        MATCH (parent:Concept)
        WHERE toLower(parent.name) = toLower($concept)

        // 1~3단계 하위 개념 탐색
        OPTIONAL MATCH (child:Concept)-[:IS_A*1..3]->(parent)
        WHERE child.type = 'skill'  // 스킬만 반환 (카테고리 제외)

        RETURN collect(DISTINCT child.name) as children
        """

        try:
            results = await self._client.execute_query(query, {"concept": concept})
            if results and results[0]["children"]:
                return results[0]["children"]
        except Exception as e:
            logger.warning(f"get_children query failed: {e}")

        return []

    async def expand_concept(
        self,
        term: str,
        category: str = "skills",
        config: ExpansionConfig | None = None,
    ) -> list[str]:
        """
        개념 확장 (동의어 + 하위 개념)

        기존 메서드들을 조합하여 확장 결과를 반환합니다.

        Args:
            term: 검색어
            category: 카테고리
            config: 확장 설정 (None이면 DEFAULT_EXPANSION_CONFIG 사용)

        Returns:
            확장된 개념 목록 (중복 제거, 최대 max_total개)
        """
        if config is None:
            config = DEFAULT_EXPANSION_CONFIG

        if category != OntologyCategory.SKILLS:
            return [term]

        result: list[str] = [term]
        seen: set[str] = {term}

        try:
            # 1. canonical 찾기
            canonical = await self.get_canonical(term, category)
            if canonical != term and canonical not in seen:
                result.append(canonical)
                seen.add(canonical)

            # 2. 동의어 조회
            if config.include_synonyms:
                synonyms = await self.get_synonyms(canonical, category)
                for syn in synonyms[:config.max_synonyms]:
                    if syn not in seen:
                        result.append(syn)
                        seen.add(syn)

            # 3. 하위 개념 조회
            if config.include_children:
                children = await self.get_children(canonical, category)
                for child in children[:config.max_children]:
                    if child not in seen:
                        result.append(child)
                        seen.add(child)

        except Exception as e:
            logger.warning(f"expand_concept failed: {e}")

        return result[:config.max_total]

    async def get_all_skills(self) -> list[str]:
        """
        모든 canonical 스킬 목록 반환

        Returns:
            canonical 스킬 이름 목록
        """
        query = """
        MATCH (c:Concept {type: 'skill', is_canonical: true})
        RETURN collect(c.name) as skills
        """

        try:
            results = await self._client.execute_query(query)
            if results:
                return results[0]["skills"] or []
        except Exception as e:
            logger.warning(f"get_all_skills query failed: {e}")

        return []

    async def get_category_hierarchy(self) -> dict[str, Any]:
        """
        스킬 카테고리 계층 구조 반환

        Returns:
            카테고리 → 서브카테고리 → 스킬 계층 구조
        """
        query = """
        // 카테고리 조회
        MATCH (cat:Concept {type: 'category'})

        // 서브카테고리 조회
        OPTIONAL MATCH (subcat:Concept {type: 'subcategory'})-[:IS_A]->(cat)

        // 스킬 조회 (서브카테고리 하위)
        OPTIONAL MATCH (skill:Concept {type: 'skill'})-[:IS_A]->(subcat)

        WITH cat, subcat,
             collect(DISTINCT skill.name) as skills

        WITH cat,
             collect({name: subcat.name, skills: skills}) as subcategories

        RETURN cat.name as category,
               cat.description as description,
               subcategories
        ORDER BY category
        """

        try:
            results = await self._client.execute_query(query)
            hierarchy = {}
            for r in results:
                hierarchy[r["category"]] = {
                    "description": r["description"],
                    "subcategories": [
                        s for s in r["subcategories"]
                        if s["name"] is not None
                    ],
                }
            return hierarchy
        except Exception as e:
            logger.warning(f"get_category_hierarchy query failed: {e}")

        return {}

    async def health_check(self) -> dict[str, Any]:
        """
        온톨로지 데이터 상태 확인

        Returns:
            통계 및 상태 정보
        """
        query = """
        MATCH (c:Concept)
        WITH c.type as type, count(c) as count
        ORDER BY type
        RETURN collect({type: type, count: count}) as concept_stats

        UNION ALL

        MATCH ()-[r]->()
        WHERE type(r) IN ['SAME_AS', 'IS_A']
        WITH type(r) as rel_type, count(r) as count
        RETURN collect({type: rel_type, count: count}) as concept_stats
        """

        try:
            results = await self._client.execute_query(query)
            stats = {
                "concepts": {},
                "relationships": {},
                "status": "healthy",
            }

            for r in results:
                for item in r.get("concept_stats", []):
                    if item["type"] in ["skill", "category", "subcategory"]:
                        stats["concepts"][item["type"]] = item["count"]
                    elif item["type"] in ["SAME_AS", "IS_A"]:
                        stats["relationships"][item["type"]] = item["count"]

            return stats
        except Exception as e:
            logger.error(f"health_check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def clear_cache(self) -> None:
        """
        내부 캐시 클리어

        향후 캐시 추가 시 이 메서드에서 클리어합니다.
        """
        pass
