"""
Graph RAG 파이프라인 상수 정의

Intent 분류, 엔티티 타입 등 파이프라인 전반에서 참조되는 상수
"""

from typing import Literal

# ARCHITECTURE.md에 정의된 7가지 Intent Type + ontology_update + unknown
IntentType = Literal[
    "personnel_search",  # A. 인력 추천
    "project_matching",  # B. 프로젝트 매칭
    "relationship_search",  # C. 관계 탐색
    "org_analysis",  # D. 조직 분석
    "mentoring_network",  # E. 멘토링 네트워크
    "certificate_search",  # F. 자격증 기반 검색
    "path_analysis",  # G. 경로 기반 분석
    "ontology_update",  # H. 온톨로지 업데이트 요청 (사용자 주도)
    "global_analysis",  # I. 거시적 분석 (커뮤니티 요약 기반)
    "unknown",  # 분류 불가
]

# Intent 분류에 사용 가능한 의도 목록 (unknown 제외)
AVAILABLE_INTENTS: list[str] = [
    "personnel_search",
    "project_matching",
    "relationship_search",
    "org_analysis",
    "mentoring_network",
    "certificate_search",
    "path_analysis",
    "ontology_update",
    "global_analysis",
]

# 특정 엔티티 없이도 Cypher 생성이 가능한 집계/통계 intent
# (route_after_resolver에서 전부 unresolved여도 clarification 대신 cypher_generator로 진행)
AGGREGATE_INTENTS: set[str] = {
    "global_analysis",
    "org_analysis",
    "mentoring_network",
    "certificate_search",
}

# 기본 엔티티 타입 (Neo4j 라벨과 일치)
DEFAULT_ENTITY_TYPES: list[str] = [
    "Employee",
    "Organization",
    "Department",
    "Position",
    "Project",
    "Skill",
    "Location",
    "Date",
]
