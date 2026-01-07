"""
Ingestion Pipeline 실제 테스트

CSV 파일을 읽어서 LLM으로 그래프를 추출하고 Neo4j에 저장하는 전체 파이프라인 테스트
"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.loaders.csv_loader import CSVLoader
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.models import generate_entity_id


async def test_csv_loader():
    """CSVLoader 테스트"""
    print("=" * 60)
    print("1. CSVLoader 테스트")
    print("=" * 60)

    csv_path = Path(__file__).parent.parent / "data/company_realistic/employees.csv"
    loader = CSVLoader(csv_path)

    count = 0
    for doc in loader.load():
        count += 1
        if count <= 3:  # 처음 3개만 출력
            print(f"\n[Document {count}]")
            print(f"  Content: {doc.page_content[:100]}...")
            print(f"  Metadata: {doc.metadata}")

    print(f"\n총 {count}개 Document 로드 완료")
    return count


def test_uuid_generation():
    """UUID 생성 테스트"""
    print("\n" + "=" * 60)
    print("2. UUID 생성 테스트")
    print("=" * 60)

    # 같은 입력 → 같은 UUID
    uuid1 = generate_entity_id("Employee", {"email": "emp0001@techstar.com", "name": "윤서준"})
    uuid2 = generate_entity_id("Employee", {"email": "emp0001@techstar.com", "name": "윤서준"})

    print(f"\n같은 입력:")
    print(f"  UUID1: {uuid1}")
    print(f"  UUID2: {uuid2}")
    print(f"  동일 여부: {uuid1 == uuid2} ✓" if uuid1 == uuid2 else "  동일 여부: False ✗")

    # 다른 이메일 → 다른 UUID
    uuid3 = generate_entity_id("Employee", {"email": "emp0002@techstar.com", "name": "성하준"})
    print(f"\n다른 입력:")
    print(f"  UUID1: {uuid1}")
    print(f"  UUID3: {uuid3}")
    print(f"  다른 여부: {uuid1 != uuid3} ✓" if uuid1 != uuid3 else "  다른 여부: False ✗")


async def test_full_pipeline(limit: int = 3):
    """전체 파이프라인 테스트 (LLM + Neo4j)"""
    print("\n" + "=" * 60)
    print("3. 전체 파이프라인 테스트 (LLM + Neo4j)")
    print("=" * 60)

    csv_path = Path(__file__).parent.parent / "data/company_realistic/employees.csv"

    # 제한된 수의 Document만 처리하는 커스텀 로더
    class LimitedCSVLoader(CSVLoader):
        def __init__(self, file_path, limit: int):
            super().__init__(file_path)
            self._limit = limit

        def load(self):
            count = 0
            for doc in super().load():
                if count >= self._limit:
                    break
                yield doc
                count += 1

    loader = LimitedCSVLoader(csv_path, limit=limit)
    pipeline = IngestionPipeline(batch_size=10, concurrency=2)

    print(f"\n{limit}개 Document 처리 시작...")
    print("(LLM 호출 및 Neo4j 저장 진행 중...)")

    try:
        stats = await pipeline.run(loader)
        print(f"\n✅ 처리 완료!")
        print(f"  - 총 노드: {stats['total_nodes']}")
        print(f"  - 총 엣지: {stats['total_edges']}")
        print(f"  - 실패 문서: {stats['failed_docs']}")
        return stats
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    print("\n🚀 Ingestion Pipeline 실제 테스트 시작\n")

    # 1. CSVLoader 테스트
    await test_csv_loader()

    # 2. UUID 생성 테스트
    test_uuid_generation()

    # 3. 전체 파이프라인 테스트 (선택적)
    print("\n" + "-" * 60)
    user_input = input("\n전체 파이프라인 테스트를 실행하시겠습니까? (LLM + Neo4j 필요) [y/N]: ")

    if user_input.lower() == 'y':
        limit = input("처리할 Document 수 (기본: 3): ").strip()
        limit = int(limit) if limit.isdigit() else 3
        await test_full_pipeline(limit=limit)
    else:
        print("\n파이프라인 테스트를 건너뜁니다.")

    print("\n✅ 테스트 완료!")


if __name__ == "__main__":
    asyncio.run(main())
