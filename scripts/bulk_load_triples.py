#!/usr/bin/env python3
"""
트리플 벌크 로딩 CLI

정규화된 트리플을 Neo4j에 벌크 로딩합니다.

사용법:
    python scripts/bulk_load_triples.py --triples normalized_triples.json
    python scripts/bulk_load_triples.py --triples triples.json --batch-size 500
    python scripts/bulk_load_triples.py --triples triples.json --dry-run

출력:
    Neo4j에 노드와 관계 생성
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.bootstrap.models import Triple
from src.bootstrap.utils import normalize_relation_type
from src.infrastructure.neo4j_client import Neo4jClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_triples(input_path: str) -> list[Triple]:
    """트리플 JSON 파일 로드"""
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    triples = []
    for item in data.get("triples", []):
        triples.append(Triple.from_dict(item))

    return triples


class BulkLoader:
    """Neo4j 벌크 로더"""

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        dry_run: bool = False,
    ):
        self._client = neo4j_client
        self._dry_run = dry_run
        self._stats = {
            "nodes_created": 0,
            "relationships_created": 0,
            "errors": [],
        }

    async def load_triples(
        self,
        triples: list[Triple],
        batch_size: int = 1000,
    ) -> dict[str, Any]:
        """
        트리플을 Neo4j에 벌크 로딩

        Args:
            triples: 로딩할 트리플 목록
            batch_size: 배치 크기

        Returns:
            로딩 통계
        """
        logger.info(f"총 {len(triples)}개 트리플 로딩 시작")
        logger.info(f"배치 크기: {batch_size}, Dry run: {self._dry_run}")

        if self._dry_run:
            return await self._dry_run_analysis(triples)

        # 1. 인덱스 생성
        await self._create_indexes()

        # 2. 고유 엔티티 추출 및 노드 생성
        entities = self._extract_entities(triples)
        await self._batch_create_nodes(entities, batch_size)

        # 3. 관계 생성
        await self._batch_create_relationships(triples, batch_size)

        return self._stats

    async def _dry_run_analysis(self, triples: list[Triple]) -> dict[str, Any]:
        """Dry run 분석"""
        entities = self._extract_entities(triples)
        relations = {}
        for t in triples:
            relations[t.relation] = relations.get(t.relation, 0) + 1

        logger.info("\n[DRY RUN] 분석 결과:")
        logger.info(f"  고유 엔티티: {len(entities)}개")
        logger.info(f"  관계: {len(triples)}개")
        logger.info(f"  고유 관계 타입: {len(relations)}개")

        logger.info("\n  관계 타입별 수:")
        for rel, count in sorted(relations.items(), key=lambda x: -x[1])[:10]:
            logger.info(f"    - {rel}: {count}개")

        return {
            "nodes_created": len(entities),
            "relationships_created": len(triples),
            "dry_run": True,
        }

    async def _create_indexes(self) -> None:
        """Entity 노드용 인덱스 생성"""
        logger.info("\n[1/3] 인덱스 생성 중...")

        indexes = [
            # Entity name 인덱스
            """
            CREATE INDEX entity_name_idx IF NOT EXISTS
            FOR (e:Entity) ON (e.name)
            """,
            # Entity type 인덱스
            """
            CREATE INDEX entity_type_idx IF NOT EXISTS
            FOR (e:Entity) ON (e.type)
            """,
            # 복합 유니크 제약
            """
            CREATE CONSTRAINT entity_name_type_unique IF NOT EXISTS
            FOR (e:Entity) REQUIRE (e.name, e.type) IS UNIQUE
            """,
        ]

        for idx_query in indexes:
            try:
                await self._client.execute_write(idx_query)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"  인덱스 생성 실패: {e}")

        logger.info("  ✓ 인덱스 생성 완료")

    def _extract_entities(self, triples: list[Triple]) -> dict[str, dict[str, Any]]:
        """트리플에서 고유 엔티티 추출"""
        entities: dict[str, dict[str, Any]] = {}

        for triple in triples:
            # Subject 엔티티
            subj_key = triple.subject.lower()
            if subj_key not in entities:
                entities[subj_key] = {
                    "name": triple.subject,
                    "type": "subject",  # 기본 타입
                    "mention_count": 0,
                }
            entities[subj_key]["mention_count"] += 1

            # Object 엔티티
            obj_key = triple.object.lower()
            if obj_key not in entities:
                entities[obj_key] = {
                    "name": triple.object,
                    "type": "object",  # 기본 타입
                    "mention_count": 0,
                }
            entities[obj_key]["mention_count"] += 1

        return entities

    async def _batch_create_nodes(
        self,
        entities: dict[str, dict[str, Any]],
        batch_size: int,
    ) -> None:
        """엔티티 노드 배치 생성"""
        logger.info(f"\n[2/3] 노드 생성 중... ({len(entities)}개)")

        entity_list = list(entities.values())

        for i in range(0, len(entity_list), batch_size):
            batch = entity_list[i : i + batch_size]

            query = """
            UNWIND $entities AS e
            MERGE (n:Entity {name: e.name})
            ON CREATE SET
                n.type = e.type,
                n.mention_count = e.mention_count,
                n.created_at = datetime(),
                n.source = 'bootstrap'
            ON MATCH SET
                n.mention_count = n.mention_count + e.mention_count,
                n.updated_at = datetime()
            RETURN count(n) as created
            """

            try:
                result = await self._client.execute_write(query, {"entities": batch})
                created = result[0]["created"] if result else 0
                self._stats["nodes_created"] += created
            except Exception as e:
                logger.error(f"  배치 {i // batch_size + 1} 실패: {e}")
                self._stats["errors"].append(str(e))

        logger.info(f"  ✓ {self._stats['nodes_created']}개 노드 생성됨")

    async def _batch_create_relationships(
        self,
        triples: list[Triple],
        batch_size: int,
    ) -> None:
        """관계 배치 생성"""
        logger.info(f"\n[3/3] 관계 생성 중... ({len(triples)}개)")

        # 관계 타입별 그룹화
        by_type: dict[str, list[dict[str, Any]]] = {}
        for triple in triples:
            rel_type = triple.relation
            if rel_type not in by_type:
                by_type[rel_type] = []

            by_type[rel_type].append({
                "subject": triple.subject,
                "object": triple.object,
                "confidence": triple.confidence,
                "source_text": triple.source_text[:200] if triple.source_text else "",
            })

        # 타입별 배치 생성
        for rel_type, rel_data in by_type.items():
            # 관계 타입 정규화 (SCREAMING_SNAKE_CASE with validation)
            try:
                safe_rel_type = normalize_relation_type(rel_type)
            except ValueError as e:
                logger.warning(f"  Skipping invalid relation type '{rel_type}': {e}")
                continue

            for i in range(0, len(rel_data), batch_size):
                batch = rel_data[i : i + batch_size]

                query = f"""
                UNWIND $relations AS r
                MATCH (a:Entity {{name: r.subject}})
                MATCH (b:Entity {{name: r.object}})
                MERGE (a)-[rel:{safe_rel_type}]->(b)
                ON CREATE SET
                    rel.confidence = r.confidence,
                    rel.source_text = r.source_text,
                    rel.created_at = datetime()
                ON MATCH SET
                    rel.confidence = CASE
                        WHEN r.confidence > rel.confidence THEN r.confidence
                        ELSE rel.confidence
                    END,
                    rel.updated_at = datetime()
                RETURN count(rel) as created
                """

                try:
                    result = await self._client.execute_write(
                        query, {"relations": batch}
                    )
                    created = result[0]["created"] if result else 0
                    self._stats["relationships_created"] += created
                except Exception as e:
                    logger.error(f"  {rel_type} 배치 실패: {e}")
                    self._stats["errors"].append(str(e))

        logger.info(f"  ✓ {self._stats['relationships_created']}개 관계 생성됨")


async def verify_load(client: Neo4jClient) -> None:
    """로딩 결과 검증"""
    logger.info("\n[검증] 로딩 결과 확인...")

    # 노드 수
    node_query = """
    MATCH (e:Entity)
    RETURN count(e) as count
    """
    result = await client.execute_query(node_query)
    node_count = result[0]["count"] if result else 0
    logger.info(f"  Entity 노드: {node_count}개")

    # 관계 수
    rel_query = """
    MATCH ()-[r]->()
    WHERE NOT type(r) IN ['SAME_AS', 'IS_A']
    RETURN type(r) as type, count(r) as count
    ORDER BY count DESC
    LIMIT 10
    """
    results = await client.execute_query(rel_query)
    if results:
        logger.info("  관계 타입별 수 (상위 10개):")
        for r in results:
            logger.info(f"    - {r['type']}: {r['count']}개")


async def main():
    parser = argparse.ArgumentParser(
        description="정규화된 트리플을 Neo4j에 벌크 로딩",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 기본 로딩
  python scripts/bulk_load_triples.py --triples normalized_triples.json

  # 배치 크기 조정
  python scripts/bulk_load_triples.py --triples triples.json --batch-size 500

  # Dry run (실제 로딩 없이 분석만)
  python scripts/bulk_load_triples.py --triples triples.json --dry-run
        """,
    )

    parser.add_argument(
        "--triples",
        required=True,
        help="입력 트리플 JSON 파일",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="배치 크기 (default: 1000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 로딩 없이 분석만 수행",
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
        default=None,
        help="Neo4j 비밀번호 (또는 NEO4J_PASSWORD 환경변수)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="상세 로깅 출력",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 환경 변수 로드
    load_dotenv()

    # 환경 변수에서 Neo4j 설정 가져오기
    import os

    uri = os.getenv("NEO4J_URI", args.uri)
    user = os.getenv("NEO4J_USER", args.user)
    password = os.getenv("NEO4J_PASSWORD") or args.password

    # Validate password is provided
    if not password:
        logger.error(
            "Neo4j 비밀번호가 필요합니다. "
            "--password 옵션 또는 NEO4J_PASSWORD 환경변수를 설정하세요."
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(" 트리플 벌크 로딩")
    logger.info("=" * 60)

    # 트리플 로드
    logger.info(f"\n입력 파일: {args.triples}")
    triples = load_triples(args.triples)

    if not triples:
        logger.error("트리플을 찾을 수 없습니다.")
        sys.exit(1)

    logger.info(f"  ✓ {len(triples)}개 트리플 로드됨")

    # Neo4j 연결
    client = Neo4jClient(uri=uri, user=user, password=password)

    try:
        await client.connect()
        logger.info(f"  ✓ Neo4j 연결 성공: {uri}")

        # 벌크 로딩
        loader = BulkLoader(client, dry_run=args.dry_run)
        stats = await loader.load_triples(triples, batch_size=args.batch_size)

        # 검증
        if not args.dry_run:
            await verify_load(client)

        # 통계 출력
        logger.info("\n" + "=" * 60)
        logger.info(" 로딩 완료!")
        logger.info("=" * 60)
        logger.info(f"  노드 생성: {stats.get('nodes_created', 0)}개")
        logger.info(f"  관계 생성: {stats.get('relationships_created', 0)}개")

        if stats.get("errors"):
            logger.warning(f"  에러: {len(stats['errors'])}건")

    except Exception as e:
        logger.error(f"❌ 오류: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
