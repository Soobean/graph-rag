"""
온톨로지 관련 유틸리티 함수

공통 패턴을 추출하여 코드 중복을 방지합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.ontology.registry import OntologyRegistry

logger = logging.getLogger(__name__)


async def safe_refresh_ontology_cache(
    registry: OntologyRegistry | None,
    context: str = "unknown",
) -> bool:
    """
    온톨로지 런타임 캐시 안전하게 새로고침

    OntologyRegistry가 주입된 경우에만 캐시를 갱신합니다.
    실패해도 예외를 발생시키지 않습니다 (graceful degradation).

    Args:
        registry: OntologyRegistry 인스턴스 (None이면 스킵)
        context: 로그용 컨텍스트 (예: "approve", "auto-approve", "batch-approve")

    Returns:
        True if refresh succeeded, False otherwise
    """
    if registry is None:
        logger.debug(f"OntologyRegistry not available, skipping cache refresh ({context})")
        return False

    try:
        success = await registry.refresh()
        if success:
            logger.info(f"Ontology runtime cache refreshed ({context})")
        else:
            logger.warning(f"Ontology cache refresh returned False ({context})")
        return success
    except Exception as e:
        # 캐시 갱신 실패는 치명적이지 않음 - 로그만 남김
        logger.warning(f"Failed to refresh ontology cache ({context}): {e}")
        return False
