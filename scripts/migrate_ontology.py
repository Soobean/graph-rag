#!/usr/bin/env python3
"""
온톨로지 YAML → Neo4j 마이그레이션 스크립트

YAML 기반 온톨로지 데이터를 Neo4j Concept 노드와 관계로 마이그레이션합니다.

사용법:
    python scripts/migrate_ontology.py --dry-run  # 미리보기
    python scripts/migrate_ontology.py            # 실행
    python scripts/migrate_ontology.py --verify   # 검증만 실행

데이터 모델:
    (:Concept {name, type, description?})
    (:Concept)-[:SAME_AS]->(:Concept)  # 동의어
    (:Concept)-[:IS_A]->(:Concept)     # 계층 (child → parent)
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.ontology.loader import OntologyLoader
from src.infrastructure.neo4j_client import Neo4jClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class OntologyMigrator:
    """YAML → Neo4j 온톨로지 마이그레이터"""

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        ontology_loader: OntologyLoader,
        dry_run: bool = False,
    ):
        self._client = neo4j_client
        self._loader = ontology_loader
        self._dry_run = dry_run
        self._stats = {
            "concepts_created": 0,
            "same_as_created": 0,
            "is_a_created": 0,
            "errors": [],
        }

    async def migrate(self) -> dict[str, Any]:
        """전체 마이그레이션 실행"""
        logger.info("=" * 60)
        logger.info(" 온톨로지 마이그레이션 시작")
        logger.info("=" * 60)
        logger.info(f"Dry run: {self._dry_run}")

        try:
            # 1. 인덱스 생성
            await self._create_indexes()

            # 2. 스킬 동의어 마이그레이션
            await self._migrate_skills()

            # 3. 스킬 계층 마이그레이션
            await self._migrate_hierarchy()

            # 4. 검증
            await self._verify_migration()

            logger.info("=" * 60)
            logger.info(" 마이그레이션 완료")
            logger.info("=" * 60)
            logger.info(f"  Concepts 생성: {self._stats['concepts_created']}")
            logger.info(f"  SAME_AS 관계: {self._stats['same_as_created']}")
            logger.info(f"  IS_A 관계: {self._stats['is_a_created']}")

            if self._stats["errors"]:
                logger.warning(f"  에러: {len(self._stats['errors'])}건")
                for err in self._stats["errors"][:5]:
                    logger.warning(f"    - {err}")

        except Exception as e:
            logger.error(f"마이그레이션 실패: {e}")
            self._stats["errors"].append(str(e))
            raise

        return self._stats

    async def _create_indexes(self) -> None:
        """Concept 노드용 인덱스 생성"""
        logger.info("\n[1/4] 인덱스 생성 중...")

        indexes = [
            # Concept name 유니크 제약 (type별로)
            """
            CREATE CONSTRAINT concept_name_type_unique IF NOT EXISTS
            FOR (c:Concept) REQUIRE (c.name, c.type) IS UNIQUE
            """,
            # name 검색용 인덱스
            """
            CREATE INDEX concept_name_idx IF NOT EXISTS
            FOR (c:Concept) ON (c.name)
            """,
            # type별 필터링 인덱스
            """
            CREATE INDEX concept_type_idx IF NOT EXISTS
            FOR (c:Concept) ON (c.type)
            """,
        ]

        if self._dry_run:
            logger.info("  [DRY RUN] 인덱스 생성 스킵")
            return

        for idx_query in indexes:
            try:
                await self._client.execute_write(idx_query)
            except Exception as e:
                # 이미 존재하는 경우 무시
                if "already exists" not in str(e).lower():
                    logger.warning(f"  인덱스 생성 실패: {e}")

        logger.info("  ✓ 인덱스 생성 완료")

    async def _migrate_skills(self) -> None:
        """스킬 동의어 마이그레이션"""
        logger.info("\n[2/4] 스킬 동의어 마이그레이션 중...")

        synonyms_data = self._loader.load_synonyms()
        skills_data = synonyms_data.get("skills", {})

        if self._dry_run:
            logger.info(f"  [DRY RUN] {len(skills_data)} 스킬 그룹 처리 예정")
            for skill_name, info in skills_data.items():
                if isinstance(info, dict):
                    canonical = info.get("canonical", skill_name)
                    aliases = info.get("aliases", [])
                    logger.info(f"    - {canonical}: {len(aliases)} 동의어")
            return

        # 배치 처리를 위한 데이터 준비
        concepts_to_create: list[dict[str, Any]] = []
        same_as_relations: list[dict[str, str]] = []

        for skill_name, info in skills_data.items():
            if not isinstance(info, dict):
                continue

            canonical = info.get("canonical", skill_name)
            aliases = info.get("aliases", [])

            # Canonical concept
            concepts_to_create.append({
                "name": canonical,
                "type": "skill",
                "description": f"Skill: {canonical}",
                "is_canonical": True,
            })

            # Alias concepts + SAME_AS relations
            for alias_entry in aliases:
                alias_name = OntologyLoader._parse_alias(alias_entry)

                concepts_to_create.append({
                    "name": alias_name,
                    "type": "skill",
                    "description": f"Alias of {canonical}",
                    "is_canonical": False,
                })
                same_as_relations.append({
                    "from_name": alias_name,
                    "to_name": canonical,
                    "weight": 1.0,
                })

        # Concept 노드 일괄 생성
        await self._batch_create_concepts(concepts_to_create)

        # SAME_AS 관계 일괄 생성
        await self._batch_create_same_as(same_as_relations)

        logger.info(f"  ✓ 스킬 동의어 마이그레이션 완료")

    async def _migrate_hierarchy(self) -> None:
        """스킬 계층 마이그레이션"""
        logger.info("\n[3/4] 스킬 계층 마이그레이션 중...")

        schema_data = self._loader.load_schema()
        concepts = schema_data.get("concepts", {})
        skill_categories = concepts.get("SkillCategory", [])

        if self._dry_run:
            logger.info(f"  [DRY RUN] {len(skill_categories)} 카테고리 처리 예정")
            for cat in skill_categories:
                if isinstance(cat, dict):
                    logger.info(f"    - {cat.get('name')}")
            return

        concepts_to_create: list[dict[str, Any]] = []
        is_a_relations: list[dict[str, str]] = []

        for category in skill_categories:
            if not isinstance(category, dict):
                continue

            cat_name = category.get("name", "")
            cat_desc = category.get("description", "")

            # Category Concept
            concepts_to_create.append({
                "name": cat_name,
                "type": "category",
                "description": cat_desc,
                "is_canonical": True,
            })

            # 직접 skills (카테고리 바로 아래)
            for skill in category.get("skills", []):
                is_a_relations.append({
                    "child": skill,
                    "parent": cat_name,
                })

            # Subcategories
            for subcat in category.get("subcategories", []):
                if not isinstance(subcat, dict):
                    continue

                subcat_name = subcat.get("name", "")
                subcat_desc = subcat.get("description", "")

                # Subcategory Concept
                concepts_to_create.append({
                    "name": subcat_name,
                    "type": "subcategory",
                    "description": subcat_desc,
                    "is_canonical": True,
                })

                # Subcategory IS_A Category
                is_a_relations.append({
                    "child": subcat_name,
                    "parent": cat_name,
                })

                # Skills IS_A Subcategory
                for skill in subcat.get("skills", []):
                    is_a_relations.append({
                        "child": skill,
                        "parent": subcat_name,
                    })

        # Category/Subcategory 노드 생성
        await self._batch_create_concepts(concepts_to_create)

        # IS_A 관계 생성
        await self._batch_create_is_a(is_a_relations)

        logger.info(f"  ✓ 스킬 계층 마이그레이션 완료")

    async def _batch_create_concepts(
        self, concepts: list[dict[str, Any]]
    ) -> None:
        """Concept 노드 일괄 생성 (MERGE 사용)"""
        if not concepts:
            return

        query = """
        UNWIND $concepts AS c
        MERGE (concept:Concept {name: c.name, type: c.type})
        ON CREATE SET
            concept.description = c.description,
            concept.is_canonical = c.is_canonical,
            concept.created_at = datetime(),
            concept.source = 'yaml_migration'
        ON MATCH SET
            concept.updated_at = datetime()
        RETURN count(concept) as created
        """

        result = await self._client.execute_write(query, {"concepts": concepts})
        created = result[0]["created"] if result else 0
        self._stats["concepts_created"] += created
        logger.debug(f"  Concepts 생성/업데이트: {created}")

    async def _batch_create_same_as(
        self, relations: list[dict[str, Any]]
    ) -> None:
        """SAME_AS 관계 일괄 생성 (가중치 지원)"""
        if not relations:
            return

        query = """
        UNWIND $relations AS r
        MATCH (from:Concept {name: r.from_name, type: 'skill'})
        MATCH (to:Concept {name: r.to_name, type: 'skill'})
        MERGE (from)-[rel:SAME_AS]->(to)
        ON CREATE SET
            rel.weight = r.weight,
            rel.source = 'synonyms.yaml',
            rel.created_at = datetime()
        ON MATCH SET
            rel.weight = r.weight,
            rel.updated_at = datetime()
        RETURN count(rel) as created
        """

        result = await self._client.execute_write(query, {"relations": relations})
        created = result[0]["created"] if result else 0
        self._stats["same_as_created"] += created
        logger.debug(f"  SAME_AS 관계 생성: {created}")

    async def _batch_create_is_a(
        self, relations: list[dict[str, str]]
    ) -> None:
        """IS_A 관계 일괄 생성 (child → parent)"""
        if not relations:
            return

        query = """
        UNWIND $relations AS r
        MATCH (child:Concept {name: r.child})
        MATCH (parent:Concept {name: r.parent})
        MERGE (child)-[rel:IS_A]->(parent)
        ON CREATE SET
            rel.weight = 1.0,
            rel.depth = 1,
            rel.source = 'schema.yaml',
            rel.created_at = datetime()
        RETURN count(rel) as created
        """

        result = await self._client.execute_write(query, {"relations": relations})
        created = result[0]["created"] if result else 0
        self._stats["is_a_created"] += created
        logger.debug(f"  IS_A 관계 생성: {created}")

    async def _verify_migration(self) -> None:
        """마이그레이션 검증"""
        logger.info("\n[4/4] 마이그레이션 검증 중...")

        if self._dry_run:
            logger.info("  [DRY RUN] 검증 스킵")
            return

        # 1. Concept 노드 수 확인
        count_query = """
        MATCH (c:Concept)
        RETURN c.type as type, count(c) as count
        ORDER BY type
        """
        results = await self._client.execute_query(count_query)
        logger.info("  Concept 노드 통계:")
        for r in results:
            logger.info(f"    - {r['type']}: {r['count']}개")

        # 2. 관계 수 확인
        rel_query = """
        MATCH ()-[r]->()
        WHERE type(r) IN ['SAME_AS', 'IS_A']
        RETURN type(r) as type, count(r) as count
        """
        results = await self._client.execute_query(rel_query)
        logger.info("  관계 통계:")
        for r in results:
            logger.info(f"    - {r['type']}: {r['count']}개")

        # 3. 샘플 검증: "파이썬" → "Python" 찾기
        sample_query = """
        MATCH (alias:Concept {name: '파이썬'})-[:SAME_AS]->(canonical:Concept)
        RETURN canonical.name as canonical
        """
        results = await self._client.execute_query(sample_query)
        if results:
            logger.info(f"  ✓ 샘플 검증: '파이썬' → '{results[0]['canonical']}'")
        else:
            logger.warning("  ⚠ 샘플 검증 실패: '파이썬' 동의어 관계 없음")

        # 4. 계층 검증: "Backend" 하위 스킬
        hierarchy_query = """
        MATCH (skill:Concept)-[:IS_A]->(parent:Concept {name: 'Backend'})
        RETURN collect(skill.name) as children
        """
        results = await self._client.execute_query(hierarchy_query)
        if results and results[0]["children"]:
            children = results[0]["children"][:5]  # 최대 5개만 표시
            logger.info(f"  ✓ 계층 검증: Backend 하위 → {children}")
        else:
            logger.warning("  ⚠ 계층 검증 실패: Backend 하위 스킬 없음")

        logger.info("  ✓ 검증 완료")


async def verify_only(neo4j_client: Neo4jClient) -> None:
    """검증만 실행 (마이그레이션 없이)"""
    logger.info("=" * 60)
    logger.info(" 온톨로지 데이터 검증")
    logger.info("=" * 60)

    # Concept 노드 확인
    concept_query = """
    MATCH (c:Concept)
    RETURN c.type as type, count(c) as count
    ORDER BY type
    """
    results = await neo4j_client.execute_query(concept_query)

    if not results:
        logger.warning("Concept 노드가 없습니다. 먼저 마이그레이션을 실행하세요.")
        return

    logger.info("\n[Concept 노드]")
    total = 0
    for r in results:
        logger.info(f"  {r['type']}: {r['count']}개")
        total += r["count"]
    logger.info(f"  합계: {total}개")

    # 관계 확인
    rel_query = """
    MATCH ()-[r]->()
    WHERE type(r) IN ['SAME_AS', 'IS_A']
    RETURN type(r) as type, count(r) as count
    """
    results = await neo4j_client.execute_query(rel_query)

    logger.info("\n[관계]")
    for r in results:
        logger.info(f"  {r['type']}: {r['count']}개")

    # YAML vs Neo4j 비교
    loader = OntologyLoader()
    synonyms = loader.load_synonyms()
    skills_in_yaml = len(synonyms.get("skills", {}))

    logger.info(f"\n[YAML vs Neo4j]")
    logger.info(f"  YAML skills 그룹: {skills_in_yaml}")

    # Neo4j canonical skill 수
    canonical_query = """
    MATCH (c:Concept {type: 'skill', is_canonical: true})
    RETURN count(c) as count
    """
    results = await neo4j_client.execute_query(canonical_query)
    neo4j_canonical = results[0]["count"] if results else 0
    logger.info(f"  Neo4j canonical skills: {neo4j_canonical}")

    if skills_in_yaml == neo4j_canonical:
        logger.info("  ✓ 일치")
    else:
        logger.warning(f"  ⚠ 불일치 (차이: {abs(skills_in_yaml - neo4j_canonical)})")


async def main():
    parser = argparse.ArgumentParser(
        description="온톨로지 YAML → Neo4j 마이그레이션"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 DB 변경 없이 미리보기만 실행",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="마이그레이션 없이 검증만 실행",
    )
    parser.add_argument(
        "--uri",
        default="bolt://localhost:7687",
        help="Neo4j URI (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--user",
        default="neo4j",
        help="Neo4j 사용자 (default: neo4j)",
    )
    parser.add_argument(
        "--password",
        default="password123",
        help="Neo4j 비밀번호",
    )

    args = parser.parse_args()

    # Neo4j 연결
    client = Neo4jClient(
        uri=args.uri,
        user=args.user,
        password=args.password,
    )

    try:
        await client.connect()
        logger.info(f"✓ Neo4j 연결 성공: {args.uri}")

        if args.verify:
            await verify_only(client)
        else:
            loader = OntologyLoader()
            migrator = OntologyMigrator(
                neo4j_client=client,
                ontology_loader=loader,
                dry_run=args.dry_run,
            )
            await migrator.migrate()

    except Exception as e:
        logger.error(f"❌ 오류: {e}")
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
