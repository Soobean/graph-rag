"""
GDS (Graph Data Science) Service

Neo4j GDS 라이브러리를 활용한 그래프 분석 서비스
- 커뮤니티 탐지 (Leiden 알고리즘)
- 유사 직원 탐색
- 최적 팀 추천
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal

from graphdatascience import GraphDataScience

logger = logging.getLogger(__name__)


@dataclass
class CommunityResult:
    """커뮤니티 탐지 결과"""

    algorithm: str
    node_count: int
    community_count: int
    modularity: float
    communities: list[dict[str, Any]]


@dataclass
class TeamRecommendation:
    """팀 추천 결과"""

    members: list[dict[str, Any]]
    skill_coverage: float
    covered_skills: list[str]
    missing_skills: list[str]
    community_diversity: int
    total_score: float


class GDSService:
    """
    Neo4j GDS 기반 그래프 분석 서비스

    비동기 FastAPI와 호환되도록 ThreadPoolExecutor 사용
    (GDS Python 클라이언트가 동기식이므로)

    사용 예시:
        async with GDSService(...) as gds:
            communities = await gds.detect_communities()
            team = await gds.recommend_team(["Python", "AWS"])
    """

    # 기본 프로젝션 이름
    SKILL_PROJECTION = "employee_skill_graph"

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_workers: int = 2,
    ):
        """
        GDS 서비스 초기화

        Args:
            uri: Neo4j Bolt URI
            user: 사용자명
            password: 비밀번호
            database: 데이터베이스 이름
            max_workers: 동시 작업 스레드 수
        """
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database
        self._gds: GraphDataScience | None = None
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        logger.info(f"GDSService initialized: uri={uri}, database={database}")

    async def connect(self) -> None:
        """GDS 클라이언트 연결"""
        if self._gds is not None:
            return

        loop = asyncio.get_event_loop()
        self._gds = await loop.run_in_executor(
            self._executor,
            lambda: GraphDataScience(
                self._uri,
                auth=(self._user, self._password),
                database=self._database,
            ),
        )
        logger.info("GDS client connected")

    async def close(self) -> None:
        """리소스 정리"""
        if self._gds:
            self._gds = None
        # wait=True로 진행 중인 작업 완료 대기 (리소스 누수 방지)
        self._executor.shutdown(wait=True)
        logger.info("GDS service closed")

    async def __aenter__(self) -> "GDSService":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @property
    def gds(self) -> GraphDataScience:
        """GDS 클라이언트 인스턴스"""
        if self._gds is None:
            raise RuntimeError("GDS not connected. Call connect() first.")
        return self._gds

    # =========================================================================
    # 그래프 프로젝션
    # =========================================================================

    async def create_skill_similarity_projection(
        self,
        projection_name: str | None = None,
        min_shared_skills: int = 1,
    ) -> dict[str, Any]:
        """
        스킬 기반 직원 유사도 그래프 프로젝션 생성

        1단계: Employee-Skill bipartite 그래프 생성
        2단계: Node Similarity로 Employee 간 유사도 관계 생성

        Args:
            projection_name: 프로젝션 이름 (기본: employee_skill_graph)
            min_shared_skills: 최소 공유 스킬 수

        Returns:
            프로젝션 생성 결과
        """
        name = projection_name or self.SKILL_PROJECTION
        bipartite_name = f"{name}_bipartite"

        def _create():
            # 기존 프로젝션 삭제
            for proj_name in [name, bipartite_name]:
                if self.gds.graph.exists(proj_name).exists:
                    self.gds.graph.drop(self.gds.graph.get(proj_name))
                    logger.info(f"Dropped existing projection: {proj_name}")

            # 기존 SIMILAR 관계 삭제 (이전 실행의 잔여 데이터)
            self.gds.run_cypher("MATCH ()-[r:SIMILAR]->() DELETE r")
            logger.info("Cleaned up existing SIMILAR relationships")

            # 1단계: Bipartite 그래프 프로젝션 (Employee-Skill)
            G_bipartite, bipartite_result = self.gds.graph.project(
                bipartite_name,
                ["Employee", "Skill"],
                {
                    "HAS_SKILL": {
                        "orientation": "UNDIRECTED",
                    }
                },
            )

            logger.info(
                f"Bipartite projection: {bipartite_result['nodeCount']} nodes, "
                f"{bipartite_result['relationshipCount']} relationships"
            )

            # 2단계: Node Similarity로 유사도 계산 후 DB에 저장
            # Jaccard 유사도 기반 (공유 스킬 비율)
            similarity_result = self.gds.nodeSimilarity.write(
                G_bipartite,
                writeRelationshipType="SIMILAR",
                writeProperty="similarity",
                similarityCutoff=0.0,  # 모든 유사도 포함
                degreeCutoff=min_shared_skills,  # 최소 공유 스킬
                topK=50,  # 상위 50개 유사 노드만
            )

            logger.info(
                f"Node Similarity: {similarity_result['relationshipsWritten']} "
                f"similarity relationships written to DB"
            )

            # Bipartite 프로젝션 삭제 (더 이상 필요 없음)
            self.gds.graph.drop(G_bipartite)

            # 3단계: Employee + SIMILAR 관계로 새 프로젝션 생성 (UNDIRECTED)
            G_final, final_result = self.gds.graph.project(
                name,
                ["Employee"],
                {
                    "SIMILAR": {
                        "orientation": "UNDIRECTED",
                        "properties": ["similarity"],
                    }
                },
            )

            return {
                "name": name,
                "node_count": final_result["nodeCount"],
                "relationship_count": final_result["relationshipCount"],
            }

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._executor, _create)

        logger.info(
            f"Created projection '{name}': "
            f"{result['node_count']} nodes, {result['relationship_count']} relationships"
        )
        return result

    async def drop_projection(self, projection_name: str | None = None) -> bool:
        """프로젝션 삭제"""
        name = projection_name or self.SKILL_PROJECTION

        def _drop():
            if self.gds.graph.exists(name).exists:
                self.gds.graph.drop(self.gds.graph.get(name))
                return True
            return False

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._executor, _drop)

        if result:
            logger.info(f"Dropped projection: {name}")
        return result

    async def get_projection_info(
        self, projection_name: str | None = None
    ) -> tuple[bool, dict]:
        """
        프로젝션 정보 조회

        Returns:
            (exists, details) 튜플
        """
        name = projection_name or self.SKILL_PROJECTION

        def _info():
            exists_result = self.gds.graph.exists(name)
            if not exists_result.exists:
                return False, {}

            G = self.gds.graph.get(name)
            return True, {
                "name": G.name(),
                "nodeCount": G.node_count(),
                "relationshipCount": G.relationship_count(),
                "nodeLabels": list(G.node_labels()),
                "relationshipTypes": list(G.relationship_types()),
            }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, _info)

    # =========================================================================
    # 커뮤니티 탐지
    # =========================================================================

    async def detect_communities(
        self,
        algorithm: Literal["leiden", "louvain"] = "leiden",
        projection_name: str | None = None,
        gamma: float = 1.0,
        write_property: str = "communityId",
    ) -> CommunityResult:
        """
        커뮤니티 탐지 실행

        Args:
            algorithm: 사용할 알고리즘 (leiden 권장)
            projection_name: 프로젝션 이름
            gamma: Resolution 파라미터 (높을수록 작은 커뮤니티)
            write_property: 결과를 저장할 노드 속성명

        Returns:
            커뮤니티 탐지 결과
        """
        name = projection_name or self.SKILL_PROJECTION

        def _detect():
            # 프로젝션 존재 확인
            if not self.gds.graph.exists(name).exists:
                raise ValueError(
                    f"Projection '{name}' not found. "
                    "Call create_skill_similarity_projection() first."
                )

            G = self.gds.graph.get(name)

            # 알고리즘 실행
            if algorithm == "leiden":
                result = self.gds.leiden.write(
                    G,
                    writeProperty=write_property,
                    gamma=gamma,
                    randomSeed=42,
                )
            else:  # louvain
                result = self.gds.louvain.write(
                    G,
                    writeProperty=write_property,
                    randomSeed=42,
                )

            # 커뮤니티별 통계 조회
            communities = self.gds.run_cypher(
                f"""
                MATCH (e:Employee)
                WHERE e.{write_property} IS NOT NULL
                RETURN e.{write_property} AS community_id,
                       count(*) AS member_count,
                       collect(e.name)[0..5] AS sample_members
                ORDER BY member_count DESC
                """
            )

            return {
                "algorithm": algorithm,
                "node_count": result["nodePropertiesWritten"],
                "community_count": result["communityCount"],
                "modularity": result["modularity"],
                "communities": communities.to_dict("records"),
            }

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._executor, _detect)

        logger.info(
            f"Community detection ({algorithm}): "
            f"{result['community_count']} communities found, "
            f"modularity={result['modularity']:.3f}"
        )

        return CommunityResult(**result)

    # =========================================================================
    # 유사 직원 탐색
    # =========================================================================

    async def find_similar_employees(
        self,
        employee_name: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        특정 직원과 유사한 스킬을 가진 직원 탐색

        Args:
            employee_name: 기준 직원 이름
            top_k: 반환할 최대 인원 수

        Returns:
            유사 직원 목록 (유사도 점수 포함)
        """

        def _find():
            # Jaccard 유사도 기반 검색
            result = self.gds.run_cypher(
                """
                MATCH (target:Employee {name: $name})-[:HAS_SKILL]->(s:Skill)
                WITH target, collect(s) AS targetSkills
                MATCH (other:Employee)-[:HAS_SKILL]->(s2:Skill)
                WHERE other <> target
                WITH target, targetSkills, other, collect(s2) AS otherSkills
                WITH target, other,
                     [s IN targetSkills WHERE s IN otherSkills] AS intersection,
                     targetSkills + [s IN otherSkills WHERE NOT s IN targetSkills] AS union_
                WITH other,
                     size(intersection) AS shared,
                     size(union_) AS total,
                     [s IN intersection | s.name] AS sharedSkillNames
                WHERE shared > 0
                RETURN other.name AS name,
                       other.job_type AS job_type,
                       other.years_experience AS experience,
                       other.communityId AS community_id,
                       shared AS shared_skills,
                       round(1.0 * shared / total, 3) AS similarity,
                       sharedSkillNames[0..5] AS common_skills
                ORDER BY similarity DESC, shared DESC
                LIMIT $top_k
                """,
                {"name": employee_name, "top_k": top_k},
            )
            return result.to_dict("records")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._executor, _find)

        logger.info(f"Found {len(result)} similar employees for '{employee_name}'")
        return result

    # =========================================================================
    # 팀 추천
    # =========================================================================

    async def recommend_team(
        self,
        required_skills: list[str],
        team_size: int = 5,
        diversity_weight: float = 0.3,
    ) -> TeamRecommendation:
        """
        필요 스킬 기반 최적 팀 추천

        Args:
            required_skills: 필요한 스킬 목록
            team_size: 팀 크기
            diversity_weight: 커뮤니티 다양성 가중치 (0~1)

        Returns:
            팀 추천 결과
        """

        def _recommend():
            # 1. 스킬 보유자 후보 조회 (스킬 커버리지 점수)
            candidates = self.gds.run_cypher(
                """
                UNWIND $skills AS skillName
                MATCH (e:Employee)-[r:HAS_SKILL]->(s:Skill)
                WHERE toLower(s.name) = toLower(skillName)
                WITH e, collect(DISTINCT s.name) AS matchedSkills,
                     count(DISTINCT s) AS skillCount
                RETURN e.employee_id AS id,
                       e.name AS name,
                       e.job_type AS job_type,
                       e.years_experience AS experience,
                       e.communityId AS community_id,
                       matchedSkills,
                       skillCount,
                       1.0 * skillCount / $totalSkills AS skill_score
                ORDER BY skillCount DESC
                LIMIT $limit
                """,
                {
                    "skills": required_skills,
                    "totalSkills": len(required_skills),
                    "limit": team_size * 3,  # 후보 풀
                },
            )
            candidates_list = candidates.to_dict("records")

            if not candidates_list:
                return {
                    "members": [],
                    "skill_coverage": 0.0,
                    "covered_skills": [],
                    "missing_skills": required_skills.copy(),
                    "community_diversity": 0,
                    "total_score": 0.0,
                }

            # 2. 그리디 선택: 스킬 커버리지 + 커뮤니티 다양성 최적화
            selected = []
            covered_skills: set[str] = set()
            used_communities: set[int] = set()

            for candidate in candidates_list:
                if len(selected) >= team_size:
                    break

                # 스킬 기여도
                new_skills = set(candidate["matchedSkills"]) - covered_skills
                skill_contribution = len(new_skills) / len(required_skills)

                # 커뮤니티 다양성 기여도
                comm_id = candidate.get("community_id")
                diversity_contribution = (
                    1.0 if comm_id and comm_id not in used_communities else 0.0
                )

                # 종합 점수
                score = (1 - diversity_weight) * skill_contribution + (
                    diversity_weight * diversity_contribution
                )

                # 새로운 스킬을 제공하거나, 충분한 스킬 기여도와 함께 다양성을 높이면 선택
                # (스킬 기여 없이 커뮤니티 다양성만으로는 선택하지 않음)
                should_select = new_skills or (
                    skill_contribution >= 0.2  # 최소 20% 스킬 기여도 필요
                    and comm_id
                    and comm_id not in used_communities
                )
                if should_select:
                    candidate["selection_score"] = round(score, 3)
                    selected.append(candidate)
                    covered_skills.update(new_skills)
                    if comm_id:
                        used_communities.add(comm_id)

            skill_coverage = len(covered_skills) / len(required_skills)
            total_score = sum(m.get("selection_score", 0) for m in selected) / max(
                len(selected), 1
            )

            missing = [s for s in required_skills if s not in covered_skills]
            return {
                "members": selected,
                "skill_coverage": round(skill_coverage, 3),
                "covered_skills": list(covered_skills),
                "missing_skills": missing,
                "community_diversity": len(used_communities),
                "total_score": round(total_score, 3),
            }

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._executor, _recommend)

        logger.info(
            f"Team recommendation: {len(result['members'])} members, "
            f"skill coverage={result['skill_coverage']:.1%}, "
            f"diversity={result['community_diversity']} communities"
        )

        return TeamRecommendation(**result)

    # =========================================================================
    # 커뮤니티 분석
    # =========================================================================

    async def get_community_details(
        self,
        community_id: int,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        특정 커뮤니티 상세 정보 조회

        Args:
            community_id: 커뮤니티 ID
            limit: 반환할 최대 멤버 수

        Returns:
            커뮤니티 상세 정보 (멤버, 주요 스킬 등)
        """

        def _get_details():
            # 멤버 조회
            members = self.gds.run_cypher(
                """
                MATCH (e:Employee {communityId: $community_id})
                OPTIONAL MATCH (e)-[:HAS_SKILL]->(s:Skill)
                WITH e, collect(s.name) AS skills
                RETURN e.employee_id AS id,
                       e.name AS name,
                       e.job_type AS job_type,
                       e.years_experience AS experience,
                       skills[0..5] AS top_skills
                LIMIT $limit
                """,
                {"community_id": community_id, "limit": limit},
            )

            # 주요 스킬 통계
            skill_stats = self.gds.run_cypher(
                """
                MATCH (e:Employee {communityId: $community_id})-[:HAS_SKILL]->(s:Skill)
                RETURN s.name AS skill,
                       count(*) AS count,
                       round(100.0 * count(*) / $member_count, 1) AS percentage
                ORDER BY count DESC
                LIMIT 10
                """,
                {"community_id": community_id, "member_count": len(members)},
            )

            return {
                "community_id": community_id,
                "member_count": len(members),
                "members": members.to_dict("records"),
                "top_skills": skill_stats.to_dict("records"),
            }

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self._executor, _get_details)

        logger.info(
            f"Community {community_id}: {result['member_count']} members"
        )
        return result
