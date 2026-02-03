#!/usr/bin/env python3
"""
스키마 자동 생성 CLI

샘플 문서들을 분석하여 지식 그래프 스키마를 자동 생성합니다.

사용법:
    python scripts/generate_schema.py --input ./sample_docs/ --domain "기업 인사"
    python scripts/generate_schema.py --input ./docs/*.txt --output schema.yaml
    python scripts/generate_schema.py --refine schema.yaml --feedback "Employee에 role 속성 추가"

출력:
    YAML 형식의 스키마 제안 파일
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

from src.bootstrap.models import SchemaProposal
from src.bootstrap.schema_generator import SchemaGenerator
from src.config import Settings
from src.repositories.llm_repository import LLMRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_documents(input_path: str) -> list[str]:
    """입력 경로에서 문서 로드"""
    path = Path(input_path)

    if path.is_file():
        # 단일 파일
        return [path.read_text(encoding="utf-8")]

    if path.is_dir():
        # 디렉토리의 모든 텍스트 파일
        documents = []
        for ext in ["*.txt", "*.md", "*.json"]:
            for file_path in path.glob(ext):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    documents.append(content)
                    logger.debug(f"  로드됨: {file_path.name}")
                except Exception as e:
                    logger.warning(f"  읽기 실패: {file_path.name} - {e}")
        return documents

    # 글로브 패턴
    parent = path.parent
    pattern = path.name
    documents = []
    for file_path in parent.glob(pattern):
        try:
            content = file_path.read_text(encoding="utf-8")
            documents.append(content)
            logger.debug(f"  로드됨: {file_path.name}")
        except Exception as e:
            logger.warning(f"  읽기 실패: {file_path.name} - {e}")

    return documents


def save_schema(schema: SchemaProposal, output_path: str) -> None:
    """스키마를 YAML 파일로 저장"""
    data = schema.to_dict()

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    logger.info(f"스키마 저장됨: {output_path}")


def load_existing_schema(schema_path: str) -> SchemaProposal:
    """기존 스키마 파일 로드"""
    with open(schema_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return SchemaProposal.from_dict(data)


async def generate_new_schema(
    generator: SchemaGenerator,
    input_path: str,
    domain_hint: str | None,
    output_path: str,
) -> None:
    """새 스키마 생성"""
    logger.info("=" * 60)
    logger.info(" 스키마 자동 생성 시작")
    logger.info("=" * 60)

    # 문서 로드
    logger.info(f"\n[1/3] 문서 로드 중: {input_path}")
    documents = load_documents(input_path)

    if not documents:
        logger.error("문서를 찾을 수 없습니다.")
        sys.exit(1)

    logger.info(f"  ✓ {len(documents)}개 문서 로드됨")

    # 스키마 생성
    logger.info("\n[2/3] LLM으로 스키마 분석 중...")
    if domain_hint:
        logger.info(f"  도메인 힌트: {domain_hint}")

    schema = await generator.discover_schema(
        sample_documents=documents,
        domain_hint=domain_hint,
    )

    # 결과 출력
    logger.info("\n[3/3] 스키마 생성 완료")
    print("\n" + schema.get_schema_summary())

    # 저장
    save_schema(schema, output_path)

    logger.info("\n" + "=" * 60)
    logger.info(" 완료!")
    logger.info("=" * 60)
    logger.info(f"  출력 파일: {output_path}")
    logger.info("  다음 단계: 스키마를 검토하고 필요시 --refine 옵션으로 개선하세요.")


async def refine_existing_schema(
    generator: SchemaGenerator,
    schema_path: str,
    feedback: str,
    output_path: str,
) -> None:
    """기존 스키마 개선"""
    logger.info("=" * 60)
    logger.info(" 스키마 개선 (HITL)")
    logger.info("=" * 60)

    # 기존 스키마 로드
    logger.info(f"\n[1/3] 기존 스키마 로드: {schema_path}")
    current_schema = load_existing_schema(schema_path)
    logger.info("  ✓ 스키마 로드됨")

    # 피드백 적용
    logger.info("\n[2/3] 피드백 적용 중...")
    logger.info(f"  피드백: {feedback}")

    refined_schema = await generator.refine_schema(
        current_schema=current_schema,
        feedback=feedback,
    )

    # 결과 출력
    logger.info("\n[3/3] 스키마 개선 완료")
    print("\n" + refined_schema.get_schema_summary())

    # 저장
    save_schema(refined_schema, output_path)

    logger.info("\n" + "=" * 60)
    logger.info(" 완료!")
    logger.info("=" * 60)


async def main():
    parser = argparse.ArgumentParser(
        description="LLM 기반 지식 그래프 스키마 자동 생성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 새 스키마 생성
  python scripts/generate_schema.py --input ./sample_docs/ --domain "기업 인사/프로젝트"

  # 글로브 패턴 사용
  python scripts/generate_schema.py --input "./data/*.txt" --output my_schema.yaml

  # 기존 스키마 개선
  python scripts/generate_schema.py --refine schema.yaml --feedback "Skill 노드에 level 속성 추가"
        """,
    )

    # 새 스키마 생성 옵션
    parser.add_argument(
        "--input",
        help="샘플 문서 경로 (파일, 디렉토리, 또는 글로브 패턴)",
    )
    parser.add_argument(
        "--domain",
        help="도메인 힌트 (예: '기업 인사/프로젝트 관리')",
    )

    # 스키마 개선 옵션
    parser.add_argument(
        "--refine",
        metavar="SCHEMA_FILE",
        help="개선할 기존 스키마 파일 경로",
    )
    parser.add_argument(
        "--feedback",
        help="스키마 개선을 위한 피드백 텍스트",
    )

    # 공통 옵션
    parser.add_argument(
        "--output",
        default="schema_proposal.yaml",
        help="출력 파일 경로 (default: schema_proposal.yaml)",
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

    # 인자 검증
    if args.refine:
        if not args.feedback:
            parser.error("--refine 옵션에는 --feedback이 필요합니다.")
    else:
        if not args.input:
            parser.error("--input 또는 --refine 중 하나는 필수입니다.")

    # 환경 변수 로드
    load_dotenv()

    # LLM Repository 초기화
    logger.info("LLM 연결 중...")
    settings = Settings()
    llm_repo = LLMRepository(settings)

    try:
        generator = SchemaGenerator(llm_repo)

        if args.refine:
            await refine_existing_schema(
                generator=generator,
                schema_path=args.refine,
                feedback=args.feedback,
                output_path=args.output,
            )
        else:
            await generate_new_schema(
                generator=generator,
                input_path=args.input,
                domain_hint=args.domain,
                output_path=args.output,
            )

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
