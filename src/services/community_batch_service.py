"""
Community Batch Service

GDS 커뮤니티 탐지 배치 파이프라인 오케스트레이션 서비스.
GDSService의 프리미티브들을 조합하여 원클릭 커뮤니티 리프레시를 제공합니다.

파이프라인: 프로젝션 정리 → 유사도 프로젝션 생성 → 커뮤니티 탐지 → 메타데이터 기록 → 프로젝션 정리
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from src.domain.exceptions import ConcurrentRefreshError
from src.repositories.neo4j_repository import Neo4jRepository
from src.services.gds_service import GDSService

logger = logging.getLogger(__name__)

STALE_THRESHOLD_HOURS = 24


@dataclass
class CommunityRefreshResult:
    """커뮤니티 리프레시 결과"""

    success: bool
    algorithm: str
    community_count: int
    modularity: float
    node_count: int  # communityId가 부여된 노드 수
    duration_seconds: float


@dataclass
class CommunityStatusResult:
    """커뮤니티 상태 조회 결과"""

    has_communities: bool
    refreshed_at: str | None  # ISO format
    algorithm: str | None
    community_count: int
    modularity: float | None
    assigned_node_count: int  # communityId가 있는 Employee 수
    is_stale: bool  # refreshed_at이 24시간 이상 전이면 True


class CommunityBatchService:
    """
    커뮤니티 탐지 배치 오케스트레이션 서비스

    GDSService의 개별 프리미티브(프로젝션 생성, 커뮤니티 탐지, 프로젝션 삭제)를
    하나의 원클릭 파이프라인으로 조합합니다. :CommunityMeta 노드로 상태를 추적합니다.
    """

    def __init__(
        self,
        gds_service: GDSService,
        neo4j_repository: Neo4jRepository,
    ):
        self._gds = gds_service
        self._neo4j = neo4j_repository
        self._refresh_lock = asyncio.Lock()

    async def refresh(
        self,
        algorithm: Literal["leiden", "louvain"] = "leiden",
        gamma: float = 1.0,
        min_shared_skills: int = 2,
    ) -> CommunityRefreshResult:
        """
        원클릭 커뮤니티 리프레시

        전체 파이프라인을 순차 실행:
        1. 기존 프로젝션 정리 (메모리 해제)
        2. 스킬 유사도 프로젝션 생성
        3. 커뮤니티 탐지 (Leiden/Louvain)
        4. :CommunityMeta 노드에 메타데이터 기록
        5. 프로젝션 정리 (메모리 해제)

        Args:
            algorithm: 커뮤니티 탐지 알고리즘
            gamma: Resolution 파라미터 (높을수록 작은 커뮤니티)
            min_shared_skills: 유사도 계산 시 최소 공유 스킬 수

        Returns:
            CommunityRefreshResult with statistics
        """
        if self._refresh_lock.locked():
            raise ConcurrentRefreshError()

        async with self._refresh_lock:
            return await self._run_refresh(algorithm, gamma, min_shared_skills)

    async def _run_refresh(
        self,
        algorithm: Literal["leiden", "louvain"],
        gamma: float,
        min_shared_skills: int,
    ) -> CommunityRefreshResult:
        """실제 리프레시 파이프라인 실행 (lock 내부에서 호출)"""
        start_time = time.monotonic()
        logger.info(
            f"Community refresh started: algorithm={algorithm}, "
            f"gamma={gamma}, min_shared_skills={min_shared_skills}"
        )

        try:
            # Step 1: 기존 프로젝션 정리
            dropped = await self._gds.cleanup_all_projections()
            logger.info(f"Cleaned up {dropped} existing projections")

            # Step 2: 스킬 유사도 프로젝션 생성
            projection = await self._gds.create_skill_similarity_projection(
                min_shared_skills=min_shared_skills,
            )
            logger.info(
                f"Projection created: {projection['node_count']} nodes, "
                f"{projection['relationship_count']} relationships"
            )

            # Step 3: 커뮤니티 탐지
            detection = await self._gds.detect_communities(
                algorithm=algorithm,
                gamma=gamma,
            )
            logger.info(
                f"Communities detected: {detection.community_count} communities, "
                f"modularity={detection.modularity:.3f}"
            )

            # Step 4: :CommunityMeta 노드에 메타데이터 기록
            await self._save_metadata(
                algorithm=algorithm,
                gamma=gamma,
                community_count=detection.community_count,
                modularity=detection.modularity,
                node_count=detection.node_count,
            )

            # Step 5: 프로젝션 정리 (메모리 해제)
            await self._gds.drop_projection()
            logger.info("Projection dropped after community detection")

            duration = time.monotonic() - start_time
            logger.info(f"Community refresh completed in {duration:.1f}s")

            return CommunityRefreshResult(
                success=True,
                algorithm=algorithm,
                community_count=detection.community_count,
                modularity=detection.modularity,
                node_count=detection.node_count,
                duration_seconds=round(duration, 2),
            )

        except Exception:
            # 에러 발생 시에도 모든 프로젝션 정리 시도 (메모리 누수 방지)
            try:
                await self._gds.cleanup_all_projections()
                logger.info("All projections cleaned up after error")
            except Exception as cleanup_err:
                logger.warning(f"Failed to cleanup projections after error: {cleanup_err}")
            raise

    async def get_status(self) -> CommunityStatusResult:
        """
        커뮤니티 상태 조회

        :CommunityMeta 노드와 communityId가 부여된 Employee 수를 조회합니다.
        메타 노드가 없으면 "never_refreshed" 상태를 반환합니다.
        """
        meta = await self._get_metadata()
        assigned_count = await self._count_assigned_nodes()

        if meta is None:
            return CommunityStatusResult(
                has_communities=False,
                refreshed_at=None,
                algorithm=None,
                community_count=0,
                modularity=None,
                assigned_node_count=assigned_count,
                is_stale=True,
            )

        refreshed_at = meta.get("refreshed_at")
        is_stale = self._check_stale(refreshed_at)

        return CommunityStatusResult(
            has_communities=assigned_count > 0,
            refreshed_at=refreshed_at,
            algorithm=meta.get("algorithm"),
            community_count=meta.get("community_count", 0),
            modularity=meta.get("modularity"),
            assigned_node_count=assigned_count,
            is_stale=is_stale,
        )

    async def _save_metadata(
        self,
        algorithm: str,
        gamma: float,
        community_count: int,
        modularity: float,
        node_count: int,
    ) -> None:
        """CommunityMeta 노드에 리프레시 메타데이터 기록"""
        await self._neo4j.execute_cypher(
            """
            MERGE (m:CommunityMeta {key: 'last_refresh'})
            SET m.refreshed_at = datetime(),
                m.algorithm = $algorithm,
                m.gamma = $gamma,
                m.community_count = $community_count,
                m.modularity = $modularity,
                m.node_count = $node_count
            """,
            {
                "algorithm": algorithm,
                "gamma": gamma,
                "community_count": community_count,
                "modularity": modularity,
                "node_count": node_count,
            },
        )
        logger.info("CommunityMeta node updated")

    async def _get_metadata(self) -> dict[str, Any] | None:
        """CommunityMeta 노드 조회"""
        results = await self._neo4j.execute_cypher(
            """
            MATCH (m:CommunityMeta {key: 'last_refresh'})
            RETURN m.refreshed_at AS refreshed_at,
                   m.algorithm AS algorithm,
                   m.community_count AS community_count,
                   m.modularity AS modularity
            """,
        )
        if not results:
            return None

        row = results[0]
        # Neo4j datetime → ISO string
        refreshed_at = row.get("refreshed_at")
        if refreshed_at is not None:
            refreshed_at = str(refreshed_at)

        return {
            "refreshed_at": refreshed_at,
            "algorithm": row.get("algorithm"),
            "community_count": row.get("community_count") or 0,
            "modularity": row.get("modularity"),
        }

    async def _count_assigned_nodes(self) -> int:
        """communityId가 부여된 Employee 수 조회 (중복 노드 제외)"""
        results = await self._neo4j.execute_cypher(
            """
            MATCH (e:Employee)
            WHERE e.communityId IS NOT NULL
            RETURN count(DISTINCT e.name) AS cnt
            """,
        )
        if not results:
            return 0
        return results[0].get("cnt") or 0

    @staticmethod
    def _check_stale(refreshed_at: str | None) -> bool:
        """refreshed_at이 24시간 이상 전이면 stale로 판단"""
        if refreshed_at is None:
            return True
        try:
            # Neo4j 나노초(9자리) → 마이크로초(6자리) 잘라내기
            # Python datetime은 최대 마이크로초 정밀도만 지원
            cleaned = re.sub(r"(\.\d{6})\d+", r"\1", refreshed_at)
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            age_hours = (datetime.now(UTC) - dt).total_seconds() / 3600
            return age_hours >= STALE_THRESHOLD_HOURS
        except (ValueError, TypeError):
            return True
