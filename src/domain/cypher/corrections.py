"""
Cypher 교정 규칙 (도메인 모델)

LLM이 생성한 Cypher 쿼리·파라미터를 실행 전에 교정하는 순수 함수 모음.
CypherGeneratorNode에 정규식 패치로 산재하던 규칙들을 수렴한 모듈이다.

순서 불변식 (apply_corrections):
    1. fix_not_in_syntax      — SQL식 NOT IN → Cypher 정식형 (canonicalize)
    2. fix_in_clause_to_tolower — IN 절 case-insensitive 변환 (convert)
    3. fix_aggregation_type_a_return — 집계 후 TYPE A RETURN 안티패턴 교정
    4. correct_parameters     — 파라미터 값을 추출 엔티티와 대조 보정
    5. coerce_tolower_params  — toLower() 대상 파라미터 타입 강제

1은 2보다 반드시 앞서야 한다: canonicalize가 만든 형태를 convert가 읽는
2-pass 구조가 negation 연쇄 버그를 구조적으로 차단한다.

향후 self-correcting 루프(실행 실패 → 재생성)에서도 재생성된 쿼리에
apply_corrections()를 그대로 재호출하면 된다 (노드/state 의존 없음).
"""

import logging
import re
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

# case-insensitive 변환 대상 속성 (id/status/type 같은 enum-like 속성 제외)
CASE_INSENSITIVE_PROPS: frozenset[str] = frozenset({"name", "title", "label", "alias"})


class CorrectedQuery(NamedTuple):
    """교정 파이프라인의 결과 (cypher, parameters) 쌍"""

    cypher: str
    parameters: dict[str, Any]


def fix_not_in_syntax(cypher: str) -> str:
    """
    Neo4j Cypher는 SQL의 'NOT IN' 문법을 지원하지 않음.
    LLM이 SQL 습관으로 잘못된 문법을 생성할 수 있으므로 후보정.
    """
    fixed = re.sub(
        r"\b(WHERE|AND|OR)\s+"
        r"((?:\w+\s*\([^)]*\)|\w+(?:\.\w+)*))"
        r"\s+NOT\s+IN\b",
        r"\1 NOT \2 IN",
        cypher,
        flags=re.IGNORECASE,
    )
    if fixed != cypher:
        logger.info("Fixed NOT IN syntax in Cypher query")
    return fixed


# `WHERE [NOT] x.<prop> IN $param` 패턴 감지 (negation은 canonical form 전제)
# — `toLower(x.name)` 또는 `toLower(...)` 등 함수 호출은 제외 (이미 처리됨)
_IN_CLAUSE_PATTERN = re.compile(
    r"\b(WHERE|AND|OR)\s+"
    r"(NOT\s+)?"  # canonical negation (fix_not_in_syntax가 만든 형태)
    r"(?!toLower\b|toUpper\b)"  # toLower/toUpper 시작이면 제외 (이미 처리됨)
    r"(\w+\.\w+)\s+"  # variable.property (e.g., s.name)
    r"IN\s+\$(\w+)\b",  # IN $paramName
    re.IGNORECASE,
)


def fix_in_clause_to_tolower(cypher: str) -> str:
    """
    `WHERE [NOT] x.name IN $list` 패턴을 case-insensitive 비교로 변환.

    Why: DB에 'Python'/'python' 같은 케이싱 차이가 있어 IN 비교가 silently 실패.
    프롬프트가 강제하지만 LLM이 가끔 빠뜨림 → 후처리로 안전망.

    변환 (2-pass 불변식 — fix_not_in_syntax가 canonicalize한 형태를 전제):
        WHERE s.name IN $skillNames
        → WHERE ANY(_item IN $skillNames WHERE toLower(s.name) = toLower(_item))

        WHERE NOT s.name IN $skillNames
        → WHERE NONE(_item IN $skillNames WHERE toLower(s.name) = toLower(_item))
          (NOT ANY(...)와 동치이며 연산자 우선순위 이슈가 없는 관용형)

    알려진 한계:
    - 파라미터(`$param`)가 아닌 리터럴 리스트(`IN ['a','b']`)는 변환하지 않음
      — 리터럴은 LLM이 케이싱을 직접 제어하므로 위험 대비 이득이 작음.
    - 괄호로 감싼 negation(`WHERE NOT (x.name IN $list)`)은 변환하지 않음
      — 프롬프트/canonicalize가 만드는 형태가 아니며, 괄호 내부 매칭은
      오탐 위험(패턴 predicate 등) 대비 이득이 작음. 유효 문법이므로 실행은 됨.
    """

    def replace(match: re.Match[str]) -> str:
        keyword = match.group(1)
        negation = match.group(2)  # "NOT " 또는 None
        prop_path = match.group(3)  # e.g., s.name
        param_name = match.group(4)  # e.g., skillNames

        # 단순 휴리스틱: name/title 류 속성만 case-insensitive (id/status/타입 enum 제외)
        prop_name = prop_path.split(".", 1)[1].lower()
        if prop_name not in CASE_INSENSITIVE_PROPS:
            return match.group(0)  # 변환하지 않음

        quantifier = "NONE" if negation else "ANY"
        return (
            f"{keyword} {quantifier}(_item IN ${param_name} "
            f"WHERE toLower({prop_path}) = toLower(_item))"
        )

    fixed = _IN_CLAUSE_PATTERN.sub(replace, cypher)
    if fixed != cypher:
        logger.info(
            "Auto-applied toLower() to IN clause for case-insensitive matching"
        )
    return fixed


def fix_aggregation_type_a_return(cypher: str) -> str:
    """WITH + 집계 후 re-MATCH + TYPE A RETURN 안티패턴을 TYPE B로 변환."""
    lines = [line.strip() for line in cypher.strip().split("\n") if line.strip()]

    agg_with_idx = -1
    agg_funcs = ("COUNT(", "SUM(", "AVG(", "COLLECT(")
    for i, line in enumerate(lines):
        upper = line.upper()
        if upper.startswith("WITH") and any(f in upper for f in agg_funcs):
            agg_with_idx = i
            break

    if agg_with_idx < 0:
        return cypher

    re_match_idx = -1
    for i in range(agg_with_idx + 1, len(lines)):
        if lines[i].upper().startswith("MATCH"):
            re_match_idx = i
            break

    if re_match_idx < 0:
        return cypher

    return_idx = -1
    for i in range(re_match_idx, len(lines)):
        if lines[i].upper().startswith("RETURN"):
            return_idx = i
            break

    if return_idx < 0 or " AS " in lines[return_idx].upper():
        return cypher

    with_line = lines[agg_with_idx]
    main_var_match = re.match(r"WITH\s+(\w+)\s*,", with_line, re.IGNORECASE)
    if not main_var_match:
        return cypher
    main_var = main_var_match.group(1)

    aliases = re.findall(r"\bAS\s+(\w+)", with_line, re.IGNORECASE)
    if not aliases:
        return cypher

    return_parts = [f"{main_var}.name AS name"] + aliases
    new_return = "RETURN " + ", ".join(return_parts)
    result_lines = lines[:re_match_idx] + [
        new_return,
        f"ORDER BY {aliases[0]} DESC",
    ]
    fixed = "\n".join(result_lines)

    logger.info("Fixed aggregation + TYPE A return → TYPE B")
    return fixed


def _correct_single_value(
    value: str,
    entity_values: list[str],
) -> str:
    """
    단일 문자열 값을 엔티티 값으로 보정.

    매칭 전략 (우선순위):
    1. 정확 일치 → 그대로
    2. 파라미터가 entity를 포함 → entity 값으로 교체
    3. entity가 파라미터를 포함 → entity 값으로 교체
    4. 매칭 실패 → 원래 값 그대로 (fallback)
    """
    # 1) 정확 일치 (대소문자 무시)
    exact = next(
        (ev for ev in entity_values if ev.lower() == value.lower()),
        None,
    )
    if exact is not None:
        return exact

    # 2) 파라미터가 entity를 포함 (e.g. "챗봇 리뉴얼 프로젝트" contains "챗봇 리뉴얼")
    val_lower = value.lower()
    contains_matches = [ev for ev in entity_values if ev.lower() in val_lower]
    if contains_matches:
        best = max(contains_matches, key=len)
        logger.info(
            f"Parameter correction: '{value}' → '{best}' (param contains entity)"
        )
        return best

    # 3) entity가 파라미터를 포함 (e.g. entity "데이터레이크 개선" contains param "데이터레이크")
    reverse_matches = [ev for ev in entity_values if val_lower in ev.lower()]
    if reverse_matches:
        best = min(reverse_matches, key=len)
        logger.info(
            f"Parameter correction: '{value}' → '{best}' (entity contains param)"
        )
        return best

    # 4) 매칭 실패 → 원래 값 유지
    return value


def correct_parameters(
    parameters: dict[str, Any],
    entities: dict[str, list[str]],
) -> dict[str, Any]:
    """
    LLM이 생성한 파라미터 값을 엔티티 값으로 보정.

    LLM이 파라미터에 접미사(프로젝트, 팀, 부서 등)를 추가하거나
    공백을 변경하는 경우, 원래 엔티티 값으로 교체합니다.
    문자열과 문자열 리스트 모두 처리합니다.
    """
    # 모든 엔티티 값을 flat list로 수집
    entity_values: list[str] = []
    for values in entities.values():
        entity_values.extend(values)

    if not entity_values:
        return parameters

    corrected: dict[str, Any] = {}
    for key, value in parameters.items():
        if isinstance(value, str):
            corrected[key] = _correct_single_value(value, entity_values)
        elif isinstance(value, list):
            # 리스트 내 문자열 요소들도 보정
            corrected[key] = [
                _correct_single_value(v, entity_values) if isinstance(v, str) else v
                for v in value
            ]
        else:
            corrected[key] = value

    return corrected


def coerce_tolower_params(
    cypher: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Cypher에서 toLower()에 사용되는 파라미터가 숫자 타입이면
    문자열로 변환합니다.

    두 가지 패턴을 감지합니다:
    1. 직접: toLower($param)
    2. 간접: ANY(var IN $param WHERE ... toLower(var))
    """
    tolower_params: set[str] = set()

    # 패턴 1: toLower($paramName) — 직접 사용
    tolower_params.update(re.findall(r"toLower\(\s*\$(\w+)\s*\)", cypher))

    # 패턴 2: var IN $param ... toLower(var) — 리스트 순회 간접 사용
    for iter_var, param_name in re.findall(r"(\w+)\s+IN\s+\$(\w+)", cypher):
        if re.search(rf"toLower\(\s*{re.escape(iter_var)}\s*\)", cypher):
            tolower_params.add(param_name)

    if not tolower_params:
        return parameters

    coerced = dict(parameters)
    for param_name in tolower_params:
        if param_name in coerced:
            value = coerced[param_name]
            if isinstance(value, (int, float)):
                logger.info(
                    f"Coercing toLower param '{param_name}': "
                    f"{type(value).__name__}({value}) → str('{value}')"
                )
                coerced[param_name] = str(value)
            elif isinstance(value, list):
                coerced[param_name] = [
                    str(v) if isinstance(v, (int, float)) else v for v in value
                ]
    return coerced


def apply_corrections(
    cypher: str,
    parameters: dict[str, Any],
    entities: dict[str, list[str]],
) -> CorrectedQuery:
    """
    LLM 생성 Cypher/파라미터에 교정 규칙 전체를 순서대로 적용.

    순서 불변식: canonicalize(NOT IN) → toLower 변환 → 집계 RETURN 교정
    → 파라미터 보정 → toLower 타입 강제. 모듈 docstring 참고.
    """
    cypher = fix_not_in_syntax(cypher)
    cypher = fix_in_clause_to_tolower(cypher)
    cypher = fix_aggregation_type_a_return(cypher)
    parameters = correct_parameters(parameters, entities)
    parameters = coerce_tolower_params(cypher, parameters)
    return CorrectedQuery(cypher=cypher, parameters=parameters)
