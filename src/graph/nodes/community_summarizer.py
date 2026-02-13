"""
Community Summarizer Node

커뮤니티 기반 거시적 분석 노드.
조직 전체의 집계 데이터를 Neo4j에서 조회하고 LLM으로 요약합니다.

Global RAG 패턴: 특정 엔티티 검색(Local) 대신 집계/요약(Global) 제공.
"""

import json
import logging
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage

from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository, ModelTier
from src.repositories.neo4j_repository import Neo4jRepository
from src.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class CommunitySummarizerUpdate(TypedDict, total=False):
    response: str
    messages: list[BaseMessage]
    graph_results: list[dict[str, Any]]
    execution_path: list[str]
    error: str | None


class CommunitySummarizerNode(BaseNode[CommunitySummarizerUpdate]):
    """커뮤니티 기반 거시적 분석 노드"""

    def __init__(
        self,
        neo4j_repository: Neo4jRepository,
        llm_repository: LLMRepository,
    ):
        super().__init__()
        self._neo4j = neo4j_repository
        self._llm = llm_repository
        self._prompt_manager = PromptManager()

    @property
    def name(self) -> str:
        return "community_summarizer"

    @property
    def input_keys(self) -> list[str]:
        return ["question", "intent", "entities"]

    async def _process(self, state: GraphRAGState) -> CommunitySummarizerUpdate:
        question = state.get("question", "")

        # Phase 1: 캐시 확인
        try:
            cached = await self._find_cached_summary(question)
            if cached:
                self._logger.info("Cache hit for global analysis question")
                source_data = cached.get("source_data", "[]")
                try:
                    graph_results = json.loads(source_data) if isinstance(source_data, str) else []
                except (json.JSONDecodeError, TypeError):
                    graph_results = []
                return CommunitySummarizerUpdate(
                    response=cached["summary"],
                    messages=[AIMessage(content=cached["summary"])],
                    graph_results=graph_results,
                    execution_path=["community_summarizer_cached"],
                )
        except Exception as e:
            self._logger.warning(f"Cache check failed, proceeding without cache: {e}")

        # Phase 2: 커뮤니티 데이터 집계
        try:
            department_stats = await self._get_department_stats()
            project_stats = await self._get_project_stats()
            skill_distribution = await self._get_skill_distribution()
        except Exception as e:
            self._logger.error(f"Data aggregation failed: {e}")
            error_msg = "조직 데이터를 조회하는 중 오류가 발생했습니다."
            return CommunitySummarizerUpdate(
                response=error_msg,
                messages=[AIMessage(content=error_msg)],
                graph_results=[],
                execution_path=["community_summarizer_error"],
                error=str(e),
            )

        # 데이터가 모두 비어있는 경우
        if not department_stats and not project_stats and not skill_distribution:
            empty_msg = "조직 데이터가 아직 등록되지 않았습니다. 데이터를 추가한 후 다시 질문해 주세요."
            return CommunitySummarizerUpdate(
                response=empty_msg,
                messages=[AIMessage(content=empty_msg)],
                graph_results=[],
                execution_path=["community_summarizer_empty"],
            )

        # Phase 3: LLM 요약 생성
        context = self._format_community_context(
            department_stats, project_stats, skill_distribution
        )
        try:
            prompt = self._prompt_manager.load_prompt("community_summary")
            system_prompt = prompt["system"]
            user_prompt = prompt["user"].format(
                context=context,
                question=question,
            )
            summary = await self._llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_tier=ModelTier.HEAVY,
            )
        except Exception as e:
            self._logger.error(f"LLM summary generation failed: {e}")
            summary = f"## 조직 데이터 요약\n\n{context}"

        # Phase 4: 그래프 시각화용 합성 데이터 생성
        community_graph = self._build_community_graph(
            department_stats, skill_distribution
        )

        # Phase 5: 캐시 저장
        try:
            await self._save_summary_cache(
                question, summary, json.dumps(community_graph, ensure_ascii=False)
            )
        except Exception as e:
            self._logger.warning(f"Cache save failed: {e}")

        return CommunitySummarizerUpdate(
            response=summary,
            messages=[AIMessage(content=summary)],
            graph_results=community_graph,
            execution_path=["community_summarizer"],
        )

    # ─── Data Aggregation Queries ───────────────────────────

    async def _get_department_stats(self) -> list[dict[str, Any]]:
        """부서별 인력 + 스킬 분포"""
        return await self._neo4j.execute_cypher("""
            MATCH (e:Employee)
            WITH e.department AS dept, collect(DISTINCT e.name) AS names
            WITH dept, size(names) AS headcount
            OPTIONAL MATCH (e2:Employee)-[:HAS_SKILL]->(s:Skill)
            WHERE e2.department = dept
            WITH dept, headcount,
                 count(DISTINCT s.name) AS unique_skills,
                 collect(DISTINCT s.name)[0..10] AS top_skills
            RETURN dept, headcount, unique_skills, top_skills
            ORDER BY headcount DESC
        """)

    async def _get_project_stats(self) -> list[dict[str, Any]]:
        """프로젝트 포트폴리오 현황"""
        return await self._neo4j.execute_cypher("""
            MATCH (p:Project)
            WITH p.status AS status, count(*) AS cnt,
                 collect(p.name)[0..5] AS sample_projects
            RETURN status, cnt, sample_projects
            ORDER BY cnt DESC
        """)

    async def _get_skill_distribution(self) -> list[dict[str, Any]]:
        """전체 스킬 분포 Top 15"""
        return await self._neo4j.execute_cypher("""
            MATCH (e:Employee)-[:HAS_SKILL]->(s:Skill)
            WITH s.name AS skill, collect(DISTINCT e.name) AS holders_list
            WITH skill, size(holders_list) AS holders
            RETURN skill, holders
            ORDER BY holders DESC
            LIMIT 15
        """)

    # ─── Context Formatting ─────────────────────────────────

    @staticmethod
    def _format_community_context(
        department_stats: list[dict[str, Any]],
        project_stats: list[dict[str, Any]],
        skill_distribution: list[dict[str, Any]],
    ) -> str:
        sections: list[str] = []

        if department_stats:
            lines = ["### 부서별 현황"]
            for d in department_stats:
                dept = d.get("dept") or "Unknown"
                hc = d.get("headcount", 0)
                us = d.get("unique_skills", 0)
                top = ", ".join(d.get("top_skills") or [])
                lines.append(f"- {dept}: 인원 {hc}명, 보유 스킬 {us}종 (주요: {top})")
            sections.append("\n".join(lines))

        if project_stats:
            lines = ["### 프로젝트 현황"]
            for p in project_stats:
                status = p.get("status") or "미지정"
                cnt = p.get("cnt", 0)
                samples = ", ".join(p.get("sample_projects") or [])
                lines.append(f"- {status}: {cnt}건 (예: {samples})")
            sections.append("\n".join(lines))

        if skill_distribution:
            lines = ["### 스킬 분포 Top 15"]
            for s in skill_distribution:
                skill = s.get("skill", "")
                holders = s.get("holders", 0)
                lines.append(f"- {skill}: {holders}명 보유")
            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    # ─── Synthetic Graph Data ───────────────────────────────

    @staticmethod
    def _build_community_graph(
        department_stats: list[dict[str, Any]],
        skill_distribution: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """부서↔스킬 네트워크 그래프 데이터 생성 (Neo4j-like 형식)"""
        graph_results: list[dict[str, Any]] = []

        # 1) Department 노드
        for dept in department_stats:
            dept_name = dept.get("dept") or "Unknown"
            graph_results.append({
                "node": {
                    "id": f"dept_{dept_name}",
                    "labels": ["Department"],
                    "properties": {
                        "name": dept_name,
                        "headcount": dept.get("headcount", 0),
                        "unique_skills": dept.get("unique_skills", 0),
                    },
                }
            })

        # 2) Top Skill 노드
        skill_set: set[str] = set()
        for row in skill_distribution:
            skill_name = row.get("skill", "")
            if skill_name:
                skill_set.add(skill_name)
                graph_results.append({
                    "node": {
                        "id": f"skill_{skill_name}",
                        "labels": ["Skill"],
                        "properties": {
                            "name": skill_name,
                            "holders": row.get("holders", 0),
                        },
                    }
                })

        # 3) Department → Skill 엣지 (top_skills 기반)
        edge_idx = 0
        for dept in department_stats:
            dept_name = dept.get("dept") or "Unknown"
            for skill_name in dept.get("top_skills") or []:
                if skill_name in skill_set:
                    graph_results.append({
                        "rel": {
                            "id": f"edge_{edge_idx}",
                            "type": "DEPT_HAS_SKILL",
                            "startNodeId": f"dept_{dept_name}",
                            "endNodeId": f"skill_{skill_name}",
                            "properties": {},
                        }
                    })
                    edge_idx += 1

        return graph_results

    # ─── Cache ──────────────────────────────────────────────

    async def _find_cached_summary(self, question: str) -> dict[str, Any] | None:
        """키워드 기반 캐시 검색 (24시간 TTL)"""
        results = await self._neo4j.execute_cypher("""
            MATCH (cs:CommunitySummary)
            WHERE cs.created_at > datetime() - duration('PT24H')
            RETURN cs.question AS question, cs.summary AS summary,
                   cs.source_data AS source_data
            ORDER BY cs.created_at DESC
            LIMIT 5
        """)
        for row in results:
            cached_question = row.get("question", "")
            if cached_question and self._is_similar_question(question, cached_question):
                return dict(row)
        return None

    async def _save_summary_cache(
        self, question: str, summary: str, source_data: str
    ) -> None:
        await self._neo4j.execute_cypher(
            """
            CREATE (cs:CommunitySummary {
                question: $question,
                summary: $summary,
                source_data: $source_data,
                created_at: datetime()
            })
            """,
            {"question": question, "summary": summary, "source_data": source_data},
        )

    # ─── Keyword Similarity (MVP) ──────────────────────────

    @staticmethod
    def _is_similar_question(q1: str, q2: str) -> bool:
        """간단한 키워드 오버랩 기반 유사도 (MVP)"""
        stopwords = {
            "은", "는", "이", "가", "을", "를", "의", "에", "에서",
            "로", "해줘", "알려줘", "뭐야", "뭔가요", "좀", "어떤",
        }
        tokens1 = {t for t in q1.split() if t not in stopwords}
        tokens2 = {t for t in q2.split() if t not in stopwords}
        if not tokens1 or not tokens2:
            return False
        overlap = len(tokens1 & tokens2) / max(len(tokens1), len(tokens2))
        return overlap >= 0.6
