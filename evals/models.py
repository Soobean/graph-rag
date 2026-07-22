"""
Eval Harness 데이터 모델

GoldenCase(골든셋 케이스 정의)와 채점 결과 모델.
golden_set.yaml 로더 포함.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.yaml"


# ============================================
# 골든셋 정의
# ============================================


@dataclass(frozen=True)
class RefCheck:
    """reference oracle 결과와 파이프라인 결과의 대조 규칙 1건"""

    type: str  # key_set | answer_contains_top | count_match | numeric_close
    column: str | None = None  # key_set/answer_contains_top/numeric_close 대상 컬럼
    mode: str = "subset"  # key_set: exact | subset | jaccard
    tolerance: int = 0  # count_match 허용 오차
    rel_tol: float = 0.05  # numeric_close 상대 오차
    jaccard_min: float = 0.8  # key_set mode=jaccard 하한


@dataclass(frozen=True)
class Reference:
    """비순환 oracle — 사람이 작성·검증한 Cypher와 대조 규칙.

    큐레이션 규칙 (docs/EVALS.md):
    - 질문 + load_to_neo4j.py 스키마로부터 작성. 파이프라인 생성 Cypher 복사 금지.
    - 인원 집계는 Employee 중복 노드 때문에 반드시 e.name 기준 DISTINCT/그룹.
    - --verify-refs로 행수·샘플을 육안 확인한 뒤 verified에 날짜 기록.
    """

    cypher: str
    checks: tuple[RefCheck, ...]
    verified: str | None = None


@dataclass(frozen=True)
class Tier1Checks:
    """경량 채점 — reference 작성이 비싼 문항용"""

    count_min: int | None = None
    count_max: int | None = None
    must_include_any: tuple[str, ...] = ()  # 응답 텍스트에 최소 1개 포함


@dataclass(frozen=True)
class GoldenCase:
    """골든셋 케이스 1건"""

    id: str
    question: str
    category: str
    expected_intent: tuple[str, ...]  # 허용 리스트 (intent 경계 모호성 흡수)
    require_execution: bool = True  # tier0: error 없음 + graph_executor 통과
    not_empty: bool = True  # tier0: result_count >= 1
    tier1: Tier1Checks | None = None
    reference: Reference | None = None
    judge: bool = False  # --judge 시 faithfulness 채점 대상


# ============================================
# 채점 결과
# ============================================


@dataclass
class CheckResult:
    """개별 체크 1건의 결과"""

    name: str  # intent_match | execution_ok | not_empty | count_range | ...
    passed: bool
    detail: str = ""  # 실패 시 기대/실제 요약


@dataclass
class JudgeResult:
    """LLM faithfulness judge 결과"""

    faithful: bool
    score: float  # 0.0 ~ 1.0
    violations: list[dict[str, str]] = field(default_factory=list)


@dataclass
class CaseResult:
    """케이스 1건의 종합 결과"""

    case_id: str
    category: str
    passed: bool  # tier0 + tier1 + reference 전부 AND (judge는 별도 축)
    checks: list[CheckResult] = field(default_factory=list)
    judge_result: JudgeResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalReport:
    """실행 1회의 전체 리포트"""

    timestamp: str
    total: int
    passed: int
    case_results: list[CaseResult] = field(default_factory=list)
    category_pass_rate: dict[str, str] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "category_pass_rate": self.category_pass_rate,
            "cases": [c.to_dict() for c in self.case_results],
        }


# ============================================
# golden_set.yaml 로더
# ============================================


def _parse_tier1(raw: dict[str, Any] | None) -> Tier1Checks | None:
    if not raw:
        return None
    count_range = raw.get("count_range") or {}
    return Tier1Checks(
        count_min=count_range.get("min"),
        count_max=count_range.get("max"),
        must_include_any=tuple(raw.get("must_include_any", ())),
    )


def _parse_reference(raw: dict[str, Any] | None) -> Reference | None:
    if not raw:
        return None
    checks = tuple(
        RefCheck(
            type=c["type"],
            column=c.get("column"),
            mode=c.get("mode", "subset"),
            tolerance=c.get("tolerance", 0),
            rel_tol=c.get("rel_tol", 0.05),
            jaccard_min=c.get("jaccard_min", 0.8),
        )
        for c in raw.get("checks", ())
    )
    return Reference(
        cypher=raw["cypher"],
        checks=checks,
        verified=raw.get("verified"),
    )


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[GoldenCase]:
    """golden_set.yaml을 GoldenCase 리스트로 로드"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cases: list[GoldenCase] = []
    for raw in data["cases"]:
        cases.append(
            GoldenCase(
                id=raw["id"],
                question=raw["question"],
                category=raw["category"],
                expected_intent=tuple(raw["expected_intent"]),
                require_execution=raw.get("require_execution", True),
                not_empty=raw.get("not_empty", True),
                tier1=_parse_tier1(raw.get("tier1")),
                reference=_parse_reference(raw.get("reference")),
                judge=raw.get("judge", False),
            )
        )

    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("golden_set.yaml: 중복된 case id가 있습니다")
    return cases
