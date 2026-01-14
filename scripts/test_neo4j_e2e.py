#!/usr/bin/env python3
"""
Neo4j End-to-End 테스트

실제 Neo4j 데이터베이스에서 온톨로지 확장 효과를 측정합니다.
- 연결 상태 확인
- 데이터 현황 조회
- 온톨로지 확장 유/무에 따른 검색 결과 비교

Usage:
    python scripts/test_neo4j_e2e.py
    python scripts/test_neo4j_e2e.py --verbose
"""

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.domain.ontology.loader import (
    ExpansionStrategy,
    OntologyLoader,
    get_config_for_strategy,
)
from src.infrastructure.neo4j_client import Neo4jClient

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# 테스트 케이스 정의
# =============================================================================

@dataclass
class QueryTestCase:
    """쿼리 테스트 케이스"""
    name: str                    # 테스트 이름
    description: str             # 테스트 설명
    search_terms: list[str]      # 검색어 (한글 또는 비표준)
    entity_type: str             # 엔티티 타입 (Skill, Position, Department)
    ontology_category: str       # 온톨로지 카테고리


# 테스트 케이스 정의
QUERY_TEST_CASES = [
    # 스킬 검색 테스트
    QueryTestCase(
        name="python_skill_search",
        description="파이썬 스킬 검색 (한글 → 영문 변환)",
        search_terms=["파이썬"],
        entity_type="Skill",
        ontology_category="skills",
    ),
    QueryTestCase(
        name="js_abbreviation_search",
        description="JS 축약형 검색 (JS → JavaScript)",
        search_terms=["JS"],
        entity_type="Skill",
        ontology_category="skills",
    ),
    QueryTestCase(
        name="k8s_search",
        description="K8s 축약형 검색 (K8s → Kubernetes)",
        search_terms=["K8s"],
        entity_type="Skill",
        ontology_category="skills",
    ),
    QueryTestCase(
        name="ml_korean_search",
        description="머신러닝 한글 검색",
        search_terms=["머신러닝"],
        entity_type="Skill",
        ontology_category="skills",
    ),
    QueryTestCase(
        name="docker_korean_search",
        description="도커 한글 검색",
        search_terms=["도커"],
        entity_type="Skill",
        ontology_category="skills",
    ),

    # 직급 검색 테스트
    QueryTestCase(
        name="backend_position_search",
        description="서버 개발자 검색 (한글 → Backend Developer)",
        search_terms=["서버 개발자"],
        entity_type="Position",
        ontology_category="positions",
    ),

    # 부서 검색 테스트
    QueryTestCase(
        name="engineering_dept_search",
        description="개발팀 검색 (한글 → Engineering)",
        search_terms=["개발팀"],
        entity_type="Department",
        ontology_category="departments",
    ),
]


# =============================================================================
# 테스트 결과
# =============================================================================

@dataclass
class QueryTestResult:
    """개별 테스트 결과"""
    test_case: QueryTestCase
    original_count: int          # 원본 검색어로 검색한 결과 수
    expanded_count: int          # 확장된 검색어로 검색한 결과 수
    expanded_terms: list[str]    # 확장된 검색어 목록
    improvement_rate: float      # 개선율 (%)
    sample_results: list[dict]   # 샘플 결과


@dataclass
class E2ETestReport:
    """E2E 테스트 리포트"""
    results: list[QueryTestResult] = field(default_factory=list)
    connection_status: dict = field(default_factory=dict)
    data_stats: dict = field(default_factory=dict)

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def improved_tests(self) -> int:
        return sum(1 for r in self.results if r.expanded_count > r.original_count)

    @property
    def total_original_results(self) -> int:
        return sum(r.original_count for r in self.results)

    @property
    def total_expanded_results(self) -> int:
        return sum(r.expanded_count for r in self.results)


# =============================================================================
# E2E 테스터
# =============================================================================

class Neo4jE2ETester:
    """Neo4j E2E 테스터"""

    def __init__(self, client: Neo4jClient, ontology_loader: OntologyLoader):
        self._client = client
        self._ontology = ontology_loader

    async def check_connection(self) -> dict:
        """연결 상태 확인"""
        return await self._client.health_check()

    async def get_data_stats(self) -> dict:
        """데이터 현황 조회"""
        stats = {}

        # 노드 수 조회
        queries = {
            "employees": "MATCH (e:Employee) RETURN count(e) as count",
            "skills": "MATCH (s:Skill) RETURN count(s) as count",
            "positions": "MATCH (p:Position) RETURN count(p) as count",
            "departments": "MATCH (d:Department) RETURN count(d) as count",
            "employee_skills": "MATCH (:Employee)-[r:HAS_SKILL]->(:Skill) RETURN count(r) as count",
        }

        for name, query in queries.items():
            try:
                result = await self._client.execute_query(query)
                stats[name] = result[0]["count"] if result else 0
            except Exception as e:
                stats[name] = f"Error: {e}"
                logger.warning(f"Failed to get {name} count: {e}")

        return stats

    async def run_skill_search_count(
        self,
        search_terms: list[str],
    ) -> int:
        """스킬 기반 직원 검색 (COUNT 반환)"""
        # 대소문자 무시 검색을 위해 toLower 사용
        query = """
        MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill)
        WHERE toLower(s.name) IN $skills
        RETURN count(DISTINCT e) as count
        """
        lower_terms = [t.lower() for t in search_terms]
        try:
            result = await self._client.execute_query(query, {"skills": lower_terms})
            return result[0]["count"] if result else 0
        except Exception as e:
            logger.error(f"Skill search failed: {e}")
            return 0

    async def run_position_search_count(
        self,
        search_terms: list[str],
    ) -> int:
        """직급 기반 직원 검색 (COUNT 반환)"""
        query = """
        MATCH (e:Employee)-[:HAS_POSITION]->(p:Position)
        WHERE p.name IN $positions
        RETURN count(DISTINCT e) as count
        """
        try:
            result = await self._client.execute_query(query, {"positions": search_terms})
            return result[0]["count"] if result else 0
        except Exception as e:
            logger.error(f"Position search failed: {e}")
            return 0

    async def run_department_search_count(
        self,
        search_terms: list[str],
    ) -> int:
        """부서 기반 직원 검색 (COUNT 반환)"""
        query = """
        MATCH (e:Employee)-[:BELONGS_TO]->(d:Department)
        WHERE d.name IN $departments
        RETURN count(DISTINCT e) as count
        """
        try:
            result = await self._client.execute_query(query, {"departments": search_terms})
            return result[0]["count"] if result else 0
        except Exception as e:
            logger.error(f"Department search failed: {e}")
            return 0

    async def run_search_count(
        self,
        entity_type: str,
        search_terms: list[str],
    ) -> int:
        """엔티티 타입별 검색 라우팅 (COUNT 반환)"""
        if entity_type == "Skill":
            return await self.run_skill_search_count(search_terms)
        elif entity_type == "Position":
            return await self.run_position_search_count(search_terms)
        elif entity_type == "Department":
            return await self.run_department_search_count(search_terms)
        else:
            logger.warning(f"Unknown entity type: {entity_type}")
            return 0

    def expand_terms(
        self,
        terms: list[str],
        category: str,
        strategy: ExpansionStrategy = ExpansionStrategy.NORMAL,
    ) -> list[str]:
        """온톨로지를 통해 검색어 확장"""
        config = get_config_for_strategy(strategy)
        expanded = set()

        for term in terms:
            result = self._ontology.expand_concept(term, category, config)
            expanded.update(result)

        return list(expanded)

    async def run_test_case(self, test_case: QueryTestCase) -> QueryTestResult:
        """단일 테스트 케이스 실행"""
        logger.info(f"Running test: {test_case.name}")

        # 1. 원본 검색어로 검색 (COUNT)
        original_count = await self.run_search_count(
            test_case.entity_type,
            test_case.search_terms,
        )

        # 2. 온톨로지로 검색어 확장
        expanded_terms = self.expand_terms(
            test_case.search_terms,
            test_case.ontology_category,
        )

        # 3. 확장된 검색어로 검색 (COUNT)
        expanded_count = await self.run_search_count(
            test_case.entity_type,
            expanded_terms,
        )

        # 4. 개선율 계산
        if original_count == 0:
            improvement_rate = float("inf") if expanded_count > 0 else 0.0
        else:
            improvement_rate = ((expanded_count - original_count) / original_count) * 100

        return QueryTestResult(
            test_case=test_case,
            original_count=original_count,
            expanded_count=expanded_count,
            expanded_terms=expanded_terms,
            improvement_rate=improvement_rate,
            sample_results=[],  # COUNT 기반이므로 샘플 없음
        )

    async def run_all_tests(
        self,
        test_cases: list[QueryTestCase] | None = None,
    ) -> E2ETestReport:
        """모든 테스트 실행"""
        if test_cases is None:
            test_cases = QUERY_TEST_CASES

        report = E2ETestReport()

        # 연결 상태 확인
        report.connection_status = await self.check_connection()
        if not report.connection_status.get("connected"):
            logger.error("Neo4j connection failed. Aborting tests.")
            return report

        # 데이터 현황 조회
        report.data_stats = await self.get_data_stats()

        # 테스트 실행
        for test_case in test_cases:
            try:
                result = await self.run_test_case(test_case)
                report.results.append(result)
            except Exception as e:
                logger.error(f"Test {test_case.name} failed: {e}")

        return report


# =============================================================================
# 리포트 출력
# =============================================================================

def print_report(report: E2ETestReport, verbose: bool = False) -> None:
    """테스트 리포트 출력"""
    print("\n" + "=" * 70)
    print("🔗 Neo4j E2E 테스트 리포트")
    print("=" * 70)

    # 연결 상태
    print("\n📡 연결 상태:")
    print("-" * 70)
    conn = report.connection_status
    if conn.get("connected"):
        print(f"  ✅ 연결됨: {conn.get('uri')}")
        if conn.get("server_info"):
            info = conn["server_info"]
            print(f"     Agent: {info.get('agent')}")
            print(f"     Protocol: {info.get('protocol_version')}")
    else:
        print(f"  ❌ 연결 실패: {conn.get('error')}")
        return

    # 데이터 현황
    print("\n📊 데이터 현황:")
    print("-" * 70)
    for name, count in report.data_stats.items():
        print(f"  {name}: {count}")

    # 테스트 결과
    print("\n🧪 테스트 결과:")
    print("-" * 70)

    for r in report.results:
        status = "✅" if r.expanded_count > r.original_count else "➖"
        if r.original_count == 0 and r.expanded_count > 0:
            status = "🎯"  # Zero-result 해결

        print(f"\n  {status} {r.test_case.name}")
        print(f"     설명: {r.test_case.description}")
        print(f"     원본 검색어: {r.test_case.search_terms}")
        print(f"     확장된 검색어: {r.expanded_terms}")
        print(f"     결과 수: {r.original_count} → {r.expanded_count}")

        if r.improvement_rate == float("inf"):
            print("     📈 개선: ∞ (Zero-result → 결과 있음)")
        elif r.improvement_rate > 0:
            print(f"     📈 개선: +{r.improvement_rate:.1f}%")
        elif r.improvement_rate < 0:
            print(f"     📉 감소: {r.improvement_rate:.1f}%")
        else:
            print("     ➖ 변화 없음")

        if verbose and r.sample_results:
            print("     샘플 결과:")
            for sample in r.sample_results[:2]:
                print(f"       - {sample}")

    # 요약
    print("\n" + "=" * 70)
    print("📈 요약:")
    print("-" * 70)
    print(f"  총 테스트: {report.total_tests}")
    print(f"  개선된 테스트: {report.improved_tests}")
    print(f"  총 원본 결과 수: {report.total_original_results}")
    print(f"  총 확장 결과 수: {report.total_expanded_results}")

    if report.total_original_results > 0:
        overall_improvement = (
            (report.total_expanded_results - report.total_original_results)
            / report.total_original_results * 100
        )
        print(f"  전체 개선율: {overall_improvement:+.1f}%")

    # Zero-result 해결 건수
    zero_resolved = sum(
        1 for r in report.results
        if r.original_count == 0 and r.expanded_count > 0
    )
    if zero_resolved > 0:
        print(f"  🎯 Zero-result 해결: {zero_resolved}건")

    print("=" * 70)


# =============================================================================
# 메인
# =============================================================================

async def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Neo4j E2E 테스트")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 결과 출력",
    )
    args = parser.parse_args()

    print("🔍 Neo4j E2E 테스트 시작...")

    # 설정 로드
    settings = get_settings()
    print(f"   Neo4j URI: {settings.neo4j_uri}")
    print(f"   Database: {settings.neo4j_database}")

    # 온톨로지 로더 초기화
    ontology = OntologyLoader()

    # Neo4j 클라이언트 초기화 및 테스트 실행
    async with Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    ) as client:
        tester = Neo4jE2ETester(client, ontology)
        report = await tester.run_all_tests()

    print_report(report, verbose=args.verbose)

    # 결과 JSON 저장
    output_path = Path(__file__).parent.parent / "output" / "neo4j_e2e_test.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import json
    result_data = {
        "connection_status": report.connection_status,
        "data_stats": report.data_stats,
        "total_tests": report.total_tests,
        "improved_tests": report.improved_tests,
        "total_original_results": report.total_original_results,
        "total_expanded_results": report.total_expanded_results,
        "test_results": [
            {
                "name": r.test_case.name,
                "description": r.test_case.description,
                "search_terms": r.test_case.search_terms,
                "expanded_terms": r.expanded_terms,
                "original_count": r.original_count,
                "expanded_count": r.expanded_count,
                "improvement_rate": r.improvement_rate if r.improvement_rate != float("inf") else "infinity",
            }
            for r in report.results
        ],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"\n📁 결과 저장됨: {output_path}")

    # 연결 실패 시 1 반환
    if not report.connection_status.get("connected"):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
