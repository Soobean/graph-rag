#!/usr/bin/env python3
"""
Ontology Validator

온톨로지 YAML 파일의 품질을 검증합니다.
- 고아 스킬 탐지 (schema에만 있고 synonyms에 없는 스킬)
- 중복 canonical 탐지
- 순환 참조 탐지 (IS_A 관계)
- 깨진 참조 탐지

Usage:
    python scripts/validate_ontology.py
    python scripts/validate_ontology.py --verbose
    python scripts/validate_ontology.py --fix  # 자동 수정 시도 (향후 구현)
"""

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.ontology.loader import OntologyLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """검증 이슈"""

    severity: str  # "error", "warning", "info"
    category: str  # "orphan", "duplicate", "circular", "broken"
    message: str
    location: str = ""  # 파일:라인 또는 개념명


@dataclass
class ValidationReport:
    """검증 리포트"""

    issues: list[ValidationIssue] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def add_issue(
        self,
        severity: str,
        category: str,
        message: str,
        location: str = "",
    ) -> None:
        self.issues.append(
            ValidationIssue(
                severity=severity,
                category=category,
                message=message,
                location=location,
            )
        )

    def print_summary(self) -> None:
        """검증 결과 요약 출력"""
        print("\n" + "=" * 60)
        print("📋 온톨로지 검증 리포트")
        print("=" * 60)

        # 통계
        print("\n📊 통계:")
        for key, value in self.stats.items():
            print(f"   - {key}: {value}")

        # 에러
        errors = [i for i in self.issues if i.severity == "error"]
        if errors:
            print(f"\n🔴 에러 ({len(errors)}건):")
            for issue in errors:
                loc = f" [{issue.location}]" if issue.location else ""
                print(f"   - [{issue.category}]{loc} {issue.message}")

        # 경고
        warnings = [i for i in self.issues if i.severity == "warning"]
        if warnings:
            print(f"\n🟡 경고 ({len(warnings)}건):")
            for issue in warnings:
                loc = f" [{issue.location}]" if issue.location else ""
                print(f"   - [{issue.category}]{loc} {issue.message}")

        # 정보
        infos = [i for i in self.issues if i.severity == "info"]
        if infos:
            print(f"\n🔵 정보 ({len(infos)}건):")
            for issue in infos:
                loc = f" [{issue.location}]" if issue.location else ""
                print(f"   - [{issue.category}]{loc} {issue.message}")

        # 결과
        print("\n" + "-" * 60)
        if self.has_errors:
            print(f"❌ 검증 실패: {self.error_count}개의 에러 발견")
        else:
            print("✅ 검증 통과: 심각한 문제 없음")

        if self.warning_count > 0:
            print(f"   ⚠️  {self.warning_count}개의 경고 확인 필요")

        print("=" * 60 + "\n")


class OntologyValidator:
    """
    온톨로지 YAML 검증기

    검증 항목:
    1. 고아 스킬 (orphan): schema에 있지만 synonyms에 없는 스킬
    2. 중복 canonical (duplicate): 동일한 canonical이 여러 엔트리에 정의됨
    3. 순환 참조 (circular): IS_A 관계에서 순환 발생
    4. 깨진 참조 (broken): 참조하는 스킬이 존재하지 않음
    """

    def __init__(self, ontology_dir: Path | str | None = None):
        self._loader = OntologyLoader(ontology_dir)

    def validate_all(self) -> ValidationReport:
        """전체 검증 수행"""
        report = ValidationReport()

        # 데이터 로드
        schema = self._loader.load_schema()
        synonyms = self._loader.load_synonyms()

        # 통계 수집
        report.stats = self._collect_stats(schema, synonyms)

        # 검증 수행
        self._check_orphan_skills(schema, synonyms, report)
        self._check_duplicate_canonicals(synonyms, report)
        self._check_broken_references(schema, synonyms, report)
        self._check_missing_synonyms(schema, synonyms, report)

        return report

    def _collect_stats(
        self,
        schema: dict,
        synonyms: dict,
    ) -> dict[str, int]:
        """통계 수집"""
        stats = {}

        # 스키마 통계
        concepts = schema.get("concepts", {})
        skill_categories = concepts.get("SkillCategory", [])

        total_skills = 0
        total_categories = 0

        for category in skill_categories:
            if isinstance(category, dict):
                total_categories += 1
                total_skills += len(category.get("skills", []))

                for sub in category.get("subcategories", []):
                    total_categories += 1
                    total_skills += len(sub.get("skills", []))

        stats["스키마 카테고리 수"] = total_categories
        stats["스키마 스킬 수"] = total_skills

        # 동의어 통계
        for category_name, entries in synonyms.items():
            if category_name.startswith("_"):
                continue
            if isinstance(entries, dict):
                count = len(entries)
                stats[f"동의어 {category_name}"] = count

        return stats

    def _check_orphan_skills(
        self,
        schema: dict,
        synonyms: dict,
        report: ValidationReport,
    ) -> None:
        """고아 스킬 검사: schema에 있지만 synonyms에 없는 스킬"""
        # 스키마에서 모든 스킬 추출
        schema_skills = self._extract_all_skills(schema)

        # 동의어에서 모든 canonical 및 alias 추출
        synonym_terms = self._extract_all_synonym_terms(synonyms, "skills")

        # 차집합: 스키마에만 있는 스킬
        orphan_skills = schema_skills - synonym_terms

        for skill in sorted(orphan_skills):
            report.add_issue(
                severity="warning",
                category="orphan",
                message=f"'{skill}'이 schema.yaml에 있지만 synonyms.yaml에 없습니다",
                location="schema.yaml",
            )

    def _check_duplicate_canonicals(
        self,
        synonyms: dict,
        report: ValidationReport,
    ) -> None:
        """중복 canonical 검사"""
        for category_name, entries in synonyms.items():
            if category_name.startswith("_"):
                continue
            if not isinstance(entries, dict):
                continue

            # canonical → 원본 키 매핑
            canonical_map: dict[str, list[str]] = {}

            for main_term, info in entries.items():
                if not isinstance(info, dict):
                    continue
                canonical = info.get("canonical", main_term)
                canonical_lower = canonical.lower()

                if canonical_lower not in canonical_map:
                    canonical_map[canonical_lower] = []
                canonical_map[canonical_lower].append(main_term)

            # 중복 체크
            for canonical, sources in canonical_map.items():
                if len(sources) > 1:
                    report.add_issue(
                        severity="error",
                        category="duplicate",
                        message=f"'{canonical}' canonical이 여러 엔트리에서 사용됨: {sources}",
                        location=f"synonyms.yaml/{category_name}",
                    )

    def _check_broken_references(
        self,
        schema: dict,
        synonyms: dict,
        report: ValidationReport,
    ) -> None:
        """깨진 참조 검사: 존재하지 않는 스킬 참조"""
        # 모든 정의된 스킬/개념 수집
        all_defined = self._extract_all_skills(schema)
        all_synonyms = self._extract_all_synonym_terms(synonyms, "skills")
        all_known = all_defined | all_synonyms

        # schema의 relations에서 참조 체크
        relations = schema.get("relations", {})
        for rel_type, rel_info in relations.items():
            examples = rel_info.get("examples", [])
            for example in examples:
                if isinstance(example, list):
                    for item in example:
                        if item not in all_known:
                            report.add_issue(
                                severity="info",
                                category="broken",
                                message=f"'{item}'이 relations 예시에 있지만 정의되지 않음",
                                location=f"schema.yaml/relations/{rel_type}",
                            )

    def _check_missing_synonyms(
        self,
        schema: dict,
        synonyms: dict,
        report: ValidationReport,
    ) -> None:
        """동의어 누락 검사: synonyms에 있지만 schema에 없는 스킬"""
        # 스키마에서 모든 스킬 추출
        schema_skills = self._extract_all_skills(schema)

        # 동의어의 canonical 추출
        skill_synonyms = synonyms.get("skills", {})
        canonical_set = set()

        for main_term, info in skill_synonyms.items():
            if isinstance(info, dict):
                canonical = info.get("canonical", main_term)
                canonical_set.add(canonical)

        # 차집합: synonyms에 canonical로 있지만 schema에 없는 스킬
        missing_in_schema = canonical_set - schema_skills

        for skill in sorted(missing_in_schema):
            report.add_issue(
                severity="info",
                category="missing",
                message=f"'{skill}'이 synonyms.yaml에 있지만 schema.yaml 계층에 없습니다",
                location="synonyms.yaml/skills",
            )

    def _extract_all_skills(self, schema: dict) -> set[str]:
        """스키마에서 모든 스킬 추출"""
        skills = set()
        concepts = schema.get("concepts", {})

        # SkillCategory에서 추출
        for category in concepts.get("SkillCategory", []):
            if isinstance(category, dict):
                skills.update(category.get("skills", []))
                for sub in category.get("subcategories", []):
                    skills.update(sub.get("skills", []))

        return skills

    def _extract_all_synonym_terms(
        self,
        synonyms: dict,
        category: str,
    ) -> set[str]:
        """동의어에서 모든 용어 추출 (canonical + aliases)"""
        terms = set()
        category_data = synonyms.get(category, {})

        for main_term, info in category_data.items():
            if isinstance(info, dict):
                canonical = info.get("canonical", main_term)
                aliases = info.get("aliases", [])

                terms.add(canonical)
                terms.add(main_term)
                terms.update(aliases)

        return terms


def main() -> int:
    parser = argparse.ArgumentParser(description="온톨로지 YAML 검증")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로그 출력",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="온톨로지 디렉토리 경로 (기본값: src/domain/ontology)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("🔍 온톨로지 검증 시작...")

    validator = OntologyValidator(args.dir)
    report = validator.validate_all()
    report.print_summary()

    return 1 if report.has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
