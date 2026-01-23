#!/usr/bin/env python3
"""
관계 정규화 CLI

추출된 트리플의 관계를 정규화합니다 (유사 관계 그룹화).

사용법:
    python scripts/normalize_relations.py --input triples.json --output normalized.json
    python scripts/normalize_relations.py --input triples.json --schema schema.yaml
    python scripts/normalize_relations.py --input triples.json --min-frequency 3

출력:
    정규화된 트리플 JSON과 관계 매핑 YAML
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import yaml

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.bootstrap.models import NormalizationResult, SchemaProposal
from src.bootstrap.relation_normalizer import RelationNormalizer
from src.bootstrap.utils import (
    load_schema_from_file,
    load_triples_from_file,
    save_triples_to_file,
)
from src.config import Settings
from src.repositories.llm_repository import LLMRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)




def save_relation_mapping(result: NormalizationResult, mapping_path: str) -> None:
    """관계 매핑 저장"""
    data = {
        "groups": [
            {
                "canonical_name": g.canonical_name,
                "variants": g.variants,
                "frequency": g.frequency,
                "description": g.description,
            }
            for g in result.groups
        ],
        "mapping": result.mapping,
        "unmapped": result.unmapped_relations,
    }

    with open(mapping_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    logger.info(f"관계 매핑 저장됨: {mapping_path}")


async def main():
    parser = argparse.ArgumentParser(
        description="추출된 트리플의 관계 정규화 (유사 관계 그룹화)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 기본 정규화
  python scripts/normalize_relations.py --input triples.json

  # 스키마 힌트와 함께
  python scripts/normalize_relations.py --input triples.json --schema schema.yaml

  # 최소 빈도 설정
  python scripts/normalize_relations.py --input triples.json --min-frequency 3
        """,
    )

    parser.add_argument(
        "--input",
        required=True,
        help="입력 트리플 JSON 파일",
    )
    parser.add_argument(
        "--schema",
        help="스키마 힌트 파일 (YAML)",
    )
    parser.add_argument(
        "--output",
        default="normalized_triples.json",
        help="출력 파일 경로 (default: normalized_triples.json)",
    )
    parser.add_argument(
        "--mapping-output",
        default="relation_mapping.yaml",
        help="관계 매핑 출력 파일 (default: relation_mapping.yaml)",
    )
    parser.add_argument(
        "--min-frequency",
        type=int,
        default=1,
        help="정규화에 포함할 최소 관계 빈도 (default: 1)",
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

    logger.info("=" * 60)
    logger.info(" 관계 정규화 (Relation Normalization)")
    logger.info("=" * 60)

    # 트리플 로드
    logger.info(f"\n[1/4] 트리플 로드 중: {args.input}")
    triples = load_triples_from_file(args.input)

    if not triples:
        logger.error("트리플을 찾을 수 없습니다.")
        sys.exit(1)

    logger.info(f"  ✓ {len(triples)}개 트리플 로드됨")

    # 관계 빈도 분석
    from collections import Counter

    rel_freq = Counter(t.relation for t in triples)
    logger.info(f"  고유 관계: {len(rel_freq)}개")

    # 스키마 로드
    schema_hint: SchemaProposal | None = None
    if args.schema:
        logger.info(f"\n[2/4] 스키마 힌트 로드: {args.schema}")
        schema_hint = load_schema_from_file(args.schema)
        if schema_hint:
            logger.info(f"  ✓ 스키마 로드됨: {len(schema_hint.relationship_types)} 관계 타입")
    else:
        logger.info("\n[2/4] 스키마 힌트 없음")

    # LLM Repository 초기화
    logger.info("\n[3/4] LLM으로 관계 그룹화 중...")
    settings = Settings()
    llm_repo = LLMRepository(settings)

    try:
        normalizer = RelationNormalizer(llm_repo)

        # 관계 그룹화
        result = await normalizer.group_relations(
            triples=triples,
            schema_hint=schema_hint,
            min_frequency=args.min_frequency,
        )

        # 그룹 결과 출력
        logger.info(f"\n  생성된 그룹: {len(result.groups)}개")
        for group in result.groups[:10]:  # 상위 10개만
            logger.info(f"    - {group.canonical_name}: "
                       f"{len(group.variants)} 변형, {group.frequency}회")

        if result.unmapped_relations:
            logger.info(f"\n  미매핑 관계: {len(result.unmapped_relations)}개")
            for rel in result.unmapped_relations[:5]:
                logger.info(f"    - {rel}")

        # 트리플 정규화
        logger.info("\n[4/4] 트리플 정규화 중...")
        normalized_triples = normalizer.normalize_triples(triples, result)

        # 결과 저장
        save_triples_to_file(normalized_triples, args.output)
        save_relation_mapping(result, args.mapping_output)

        # 통계 출력
        logger.info("\n" + "=" * 60)
        logger.info(" 정규화 완료!")
        logger.info("=" * 60)
        logger.info(f"  원본 트리플: {len(triples)}개")
        logger.info(f"  정규화된 트리플: {len(normalized_triples)}개")
        logger.info(f"  관계 그룹: {len(result.groups)}개")
        logger.info(f"  출력 파일: {args.output}")
        logger.info(f"  매핑 파일: {args.mapping_output}")

        # 정규화 후 관계 빈도
        new_rel_freq = Counter(t.relation for t in normalized_triples)
        logger.info(f"\n  정규화 후 고유 관계: {len(new_rel_freq)}개 "
                   f"({len(rel_freq)} → {len(new_rel_freq)})")

        logger.info("\n  다음 단계: scripts/bulk_load_triples.py로 Neo4j 적재")

    except Exception as e:
        logger.error(f"❌ 오류: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
    finally:
        await llm_repo.close()


if __name__ == "__main__":
    asyncio.run(main())
