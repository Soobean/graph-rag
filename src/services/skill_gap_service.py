"""
Skill Gap Analysis Service

온톨로지 기반 스킬 갭 분석 서비스
- 팀의 스킬 커버리지 분석
- 유사 스킬 보유자 탐색 (IS_A 관계 기반)
- 갭 해소 추천
"""

import asyncio
import logging
from time import time
from typing import Any

from src.api.schemas.skill_gap import (
    CategoryCoverage,
    CoverageStatus,
    MatchType,
    RecommendedEmployee,
    SkillCategory,
    SkillCoverage,
    SkillGapAnalyzeResponse,
    SkillMatch,
    SkillRecommendResponse,
)
from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# 카테고리별 색상 정의 (UI 표시용)
CATEGORY_COLORS: dict[str, str] = {
    "Backend": "#10B981",
    "Frontend": "#F59E0B",
    "AI/ML": "#8B5CF6",
    "LLM Framework": "#EC4899",
    "Data": "#EF4444",
    "Cloud": "#0EA5E9",
    "DevOps": "#6366F1",
    "Programming": "#3B82F6",
}

DEFAULT_COLOR = "#6B7280"

# 매칭 타입별 우선순위 (낮을수록 더 강한 매칭)
MATCH_TYPE_PRIORITY: dict[MatchType, int] = {
    MatchType.EXACT: 0,
    MatchType.SYNONYM: 1,
    MatchType.SAME_CATEGORY: 2,
    MatchType.PARENT_CATEGORY: 3,
    MatchType.RELATED: 4,
    MatchType.NONE: 99,
}

# 표시할 최대 스킬 개수
MAX_DISPLAY_SKILLS = 5

# 외부 검색 시 최대 동의어 개수
MAX_EXTERNAL_SEARCH_KEYWORDS = 3

# Partial 커버리지 가중치 (0.5 = 유사 스킬 보유자는 교육 후 전환 가능하므로 50%로 계산)
PARTIAL_COVERAGE_WEIGHT = 0.5

# LCA 쿼리 최대 깊이 (온톨로지 계층 탐색 제한)
LCA_MAX_DEPTH = 3

# 캐시 TTL (초) - 5분 후 자동 만료
CACHE_TTL_SECONDS = 300


class SkillGapService:
    """온톨로지 기반 스킬 갭 분석 서비스"""

    def __init__(self, neo4j_repository: Neo4jRepository):
        self._neo4j = neo4j_repository
        # 캐시: 반복 조회 방지 (TTL 적용으로 메모리 누수 방지)
        self._category_cache: dict[str, str | None] = {}
        self._canonical_cache: dict[str, str | None] = {}
        self._relation_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
        self._cache_timestamp: float = time()

    def _clear_cache_if_expired(self) -> None:
        """TTL 초과 시 캐시 초기화 (메모리 누수 방지)"""
        if time() - self._cache_timestamp > CACHE_TTL_SECONDS:
            self._category_cache.clear()
            self._canonical_cache.clear()
            self._relation_cache.clear()
            self._cache_timestamp = time()
            logger.debug("Cache cleared due to TTL expiration")

    async def analyze(
        self,
        required_skills: list[str],
        team_members: list[str],
    ) -> SkillGapAnalyzeResponse:
        """
        스킬 갭 분석 메인 로직

        Args:
            required_skills: 필요한 스킬 목록
            team_members: 분석 대상 팀원 목록

        Returns:
            SkillGapAnalyzeResponse
        """
        # TTL 초과 시 캐시 자동 정리 (메모리 누수 방지)
        self._clear_cache_if_expired()

        logger.info(
            f"Analyzing skill gap: skills={required_skills}, members={team_members}"
        )

        # 1. 팀원들의 스킬 수집
        team_skills = await self._get_team_skills(team_members)
        logger.debug(f"Team skills: {team_skills}")

        # 2. 모든 스킬의 메타데이터 미리 로드 (N+1 쿼리 방지)
        await self._prefetch_skill_metadata(required_skills, team_skills)

        # 3. 각 필요 스킬에 대해 커버리지 분석 (병렬 처리)
        tasks = [
            self._analyze_skill_coverage(skill, team_skills)
            for skill in required_skills
        ]
        skill_details = await asyncio.gather(*tasks)

        # 4. 카테고리별 요약 생성
        category_summary = self._summarize_by_category(list(skill_details))

        # 5. 전체 상태 결정
        overall_status = self._determine_overall_status(list(skill_details))

        # 6. 갭 목록 추출
        gaps = [s.skill for s in skill_details if s.status == CoverageStatus.GAP]

        # 7. 추천 생성
        recommendations = self._generate_recommendations(list(skill_details))

        return SkillGapAnalyzeResponse(
            team_members=team_members,
            total_required_skills=len(required_skills),
            overall_status=overall_status,
            category_summary=category_summary,
            skill_details=list(skill_details),
            gaps=gaps,
            recommendations=recommendations,
        )

    async def recommend_for_skill(
        self,
        skill: str,
        exclude_members: list[str],
        limit: int = 5,
    ) -> SkillRecommendResponse:
        """
        특정 스킬 갭 해소를 위한 인력 추천

        Args:
            skill: 부족한 스킬
            exclude_members: 제외할 팀원 (이미 팀에 있는 인원)
            limit: 추천 인원 수

        Returns:
            SkillRecommendResponse
        """
        logger.info(f"Recommending for skill: {skill}, exclude={exclude_members}")

        # 스킬 카테고리 조회
        category = await self._get_skill_category(skill)

        # 내부 추천 인력 조회
        internal_candidates = await self._find_internal_candidates(
            skill, exclude_members, limit
        )

        # 외부 채용 검색 키워드 생성
        external_query = await self._generate_external_search_query(skill)

        return SkillRecommendResponse(
            target_skill=skill,
            category=category,
            internal_candidates=internal_candidates,
            external_search_query=external_query,
        )

    async def get_categories(self) -> list[SkillCategory]:
        """스킬 카테고리 목록 조회"""
        query = """
        MATCH (skill:Concept {type: 'skill'})-[:IS_A]->(category:Concept)
        WHERE category.type IN ['subcategory', 'category']
        WITH category.name AS cat, collect(DISTINCT skill.name) AS skills
        RETURN cat AS category, skills
        ORDER BY cat
        """

        try:
            results = await self._neo4j.execute_cypher(query)
            categories = []
            for row in results:
                cat_name = row["category"]
                categories.append(
                    SkillCategory(
                        name=cat_name,
                        color=CATEGORY_COLORS.get(cat_name, DEFAULT_COLOR),
                        skills=row["skills"],
                    )
                )
            return categories
        except Exception as e:
            logger.error(f"Failed to get categories: {e}")
            return []

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _prefetch_skill_metadata(
        self,
        required_skills: list[str],
        team_skills: dict[str, list[str]],
    ) -> None:
        """
        모든 스킬의 메타데이터 일괄 조회 (N+1 쿼리 방지)

        canonical 이름과 카테고리를 한 번의 쿼리로 조회하여 캐시에 저장합니다.
        """
        # 모든 스킬 수집
        all_skills: set[str] = set(required_skills)
        for skills in team_skills.values():
            all_skills.update(skills)

        # 캐시되지 않은 스킬만 필터링
        # (canonical과 category는 동시에 캐싱되므로 하나만 체크)
        uncached_skills = [
            s for s in all_skills
            if s not in self._canonical_cache
        ]

        if not uncached_skills:
            return

        query = """
        UNWIND $skills AS skill_name
        OPTIONAL MATCH (s:Concept {name: skill_name})
        OPTIONAL MATCH (s)-[:SAME_AS]->(canonical:Concept {is_canonical: true})
        OPTIONAL MATCH (s)-[:IS_A]->(category)
        RETURN skill_name,
               canonical.name AS canonical,
               category.name AS category
        """

        try:
            results = await self._neo4j.execute_cypher(
                query, {"skills": uncached_skills}
            )

            for row in results:
                skill = row["skill_name"]
                self._canonical_cache[skill] = row.get("canonical")
                self._category_cache[skill] = row.get("category")

            logger.debug(f"Prefetched metadata for {len(uncached_skills)} skills")

        except Exception as e:
            logger.warning(f"Failed to prefetch skill metadata: {e}")

    async def _get_team_skills(
        self, team_members: list[str]
    ) -> dict[str, list[str]]:
        """팀원들의 스킬 조회"""
        query = """
        MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill)
        WHERE e.name IN $members
        RETURN e.name AS employee, collect(s.name) AS skills
        """

        try:
            results = await self._neo4j.execute_cypher(
                query, {"members": team_members}
            )
            return {row["employee"]: row["skills"] for row in results}
        except Exception as e:
            logger.error(f"Failed to get team skills: {e}")
            return {}

    async def _analyze_skill_coverage(
        self,
        required_skill: str,
        team_skills: dict[str, list[str]],
    ) -> SkillCoverage:
        """단일 스킬 커버리지 분석"""
        exact_matches: list[str] = []
        similar_matches: list[SkillMatch] = []

        # 스킬 카테고리 조회 (캐시 사용)
        category = await self._get_skill_category(required_skill)

        # 필요 스킬의 canonical 이름 (없으면 자기 자신이 canonical)
        required_canonical = await self._get_canonical_skill(required_skill) or required_skill

        for employee, skills in team_skills.items():
            # 1. 정확히 일치하는지 확인
            if required_skill in skills:
                exact_matches.append(employee)
                continue

            # 2. 동의어 확인: 팀원 스킬의 canonical이 required_canonical과 같으면 동의어
            synonym_found = False
            for skill in skills:
                skill_canonical = await self._get_canonical_skill(skill) or skill
                if skill_canonical == required_canonical:
                    exact_matches.append(employee)
                    synonym_found = True
                    break

            if synonym_found:
                continue

            # 3. 유사 스킬 확인 - 가장 강한 매칭 선택
            best_match: SkillMatch | None = None
            best_priority = 99

            for skill in skills:
                match_info = await self._find_skill_relation(required_skill, skill)
                if match_info and match_info["match_type"] != MatchType.NONE:
                    priority = MATCH_TYPE_PRIORITY.get(match_info["match_type"], 99)
                    if priority < best_priority:
                        best_priority = priority
                        best_match = SkillMatch(
                            employee_name=employee,
                            possessed_skill=skill,
                            match_type=match_info["match_type"],
                            common_ancestor=match_info.get("common_ancestor"),
                            explanation=match_info["explanation"],
                        )

            if best_match:
                similar_matches.append(best_match)

        # 상태 결정
        if exact_matches:
            status = CoverageStatus.COVERED
            explanation = f"{', '.join(exact_matches)}이(가) {required_skill}을(를) 직접 보유"
        elif similar_matches:
            status = CoverageStatus.PARTIAL
            names = [m.employee_name for m in similar_matches]
            explanation = (
                f"직접 보유자 없음. "
                f"{', '.join(names)}이(가) 유사 스킬 보유"
            )
        else:
            status = CoverageStatus.GAP
            explanation = "관련 스킬 보유자 없음"

        return SkillCoverage(
            skill=required_skill,
            category=category,
            category_color=CATEGORY_COLORS.get(category, DEFAULT_COLOR) if category is not None else None,
            status=status,
            exact_matches=exact_matches,
            similar_matches=similar_matches,
            explanation=explanation,
        )

    async def _get_skill_category(self, skill: str) -> str | None:
        """스킬의 카테고리 조회 (캐시 사용)"""
        if skill in self._category_cache:
            return self._category_cache[skill]

        query = """
        MATCH (s:Concept {name: $skill})-[:IS_A]->(category)
        RETURN category.name AS category
        LIMIT 1
        """

        try:
            results = await self._neo4j.execute_cypher(query, {"skill": skill})
            category = results[0]["category"] if results else None
            self._category_cache[skill] = category
            return category
        except Exception as e:
            logger.warning(f"Failed to get category for {skill}: {e}")
            self._category_cache[skill] = None
            return None

    async def _get_canonical_skill(self, skill: str) -> str | None:
        """동의어의 정규 이름 조회 (캐시 사용)"""
        if skill in self._canonical_cache:
            return self._canonical_cache[skill]

        query = """
        MATCH (s:Concept {name: $skill})-[:SAME_AS]->(canonical:Concept {is_canonical: true})
        RETURN canonical.name AS canonical
        LIMIT 1
        """

        try:
            results = await self._neo4j.execute_cypher(query, {"skill": skill})
            canonical = results[0]["canonical"] if results else None
            self._canonical_cache[skill] = canonical
            return canonical
        except Exception as e:
            logger.warning(f"Failed to get canonical for {skill}: {e}")
            self._canonical_cache[skill] = None
            return None

    async def _find_skill_relation(
        self,
        required: str,
        possessed: str,
    ) -> dict[str, Any] | None:
        """
        두 스킬 간 온톨로지 관계 찾기 (최적화된 LCA 쿼리)

        Note:
            계층 탐색 깊이는 3단계로 고정 (Skill -> Subcategory -> Category)
        """
        cache_key = (required, possessed)
        if cache_key in self._relation_cache:
            return self._relation_cache[cache_key]

        query = """
        MATCH (s1:Concept {name: $required})-[:IS_A*0..3]->(ancestor)<-[:IS_A*0..3]-(s2:Concept {name: $possessed})
        RETURN ancestor.name AS common_ancestor
        LIMIT 1
        """

        result: dict[str, Any] | None = None

        try:
            results = await self._neo4j.execute_cypher(
                query, {"required": required, "possessed": possessed}
            )

            if not results:
                self._relation_cache[cache_key] = None
                return None

            common_ancestor = results[0].get("common_ancestor")
            if not common_ancestor:
                self._relation_cache[cache_key] = None
                return None

            # 공통 조상이 스킬 자체인 경우 (동의어)
            if common_ancestor == required or common_ancestor == possessed:
                result = {
                    "match_type": MatchType.SYNONYM,
                    "common_ancestor": None,
                    "explanation": f"{possessed}은(는) {required}의 동의어",
                }
            else:
                result = {
                    "match_type": MatchType.SAME_CATEGORY,
                    "common_ancestor": common_ancestor,
                    "explanation": f"같은 {common_ancestor} 카테고리",
                }

        except Exception as e:
            logger.warning(f"Failed to find relation: {required} ↔ {possessed}: {e}")

        self._relation_cache[cache_key] = result
        return result

    async def _find_internal_candidates(
        self,
        skill: str,
        exclude_members: list[str],
        limit: int,
    ) -> list[RecommendedEmployee]:
        """내부 교육 추천 인력 찾기 (N+1 쿼리 제거)"""
        # 단일 쿼리로 후보자와 스킬을 함께 조회
        query = """
        // 타겟 스킬의 형제 스킬 찾기
        MATCH (target:Concept {name: $skill})-[:IS_A]->(parent)
        MATCH (sibling:Concept)-[:IS_A]->(parent)
        WHERE sibling.name <> $skill

        // 형제 스킬을 가진 직원 찾기
        MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill {name: sibling.name})
        WHERE NOT e.name IN $exclude

        OPTIONAL MATCH (e)-[:BELONGS_TO]->(d:Department)

        // 해당 직원의 모든 스킬도 함께 조회
        OPTIONAL MATCH (e)-[:HAS_SKILL]->(all_skills:Skill)

        WITH e, sibling, parent, d,
             sibling.name AS matched_skill,
             collect(DISTINCT all_skills.name) AS all_skills

        RETURN e.name AS employee,
               d.name AS department,
               matched_skill,
               parent.name AS common_category,
               all_skills
        LIMIT $limit
        """

        try:
            results = await self._neo4j.execute_cypher(
                query,
                {"skill": skill, "exclude": exclude_members, "limit": limit},
            )

            candidates = []
            for row in results:
                # COLLECT는 항상 리스트 반환 (None 아님)
                all_skills = row["all_skills"]
                candidates.append(
                    RecommendedEmployee(
                        name=row["employee"],
                        department=row["department"],
                        current_skills=all_skills[:MAX_DISPLAY_SKILLS],
                        match_type=MatchType.SAME_CATEGORY,
                        matched_skill=row["matched_skill"],
                        reason=f"{row['matched_skill']} 보유 (같은 {row['common_category']})",
                    )
                )

            return candidates

        except Exception as e:
            logger.error(f"Failed to find internal candidates: {e}")
            return []

    async def _generate_external_search_query(self, skill: str) -> str:
        """외부 채용 검색 키워드 생성"""
        # 동의어 조회
        query = """
        MATCH (s:Concept {name: $skill})-[:SAME_AS]-(synonym)
        RETURN collect(DISTINCT synonym.name) AS synonyms
        """

        try:
            results = await self._neo4j.execute_cypher(query, {"skill": skill})
            synonyms = results[0]["synonyms"] if results else []

            # 검색 키워드 조합
            keywords = [skill] + [s for s in synonyms if s != skill][:MAX_EXTERNAL_SEARCH_KEYWORDS]
            return " OR ".join(keywords)

        except Exception as e:
            logger.warning(f"Failed to generate search query: {e}")
            return skill

    def _summarize_by_category(
        self, skill_details: list[SkillCoverage]
    ) -> list[CategoryCoverage]:
        """카테고리별 커버리지 요약"""
        category_map: dict[str, dict[str, Any]] = {}

        for skill in skill_details:
            cat = skill.category or "기타"

            if cat not in category_map:
                category_map[cat] = {
                    "total": 0,
                    "covered": 0,
                    "partial": 0,
                    "gap": 0,
                }

            category_map[cat]["total"] += 1

            if skill.status == CoverageStatus.COVERED:
                category_map[cat]["covered"] += 1
            elif skill.status == CoverageStatus.PARTIAL:
                category_map[cat]["partial"] += 1
            else:
                category_map[cat]["gap"] += 1

        result = []
        for cat, stats in category_map.items():
            total = stats["total"]
            covered = stats["covered"]
            partial = stats["partial"]

            # 커버리지 비율 계산
            ratio = (covered + partial * PARTIAL_COVERAGE_WEIGHT) / total if total > 0 else 0

            result.append(
                CategoryCoverage(
                    category=cat,
                    color=CATEGORY_COLORS.get(cat, DEFAULT_COLOR),
                    total_skills=total,
                    covered_count=covered,
                    partial_count=partial,
                    gap_count=stats["gap"],
                    coverage_ratio=round(ratio, 2),
                )
            )

        return sorted(result, key=lambda x: x.coverage_ratio)

    def _determine_overall_status(
        self, skill_details: list[SkillCoverage]
    ) -> CoverageStatus:
        """전체 상태 결정"""
        if not skill_details:
            return CoverageStatus.GAP

        statuses = [s.status for s in skill_details]

        if all(s == CoverageStatus.COVERED for s in statuses):
            return CoverageStatus.COVERED
        elif any(s == CoverageStatus.GAP for s in statuses):
            return CoverageStatus.GAP
        else:
            return CoverageStatus.PARTIAL

    def _generate_recommendations(
        self, skill_details: list[SkillCoverage]
    ) -> list[str]:
        """갭 해소 추천 메시지 생성"""
        recommendations = []

        for skill in skill_details:
            if skill.status == CoverageStatus.PARTIAL:
                # 유사 스킬 보유자에게 교육 추천
                for match in skill.similar_matches[:1]:
                    recommendations.append(
                        f"{match.possessed_skill} 경험자({match.employee_name})에게 "
                        f"{skill.skill} 교육 추천"
                    )

            elif skill.status == CoverageStatus.GAP:
                # 충원 필요
                recommendations.append(f"{skill.skill} 전문가 충원 필요")

        return recommendations
