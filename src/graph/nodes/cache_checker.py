"""
Cache Checker Node

질문-Cypher 캐시를 확인하여 유사 질문이 있으면 캐싱된 Cypher 쿼리를 재사용합니다.
캐시 히트 시 Cypher 생성 단계를 스킵하여 응답 시간을 단축합니다.
"""

from src.config import Settings
from src.domain.types import CacheCheckerUpdate
from src.graph.nodes.base import BaseNode
from src.graph.state import GraphRAGState
from src.repositories.llm_repository import LLMRepository
from src.repositories.query_cache_repository import QueryCacheRepository


class CacheCheckerNode(BaseNode[CacheCheckerUpdate]):
    """질문-Cypher 캐시 확인 노드"""

    def __init__(
        self,
        llm_repository: LLMRepository,
        cache_repository: QueryCacheRepository,
        settings: Settings,
    ):
        super().__init__()
        self._llm = llm_repository
        self._cache = cache_repository
        self._settings = settings

    @property
    def name(self) -> str:
        return "cache_checker"

    @property
    def input_keys(self) -> list[str]:
        return ["question"]


    async def _process(self, state: GraphRAGState) -> CacheCheckerUpdate:
        """
        질문에 대한 캐시 확인

        1. 질문 임베딩 생성
        2. 유사 캐시 조회
        3. 캐시 히트 시: 캐싱된 Cypher 쿼리 반환 + skip_generation=True
        4. 캐시 미스 시: 임베딩만 반환 (후속 노드에서 활용)

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state.get("question", "")
        self._logger.info(f"Checking cache for: {question[:50]}...")

        # Vector Search 비활성화 시 스킵
        if not self._settings.vector_search_enabled:
            self._logger.debug("Vector search disabled, skipping cache check")
            return CacheCheckerUpdate(
                question_embedding=None,
                cache_hit=False,
                cache_score=0.0,
                skip_generation=False,
                execution_path=[f"{self.name}_skipped"],
            )

        try:
            # 1. 질문 임베딩 생성
            embedding = await self._llm.get_embedding(question)
            self._logger.debug(f"Generated question embedding: dim={len(embedding)}")

            # 2. 캐시에서 유사 질문 검색
            cached = await self._cache.find_similar_query(embedding)

            if cached:
                # 캐시 히트
                self._logger.info(
                    f"Cache HIT: score={cached.score:.3f}, "
                    f"cached_question='{cached.question[:50]}...'"
                )
                return CacheCheckerUpdate(
                    question_embedding=embedding,
                    cache_hit=True,
                    cache_score=cached.score,
                    skip_generation=True,
                    cypher_query=cached.cypher_query,
                    cypher_parameters=cached.cypher_parameters,
                    execution_path=[f"{self.name}_hit"],
                )
            else:
                # 캐시 미스
                self._logger.info("Cache MISS: no similar query found")
                return CacheCheckerUpdate(
                    question_embedding=embedding,
                    cache_hit=False,
                    cache_score=0.0,
                    skip_generation=False,
                    execution_path=[f"{self.name}_miss"],
                )

        except Exception as e:
            self._logger.error(f"Cache check failed: {e}")
            # 캐시 실패 시에도 파이프라인 계속 진행 (graceful degradation)
            return CacheCheckerUpdate(
                question_embedding=None,
                cache_hit=False,
                cache_score=0.0,
                skip_generation=False,
                error=f"Cache check failed: {e}",
                execution_path=[f"{self.name}_error"],
            )
