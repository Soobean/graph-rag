"""
Cypher 교정 규칙 단위 테스트 (도메인 계층)

CypherGeneratorNode에서 이관된 characterization 테스트 + 회귀 테스트.

실행 방법:
    pytest tests/domain/test_cypher_corrections.py -v
"""

import re

from src.domain.cypher import (
    coerce_tolower_params,
    correct_parameters,
    fix_aggregation_type_a_return,
    fix_in_clause_to_tolower,
    fix_not_in_syntax,
)


class TestCypherCorrections:
    """Cypher 교정 순수 함수 테스트"""

    def test_fix_in_clause_converts_name_to_tolower(self):
        """`WHERE x.name IN $list` → ANY(...toLower(x.name)=toLower(_item))"""
        cypher = "MATCH (s:Skill) WHERE s.name IN $skillNames RETURN s"
        fixed = fix_in_clause_to_tolower(cypher)

        assert "ANY(_item IN $skillNames" in fixed
        assert "toLower(s.name)" in fixed
        assert "toLower(_item)" in fixed
        # 원본의 단순 IN 패턴은 사라짐
        assert "s.name IN $skillNames" not in fixed

    def test_fix_in_clause_preserves_already_tolower(self):
        """이미 toLower(x) IN $list 형태면 변환하지 않음"""
        cypher = "WHERE toLower(s.name) IN $names"
        assert fix_in_clause_to_tolower(cypher) == cypher

    def test_fix_in_clause_skips_non_name_properties(self):
        """status/id/type 같은 속성은 변환 대상 아님 (정확한 매칭 의도)"""
        for prop in ("status", "id", "type", "category"):
            cypher = f"WHERE s.{prop} IN $list"
            assert fix_in_clause_to_tolower(cypher) == cypher

    # ------------------------------------------------------------------
    # Characterization 테스트: 도메인 모델 이전(2단계) 전 현재 동작 고정
    # ------------------------------------------------------------------

    # --- _fix_not_in_syntax ---

    def test_fix_not_in_converts_sql_style(self):
        """SQL식 `x.name NOT IN $list` → Cypher `NOT x.name IN $list`"""
        cypher = "MATCH (s:Skill) WHERE s.name NOT IN $excluded RETURN s"
        fixed = fix_not_in_syntax(cypher)
        assert "WHERE NOT s.name IN $excluded" in fixed

    def test_fix_not_in_converts_after_and(self):
        """AND 뒤 NOT IN도 교정 (리터럴 리스트 포함)"""
        cypher = "WHERE e.active = true AND s.status NOT IN ['done', 'hold']"
        fixed = fix_not_in_syntax(cypher)
        assert "AND NOT s.status IN ['done', 'hold']" in fixed

    def test_fix_not_in_converts_function_call_lhs(self):
        """함수 호출 LHS: toLower(s.name) NOT IN → NOT toLower(s.name) IN"""
        cypher = "WHERE toLower(s.name) NOT IN $names"
        fixed = fix_not_in_syntax(cypher)
        assert "WHERE NOT toLower(s.name) IN $names" in fixed

    def test_fix_not_in_case_insensitive_keywords(self):
        """소문자 where/not/in 키워드도 교정 (IGNORECASE)"""
        cypher = "match (s) where s.name not in $list return s"
        fixed = fix_not_in_syntax(cypher)
        assert re.search(r"where\s+NOT\s+s\.name\s+IN", fixed, re.IGNORECASE)

    def test_fix_not_in_noop_when_already_canonical(self):
        """이미 `NOT x IN` 정식형이면 무변환"""
        cypher = "WHERE NOT s.name IN $list"
        assert fix_not_in_syntax(cypher) == cypher

    def test_fix_not_in_noop_without_not_in(self):
        """NOT IN이 없으면 무변환"""
        cypher = "MATCH (s) WHERE s.name IN $list RETURN s"
        assert fix_not_in_syntax(cypher) == cypher

    # --- _fix_aggregation_type_a_return ---

    def test_fix_aggregation_rewrites_type_a_return(self):
        """WITH+집계 → re-MATCH → alias 없는 RETURN 안티패턴을 TYPE B로 재작성"""
        cypher = (
            "MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill)\n"
            "WITH e, COUNT(s) AS skillCount\n"
            "MATCH (e)-[:WORKS_ON]->(p:Project)\n"
            "RETURN e, p"
        )
        fixed = fix_aggregation_type_a_return(cypher)
        assert "RETURN e.name AS name, skillCount" in fixed
        assert "ORDER BY skillCount DESC" in fixed
        # re-MATCH 라인은 제거됨
        assert "WORKS_ON" not in fixed

    def test_fix_aggregation_noop_without_agg_with(self):
        """집계 없는 WITH만 있으면 무변환"""
        cypher = "MATCH (e)\nWITH e, e.name AS n\nMATCH (e)-[r]->(x)\nRETURN e, x"
        assert fix_aggregation_type_a_return(cypher) == cypher

    def test_fix_aggregation_noop_without_rematch(self):
        """집계 후 re-MATCH가 없으면 무변환"""
        cypher = "MATCH (e)-[:HAS_SKILL]->(s)\nWITH e, COUNT(s) AS c\nRETURN e, c"
        assert fix_aggregation_type_a_return(cypher) == cypher

    def test_fix_aggregation_noop_when_return_has_alias(self):
        """RETURN에 AS(alias)가 있으면 TYPE B로 판단, 무변환"""
        cypher = (
            "MATCH (e)-[:HAS_SKILL]->(s)\n"
            "WITH e, COUNT(s) AS c\n"
            "MATCH (e)-[:WORKS_ON]->(p)\n"
            "RETURN e.name AS name, c"
        )
        assert fix_aggregation_type_a_return(cypher) == cypher

    def test_fix_aggregation_noop_when_with_var_unmatched(self):
        """WITH 선두가 `var,` 형태가 아니면 무변환"""
        cypher = (
            "MATCH (e)-[:HAS_SKILL]->(s)\n"
            "WITH COUNT(s) AS c\n"
            "MATCH (x)\n"
            "RETURN x"
        )
        assert fix_aggregation_type_a_return(cypher) == cypher

    def test_fix_aggregation_noop_without_alias_in_with(self):
        """WITH에 AS alias가 없으면 무변환"""
        cypher = (
            "MATCH (e)-[:HAS_SKILL]->(s)\n"
            "WITH e, COUNT(s)\n"
            "MATCH (x)\n"
            "RETURN x"
        )
        assert fix_aggregation_type_a_return(cypher) == cypher

    # --- _correct_parameters / _correct_single_value ---

    def test_correct_params_exact_match_restores_casing(self):
        """대소문자 무시 정확 일치 시 엔티티 케이싱으로 복원"""
        result = correct_parameters(
            {"skillName": "python"}, {"Skill": ["Python"]}
        )
        assert result["skillName"] == "Python"

    def test_correct_params_param_contains_entity_longest(self):
        """param ⊃ entity: 가장 긴 엔티티로 교체 (접미사 제거 효과)"""
        result = correct_parameters(
            {"projectName": "챗봇 리뉴얼 프로젝트"},
            {"Project": ["챗봇", "챗봇 리뉴얼"]},
        )
        assert result["projectName"] == "챗봇 리뉴얼"

    def test_correct_params_entity_contains_param_shortest(self):
        """entity ⊃ param: 가장 짧은 엔티티로 교체"""
        result = correct_parameters(
            {"projectName": "데이터레이크"},
            {"Project": ["데이터레이크 개선 프로젝트", "데이터레이크 개선"]},
        )
        assert result["projectName"] == "데이터레이크 개선"

    def test_correct_params_no_match_keeps_original(self):
        """매칭 실패 시 원본 유지"""
        result = correct_parameters(
            {"skillName": "Rust"}, {"Skill": ["Python"]}
        )
        assert result["skillName"] == "Rust"

    def test_correct_params_list_elements_corrected(self):
        """리스트 파라미터의 문자열 요소도 개별 보정"""
        result = correct_parameters(
            {"names": ["python", "자바스크립트 스킬"]},
            {"Skill": ["Python", "자바스크립트"]},
        )
        assert result["names"] == ["Python", "자바스크립트"]

    def test_correct_params_empty_entities_early_return(self):
        """엔티티가 비어 있으면 파라미터 그대로 반환"""
        params = {"skillName": "python"}
        assert correct_parameters(params, {}) is params

    def test_correct_params_non_string_preserved(self):
        """숫자/불리언 등 비문자열 파라미터는 보존"""
        result = correct_parameters(
            {"limit": 10, "active": True, "rates": [1, 2]},
            {"Skill": ["Python"]},
        )
        assert result["limit"] == 10
        assert result["active"] is True
        assert result["rates"] == [1, 2]

    # --- _coerce_tolower_params ---

    def test_coerce_direct_tolower_int_to_str(self):
        """toLower($p) 직접 사용 시 int → str 강제"""
        result = coerce_tolower_params(
            "WHERE toLower(s.name) = toLower($val)", {"val": 123}
        )
        assert result["val"] == "123"

    def test_coerce_indirect_any_pattern_list(self):
        """ANY(v IN $p ... toLower(v)) 간접 패턴 시 리스트 요소 int → str"""
        cypher = "WHERE ANY(_item IN $names WHERE toLower(s.name) = toLower(_item))"
        result = coerce_tolower_params(cypher, {"names": [1, "Python", 2]})
        assert result["names"] == ["1", "Python", "2"]

    def test_coerce_preserves_unrelated_params(self):
        """toLower에 쓰이지 않는 파라미터는 타입 보존"""
        cypher = "WHERE toLower($name) = 'x' AND e.rate > $rate"
        result = coerce_tolower_params(cypher, {"name": "A", "rate": 50000})
        assert result["rate"] == 50000

    def test_coerce_noop_without_tolower(self):
        """toLower가 없으면 파라미터 그대로 반환"""
        params = {"val": 123}
        assert coerce_tolower_params("MATCH (n) RETURN n", params) is params

    def test_coerce_float_and_mixed_list(self):
        """float 및 혼합 타입 리스트도 문자열로 강제"""
        result = coerce_tolower_params(
            "WHERE toLower($a) = 'x' AND ANY(v IN $b WHERE toLower(v) = 'y')",
            {"a": 1.5, "b": [2.5, True, "s"]},
        )
        assert result["a"] == "1.5"
        # bool은 int의 서브클래스 → 현재 구현은 str로 강제함 (동작 고정)
        assert result["b"] == ["2.5", "True", "s"]

    # --- 현재 버그 고정 (negation IN 절 — 커밋 4에서 기대 동작으로 갱신 예정) ---

    def test_bug_negation_in_clause_not_converted(self):
        """[버그 고정] `WHERE NOT x.name IN $list`는 toLower 변환에서 누락됨.

        2단계 커밋 4(2-pass 정규화)에서 NONE(...) 변환으로 갱신될 예정.
        """
        cypher = "MATCH (s) WHERE NOT s.name IN $excluded RETURN s"
        assert fix_in_clause_to_tolower(cypher) == cypher

    def test_bug_not_in_chain_stops_at_canonical_form(self):
        """[버그 고정] `x.name NOT IN $l` 연쇄: 문법 교정까지만 되고 toLower 누락.

        _fix_not_in_syntax → `NOT x.name IN $l` → _fix_in_clause_to_tolower가
        건너뜀. 커밋 4에서 NONE(...) 변환으로 갱신될 예정.
        """
        cypher = "WHERE s.name NOT IN $excluded"
        step1 = fix_not_in_syntax(cypher)
        assert step1 == "WHERE NOT s.name IN $excluded"
        step2 = fix_in_clause_to_tolower(step1)
        assert step2 == step1  # 변환 안 됨 (버그)

