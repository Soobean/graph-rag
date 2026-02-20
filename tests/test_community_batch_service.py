"""
CommunityBatchService 단위 테스트

GDSService와 Neo4jRepository를 mock하여
배치 파이프라인의 오케스트레이션 로직을 검증합니다.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.exceptions import ConcurrentRefreshError
from src.services.community_batch_service import (
    CommunityBatchService,
    CommunityRefreshResult,
    CommunityStatusResult,
)
from src.services.gds_service import CommunityResult, GDSService


@pytest.fixture
def mock_gds():
    """Mock GDSService"""
    gds = MagicMock(spec=GDSService)
    gds.cleanup_all_projections = AsyncMock(return_value=1)
    gds.create_skill_similarity_projection = AsyncMock(
        return_value={
            "name": "employee_skill_graph",
            "node_count": 100,
            "relationship_count": 500,
        }
    )
    gds.detect_communities = AsyncMock(
        return_value=CommunityResult(
            algorithm="leiden",
            node_count=95,
            community_count=5,
            modularity=0.72,
            communities=[
                {"community_id": 0, "member_count": 30, "sample_members": ["김철수"]},
                {"community_id": 1, "member_count": 25, "sample_members": ["이영희"]},
            ],
        )
    )
    gds.drop_projection = AsyncMock(return_value=True)
    return gds


@pytest.fixture
def mock_neo4j_repo():
    """Mock Neo4jRepository"""
    from src.repositories.neo4j_repository import Neo4jRepository

    repo = MagicMock(spec=Neo4jRepository)
    repo.execute_cypher = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_gds, mock_neo4j_repo):
    """CommunityBatchService with mocked dependencies"""
    return CommunityBatchService(
        gds_service=mock_gds,
        neo4j_repository=mock_neo4j_repo,
    )


# ============================================
# refresh() 테스트
# ============================================


async def test_refresh_success(service, mock_gds, mock_neo4j_repo):
    """정상 리프레시: 5단계 파이프라인 순차 실행 확인"""
    result = await service.refresh(
        algorithm="leiden",
        gamma=1.0,
        min_shared_skills=2,
    )

    # 결과 검증
    assert isinstance(result, CommunityRefreshResult)
    assert result.success is True
    assert result.algorithm == "leiden"
    assert result.community_count == 5
    assert result.modularity == 0.72
    assert result.node_count == 95
    assert result.duration_seconds >= 0

    # 5단계 순차 호출 검증
    mock_gds.cleanup_all_projections.assert_called_once()
    mock_gds.create_skill_similarity_projection.assert_called_once_with(
        min_shared_skills=2,
    )
    mock_gds.detect_communities.assert_called_once_with(
        algorithm="leiden",
        gamma=1.0,
    )
    mock_neo4j_repo.execute_cypher.assert_called_once()  # metadata save
    mock_gds.drop_projection.assert_called_once()

    # 호출 순서 검증 (GDS 호출만)
    gds_calls = mock_gds.method_calls
    gds_method_names = [c[0] for c in gds_calls]
    assert gds_method_names == [
        "cleanup_all_projections",
        "create_skill_similarity_projection",
        "detect_communities",
        "drop_projection",
    ]


async def test_refresh_with_louvain(service, mock_gds):
    """Louvain 알고리즘으로 리프레시"""
    mock_gds.detect_communities.return_value = CommunityResult(
        algorithm="louvain",
        node_count=90,
        community_count=4,
        modularity=0.68,
        communities=[],
    )

    result = await service.refresh(algorithm="louvain", gamma=2.0, min_shared_skills=3)

    assert result.algorithm == "louvain"
    mock_gds.detect_communities.assert_called_once_with(
        algorithm="louvain",
        gamma=2.0,
    )
    mock_gds.create_skill_similarity_projection.assert_called_once_with(
        min_shared_skills=3,
    )


async def test_refresh_records_metadata(service, mock_neo4j_repo):
    """refresh 후 CommunityMeta 노드에 MERGE 쿼리 실행 확인"""
    await service.refresh()

    # execute_cypher 호출 확인
    mock_neo4j_repo.execute_cypher.assert_called_once()
    cypher_call = mock_neo4j_repo.execute_cypher.call_args

    # Cypher 쿼리에 MERGE와 CommunityMeta 포함 확인
    query = cypher_call[0][0]
    assert "MERGE" in query
    assert "CommunityMeta" in query
    assert "last_refresh" in query

    # 파라미터 검증
    params = cypher_call[0][1]
    assert params["algorithm"] == "leiden"
    assert params["community_count"] == 5
    assert params["modularity"] == 0.72
    assert params["node_count"] == 95


async def test_refresh_cleans_up_on_error(service, mock_gds):
    """detect 실패 시 모든 프로젝션 정리 호출 확인 (메모리 누수 방지)"""
    mock_gds.detect_communities = AsyncMock(
        side_effect=RuntimeError("GDS algorithm failed")
    )

    with pytest.raises(RuntimeError, match="GDS algorithm failed"):
        await service.refresh()

    # Step 1 cleanup + error handler cleanup = 2회 호출
    assert mock_gds.cleanup_all_projections.call_count == 2


async def test_refresh_cleans_up_even_if_projection_create_fails(service, mock_gds):
    """프로젝션 생성 실패 시에도 정리 시도"""
    mock_gds.create_skill_similarity_projection = AsyncMock(
        side_effect=RuntimeError("Projection creation failed")
    )

    with pytest.raises(RuntimeError, match="Projection creation failed"):
        await service.refresh()

    # Step 1 cleanup + error handler cleanup = 2회 호출
    assert mock_gds.cleanup_all_projections.call_count == 2


async def test_refresh_handles_double_failure(service, mock_gds):
    """detect 실패 + cleanup 실패 시 원래 에러가 전파됨"""
    mock_gds.detect_communities = AsyncMock(side_effect=RuntimeError("GDS failed"))
    mock_gds.cleanup_all_projections = AsyncMock(
        side_effect=[1, RuntimeError("Cleanup also failed")]
    )

    with pytest.raises(RuntimeError, match="GDS failed"):
        await service.refresh()


async def test_refresh_cleans_up_on_metadata_save_error(
    service, mock_gds, mock_neo4j_repo
):
    """Step 4 메타데이터 저장 실패 시에도 프로젝션 정리"""
    mock_neo4j_repo.execute_cypher = AsyncMock(
        side_effect=RuntimeError("DB write failed")
    )

    with pytest.raises(RuntimeError, match="DB write failed"):
        await service.refresh()

    # Step 1 cleanup + error handler cleanup = 2회 호출
    assert mock_gds.cleanup_all_projections.call_count == 2


async def test_refresh_rejects_concurrent_call(service, mock_gds):
    """동시 리프레시 시 두 번째 호출은 ConcurrentRefreshError"""
    import asyncio

    # detect_communities를 느리게 만들어서 lock 유지
    async def slow_detect(*args, **kwargs):
        await asyncio.sleep(0.1)
        return CommunityResult(
            algorithm="leiden",
            node_count=95,
            community_count=5,
            modularity=0.72,
            communities=[],
        )

    mock_gds.detect_communities = AsyncMock(side_effect=slow_detect)

    # 동시 호출
    results = await asyncio.gather(
        service.refresh(),
        service.refresh(),
        return_exceptions=True,
    )

    # 하나는 성공, 하나는 ConcurrentRefreshError
    successes = [r for r in results if isinstance(r, CommunityRefreshResult)]
    errors = [r for r in results if isinstance(r, ConcurrentRefreshError)]
    assert len(successes) == 1
    assert len(errors) == 1


# ============================================
# get_status() 테스트
# ============================================


async def test_get_status_with_communities(service, mock_neo4j_repo):
    """CommunityMeta 존재 시 정상 반환"""
    fresh_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    mock_neo4j_repo.execute_cypher = AsyncMock(
        side_effect=[
            [
                {
                    "refreshed_at": fresh_time,
                    "algorithm": "leiden",
                    "community_count": 5,
                    "modularity": 0.72,
                    "node_count": 95,
                }
            ],
            [{"cnt": 95}],
        ]
    )

    result = await service.get_status()

    assert isinstance(result, CommunityStatusResult)
    assert result.has_communities is True
    assert result.refreshed_at == fresh_time
    assert result.algorithm == "leiden"
    assert result.community_count == 5
    assert result.modularity == 0.72
    assert result.assigned_node_count == 95
    assert result.is_stale is False


async def test_get_status_never_refreshed(service, mock_neo4j_repo):
    """CommunityMeta 없으면 has_communities=False"""
    mock_neo4j_repo.execute_cypher = AsyncMock(
        side_effect=[
            [],  # no CommunityMeta
            [{"cnt": 0}],
        ]
    )

    result = await service.get_status()

    assert result.has_communities is False
    assert result.refreshed_at is None
    assert result.algorithm is None
    assert result.community_count == 0
    assert result.modularity is None
    assert result.assigned_node_count == 0
    assert result.is_stale is True


async def test_get_status_stale(service, mock_neo4j_repo):
    """24시간 이상 전 리프레시 → is_stale=True"""
    stale_time = (datetime.now(UTC) - timedelta(hours=30)).isoformat()

    mock_neo4j_repo.execute_cypher = AsyncMock(
        side_effect=[
            [
                {
                    "refreshed_at": stale_time,
                    "algorithm": "leiden",
                    "community_count": 3,
                    "modularity": 0.65,
                    "node_count": 80,
                }
            ],
            [{"cnt": 60}],
        ]
    )

    result = await service.get_status()

    assert result.is_stale is True
    assert result.has_communities is True
    assert result.assigned_node_count == 60


# ============================================
# _check_stale() 단위 테스트
# ============================================


def test_check_stale_fresh():
    """24시간 미만이면 is_stale=False"""
    fresh_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert CommunityBatchService._check_stale(fresh_time) is False


def test_check_stale_old():
    """24시간 이상이면 is_stale=True"""
    old_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    assert CommunityBatchService._check_stale(old_time) is True


def test_check_stale_none():
    """None이면 is_stale=True"""
    assert CommunityBatchService._check_stale(None) is True


def test_check_stale_invalid_string():
    """파싱 불가 문자열이면 is_stale=True"""
    assert CommunityBatchService._check_stale("not-a-date") is True


def test_check_stale_naive_datetime():
    """타임존 없는 datetime 문자열도 UTC로 간주하여 처리"""
    # UTC 기준 1시간 전 (naive → UTC 변환 경로 검증)
    fresh_time = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    assert CommunityBatchService._check_stale(fresh_time) is False


def test_check_stale_exact_boundary():
    """정확히 24시간이면 is_stale=True (>= 경계값)"""
    boundary_time = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    assert CommunityBatchService._check_stale(boundary_time) is True


def test_check_stale_just_under_boundary():
    """23시간 59분이면 is_stale=False"""
    just_under = (datetime.now(UTC) - timedelta(hours=23, minutes=59)).isoformat()
    assert CommunityBatchService._check_stale(just_under) is False


def test_check_stale_nanosecond_precision():
    """Neo4j 나노초 정밀도 datetime도 정상 파싱"""
    fresh_time = (datetime.now(UTC) - timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.123456789+00:00"
    )
    assert CommunityBatchService._check_stale(fresh_time) is False
