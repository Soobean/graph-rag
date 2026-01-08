"""
Entity Extractor Node

질문에서 엔티티(사람, 조직, 날짜 등)를 추출합니다.
"""

import logging

from src.domain.types import EntityExtractorUpdate
from src.graph.state import GraphRAGState
from src.graph.utils import format_chat_history
from src.repositories.llm_repository import LLMRepository

logger = logging.getLogger(__name__)


class EntityExtractorNode:
    """엔티티 추출 노드"""

    # 기본 엔티티 타입
    DEFAULT_ENTITY_TYPES = [
        "Person",  # 사람
        "Organization",  # 조직/회사
        "Department",  # 부서
        "Position",  # 직책/직급
        "Project",  # 프로젝트
        "Skill",  # 기술/스킬
        "Location",  # 장소
        "Date",  # 날짜
    ]

    def __init__(
        self,
        llm_repository: LLMRepository,
        entity_types: list[str] | None = None,
    ):
        self._llm = llm_repository
        self._entity_types = entity_types or self.DEFAULT_ENTITY_TYPES

    async def __call__(self, state: GraphRAGState) -> EntityExtractorUpdate:
        """
        엔티티 추출

        Args:
            state: 현재 파이프라인 상태

        Returns:
            업데이트할 상태 딕셔너리
        """
        question = state["question"]
        logger.info(f"Extracting entities from: {question[:50]}...")

        try:
            # 대화 기록 포맷팅 (현재 질문 제외)
            messages = state.get("messages", [])
            chat_history = format_chat_history(messages)

            result = await self._llm.extract_entities(
                question=question,
                entity_types=self._entity_types,
                chat_history=chat_history,
            )

            raw_entities = result.get("entities", [])

            # list[dict] -> dict[str, list[str]] 변환
            # GraphRAGState.entities는 {'type': ['value1', 'value2']} 형태임
            structured_entities: dict[str, list[str]] = {}

            count = 0
            for entity in raw_entities:
                entity_type = entity.get("type", "Unknown")
                value = entity.get("normalized") or entity.get("value")

                if value:
                    if entity_type not in structured_entities:
                        structured_entities[entity_type] = []
                    structured_entities[entity_type].append(str(value))
                    count += 1

            logger.info(
                f"Extracted {count} entities in {len(structured_entities)} categories"
            )

            return {
                "entities": structured_entities,
                "execution_path": ["entity_extractor"],
            }

        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return {
                "entities": {},
                "error": f"Entity extraction failed: {e}",
                "execution_path": ["entity_extractor_error"],
            }
