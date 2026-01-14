#!/usr/bin/env python3
"""
Ontology Effectiveness Evaluator

온톨로지 시스템의 검색 성능 개선 효과를 측정합니다.
- 동의어 확장 효과 (Synonym Expansion)
- 계층 확장 효과 (Hierarchy Expansion)
- Recall, Zero-result rate 측정

Usage:
    python scripts/evaluate_ontology.py
    python scripts/evaluate_ontology.py --verbose
"""

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.ontology.loader import (
    ExpansionStrategy,
    OntologyLoader,
    get_config_for_strategy,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# 테스트 케이스 정의
# =============================================================================

@dataclass
class TestCase:
    """테스트 케이스"""
    query_term: str           # 검색어 (한글 또는 비표준)
    category: str             # skills, positions, departments
    expected_canonical: str   # 기대되는 정규화된 이름
    description: str = ""     # 테스트 설명


# 동의어 테스트 케이스 (한글 → 영문 변환)
SYNONYM_TEST_CASES = [
    # 프로그래밍 언어
    TestCase("파이썬", "skills", "Python", "한글 → 영문 변환"),
    TestCase("Python3", "skills", "Python", "버전 표기 정규화"),
    TestCase("Py", "skills", "Python", "축약형 확장"),
    TestCase("자바", "skills", "Java", "한글 → 영문 변환"),
    TestCase("자바스크립트", "skills", "JavaScript", "한글 → 영문 변환"),
    TestCase("JS", "skills", "JavaScript", "축약형 확장"),
    TestCase("타입스크립트", "skills", "TypeScript", "한글 → 영문 변환"),
    TestCase("고랭", "skills", "Go", "한글 → 영문 변환"),

    # AI/ML
    TestCase("머신러닝", "skills", "ML", "한글 → 영문 변환"),
    TestCase("딥러닝", "skills", "Deep Learning", "한글 → 영문 변환"),
    TestCase("자연어처리", "skills", "NLP", "한글 → 영문 변환"),
    TestCase("텐서플로우", "skills", "TensorFlow", "한글 → 영문 변환"),
    TestCase("파이토치", "skills", "PyTorch", "한글 → 영문 변환"),

    # 클라우드/인프라
    TestCase("도커", "skills", "Docker", "한글 → 영문 변환"),
    TestCase("쿠버네티스", "skills", "Kubernetes", "한글 → 영문 변환"),
    TestCase("K8s", "skills", "Kubernetes", "축약형 확장"),
    TestCase("아마존 웹 서비스", "skills", "AWS", "전체 이름 → 축약"),
    TestCase("구글 클라우드", "skills", "GCP", "전체 이름 → 축약"),

    # 프레임워크
    TestCase("리액트", "skills", "React", "한글 → 영문 변환"),
    TestCase("스프링", "skills", "Spring", "한글 → 영문 변환"),

    # 직급
    TestCase("Backend Developer", "positions", "Backend Developer", "영문 직급"),
    TestCase("서버 개발자", "positions", "Backend Developer", "한글 직급 변환"),
    TestCase("ML Engineer", "positions", "ML Engineer", "영문 직급"),

    # 부서
    TestCase("Engineering", "departments", "Engineering", "영문 부서"),
    TestCase("개발팀", "departments", "Engineering", "한글 부서 변환"),
]


# =============================================================================
# 평가 결과
# =============================================================================

@dataclass
class EvaluationResult:
    """개별 테스트 결과"""
    test_case: TestCase
    expanded_terms: list[str]
    found_canonical: bool
    expansion_count: int


@dataclass
class EvaluationReport:
    """평가 리포트"""
    results: list[EvaluationResult] = field(default_factory=list)

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def successful_tests(self) -> int:
        return sum(1 for r in self.results if r.found_canonical)

    @property
    def recall(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return self.successful_tests / self.total_tests

    @property
    def zero_result_rate_without_ontology(self) -> float:
        """온톨로지 없이 검색했을 때 결과 0건 비율"""
        # 원본 검색어와 expected_canonical이 다른 경우를 zero-result로 가정
        zero_results = sum(
            1 for r in self.results
            if r.test_case.query_term.lower() != r.test_case.expected_canonical.lower()
        )
        return zero_results / self.total_tests if self.total_tests > 0 else 0.0

    @property
    def zero_result_rate_with_ontology(self) -> float:
        """온톨로지로 검색했을 때 결과 0건 비율"""
        zero_results = sum(1 for r in self.results if not r.found_canonical)
        return zero_results / self.total_tests if self.total_tests > 0 else 0.0

    @property
    def avg_expansion_count(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return sum(r.expansion_count for r in self.results) / self.total_tests


# =============================================================================
# 평가기
# =============================================================================

class OntologyEvaluator:
    """온톨로지 효과 평가기"""

    def __init__(self, ontology_dir: Path | str | None = None):
        self._loader = OntologyLoader(ontology_dir)

    def evaluate_synonym_expansion(
        self,
        test_cases: list[TestCase] | None = None,
        strategy: ExpansionStrategy = ExpansionStrategy.NORMAL,
    ) -> EvaluationReport:
        """동의어 확장 효과 평가"""
        if test_cases is None:
            test_cases = SYNONYM_TEST_CASES

        config = get_config_for_strategy(strategy)
        report = EvaluationReport()

        for tc in test_cases:
            # 온톨로지로 확장
            expanded = self._loader.expand_concept(tc.query_term, tc.category, config)

            # canonical이 확장 결과에 포함되는지 확인
            found = any(
                term.lower() == tc.expected_canonical.lower()
                for term in expanded
            )

            result = EvaluationResult(
                test_case=tc,
                expanded_terms=expanded,
                found_canonical=found,
                expansion_count=len(expanded),
            )
            report.results.append(result)

        return report

    def print_report(self, report: EvaluationReport, verbose: bool = False) -> None:
        """평가 결과 출력"""
        print("\n" + "=" * 70)
        print("📊 온톨로지 효과 측정 리포트")
        print("=" * 70)

        # 개별 결과 (verbose 모드)
        if verbose:
            print("\n📋 개별 테스트 결과:")
            print("-" * 70)
            for r in report.results:
                status = "✅" if r.found_canonical else "❌"
                print(f"  {status} '{r.test_case.query_term}' → '{r.test_case.expected_canonical}'")
                print(f"     확장 결과 ({r.expansion_count}개): {r.expanded_terms[:5]}...")
                if not r.found_canonical:
                    print(f"     ⚠️  Expected '{r.test_case.expected_canonical}' not found!")
                print()

        # 요약 통계
        print("\n📈 요약 통계:")
        print("-" * 70)
        print(f"  총 테스트 수: {report.total_tests}")
        print(f"  성공 테스트 수: {report.successful_tests}")
        print(f"  평균 확장 개수: {report.avg_expansion_count:.1f}")

        # 핵심 메트릭
        print("\n🎯 핵심 메트릭:")
        print("-" * 70)

        # 테이블 형식으로 출력
        print(f"  {'메트릭':<35} {'값':>10}")
        print(f"  {'-' * 35} {'-' * 10}")
        print(f"  {'Recall (온톨로지 ON)':<35} {report.recall:>9.1%}")
        print(f"  {'Zero-result Rate (온톨로지 OFF)':<35} {report.zero_result_rate_without_ontology:>9.1%}")
        print(f"  {'Zero-result Rate (온톨로지 ON)':<35} {report.zero_result_rate_with_ontology:>9.1%}")

        # 개선 효과 계산
        zero_result_reduction = (
            (report.zero_result_rate_without_ontology - report.zero_result_rate_with_ontology)
            / max(report.zero_result_rate_without_ontology, 0.01) * 100
        )

        # Recall 개선율 (온톨로지 없을 때 vs 있을 때)
        baseline_recall = 1 - report.zero_result_rate_without_ontology
        recall_improvement = (
            (report.recall - baseline_recall) / max(baseline_recall, 0.01) * 100
            if baseline_recall > 0 else float("inf")
        )

        # 개선 효과
        print("\n🚀 개선 효과:")
        print("-" * 70)
        print(f"  ✨ Zero-result Rate 감소: {zero_result_reduction:.1f}%")
        if recall_improvement != float("inf"):
            print(f"  ✨ Recall 개선율: +{recall_improvement:.1f}%")
        else:
            print("  ✨ Recall 개선율: ∞ (기존 검색 불가 → 검색 가능)")

        if report.recall >= 0.9:
            print("  🎉 온톨로지 시스템이 매우 효과적으로 작동합니다!")
        elif report.recall >= 0.7:
            print("  👍 온톨로지 시스템이 효과적으로 작동합니다.")
        else:
            print("  ⚠️  온톨로지 커버리지를 개선해야 합니다.")

        # 실패 케이스
        failed = [r for r in report.results if not r.found_canonical]
        if failed:
            print(f"\n❌ 실패 케이스 ({len(failed)}건):")
            print("-" * 70)
            for r in failed:
                print(f"  - '{r.test_case.query_term}' → expected '{r.test_case.expected_canonical}'")
                print(f"    확장 결과: {r.expanded_terms}")

        print("\n" + "=" * 70)


# =============================================================================
# 메인
# =============================================================================

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="온톨로지 효과 측정")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 결과 출력",
    )
    parser.add_argument(
        "--strategy",
        choices=["strict", "normal", "broad"],
        default="normal",
        help="확장 전략 (기본값: normal)",
    )
    args = parser.parse_args()

    strategy_map = {
        "strict": ExpansionStrategy.STRICT,
        "normal": ExpansionStrategy.NORMAL,
        "broad": ExpansionStrategy.BROAD,
    }

    print("🔍 온톨로지 효과 측정 시작...")
    print(f"   전략: {args.strategy.upper()}")

    evaluator = OntologyEvaluator()
    report = evaluator.evaluate_synonym_expansion(
        strategy=strategy_map[args.strategy]
    )
    evaluator.print_report(report, verbose=args.verbose)

    # 결과를 JSON으로도 저장
    output_path = Path(__file__).parent.parent / "output" / "ontology_evaluation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import json
    result_data = {
        "strategy": args.strategy,
        "total_tests": report.total_tests,
        "successful_tests": report.successful_tests,
        "recall": report.recall,
        "zero_result_rate_without_ontology": report.zero_result_rate_without_ontology,
        "zero_result_rate_with_ontology": report.zero_result_rate_with_ontology,
        "avg_expansion_count": report.avg_expansion_count,
        "failed_cases": [
            {
                "query": r.test_case.query_term,
                "expected": r.test_case.expected_canonical,
                "expanded": r.expanded_terms,
            }
            for r in report.results if not r.found_canonical
        ],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"\n📁 결과 저장됨: {output_path}")

    return 0 if report.recall >= 0.7 else 1


if __name__ == "__main__":
    sys.exit(main())
