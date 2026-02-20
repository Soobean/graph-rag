"""
Project Staffing Service

비용 기반 프로젝트 인력 배치 서비스
- 프로젝트 후보자 탐색 (예산 내)
- 스태핑 플랜 + 예상 비용
- 예산 대비 인건비 분석
"""

import logging
from typing import Any

from src.api.schemas.staffing import (
    BudgetAnalysisResponse,
    CandidateInfo,
    FindCandidatesResponse,
    ProjectListItem,
    ProjectParticipation,
    RecommendedCandidate,
    SkillCandidates,
    SkillCategory,
    SkillStaffingPlan,
    StaffingPlanResponse,
    TeamMemberCost,
)
from src.domain.constants import (
    PROFICIENCY_MAP,
    PROJECT_STATUS_ACTIVE,
    PROJECT_STATUS_PLANNED,
    active_statuses_literal,
    build_proficiency_case_cypher,
    tolower_match,
)
from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)

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


class ProjectStaffingService:
    """비용 기반 프로젝트 인력 배치 서비스"""

    def __init__(self, neo4j_repository: Neo4jRepository):
        self._neo4j = neo4j_repository

    # =========================================================================
    # 프로젝트 목록 조회
    # =========================================================================

    async def list_projects(self) -> list[ProjectListItem]:
        """
        프로젝트 목록 조회 (프론트엔드 드롭다운용)

        Returns:
            프로젝트 이름, 상태, 예산, 필요 인원 목록
        """
        query = """
        MATCH (p:Project)
        WITH p.name AS name,
             max(p.status) AS status,
             max(p.budget_million) AS budget_million,
             max(p.required_headcount) AS required_headcount
        RETURN name, status, budget_million, required_headcount
        ORDER BY name
        """

        results = await self._neo4j.execute_cypher(query)
        return [
            ProjectListItem(
                name=row["name"],
                status=row.get("status"),
                budget_million=row.get("budget_million"),
                required_headcount=row.get("required_headcount"),
            )
            for row in results
        ]

    # =========================================================================
    # Scenario 1: 프로젝트 후보자 탐색
    # =========================================================================

    async def find_candidates(
        self,
        project_name: str,
        skill_name: str | None = None,
        min_proficiency: int | None = None,
    ) -> FindCandidatesResponse:
        """
        프로젝트의 REQUIRES 스킬별 적격 후보자를 탐색합니다.

        - proficiency >= required_proficiency
        - effective_rate <= max_hourly_rate (설정된 경우)
        - availability IN ['available', 'partial']
        - active_projects < max_projects
        - 단가 오름차순 정렬

        Args:
            project_name: 프로젝트 이름
            skill_name: 특정 스킬 필터 (None이면 전체)
            min_proficiency: 최소 숙련도 필터

        Returns:
            FindCandidatesResponse

        Raises:
            ValueError: 프로젝트가 존재하지 않는 경우
        """
        # 1. 프로젝트 상세 조회
        project = await self._get_project_info(project_name)

        # 2. REQUIRES 스킬 목록 조회
        requirements = await self._get_project_requirements(
            project_name, skill_name
        )

        # 3. 스킬별 후보자 탐색
        skill_candidates_list: list[SkillCandidates] = []
        all_candidate_names: set[str] = set()

        for req in requirements:
            req_skill = req["skill_name"]
            req_proficiency_raw = req.get("required_proficiency")
            max_rate = req.get("max_hourly_rate")
            headcount = req.get("required_headcount")
            importance = req.get("importance")

            # DB에 한글 문자열("초급"~"전문가")로 저장됨 → 숫자로 변환
            if isinstance(req_proficiency_raw, str):
                req_proficiency = PROFICIENCY_MAP.get(req_proficiency_raw, 0)
            else:
                req_proficiency = req_proficiency_raw

            # min_proficiency 파라미터가 있으면 우선 사용
            effective_min_prof = (
                min_proficiency if min_proficiency is not None else req_proficiency
            )

            candidates = await self._find_skill_candidates(
                skill_name=req_skill,
                min_proficiency=effective_min_prof,
                max_hourly_rate=max_rate,
            )

            # 매칭 점수 계산 및 점수 DESC 정렬
            candidates = [
                self._compute_match_context(c, req_proficiency, max_rate)
                for c in candidates
            ]
            candidates.sort(key=lambda c: (-c.match_score, c.effective_rate))

            for c in candidates:
                all_candidate_names.add(c.employee_name)

            skill_candidates_list.append(
                SkillCandidates(
                    skill_name=req_skill,
                    required_proficiency=req_proficiency,
                    max_hourly_rate=max_rate,
                    required_headcount=headcount,
                    importance=importance,
                    candidates=candidates,
                )
            )

        return FindCandidatesResponse(
            project_name=project_name,
            project_budget=project.get("budget_million"),
            estimated_hours=project.get("estimated_hours"),
            required_headcount=project.get("required_headcount"),
            skill_candidates=skill_candidates_list,
            total_skills=len(skill_candidates_list),
            total_candidates=len(all_candidate_names),
        )

    # =========================================================================
    # Scenario 2: 스태핑 플랜 + 예상 비용
    # =========================================================================

    async def generate_staffing_plan(
        self,
        project_name: str,
        top_n_per_skill: int = 3,
    ) -> StaffingPlanResponse:
        """
        프로젝트 스태핑 플랜을 생성합니다.

        find_candidates() 결과에서 top N을 선별하고 비용을 추정합니다.

        Args:
            project_name: 프로젝트 이름
            top_n_per_skill: 스킬당 추천 인원 수

        Returns:
            StaffingPlanResponse
        """
        # 후보자 탐색 결과 재사용
        candidates_result = await self.find_candidates(project_name)

        estimated_hours = candidates_result.estimated_hours or 0
        skill_plans: list[SkillStaffingPlan] = []
        total_cost = 0.0

        # 총 필요 인원으로 인당 시간 계산
        total_headcount = sum(
            sc.required_headcount or 1
            for sc in candidates_result.skill_candidates
        )
        hours_per_person = (
            estimated_hours / max(total_headcount, 1)
            if estimated_hours > 0
            else 0
        )

        for sc in candidates_result.skill_candidates:
            top_candidates = sc.candidates[:top_n_per_skill]

            recommended = [
                RecommendedCandidate(
                    employee_name=c.employee_name,
                    department=c.department,
                    proficiency=c.proficiency,
                    effective_rate=c.effective_rate,
                    availability=c.availability,
                    match_score=c.match_score,
                    match_reasons=c.match_reasons[:2],
                )
                for c in top_candidates
            ]

            # 시간당 비용 = 추천 인원의 effective_rate 합
            cost_per_hour = sum(c.effective_rate for c in top_candidates)

            # 스킬별 예상 비용 = 추천 팀의 시간당 비용 × 인당 시간
            if hours_per_person > 0 and top_candidates:
                skill_cost = cost_per_hour * hours_per_person
                total_cost += skill_cost

            skill_plans.append(
                SkillStaffingPlan(
                    skill_name=sc.skill_name,
                    importance=sc.importance,
                    required_headcount=sc.required_headcount,
                    recommended_candidates=recommended,
                    estimated_cost_per_hour=cost_per_hour,
                )
            )

        # 예산 활용률
        budget = candidates_result.project_budget
        budget_util = None
        if budget and budget > 0 and total_cost > 0:
            # budget은 백만원 단위이므로 변환
            budget_util = round((total_cost / (budget * 1_000_000)) * 100, 1)

        return StaffingPlanResponse(
            project_name=project_name,
            project_budget=candidates_result.project_budget,
            estimated_hours=estimated_hours if estimated_hours > 0 else None,
            skill_plans=skill_plans,
            total_estimated_labor_cost=round(total_cost, 0),
            budget_utilization_percent=budget_util,
        )

    # =========================================================================
    # Scenario 3: 예산 대비 인건비 분석
    # =========================================================================

    async def analyze_budget(
        self,
        project_name: str,
    ) -> BudgetAnalysisResponse:
        """
        프로젝트의 예산 대비 인건비를 분석합니다.

        Args:
            project_name: 프로젝트 이름

        Returns:
            BudgetAnalysisResponse

        Raises:
            ValueError: 프로젝트가 존재하지 않는 경우
        """
        # 프로젝트 정보 + 팀원 비용 내역 조회
        project = await self._get_project_info(project_name)

        query = f"""
        MATCH (e:Employee)-[w:WORKS_ON]->(p:Project)
        WHERE {tolower_match("p.name", "project_name")}
        WITH e.name AS emp_name,
             max(w.role) AS role,
             max(w.agreed_rate) AS agreed_rate,
             max(w.allocated_hours) AS allocated_hours,
             max(w.actual_hours) AS actual_hours
        RETURN emp_name, role, agreed_rate, allocated_hours, actual_hours
        ORDER BY emp_name
        """

        results = await self._neo4j.execute_cypher(
            query, {"project_name": project_name}
        )

        team_breakdown: list[TeamMemberCost] = []
        total_planned = 0.0
        total_actual = 0.0

        for row in results:
            agreed = row.get("agreed_rate") or 0.0
            allocated = row.get("allocated_hours") or 0.0
            actual = row.get("actual_hours") or 0.0
            planned_cost = agreed * allocated
            actual_cost = agreed * actual

            total_planned += planned_cost
            total_actual += actual_cost

            team_breakdown.append(
                TeamMemberCost(
                    employee_name=row["emp_name"],
                    role=row.get("role"),
                    agreed_rate=agreed,
                    allocated_hours=allocated,
                    actual_hours=actual,
                    planned_cost=planned_cost,
                    actual_cost=actual_cost,
                )
            )

        variance = total_actual - total_planned
        variance_pct = None
        if total_planned > 0:
            variance_pct = round((variance / total_planned) * 100, 1)

        return BudgetAnalysisResponse(
            project_name=project_name,
            project_budget=project.get("budget_million"),
            budget_allocated=project.get("budget_allocated"),
            budget_spent=project.get("budget_spent"),
            team_breakdown=team_breakdown,
            total_planned_cost=round(total_planned, 0),
            total_actual_cost=round(total_actual, 0),
            variance=round(variance, 0),
            variance_percent=variance_pct,
        )

    # =========================================================================
    # 공통: 카테고리 목록
    # =========================================================================

    async def get_categories(self) -> list[SkillCategory]:
        """Skill 노드의 category 속성 기반 카테고리 목록 조회"""
        query = """
        MATCH (s:Skill)
        WHERE s.category IS NOT NULL
        WITH s.category AS cat, collect(DISTINCT s.name) AS skills
        RETURN cat AS category, skills
        ORDER BY cat
        """

        try:
            results = await self._neo4j.execute_cypher(query)
            return [
                SkillCategory(
                    name=row["category"],
                    color=CATEGORY_COLORS.get(row["category"], DEFAULT_COLOR),
                    skills=row["skills"],
                )
                for row in results
            ]
        except Exception as e:
            logger.error(f"Failed to get categories: {e}")
            return []

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _get_project_info(self, project_name: str) -> dict[str, Any]:
        """프로젝트 기본 정보 조회"""
        query = f"""
        MATCH (p:Project)
        WHERE {tolower_match("p.name", "project_name")}
        RETURN p.name AS name,
               p.budget_million AS budget_million,
               p.estimated_hours AS estimated_hours,
               p.required_headcount AS required_headcount,
               p.budget_allocated AS budget_allocated,
               p.budget_spent AS budget_spent,
               p.status AS status
        LIMIT 1
        """

        results = await self._neo4j.execute_cypher(
            query, {"project_name": project_name}
        )

        if not results:
            raise ValueError(f"프로젝트 '{project_name}'을(를) 찾을 수 없습니다")

        return dict(results[0])

    async def _get_project_requirements(
        self,
        project_name: str,
        skill_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """프로젝트의 REQUIRES 스킬 목록 조회"""
        skill_clause = ""
        params: dict[str, Any] = {"project_name": project_name}

        if skill_filter:
            skill_clause = f"AND {tolower_match('s.name', 'skill_filter')}"
            params["skill_filter"] = skill_filter

        query = f"""
        MATCH (p:Project)-[r:REQUIRES]->(s:Skill)
        WHERE {tolower_match("p.name", "project_name")}
        {skill_clause}
        // Project 중복 노드 대응: 스킬명 기반 그룹핑
        WITH s.name AS skill_name,
             max(r.required_proficiency) AS required_proficiency,
             max(r.max_hourly_rate) AS max_hourly_rate,
             max(r.required_headcount) AS required_headcount,
             max(r.importance) AS importance
        RETURN skill_name, required_proficiency, max_hourly_rate,
               required_headcount, importance
        ORDER BY importance DESC, skill_name
        """

        return [dict(row) for row in await self._neo4j.execute_cypher(query, params)]

    @staticmethod
    def _compute_workload(project_details: list[dict]) -> float:
        """
        프로젝트별 가중 워크로드를 합산합니다.

        각 프로젝트 부담 = base_weight × remaining_factor
          - base_weight: contribution_percent/100 (없으면 상태 기반 기본값)
          - remaining_factor: 1 - progress (진행률이 높을수록 잔여 부담 낮음)

        상태 기본값:
          - '진행중' → 1.0 (풀타임)
          - '계획'  → 0.3 (아직 본격 투입 전)
        """
        total = 0.0
        for proj in project_details:
            # Base weight: contribution_percent 우선, 없으면 상태 기반 기본값
            contrib = proj.get("contribution_pct")
            status = proj.get("status", PROJECT_STATUS_ACTIVE)
            if contrib and contrib > 0:
                base = contrib / 100
            else:
                base = 0.3 if status == PROJECT_STATUS_PLANNED else 1.0

            # Remaining factor: 진행률 기반 잔여 부담
            alloc = proj.get("allocated") or 0
            actual = proj.get("actual") or 0
            if alloc > 0 and actual >= 0:
                progress = min(actual / alloc, 0.95)  # 최대 95% (완전 0 방지)
                remaining = 1.0 - progress
            else:
                remaining = 1.0  # 시간 정보 없으면 보수적으로 풀부담

            total += base * remaining
        return round(total, 2)

    @staticmethod
    def _build_participations(
        project_details: list[dict],
    ) -> list[ProjectParticipation]:
        """project_details → ProjectParticipation 리스트 변환"""
        result = []
        for proj in project_details:
            alloc = proj.get("allocated") or 0
            actual = proj.get("actual") or 0
            progress = round(actual / alloc * 100, 0) if alloc > 0 else None
            result.append(
                ProjectParticipation(
                    project_name=proj.get("name", "unknown"),
                    status=proj.get("status"),
                    progress_pct=progress,
                    contribution_pct=proj.get("contribution_pct"),
                )
            )
        return result

    @staticmethod
    def _compute_availability_label(capacity_remaining: float) -> str:
        """잔여 여력 기반 투입 가능 여부 라벨 계산"""
        if capacity_remaining >= 2.0:
            return "가능"
        elif capacity_remaining >= 0.5:
            return "애매"
        return "빠듯"

    def _compute_match_context(
        self,
        candidate: CandidateInfo,
        req_proficiency: int | None,
        max_rate: float | None,
    ) -> CandidateInfo:
        """
        후보자의 매칭 점수·사유를 계산하여 새 CandidateInfo를 반환합니다.

        점수 (100점 만점 가중합):
          - 숙련도 (40점): 절대 스케일 prof/4 × 40, years_used 보정 ×(1+bonus)
          - 비용 효율 (35점): 예산 내 base 15 + 절약 보너스 최대 20
          - 가용성 (25점): remaining_capacity / max_proj × 25
        """
        score = 0.0
        reasons: list[str] = []

        prof = candidate.proficiency
        rate = candidate.effective_rate
        years_used = candidate.years_used
        max_proj = candidate.max_projects if candidate.max_projects > 0 else 5
        workload = candidate.effective_workload
        remaining_capacity = max(max_proj - workload, 0)

        # --- 숙련도 축 (40점) ---
        # 절대 스케일: 전문가(4)=40, 고급(3)=30, 중급(2)=20, 초급(1)=10
        # years_used 보정: 최대 +25% (10년 이상 사용 시)
        req_prof = req_proficiency or 1
        prof_gap = prof - req_prof

        base_prof_score = (prof / 4) * 40
        years_bonus = min(years_used / 10, 0.25)
        score += min(base_prof_score * (1 + years_bonus), 40)

        if prof_gap > 0:
            reasons.append(f"숙련도 {prof_gap}단계 초과 충족")
        elif prof_gap == 0:
            reasons.append("요구 숙련도 정확히 충족")
        else:
            reasons.append(f"숙련도 {abs(prof_gap)}단계 미달")

        if years_used >= 5:
            reasons.append(f"해당 스킬 {years_used}년 경력")
        elif years_used >= 2:
            reasons.append(f"해당 스킬 {years_used}년 사용")

        # --- 비용 효율 축 (35점) ---
        # 예산 있음: base 15점 + 절약 보너스 최대 20점
        # 예산 없음: 중립 17점 (예산 기준 없이 비용 비교 무의미)
        cost_eff: float | None = None
        if max_rate and max_rate > 0 and rate > 0:
            cost_eff = round((max_rate / rate) * 100, 1)
            savings_ratio = max(1 - rate / max_rate, 0)
            cost_score = savings_ratio * 20 + 15
            score += min(cost_score, 35)
            if savings_ratio >= 0.4:
                reasons.append("예산 대비 매우 저렴")
            elif savings_ratio >= 0.1:
                reasons.append("예산 범위 내")
            else:
                reasons.append("예산 상한 근접")
        else:
            score += 17

        # --- 가용성 축 (25점) ---
        # effective_workload 기반 (프로젝트 상태/진행률/투입비율 반영)
        if max_proj > 0:
            cap_ratio = remaining_capacity / max_proj
            score += min(cap_ratio * 25, 25)

        if remaining_capacity >= 2:
            reasons.append(f"가용 여력 {remaining_capacity:.1f}건")
        elif remaining_capacity >= 0.5:
            reasons.append(f"가용 여력 {remaining_capacity:.1f}건")
        else:
            reasons.append("마지막 프로젝트 슬롯")

        if candidate.availability == "available":
            reasons.append("즉시 투입 가능")

        return candidate.model_copy(
            update={
                "match_score": min(round(score), 100),
                "proficiency_gap": prof_gap,
                "cost_efficiency": cost_eff,
                "capacity_remaining": round(remaining_capacity, 1),
                "match_reasons": reasons,
                "availability_label": self._compute_availability_label(
                    remaining_capacity
                ),
            }
        )

    async def _find_skill_candidates(
        self,
        skill_name: str,
        min_proficiency: int | None = None,
        max_hourly_rate: float | None = None,
    ) -> list[CandidateInfo]:
        """
        특정 스킬의 적격 후보자를 탐색합니다.

        Employee 중복 노드를 e.name 기반으로 그룹핑하여 통합합니다.
        """
        proficiency_clause = ""
        rate_clause = ""
        params: dict[str, Any] = {"skill_name": skill_name}

        if min_proficiency is not None:
            proficiency_clause = "AND proficiency >= $min_proficiency"
            params["min_proficiency"] = min_proficiency

        if max_hourly_rate is not None:
            rate_clause = "AND effective_rate <= $max_hourly_rate"
            params["max_hourly_rate"] = max_hourly_rate

        proficiency_case = build_proficiency_case_cypher("hs.proficiency")
        active_statuses = active_statuses_literal()

        query = f"""
        // 스킬 보유자 조회 (Employee 중복 노드 통합)
        MATCH (e:Employee)-[hs:HAS_SKILL]->(s:Skill)
        WHERE {tolower_match("s.name", "skill_name")}

        // Employee name 기반 그룹핑 (중복 노드 대응)
        // proficiency: 한글 문자열("초급"~"전문가") → 숫자 변환 후 max
        // availability: min()으로 최적(available) 상태 우선
        WITH e.name AS emp_name,
             max({proficiency_case}) AS proficiency,
             min(hs.effective_rate) AS effective_rate,
             max(coalesce(hs.years_used, 0)) AS years_used,
             min(e.availability) AS availability,
             max(e.department) AS department,
             max(e.max_projects) AS max_projects

        // 숙련도·단가 필터 (availability 필터 제거 — 프로젝트 수 기반으로 대체)
        WHERE true
        {proficiency_clause}
        {rate_clause}

        // 진행중 프로젝트 상세 (프로젝트별 그룹핑, 중복 노드 대응)
        OPTIONAL MATCH (e2:Employee)-[w2:WORKS_ON]->(proj:Project)
        WHERE e2.name = emp_name AND proj.status IN {active_statuses}
        WITH emp_name, proficiency, effective_rate, years_used,
             availability, department, max_projects,
             proj.name AS proj_name,
             max(proj.status) AS proj_status,
             max(w2.contribution_percent) AS proj_contrib,
             max(w2.allocated_hours) AS proj_alloc,
             max(w2.actual_hours) AS proj_actual

        // 프로젝트별 정보를 리스트로 수집
        WITH emp_name, proficiency, effective_rate, years_used,
             availability, department, max_projects,
             count(proj_name) AS current_projects,
             [x IN collect(CASE WHEN proj_name IS NOT NULL THEN {{
               name: proj_name,
               status: proj_status,
               contribution_pct: proj_contrib,
               allocated: proj_alloc,
               actual: proj_actual
             }} END) WHERE x IS NOT NULL] AS project_details

        RETURN emp_name, department, proficiency, effective_rate,
               years_used, availability, current_projects, max_projects,
               project_details
        ORDER BY effective_rate ASC, proficiency DESC
        """

        try:
            results = await self._neo4j.execute_cypher(query, params)
            candidates = []
            for row in results:
                project_details = row.get("project_details") or []
                workload = self._compute_workload(project_details)
                raw_max = row.get("max_projects")
                max_proj = raw_max if raw_max is not None and raw_max > 0 else 5

                # 가중 워크로드 기반 필터 (워크로드 < 최대 프로젝트)
                if workload >= max_proj:
                    continue

                participations = self._build_participations(project_details)

                candidates.append(
                    CandidateInfo(
                        employee_name=row["emp_name"],
                        department=row.get("department"),
                        proficiency=row.get("proficiency") or 0,
                        effective_rate=row.get("effective_rate") or 0.0,
                        years_used=row.get("years_used") or 0,
                        availability=row.get("availability"),
                        current_projects=row.get("current_projects", 0),
                        max_projects=max_proj,
                        effective_workload=workload,
                        project_participations=participations,
                    )
                )
            return candidates
        except Exception as e:
            logger.error(
                f"Failed to find candidates for skill '{skill_name}': {e}"
            )
            return []
