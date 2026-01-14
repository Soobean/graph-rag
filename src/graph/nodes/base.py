"""
Base Node Abstract Class

모든 LangGraph 노드가 따라야 할 표준 인터페이스를 정의합니다.
문서(docs/architecture/05-design-decisions.md)의 설계에 따라 구현됩니다.
"""

import logging
from abc import ABC, abstractmethod

from src.graph.state import GraphRAGState


class BaseNode[T](ABC):
    """
    모든 LangGraph 노드가 상속해야 할 추상 클래스

    설계 원칙:
    - 각 노드는 독립적인 컴포넌트로 재사용 가능
    - 의존성은 생성자에서 주입받음
    - 입력 필드를 명시적으로 선언

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
        """필요한 State 필드 목록"""
        ...

    def validate_input(self, state: GraphRAGState) -> bool:
        """
        입력 State 검증

        Args:
            state: 현재 그래프 상태

        Returns:
            검증 성공 여부
        """
        missing_keys = [key for key in self.input_keys if key not in state]
        if missing_keys:
            self._logger.warning(f"Missing required keys: {missing_keys}")
            return False
        return True

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

    async def __call__(self, state: GraphRAGState) -> T:
        """
        노드 실행 (Template Method Pattern)

        1. 입력 검증
        2. 처리 실행
        3. 에러 핸들링

        Args:
            state: 현재 그래프 상태

        Returns:
            업데이트할 State 필드들 (T 타입)
        """
        self._logger.debug(f"Node '{self.name}' started")

        # 입력 검증 (선택적 - 검증 실패해도 진행)
        if not self.validate_input(state):
            self._logger.warning(
                f"Input validation failed for node '{self.name}', proceeding anyway"
            )

        try:
            result = await self._process(state)
            self._logger.debug(f"Node '{self.name}' completed successfully")
            return result
        except Exception as e:
            self._logger.error(f"Node '{self.name}' failed: {e}")
            raise

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
