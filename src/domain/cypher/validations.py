"""
Cypher 실행 전 검증 (도메인 모델)

LLM이 생성한 Cypher가 스키마에 실재하는 속성만 참조하는지 검사한다.

배경: LLM이 질문 문구에서 속성을 발명하는 실패 모드가 실증됨
(예: "필수 스킬" → 존재하지 않는 `req.importance = '필수'` 필터).
이런 쿼리는 문법이 유효해서 SyntaxError 기반 self-correction이 발동하지 않고
조용히 0건을 반환한다. 실행 전 검증으로 재생성 피드백을 만들 수 있다.

주의: 스키마 인트로스펙션은 불완전할 수 있으므로(라벨당 속성 수집 제한 등)
이 검증은 **하드 차단이 아니라 재생성 힌트**로만 사용해야 한다.
"""

from __future__ import annotations

import re
from typing import Any

# 'var.prop' 참조 추출 (파라미터 $p.x 제외는 호출부에서 문자열 정리로 처리)
_PROP_REF_PATTERN = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b")

# 따옴표 문자열 제거용 (문자열 리터럴 내부의 점 표기 오탐 방지, 예: 'ML.NET')
_QUOTED_STRING_PATTERN = re.compile(r"'[^']*'|\"[^\"]*\"")


def _known_properties(schema: dict[str, Any]) -> set[str] | None:
    """스키마에서 알려진 속성명 집합을 수집.

    속성 정보가 없는 스키마(labels만 있는 축약형)면 None을 반환해
    "검증 불가"를 표현한다 — 이 경우 검증을 건너뛰어야 한다.
    """
    known: set[str] = set()
    has_property_info = False

    for node in schema.get("nodes", []) or []:
        for prop in node.get("properties", []) or []:
            name = prop.get("name")
            if name:
                known.add(name.lower())
                has_property_info = True

    for rel in schema.get("relationships", []) or []:
        for prop in rel.get("properties", []) or []:
            name = prop.get("name")
            if name:
                known.add(name.lower())
                has_property_info = True

    return known if has_property_info else None


def find_unknown_properties(cypher: str, schema: dict[str, Any]) -> list[str]:
    """Cypher가 참조하는 `var.prop` 중 스키마에 없는 속성명 목록.

    - 문자열 리터럴 내부는 무시 ('ML.NET' 등 오탐 방지)
    - 스키마에 속성 정보가 없으면 검증 불가 → 빈 목록 (false positive 방지)
    - 반환된 속성은 "환각 의심"이지 확정이 아님 — 재생성 힌트로만 사용할 것
    """
    known = _known_properties(schema)
    if known is None:
        return []

    stripped = _QUOTED_STRING_PATTERN.sub("''", cypher)

    unknown: list[str] = []
    seen: set[str] = set()
    for _var, prop in _PROP_REF_PATTERN.findall(stripped):
        prop_lower = prop.lower()
        if prop_lower in known or prop_lower in seen:
            continue
        seen.add(prop_lower)
        unknown.append(prop)
    return unknown
