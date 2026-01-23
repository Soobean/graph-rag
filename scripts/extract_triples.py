#!/usr/bin/env python3
"""
Triple 추출 CLI

문서에서 (주어, 관계, 목적어) 트리플을 추출합니다.

사용법:
    python scripts/extract_triples.py --input ./documents/ --output triples.json
    python scripts/extract_triples.py --input ./docs/*.txt --schema schema.yaml
    python scripts/extract_triples.py --input large_doc.txt --chunk-size 2000

출력:
    JSON 형식의 트리플 목록
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.bootstrap.models import SchemaProposal
from src.bootstrap.open_extractor import OpenExtractor
from src.bootstrap.utils import load_schema_from_file, save_triples_to_file
from src.config import Settings
from src.repositories.llm_repository import LLMRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_documents(input_path: str) -> list[tuple[str, str]]:
    """입력 경로에서 문서 로드 (파일명과 함께)"""
    path = Path(input_path)
    documents: list[tuple[str, str]] = []  # (filename, content)

    if path.is_file():
        content = path.read_text(encoding="utf-8")
        documents.append((path.name, content))

    elif path.is_dir():
        for ext in ["*.txt", "*.md", "*.json"]:
            for file_path in path.glob(ext):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    documents.append((file_path.name, content))
                except Exception as e:
                    logger.warning(f"읽기 실패: {file_path.name} - {e}")

    else:
        # 글로브 패턴
        parent = path.parent
        pattern = path.name
        for file_path in parent.glob(pattern):
            try:
                content = file_path.read_text(encoding="utf-8")
                documents.append((file_path.name, content))
            except Exception as e:
                logger.warning(f"읽기 실패: {file_path.name} - {e}")

    return documents




async def main():
    parser = argparse.ArgumentParser(
        description="문서에서 (주어, 관계, 목적어) 트리플 추출",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 기본 추출
  python scripts/extract_triples.py --input ./documents/ --output triples.json

  # 스키마 힌트와 함께
  python scripts/extract_triples.py --input ./docs/*.txt --schema schema.yaml

  # 긴 문서 청킹
  python scripts/extract_triples.py --input large_doc.txt --chunk-size 2000
        """,
    )

    parser.add_argument(
        "--input",
        required=True,
        help="문서 경로 (파일, 디렉토리, 또는 글로브 패턴)",
    )
    parser.add_argument(
        "--schema",
        help="스키마 힌트 파일 (YAML)",
    )
    parser.add_argument(
        "--output",
        default="triples.json",
        help="출력 파일 경로 (default: triples.json)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="최소 신뢰도 임계값 (default: 0.5)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="동시 처리 배치 크기 (default: 10)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=0,
        help="긴 문서 청킹 크기 (0=비활성화)",
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
    logger.info(" Open Information Extraction")
    logger.info("=" * 60)

    # 문서 로드
    logger.info(f"\n[1/4] 문서 로드 중: {args.input}")
    documents = load_documents(args.input)

    if not documents:
        logger.error("문서를 찾을 수 없습니다.")
        sys.exit(1)

    logger.info(f"  ✓ {len(documents)}개 문서 로드됨")

    # 스키마 로드
    schema_hint: SchemaProposal | None = None
    if args.schema:
        logger.info(f"\n[2/4] 스키마 힌트 로드: {args.schema}")
        schema_hint = load_schema_from_file(args.schema)
        if schema_hint:
            logger.info(f"  ✓ 스키마 로드됨: {len(schema_hint.node_labels)} 노드, "
                       f"{len(schema_hint.relationship_types)} 관계")
    else:
        logger.info("\n[2/4] 스키마 힌트 없음 (자유 추출)")

    # LLM Repository 초기화
    logger.info("\n[3/4] LLM 연결 중...")
    settings = Settings()
    llm_repo = LLMRepository(settings)

    try:
        extractor = OpenExtractor(llm_repo)

        # 추출 실행
        logger.info(f"\n[4/4] 트리플 추출 중 (min_confidence={args.min_confidence})...")

        all_triples = []

        if args.chunk_size > 0:
            # 청킹 모드 (긴 문서용)
            for filename, content in documents:
                logger.info(f"  처리 중: {filename}")
                triples = await extractor.extract_with_chunking(
                    document=content,
                    chunk_size=args.chunk_size,
                    overlap=200,
                    schema_hint=schema_hint,
                    min_confidence=args.min_confidence,
                )
                for t in triples:
                    t.metadata["source_file"] = filename
                all_triples.extend(triples)
                logger.info(f"    → {len(triples)} 트리플 추출됨")
        else:
            # 배치 모드
            contents = [content for _, content in documents]
            result = await extractor.batch_extract(
                documents=contents,
                schema_hint=schema_hint,
                batch_size=args.batch_size,
                min_confidence=args.min_confidence,
            )

            # 파일명 메타데이터 추가
            for i, (filename, _) in enumerate(documents):
                doc_id = f"doc_{i}"
                for triple in result.triples:
                    if triple.metadata.get("document_id") == doc_id:
                        triple.metadata["source_file"] = filename

            all_triples = result.triples

            if result.errors:
                logger.warning(f"  ⚠ {len(result.errors)}개 문서 처리 실패")

        # 결과 저장
        save_triples_to_file(all_triples, args.output)

        # 통계 출력
        logger.info("\n" + "=" * 60)
        logger.info(" 추출 완료!")
        logger.info("=" * 60)
        logger.info(f"  총 트리플: {len(all_triples)}개")
        logger.info(f"  출력 파일: {args.output}")

        # 관계 빈도 출력
        if all_triples:
            from collections import Counter

            rel_freq = Counter(t.relation for t in all_triples)
            logger.info("\n  관계 빈도 (상위 10개):")
            for rel, count in rel_freq.most_common(10):
                logger.info(f"    - {rel}: {count}회")

        logger.info("\n  다음 단계: scripts/normalize_relations.py로 관계 정규화")

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
