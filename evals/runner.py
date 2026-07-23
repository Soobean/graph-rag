"""
Eval Harness 러너

골든셋 케이스를 실제 파이프라인(라이브 Neo4j + Azure OpenAI)에 실행하고
결정적 채점 + 선택적 LLM judge로 리포트를 생성한다.

실행:
    uv run python -m evals.runner                 # 결정적 채점 풀런
    uv run python -m evals.runner --judge         # + LLM faithfulness
    uv run python -m evals.runner --only q01_dept_avg_rate
    uv run python -m evals.runner --limit 5
    uv run python -m evals.runner --category org_analysis
    uv run python -m evals.runner --verify-refs   # reference만 실행 (LLM 0회)
    uv run python -m evals.runner --baseline evals/baselines/baseline.json

주의: CI pytest에 넣지 않는다 — 라이브 의존 + LLM 비용 + 비결정성.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from evals.graders import grade_case_deterministic
from evals.models import (
    CaseResult,
    EvalReport,
    GoldenCase,
    load_golden_set,
)
from src.application.llm import LLMTaskService
from src.config import get_settings
from src.graph.pipeline import GraphRAGPipeline
from src.infrastructure.llm import AzureOpenAIGateway
from src.infrastructure.neo4j_client import Neo4jClient
from src.repositories.neo4j_repository import Neo4jRepository

logging.basicConfig(level=logging.WARNING)  # 파이프라인 INFO 로그 억제
logger = logging.getLogger("evals")
logger.setLevel(logging.INFO)

REPORTS_DIR = Path(__file__).parent / "reports"
SEP = "=" * 70


# ============================================
# 케이스 실행
# ============================================


async def run_case(
    pipeline: GraphRAGPipeline,
    neo4j_repo: Neo4jRepository,
    case: GoldenCase,
    *,
    run_ts: str,
    use_judge: bool,
    gateway: AzureOpenAIGateway,
) -> CaseResult:
    """케이스 1건: reference oracle 실행 → 파이프라인 실행 → 채점"""
    start = time.time()

    # 1) reference oracle (LLM 미경유 — Neo4j 직접 실행)
    ref_rows: list[dict[str, Any]] | None = None
    if case.reference is not None:
        try:
            ref_rows = await neo4j_repo.execute_cypher(case.reference.cypher, {})
        except Exception as e:
            logger.error(f"[{case.id}] reference 실행 실패: {e}")
            ref_rows = None  # 채점에서 생략되고 tier0/tier1만 적용됨

    # 2) 파이프라인 실행 (캐시는 Settings 오버라이드로 비활성 — main() 참고)
    result = await pipeline.run(
        case.question,
        session_id=f"eval-{run_ts}-{case.id}",
        return_full_state=True,
    )
    metadata: dict[str, Any] = dict(result.get("metadata", {}))
    response: str = result.get("response", "") or ""
    full_state = metadata.pop("_full_state", {}) or {}
    graph_results: list[dict[str, Any]] = full_state.get("graph_results", []) or []

    # 3) 결정적 채점
    checks = grade_case_deterministic(
        case,
        metadata=metadata,
        response=response,
        graph_results=graph_results,
        ref_rows=ref_rows,
    )

    # 4) LLM judge (옵트인)
    judge_result = None
    if use_judge and case.judge:
        from evals.judge import judge_faithfulness

        try:
            judge_result = await judge_faithfulness(
                gateway,
                question=case.question,
                response=response,
                graph_results=graph_results,
            )
        except Exception as e:
            logger.error(f"[{case.id}] judge 실패: {e}")

    return CaseResult(
        case_id=case.id,
        category=case.category,
        passed=all(c.passed for c in checks),
        checks=checks,
        judge_result=judge_result,
        metadata={
            "intent": metadata.get("intent"),
            "cypher_query": metadata.get("cypher_query"),
            "result_count": metadata.get("result_count"),
            "execution_path": metadata.get("execution_path"),
            "node_timings": metadata.get("node_timings", {}),
            "error": metadata.get("error"),
        },
        elapsed_seconds=round(time.time() - start, 2),
    )


async def verify_refs(
    neo4j_repo: Neo4jRepository, cases: list[GoldenCase]
) -> None:
    """--verify-refs: reference Cypher만 실행해 행수·샘플을 출력 (큐레이션 검증)"""
    print(SEP)
    print("Reference Oracle 검증 (LLM 0회)")
    print(SEP)
    for case in cases:
        if case.reference is None:
            continue
        marker = f"verified={case.reference.verified}" if case.reference.verified else "UNVERIFIED"
        try:
            rows = await neo4j_repo.execute_cypher(case.reference.cypher, {})
            print(f"\n✅ {case.id} [{marker}] — {len(rows)}행")
            for row in rows[:3]:
                print(f"   {row}")
            if len(rows) > 3:
                print(f"   ... 외 {len(rows) - 3}행")
        except Exception as e:
            print(f"\n❌ {case.id} [{marker}] — 실행 실패: {e}")
    print(f"\n{SEP}")


# ============================================
# 리포트
# ============================================


def build_report(results: list[CaseResult], timestamp: str) -> EvalReport:
    by_category: dict[str, list[CaseResult]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)
    category_rate = {
        cat: f"{sum(1 for r in rs if r.passed)}/{len(rs)}"
        for cat, rs in sorted(by_category.items())
    }
    return EvalReport(
        timestamp=timestamp,
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        case_results=results,
        category_pass_rate=category_rate,
    )


def print_report(report: EvalReport) -> None:
    print(f"\n{SEP}")
    print("Eval 결과 요약")
    print(SEP)
    for r in report.case_results:
        icon = "✅" if r.passed else "❌"
        failed = [c.name for c in r.checks if not c.passed]
        judge_str = ""
        if r.judge_result:
            judge_icon = "🟢" if r.judge_result.faithful else "🔴"
            judge_str = f"  judge={judge_icon}{r.judge_result.score:.2f}"
        detail = f"  실패: {failed}" if failed else ""
        print(
            f"{icon} {r.case_id:<36} intent={r.metadata.get('intent', '?'):<18}"
            f"rows={r.metadata.get('result_count', '?'):<5}"
            f"{r.elapsed_seconds:>6.1f}s{judge_str}{detail}"
        )
    print(SEP)
    print(f"전체: {report.passed}/{report.total} ({report.pass_rate:.0%})")
    for cat, rate in report.category_pass_rate.items():
        print(f"  {cat}: {rate}")
    judged = [r for r in report.case_results if r.judge_result]
    if judged:
        faithful = sum(1 for r in judged if r.judge_result and r.judge_result.faithful)
        print(f"  judge faithful: {faithful}/{len(judged)}")

    # 노드별 레이턴시 브레이크다운 (계측 데이터가 있는 케이스 기준)
    node_samples: dict[str, list[float]] = {}
    for r in report.case_results:
        for node, sec in (r.metadata.get("node_timings") or {}).items():
            node_samples.setdefault(node, []).append(sec)
    if node_samples:
        print("\n노드별 레이턴시 (avg / max, n=케이스 수):")
        total_avg = 0.0
        for node, samples in sorted(
            node_samples.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])
        ):
            avg = sum(samples) / len(samples)
            total_avg += avg
            print(
                f"  {node:<28} {avg:6.2f}s / {max(samples):6.2f}s  (n={len(samples)})"
            )
        print(f"  {'합계(노드 평균의 합)':<27} {total_avg:6.2f}s")
    print(SEP)


def save_report(report: EvalReport) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"eval_{report.timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def diff_against_baseline(report: EvalReport, baseline_path: Path) -> list[str]:
    """베이스라인 대비 pass→fail 회귀 케이스 id 목록"""
    with open(baseline_path, encoding="utf-8") as f:
        baseline = json.load(f)
    baseline_passed = {
        c["case_id"] for c in baseline.get("cases", []) if c.get("passed")
    }
    current = {r.case_id: r.passed for r in report.case_results}
    return sorted(
        cid for cid in baseline_passed if cid in current and not current[cid]
    )


# ============================================
# 진입점
# ============================================


def _select_cases(args: argparse.Namespace) -> list[GoldenCase]:
    cases = load_golden_set()
    if args.only:
        wanted = set(args.only)
        cases = [c for c in cases if c.id in wanted]
        missing = wanted - {c.id for c in cases}
        if missing:
            raise SystemExit(f"알 수 없는 case id: {sorted(missing)}")
    if args.category:
        cases = [c for c in cases if c.category == args.category]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("선택된 케이스가 없습니다")
    return cases


async def main() -> int:
    parser = argparse.ArgumentParser(description="Graph RAG Eval Harness")
    parser.add_argument("--judge", action="store_true", help="LLM faithfulness judge 실행")
    parser.add_argument("--only", nargs="+", metavar="ID", help="특정 케이스만 실행")
    parser.add_argument("--limit", type=int, help="앞 N개 케이스만 실행")
    parser.add_argument("--category", help="카테고리 필터")
    parser.add_argument(
        "--verify-refs", action="store_true", help="reference oracle만 실행 (LLM 0회)"
    )
    parser.add_argument(
        "--baseline", type=Path, help="회귀 비교할 베이스라인 리포트 JSON"
    )
    args = parser.parse_args()

    cases = _select_cases(args)
    settings = get_settings().model_copy(
        update={"vector_search_enabled": False}  # 캐시 노드 제거 — fresh 평가 보장
    )

    async with Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    ) as neo4j_client:
        neo4j_repo = Neo4jRepository(neo4j_client)

        if args.verify_refs:
            await verify_refs(neo4j_repo, cases)
            return 0

        gateway = AzureOpenAIGateway(settings)
        llm_tasks = LLMTaskService(gateway)
        schema = await neo4j_repo.get_schema()
        pipeline = GraphRAGPipeline(
            settings=settings,
            neo4j_repository=neo4j_repo,
            llm_tasks=llm_tasks,
            llm_gateway=gateway,
            neo4j_client=neo4j_client,
            graph_schema=schema,
        )

        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"{SEP}\nEval 실행: {len(cases)}케이스 (judge={'on' if args.judge else 'off'})\n{SEP}")

        results: list[CaseResult] = []
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {case.id} ...", flush=True)
            try:
                results.append(
                    await run_case(
                        pipeline,
                        neo4j_repo,
                        case,
                        run_ts=run_ts,
                        use_judge=args.judge,
                        gateway=gateway,
                    )
                )
            except Exception as e:
                logger.error(f"[{case.id}] 실행 자체가 실패: {e}")
                results.append(
                    CaseResult(
                        case_id=case.id,
                        category=case.category,
                        passed=False,
                        metadata={"error": f"runner exception: {e}"},
                    )
                )

        await gateway.close()

    report = build_report(results, run_ts)
    print_report(report)
    path = save_report(report)
    print(f"리포트 저장: {path}")

    if args.baseline:
        regressions = diff_against_baseline(report, args.baseline)
        if regressions:
            print(f"\n🔴 베이스라인 대비 회귀 {len(regressions)}건: {regressions}")
            return 1
        print("\n🟢 베이스라인 대비 회귀 없음")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
