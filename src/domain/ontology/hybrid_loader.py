"""
Hybrid Ontology Loader

YAML과 Neo4j 백엔드를 모두 지원하는 하이브리드 온톨로지 로더.
- yaml 모드: YAML 파일만 사용 (기본값, 하위호환)
- neo4j 모드: Neo4j만 사용
- hybrid 모드: Neo4j 우선, 실패 시 YAML 폴백

사용 예시:
    # YAML 모드 (기본값)
    loader = HybridOntologyLoader()

    # Neo4j 모드
    loader = HybridOntologyLoader(
        neo4j_client=client,
        mode="neo4j"
    )

    # 하이브리드 모드
    loader = HybridOntologyLoader(
        neo4j_client=client,
        mode="hybrid"
    )
"""

import logging
from pathlib import Path
from typing import Any, Literal

from src.domain.ontology.loader import (
    DEFAULT_EXPANSION_CONFIG,
    ExpansionConfig,
    OntologyLoader,
)
from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


# Lazy import to avoid circular dependency
def _get_neo4j_loader():
    from src.domain.ontology.neo4j_loader import Neo4jOntologyLoader
    return Neo4jOntologyLoader


class HybridOntologyLoader:
    """
    하이브리드 온톨로지 로더

    YAML과 Neo4j 백엔드를 모드에 따라 전환하여 사용합니다.
    모든 public 메서드는 비동기(async)입니다.

    Attributes:
        mode: 동작 모드 ("yaml", "neo4j", "hybrid")

    Note:
        - yaml 모드에서는 기존 OntologyLoader를 래핑하여 async로 제공
        - neo4j 모드에서는 Neo4jOntologyLoader 직접 사용
        - hybrid 모드에서는 Neo4j 우선, 예외 발생 시 YAML 폴백
    """

    def __init__(
        self,
        ontology_dir: Path | str | None = None,
        neo4j_client: Neo4jClient | None = None,
        mode: Literal["yaml", "neo4j", "hybrid"] = "yaml",
    ):
        """
        Args:
            ontology_dir: YAML 파일 디렉토리 (yaml/hybrid 모드용)
            neo4j_client: Neo4j 클라이언트 (neo4j/hybrid 모드용)
            mode: 동작 모드

        Raises:
            ValueError: neo4j/hybrid 모드인데 neo4j_client가 None인 경우
        """
        self._mode = mode

        # YAML 로더 (yaml, hybrid 모드)
        self._yaml_loader: OntologyLoader | None = None
        if mode in ("yaml", "hybrid"):
            self._yaml_loader = OntologyLoader(ontology_dir)

        # Neo4j 로더 (neo4j, hybrid 모드)
        self._neo4j_loader: Any = None  # Neo4jOntologyLoader
        if mode in ("neo4j", "hybrid"):
            if neo4j_client is None:
                raise ValueError(
                    f"neo4j_client is required for mode='{mode}'"
                )
            Neo4jOntologyLoader = _get_neo4j_loader()
            self._neo4j_loader = Neo4jOntologyLoader(neo4j_client)

        logger.info(f"HybridOntologyLoader initialized: mode={mode}")

    @property
    def mode(self) -> str:
        """현재 동작 모드"""
        return self._mode

    async def get_canonical(
        self,
        term: str,
        category: str = "skills",
    ) -> str:
        """
        정규화된 이름 반환

        Args:
            term: 검색어
            category: 카테고리

        Returns:
            정규화된 이름
        """
        if self._mode == "yaml":
            assert self._yaml_loader is not None
            return self._yaml_loader.get_canonical(term, category)

        if self._mode == "neo4j":
            assert self._neo4j_loader is not None
            return await self._neo4j_loader.get_canonical(term, category)

        # hybrid 모드
        try:
            assert self._neo4j_loader is not None
            result = await self._neo4j_loader.get_canonical(term, category)
            if result != term:  # 결과가 있으면 반환
                return result
        except Exception as e:
            logger.warning(f"Neo4j get_canonical failed, falling back to YAML: {e}")

        assert self._yaml_loader is not None
        return self._yaml_loader.get_canonical(term, category)

    async def get_synonyms(
        self,
        term: str,
        category: str = "skills",
    ) -> list[str]:
        """
        동의어 목록 반환

        Args:
            term: 검색어
            category: 카테고리

        Returns:
            동의어 목록
        """
        if self._mode == "yaml":
            assert self._yaml_loader is not None
            return self._yaml_loader.get_synonyms(term, category)

        if self._mode == "neo4j":
            assert self._neo4j_loader is not None
            return await self._neo4j_loader.get_synonyms(term, category)

        # hybrid 모드
        try:
            assert self._neo4j_loader is not None
            result = await self._neo4j_loader.get_synonyms(term, category)
            if len(result) > 1:  # 동의어가 있으면 반환
                return result
        except Exception as e:
            logger.warning(f"Neo4j get_synonyms failed, falling back to YAML: {e}")

        assert self._yaml_loader is not None
        return self._yaml_loader.get_synonyms(term, category)

    async def get_children(
        self,
        concept: str,
        category: str = "skills",
    ) -> list[str]:
        """
        하위 개념 반환

        Args:
            concept: 상위 개념
            category: 카테고리

        Returns:
            하위 개념 목록
        """
        if self._mode == "yaml":
            assert self._yaml_loader is not None
            return self._yaml_loader.get_children(concept, category)

        if self._mode == "neo4j":
            assert self._neo4j_loader is not None
            return await self._neo4j_loader.get_children(concept, category)

        # hybrid 모드
        try:
            assert self._neo4j_loader is not None
            result = await self._neo4j_loader.get_children(concept, category)
            if result:  # 결과가 있으면 반환
                return result
        except Exception as e:
            logger.warning(f"Neo4j get_children failed, falling back to YAML: {e}")

        assert self._yaml_loader is not None
        return self._yaml_loader.get_children(concept, category)

    async def expand_concept(
        self,
        term: str,
        category: str = "skills",
        config: ExpansionConfig | None = None,
    ) -> list[str]:
        """
        개념 확장 (동의어 + 하위 개념)

        Args:
            term: 검색어
            category: 카테고리
            config: 확장 설정

        Returns:
            확장된 개념 목록
        """
        if config is None:
            config = DEFAULT_EXPANSION_CONFIG

        if self._mode == "yaml":
            assert self._yaml_loader is not None
            return self._yaml_loader.expand_concept(term, category, config)

        if self._mode == "neo4j":
            assert self._neo4j_loader is not None
            return await self._neo4j_loader.expand_concept(term, category, config)

        # hybrid 모드
        try:
            assert self._neo4j_loader is not None
            result = await self._neo4j_loader.expand_concept(term, category, config)
            if len(result) > 1:  # 확장 결과가 있으면 반환
                return result
        except Exception as e:
            logger.warning(f"Neo4j expand_concept failed, falling back to YAML: {e}")

        assert self._yaml_loader is not None
        return self._yaml_loader.expand_concept(term, category, config)

    async def clear_cache(self) -> None:
        """
        내부 캐시 클리어

        OntologyRegistry.refresh() 호출 시 사용됩니다.
        YAML 로더와 Neo4j 로더의 캐시를 모두 클리어합니다.
        """
        if self._yaml_loader is not None:
            self._yaml_loader.clear_cache()

        if self._neo4j_loader is not None and hasattr(self._neo4j_loader, "clear_cache"):
            await self._neo4j_loader.clear_cache()

    async def health_check(self) -> dict[str, Any]:
        """
        로더 상태 확인

        Returns:
            상태 정보 딕셔너리
        """
        status: dict[str, Any] = {
            "mode": self._mode,
            "yaml_available": self._yaml_loader is not None,
            "neo4j_available": self._neo4j_loader is not None,
        }

        if self._neo4j_loader is not None:
            try:
                neo4j_health = await self._neo4j_loader.health_check()
                status["neo4j"] = neo4j_health
            except Exception as e:
                status["neo4j"] = {"status": "unhealthy", "error": str(e)}

        return status
