"""
OntologyRegistry - 온톨로지 로더 생명주기 관리

런타임 캐시 새로고침을 지원하는 온톨로지 로더 레지스트리입니다.
승인된 온톨로지 제안이 Neo4j에 저장된 후 즉시 쿼리 파이프라인에
반영되도록 캐시를 갱신합니다.

핵심 기능:
- 모드별(yaml/neo4j/hybrid) 로더 초기화
- Thread-safe 캐시 refresh
- YAML @lru_cache 및 HybridLoader 내부 캐시 클리어

사용 패턴:
    # 앱 시작 시 (main.py lifespan)
    registry = OntologyRegistry(neo4j_client, settings)

    # Pipeline에 로더 주입
    pipeline = GraphRAGPipeline(..., ontology_loader=registry.get_loader())

    # OntologyService에 registry 주입
    ontology_service = OntologyService(..., ontology_registry=registry)

    # 승인 후 (OntologyService.approve_proposal)
    await registry.refresh()
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal

from src.domain.ontology.hybrid_loader import HybridOntologyLoader
from src.domain.ontology.loader import OntologyLoader, get_ontology_loader

if TYPE_CHECKING:
    from src.config import Settings
    from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class OntologyRegistry:
    """
    온톨로지 로더 생명주기 관리자

    앱 전체에서 단일 로더 인스턴스를 공유하면서,
    온톨로지 변경 시 캐시를 안전하게 갱신합니다.

    Attributes:
        mode: 동작 모드 ("yaml", "neo4j", "hybrid")

    Thread Safety:
        refresh() 메서드는 asyncio.Lock으로 보호되어
        동시 호출 시 직렬화됩니다.
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient | None = None,
        settings: Settings | None = None,
        mode: Literal["yaml", "neo4j", "hybrid"] | None = None,
    ):
        """
        Args:
            neo4j_client: Neo4j 클라이언트 (neo4j/hybrid 모드용)
            settings: 앱 설정 (ontology_mode 결정용)
            mode: 명시적 모드 지정 (settings보다 우선)

        Raises:
            ValueError: neo4j/hybrid 모드인데 neo4j_client가 None인 경우
        """
        # 모드 결정: 명시적 > settings > 기본값(yaml)
        if mode is not None:
            self._mode = mode
        elif settings is not None:
            self._mode = settings.ontology_mode
        else:
            self._mode = "yaml"

        self._refresh_lock = asyncio.Lock()

        # 로더 초기화
        self._loader: OntologyLoader | HybridOntologyLoader
        if self._mode in ("neo4j", "hybrid"):
            if neo4j_client is None:
                raise ValueError(f"neo4j_client is required for mode='{self._mode}'")
            self._loader = HybridOntologyLoader(
                neo4j_client=neo4j_client,
                mode=self._mode,
            )
            logger.info(f"OntologyRegistry initialized: mode={self._mode} (Hybrid)")
        else:
            # YAML 모드: 싱글톤 인스턴스 사용
            self._loader = get_ontology_loader()
            logger.info("OntologyRegistry initialized: mode=yaml (YAML)")

    @property
    def mode(self) -> str:
        """현재 동작 모드"""
        return self._mode

    def get_loader(self) -> OntologyLoader | HybridOntologyLoader:
        """
        현재 온톨로지 로더 반환

        Returns:
            OntologyLoader (yaml 모드) 또는 HybridOntologyLoader (neo4j/hybrid 모드)
        """
        return self._loader

    async def refresh(self) -> bool:
        """
        온톨로지 캐시 새로고침

        승인된 제안이 Neo4j에 저장된 후 호출하여
        런타임 캐시를 갱신합니다.

        Returns:
            True if refresh succeeded, False otherwise

        Thread Safety:
            동시 호출 시 asyncio.Lock으로 직렬화됩니다.
        """
        async with self._refresh_lock:
            try:
                return await self._do_refresh()
            except Exception as e:
                logger.error(f"Ontology refresh failed: {e}")
                return False

    async def _do_refresh(self) -> bool:
        """실제 캐시 갱신 로직 (lock 내부에서 실행)"""
        if self._mode == "yaml":
            return self._refresh_yaml_cache()
        else:
            return await self._refresh_hybrid_cache()

    def _refresh_yaml_cache(self) -> bool:
        """
        YAML 모드 캐시 갱신

        @lru_cache로 캐싱된 get_ontology_loader()를 클리어하고
        OntologyLoader 내부 캐시를 리셋합니다.

        Note:
            YAML 파일 자체는 변경되지 않으므로, 이 메서드는
            주로 테스트나 파일 변경 후 수동 갱신에 사용됩니다.
        """
        try:
            # 1. @lru_cache 클리어
            get_ontology_loader.cache_clear()

            # 2. 새 싱글톤 인스턴스로 교체 (새 인스턴스는 빈 캐시 상태)
            self._loader = get_ontology_loader()

            logger.info("YAML ontology cache refreshed")
            return True

        except Exception as e:
            logger.error(f"YAML cache refresh failed: {e}")
            return False

    async def _refresh_hybrid_cache(self) -> bool:
        """
        Hybrid/Neo4j 모드 캐시 갱신

        HybridOntologyLoader의 내부 캐시를 클리어합니다:
        - YAML 로더 캐시 (hybrid 모드)
        - Neo4j 로더 캐시 (있는 경우)
        """
        try:
            if not isinstance(self._loader, HybridOntologyLoader):
                logger.warning("Expected HybridOntologyLoader but got different type")
                return False

            # HybridOntologyLoader의 clear_cache() 메서드 호출
            await self._loader.clear_cache()

            logger.info(f"Hybrid ontology cache refreshed (mode={self._mode})")
            return True

        except Exception as e:
            logger.error(f"Hybrid cache refresh failed: {e}")
            return False
