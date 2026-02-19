ALLOWED_LABELS: set[str] = {
    "Employee",
    "Skill",
    "Project",
    "Department",
    "Position",
    "Certificate",
    "Office",
}

# 라벨별 설명 (프롬프트에서 LLM에게 분류 힌트 제공)
LABEL_DESCRIPTIONS: dict[str, str] = {
    "Employee": "사람",
    "Skill": "기술 스킬 (프로그래밍 언어, 프레임워크, 도구 등)",
    "Project": "프로젝트",
    "Department": "부서",
    "Position": "직급/직위",
    "Certificate": "자격증",
    "Office": "사무실/위치",
}

VALID_RELATIONSHIP_COMBINATIONS: dict[str, list[tuple[str, str]]] = {
    "HAS_SKILL": [("Employee", "Skill")],
    "WORKS_ON": [("Employee", "Project")],
    "BELONGS_TO": [("Employee", "Department")],
    "HAS_POSITION": [("Employee", "Position")],
    "HAS_CERTIFICATE": [("Employee", "Certificate")],
    "REQUIRES": [("Project", "Skill")],
    "MENTORS": [("Employee", "Employee")],
    "OWNED_BY": [("Project", "Department")],
    "LOCATED_AT": [("Department", "Office")],
}

PROFICIENCY_MAP: dict[str, int] = {
    "초급": 1,
    "중급": 2,
    "고급": 3,
    "전문가": 4,
}


def build_proficiency_case_cypher(variable: str = "hs.proficiency") -> str:
    """PROFICIENCY_MAP에서 Cypher CASE문을 동적 생성.

    Args:
        variable: Cypher 변수명 (기본값: "hs.proficiency")

    Returns:
        Cypher CASE 표현식 문자열
    """
    whens = "\n".join(
        f"               WHEN '{label}' THEN {value}"
        for label, value in PROFICIENCY_MAP.items()
    )
    return f"CASE {variable}\n{whens}\n               ELSE 0\n             END"


PROJECT_STATUS_ACTIVE = "진행중"
PROJECT_STATUS_PLANNED = "계획"
PROJECT_STATUS_ACTIVE_LIST = [PROJECT_STATUS_ACTIVE, PROJECT_STATUS_PLANNED]

INTENT_DESCRIPTIONS: dict[str, str] = {
    "personnel_search": "관련 인력 정보",
    "project_matching": "참여한 프로젝트 정보",
    "relationship_search": "관계 정보",
    "org_analysis": "소속 조직 정보",
    "mentoring_network": "멘토링 관계",
    "certificate_search": "자격증 정보",
    "path_analysis": "연결 경로",
    "ontology_update": "온톨로지 정보",
    "global_analysis": "조직 전체 분석",
    "unknown": "관련 정보",
}
