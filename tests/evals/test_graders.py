"""
Eval Harness 채점기 단위 테스트

graders.py는 순수 함수(라이브 의존 없음)이므로 결정적으로 테스트 가능.
채점기 자체는 파이프라인 코드와 무관 → 순환성 없음.

실행 방법:
    pytest tests/evals/test_graders.py -v
"""

from evals.graders import (
    flatten_values,
    grade_case_deterministic,
    grade_execution,
    grade_intent,
    grade_reference,
    grade_tier1,
    normalize_text,
)
from evals.models import (
    GOLDEN_SET_PATH,
    GoldenCase,
    RefCheck,
    Tier1Checks,
    load_golden_set,
)


class TestNormalization:
    """텍스트/값 정규화"""

    def test_normalize_lowercases(self):
        assert normalize_text("Python") == "python"

    def test_normalize_removes_thousands_commas(self):
        assert normalize_text("평균 66,000원") == "평균 66000원"

    def test_normalize_keeps_list_commas(self):
        """숫자 사이가 아닌 콤마(나열)는 보존"""
        assert normalize_text("Python, Java") == "python, java"

    def test_flatten_values_nested_node_dict(self):
        """Neo4j 노드 dict의 중첩 properties까지 평탄화"""
        rows = [
            {
                "e": {
                    "labels": ["Employee"],
                    "properties": {"name": "홍길동", "hourly_rate": 50000},
                },
                "count": 3,
            }
        ]
        values = flatten_values(rows)
        assert "홍길동" in values
        assert "50000" in values
        assert "3" in values

    def test_flatten_values_skips_none(self):
        assert flatten_values([{"a": None}]) == set()


class TestGradeIntent:
    """intent 허용 리스트 채점"""

    def test_intent_in_allowed_list(self):
        result = grade_intent(("org_analysis", "global_analysis"), "org_analysis")
        assert result.passed

    def test_intent_not_in_allowed_list(self):
        result = grade_intent(("org_analysis",), "personnel_search")
        assert not result.passed
        assert "personnel_search" in result.detail


class TestGradeExecution:
    """tier0: 실행 성공 + not_empty"""

    def _metadata(self, **overrides):
        base = {
            "error": None,
            "execution_path": ["intent_entity_extractor", "graph_executor"],
            "result_count": 5,
        }
        base.update(overrides)
        return base

    def test_execution_ok(self):
        results = grade_execution(
            self._metadata(), require_execution=True, not_empty=True
        )
        assert all(r.passed for r in results)

    def test_execution_fails_on_error(self):
        results = grade_execution(
            self._metadata(error="Cypher generation failed"),
            require_execution=True,
            not_empty=True,
        )
        exec_check = next(r for r in results if r.name == "execution_ok")
        assert not exec_check.passed

    def test_execution_fails_without_graph_executor(self):
        """graph_executor_error 같은 변형 경로는 실행 성공이 아님"""
        results = grade_execution(
            self._metadata(execution_path=["cypher_generator", "graph_executor_error"]),
            require_execution=True,
            not_empty=True,
        )
        exec_check = next(r for r in results if r.name == "execution_ok")
        assert not exec_check.passed

    def test_not_empty_fails_on_zero(self):
        results = grade_execution(
            self._metadata(result_count=0), require_execution=True, not_empty=True
        )
        empty_check = next(r for r in results if r.name == "not_empty")
        assert not empty_check.passed

    def test_checks_skippable(self):
        results = grade_execution(
            self._metadata(), require_execution=False, not_empty=False
        )
        assert results == []


class TestGradeTier1:
    """tier1: count_range + must_include_any"""

    def test_count_in_range(self):
        tier1 = Tier1Checks(count_min=10, count_max=None)
        results = grade_tier1(tier1, response="", result_count=37)
        assert results[0].passed

    def test_count_below_min(self):
        tier1 = Tier1Checks(count_min=10)
        results = grade_tier1(tier1, response="", result_count=3)
        assert not results[0].passed

    def test_count_above_max(self):
        tier1 = Tier1Checks(count_min=1, count_max=50)
        results = grade_tier1(tier1, response="", result_count=200)
        assert not results[0].passed

    def test_must_include_any_hit(self):
        tier1 = Tier1Checks(must_include_any=("멘토", "멘티"))
        results = grade_tier1(
            tier1, response="멘토 1인당 평균 2.3명입니다.", result_count=1
        )
        assert results[0].passed

    def test_must_include_any_case_insensitive(self):
        tier1 = Tier1Checks(must_include_any=("PM",))
        results = grade_tier1(tier1, response="pm 역할 분포는...", result_count=1)
        assert results[0].passed

    def test_must_include_any_miss(self):
        tier1 = Tier1Checks(must_include_any=("멘토",))
        results = grade_tier1(tier1, response="관련 없는 응답", result_count=1)
        assert not results[0].passed


class TestGradeReference:
    """reference oracle 대조"""

    REF_ROWS = [
        {"name": "홍길동", "cnt": 5},
        {"name": "김철수", "cnt": 4},
    ]

    def _pipeline_rows(self, *names):
        return [
            {"e": {"labels": ["Employee"], "properties": {"name": n}}} for n in names
        ]

    def test_key_set_subset_pass(self):
        """ref 명단이 파이프라인 결과에 전부 포함되면 통과"""
        checks = (RefCheck(type="key_set", column="name", mode="subset"),)
        results = grade_reference(
            self.REF_ROWS,
            checks,
            graph_results=self._pipeline_rows("홍길동", "김철수", "이영희"),
            response="",
            result_count=3,
        )
        assert results[0].passed

    def test_key_set_subset_fail_missing(self):
        checks = (RefCheck(type="key_set", column="name", mode="subset"),)
        results = grade_reference(
            self.REF_ROWS,
            checks,
            graph_results=self._pipeline_rows("홍길동"),
            response="",
            result_count=1,
        )
        assert not results[0].passed
        assert "김철수" in results[0].detail

    def test_key_set_empty_reference_fails(self):
        """reference가 0행이면 oracle 자체가 잘못된 것 — 실패 처리"""
        checks = (RefCheck(type="key_set", column="name"),)
        results = grade_reference(
            [], checks, graph_results=[], response="", result_count=0
        )
        assert not results[0].passed

    def test_answer_contains_top_pass(self):
        checks = (RefCheck(type="answer_contains_top", column="dept"),)
        results = grade_reference(
            [{"dept": "AI연구소", "avg": 70000}, {"dept": "백엔드개발팀"}],
            checks,
            graph_results=[],
            response="가장 높은 부서는 AI연구소입니다.",
            result_count=1,
        )
        assert results[0].passed

    def test_answer_contains_top_fail(self):
        checks = (RefCheck(type="answer_contains_top", column="dept"),)
        results = grade_reference(
            [{"dept": "AI연구소"}],
            checks,
            graph_results=[],
            response="가장 높은 부서는 데이터팀입니다.",
            result_count=1,
        )
        assert not results[0].passed

    def test_count_match_within_tolerance(self):
        checks = (RefCheck(type="count_match", tolerance=1),)
        results = grade_reference(
            self.REF_ROWS, checks, graph_results=[], response="", result_count=3
        )
        assert results[0].passed

    def test_count_match_exceeds_tolerance(self):
        checks = (RefCheck(type="count_match", tolerance=0),)
        results = grade_reference(
            self.REF_ROWS, checks, graph_results=[], response="", result_count=5
        )
        assert not results[0].passed

    def test_numeric_close_with_comma_formatting(self):
        """응답의 '66,000원' 포맷도 정규화 후 근접 판정"""
        checks = (RefCheck(type="numeric_close", column="avg", rel_tol=0.05),)
        results = grade_reference(
            [{"avg": 66123.4}],
            checks,
            graph_results=[],
            response="평균 시급은 66,000원입니다.",
            result_count=1,
        )
        assert results[0].passed

    def test_numeric_close_fail_far_off(self):
        checks = (RefCheck(type="numeric_close", column="avg", rel_tol=0.05),)
        results = grade_reference(
            [{"avg": 66000}],
            checks,
            graph_results=[],
            response="평균 시급은 30,000원입니다.",
            result_count=1,
        )
        assert not results[0].passed

    def test_unknown_check_type_fails_loudly(self):
        checks = (RefCheck(type="nonexistent"),)
        results = grade_reference(
            self.REF_ROWS, checks, graph_results=[], response="", result_count=2
        )
        assert not results[0].passed


class TestGradeCaseDeterministic:
    """케이스 종합 채점"""

    def test_full_pass(self):
        case = GoldenCase(
            id="t1",
            question="q",
            category="org_analysis",
            expected_intent=("org_analysis",),
            tier1=Tier1Checks(count_min=1),
        )
        checks = grade_case_deterministic(
            case,
            metadata={
                "intent": "org_analysis",
                "error": None,
                "execution_path": ["graph_executor"],
                "result_count": 3,
            },
            response="응답",
            graph_results=[],
            ref_rows=None,
        )
        assert all(c.passed for c in checks)

    def test_reference_skipped_when_ref_rows_none(self):
        """reference가 정의돼도 ref_rows가 없으면(실행 실패) 채점 생략"""
        from evals.models import Reference

        case = GoldenCase(
            id="t2",
            question="q",
            category="org_analysis",
            expected_intent=("org_analysis",),
            reference=Reference(
                cypher="RETURN 1", checks=(RefCheck(type="count_match"),)
            ),
        )
        checks = grade_case_deterministic(
            case,
            metadata={
                "intent": "org_analysis",
                "error": None,
                "execution_path": ["graph_executor"],
                "result_count": 1,
            },
            response="",
            graph_results=[],
            ref_rows=None,
        )
        assert not any(c.name == "count_match" for c in checks)


class TestGoldenSetFile:
    """golden_set.yaml 무결성"""

    def test_loads_33_cases(self):
        cases = load_golden_set(GOLDEN_SET_PATH)
        assert len(cases) == 33

    def test_ids_unique_and_prefixed(self):
        cases = load_golden_set(GOLDEN_SET_PATH)
        ids = [c.id for c in cases]
        assert len(ids) == len(set(ids))
        assert all(i[0] in ("q", "s", "n", "g") for i in ids)

    def test_all_cases_have_expected_intent(self):
        cases = load_golden_set(GOLDEN_SET_PATH)
        valid_intents = {
            "personnel_search",
            "project_matching",
            "relationship_search",
            "org_analysis",
            "mentoring_network",
            "certificate_search",
            "path_analysis",
            "ontology_update",
            "global_analysis",
        }
        for case in cases:
            assert case.expected_intent, f"{case.id}: expected_intent 비어 있음"
            for intent in case.expected_intent:
                assert intent in valid_intents, f"{case.id}: 잘못된 intent {intent}"

    def test_judge_cases_marked(self):
        """판단형/시나리오 케이스는 judge 대상"""
        cases = {c.id: c for c in load_golden_set(GOLDEN_SET_PATH)}
        for case_id in ("q02_career_vs_guideline", "s03_pinecone_gap_candidates"):
            assert cases[case_id].judge


class TestResultExcludes:
    """negation 회귀 감지 — 제외 값이 결과에 등장하면 실패"""

    def test_excluded_value_absent_passes(self):
        from evals.models import RefCheck

        checks = (RefCheck(type="result_excludes", values=("Python", "Java")),)
        results = grade_reference(
            [{"name": "x"}],
            checks,
            graph_results=[
                {"s": {"labels": ["Skill"], "properties": {"name": "Docker"}}}
            ],
            response="",
            result_count=1,
        )
        assert results[0].passed

    def test_excluded_value_present_fails(self):
        from evals.models import RefCheck

        checks = (RefCheck(type="result_excludes", values=("Python",)),)
        results = grade_reference(
            [{"name": "x"}],
            checks,
            graph_results=[
                {"s": {"labels": ["Skill"], "properties": {"name": "python"}}}
            ],
            response="",
            result_count=1,
        )
        assert not results[0].passed
        assert "python" in results[0].detail

    def test_case_insensitive_matching(self):
        from evals.models import RefCheck

        checks = (RefCheck(type="result_excludes", values=("JAVA",)),)
        results = grade_reference(
            [{"name": "x"}],
            checks,
            graph_results=[{"skill": "Java"}],
            response="",
            result_count=1,
        )
        assert not results[0].passed
