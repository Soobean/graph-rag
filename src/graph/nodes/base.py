"""
Base Node Abstract Class

모든 LangGraph 노드가 따라야 할 표준 인터페이스를 정의합니다.
문서(docs/architecture/05-design-decisions.md)의 설계에 따라 구현됩니다.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from src.graph.state import GraphRAGState

# 노드 카테고리별 기본 타임아웃 (초)
DEFAULT_TIMEOUT = 30  # LLM 호출 포함 노드
DB_TIMEOUT = 15  # DB 전용 노드
CPU_TIMEOUT = 10  # CPU 전용 노드 (온톨로지 확장 등)


class BaseNode[T](ABC):
    """
    모든 LangGraph 노드가 상속해야 할 추상 클래스

    설계 원칙:
    - 각 노드는 독립적인 컴포넌트로 재사용 가능
    - 의존성은 생성자에서 주입받음
    - 입력 필드를 명시적으로 선언
    - timeout_seconds로 노드별 실행 시간 제한 (LLM hang 방지)

    Usage:
        class MyNode(BaseNode[MyNodeUpdate]):
            @property
            def name(self) -> str:
                return "my_node"

            @property
            def input_keys(self) -> list[str]:
                return ["question"]

            async def _process(self, state: GraphRAGState) -> MyNodeUpdate:
                # 실제 처리 로직
                return {"result": "...", "execution_path": ["my_node"]}
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """노드 고유 이름 (execution_path에 기록됨)"""
        ...

    @property
    @abstractmethod
    def input_keys(self) -> list[str]:
        """필요한 State 필드 목록 (문서화 용도)"""
        ...

    @property
    def timeout_seconds(self) -> float:
        """노드 실행 타임아웃 (초). 서브클래스에서 오버라이드 가능."""
        return DEFAULT_TIMEOUT

    @abstractmethod
    async def _process(self, state: GraphRAGState) -> T:
        """
        노드의 실제 처리 로직 (서브클래스에서 구현)

        Args:
            state: 현재 그래프 상태

        Returns:
            업데이트할 State 필드들 (T 타입)
        """
        ...

    async def __call__(self, state: GraphRAGState) -> T | dict[str, Any]:
        """노드 실행 (타임아웃 적용)"""
        self._logger.debug(f"Node '{self.name}' started")
        try:
            result = await asyncio.wait_for(
                self._process(state),
                timeout=self.timeout_seconds,
            )
            self._logger.debug(f"Node '{self.name}' completed")
            return result
        except TimeoutError:
            self._logger.error(
                f"Node '{self.name}' timed out after {self.timeout_seconds}s"
            )
            return {
                "error": f"처리 시간이 초과되었습니다 ({self.name}: {self.timeout_seconds}초)",
                "execution_path": [f"{self.name}_timeout"],
            }
        except Exception as e:
            self._logger.error(f"Node '{self.name}' failed: {e}")
            raise

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
