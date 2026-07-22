"""
결정적 채점기 (순수 함수)

라이브 의존(Neo4j/LLM) 없음 — tests/evals/test_graders.py에서 pytest로 검증된다.
채점기 자체는 파이프라인 코드와 무관하므로 순환성이 없다.
"""

from __future__ import annotations

import re
from typing import Any

from evals.models import CheckResult, GoldenCase, RefCheck, Tier1Checks

# ============================================
# 텍스트/값 정규화
# ============================================


def normalize_text(text: str) -> str:
    """비교용 정규화: 소문자화 + 숫자 천단위 콤마 제거"""
    lowered = text.lower()
    # 1,234,567 → 1234567 (숫자 사이 콤마만 제거)
    return re.sub(r"(?<=\d),(?=\d)", "", lowered)


def _collect_values(value: Any, out: set[str]) -> None:
    """중첩 구조(노드 dict, 리스트)에서 모든 스칼라 값을 문자열로 수집"""
    if isinstance(value, dict):
        for v in value.values():
            _collect_values(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect_values(v, out)
    elif value is not None:
        out.add(normalize_text(str(value)))


def flatten_values(rows: list[dict[str, Any]]) -> set[str]:
    """graph_results 행들을 평탄화한 소문자 문자열 값 집합.

    파이프라인 Cypher는 같은 답을 다른 행 모양(노드 vs 스칼라 컬럼)으로
    반환할 수 있으므로, 행 모양 비교 대신 값 집합으로 대조한다.
    """
    out: set[str] = set()
    for row in rows:
        _collect_values(row, out)
    return out


# ============================================
# tier0: 공통 채점
# ============================================


def grade_intent(expected: tuple[str, ...], actual: str) -> CheckResult:
    """intent가 허용 리스트에 포함되는가"""
    passed = actual in expected
    return CheckResult(
        name="intent_match",
        passed=passed,
        detail="" if passed else f"expected one of {list(expected)}, got '{actual}'",
    )


def grade_execution(
    metadata: dict[str, Any],
    *,
    require_execution: bool,
    not_empty: bool,
) -> list[CheckResult]:
    """tier0: 파이프라인이 에러 없이 Cypher를 실행했고 결과가 비어 있지 않은가"""
    results: list[CheckResult] = []

    if require_execution:
        error = metadata.get("error")
        path = metadata.get("execution_path", [])
        executed = any(p == "graph_executor" for p in path)
        passed = error is None and executed
        detail = ""
        if not passed:
            detail = f"error={error!r}, execution_path={path}"
        results.append(
            CheckResult(name="execution_ok", passed=passed, detail=detail)
        )

    if not_empty:
        count = metadata.get("result_count", 0)
        results.append(
            CheckResult(
                name="not_empty",
                passed=count >= 1,
                detail="" if count >= 1 else f"result_count={count}",
            )
        )

    return results


# ============================================
# tier1: 경량 채점
# ============================================


def grade_tier1(
    tier1: Tier1Checks,
    *,
    response: str,
    result_count: int,
) -> list[CheckResult]:
    """count_range + must_include_any"""
    results: list[CheckResult] = []

    if tier1.count_min is not None or tier1.count_max is not None:
        lo = tier1.count_min if tier1.count_min is not None else 0
        hi = tier1.count_max if tier1.count_max is not None else float("inf")
        passed = lo <= result_count <= hi
        results.append(
            CheckResult(
                name="count_range",
                passed=passed,
                detail=""
                if passed
                else f"result_count={result_count}, expected [{lo}, {hi}]",
            )
        )

    if tier1.must_include_any:
        norm_response = normalize_text(response)
        hit = any(
            normalize_text(term) in norm_response for term in tier1.must_include_any
        )
        results.append(
            CheckResult(
                name="must_include_any",
                passed=hit,
                detail=""
                if hit
                else f"none of {list(tier1.must_include_any)} found in response",
            )
        )

    return results


# ============================================
# reference oracle 채점
# ============================================


def _ref_column_values(ref_rows: list[dict[str, Any]], column: str) -> list[str]:
    """reference 결과에서 특정 컬럼 값들을 정규화 문자열로 추출"""
    values: list[str] = []
    for row in ref_rows:
        if column in row and row[column] is not None:
            values.append(normalize_text(str(row[column])))
    return values


def grade_reference(
    ref_rows: list[dict[str, Any]],
    checks: tuple[RefCheck, ...],
    *,
    graph_results: list[dict[str, Any]],
    response: str,
    result_count: int,
) -> list[CheckResult]:
    """reference oracle 결과와 파이프라인 결과를 의미 단위로 대조"""
    results: list[CheckResult] = []
    pipeline_values = flatten_values(graph_results)
    norm_response = normalize_text(response)

    for check in checks:
        if check.type == "key_set":
            assert check.column is not None, "key_set requires column"
            ref_keys = set(_ref_column_values(ref_rows, check.column))
            if not ref_keys:
                results.append(
                    CheckResult(
                        name=f"key_set:{check.column}",
                        passed=False,
                        detail="reference returned no keys",
                    )
                )
                continue
            if check.mode == "exact":
                # ref 키가 전부 있고, 파이프라인에 ref 밖 키가 있어도 무방하지 않음
                # (평탄화 집합엔 관계값 등 잡음이 섞이므로 exact는 ref ⊆ pipeline
                #  + 건수 일치로 근사)
                passed = ref_keys <= pipeline_values and len(ref_rows) == result_count
            elif check.mode == "jaccard":
                inter = len(ref_keys & pipeline_values)
                union = len(ref_keys | pipeline_values)
                passed = union > 0 and (inter / len(ref_keys)) >= check.jaccard_min
            else:  # subset (기본)
                passed = ref_keys <= pipeline_values
            missing = sorted(ref_keys - pipeline_values)[:5]
            results.append(
                CheckResult(
                    name=f"key_set:{check.column}",
                    passed=passed,
                    detail="" if passed else f"missing from pipeline: {missing}",
                )
            )

        elif check.type == "answer_contains_top":
            assert check.column is not None, "answer_contains_top requires column"
            top_values = _ref_column_values(ref_rows[:1], check.column)
            if not top_values:
                results.append(
                    CheckResult(
                        name=f"answer_contains_top:{check.column}",
                        passed=False,
                        detail="reference returned no rows",
                    )
                )
                continue
            top = top_values[0]
            passed = top in norm_response
            results.append(
                CheckResult(
                    name=f"answer_contains_top:{check.column}",
                    passed=passed,
                    detail="" if passed else f"top value '{top}' not in response",
                )
            )

        elif check.type == "count_match":
            ref_count = len(ref_rows)
            passed = abs(ref_count - result_count) <= check.tolerance
            results.append(
                CheckResult(
                    name="count_match",
                    passed=passed,
                    detail=""
                    if passed
                    else f"ref={ref_count}, pipeline={result_count}, "
                    f"tolerance={check.tolerance}",
                )
            )

        elif check.type == "numeric_close":
            assert check.column is not None, "numeric_close requires column"
            top_values = _ref_column_values(ref_rows[:1], check.column)
            if not top_values:
                results.append(
                    CheckResult(
                        name=f"numeric_close:{check.column}",
                        passed=False,
                        detail="reference returned no rows",
                    )
                )
                continue
            try:
                ref_num = float(top_values[0])
            except ValueError:
                results.append(
                    CheckResult(
                        name=f"numeric_close:{check.column}",
                        passed=False,
                        detail=f"reference value not numeric: {top_values[0]!r}",
                    )
                )
                continue
            # 응답 텍스트에서 ref_num과 rel_tol 이내인 숫자가 존재하는가
            passed = _response_has_close_number(norm_response, ref_num, check.rel_tol)
            results.append(
                CheckResult(
                    name=f"numeric_close:{check.column}",
                    passed=passed,
                    detail=""
                    if passed
                    else f"no number within {check.rel_tol:.0%} of {ref_num:.2f} "
                    f"in response",
                )
            )

        elif check.type == "result_excludes":
            # negation 회귀 감지: 제외 조건이 실제로 걸렸다면 해당 값들이
            # graph_results에 등장할 수 없다 (LIMIT 절단과 무관하게 유효한 검사)
            found = sorted(
                v
                for v in (normalize_text(t) for t in check.values)
                if v in pipeline_values
            )
            results.append(
                CheckResult(
                    name="result_excludes",
                    passed=not found,
                    detail=""
                    if not found
                    else f"excluded values present in results: {found}",
                )
            )

        else:
            results.append(
                CheckResult(
                    name=f"unknown_check:{check.type}",
                    passed=False,
                    detail=f"unsupported check type: {check.type}",
                )
            )

    return results


def _response_has_close_number(
    norm_response: str, target: float, rel_tol: float
) -> bool:
    """정규화된 응답 텍스트에 target과 상대 오차 이내인 숫자가 존재하는가"""
    if target == 0:
        return "0" in norm_response
    for token in re.findall(r"\d+(?:\.\d+)?", norm_response):
        try:
            value = float(token)
        except ValueError:
            continue
        if abs(value - target) / abs(target) <= rel_tol:
            return True
    return False


# ============================================
# 케이스 채점 조합
# ============================================


def grade_case_deterministic(
    case: GoldenCase,
    *,
    metadata: dict[str, Any],
    response: str,
    graph_results: list[dict[str, Any]],
    ref_rows: list[dict[str, Any]] | None,
) -> list[CheckResult]:
    """케이스 1건의 결정적 채점 전체 (judge 제외)"""
    checks: list[CheckResult] = []

    checks.append(grade_intent(case.expected_intent, metadata.get("intent", "")))
    checks.extend(
        grade_execution(
            metadata,
            require_execution=case.require_execution,
            not_empty=case.not_empty,
        )
    )

    result_count = metadata.get("result_count", 0)
    if case.tier1 is not None:
        checks.extend(
            grade_tier1(case.tier1, response=response, result_count=result_count)
        )

    if case.reference is not None and ref_rows is not None:
        checks.extend(
            grade_reference(
                ref_rows,
                case.reference.checks,
                graph_results=graph_results,
                response=response,
                result_count=result_count,
            )
        )

    return checks
